"""
Institutional Pinbar VWAP Strategy
Based on:
1. Entry Long: Bullish Pin Bar + Price > VWAP
2. Entry Short: Bearish Pin Bar + Price < VWAP
3. Exit: SL, TP, EMA Crossover Reversal
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class InstitutionalStrategy(StrategyInterface):
    def __init__(self, ema_fast=5, ema_slow=13, sl_atr_mult=1.5, tp_rr=2.0):
        super().__init__("InstitutionalPinbarVWAP")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.sl_atr_mult = sl_atr_mult
        self.tp_rr = tp_rr
        self.current_status = "Initializing..."
        
        # State
        self.last_signal = None
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_vwap(self, df):
        """Calculate Intraday VWAP"""
        df = df.copy()
        
        df['date'] = df.index.date
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['pv'] = df['typical_price'] * df['Volume']
        
        # Group by date to reset VWAP daily
        df['cum_pv'] = df.groupby('date')['pv'].cumsum()
        df['cum_vol'] = df.groupby('date')['Volume'].cumsum()
        df['vwap'] = df['cum_pv'] / df['cum_vol']
        
        return df['vwap']

    def _calculate_rsi(self, series, period=14):
        """Calculate RSI"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _is_bullish_pin_bar(self, row):
        """
        Detect Bullish Pin Bar (Hammer):
        - Long lower wick (>= 51% of range)
        - Body in upper 25% of range
        """
        open_p = row['Open']
        close_p = row['Close']
        high_p = row['High']
        low_p = row['Low']
        
        total_range = high_p - low_p
        if total_range == 0:
            return False
            
        lower_wick = min(open_p, close_p) - low_p
        
        is_long_lower_wick = lower_wick >= (total_range * 0.51)
        is_upper_body = (high_p - max(open_p, close_p)) <= (total_range * 0.25)
        
        return is_long_lower_wick and is_upper_body

    def _is_bearish_pin_bar(self, row):
        """
        Detect Bearish Pin Bar (Shooting Star):
        - Long upper wick (>= 51% of range)
        - Body in lower 25% of range
        """
        open_p = row['Open']
        close_p = row['Close']
        high_p = row['High']
        low_p = row['Low']
        
        total_range = high_p - low_p
        if total_range == 0:
            return False
            
        upper_wick = high_p - max(open_p, close_p)
        
        is_long_upper_wick = upper_wick >= (total_range * 0.51)
        is_lower_body = (min(open_p, close_p) - low_p) <= (total_range * 0.25)
        
        return is_long_upper_wick and is_lower_body

    def detect_ema_crossover_reversal(self, df, direction='long'):
        """
        Check for EMA crossover reversal.
        - Long Exit: Fast EMA crosses below Slow EMA
        - Short Exit: Fast EMA crosses above Slow EMA
        """
        if len(df) < 2: 
            return False
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        if direction == 'long':
            # Cross under (exit long)
            return (prev['ema_fast'] > prev['ema_slow']) and (curr['ema_fast'] < curr['ema_slow'])
        else:
            # Cross over (exit short)
            return (prev['ema_fast'] < prev['ema_slow']) and (curr['ema_fast'] > curr['ema_slow'])

    def calculate_signal(self, df):
        """
        Returns:
        - 'buy': Long entry signal
        - 'sell': Short entry signal
        - 'exit_reversal': Exit signal (EMA crossover)
        - None: No action
        """
        if len(df) < 50:
            self.current_status = f"Warming up ({len(df)}/50)"
            return None
            
        df = df.copy()
        
        # Indicators
        df['vwap'] = self._calculate_vwap(df)
        df['ema_fast'] = df['Close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['Close'].ewm(span=self.ema_slow, adjust=False).mean()
        df['rsi'] = self._calculate_rsi(df['Close'])
        
        # ATR for Stop Loss
        df['tr'] = np.maximum(
            df['High'] - df['Low'],
            np.maximum(
                abs(df['High'] - df['Close'].shift(1)),
                abs(df['Low'] - df['Close'].shift(1))
            )
        )
        atr = df['tr'].rolling(14).mean().iloc[-1]
        
        curr = df.iloc[-1]
        close_p = curr['Close']
        vwap = curr['vwap']
        rsi = curr['rsi']
        
        rsi_str = f"{rsi:.1f}" if pd.notna(rsi) else "NaN"
        vwap_str = f"{vwap:.1f}" if pd.notna(vwap) else "NaN"
        self.current_status = f"Scanning... Price:{close_p:.1f} VWAP:{vwap_str} RSI:{rsi_str}"
        
        # EXIT LOGIC (EMA Reversal) - Check both directions
        if self.detect_ema_crossover_reversal(df, 'long'):
            self.last_signal_data['exit_type'] = 'long_reversal'
            return 'exit_reversal'
        if self.detect_ema_crossover_reversal(df, 'short'):
            self.last_signal_data['exit_type'] = 'short_reversal'
            return 'exit_reversal'
            
        if pd.isna(vwap) or pd.isna(rsi):
            return None

        # ============ LONG ENTRY LOGIC ============
        # Condition: Price > VWAP + Bullish Pin Bar
        # Optimization: RSI < 60 (Allow pullbacks)
        if close_p > vwap and rsi < 60:
            if self._is_bullish_pin_bar(curr):
                stop_loss = curr['Low'] - (0.5 * atr)
                risk = close_p - stop_loss
                target = close_p + (risk * self.tp_rr)
                
                self.last_signal_data = {
                    'side': 'buy',
                    'entry': close_p,
                    'stop_loss': stop_loss,
                    'take_profit': target,
                    'risk': risk
                }
                
                self.current_status = "BUY Signal: Better Pin Bar > VWAP"
                return 'buy'
        
        # ============ SHORT ENTRY LOGIC ============
        # Condition: Price < VWAP + Bearish Pin Bar
        # Optimization: RSI > 40 (Allow pullbacks)
        if close_p < vwap and rsi > 40:
            if self._is_bearish_pin_bar(curr):
                stop_loss = curr['High'] + (0.5 * atr)
                risk = stop_loss - close_p
                target = close_p - (risk * self.tp_rr)
                
                self.last_signal_data = {
                    'side': 'sell',
                    'entry': close_p,
                    'stop_loss': stop_loss,
                    'take_profit': target,
                    'risk': risk
                }
                
                self.current_status = "SELL Signal: Better Pin Bar < VWAP"
                return 'sell'
                
        return None

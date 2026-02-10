"""
Poor Low Target (Unfinished Auction) Strategy - 5m
Based on Strategy 20e24627 (Corrected)

Strategy Logic:
- Core Pattern: Poor Low (Bearish Signal) / Poor High (Bullish Signal)
  * Logic derived from 'detect_poor_high_low_bearish' in indicators.py (Detects Poor Low -> Short)
  * Logic derived from 'detect_poor_high_low_bullish' in indicators.py (Detects Poor High -> Long)
- Filter: Price within 0.5% of VWAP (CRITICAL)
- Exit: Stop Loss, Take Profit (4.8R), EMA 9/34 Crossover Reversal

Original Logic Source:
- detect_poor_high_low_bearish: Checks for Local Low (5 bars) with Wick/Body ratio < 0.05
- Market Expectation: "Unfinished Auction" implies price will trade through the level.
  - Poor Low -> Price needs to go lower -> Short.
  - Poor High -> Price needs to go higher -> Long.
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface


class PoorLowStrategy(StrategyInterface):
    def __init__(self, ema_fast=9, ema_slow=34, lookback_period=5, vwap_band=0.005, tp_rr=4.8):
        super().__init__("Poor Low Target")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.lookback_period = lookback_period # 5 bars from indicators.py
        self.vwap_band = vwap_band  # 0.5% = 0.005
        self.tp_rr = tp_rr  # 4.8x risk:reward
        
        self.current_status = "Initializing..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_vwap(self, df):
        """Calculate Intraday VWAP"""
        df = df.copy()
        if 'date' not in df.columns:
            df['date'] = df.index.date
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['pv'] = df['typical_price'] * df['Volume']
        df['cum_pv'] = df.groupby('date')['pv'].cumsum()
        df['cum_vol'] = df.groupby('date')['Volume'].cumsum()
        return df['cum_pv'] / (df['cum_vol'] + 1e-10)

    def _calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()

    def detect_poor_low_bearish_logic(self, df, idx):
        """
        Exact logic from indicators.py: detect_poor_high_low_bearish
        Detects a POOR LOW which is a BEARISH SIGNAL (Breakout/Continuation Lower).
        """
        # Need 5 bars lookback
        if idx < 5: return False
        
        # 1. Local Low check: low[i] <= min(low[i-5:i])
        recent_lows = df['Low'].iloc[idx-5:idx]
        current_low = df['Low'].iloc[idx]
        
        if current_low <= recent_lows.min():
            open_p = df['Open'].iloc[idx]
            close_p = df['Close'].iloc[idx]
            
            body_low = min(open_p, close_p)
            wick_size = body_low - current_low
            body_size = abs(close_p - open_p)
            
            # 2. Wick Ratio: (Lower Wick / Body) < 0.05
            # Note: Requires body_size > 0
            if body_size > 0:
                ratio = wick_size / body_size
                if ratio < 0.05:
                    return True
        return False

    def detect_poor_high_bullish_logic(self, df, idx):
        """
        Exact logic from indicators.py: detect_poor_high_low_bullish
        Detects a POOR HIGH which is a BULLISH SIGNAL (Breakout/Continuation Higher).
        """
        if idx < 5: return False
        
        recent_highs = df['High'].iloc[idx-5:idx]
        current_high = df['High'].iloc[idx]
        
        if current_high >= recent_highs.max():
            open_p = df['Open'].iloc[idx]
            close_p = df['Close'].iloc[idx]
            
            body_high = max(open_p, close_p)
            wick_size = current_high - body_high
            body_size = abs(close_p - open_p)
            
            if body_size > 0:
                ratio = wick_size / body_size
                if ratio < 0.05:
                    return True
        return False

    def price_within_vwap_band(self, close, vwap):
        """Check if price is within the VWAP band (0.5%)"""
        if pd.isna(vwap) or vwap == 0:
            return False
        distance_pct = abs(close - vwap) / vwap
        return distance_pct < self.vwap_band

    def detect_ema_crossover_reversal(self, df, direction):
        """
        Exit Logic: EMA 9/34 Crossover Reversal
        """
        if len(df) < 2: return False
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        if direction == 'sell': # We are Short, Exit if Bullish Crossover (Fast > Slow)
            return (prev['ema_fast'] < prev['ema_slow']) and (curr['ema_fast'] > curr['ema_slow'])
        else: # We are Long, Exit if Bearish Crossover (Fast < Slow)
             return (prev['ema_fast'] > prev['ema_slow']) and (curr['ema_fast'] < curr['ema_slow'])

    def calculate_signal(self, df):
        if len(df) < 50:
            self.current_status = f"Warming up ({len(df)}/50 bars)"
            return None

        df = df.copy()
        df['vwap'] = self._calculate_vwap(df)
        df['ema_fast'] = self._calculate_ema(df['Close'], self.ema_fast)
        df['ema_slow'] = self._calculate_ema(df['Close'], self.ema_slow)
        
        curr_idx = len(df) - 1
        curr = df.iloc[-1]
        close_p = curr['Close']
        vwap = curr['vwap']
        
        vwap_str = f"{vwap:.1f}" if pd.notna(vwap) and vwap != 0 else "NaN"
        self.current_status = f"Price:{close_p:.1f} VWAP:{vwap_str}"

        # 1. EXIT CHECKS
        if self.detect_ema_crossover_reversal(df, 'sell'): # Exit Short
            self.last_signal_data['exit_type'] = 'short_reversal'
            return 'exit_reversal'
        if self.detect_ema_crossover_reversal(df, 'buy'): # Exit Long
            self.last_signal_data['exit_type'] = 'long_reversal'
            return 'exit_reversal'

        # 2. VWAP FILTER
        if not self.price_within_vwap_band(close_p, vwap):
             dist_pct = abs(close_p - vwap) / vwap * 100 if vwap != 0 else 0
             self.current_status = f"Outside VWAP Band ({dist_pct:.2f}% > 0.5%)"
             return None

        # 3. ENTRY CHECKS
        
        # Check Short (Poor Low)
        if self.detect_poor_low_bearish_logic(df, curr_idx):
            # Short Setup
            stop_loss = curr['High'] # Stop above the candle
            entry_price = close_p
            risk = stop_loss - entry_price
            if risk <= 0: risk = entry_price * 0.001
            
            target = entry_price - (risk * self.tp_rr) 
            
            self.last_signal_data = {
                'side': 'sell',
                'entry': entry_price,
                'stop_loss': stop_loss,
                'take_profit': target,
                'risk': risk,
                'pattern': 'Poor Low (Unfinished Auction)'
            }
            self.current_status = f"SELL Signal: Poor Low at {curr['Low']:.1f}"
            return 'sell'
            
        # Check Long (Poor High) - DISABLED as per Corrected Strategy 20e24627 (Short Only)
        # if self.detect_poor_high_bullish_logic(df, curr_idx):
        #     # Long Setup
        #     stop_loss = curr['Low']
        #     entry_price = close_p
        #     risk = entry_price - stop_loss
        #     if risk <= 0: risk = entry_price * 0.001
            
        #     target = entry_price + (risk * self.tp_rr)
            
        #     self.last_signal_data = {
        #         'side': 'buy',
        #         'entry': entry_price,
        #         'stop_loss': stop_loss,
        #         'take_profit': target,
        #         'risk': risk,
        #         'pattern': 'Poor High (Unfinished Auction)'
        #     }
        #     self.current_status = f"BUY Signal: Poor High at {curr['High']:.1f}"
        #     return 'buy'
            
        return None

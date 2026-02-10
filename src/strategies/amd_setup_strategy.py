"""
AMD Setup Strategy (Accum-Manip-Dist)_5m_100
Bidirectional AMD Strategy for NIFTY50-INDEX

Algorithmic Logic & Concepts:

POWER OF 3 (AMD): Accumulation-Manipulation-Distribution pattern.
- Catching the 'Judas Swing' where price fakes a move before the real trend.

BEARISH (SHORT) Entry:
- detect_amd_setup_bearish: Price accumulates → manipulates UP (Judas Swing) → distributes DOWN
- detect_premium_zone: Price in upper 50% of dealing range
- rsi_crossed_below_70: RSI(14) just crossed below 70

BULLISH (LONG) Entry:
- detect_amd_setup_bullish: Price accumulates → manipulates DOWN (Judas Swing) → distributes UP
- detect_discount_zone: Price in lower 50% of dealing range
- rsi_crossed_above_30: RSI(14) just crossed above 30

Exit Logic:
- stop_loss_hit: Beyond the manipulation swing
- take_profit_hit: 1:2 Risk-Reward ratio
- end_of_session: Square off at 15:15 IST
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface


class AMDSetupStrategy(StrategyInterface):
    """AMD Setup Strategy supporting both bullish and bearish setups."""
    
    def __init__(self, rsi_period=14, lookback_period=20, range_period=50, rr_ratio=2.0):
        super().__init__("AMD Setup")
        self.rsi_period = rsi_period
        self.lookback_period = lookback_period
        self.range_period = range_period
        self.rr_ratio = rr_ratio
        self.current_status = "Initializing..."
        self.last_signal_data = {}
    
    def get_status(self):
        return self.current_status
    
    def _calculate_rsi(self, series, period=14):
        """Calculate RSI indicator."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 0.0001)
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, df, period=14):
        """Calculate ATR for stop loss sizing."""
        high = df['High']
        low = df['Low']
        close = df['Close']
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def _identify_swings(self, df, period=5):
        """Identify swing highs and lows for AMD detection."""
        highs = df['High'].rolling(window=period*2+1, center=True).apply(
            lambda x: x.iloc[period] == x.max(), raw=False
        )
        lows = df['Low'].rolling(window=period*2+1, center=True).apply(
            lambda x: x.iloc[period] == x.min(), raw=False
        )
        return highs.fillna(0).astype(bool), lows.fillna(0).astype(bool)
    
    def detect_amd_setup_bearish(self, df):
        """
        Detect Bearish AMD Pattern (Judas Swing UP then Distribution DOWN).
        
        Pattern:
        1. Accumulation: Range-bound/consolidation period
        2. Manipulation: Fake breakout UP (Judas Swing) - sweeps highs
        3. Distribution: Reversal and move DOWN
        
        Returns: (is_bearish_amd, manipulation_high)
        """
        if len(df) < self.lookback_period + 10:
            return False, None
        
        recent = df.iloc[-self.lookback_period:]
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Find recent swing high (manipulation point)
        range_high = recent['High'].max()
        range_low = recent['Low'].min()
        range_size = range_high - range_low
        
        # Accumulation: Tight range before (low volatility)
        accum_window = df.iloc[-self.lookback_period:-5]
        accum_range = accum_window['High'].max() - accum_window['Low'].min()
        
        # Manipulation: Recent high sweep (price spiked above range)
        last_5 = df.iloc[-5:]
        manipulation_high = last_5['High'].max()
        swept_high = manipulation_high >= range_high
        
        # Distribution: Current/recent candle shows reversal (close below previous close)
        distributing = curr['Close'] < prev['Close'] and curr['Close'] < manipulation_high
        
        # Confirm rejection (upper wick rejection)
        curr_body = abs(curr['Close'] - curr['Open'])
        curr_upper_wick = curr['High'] - max(curr['Open'], curr['Close'])
        rejection = curr_upper_wick > curr_body * 0.5
        
        is_bearish_amd = swept_high and distributing and rejection
        
        return is_bearish_amd, manipulation_high
    
    def detect_amd_setup_bullish(self, df):
        """
        Detect Bullish AMD Pattern (Judas Swing DOWN then Distribution UP).
        
        Pattern:
        1. Accumulation: Range-bound/consolidation period
        2. Manipulation: Fake breakdown DOWN (Judas Swing) - sweeps lows
        3. Distribution: Reversal and move UP
        
        Returns: (is_bullish_amd, manipulation_low)
        """
        if len(df) < self.lookback_period + 10:
            return False, None
        
        recent = df.iloc[-self.lookback_period:]
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Find recent swing low (manipulation point)
        range_high = recent['High'].max()
        range_low = recent['Low'].min()
        
        # Manipulation: Recent low sweep (price spiked below range)
        last_5 = df.iloc[-5:]
        manipulation_low = last_5['Low'].min()
        swept_low = manipulation_low <= range_low
        
        # Distribution: Current/recent candle shows reversal (close above previous close)
        distributing = curr['Close'] > prev['Close'] and curr['Close'] > manipulation_low
        
        # Confirm rejection (lower wick rejection)
        curr_body = abs(curr['Close'] - curr['Open'])
        curr_lower_wick = min(curr['Open'], curr['Close']) - curr['Low']
        rejection = curr_lower_wick > curr_body * 0.5
        
        is_bullish_amd = swept_low and distributing and rejection
        
        return is_bullish_amd, manipulation_low
    
    def detect_premium_zone(self, df):
        """Price in upper 50% of recent range (for short entries)."""
        curr_price = df['Close'].iloc[-1]
        recent = df.iloc[-self.range_period:]
        r_high = recent['High'].max()
        r_low = recent['Low'].min()
        r_mid = (r_high + r_low) / 2
        
        is_premium = curr_price > r_mid
        return is_premium, r_low, r_high
    
    def detect_discount_zone(self, df):
        """Price in lower 50% of recent range (for long entries)."""
        curr_price = df['Close'].iloc[-1]
        recent = df.iloc[-self.range_period:]
        r_high = recent['High'].max()
        r_low = recent['Low'].min()
        r_mid = (r_high + r_low) / 2
        
        is_discount = curr_price < r_mid
        return is_discount, r_low, r_high
    
    def calculate_signal(self, df):
        """
        Main signal calculation.
        Returns: 'buy', 'sell', or None
        """
        min_bars = max(self.range_period, self.lookback_period, 60)
        if len(df) < min_bars:
            self.current_status = f"Warming up ({len(df)}/{min_bars} bars)"
            return None
        
        df = df.copy()
        df['rsi'] = self._calculate_rsi(df['Close'], self.rsi_period)
        df['atr'] = self._calculate_atr(df)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        close_p = curr['Close']
        rsi = curr['rsi']
        prev_rsi = prev['rsi']
        atr = curr['atr']
        
        # Check for BEARISH (SHORT) Setup
        rsi_crossed_below_70 = prev_rsi >= 70 and rsi < 70
        is_premium, r_low, r_high = self.detect_premium_zone(df)
        is_bearish_amd, manipulation_high = self.detect_amd_setup_bearish(df)
        
        if rsi_crossed_below_70 and is_premium and is_bearish_amd:
            # SHORT Signal
            stop_loss = manipulation_high + (atr * 0.5)  # Above manipulation high
            risk = stop_loss - close_p
            if risk <= 0:
                risk = atr
            take_profit = close_p - (risk * self.rr_ratio)
            
            self.last_signal_data = {
                'side': 'sell',
                'entry': close_p,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'pattern': 'AMD Bearish (Judas Swing Up)'
            }
            self.current_status = f"SHORT Signal: AMD Bearish at {close_p:.1f}, RSI:{rsi:.1f}"
            return 'sell'
        
        # Check for BULLISH (LONG) Setup
        rsi_crossed_above_30 = prev_rsi <= 30 and rsi > 30
        is_discount, r_low, r_high = self.detect_discount_zone(df)
        is_bullish_amd, manipulation_low = self.detect_amd_setup_bullish(df)
        
        if rsi_crossed_above_30 and is_discount and is_bullish_amd:
            # LONG Signal
            stop_loss = manipulation_low - (atr * 0.5)  # Below manipulation low
            risk = close_p - stop_loss
            if risk <= 0:
                risk = atr
            take_profit = close_p + (risk * self.rr_ratio)
            
            self.last_signal_data = {
                'side': 'buy',
                'entry': close_p,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'pattern': 'AMD Bullish (Judas Swing Down)'
            }
            self.current_status = f"LONG Signal: AMD Bullish at {close_p:.1f}, RSI:{rsi:.1f}"
            return 'buy'
        
        # Update scanning status
        zone = "Premium" if is_premium else "Discount" if is_discount else "Mid"
        self.current_status = f"Scanning... RSI:{rsi:.1f} Zone:{zone}"
        return None

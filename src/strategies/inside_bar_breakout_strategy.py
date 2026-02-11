"""
Inside Bar b3 Breakout Short_15m_150
Algorithmic Logic & Concepts

Entry Logic:
- detect_inside_bar: Mother bar contains child bar (High/Low within prior bar)
- breakout_below_20bar_low: Price breaks below 20-bar low
- price_above_vwap: Price is above VWAP (selling into strength)
- rsi_crossed_below_70: RSI crossed below 70 (overbought rejection)
- is_in_kill_zone: Trade during high-volume market hours (open/close)

Exit Logic:
- stop_loss_hit: ATR-based stop loss above entry
- take_profit_hit: 1:2 Risk-Reward target

Institutional Concepts:
* KILL ZONE (TIME): Trade execution restricted to high-volume market hours
  - Morning: 09:15 - 10:30 IST (Open volatility)
  - Afternoon: 14:00 - 15:15 IST (Close volatility)
"""
import pandas as pd
import numpy as np
from datetime import datetime, time
from src.interfaces.strategy_interface import StrategyInterface


class InsideBarBreakoutStrategy(StrategyInterface):
    """Inside Bar b3 Breakout Short - 15m Strategy"""
    
    def __init__(self, rsi_period=14, lookback_period=20, atr_period=14, rr_ratio=2.0):
        super().__init__("Inside Bar b3 Breakout")
        self.rsi_period = rsi_period
        self.lookback_period = lookback_period  # 20-bar low lookback
        self.atr_period = atr_period
        self.rr_ratio = rr_ratio
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        
        # Kill Zone Times (IST)
        self.kill_zones = [
            (time(9, 15), time(10, 30)),   # Morning session
            (time(14, 0), time(15, 15))    # Afternoon session
        ]
    
    def get_status(self):
        return self.current_status
    
    def _calculate_rsi(self, series, period=14):
        """Calculate RSI indicator"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_vwap(self, df):
        """Calculate Intraday VWAP"""
        df = df.copy()
        if 'date' not in df.columns:
            df['date'] = df.index.date
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['pv'] = df['typical_price'] * df['Volume']
        df['cum_pv'] = df.groupby('date')['pv'].cumsum()
        df['cum_vol'] = df.groupby('date')['Volume'].cumsum()
        return df['cum_pv'] / df['cum_vol']
    
    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close'].shift(1)
        
        tr = pd.concat([
            high - low,
            abs(high - close),
            abs(low - close)
        ], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean()
    
    def detect_inside_bar(self, df):
        """
        Detect Inside Bar Pattern on PREVIOUS Bar:
        - Prev bar (T-1) High < Mother bar (T-2) High
        - Prev bar (T-1) Low > Mother bar (T-2) Low
        - Allows Current Bar (T) to be the Breakout bar
        
        Returns: (is_inside_bar, mother_bar_high, mother_bar_low)
        """
        if len(df) < 3:
            return False, 0, 0
        
        prev = df.iloc[-2]   # Inside Bar Candidate
        mother = df.iloc[-3] # Mother Bar Candidate
        
        is_inside = (prev['High'] < mother['High']) and (prev['Low'] > mother['Low'])
        
        return is_inside, mother['High'], mother['Low']
    
    def breakout_below_20bar_low(self, df):
        """
        Check if current price breaks below the 20-bar low.
        
        Returns: (is_breakout, low_level)
        """
        if len(df) < self.lookback_period + 1:
            return False, 0
        
        curr_low = df['Low'].iloc[-1]
        # Exclude current bar from lookback
        past_df = df.iloc[-(self.lookback_period + 1):-1]
        low_20 = past_df['Low'].min()
        
        # Wick Breakout (Stop Entry trigger)
        is_breakout = curr_low < low_20
        
        return is_breakout, low_20
    
    def price_above_vwap(self, df):
        """
        Check if current price is above VWAP.
        Selling into strength = reversal trade setup.
        
        Returns: (is_above_vwap, vwap_value)
        """
        vwap = self._calculate_vwap(df)
        curr_close = df['Close'].iloc[-1]
        curr_vwap = vwap.iloc[-1]
        
        return curr_close > curr_vwap, curr_vwap
    
    def rsi_crossed_below_70(self, df):
        """
        Check if RSI is in bearish territory (below 70).
        Original strict 'cross' condition was too restrictive for 15m inside bars.
        
        Returns: (is_below_70, current_rsi)
        """
        rsi = self._calculate_rsi(df['Close'], self.rsi_period)
        
        if len(rsi) < 1:
            return False, 0
        
        curr_rsi = rsi.iloc[-1]
        
        # Simple condition: RSI < 70 (Bearish bias or not overbought)
        return (curr_rsi < 70), curr_rsi
    
    def is_in_kill_zone(self, df):
        """
        Check if current time is within Kill Zone (high-volume hours).
        
        Kill Zones (IST):
        - Morning: 09:15 - 10:30 (Open volatility)
        - Afternoon: 14:00 - 15:15 (Close volatility)
        
        Returns: (in_kill_zone, current_time)
        """
        try:
            curr_time = df.index[-1]
            if hasattr(curr_time, 'time'):
                current_time = curr_time.time()
            else:
                current_time = datetime.now().time()
            
            for start, end in self.kill_zones:
                if start <= current_time <= end:
                    return True, current_time
            
            return False, current_time
        except Exception:
            return False, None
    
    def calculate_signal(self, df):
        """
        Calculate trading signal based on all entry conditions.
        
        Entry Logic (ALL must be True for SHORT signal):
        1. detect_inside_bar - Inside bar pattern detected
        2. breakout_below_20bar_low - Price breaks below 20-bar low
        3. price_above_vwap - Price above VWAP (selling into strength)
        4. rsi_crossed_below_70 - RSI crossed below 70
        5. is_in_kill_zone - Within high-volume trading hours
        
        Returns: 'sell' for SHORT entry, None otherwise
        """
        min_bars = max(self.lookback_period, self.rsi_period, 50)
        
        if len(df) < min_bars:
            self.current_status = f"Warming up ({len(df)}/{min_bars} bars)"
            return None
        
        df = df.copy()
        
        # Calculate indicators
        df['rsi'] = self._calculate_rsi(df['Close'], self.rsi_period)
        df['vwap'] = self._calculate_vwap(df)
        df['atr'] = self._calculate_atr(df, self.atr_period)
        
        curr = df.iloc[-1]
        close_p = curr['Close']
        rsi = curr['rsi']
        vwap = curr['vwap']
        atr = curr['atr']
        
        # Check each condition
        # 1. Kill Zone Check (most restrictive filter first)
        in_kill_zone, current_time = self.is_in_kill_zone(df)
        if not in_kill_zone:
            time_str = current_time.strftime('%H:%M') if current_time else "Unknown"
            self.current_status = f"Outside Kill Zone ({time_str}). Waiting..."
            return None
        
        # 2. Inside Bar Check
        is_inside_bar, mother_high, mother_low = self.detect_inside_bar(df)
        if not is_inside_bar:
            self.current_status = f"Scanning... RSI:{rsi:.1f} | No Inside Bar pattern."
            return None
        
        # 3. RSI Crossed Below 70
        rsi_crossed, curr_rsi = self.rsi_crossed_below_70(df)
        if not rsi_crossed:
            self.current_status = f"Inside Bar detected. RSI:{curr_rsi:.1f} (Waiting for cross < 70)."
            return None
        
        # 4. Price Above VWAP
        above_vwap, vwap_val = self.price_above_vwap(df)
        if not above_vwap:
            self.current_status = f"Inside Bar + RSI cross. Price below VWAP (Filter fail)."
            return None
        
        # 5. Breakout Below 20-Bar Low
        is_breakout, low_20 = self.breakout_below_20bar_low(df)
        if not is_breakout:
            self.current_status = f"Inside Bar + RSI + VWAP . Awaiting breakout < {low_20:.1f}"
            return None
        
        # ALL CONDITIONS MET - GENERATE SHORT SIGNAL
        self.current_status = f" SHORT SIGNAL: Inside Bar Breakout @ {close_p:.1f}"
        
        # Entry Price (Simulating Stop Order at Breakout Level)
        entry_price = low_20
        
        # Calculate Stop Loss and Take Profit
        # Stop Loss: Above mother bar high + buffer (0.5 ATR)
        stop_loss = mother_high + (0.5 * atr)
        risk = stop_loss - entry_price
        
        # Ensure positive risk
        if risk <= 0:
            risk = atr
            stop_loss = entry_price + risk
        
        # Take Profit: 1:2 Risk-Reward
        take_profit = entry_price - (risk * self.rr_ratio)
        
        self.last_signal_data = {
            'side': 'sell',
            'entry': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk': risk,
            'pattern': 'Inside Bar Breakout Short',
            'mother_bar_high': mother_high,
            'mother_bar_low': mother_low,
            '20bar_low': low_20,
            'rsi': curr_rsi,
            'vwap': vwap_val
        }
        
        return 'sell'

import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class StopsHuntStrategy(StrategyInterface):
    def __init__(self, ema_fast=9, ema_slow=34, lookback=50, atr_period=14, tp_rr=4.9):
        super().__init__("Stops Hunt Short")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.lookback = lookback  # PDF uses 50 for premium zone
        self.atr_period = atr_period
        self.tp_rr = tp_rr
        self.current_status = "Monitoring..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_indicators(self, df):
        df = df.copy()
        # 1. EMAs for Direction (per Corrected Backtest logic)
        df['ema_f'] = df['Close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_s'] = df['Close'].ewm(span=self.ema_slow, adjust=False).mean()
        
        # 2. ATR for Stop Loss
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean()
        
        # 3. Premium Zone (50-bar range as per Corrected Backtest)
        df['rolling_high'] = df['High'].rolling(window=self.lookback).max()
        df['rolling_low'] = df['Low'].rolling(window=self.lookback).min()
        df['midpoint'] = (df['rolling_high'] + df['rolling_low']) / 2
        
        return df

    def detect_stops_hunt_bearish(self, df):
        """
        Bearish Stop Hunt: High sweeps previous high and reclaims (reverses).
        """
        if len(df) < 3: return False
        target_high = df['High'].iloc[-3]  # idx-2
        curr_high = df['High'].iloc[-1]
        curr_close = df['Close'].iloc[-1]
        curr_open = df['Open'].iloc[-1]
        
        sweep = curr_high > target_high
        reclaim = curr_close < target_high
        is_red = curr_close < curr_open
        return sweep and reclaim and is_red

    def detect_stops_hunt_bullish(self, df):
        """
        Bullish Stop Hunt: Low sweeps previous low and reclaims (reverses).
        """
        if len(df) < 3: return False
        target_low = df['Low'].iloc[-3]  # idx-2
        curr_low = df['Low'].iloc[-1]
        curr_close = df['Close'].iloc[-1]
        curr_open = df['Open'].iloc[-1]
        
        sweep = curr_low < target_low
        reclaim = curr_close > target_low
        is_green = curr_close > curr_open
        return sweep and reclaim and is_green

    def calculate_signal(self, df):
        if len(df) < 60:
            self.current_status = f"Warming up ({len(df)} bars)"
            return None

        # Strategy expects indicators
        if 'ema_f' not in df.columns:
            df = self._calculate_indicators(df)
            
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Status update
        self.current_status = f"Price:{curr['Close']:.1f} Fast:{curr['ema_f']:.1f} Slow:{curr['ema_s']:.1f}"

        # 1. TREND DETERMINATION
        trend_up = curr['ema_f'] > curr['ema_s']
        
        # 2. PATTERN DETECTION
        hunt_bear = self.detect_stops_hunt_bearish(df)
        hunt_bull = self.detect_stops_hunt_bullish(df)
        
        # 3. SIGNAL GENERATION (Trend Following)
        if trend_up and hunt_bull:
            entry_price = curr['Close']
            atr_stop = curr['atr'] * 1.5
            sl = entry_price - atr_stop
            tp = entry_price + (atr_stop * self.tp_rr)
            
            self.last_signal_data = {
                'side': 'buy',
                'entry': entry_price,
                'stop_loss': sl,
                'take_profit': tp,
                'risk': atr_stop,
                'pattern': 'Stops Hunt Long (Verified)'
            }
            self.current_status = f"BUY Signal Generated @ {entry_price:.1f}"
            return 'buy'
            
        elif not trend_up and hunt_bear:
            entry_price = curr['Close']
            atr_stop = curr['atr'] * 1.5
            sl = entry_price + atr_stop
            tp = entry_price - (atr_stop * self.tp_rr)
            
            self.last_signal_data = {
                'side': 'sell',
                'entry': entry_price,
                'stop_loss': sl,
                'take_profit': tp,
                'risk': atr_stop,
                'pattern': 'Stops Hunt Short (Verified)'
            }
            self.current_status = f"SELL Signal Generated @ {entry_price:.1f}"
            return 'sell'
            
        # 4. REVERSAL EXIT Detection
        if (prev['ema_f'] < prev['ema_s'] and curr['ema_f'] > curr['ema_s']):
            return 'exit_reversal'
            
        return None

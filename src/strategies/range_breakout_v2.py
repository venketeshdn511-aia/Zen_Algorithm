
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface
from datetime import time

class RangeBreakoutStrategyV2(StrategyInterface):
    """
    Regime-Aware Range Breakout (v2.1)
    
    Fixes:
    - Trade Limiters (Max 3 per day)
    - Volatility Gate (ATR based)
    - Noise Filter (Min SL 15 pts)
    - Capital Management (Move to BE @ 1R, Partial @ 2.5R)
    """
    
    def __init__(self, high_period=20, rsi_period=14, rsi_max=75, 
                 kill_zone=(time(13, 0), time(15, 15)),
                 risk_reward=5.4,
                 max_trades_per_day=3,
                 atr_gate_multiplier=0.5):
        super().__init__("RangeBreakoutV2")
        self.high_period = high_period
        self.rsi_period = rsi_period
        self.rsi_max = rsi_max
        self.kill_zone = kill_zone
        self.risk_reward = risk_reward
        self.max_trades_per_day = max_trades_per_day
        self.atr_gate_multiplier = atr_gate_multiplier
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        
        self.current_day = None
        self.daily_trade_count = 0

    def get_status(self):
        return self.current_status

    def _calculate_rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))

    def _calculate_atr(self, df, period=14):
        high_low = df['High'] - df['Low']
        high_cp = np.abs(df['High'] - df['Close'].shift(1))
        low_cp = np.abs(df['Low'] - df['Close'].shift(1))
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def calculate_signal(self, df):
        if len(df) < 200:
            return None

        curr_timestamp = df.index[-1]
        curr_day = curr_timestamp.date()
        curr_time = curr_timestamp.time()

        if self.current_day != curr_day:
            self.current_day = curr_day
            self.daily_trade_count = 0

        if self.daily_trade_count >= self.max_trades_per_day:
            return None

        if not (self.kill_zone[0] <= curr_time <= self.kill_zone[1]):
            return None

        df_15m = df.resample('15min').agg({
            'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()
        
        if len(df_15m) < self.high_period + 1:
            return None

        df_15m['high_20_prev'] = df_15m['High'].rolling(window=self.high_period).max().shift(1)
        df_15m['rsi_prev'] = self._calculate_rsi(df_15m['Close'], self.rsi_period).shift(1)
        
        df_5m = df.resample('5min').agg({'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
        df_5m['atr'] = self._calculate_atr(df_5m)
        df_5m['atr_median'] = df_5m['atr'].rolling(20).median()
        
        curr_atr = df_5m['atr'].iloc[-1]
        median_atr = df_5m['atr_median'].iloc[-1]
        
        if curr_atr < (median_atr * self.atr_gate_multiplier):
            self.current_status = "Skipping: Low Volatility"
            return None

        high_15m = df_15m['high_20_prev'].iloc[-1]
        rsi_15m = df_15m['rsi_prev'].iloc[-1]
        
        curr_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2]

        if rsi_15m < self.rsi_max:
            if curr_close > high_15m and prev_close <= high_15m:
                 sl_dist = max(15, curr_close - df['Low'].iloc[-5:].min())
                 stop_loss = curr_close - sl_dist
                 
                 self.last_signal_data = {
                    'side': 'buy',
                    'entry': curr_close,
                    'stop_loss': stop_loss,
                    'take_profit': curr_close + (sl_dist * self.risk_reward),
                    'timestamp': curr_timestamp,
                    # Metadata for Live Engine TSL tracking
                    'initial_risk': sl_dist,
                    'trail_after': 1.5,
                    'be_at': 1.0,
                    'partial_at': 2.5
                 }
                 
                 self.daily_trade_count += 1
                 return 'buy'

        return None

"""
Strategy: ORB Breakout Long (30m)_5m_150
Strategy ID: 1f3f7627

Core Logic:
1. Range Breakout: Price breaks above the 20-period High.
2. Volume Filter: Volume must be > 1.5x of its 20-period SMA.
3. Time Filter: Only entries after 09:45 IST (30m Opening Range).
4. Long Only: This specific variation is bullish.

Risk Management:
- Stop Loss: 1% from entry.
- Take Profit: 4.5x Risk Distance (RR 4.5).
- Secondary Exit: EMA 9 crosses below EMA 21.
- Global Exit: 15:15 IST.
"""

import pandas as pd
import numpy as np
from datetime import time
from src.interfaces.strategy_interface import StrategyInterface

class Strategy1f3f7627(StrategyInterface):
    def __init__(self, lookback=20, volume_mult=1.0, ema_fast=9, ema_slow=21, tp_rr=4.5, sl_points=15):
        super().__init__("Strategy 1f3f7627")
        self.lookback = lookback
        self.volume_mult = volume_mult
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.tp_rr = tp_rr
        self.sl_points = sl_points
        
        self.current_status = "Initializing..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_indicators(self, df):
        """Calculate logic indicators on 5m data"""
        df = df.copy()
        
        # 1. 20-period High/Low
        df['rolling_high'] = df['High'].rolling(window=self.lookback).max()
        df['rolling_low'] = df['Low'].rolling(window=self.lookback).min()
        
        # 2. Volume SMA
        df['vol_sma'] = df['Volume'].rolling(window=self.lookback).mean()
        
        # 3. Exit EMAs
        df['ema_f'] = df['Close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_s'] = df['Close'].ewm(span=self.ema_slow, adjust=False).mean()
        
        return df

    def calculate_signal(self, df):
        """
        Main signal calculation.
        Input: 5m DataFrame with capitalized columns 'Open', 'High', 'Low', 'Close', 'Volume'
        """
        if 'ema_f' not in df.columns and len(df) < self.lookback + 5:
            self.current_status = f"Warming up ({len(df)} bars)"
            return None

        # Optimization: Only calculate indicators if they don't exist
        # This allows pre-calculation in backtests for performance
        if 'ema_f' not in df.columns:
            df = self._calculate_indicators(df)
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        idx = len(df) - 1
        close_p = curr['Close']
        high_p = curr['High']
        vol = curr['Volume']
        
        # Time Filter (Entries after 09:45 IST)
        # Assuming index is DatetimeIndex
        ts = df.index[-1]
        entry_allowed_time = time(9, 15)
        
        # Status
        self.current_status = f"Price:{close_p:.0f} RHigh:{curr['rolling_high']:.0f} Vol:{vol:.0f}/{curr['vol_sma']*1.5:.0f}"

        # --- 1. EXIT CHECK (EMA Crossover) ---
        if (prev['ema_f'] >= prev['ema_s'] and curr['ema_f'] < curr['ema_s']):
            self.last_signal_data['exit_type'] = 'ema_reversal_long'
            return 'exit_reversal'
        if (prev['ema_f'] <= prev['ema_s'] and curr['ema_f'] > curr['ema_s']):
            self.last_signal_data['exit_type'] = 'ema_reversal_short'
            return 'exit_reversal'

        # --- 2. ENTRY CHECK (Long & Short) ---
        # a. Time Filter
        if ts.time() < entry_allowed_time:
            return None
            
        # b. Opening Range / 20-bar Breakout
        # PDF: Close > 20-bar High (Long), Close < 20-bar Low (Short)
        breakout_long = curr['Close'] > prev['rolling_high']
        breakout_short = curr['Close'] < prev['rolling_low']
        
        # c. Volume Filter
        vol_spike = vol > (curr['vol_sma'] * self.volume_mult)
        
        if vol_spike:
            if breakout_long:
                # Entry Signal Generated (Long)
                entry_price = close_p
                sl = entry_price - self.sl_points
                tp = entry_price + (self.sl_points * self.tp_rr) # RR 4.5
                
                self.last_signal_data = {
                    'side': 'buy',
                    'entry': entry_price,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'risk': self.sl_points,
                    'pattern': 'ORB Breakout Long'
                }
                self.current_status = f"BUY Signal: Breakout @ {entry_price:.0f}"
                return 'buy'
            
            elif breakout_short:
                # Entry Signal Generated (Short)
                entry_price = close_p
                sl = entry_price + self.sl_points
                tp = entry_price - (self.sl_points * self.tp_rr) # RR 4.5
                
                self.last_signal_data = {
                    'side': 'sell',
                    'entry': entry_price,
                    'stop_loss': sl,
                    'take_profit': tp,
                    'risk': self.sl_points,
                    'pattern': 'ORB Breakout Short'
                }
                self.current_status = f"SELL Signal: Breakout @ {entry_price:.0f}"
                return 'sell'
            
        return None

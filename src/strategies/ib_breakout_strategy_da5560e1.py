"""
Initial Balance Breakout Short Strategy (da5560e1)
Logic:
1. Identify the Initial Balance (IB) range: High and Low of the first 60 minutes of trading (09:15 to 10:15 IST).
2. Bearish Breakout: Signal 'sell' when Price < IB Low.
3. Exit Rules:
   - Stop Loss: 0.5% from entry price (Optimized).
   - Take Profit: 3.9x the stop loss distance.
4. Framework: 5m analysis, 1m entry precision.
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class IBBreakoutStrategy(StrategyInterface):
    def __init__(self, ib_start="09:15", ib_end="10:15", risk_reward=3.9):
        super().__init__("IBBreakout_da5560e1")
        self.ib_start = pd.to_datetime(ib_start).time()
        self.ib_end = pd.to_datetime(ib_end).time()
        self.risk_reward = risk_reward
        self.current_status = "Waiting for IB range..."
        self.last_signal_data = {}
        self.ib_high = None
        self.ib_low = None
        self.last_ib_date = None

    def get_status(self):
        return self.current_status

    def calculate_signal(self, df):
        if len(df) < 5: return None
        
        df = df.copy()
        curr_time = df.index[-1].time()
        curr_date = df.index[-1].date()
        curr_close = df.iloc[-1]['Close']
        
        # 1. Reset IB for new day
        if self.last_ib_date != curr_date:
            self.ib_high = None
            self.ib_low = None
            self.last_ib_date = curr_date
            
        # 2. Extract IB range during the first hour
        day_data = df[df.index.date == curr_date]
        ib_period_data = day_data[(day_data.index.time >= self.ib_start) & (day_data.index.time <= self.ib_end)]
        
        if not ib_period_data.empty:
            self.ib_high = ib_period_data['High'].max()
            self.ib_low = ib_period_data['Low'].min()
            
        if self.ib_low is None or curr_time <= self.ib_end:
            self.current_status = f"Defining IB... Range: {self.ib_high} - {self.ib_low}"
            return None

        self.current_status = f"IB Low: {self.ib_low:.1f}. Close: {curr_close:.1f}"

        # 3. ENTRY Check: Bearish Breakout
        if curr_close < self.ib_low:
            entry_p = curr_close
            # Stop loss: 0.5% (Optimized)
            stop_loss = entry_p * 1.005
            risk = stop_loss - entry_p
            # Take profit: 3.9x risk
            target = entry_p - (risk * self.risk_reward)
            
            self.last_signal_data = {
                'side': 'sell',
                'entry': entry_p,
                'stop_loss': stop_loss,
                'take_profit': target,
                'risk': risk,
                'pattern': 'IB Breakout Bearish'
            }
            self.current_status = " SELL SIGNAL: IB Breakout Bearish"
            return 'sell'

        return None

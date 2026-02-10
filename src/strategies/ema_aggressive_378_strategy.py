
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface
from datetime import time

class EMAAggressive378Strategy(StrategyInterface):
    """
    EMA Aggressive 378 Strategy (Long Only)
    
    Logic:
    - 5m Trend: EMA 8 > EMA 89
    - Price (1m close) > Both 5m EMAs
    - Confirmation: 1m Bullish Candle (Close > Open)
    - Risk Reward: 4.6
    - Stop Loss: Entry Candle Low (min 0.5 * ATR)
    """
    def __init__(self):
        super().__init__("EMA Aggressive 378")
        self.ema_fast_len = 8
        self.ema_slow_len = 89
        self.risk_reward = 4.6
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        # Parameters matching run_backtest_378_30days.py
        
    def get_status(self):
        return self.current_status
        
    def calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
        
    def calculate_atr(self, df, period=14):
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def calculate_signal(self, df):
        """
        Calculate entry signal based on 1m data (df)
        """
        if len(df) < 200:
            self.current_status = f"Warming ({len(df)}/200)"
            return None
            
        # Standardize columns to lowercase
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        
        # Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            # Try to convert if 'datetime' column exists, though usually index is expected
            if 'datetime' in df.columns:
                 df['ref_index'] = pd.to_datetime(df['datetime'])
                 df.set_index('ref_index', inplace=True)
            else:
                 self.current_status = "Error: DataFrame must have DatetimeIndex"
                 return None
        
        # Resample to 5m
        try:
            df_5m = df.resample('5min').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()
        except KeyError as e:
            self.current_status = f"Data Error: {e}"
            return None
        
        if len(df_5m) < 100:
             self.current_status = f"Warming 5m ({len(df_5m)}/100)"
             return None
             
        # Calculate 5m Indicators
        df_5m['ema_fast'] = self.calculate_ema(df_5m['close'], self.ema_fast_len)
        df_5m['ema_slow'] = self.calculate_ema(df_5m['close'], self.ema_slow_len)
        df_5m['atr'] = self.calculate_atr(df_5m, 14)
        
        # Use LAST COMPLETED 5m candle (index -2) for structure
        # Index -1 is the current forming candle
        prev_5m = df_5m.iloc[-2] 
        
        ema_f = prev_5m['ema_fast']
        ema_s = prev_5m['ema_slow']
        atr_val = prev_5m['atr']
        
        # 1m Data - Current forming or last completed? 
        # Usually signals are checked on the last completed 1m candle (index -1)
        curr_1m = df.iloc[-1]
        
        current_price = curr_1m['close']
        
        self.current_status = f"Monitor: Price {current_price:.2f} | 5m EMA8: {ema_f:.2f} | 5m EMA89: {ema_s:.2f}"
        
        # Rule 1: Trend Bullish (Fast > Slow)
        if ema_f <= ema_s:
            self.current_status += " | Trend Bearish"
            return None
            
        # Rule 2: Price > Both EMAs
        if current_price <= ema_f or current_price <= ema_s:
            # self.current_status += " | Price below EMAs"
            return None
            
        # Rule 3: 1m Confirmation (Bullish Candle)
        if curr_1m['close'] <= curr_1m['open']:
             # self.current_status += " | Waiting for Green Candle"
             return None
             
        # Rule 4: Time Filter (09:15 - 15:00) - Basic check
        ts = curr_1m.name
        if ts.hour < 9 or (ts.hour == 9 and ts.minute < 15) or ts.hour >= 15:
            self.current_status += " | Outside Trading Hours"
            return None

        # Trigger
        entry_price = curr_1m['close']
        c_low = curr_1m['low']
        
        # Risk Calc (as per run_backtest_378_30days.py)
        risk = abs(entry_price - c_low)
        min_risk = atr_val * 0.5
        final_risk = max(risk, min_risk)
        
        self.last_signal_data = {
            'side': 'buy',
            'entry': entry_price,
            'stop_loss': entry_price - final_risk,
            'risk': final_risk,
            'target_rr': self.risk_reward,
            'pattern': 'EMA Aggressive 378'
        }
        
        self.current_status = f"Signal Found! Long @ {entry_price:.2f}"
        return 'buy'

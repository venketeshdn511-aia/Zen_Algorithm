import pandas as pd
import numpy as np
from datetime import datetime, time
from src.interfaces.strategy_interface import StrategyInterface

class EMACrossover5m1mStrategy(StrategyInterface):
    """
    EMA Crossover Long 5m-1m TSL 75
    
    Logic:
    - Analysis TF: 5m
    - Entry TF: 1m
    - Indicators: EMA(8), EMA(34) on 5m
    - Signal: 5m EMA8 > 5m EMA34 AND Price > Both EMAs
    - Confirmation: 1m Bullish Candle (Close > Open)
    - Kill Zone: 09:15-11:00 OR 13:30-15:00
    - Risk Reward: 5.9
    """
    
    def __init__(self):
        super().__init__("EMA Crossover 5m/1m")
        self.ema_fast = 8
        self.ema_slow = 34
        self.risk_reward = 5.9
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        # New: Fresh Crossover Logic
        self.fresh_crossover_only = True
        self.last_trade_trend = None
        
    def get_status(self):
        return self.current_status
        
    def _ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
        
    def _atr(self, df, period=14):
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def detect_kill_zone(self, timestamp):
        t = timestamp.time()
        # NSE Kill Zones
        am_start = time(9, 15)
        am_end = time(11, 0)
        pm_start = time(13, 30)
        pm_end = time(15, 0)
        return (am_start <= t <= am_end) or (pm_start <= t <= pm_end)

    def calculate_signal(self, df):
        if len(df) < 100:
            self.current_status = f"Warming ({len(df)}/100)"
            return None
            
        # 1. Prepare Data (Normalize cols)
        df = df.copy()
        # Ensure Title Case for consistency if needed, but Engine passes lowercase usually.
        # Let's standardize to Title Case for local logic
        rename_map = {k: k.title() for k in df.columns}
        df = df.rename(columns=rename_map)
        
        # 2. Resample to 5m for Analysis
        df_5m = df.resample('5min').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
        }).dropna()
        
        if len(df_5m) < 40:
            self.current_status = f"Warming 5m ({len(df_5m)}/40)"
            return None
            
        # 3. Calculate 5m Indicators
        df_5m['ema_fast'] = self._ema(df_5m['Close'], self.ema_fast)
        df_5m['ema_slow'] = self._ema(df_5m['Close'], self.ema_slow)
        df_5m['atr'] = self._atr(df_5m, 14)
        
        # 4. Check Signal on LATEST COMPLETED 5m candle?
        # Real-time: We check the actively forming state OR the last closed.
        # "Signal on 5m" usually implies structure is valid.
        # Let's check the LAST CLOSED 5m bar for stability, or current forming if we want speed.
        # Given "Verified" code check: `ema_fast <= ema_slow` (check current index).
        # In backtest, `check_entry` is called on `a_idx`.
        # If we use `iloc[-1]`, it's the current forming 5m bar.
        # Using forming bar can be repainting. 
        # But "Entry on 1m" implies we are inside the 5m bar.
        # So we use `iloc[-1]` of 5m (live) but require it to be valid NOW.
        
        curr_5m = df_5m.iloc[-1]
        
        # Indicators
        ema_f = curr_5m['ema_fast']
        ema_s = curr_5m['ema_slow']
        atr_5m = curr_5m['atr']
        price_5m = curr_5m['Close']
        
        self.current_status = f"5m: Price {price_5m:.1f} | E8:{ema_f:.1f} E34:{ema_s:.1f}"
        
        # Rule 1: Fast > Slow
        if ema_f <= ema_s:
            # Trend Reset (Bearish Cross)
            if self.fresh_crossover_only:
                self.last_trade_trend = None
            return None
            
        # Rule 2: Price > Both
        if price_5m <= ema_f or price_5m <= ema_s:
            return None
            
        # Rule 3: Kill Zone
        current_ts = df.index[-1]
        if not self.detect_kill_zone(current_ts):
            self.current_status += " | Outside KZ"
            return None
            
        # Rule 4: 1m Confirmation (Bullish Candle)
        # Check LATEST 1m candle (completed or forming? usually completed for signal)
        # `df` is 1m data. `iloc[-1]` is the latest update.
        curr_1m = df.iloc[-1]
        
        if curr_1m['Close'] <= curr_1m['Open']:
            self.current_status += " | 1m Not Bullish"
            return None
            
        # All Conditions Met -> LONG
        # Calculate Logic-based Stop
        # "entry_candle_stop": max(abs(price - low), abs(high - price))
        # This implies volatility of the entry candle.
        
        # Determine strict stop distance
        # Current 1m candle High/Low/Price
        c_high = curr_1m['High']
        c_low = curr_1m['Low']
        c_close = curr_1m['Close']
        
        # Verified code: max(abs(price - low_val), abs(high_val - price))
        entry_candle_risk = max(abs(c_close - c_low), abs(c_high - c_close))
        
        # Minimum safety stop (e.g. 5 pts)
        risk = max(5.0, entry_candle_risk)
        
        self.last_signal_data = {
            'side': 'buy',
            'entry': c_close,
            'stop_loss': c_close - risk,
            'risk': risk,
            'target_rr': self.risk_reward,
            'pattern': 'EMA Crossover 5m/1m'
        }
        
        # Fresh Crossover Check
        if self.fresh_crossover_only:
            if self.last_trade_trend == 'buy':
                 return None # Already traded this trend
        
        # Update Trend State
        self.last_trade_trend = 'buy'
        
        return 'buy'

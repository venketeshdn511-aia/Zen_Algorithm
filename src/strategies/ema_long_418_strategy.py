import pandas as pd
import numpy as np
from datetime import datetime, time
from src.interfaces.strategy_interface import StrategyInterface

class EMACrossoverLong418Strategy(StrategyInterface):
    """
    EMA Crossover Long 5m-1m TSL 418
    
    Logic:
    - Analysis TF: 5m
    - Entry TF: 1m
    - Indicators: EMA(20), EMA(50) on 5m
    - Signal: 5m EMA20 > 5m EMA50 AND Price > Both EMAs
    - Confirmation: 1m Bullish Candle (Close > Open)
    - Kill Zone: 09:15-11:00 OR 13:30-15:00
    - Risk Reward: 4.9
    - Trailing SL: 1.0x ATR
    """
    
    def __init__(self):
        # We don't call super().__init__ if it's not defined in the base class effectively or expects something else
        # Most strategies here don't seem to use super().__init__ or pass name
        self.name = "EMA Crossover Long 418"
        self.ema_fast = 20
        self.ema_slow = 50
        self.risk_reward = 4.9
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        self.fresh_crossover_only = True
        self.last_trade_trend = None
        
    def get_status(self):
        return self.current_status
        
    def _ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
        
    def _atr(self, df, period=14):
        # Ensure Title Case for ATR calculation if we used it earlier
        high = df['High'] if 'High' in df.columns else df['high']
        low = df['Low'] if 'Low' in df.columns else df['low']
        close = df['Close'] if 'Close' in df.columns else df['close']
        
        high_low = high - low
        high_close = abs(high - close.shift())
        low_close = abs(low - close.shift())
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
            
        # Standardize columns to Title Case
        df = df.copy()
        rename_map = {k: k.title() for k in df.columns if k.lower() in ['open', 'high', 'low', 'close', 'volume']}
        df = df.rename(columns=rename_map)
        
        # 1. MTF Analysis: Resample to 5m
        try:
            df_5m = df.resample('5min').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
            }).dropna()
            
            if len(df_5m) < 60:
                self.current_status = f"Warming 5m ({len(df_5m)}/60)"
                return None
                
            # Indicators on 5m
            ema_f = self._ema(df_5m['Close'], self.ema_fast).iloc[-1]
            ema_s = self._ema(df_5m['Close'], self.ema_slow).iloc[-1]
            atr_5m = self._atr(df_5m, 14).iloc[-1]
            price_5m = df_5m['Close'].iloc[-1]
        except Exception as e:
            self.current_status = f"Error: {str(e)}"
            return None
            
        self.current_status = f"5m: Price {price_5m:.1f} | E20:{ema_f:.1f} E50:{ema_s:.1f}"
        
        # Rule 3: Kill Zone
        current_ts = df.index[-1]
        if not self.detect_kill_zone(current_ts):
            self.current_status = "☕ Coffee break. Outside Kill Zone (Waiting for the institutional surge)."
            return None
            
        # Rule 1: Fast > Slow
        if ema_f <= ema_s:
            if self.fresh_crossover_only:
                self.last_trade_trend = None
            self.current_status = f"🧐 Trend is Neutral/Bearish. Waiting for EMA20 ({ema_f:.1f}) to cross above EMA50 ({ema_s:.1f})."
            return None
            
        # Rule 2: Price > Both
        if price_5m <= ema_f or price_5m <= ema_s:
            self.current_status = f"📉 Bullish cross confirmed, but price ({price_5m:.1f}) is taking a breather. Waiting for it to climb back above EMAs."
            return None
            
        # Rule 4: 1m Confirmation (Bullish Candle)
        curr_1m = df.iloc[-1]
        if curr_1m['Close'] <= curr_1m['Open']:
            self.current_status = f"🔎 SETUP READY! High conviction on 5m. Just waiting for the next 1m green candle to fire entry."
            return None
            
        # Signal Generated
        c_high = curr_1m['High']
        c_low = curr_1m['Low']
        c_close = curr_1m['Close']
        
        # Risk: entry_candle_stop
        entry_candle_risk = max(abs(c_close - c_low), abs(c_high - c_close))
        risk = max(5.0, entry_candle_risk)
        
        self.last_signal_data = {
            'side': 'buy',
            'entry': c_close,
            'stop_loss': c_close - risk,
            'risk': risk,
            'target_rr': self.risk_reward,
            'pattern': 'EMA Crossover Long 418'
        }
        
        if self.fresh_crossover_only and self.last_trade_trend == 'buy':
            return None
            
        self.last_trade_trend = 'buy'
        self.current_status = f"SIGNAL: EMA 418 Entry @ {c_close}"
        return 'buy'

    def check_exit(self, df, position):
        """TSL Logic: 1.0x ATR trail"""
        if not position: return False, None
        
        # Ensure Title Case
        df = df.copy()
        rename_map = {k: k.title() for k in df.columns if k.lower() in ['open', 'high', 'low', 'close', 'volume']}
        df = df.rename(columns=rename_map)
        
        curr = df.iloc[-1]
        atr_val = self._atr(df, 14).iloc[-1]
        trail_dist = atr_val * 1.0
        
        current_sl = position.get('stop', 0)
        new_sl = curr['Close'] - trail_dist
        
        if new_sl > current_sl:
            return True, f"tsl_update:{new_sl}"
            
        return False, None

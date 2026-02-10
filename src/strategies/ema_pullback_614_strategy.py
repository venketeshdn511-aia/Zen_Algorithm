import pandas as pd
import numpy as np
from datetime import datetime, time
from src.interfaces.strategy_interface import StrategyInterface

class EMAPullback614Strategy(StrategyInterface):
    """
    EMA Pullback Long 15m-1m 614
    
    Logic:
    - Analysis TF: 15m
    - Entry TF: 1m
    - Indicators: EMA(8), EMA(21) on 15m
    - Signal: 15m Low <= EMA8 AND 15m Close > EMA8 (Pullback)
    - Confirmation: 1m Bullish Candle (Close > Open)
    - Kill Zone: 09:15-11:00 OR 13:30-15:00
    - Risk Reward: 5.6
    - Stop Loss: entry_candle_stop
    """
    
    def __init__(self):
        self.name = "EMA Pullback Long 614"
        self.ema_fast = 8
        self.ema_slow = 21
        self.risk_reward = 5.6
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        self.last_trade_trend = None
        
    def get_status(self):
        return self.current_status
        
    def _ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()
        
    def _atr(self, df, period=14):
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
        am_start = time(9, 15)
        am_end = time(11, 0)
        pm_start = time(13, 30)
        pm_end = time(15, 0)
        return (am_start <= t <= am_end) or (pm_start <= t <= pm_end)

    def calculate_signal(self, df):
        if len(df) < 100:
            self.current_status = f"Warming ({len(df)}/100)"
            return None
            
        # Standardize columns to Title Case for local resampling logic
        df_norm = df.copy()
        rename_map = {k: k.title() for k in df_norm.columns if k.lower() in ['open', 'high', 'low', 'close', 'volume']}
        df_norm = df_norm.rename(columns=rename_map)
        
        # 1. MTF Analysis: Resample to 15m
        try:
            df_15m = df_norm.resample('15min').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
            }).dropna()
            
            if len(df_15m) < 30:
                self.current_status = f"Warming 15m ({len(df_15m)}/30)"
                return None
                
            # Indicators on 15m
            ema_f = self._ema(df_15m['Close'], self.ema_fast).iloc[-1]
            price_15m_low = df_15m['Low'].iloc[-1]
            price_15m_close = df_15m['Close'].iloc[-1]
        except Exception as e:
            self.current_status = f"Error: {str(e)}"
            return None
            
        self.current_status = f"15m: Low {price_15m_low:.1f} | Close {price_15m_close:.1f} | E8:{ema_f:.1f}"
        
        # Rule 2: Kill Zone
        current_ts = df.index[-1]
        if not self.detect_kill_zone(current_ts):
            self.current_status = "☕ Resting. Outside Kill Zone (Market is a jungle right now)."
            return None
            
        # Rule 1: Pullback to EMA8 (Low must touch/under EMA8 AND Close must be above)
        if not (price_15m_low <= ema_f and price_15m_close > ema_f):
            self.current_status = f"🧐 Watching 15m trend. Waiting for a dip towards EMA8 ({ema_f:.1f}) to buy the fear."
            return None
            
        # Rule 3: 1m Confirmation (Bullish Candle)
        curr_1m = df_norm.iloc[-1]
        if curr_1m['Close'] <= curr_1m['Open']:
            self.current_status = f"🔎 Bullish setup on 15m! Just waiting for a 1m green candle to confirm entry."
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
            'pattern': 'EMA Pullback Long 614'
        }
        
        self.current_status = f"SIGNAL: EMA 614 Entry @ {c_close}"
        return 'buy'

    def check_exit(self, df, position):
        """Standard exit check for adapter compatibility"""
        if not position: return False, None
        return False, None # Handled by adapter SL/TP logic defaults

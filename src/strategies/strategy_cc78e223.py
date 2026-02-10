import pandas as pd
import pandas_ta as ta

class StrategyCc78e223:
    """
    EMA Pullback Short (cc78e223)
    Logic:
    - Analysis: 15m Trend (Price < EMA 21)
    - Execution: 1m Pullback (Entry when price rallies to EMA 13, stays above VWAP, RSI > 30)
    - Exit: Target (4.7x), 2x ATR Stop
    """
    def __init__(self, ema_fast=13, ema_slow=21, atr_period=14, rr_ratio=4.7):
        self.name = "EMA Pullback Short (cc78e223)"
        self.ema_fast_p = ema_fast
        self.ema_slow_p = ema_slow
        self.atr_period = atr_period
        self.rr_ratio = rr_ratio
        
        self.last_status = "Initializing..."
        self.last_signal_data = {}

    def calculate_signal(self, df):
        if len(df) < 50:
            return None

        # 1. Analysis Timeframe (15m) Context
        df_15m = df.resample('15min').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        if len(df_15m) < self.ema_slow_p: return None
        
        df_15m['ema_s'] = ta.ema(df_15m['close'], length=self.ema_slow_p)
        
        trend_bearish = df_15m['close'].iloc[-1] < df_15m['ema_s'].iloc[-1]
        
        # 2. Execution Timeframe (1m) Logic
        row = df.iloc[-1]
        curr_price = row['close']
        
        # Indicators
        df['ema_f'] = ta.ema(df['close'], length=self.ema_fast_p)
        df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
        
        last_ema_f = df['ema_f'].iloc[-1]
        last_vwap = df['vwap'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        last_atr = df['atr'].iloc[-1]
        
        # Entry Conditions (PDF Rules)
        cond_trend = trend_bearish
        cond_pullback = curr_price >= last_ema_f # Rally to EMA Fast
        cond_vwap = curr_price > last_vwap # Above fair value
        cond_rsi = last_rsi > 30 # Not oversold
        
        self.last_status = f"Trend:{'DOWN' if cond_trend else 'WAIT'} | Pullback:{'OK' if cond_pullback else 'WAIT'} | VWAP:{'HIGH' if cond_vwap else 'LOW'}"
        
        if cond_trend and cond_pullback and cond_vwap and cond_rsi:
            risk = 2.0 * last_atr
            if pd.isna(risk) or risk == 0: risk = 10.0 # Fallback
            
            self.last_signal_data = {
                'side': 'sell', # Signal for PE buying
                'entry': curr_price,
                'stop': curr_price + risk,
                'target': curr_price - (risk * self.rr_ratio),
                'risk': risk
            }
            return 'sell'
            
        return None

    def get_status(self):
        return self.last_status

    def check_exit(self, df, position_data):
        # Standard SL/TP handled by engine
        return False, ""

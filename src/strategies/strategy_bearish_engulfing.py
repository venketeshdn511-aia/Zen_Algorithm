import pandas as pd
import numpy as np
from datetime import time
from src.interfaces.strategy_interface import StrategyInterface

class BearishEngulfingResistanceStrategy(StrategyInterface):
    """
    Bearish Engulfing at Resistance (v2.2) - STRICT BACKTEST LOGIC
    Verified on 365-day backtest.
    
    Logic:
    1. MTF Setup: Signals on 15m, Execution confirmed on 1m.
    2. Pattern: Bearish Engulfing on 15m.
    3. Filters: Price < VWAP (0.15% toll) and RSI < 70 on 15m.
    4. Confirmation: 1m candle must be bearish (Close < Open).
    5. Risk Management: 5.5 RR, 1.0x ATR Trailing Stop.
    """
    
    def __init__(self, risk_reward=5.5, trailing_sl=True):
        super().__init__("BearishEngulfingResistance")
        self.risk_reward = risk_reward
        self.trailing_sl = trailing_sl
        self.current_status = "Initializing..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_indicators(self, df):
        """Standard indicator calculations matching backtest exactly"""
        h, l, c = df['High'].values, df['Low'].values, df['Close'].values
        v = df['Volume'].values if 'Volume' in df.columns else np.zeros_like(c)
        
        # ATR (14) - Wilder's
        tr = np.zeros(len(h))
        tr[0] = h[0] - l[0]
        for i in range(1, len(h)):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        
        atr = np.zeros(len(h))
        atr[13] = np.mean(tr[:14])
        for i in range(14, len(h)):
            atr[i] = (atr[i-1] * 13 + tr[i]) / 14
            
        # RSI (14) - Wilder's
        diff = np.diff(c)
        gains = np.where(diff > 0, diff, 0)
        losses = np.where(diff < 0, -diff, 0)
        
        avg_gain = np.zeros(len(c))
        avg_loss = np.zeros(len(c))
        avg_gain[14] = np.mean(gains[:14])
        avg_loss[14] = np.mean(losses[:14])
        for i in range(15, len(c)):
            avg_gain[i] = (avg_gain[i-1] * 13 + gains[i-1]) / 14
            avg_loss[i] = (avg_loss[i-1] * 13 + losses[i-1]) / 14
            
        rsi = np.zeros(len(c))
        for i in range(14, len(c)):
            if avg_loss[i] == 0: rsi[i] = 100
            else: rsi[i] = 100 - (100 / (1 + (avg_gain[i] / avg_loss[i])))
            
        # VWAP
        tp = (h + l + c) / 3.0
        vwap = (tp * v).cumsum() / v.cumsum()
        
        return {'atr': atr, 'rsi': rsi, 'vwap': vwap}

    def calculate_signal(self, df_1m):
        """MTF Signal Detection from 1m stream"""
        if len(df_1m) < 150:
            self.current_status = f"Warming up ({len(df_1m)}/150 bars)"
            return None

        # Ensure correct column casing
        df_1m_clean = df_1m.copy()
        if 'open' in df_1m_clean.columns: df_1m_clean.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)

        # Resample to 15m
        df_15m = df_1m_clean.resample('15min').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        
        if len(df_15m) < 20: return None
        
        # Calculate Indicators on 15m
        ind_15m = self._calculate_indicators(df_15m)
        
        idx = len(df_15m) - 1
        curr_15m = df_15m.iloc[idx]
        prev_15m = df_15m.iloc[idx-1]
        
        # Pattern Detection (Bearish Engulfing)
        is_engulfing = (prev_15m['Close'] > prev_15m['Open']) and \
                       (curr_15m['Close'] < curr_15m['Open']) and \
                       (curr_15m['Open'] > prev_15m['Close']) and \
                       (curr_15m['Close'] < prev_15m['Open'])
                       
        if is_engulfing:
            price = curr_15m['Close']
            vwap_val = ind_15m['vwap'][idx]
            rsi_val = ind_15m['rsi'][idx]
            
            # Rule: price_below_vwap (0.15% toll)
            if price > (vwap_val * 1.0015): 
                self.current_status = "Pattern detected, but price > VWAP threshold"
                return None
            
            # Rule: rsi_below_70
            if rsi_val >= 70:
                self.current_status = "Pattern detected, but RSI overbought"
                return None
            
            # 1m Confirmation
            last_1m = df_1m_clean.iloc[-1]
            if last_1m['Close'] < last_1m['Open']:
                risk = max(10, curr_15m['High'] - last_1m['Close'])
                self.last_signal_data = {
                    'type': 'SHORT',
                    'entry': last_1m['Close'],
                    'stop': curr_15m['High'],
                    'risk': risk,
                    'target_rr': self.risk_reward
                }
                self.current_status = f"SHORT Signal! (15m Engulfing @ {price:.1f})"
                return 'sell'
                
        self.current_status = f"Scanning... (15m Trend: {'Bearish' if curr_15m['Close'] < ind_15m['vwap'][idx] else 'Bullish'})"
        return None

    def check_exit(self, df_1m, position):
        """Trailing Stop Loss using 1m data"""
        if not position: return False, None
        
        # Ensure clean 1m data
        df_1m_clean = df_1m.copy()
        if 'open' in df_1m_clean.columns: df_1m_clean.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        
        curr_price = df_1m_clean.iloc[-1]['Close']
        high_1m = df_1m_clean.iloc[-1]['High']
        
        # Hard SL check (optional as Engine does it, but good for custom)
        if high_1m >= position['stop']:
            return True, "stop_loss"
            
        # Trailing SL (1.0x ATR)
        if self.trailing_sl:
            ind_1m = self._calculate_indicators(df_1m_clean)
            atr_1m = ind_1m['atr'][-1]
            
            if position['type'] == 'SHORT':
                new_sl = curr_price + (atr_1m * 1.0)
                if new_sl < position['stop']:
                    return True, f"tsl_update:{new_sl}"
                    
        return False, None

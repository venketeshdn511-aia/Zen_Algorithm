"""
Unified EMA Crossover Strategy (Long: 92b8f5e3, Short: 91cd6655)
Logic:
1. Multi-Timeframe: 15m Analysis, 1m Precision Entry.
2. Long: 15m EMA(9) > 15m EMA(21) AND 1m HA Bullish.
3. Short: 15m EMA(9) < 15m EMA(21) AND 1m HA Bearish.
4. Exit: 4.5x - 5.0x Reward-to-Risk ratio or HA Color Flip.
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class UnifiedEMACrossoverStrategy(StrategyInterface):
    def __init__(self, ema_9=9, ema_21=21, risk_reward=5.0):
        super().__init__("UnifiedEMA_Duo")
        self.ema_9 = ema_9
        self.ema_21 = ema_21
        self.risk_reward = risk_reward
        self.current_status = "Scanning Combined..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def calculate_signal(self, df):
        if len(df) < 110: 
            self.current_status = f"Warming indicators ({len(df)}/110 bars)"
            return None
        
        # 1. MTF Analysis (15m Regime)
        try:
            # Normalize columns to Title Case for internal logic
            calc_df = df.copy()
            calc_df.columns = [c.title() for c in calc_df.columns]
            
            df_15m = calc_df.resample('15min').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last'
            }).dropna()
            
            if len(df_15m) < 22:
                self.current_status = f"Warming 15m EMAs ({len(df_15m)}/22 bars)"
                return None
                
            e9_15 = df_15m['Close'].ewm(span=self.ema_9, adjust=False).mean()
            e21_15 = df_15m['Close'].ewm(span=self.ema_21, adjust=False).mean()
            
            curr_e9 = float(e9_15.iloc[-1])
            curr_e21 = float(e21_15.iloc[-1])
        except Exception as e:
            self.current_status = f"MTF Error: {str(e)}"
            return None
            
        # 2. 1m Precision (Heikin Ashi)
        curr = calc_df.iloc[-1]
        prev = calc_df.iloc[-2]
        
        # Heikin Ashi 1m
        ha_close = (curr['Open'] + curr['High'] + curr['Low'] + curr['Close']) / 4
        ha_open = (prev['Open'] + prev['Close']) / 2
        is_ha_bullish = ha_close > ha_open
        is_ha_bearish = ha_close < ha_open
        
        ha_color = " GREEN" if is_ha_bullish else " RED"
        regime = "UP " if curr_e9 > curr_e21 else "DOWN "
        
        # Update Dashboard Status with Live Data
        self.current_status = f"Nifty:{curr['Close']:.1f} | {ha_color} | E9:{curr_e9:.1f} E21:{curr_e21:.1f} | {regime}"

        # 3. Execution Logic (Match Backtest)
        if curr_e9 > curr_e21 and is_ha_bullish and ha_close > calc_df['Close'].iloc[-2]:
            self.last_signal_data = {
                'side': 'buy', 'entry': curr['Close'], 'stop_loss': curr['Low'],
                'risk': max(15, curr['Close'] - curr['Low']), 'pattern': 'Unified HA Long'
            }
            return 'buy'
            
        if curr_e9 < curr_e21 and is_ha_bearish and ha_close < calc_df['Close'].iloc[-2]:
            self.last_signal_data = {
                'side': 'sell', 'entry': curr['Close'], 'stop_loss': curr['High'],
                'risk': max(15, curr['High'] - curr['Close']), 'pattern': 'Unified HA Short'
            }
            return 'sell'

        return None

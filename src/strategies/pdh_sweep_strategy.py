"""
- Core Pattern: PDH/PDL Sweep (Liquidity Grab)
  * Identify Previous Day High (PDH) and Previous Day Low (PDL).
  * Price sweeps above PDH (for short) or below PDL (for long) and then reverses inside.
- Filter: Premium/Discount Zone
  * Premium: Upper 50% of recent dealing range (Shorts).
  * Discount: Lower 50% of recent dealing range (Longs).
- Exit: Stop Loss (1.5x ATR), Take Profit (4.9x Risk), End of Session (15:15 IST).
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface


class PDHSweepStrategy(StrategyInterface):
    def __init__(self, ema_fast=9, ema_slow=34, lookback_period=20, tp_rr=4.9, atr_period=14):
        super().__init__("PDH Sweep")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.lookback_period = lookback_period
        self.tp_rr = tp_rr
        self.atr_period = atr_period
        
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        self.pivots = {}

    def get_status(self):
        return self.current_status

    def _calculate_pdr(self, df):
        """Calculate Previous Day Range (PDH and PDL)"""
        if df.empty:
            return None, None
        
        df = df.copy()
        if 'date' not in df.columns:
            df['date'] = df.index.date
            
        unique_dates = sorted(df['date'].unique())
        if len(unique_dates) < 2:
            return None, None
            
        # Get yesterday's data
        yesterday = unique_dates[-2]
        yesterday_df = df[df['date'] == yesterday]
        return yesterday_df['High'].max(), yesterday_df['Low'].min()

    def _calculate_atr(self, df, period=14):
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def detect_zone(self, df, idx, direction='short'):
        """
        Premium Zone: Close > Equilibrium (Shorts)
        Discount Zone: Close < Equilibrium (Longs)
        """
        if idx < self.lookback_period:
            return False
            
        recent = df.iloc[idx-self.lookback_period:idx] # Exclusive of i as per PDF formula
        swing_high = recent['High'].max()
        swing_low = recent['Low'].min()
        equilibrium = (swing_high + swing_low) / 2
        
        if direction == 'short':
            return df['Close'].iloc[idx] > equilibrium
        else:
            return df['Close'].iloc[idx] < equilibrium

    def detect_pdr_sweep(self, df, idx, pdh, pdl, direction='short'):
        """
        Price sweeps PDH/PDL and then closes back inside.
        """
        if idx < 5 or (pdh is None and pdl is None):
            return False
            
        # Check for sweep in any of the last 5 bars
        recent = df.iloc[idx-5:idx+1]
        curr = df.iloc[idx]
        
        if direction == 'short':
            # Bullish sweep above PDH
            swept = recent['High'].max() > pdh
            # Currently back below PDH
            closed_inside = curr['Close'] < pdh
            # Ensure it hasn't stayed above for too long (must have recently swept)
            was_below = df.iloc[idx-6]['Close'] < pdh if idx >= 6 else True
            return swept and closed_inside and was_below
        else:
            # Bearish sweep below PDL
            swept = recent['Low'].min() < pdl
            # Currently back above PDL
            closed_inside = curr['Close'] > pdl
            # Was above PDL before the sweep sequence
            was_above = df.iloc[idx-6]['Close'] > pdl if idx >= 6 else True
            return swept and closed_inside and was_above

    def _calculate_rsi(self, df, period=14):
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_signal(self, df):
        if len(df) < 50:
            self.current_status = f"Warming up ({len(df)}/50 bars)"
            return None

        df = df.copy()
        pdh, pdl = self._calculate_pdr(df)
        df['rsi'] = self._calculate_rsi(df, 14)
        
        curr_idx = len(df) - 1
        curr = df.iloc[-1]
        close_p = curr['Close']
        high_p = curr['High']
        rsi_val = curr['rsi']
        
        pdh_str = f"{pdh:.0f}" if pdh is not None else "NaN"
        self.current_status = f"Price:{close_p:.0f} PDH:{pdh_str} RSI:{rsi_val:.1f}"

        # 1. PDR FETCH CHECK
        if pdh is None:
            self.current_status = "Waiting for PDH data..."
            return None

        # 2. ENTRY CHECKS (EXACT RULES)
        # Rule 1 & 2: Sweep (High > PDH) and Reclaim (Close < PDH)
        if high_p > pdh and close_p < pdh:
            # Rule 3: Momentum (RSI > 55)
            if rsi_val > 55:
                # Execution & Risk Rules (Single-TF Fixed)
                entry_price = close_p
                # SL: 20 Points Fixed
                stop_loss = entry_price + 20.0
                # TP: 50 Points Fixed (2.5x RR)
                target = entry_price - 50.0
                
                self.last_signal_data = {
                    'side': 'sell', 'entry': entry_price, 'stop_loss': stop_loss,
                    'take_profit': target, 'risk': 20.0, 'pattern': 'PDH Sweep Single-TF',
                    'rsi': rsi_val
                }
                return 'sell'
            
        return None

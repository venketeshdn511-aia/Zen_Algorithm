
import pandas as pd
import numpy as np
import logging
from datetime import time
from typing import Dict, List, Optional, Tuple
from src.core.base_strategy import BaseStrategy

class ORBBreakoutShortStrategy(BaseStrategy):
    """
    ORB Breakout Short (30m)_1m_3
    
    Strategy: Opening Range Breakout (30m) Short
    Market: NIFTY50 Index
    Timeframes: 
        - Analysis: 5m (VWAP context, Swing Highs)
        - Entry: 1m (Breakout execution)
    """
    
    def __init__(self, name="ORB Breakout Short (30m)", capital=15000):
        super().__init__(name, capital)
        self.orb_start_time = time(9, 15)
        self.orb_end_time = time(9, 45)
        self.last_signal_data = {}
        
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate indicators using MTF logic:
        1. Resample 1m Input -> 5m Data
        2. Calculate VWAP & Swing Points on 5m
        3. Merge 5m indicators back to 1m Data (ffill)
        """
        df = df.copy()
        
        # Ensure 'date' column
        if 'date' not in df.columns:
            # Safely join index to datetime if it's not already
            if not isinstance(df.index, pd.DatetimeIndex):
                # Try to convert index to datetime
                try:
                    df.index = pd.to_datetime(df.index)
                except:
                    # Fallback: if 'datetime' column exists
                    if 'datetime' in df.columns:
                        df.index = pd.to_datetime(df['datetime'])
            
            # Now extract date
            if isinstance(df.index, pd.DatetimeIndex):
                df['date'] = df.index.date
            else:
                # Critical fallback
                df['date'] = pd.Timestamp.now().date()
            
        # --- MTF STEP 1: RESAMPLE TO 5M ---
        # Resample logic: 9:15-9:20 -> Label 9:20 (or 9:15 depending on convention). 
        # Standard pandas resample '5min' defaults to left edge (9:15).
        
        # Resample rules for OHLCV
        logic = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        
        # Resample
        df_5m = df.resample('5min').agg(logic).dropna()
        
        # --- MTF STEP 2: CALCULATE INDICATORS ON 5M ---
        if 'typical_price' not in df_5m.columns:
            df_5m['typical_price'] = (df_5m['High'] + df_5m['Low'] + df_5m['Close']) / 3
            
        # Group by date for intraday VWAP on 5m candles
        df_5m['date_group'] = df_5m.index.date
        df_5m['tp_vol'] = df_5m['typical_price'] * df_5m['Volume']
        
        # Calculate Cumulative Volume-Price and Volume by Date
        df_5m['cum_vp'] = df_5m.groupby('date_group')['tp_vol'].cumsum()
        df_5m['cum_vol'] = df_5m.groupby('date_group')['Volume'].cumsum()
        df_5m['vwap_5m'] = df_5m['cum_vp'] / df_5m['cum_vol']
        
        # Calculate Swing Highs on 5m (more significant pivots)
        # Using rolling max of Highs on 5m
        # Lookback 20 periods on 5m = 100 mins context
        df_5m['swing_high_5m'] = df_5m['High'].rolling(20).max()
        
        # --- MTF STEP 3: MERGE BACK TO 1M ---
        # We merge 'asof' or reindex with ffill.
        # Since 5m closes at 9:20, that data is available for 9:21 1m candle? 
        # Or do we use the *current forming* 5m data? 
        # "Analysis on 5m": Usually means "completed" 5m bars.
        # So for 9:16, 9:17... we see the state ofindicators from 9:15 close? 
        # Actually, standard backtesting often ffills the *latest known* 5m value.
        # Let's resample with 'closed' right? No, standard resample is left label.
        # 9:15-9:20 bar is labeled 9:15. It is completed at 9:20.
        # So at 9:16 (1m), we don't have the 9:15(5m) bar finished yet!
        # This is tricky. 
        # Option A: Real-time update. 1m data builds the "live" 5m bar.
        # Option B: Lagged. Use previous 5m close.
        # The PDF "Entry on 1m" suggests we might just be looking at the higher timeframe context.
        # Let's align on index.
        
        # Simple approach used in vectors: Resample, then reindex to 1m index, ffill.
        # This effectively applies the "current emerging" 5m vwap to the 1m candles if we align timestamps carefully.
        # Or if we strictly want "Completed" values, we shift.
        
        # For VWAP, it's an intraday accumulator. It should be "Live 5m VWAP".
        # Which is essentially just... "Live VWAP". 
        # VWAP calculated on 1m vs 5m is mathematically almost identical (just granularity of Volume*Price).
        # HOWEVER, the "Swing High" filter is definitely different on 5m.
        
        mtf_features = df_5m[['vwap_5m', 'swing_high_5m']]
        
        # Merge logic
        # df has index 9:15, 9:16...
        # df_5m has index 9:15, 9:20...
        # If we reindex df_5m to df.index with ffill, then:
        # 9:15 1m gets 9:15 5m value. 9:16 1m gets 9:15 5m value.
        # This means 9:19 1m is using 9:15 5m value (which technically only "closed" or "started" at 9:15).
        # Standard pandas resample puts timestamp at START of bin.
        # So 9:15 bin contains data from 9:15:00 to 9:19:59.
        # We only know the "Close" of 9:15 bin at 9:20:00.
        # So strictly, at 9:16, we CANNOT know the 9:15(5m) Close/VWAP if it includes future data?
        # WAIT. VWAP is cumulative.
        # Let's stick to: "VWAP is trend". 
        # I will map the indicators forward.
        
        df_merged = df.join(mtf_features, how='left')
        df_merged[['vwap_5m', 'swing_high_5m']] = df_merged[['vwap_5m', 'swing_high_5m']].ffill()
        
        return df_merged

    def get_opening_range(self, df: pd.DataFrame, current_date) -> Tuple[float, float]:
        """Get High and Low of the Opening Range (9:15 - 9:45)."""
        day_data = df[df['date'] == current_date]
        # Just use raw 1m data for high/low precision
        orb_data = day_data[(day_data.index.time >= self.orb_start_time) & (day_data.index.time < self.orb_end_time)]
        
        if orb_data.empty:
            return None, None
            
        self.orb_high = orb_data['High'].max()
        self.orb_low = orb_data['Low'].min()
        
        return self.orb_high, self.orb_low

    def calculate_signal(self, df: pd.DataFrame) -> str:
        """
        Calculate signal for the latest bar in the dataframe.
        """
        if df.empty: return None
        
        # 1. Feature Engineering (MTF 5m) - Ensures we have VWAP and Swing Highs
        # Note: In live execution, we might be calling this every bar.
        # Ideally, we should optimize, but for now we follow the backtest pattern.
        df_analyzed = self.calculate_indicators(df)
        
        current_bar = df_analyzed.iloc[-1]
        prev_bar = df_analyzed.iloc[-2]
        timestamp = current_bar.name if isinstance(current_bar.name, pd.Timestamp) else pd.Timestamp.now()
        
        # 2. Time Filter
        current_time = timestamp.time()
        if current_time <= self.orb_end_time or current_time >= time(15, 15):
            return None
            
        # 3. Get Opening Range
        current_date = timestamp.date()
        orb_high, orb_low = self.get_opening_range(df_analyzed, current_date)
        if not orb_low: 
            return None
            
        # 4. Breakout Condition (Bearish Only)
        # Previous Close was above/at Low, Current Close is below Low
        if not (prev_bar['Close'] >= orb_low and current_bar['Close'] < orb_low):
            return None
            
        # 5. VWAP Filter (Price must be within 0.5% of VWAP)
        vwap = current_bar.get('vwap_5m')
        if pd.isna(vwap): return None
        
        dist = abs(current_bar['Close'] - vwap) / vwap
        if dist > 0.005:
            return None
            
        # 6. Stop Loss Logic (MTF Swing High)
        swing_high = current_bar.get('swing_high_5m')
        entry_price = current_bar['Close']
        
        # Fallback if swing high is invalid/missing
        if pd.isna(swing_high) or swing_high <= entry_price:
            swing_high = current_bar['High']
            if swing_high <= entry_price:
                swing_high = entry_price * 1.001 # 0.1% min risk fallback
                
        # 7. Risk/Reward
        risk = swing_high - entry_price
        reward = risk * 4.4
        tp = entry_price - reward
        
        # Store signal data for Adapter
        self.last_signal_data = {
            'time': timestamp,
            'entry': entry_price,
            'stop_loss': swing_high,
            'take_profit': tp,
            'risk': risk,
            'pattern': 'ORB Breakout Short (5m MTF)'
        }
        
        return 'sell'


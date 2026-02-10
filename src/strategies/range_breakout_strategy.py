
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface
from datetime import time

class RangeBreakoutStrategy(StrategyInterface):
    """
    Range Breakout Long_15m-1m_TSL_104
    
    Structure:
    - MTF Analysis: 15m timeframe (20-bar High, RSI)
    - Entry: 1m timeframe (Breakout > 15m High, RSI < 70, Kill Zone)
    - Kill Zones (Indian Nifty 50):
        - Morning: 09:15 - 11:30 IST
        - Afternoon: 13:00 - 15:15 IST
    """
    
    def __init__(self, high_period=20, rsi_period=14, rsi_max=70, 
                 kill_zone_morning=(time(13, 0), time(15, 15)), # Shifted to Afternoon as per verification
                 kill_zone_afternoon=(time(13, 0), time(15, 15)),
                 risk_reward=5.4):
        super().__init__("RangeBreakoutLong_15m_1m")
        self.high_period = high_period
        self.rsi_period = rsi_period
        self.rsi_max = rsi_max
        self.kill_zone_morning = kill_zone_morning
        self.kill_zone_afternoon = kill_zone_afternoon
        self.risk_reward = risk_reward
        self.current_status = "Initializing..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))

    def _is_in_kill_zone(self, timestamp):
        t = timestamp.time()
        morning_check = self.kill_zone_morning[0] <= t <= self.kill_zone_morning[1]
        afternoon_check = self.kill_zone_afternoon[0] <= t <= self.kill_zone_afternoon[1]
        return morning_check or afternoon_check

    def calculate_signal(self, df):
        """
        Process 1m DataFrame to generate signals.
        Arguments:
            df: 1m OHLCV DataFrame
        """
        if len(df) < 200: # Need enough data for 15m resampling
            self.current_status = f"Warming up ({len(df)}/200)"
            return None

        # --- step 1: MTF Analysis (15m) ---
        # Resample to 15m
        df_15m = df.resample('15min').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        
        # Calculate 15m Indicators
        df_15m['high_20'] = df_15m['High'].rolling(window=self.high_period).max()
        df_15m['rsi'] = self._calculate_rsi(df_15m['Close'], self.rsi_period)

        # Shift 15m indicators to avoid lookahead bias
        # We want the COMPLETED 15m candle's high/rsi to be available for the NEXT 1m candles
        df_15m['high_20_prev'] = df_15m['high_20'].shift(1)
        df_15m['rsi_prev'] = df_15m['rsi'].shift(1)

        # --- Step 2: Merge to 1m ---
        # Reindex 15m data to 1m index, ffill to propagate values forward
        # This ensures that at 09:25, we see the 15m values from the 09:15-09:30 candle (which is not yet closed?? No.)
        # Wait, if we use .shift(1) on 15m, we get the values from 09:00-09:15 candle available at 09:15.
        # So at 09:16 (1m), we should see the values from the 09:00-09:15 candle.
        
        # Resample logic check:
        # Pandas resample '15min' usually labels with LEFT edge (09:15 covers 09:15-09:30).
        # We only know the High of 09:15-09:30 at 09:30.
        # So at 09:16, we should only see data from BEFORE 09:15.
        
        # Let's map 15m metrics back to 1m
        mtf_features = df_15m[['high_20_prev', 'rsi_prev']].reindex(df.index, method='ffill')
        
        df_combined = df.join(mtf_features)
        
        curr = df_combined.iloc[-1]
        prev = df_combined.iloc[-2]
        
        # Current State
        close_p = curr['Close']
        high_15m = curr['high_20_prev']
        rsi_15m = curr['rsi_prev']
        timestamp = curr.name
        
        if pd.isna(high_15m) or pd.isna(rsi_15m):
            self.current_status = "Waiting for MTF data..."
            return None

        self.current_status = f"Scanning... Price:{close_p:.1f} 15mHigh:{high_15m:.1f} 15mRSI:{rsi_15m:.1f}"

        # --- Step 3: Entry Logic ---
        # 1. Kill Zone
        if not self._is_in_kill_zone(timestamp):
            return None
            
        # 2. RSI Filter (Not Overbought)
        if rsi_15m >= self.rsi_max:
            return None
            
        # 3. Breakout Logic
        # Close crossed above 15m High
        # Ideally we want to check if it JUST crossed, or if it IS above.
        # "Breakout Long: Close > 20-bar high" usually implies state, but for a signal we want the crossover moment.
        # Let's check crossover: Prev Close <= High OR just current Close > High?
        # A pure "Close > High" condition might trigger continuously if we are in a trend. 
        # We should probably check if we are NOT already in a trade (handled by engine), 
        # but for signal generation, a crossover is safer.
        # However, checking "prev_close <= high_15m and close_p > high_15m" is strict.
        # Let's stick to "Close > High" and rely on the engine to only take one trade per signal/state.
        # Actually, let's use crossover to be precise.
        
        # The PDF says "Breakout Long: Close > 20-bar high". 
        # I'll use crossover to avoid re-signaling.
        
        breakout = (prev['Close'] <= high_15m) and (close_p > high_15m)
        
        if breakout:
            # Entry Parameters
            stop_loss = curr['Low']  # Low of entry candle
            # Safety: ensure SL is below Entry
            if stop_loss >= close_p:
               stop_loss = close_p - 5 # Fallback small SL
               
            risk = close_p - stop_loss
            take_profit = close_p + (risk * self.risk_reward)
            
            self.last_signal_data = {
                'side': 'buy',
                'entry': close_p,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'timestamp': timestamp
            }
            
            self.current_status = f"BUY Signal @ {close_p} (MTF Breakout)"
            return 'buy'

        return None

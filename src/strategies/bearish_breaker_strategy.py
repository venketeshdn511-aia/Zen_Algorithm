"""
Bearish Breaker b4 Re-test_5m_7
Algorithmic Logic & Concepts

Entry Logic:
- detect_bearish_breaker: A failed Bullish Order Block that is reclaimed (Old Support -> New Resistance).
  - Logic:
    1. Identify Swing Low (SL) that leads to a Break of Structure (Higher High).
    2. This SL marked as Bullish Order Block (OB).
    3. Price breaks BELOW this OB.
    4. This zone becomes the Bearish Breaker.
- detect_premium_zone: Price is in the upper 50% of the dealing range (Swing High to Current Low).
- retest_entry: Price returns to the Breaker Zone.

Exit Logic:
- stop_loss_hit: Above the Breaker High.
- take_profit_hit: Fixed RR (e.g., 1:2 or 1:3).
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class BearishBreakerStrategy(StrategyInterface):
    """Bearish Breaker b4 Re-test Strategy"""

    def __init__(self, pivot_period=5, rr_ratio=2.5, atr_period=14):
        super().__init__("Bearish Breaker b4 Re-test")
        self.pivot_period = pivot_period # Lookback for pivots
        self.rr_ratio = rr_ratio
        self.atr_period = atr_period
        
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        
        # State variables to track market structure
        self.active_breaker = None # {top, bottom, formed_at_time}
        self.last_bullish_ob = None # {top, bottom, time}
        self.market_structure = {} # track swings
        
    def get_status(self):
        return self.current_status

    def _calculate_atr(self, df):
        """Calculate ATR for dynamic sizing/stops if needed"""
        high = df['High']
        low = df['Low']
        close = df['Close'].shift(1)
        tr = pd.concat([high-low, abs(high-close), abs(low-close)], axis=1).max(axis=1)
        return tr.rolling(self.atr_period).mean()

    def identify_swings(self, df):
        """
        Identify Swing Highs and Lows using pivot points.
        Returns latest swings.
        """
        # We need a bit of history. pivot_period=5 means checking 5 bars left and right.
        # For real-time, we can only check left. " Fractal" usually needs right bars too, 
        # but that introduces lag. We'll use a rolling max/min for simplicity or checks.
        
        # Heuristic: A low is a low if it's the lowest in the last N bars and price has moved up since?
        # Better: Standard Pivot logic (Requires lag of `pivot_period` bars to confirm a pivot).
        # We will use the 'pandas_ta' approach or simple rolling window.
        
        # For this strategy, a "Key Level" is often clear.
        # We will detect swings retrospectively (lagged) to define the OB.
        
        # Using a simple window approach for robustness in streaming:
        # Swing Low = Lowest Low in window, surrounded by higher lows.
        
        # Let's use `argrelextrema` style logic manually for speed/simplicity
        pass # Implemented inside calculate logic for stateful tracking

    def detect_market_structure(self, df):
        """
        Scans for:
        1. Valid Bullish Order Block (Swing Low that caused a Higher High).
        2. Break of that Order Block (Breaker Formation).
        """
        if len(df) < 50:
            return
            
        # 1. Identify Pivots (Lagged by pivot_period)
        # We look back `pivot_period` bars to see if `df.iloc[-pivot_period-1]` was a pivot.
        
        pp = self.pivot_period
        
        # We need to analyze history to find the 'Last Significant Structure'
        # This is expensive to do every tick from scratch. Ideally we track state.
        # For the simulation/bot, we'll re-scan the recent window.
        
        # Simplification:
        # 1. Find recent Swing Lows.
        # 2. Check if a Swing Low was followed by a price move that exceeded the previous Swing High (BOS).
        # 3. If yes, that Swing Low is a "Bullish OB".
        # 4. If price CURRENTLY breaks below that Bullish OB, it becomes a Bearish Breaker.
        
        # Get candles
        highs = df['High'].values
        lows = df['Low'].values
        closes = df['Close'].values
        times = df.index
        
        # Find latest Swing Low (SL) and Swing High (SH)
        # We'll valid a pivot if it's extreme in +/- pp window
        
        # Optimization: Just look at the last 100 bars
        window_size = 100
        if len(df) > window_size:
            highs = highs[-window_size:]
            lows = lows[-window_size:]
            closes = closes[-window_size:]
            times = times[-window_size:]
            
        # Detect Pivots
        # pivot_lows is a list of (index, price)
        pivot_lows = []
        pivot_highs = []
        
        for i in range(pp, len(highs) - pp):
            # Check Low
            if lows[i] == min(lows[i-pp:i+pp+1]):
                pivot_lows.append((i, lows[i], times[i]))
            
            # Check High
            if highs[i] == max(highs[i-pp:i+pp+1]):
                pivot_highs.append((i, highs[i], times[i]))
                
        if not pivot_lows or not pivot_highs:
            return
            
        # Analyze structure from pivots
        # We are looking for: PIVOT_LOW (A) -> PIVOT_HIGH (B) -> HIGHER_HIGH (C)
        # Wait, Definition of OB: The move UP from A broke a prior High?
        # Yes. A "Bullish OB" is established when it creates a BOS (Break of Structure).
        
        # Let's iterate pivots to find the valid OB
        last_confirmed_ob = None
        
        # We need at least one high before the low to compare? 
        # Or just checking if the move *after* the low broke the *previous* high.
        
        for i in range(1, len(pivot_lows)):
            curr_low_idx, curr_low_val, curr_low_time = pivot_lows[i]
            
            # Find the highest high *before* this low
            # Filter highs where index < curr_low_idx
            prior_highs = [h for h in pivot_highs if h[0] < curr_low_idx]
            if not prior_highs:
                continue
                
            last_high_val = prior_highs[-1][1] # Most recent high before this low
            
            # Now check if price *after* this low broke that last_high_val
            # The "Breaking" move usually culminates in a new Pivot High
            subsequent_highs = [h for h in pivot_highs if h[0] > curr_low_idx]
            
            check_break = False
            for sh_idx, sh_val, sh_time in subsequent_highs:
                if sh_val > last_high_val:
                    check_break = True
                    break
            
            # Also check if current price (if not a pivot yet) broke it
            # (Handled by subsequent pivots usually)
            
            if check_break:
                # This Low is a Valid Bullish OB
                # OB Zone: Low to the body close? or Low to High of the candle?
                # Usually the "Order Block" is the last bearish candle. 
                # Simplification: The Zone is the Pivot Low to the High of that same candle (or nearby candle).
                # Let's define OB Zone = [Pivot Low, Pivot Low + ATR] or just the Candle dimensions.
                # We'll use the candle at pivot_low_idx.
                
                # Global index mapping
                # We need to map back to original DF to get candle details
                # But 'i' is relative to our slice.
                
                # Careful with indices. Let's just track the value.
                # Zone Top: Max(Open, Close) of the pivot candle (Body top) or High? 
                # Let's use the entire candle range of the bottom-most candle.
                # Or standard ICT: Last down candle.
                
                # We will approximate: Zone Bottom = Low, Zone Top = High of that candle
                candle_idx = curr_low_idx
                ob_bottom = lows[candle_idx]
                ob_top = highs[candle_idx]
                
                last_confirmed_ob = {
                    'bottom': ob_bottom,
                    'top': ob_top,
                    'time': curr_low_time,
                    'break_of': last_high_val
                }
        
        self.last_bullish_ob = last_confirmed_ob
        
        # Now Check for Maker Break (Breaker)
        # A Breaker is confirmed when Price CLOSES below the Bullish OB Bottom.
        if self.last_bullish_ob:
            current_close = closes[-1]
            if current_close < self.last_bullish_ob['bottom']:
                # It is broken!
                # But we want to catch the *retest*. 
                # If we are currently way below, we identify this as an Active Bearish Breaker.
                self.active_breaker = self.last_bullish_ob
            else:
                # Note: If we just broke it, 'active_breaker' becomes set.
                # If price is above, it's still a Bullish OB (Support).
                pass

    def calculate_signal(self, df):
        """
        Main Signal Logic
        """
        if len(df) < 50:
            self.current_status = "Data too short."
            return None
        
        # 1. Structure Analysis
        self.detect_market_structure(df)
        
        if not self.active_breaker:
            self.current_status = "Scanning for Bullish OB failures..."
            return None
            
        breaker = self.active_breaker
        current_price = df['Close'].iloc[-1]
        current_high = df['High'].iloc[-1]
        
        # Check if Breaker is "Fresh" (Time limit?) - optional.
        
        # 2. Detect Retest
        # Price must come UP into the Breaker Zone (Bottom - Top)
        # OR come close to it.
        # Strict Retest: High >= Breaker Bottom
        
        # We need to verify we are retesting from BELOW.
        # i.e., at some point since the breaker formed, price was well below it.
        # (Implicit if we detected a break).
        
        in_zone = (current_high >= breaker['bottom']) and (df['Low'].iloc[-1] <= breaker['top'])
        
        # 3. Premium Zone Logic
        # Range: From the Swing High that occurred BEFORE the break, down to the Lowest Low AFTER the break.
        # This is complex to track stateless.
        # Simplification: Look at standard lookback (e.g. 50 bars) high vs low.
        
        lookback = 50 
        recent_high = df['High'].iloc[-lookback:].max()
        recent_low = df['Low'].iloc[-lookback:].min()
        
        mid_point = (recent_high + recent_low) / 2
        in_premium = current_price > mid_point
        
        if not in_premium:
            self.current_status = f"Breaker detected ({breaker['bottom']:.2f}). Waiting for Spot Price > {mid_point:.2f} (Premium Zone)"
            return None
            
        if not in_zone:
            # Maybe we are ABOVE the zone? (Invalidated)
            if current_price > breaker['top']:
                 self.current_status = "Price reclaimed Breaker (Invalidated)."
                 return None
            
            # We are below, waiting for retest
            dist = breaker['bottom'] - current_price
            self.current_status = f"Bearish Breaker active @ {breaker['bottom']:.2f}. Dist: {dist:.2f}"
            return None
            
        # If in zone and in premium
        # SIGNAL
        atr = self._calculate_atr(df).iloc[-1]
        
        # Stop Loss: Above Breaker Top + Buffer
        stop_loss = breaker['top'] + (0.5 * atr)
        entry_price = current_price
        risk = stop_loss - entry_price
        
        if risk <= 0: # Should not happen if in zone
             risk = atr
             stop_loss = entry_price + atr
             
        take_profit = entry_price - (risk * self.rr_ratio)
        
        self.last_signal_data = {
            'side': 'sell',
            'pattern': 'Bearish Breaker',
            'breaker_bottom': breaker['bottom'],
            'breaker_top': breaker['top'],
            'premium_threshold': mid_point,
            'entry': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk': risk
        }
        
        self.current_status = f"🔴 SHORT SIGNAL: Bearish Breaker Retest @ {entry_price:.2f}"
        return 'sell'


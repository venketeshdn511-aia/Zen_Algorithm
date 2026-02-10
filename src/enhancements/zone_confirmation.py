"""
Zone Confirmation Filter - Phase 1 Enhancement
Validates zone quality before entry to reduce false breakouts
"""

import pandas as pd
import numpy as np
from datetime import datetime

class ZoneConfirmationFilter:
    def __init__(self, logger=None):
        self.logger = logger
        self.zone_touch_history = {}  # Track touches per zone
        
    def validate_entry(self, zone_data, current_bar, bars_5m, bars_15m):
        """
        Multi-point zone validation
        
        Returns: (bool, score, reason)
        """
        score = 0
        reasons = []
        
        # Extract zone bounds
        zone_low = zone_data.get('bottom', 0)
        zone_high = zone_data.get('top', 0)
        zone_id = f"{zone_low:.2f}_{zone_high:.2f}"
        
        # Confirmation 1: Retest (not first touch)
        touch_count = self._count_zone_touches(zone_id, zone_low, zone_high, bars_5m)
        if touch_count >= 2:
            score += 2
            reasons.append(f"Retest (#{touch_count} touch)")
        else:
            reasons.append("First touch (risky)")
        
        # Confirmation 2: Volume spike
        current_volume = current_bar.get('Volume', 0)
        avg_volume = bars_5m['Volume'].tail(20).mean()
        
        if current_volume > avg_volume * 1.5:
            score += 2
            reasons.append(f"Volume spike ({current_volume/avg_volume:.1f}x)")
        
        # Confirmation 3: Rejection wick (pin bar)
        wick_score = self._check_rejection_wick(current_bar)
        score += wick_score
        if wick_score > 0:
            reasons.append(f"Rejection wick ({wick_score}pts)")
        
        # Confirmation 4: Higher timeframe alignment
        htf_aligned = self._check_htf_alignment(bars_15m, zone_data)
        if htf_aligned:
            score += 2
            reasons.append("15m trend aligned")
        
        # Confirmation 5: Time of day probability
        if self._is_high_probability_time():
            score += 2
            reasons.append("High probability time")
        
        # Threshold: Require 6+ points to enter
        is_valid = score >= 6
        
        if self.logger:
            self.logger.info(f"Zone Validation: {score}/10 - {', '.join(reasons)}")
        
        return is_valid, score, reasons
    
    def _count_zone_touches(self, zone_id, zone_low, zone_high, bars):
        """Count how many times price has touched this zone"""
        touches = 0
        
        for i in range(len(bars)):
            bar_low = bars['Low'].iloc[i]
            bar_high = bars['High'].iloc[i]
            
            # Check if bar intersects zone
            if bar_low <= zone_high and bar_high >= zone_low:
                touches += 1
        
        # Cache result
        self.zone_touch_history[zone_id] = touches
        
        return touches
    
    def _check_rejection_wick(self, bar):
        """
        Detect pin bar rejections from zone
        Returns: 0-2 points based on wick quality
        """
        open_price = bar.get('Open', 0)
        high_price = bar.get('High', 0)
        low_price = bar.get('Low', 0)
        close_price = bar.get('Close', 0)
        
        body_size = abs(close_price - open_price)
        
        # Bullish rejection (long lower wick)
        lower_wick = min(open_price, close_price) - low_price
        
        # Bearish rejection (long upper wick)
        upper_wick = high_price - max(open_price, close_price)
        
        # Pin bar: wick > 2x body
        if lower_wick > body_size * 2:
            return 2  # Strong bullish rejection
        elif upper_wick > body_size * 2:
            return 2  # Strong bearish rejection
        elif lower_wick > body_size or upper_wick > body_size:
            return 1  # Moderate rejection
        
        return 0
    
    def _check_htf_alignment(self, bars_15m, zone_data):
        """
        Check if 15m trend aligns with zone direction
        """
        if len(bars_15m) < 20:
            return False
        
        # Calculate 15m EMA
        ema_20 = bars_15m['Close'].tail(20).ewm(span=20).mean()
        
        current_price = bars_15m['Close'].iloc[-1]
        ema_value = ema_20.iloc[-1]
        
        zone_type = zone_data.get('type', 'demand')
        
        # Demand zone: want price above EMA (uptrend)
        if zone_type == 'demand' and current_price > ema_value:
            return True
        
        # Supply zone: want price below EMA (downtrend)
        if zone_type == 'supply' and current_price < ema_value:
            return True
        
        return False
    
    def _is_high_probability_time(self):
        """
        Check if current time is in high-probability window
        Best Nifty times: 10-11 AM, 1-2 PM IST
        """
        now = datetime.now()
        hour = now.hour
        
        # High probability windows
        if (10 <= hour < 11) or (13 <= hour < 14):
            return True
        
        return False
    
    def reset_history(self):
        """Clear zone touch history (call daily)"""
        self.zone_touch_history = {}

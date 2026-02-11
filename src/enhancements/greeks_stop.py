"""
Greeks-Based Stop Calculator - Phase 1 Enhancement
Calculates dynamic stops based on option Greeks, not just price
"""

import numpy as np

class GreeksStopCalculator:
    def __init__(self, logger=None):
        self.logger = logger
        
    def calculate_stop(self, entry_price, entry_iv, current_iv, 
                      option_delta, days_to_expiry, atr, signal_side):
        """
        Calculate dynamic stop loss based on Greeks
        
        Args:
            entry_price: Spot price at entry
            entry_iv: Implied volatility at entry
            current_iv: Current implied volatility
            option_delta: Option delta (0.5 for ATM, 0.6 for ITM)
            days_to_expiry: Days until expiry
            atr: Current ATR
            signal_side: 'buy' or 'sell'
        
        Returns: stop_price
        """
        # Base stop: 1.5 ATR (original logic)
        base_stop_distance = atr * 1.5
        
        # Factor 1: IV Adjustment
        iv_multiplier = self._get_iv_multiplier(entry_iv, current_iv)
        
        # Factor 2: Theta Adjustment (tighten near expiry)
        theta_multiplier = self._get_theta_multiplier(days_to_expiry)
        
        # Factor 3: Delta Adjustment (ITM vs ATM)
        delta_multiplier = self._get_delta_multiplier(option_delta)
        
        # Combined multiplier
        total_multiplier = iv_multiplier * theta_multiplier * delta_multiplier
        
        # Adjusted stop distance
        adjusted_stop_distance = base_stop_distance * total_multiplier
        
        # Calculate actual stop price
        if signal_side == 'buy':
            stop_price = entry_price - adjusted_stop_distance
        else:  # sell
            stop_price = entry_price + adjusted_stop_distance
        
        if self.logger:
            self.logger.info(f"Greeks Stop: Base={base_stop_distance:.2f} | "
                           f"IV={iv_multiplier:.2f}x | "
                           f"Theta={theta_multiplier:.2f}x | "
                           f"Delta={delta_multiplier:.2f}x | "
                           f"Final={adjusted_stop_distance:.2f}")
        
        return stop_price
    
    def _get_iv_multiplier(self, entry_iv, current_iv):
        """
        Adjust stop based on IV change
        IV spike = widen stop (more volatility)
        IV drop = tighten stop (less volatility)
        """
        if entry_iv == 0:
            return 1.0  # No IV data
        
        iv_change_pct = (current_iv - entry_iv) / entry_iv
        
        if iv_change_pct > 0.3:  # IV spiked 30%+
            return 1.3  # Widen stop 30%
        
        elif iv_change_pct > 0.15:  # IV up 15-30%
            return 1.15  # Widen stop 15%
        
        elif iv_change_pct < -0.15:  # IV dropped 15%+
            return 0.85  # Tighten stop 15%
        
        return 1.0  # No adjustment
    
    def _get_theta_multiplier(self, days_to_expiry):
        """
        Adjust stop based on time decay
        Near expiry = tighter stops (theta decay faster)
        """
        if days_to_expiry <= 1:
            return 0.6  # Very tight stop (40% tighter)
        
        elif days_to_expiry <= 2:
            return 0.75  # Tight stop (25% tighter)
        
        elif days_to_expiry <= 4:
            return 0.9  # Slightly tight (10% tighter)
        
        elif days_to_expiry >= 10:
            return 1.1  # Wider stop (10% wider)
        
        return 1.0  # Normal
    
    def _get_delta_multiplier(self, option_delta):
        """
        Adjust stop based on option delta
        Higher delta (ITM) = tighter stop (more intrinsic value)
        Lower delta (OTM) = wider stop (more extrinsic value)
        """
        if option_delta >= 0.7:  # Deep ITM
            return 0.85  # Tighter stop
        
        elif option_delta >= 0.6:  # ITM
            return 0.9  # Slightly tight
        
        elif option_delta >= 0.5:  # ATM
            return 1.0  # Normal
        
        elif option_delta >= 0.4:  # OTM
            return 1.1  # Slightly wide
        
        else:  # Deep OTM
            return 1.2  # Wider stop
    
    def estimate_iv_from_atr(self, atr, spot_price):
        """
        Rough IV estimate when actual IV not available
        IV  (ATR / Price) * sqrt(252) * 100
        """
        if spot_price == 0:
            return 20.0  # Default IV
        
        daily_volatility = atr / spot_price
        annual_volatility = daily_volatility * np.sqrt(252)
        iv_estimate = annual_volatility * 100
        
        # Clamp to reasonable range
        return max(10, min(60, iv_estimate))
    
    def calculate_vega_risk(self, position_size, option_delta, days_to_expiry):
        """
        Calculate Vega risk (sensitivity to IV changes)
        Used for position sizing adjustments
        """
        # Vega peaks around 30 DTE for ATM options
        # Simplest estimate: Vega  sqrt(DTE) * 0.04 for ATM
        
        if days_to_expiry < 1:
            vega_per_lot = 0.01  # Very low vega near expiry
        else:
            vega_per_lot = np.sqrt(days_to_expiry) * 0.04 * option_delta
        
        total_vega = position_size * vega_per_lot
        
        return total_vega

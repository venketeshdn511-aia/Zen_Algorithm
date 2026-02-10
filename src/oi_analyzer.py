"""
OI (Open Interest) Analyzer for Nifty Options
Provides PCR, Max Pain, and Smart Strike Selection
"""

import logging
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta


class OIAnalyzer:
    """
    Analyzes Open Interest data for smarter strike selection.
    
    Features:
    - Put-Call Ratio (PCR) calculation
    - Max Pain computation
    - OI change detection
    - Smart strike selection based on institutional positioning
    """
    
    def __init__(self, fyers_broker, logger=None):
        """
        Initialize OI Analyzer.
        
        Args:
            fyers_broker: FyersBroker instance for API calls
            logger: Optional logger
        """
        self.fyers = fyers_broker
        self.logger = logger or logging.getLogger(__name__)
        
        # Nifty configuration
        self.STRIKE_INTERVAL = 50
        self.CHAIN_RANGE = 10  # Number of strikes above/below ATM to fetch
        
        # Cache for OI data (avoid excessive API calls)
        self.oi_cache = {}
        self.cache_expiry = None
        self.cache_duration_seconds = 60  # Refresh every 60 seconds
        
        # Historical OI for change detection
        self.previous_oi = {}
    
    def get_option_chain_data(self, spot_price: float, expiry_date: str = None) -> Dict:
        """
        Fetch full option chain data around ATM.
        
        Args:
            spot_price: Current Nifty spot price
            expiry_date: Optional expiry (auto-detect if None)
        
        Returns:
            Dict with strikes as keys, containing CE/PE OI and LTP
        """
        # Check cache
        if self.cache_expiry and datetime.now() < self.cache_expiry:
            return self.oi_cache
        
        atm_strike = round(spot_price / self.STRIKE_INTERVAL) * self.STRIKE_INTERVAL
        
        chain_data = {}
        
        # Fetch strikes from ATM - CHAIN_RANGE to ATM + CHAIN_RANGE
        for i in range(-self.CHAIN_RANGE, self.CHAIN_RANGE + 1):
            strike = atm_strike + (i * self.STRIKE_INTERVAL)
            
            try:
                # Get CE data
                ce_premium = self.fyers.fyers.get_option_chain(strike, 'CE', expiry_date)
                pe_premium = self.fyers.fyers.get_option_chain(strike, 'PE', expiry_date)
                
                chain_data[strike] = {
                    'ce_ltp': ce_premium or 0,
                    'pe_ltp': pe_premium or 0,
                    'ce_oi': self._estimate_oi_from_premium(ce_premium, strike, spot_price, 'CE'),
                    'pe_oi': self._estimate_oi_from_premium(pe_premium, strike, spot_price, 'PE')
                }
                
            except Exception as e:
                self.logger.debug(f"Failed to fetch OI for strike {strike}: {e}")
                continue
        
        # Update cache
        self.oi_cache = chain_data
        self.cache_expiry = datetime.now() + timedelta(seconds=self.cache_duration_seconds)
        
        self.logger.info(f"📊 Fetched OI chain: {len(chain_data)} strikes around ATM {atm_strike}")
        
        return chain_data
    
    def _estimate_oi_from_premium(self, premium: float, strike: int, spot: float, option_type: str) -> int:
        """
        Estimate OI based on premium and moneyness.
        
        Note: Fyers API doesn't provide direct OI in quotes.
        This is a heuristic estimation. For production, use NSE data feed.
        
        Higher premium at OTM = Higher OI (more interest)
        """
        if not premium or premium <= 0:
            return 0
        
        moneyness = abs(spot - strike) / spot
        
        # Base OI estimate (higher premium = more interest)
        base_oi = int(premium * 1000)
        
        # OTM options with premium = high OI (lots of speculative interest)
        if option_type == 'CE' and strike > spot:
            oi_multiplier = 1 + (moneyness * 10)
        elif option_type == 'PE' and strike < spot:
            oi_multiplier = 1 + (moneyness * 10)
        else:
            oi_multiplier = 0.8  # ITM has less speculative OI
        
        return int(base_oi * oi_multiplier)
    
    def calculate_pcr(self, chain_data: Dict = None, spot_price: float = None) -> Tuple[float, str]:
        """
        Calculate Put-Call Ratio.
        
        Args:
            chain_data: Option chain data (fetches if None)
            spot_price: Current spot (required if chain_data is None)
        
        Returns:
            (PCR value, sentiment string)
        """
        if chain_data is None:
            if spot_price is None:
                return 1.0, "NEUTRAL"
            chain_data = self.get_option_chain_data(spot_price)
        
        if not chain_data:
            return 1.0, "NEUTRAL"
        
        total_put_oi = sum(data['pe_oi'] for data in chain_data.values())
        total_call_oi = sum(data['ce_oi'] for data in chain_data.values())
        
        if total_call_oi == 0:
            return 1.0, "NEUTRAL"
        
        pcr = total_put_oi / total_call_oi
        
        # Determine sentiment
        if pcr > 1.2:
            sentiment = "BULLISH"
        elif pcr < 0.8:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"
        
        self.logger.info(f"📊 PCR: {pcr:.2f} ({sentiment}) | Put OI: {total_put_oi:,} | Call OI: {total_call_oi:,}")
        
        return pcr, sentiment
    
    def calculate_max_pain(self, chain_data: Dict = None, spot_price: float = None) -> int:
        """
        Calculate Max Pain strike.
        
        Max Pain = Strike where total value of options expiring worthless is maximum.
        
        Args:
            chain_data: Option chain data
            spot_price: Current spot
        
        Returns:
            Max Pain strike price
        """
        if chain_data is None:
            if spot_price is None:
                return 0
            chain_data = self.get_option_chain_data(spot_price)
        
        if not chain_data:
            return 0
        
        strikes = sorted(chain_data.keys())
        min_pain = float('inf')
        max_pain_strike = strikes[len(strikes) // 2]  # Default to middle
        
        for test_strike in strikes:
            total_pain = 0
            
            for strike, data in chain_data.items():
                # Call pain: If price settles at test_strike
                if strike < test_strike:
                    # ITM calls have intrinsic value = (test_strike - strike) * OI
                    call_pain = (test_strike - strike) * data['ce_oi']
                else:
                    call_pain = 0
                
                # Put pain: If price settles at test_strike
                if strike > test_strike:
                    # ITM puts have intrinsic value = (strike - test_strike) * OI
                    put_pain = (strike - test_strike) * data['pe_oi']
                else:
                    put_pain = 0
                
                total_pain += call_pain + put_pain
            
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_strike
        
        self.logger.info(f"🎯 Max Pain: {max_pain_strike}")
        
        return max_pain_strike
    
    def get_optimal_strike(
        self,
        spot_price: float,
        signal_direction: str,  # 'buy' or 'sell'
        trend_strength: str = 'normal',  # 'strong', 'normal', 'weak'
        expiry_date: str = None
    ) -> Tuple[int, str, Dict]:
        """
        Get optimal strike based on OI analysis.
        
        Args:
            spot_price: Current Nifty spot
            signal_direction: 'buy' (CE) or 'sell' (PE)
            trend_strength: 'strong', 'normal', 'weak'
            expiry_date: Optional expiry
        
        Returns:
            (optimal_strike, option_type, analysis_dict)
        """
        # Fetch chain data
        chain_data = self.get_option_chain_data(spot_price, expiry_date)
        
        # Calculate metrics
        pcr, sentiment = self.calculate_pcr(chain_data, spot_price)
        max_pain = self.calculate_max_pain(chain_data, spot_price)
        
        atm_strike = round(spot_price / self.STRIKE_INTERVAL) * self.STRIKE_INTERVAL
        
        # Determine option type
        option_type = 'CE' if 'buy' in signal_direction.lower() else 'PE'
        
        # Strike offset based on analysis
        strike_offset = 0  # 0 = ATM, +1 = 1 OTM, -1 = 1 ITM
        
        # === SMART STRIKE SELECTION LOGIC ===
        
        # Rule 1: PCR Confirmation
        if option_type == 'CE':
            if sentiment == 'BULLISH':
                # PCR confirms bullish - go slightly ITM for higher delta
                strike_offset = -1 if trend_strength == 'strong' else 0
            elif sentiment == 'BEARISH':
                # PCR against our direction - stay ATM or go OTM (cheaper)
                strike_offset = 1
        else:  # PE
            if sentiment == 'BEARISH':
                # PCR confirms bearish - go slightly ITM
                strike_offset = -1 if trend_strength == 'strong' else 0
            elif sentiment == 'BULLISH':
                # PCR against our direction - stay ATM or go OTM
                strike_offset = 1
        
        # Rule 2: Max Pain Adjustment
        if max_pain > 0:
            if option_type == 'CE':
                if spot_price > max_pain:
                    # Above max pain - expect pullback, be cautious
                    strike_offset = min(strike_offset + 1, 2)  # Go more OTM
                elif spot_price < max_pain:
                    # Below max pain - expect rally toward it
                    strike_offset = max(strike_offset - 1, -2)  # Go more ITM
            else:  # PE
                if spot_price < max_pain:
                    # Below max pain - expect rally, be cautious with PE
                    strike_offset = min(strike_offset + 1, 2)
                elif spot_price > max_pain:
                    # Above max pain - expect drop toward it
                    strike_offset = max(strike_offset - 1, -2)
        
        # Rule 3: Trend Strength Override
        if trend_strength == 'strong':
            # Strong trend - go ITM for higher delta exposure
            strike_offset = max(strike_offset - 1, -2)
        elif trend_strength == 'weak':
            # Weak trend - go OTM for cheaper premium (defined risk)
            strike_offset = min(strike_offset + 1, 2)
        
        # Calculate final strike
        if option_type == 'CE':
            optimal_strike = atm_strike - (strike_offset * self.STRIKE_INTERVAL)
        else:
            optimal_strike = atm_strike + (strike_offset * self.STRIKE_INTERVAL)
        
        # Prepare analysis summary
        analysis = {
            'atm_strike': atm_strike,
            'optimal_strike': optimal_strike,
            'strike_offset': strike_offset,
            'pcr': pcr,
            'pcr_sentiment': sentiment,
            'max_pain': max_pain,
            'spot_vs_maxpain': 'ABOVE' if spot_price > max_pain else 'BELOW',
            'trend_strength': trend_strength,
            'recommendation': f"{optimal_strike} {option_type}"
        }
        
        self.logger.info(
            f"🎯 Strike Selection: {optimal_strike} {option_type} | "
            f"PCR: {pcr:.2f} ({sentiment}) | MaxPain: {max_pain} | "
            f"Offset: {strike_offset} strikes"
        )
        
        return optimal_strike, option_type, analysis
    
    def get_oi_summary(self, spot_price: float) -> str:
        """Get human-readable OI summary for logging/display."""
        chain_data = self.get_option_chain_data(spot_price)
        pcr, sentiment = self.calculate_pcr(chain_data, spot_price)
        max_pain = self.calculate_max_pain(chain_data, spot_price)
        
        spot_vs_mp = "ABOVE" if spot_price > max_pain else "BELOW"
        
        return (
            f"OI Summary | PCR: {pcr:.2f} ({sentiment}) | "
            f"MaxPain: {max_pain} | Spot {spot_vs_mp} MaxPain"
        )

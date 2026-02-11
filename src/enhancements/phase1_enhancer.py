"""
Phase 1 Enhancer - Master Wrapper
Orchestrates all Phase 1 enhancements around NiftyOptionsStrategyV2
"""

from src.enhancements.zone_confirmation import ZoneConfirmationFilter
from src.enhancements.time_optimizer import TimeOfDayOptimizer
from src.enhancements.expiry_manager import ExpiryWeekManager
from src.enhancements.greeks_stop import GreeksStopCalculator

class Phase1Enhancer:
    def __init__(self, base_strategy, logger=None, config=None):
        """
        Wraps base strategy (NiftyOptionsStrategyV2) with Phase 1 enhancements
        
        Args:
            base_strategy: The core strategy (V2)
            logger: Logger instance
            config: Configuration dict with enhancement settings
        """
        self.base_strategy = base_strategy
        self.logger = logger
        self.config = config or {}
        
        # Initialize enhancement modules
        self.zone_filter = ZoneConfirmationFilter(logger)
        self.time_optimizer = TimeOfDayOptimizer(
            timezone=self.config.get('timezone', 'Asia/Kolkata'),
            logger=logger
        )
        self.expiry_manager = ExpiryWeekManager(logger)
        self.greeks_calc = GreeksStopCalculator(logger)
        
        # Enhancement flags (can be toggled via config)
        self.use_zone_filter = self.config.get('use_zone_filter', True)
        self.use_time_filter = self.config.get('use_time_filter', True)
        self.use_expiry_filter = self.config.get('use_expiry_filter', True)
        self.use_greeks_stops = self.config.get('use_greeks_stops', True)
        
        # Stats tracking
        self.stats = {
            'signals_generated': 0,
            'signals_filtered': 0,
            'filter_reasons': {}
        }
        self.enhanced_status = "Initializing Enhancer..."
        
    def get_current_status(self):
        return self.enhanced_status
    
    def calculate_enhanced_signal(self, major_bars, minor_bars, symbol):
        """
        Main entry point - wraps base strategy with enhancements
        
        Returns: signal ('buy', 'sell', None) or None if filtered
        """
        # Step 1: Get signal from base strategy (UNTOUCHED)
        base_signal = self.base_strategy.calculate_signal(major_bars, minor_bars, symbol)
        
        # Propagate base status if no signal
        if not base_signal:
            self.enhanced_status = self.base_strategy.get_status()
            return None
        
        self.stats['signals_generated'] += 1
        
        # Parse signal mode (buy_trend, buy_scalp, etc.)
        signal_raw = base_signal
        signal_mode = 'scalp'  # default
        
        if '_' in str(base_signal):
            parts = base_signal.split('_')
            signal_raw = parts[0]  # 'buy' or 'sell'
            signal_mode = parts[1]  # 'trend' or 'scalp'
        
        # Step 2: Apply Time-of-Day Filter
        if self.use_time_filter:
            time_valid, adjusted_mode = self._apply_time_filter(signal_mode)
            
            if not time_valid:
                self._log_filter('time_filter', 'Market closed or wrong time window')
                self.enhanced_status = "Signal Filtered: Time of Day"
                return None
            
            # Update mode if time suggests adjustment
            if adjusted_mode != signal_mode:
                signal_mode = adjusted_mode
                if self.logger:
                    self.logger.info(f"Time optimizer adjusted mode: {signal_mode}")
        
        # Step 3: Apply Expiry Week Filter
        if self.use_expiry_filter:
            expiry_valid = self._apply_expiry_filter()
            
            if not expiry_valid:
                self._log_filter('expiry_filter', 'Too close to expiry (theta risk)')
                self.enhanced_status = "Signal Filtered: Expiry Risk"
                return None
        
        # Step 4: Apply Zone Confirmation Filter
        if self.use_zone_filter:
            zone_valid = self._apply_zone_filter(major_bars, minor_bars, symbol)
            
            if not zone_valid:
                self._log_filter('zone_filter', 'Zone quality insufficient (<6/10)')
                self.enhanced_status = "Signal Filtered: Zone Quality Low"
                return None
        
        # All filters passed - return enhanced signal
        enhanced_signal = f"{signal_raw}_{signal_mode}"
        
        if self.logger:
            self.logger.info(f" Phase1 Enhanced Signal: {enhanced_signal} | "
                           f"Filters Passed: {self.stats['signals_generated'] - self.stats['signals_filtered']} / "
                           f"{self.stats['signals_generated']}")
        
        return enhanced_signal
    
    def _apply_time_filter(self, signal_mode):
        """Apply time-of-day filter"""
        rules = self.time_optimizer.get_trading_rules()
        
        if not rules['allow_new_trades']:
            return False, None
        
        # Check mode alignment
        optimal_mode = self.time_optimizer.get_optimal_mode(signal_mode)
        
        return True, optimal_mode[1]
    
    def _apply_expiry_filter(self):
        """Apply expiry week filter"""
        if self.expiry_manager.should_avoid_trade():
            return False
        
        return True
    
    def _apply_zone_filter(self, major_bars, minor_bars, symbol):
        """Apply zone confirmation filter"""
        # Get latest zone from base strategy
        if symbol in self.base_strategy.zones:
            zones = self.base_strategy.zones[symbol]
            
            if zones:
                latest_zone = zones[-1]
                current_bar = minor_bars.iloc[-1].to_dict()
                
                # Validate zone quality
                is_valid, score, reasons = self.zone_filter.validate_entry(
                    latest_zone,
                    current_bar,
                    minor_bars,
                    major_bars
                )
                
                if not is_valid:
                    return False
        
        return True
    
    def calculate_enhanced_stop(self, entry_price, atr, signal_side, option_delta=0.5):
        """
        Calculate Greeks-based stop (if enabled)
        Otherwise fall back to standard ATR stop
        """
        if not self.use_greeks_stops:
            # Standard stop: 1.5 ATR
            if signal_side == 'buy':
                return entry_price - (atr * 1.5)
            else:
                return entry_price + (atr * 1.5)
        
        # Estimate IV from ATR
        entry_iv = self.greeks_calc.estimate_iv_from_atr(atr, entry_price)
        current_iv = entry_iv  # Assume same at entry
        
        # Get days to expiry
        days_to_expiry = self.expiry_manager.get_days_to_expiry()
        
        # Calculate Greeks-based stop
        greeks_stop = self.greeks_calc.calculate_stop(
            entry_price=entry_price,
            entry_iv=entry_iv,
            current_iv=current_iv,
            option_delta=option_delta,
            days_to_expiry=days_to_expiry,
            atr=atr,
            signal_side=signal_side
        )
        
        return greeks_stop
    
    def adjust_position_size(self, base_size):
        """
        Adjust position size based on time and expiry
        """
        adjusted_size = base_size
        
        # Time-of-day adjustment
        if self.use_time_filter:
            adjusted_size = self.time_optimizer.adjust_position_size(adjusted_size)
        
        # Expiry adjustment
        if self.use_expiry_filter:
            adjusted_size = self.expiry_manager.adjust_position_size(adjusted_size)
        
        return adjusted_size
    
    def _log_filter(self, filter_name, reason):
        """Track filter statistics"""
        self.stats['signals_filtered'] += 1
        
        if filter_name not in self.stats['filter_reasons']:
            self.stats['filter_reasons'][filter_name] = 0
        
        self.stats['filter_reasons'][filter_name] += 1
        
        if self.logger:
            self.logger.warning(f" Filtered by {filter_name}: {reason}")
    
    def get_stats(self):
        """Get enhancement statistics"""
        total = self.stats['signals_generated']
        if total == 0:
            return "No signals yet"
        
        passed = total - self.stats['signals_filtered']
        filter_rate = (self.stats['signals_filtered'] / total) * 100
        
        return {
            'signals_generated': total,
            'signals_passed': passed,
            'signals_filtered': self.stats['signals_filtered'],
            'filter_rate': f"{filter_rate:.1f}%",
            'filter_breakdown': self.stats['filter_reasons']
        }
    
    def reset_stats(self):
        """Reset statistics (call daily)"""
        self.stats = {
            'signals_generated': 0,
            'signals_filtered': 0,
            'filter_reasons': {}
        }
        
        # Reset zone touch history
        self.zone_filter.reset_history()

"""
Time-of-Day Optimizer - Phase 1 Enhancement
Optimizes trading based on Nifty's intraday behavioral patterns
"""

from datetime import datetime, time
import pytz

class TimeOfDayOptimizer:
    def __init__(self, timezone='Asia/Kolkata', logger=None):
        self.timezone = pytz.timezone(timezone)
        self.logger = logger
        
        # Nifty trading windows (IST)
        self.trading_windows = {
            'opening_volatility': {
                'start': time(9, 15),
                'end': time(10, 0),
                'mode': 'TREND',
                'risk_multiplier': 0.5,  # Reduce size
                'reason': 'Opening volatility - unpredictable moves'
            },
            'morning_trend': {
                'start': time(10, 0),
                'end': time(11, 0),
                'mode': 'TREND',
                'risk_multiplier': 1.0,  # Full size
                'reason': 'Best trending period - follow momentum'
            },
            'lunch_consolidation': {
                'start': time(11, 0),
                'end': time(13, 0),
                'mode': 'SCALP',
                'risk_multiplier': 0.7,  # Moderate size
                'reason': 'Lunch period - range-bound'
            },
            'afternoon_momentum': {
                'start': time(13, 0),
                'end': time(14, 0),
                'mode': 'TREND',
                'risk_multiplier': 1.0,  # Full size
                'reason': 'Afternoon push - strong trends'
            },
            'pre_close_chop': {
                'start': time(14, 0),
                'end': time(15, 0),
                'mode': 'SCALP',
                'risk_multiplier': 0.5,  # Reduce size
                'reason': 'Pre-close volatility - choppy'
            },
            'close_only': {
                'start': time(15, 0),
                'end': time(15, 30),
                'mode': 'CLOSE_ONLY',
                'risk_multiplier': 0.0,  # No new trades
                'reason': 'Market closing - exit all positions'
            }
        }
    
    def get_trading_rules(self, current_time=None):
        """
        Get optimal trading rules for current time
        
        Returns: dict with mode, risk_multiplier, reason
        """
        if current_time is None:
            current_time = datetime.now(self.timezone)
        
        # Extract time component
        if isinstance(current_time, datetime):
            check_time = current_time.time()
        else:
            check_time = current_time
        
        # Find which window we're in
        for window_name, window_config in self.trading_windows.items():
            if window_config['start'] <= check_time < window_config['end']:
                if self.logger:
                    self.logger.info(f"Time Window: {window_name} - {window_config['reason']}")
                
                return {
                    'window': window_name,
                    'mode': window_config['mode'],
                    'risk_multiplier': window_config['risk_multiplier'],
                    'reason': window_config['reason'],
                    'allow_new_trades': window_config['mode'] != 'CLOSE_ONLY'
                }
        
        # Before market open or after close
        return {
            'window': 'MARKET_CLOSED',
            'mode': 'CLOSED',
            'risk_multiplier': 0.0,
            'reason': 'Market not open',
            'allow_new_trades': False
        }
    
    def is_market_open(self, current_time=None):
        """Check if market is currently open"""
        rules = self.get_trading_rules(current_time)
        return rules['window'] != 'MARKET_CLOSED'
    
    def should_close_positions(self, current_time=None):
        """Check if we should force-close all positions"""
        rules = self.get_trading_rules(current_time)
        return rules['mode'] == 'CLOSE_ONLY'
    
    def get_optimal_mode(self, signal_mode, current_time=None):
        """
        Validate if signal mode aligns with time-of-day mode
        
        Returns: (bool, adjusted_mode)
        """
        rules = self.get_trading_rules(current_time)
        
        if rules['mode'] == 'CLOSE_ONLY':
            return False, None  # Don't take any new trades
        
        # If time says TREND but signal says SCALP, respect time
        if rules['mode'] == 'TREND' and signal_mode == 'scalp':
            if self.logger:
                self.logger.warning(f"Time suggests TREND, but signal is SCALP - passing")
            return True, 'trend'  # Override to trend
        
        # If time says SCALP but signal says TREND, allow but reduce size
        if rules['mode'] == 'SCALP' and signal_mode == 'trend':
            if self.logger:
                self.logger.warning(f"Time suggests SCALP, reducing trend size")
            return True, 'scalp'  # Convert to scalp
        
        # Alignment - good to go
        return True, signal_mode
    
    def adjust_position_size(self, base_size, current_time=None):
        """Adjust position size based on time-of-day risk"""
        rules = self.get_trading_rules(current_time)
        
        adjusted_size = int(base_size * rules['risk_multiplier'])
        
        if self.logger and adjusted_size != base_size:
            self.logger.info(f"Position size adjusted: {base_size}  {adjusted_size} "
                           f"({rules['risk_multiplier']*100:.0f}% due to {rules['window']})")
        
        return adjusted_size
    
    def get_profit_target_multiplier(self, current_time=None):
        """
        Adjust profit targets based on time
        Morning trends: extend targets
        Lunch/close: take quick profits
        """
        rules = self.get_trading_rules(current_time)
        
        if rules['window'] == 'morning_trend':
            return 1.2  # Extend targets 20%
        
        elif rules['window'] == 'afternoon_momentum':
            return 1.1  # Extend targets 10%
        
        elif rules['window'] in ['lunch_consolidation', 'pre_close_chop']:
            return 0.8  # Tighten targets 20%
        
        return 1.0  # Normal targets

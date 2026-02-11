"""
Expiry Week Manager - Phase 1 Enhancement
Manages position sizing and targets based on days to expiry (DTE)
"""

from datetime import datetime, timedelta

class ExpiryWeekManager:
    def __init__(self, logger=None):
        self.logger = logger
        
        # Nifty weekly expiry: Every Tuesday (changed from Thursday in 2024)
        self.expiry_day = 1  # Tuesday = 1 (0=Monday)
        
    def get_next_expiry(self, current_date=None):
        """Calculate next weekly expiry (Tuesday)"""
        if current_date is None:
            current_date = datetime.now()
        
        # Find next Tuesday
        days_ahead = self.expiry_day - current_date.weekday()
        
        if days_ahead <= 0:  # Today is Tuesday or later
            days_ahead += 7  # Next week's Tuesday
        
        next_expiry = current_date + timedelta(days=days_ahead)
        
        return next_expiry.replace(hour=15, minute=30, second=0)
    
    def get_days_to_expiry(self, current_date=None):
        """Calculate days remaining until expiry"""
        if current_date is None:
            current_date = datetime.now()
        
        next_expiry = self.get_next_expiry(current_date)
        
        # Calculate days (fractional for intraday)
        time_diff = next_expiry - current_date
        days = time_diff.total_seconds() / 86400
        
        return days
    
    def get_expiry_rules(self, current_date=None):
        """
        Get trading rules based on days to expiry
        
        Returns: dict with constraints based on DTE
        """
        dte = self.get_days_to_expiry(current_date)
        
        if dte <= 1:  # Expiry day or 1 day before
            return {
                'zone': 'DANGER',
                'max_positions': 0,  # AVOID completely
                'size_multiplier': 0.0,
                'profit_target': '0.5R',  # Quick exit if already in
                'reason': 'Theta decay too fast - avoid new trades',
                'allow_new_trades': False,
                'force_close': True  # Close existing positions
            }
        
        elif dte <= 2:  # Mon-Tue of expiry week
            return {
                'zone': 'HIGH_RISK',
                'max_positions': 1,  # Only 1 position max
                'size_multiplier': 0.3,  # 30% of normal size
                'profit_target': '1R',  # Quick 1R exits
                'reason': 'Expiry week - high theta decay',
                'allow_new_trades': True,
                'prefer_itm': True  # Prefer ITM options (less theta)
            }
        
        elif dte <= 4:  # Wed-Thu previous week
            return {
                'zone': 'MODERATE_RISK',
                'max_positions': 3,
                'size_multiplier': 0.6,  # 60% size
                'profit_target': '2R',
                'reason': '3-4 days to expiry - moderate caution',
                'allow_new_trades': True,
                'prefer_itm': False
            }
        
        elif dte <= 7:  # Fri-Tue of previous week
            return {
                'zone': 'SAFE',
                'max_positions': 5,
                'size_multiplier': 0.9,  # 90% size
                'profit_target': '3R',
                'reason': 'Good time window - normal operation',
                'allow_new_trades': True,
                'prefer_itm': False
            }
        
        else:  # 8+ days (rare for weekly options)
            return {
                'zone': 'OPTIMAL',
                'max_positions': 5,
                'size_multiplier': 1.0,  # Full size
                'profit_target': '3R+',
                'reason': 'Optimal time - full aggressive mode',
                'allow_new_trades': True,
                'prefer_itm': False
            }
    
    def should_avoid_trade(self, current_date=None):
        """Quick check if we should avoid new trades"""
        rules = self.get_expiry_rules(current_date)
        return not rules['allow_new_trades']
    
    def should_close_positions(self, current_date=None):
        """Check if we should force-close existing positions"""
        rules = self.get_expiry_rules(current_date)
        return rules.get('force_close', False)
    
    def adjust_position_size(self, base_size, current_date=None):
        """Adjust position size based on DTE"""
        rules = self.get_expiry_rules(current_date)
        
        adjusted_size = int(base_size * rules['size_multiplier'])
        
        if self.logger:
            dte = self.get_days_to_expiry(current_date)
            self.logger.info(f"Expiry Management: {dte:.1f} DTE | "
                           f"Zone: {rules['zone']} | "
                           f"Size: {base_size}  {adjusted_size} "
                           f"({rules['size_multiplier']*100:.0f}%)")
        
        return adjusted_size
    
    def get_profit_target(self, current_date=None):
        """Get recommended profit target based on DTE"""
        rules = self.get_expiry_rules(current_date)
        return rules['profit_target']
    
    def get_option_strike_preference(self, current_date=None):
        """
        Determine whether to prefer ITM, ATM, or OTM
        Near expiry: prefer ITM (less theta)
        """
        rules = self.get_expiry_rules(current_date)
        
        if rules.get('prefer_itm'):
            return 'ITM'  # In-the-money
        else:
            return 'ATM'  # At-the-money

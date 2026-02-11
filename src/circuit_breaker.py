"""
Multi-level circuit breaker system.

Protects account from catastrophic losses with graduated response.
"""

from typing import Optional, Dict
from datetime import datetime, timedelta


class CircuitBreaker:
    """
    3-Level circuit breaker system:
    - Level 1: Pause new trades at -2% daily DD
    - Level 2: Reduce position size 50% at -5% DD
    - Level 3: Liquidate all at -10% DD
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        
        # Circuit breaker levels
        self.levels = {
            'LEVEL_1': {'threshold': -0.02, 'action': 'PAUSE'},     # -2%
            'LEVEL_2': {'threshold': -0.05, 'action': 'REDUCE'},    # -5%
            'LEVEL_3': {'threshold': -0.10, 'action': 'LIQUIDATE'}  # -10%
        }
        
        # State tracking
        self.current_level = None
        self.breaker_triggered_time: Optional[datetime] = None
        self.pause_until: Optional[datetime] = None
        self.size_reduction_active = False
    
    def check_drawdown(
        self,
        current_balance: float,
        starting_balance: float
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Check if circuit breaker should trigger.
        
        Args:
            current_balance: Current equity
            starting_balance: Starting equity for the day
        
        Returns:
            (level: str, action: str) or (None, None)
        """
        if starting_balance <= 0:
            return None, None
        
        # Calculate drawdown percentage
        pnl = current_balance - starting_balance
        dd_pct = pnl / starting_balance
        
        # Check levels in order (L3 -> L2 -> L1)
        for level_name in ['LEVEL_3', 'LEVEL_2', 'LEVEL_1']:
            level = self.levels[level_name]
            
            if dd_pct <= level['threshold']:
                if self.current_level != level_name:
                    # New level triggered
                    self.current_level = level_name
                    self.breaker_triggered_time = datetime.now()
                    
                    if self.logger:
                        self.logger.critical(
                            f" CIRCUIT BREAKER {level_name}: "
                            f"Drawdown {dd_pct*100:.2f}% <= {level['threshold']*100:.0f}% | "
                            f"Action: {level['action']}"
                        )
                    
                    return level_name, level['action']
        
        return None, None
    
    def pause_trading(self, duration_minutes: int = 60):
        """
        Pause new trades for specified duration.
        
        Args:
            duration_minutes: Pause duration (default 60 min)
        """
        self.pause_until = datetime.now() + timedelta(minutes=duration_minutes)
        
        if self.logger:
            self.logger.warning(
                f" Trading PAUSED until {self.pause_until.strftime('%H:%M:%S')} "
                f"({duration_minutes} min)"
            )
    
    def is_trading_paused(self) -> bool:
        """Check if trading is currently paused."""
        if self.pause_until is None:
            return False
        
        if datetime.now() >= self.pause_until:
            # Pause expired
            if self.logger:
                self.logger.info(" Trading pause expired, resuming")
            self.pause_until = None
            return False
        
        return True
    
    def activate_size_reduction(self):
        """Activate 50% position size reduction."""
        self.size_reduction_active = True
        
        if self.logger:
            self.logger.warning(" Position size reduced to 50% due to drawdown")
    
    def get_size_multiplier(self) -> float:
        """
        Get position size multiplier based on circuit breaker state.
        
        Returns:
            1.0 (normal) or 0.5 (reduced)
        """
        return 0.5 if self.size_reduction_active else 1.0
    
    def should_allow_new_trades(self) -> tuple[bool, Optional[str]]:
        """
        Check if new trades are allowed.
        
        Returns:
            (allowed: bool, reason: str)
        """
        if self.is_trading_paused():
            return False, "TRADING_PAUSED"
        
        if self.current_level == 'LEVEL_3':
            return False, "LIQUIDATION_MODE"
        
        return True, None
    
    def reset_daily(self):
        """Reset circuit breaker for new trading day."""
        self.current_level = None
        self.breaker_triggered_time = None
        self.pause_until = None
        self.size_reduction_active = False
        
        if self.logger:
            self.logger.info(" Circuit breaker reset for new day")
    
    def get_status(self) -> Dict:
        """Get current circuit breaker status."""
        return {
            'current_level': self.current_level,
            'trading_paused': self.is_trading_paused(),
            'pause_until': self.pause_until.isoformat() if self.pause_until else None,
            'size_reduction_active': self.size_reduction_active,
            'size_multiplier': self.get_size_multiplier()
        }


class AnomalyDetector:
    """
    Detects abnormal market/system conditions.
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        
        # Error tracking
        self.broker_errors = []
        self.max_consecutive_errors = 3
        
        # Slippage tracking
        self.slippage_history = []
    
    def check_volatility_spike(
        self,
        current_atr: float,
        avg_atr: float,
        threshold_multiplier: float = 3.0
    ) -> bool:
        """
        Detect volatility spike.
        
        Args:
            current_atr: Current ATR
            avg_atr: Average ATR
            threshold_multiplier: Spike threshold (default 3x)
        
        Returns:
            True if spike detected
        """
        if avg_atr <= 0:
            return False
        
        if current_atr > (avg_atr * threshold_multiplier):
            if self.logger:
                self.logger.warning(
                    f" VOLATILITY SPIKE: ATR {current_atr:.4f} > "
                    f"{threshold_multiplier} avg ({avg_atr:.4f})"
                )
            return True
        
        return False
    
    def log_broker_error(self, error_msg: str):
        """Log broker API error."""
        self.broker_errors.append({
            'time': datetime.now(),
            'error': error_msg
        })
        
        # Keep only last 10 errors
        if len(self.broker_errors) > 10:
            self.broker_errors.pop(0)
    
    def check_consecutive_errors(self) -> bool:
        """
        Check if too many consecutive errors.
        
        Returns:
            True if critical error count reached
        """
        if len(self.broker_errors) < self.max_consecutive_errors:
            return False
        
        # Check if last N errors happened within 5 minutes
        recent_errors = self.broker_errors[-self.max_consecutive_errors:]
        time_span = (recent_errors[-1]['time'] - recent_errors[0]['time']).total_seconds()
        
        if time_span < 300:  # 5 minutes
            if self.logger:
                self.logger.error(
                    f" CRITICAL: {self.max_consecutive_errors} broker errors "
                    f"in {time_span:.0f} seconds"
                )
            return True
        
        return False
    
    def check_slippage(
        self,
        expected_price: float,
        fill_price: float,
        max_slippage_pct: float = 0.002  # 0.2%
    ) -> bool:
        """
        Check if slippage is excessive.
        
        Args:
            expected_price: Expected fill price
            fill_price: Actual fill price
            max_slippage_pct: Max allowed slippage (default 0.2%)
        
        Returns:
            True if excessive slippage
        """
        if expected_price <= 0:
            return False
        
        slippage_pct = abs(fill_price - expected_price) / expected_price
        
        self.slippage_history.append(slippage_pct)
        
        # Keep only last 20 fills
        if len(self.slippage_history) > 20:
            self.slippage_history.pop(0)
        
        if slippage_pct > max_slippage_pct:
            if self.logger:
                self.logger.warning(
                    f" EXCESSIVE SLIPPAGE: {slippage_pct*100:.2f}% | "
                    f"Expected: {expected_price:.2f}, Fill: {fill_price:.2f}"
                )
            return True
        
        return False
    
    def get_avg_slippage(self) -> float:
        """Get average slippage percentage."""
        if not self.slippage_history:
            return 0.0
        
        return sum(self.slippage_history) / len(self.slippage_history)

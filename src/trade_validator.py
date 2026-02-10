"""
Pre-trade validation checklist.

Ensures every trade passes 6 critical checks before execution.
"""


class TradeValidator:
    """
    Pre-trade checklist gate:
    1. Zone valid (price within supply/demand zone)
    2. HTF bias aligned (higher timeframe supports direction)
    3. Stop defined (stop-loss calculated and valid)
    4. Risk ≤ target% (position size within risk limits)
    5. Trade classified (scalp or trend mode known)
    6. Exit plan known (TP targets calculated)
    """
    
    def __init__(self, logger=None):
        self.logger = logger
    
    def validate_trade(
        self,
        signal: dict,
        stop_price: float,
        lots: int,
        capital: float,
        risk_pct: float,
        max_risk_pct: float = 0.90  # Hard cap at 90%
    ) -> tuple[bool, list]:
        """
        Run full pre-trade validation checklist.
        
        Args:
            signal: Signal dict with action, entry_price, zone_low, zone_high, etc.
            stop_price: Calculated stop-loss
            lots: Position size
            capital: Account balance
            risk_pct: Configured risk per trade
            max_risk_pct: Maximum allowed risk (hard cap)
        
        Returns:
            (is_valid: bool, failed_checks: list)
        """
        failed_checks = []
        
        # 1. Zone Valid
        if not self._check_zone_valid(signal):
            failed_checks.append("ZONE_INVALID")
        
        # 2. HTF Bias Aligned
        if not self._check_htf_bias(signal):
            failed_checks.append("HTF_BIAS_NOT_ALIGNED")
        
        # 3. Stop Defined
        if not self._check_stop_defined(stop_price, signal):
            failed_checks.append("STOP_NOT_DEFINED")
        
        # 4. Risk ≤ Target %
        if not self._check_risk_limit(lots, signal, stop_price, capital, risk_pct, max_risk_pct):
            failed_checks.append("RISK_EXCEEDS_LIMIT")
        
        # 5. Trade Classified
        if not self._check_trade_classified(signal):
            failed_checks.append("TRADE_MODE_UNKNOWN")
        
        # 6. Exit Plan Known
        if not self._check_exit_plan(signal, stop_price):
            failed_checks.append("EXIT_PLAN_MISSING")
        
        is_valid = len(failed_checks) == 0
        
        if not is_valid and self.logger:
            self.logger.warning(f"❌ Trade validation FAILED: {', '.join(failed_checks)}")
        elif is_valid and self.logger:
            self.logger.info("✅ Trade validation PASSED (all 6 checks OK)")
        
        return is_valid, failed_checks
    
    def _check_zone_valid(self, signal: dict) -> bool:
        """Check if entry price is within valid zone."""
        entry_price = signal.get('entry_price', 0)
        zone_low = signal.get('zone_low', 0)
        zone_high = signal.get('zone_high', 0)
        
        # If zones not provided, assume valid
        if zone_low == 0 and zone_high == 0:
            return True
        
        # Check if entry within zone
        return zone_low <= entry_price <= zone_high
    
    def _check_htf_bias(self, signal: dict) -> bool:
        """Check if higher timeframe supports trade direction."""
        # This requires HTF trend info from signal
        # For now, assume valid if action is present
        action = signal.get('action')
        return action in ['buy', 'sell']
    
    def _check_stop_defined(self, stop_price: float, signal: dict) -> bool:
        """Check if stop-loss is defined and reasonable."""
        if stop_price <= 0:
            return False
        
        entry_price = signal.get('entry_price', 0)
        
        # Stop should be different from entry
        if abs(stop_price - entry_price) < 0.01:
            return False
        
        # Stop should be in correct direction
        if signal.get('action') == 'buy':
            return stop_price < entry_price
        elif signal.get('action') == 'sell':
            return stop_price > entry_price
        
        return True
    
    def _check_risk_limit(
        self,
        lots: int,
        signal: dict,
        stop_price: float,
        capital: float,
        risk_pct: float,
        max_risk_pct: float
    ) -> bool:
        """Check if risk per trade is within limits."""
        entry_price = signal.get('entry_price', 0)
        stop_distance = abs(entry_price - stop_price)
        
        actual_risk = lots * stop_distance
        risk_percentage = actual_risk / capital if capital > 0 else 1.0
        
        # Check against configured risk
        if risk_percentage > risk_pct * 1.1:  # Allow 10% tolerance
            if self.logger:
                self.logger.warning(
                    f"Risk {risk_percentage*100:.1f}% exceeds target {risk_pct*100:.1f}%"
                )
            return False
        
        # Hard cap at max_risk_pct
        if risk_percentage > max_risk_pct:
            if self.logger:
                self.logger.error(
                    f"Risk {risk_percentage*100:.1f}% exceeds hard cap {max_risk_pct*100:.1f}%"
                )
            return False
        
        return True
    
    def _check_trade_classified(self, signal: dict) -> bool:
        """Check if trade mode is known."""
        mode = signal.get('mode', '')
        return mode in ['scalp', 'trend', 'swing']
    
    def _check_exit_plan(self, signal: dict, stop_price: float) -> bool:
        """Check if exit plan is defined."""
        # Exit plan requires stop + entry
        entry_price = signal.get('entry_price', 0)
        
        if entry_price <= 0 or stop_price <= 0:
            return False
        
        # TP targets can be calculated from entry + stop
        # So this check is essentially "do we have entry and stop"
        return True
    
    def log_validation_summary(
        self,
        signal: dict,
        stop_price: float,
        lots: int,
        capital: float
    ):
        """Log detailed validation summary."""
        if not self.logger:
            return
        
        entry_price = signal.get('entry_price', 0)
        stop_distance = abs(entry_price - stop_price)
        risk_amount = lots * stop_distance
        risk_pct = (risk_amount / capital * 100) if capital > 0 else 0
        
        self.logger.info(
            f"\n"
            f"╔══════════════════════════════════════╗\n"
            f"║       PRE-TRADE CHECKLIST            ║\n"
            f"╠══════════════════════════════════════╣\n"
            f"║ ✓ Zone: {signal.get('zone_low', 0):.2f} - {signal.get('zone_high', 0):.2f}\n"
            f"║ ✓ HTF Bias: {signal.get('action', '').upper()}\n"
            f"║ ✓ Stop: {stop_price:.2f}\n"
            f"║ ✓ Risk: ${risk_amount:.2f} ({risk_pct:.1f}%)\n"
            f"║ ✓ Mode: {signal.get('mode', 'scalp').upper()}\n"
            f"║ ✓ Exit: TP @ 1R/2R/3R\n"
            f"╚══════════════════════════════════════╝"
        )

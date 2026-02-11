import pandas as pd
from datetime import datetime, time
from typing import Dict, Optional, Tuple
import pytz


class ExitManager:
    """
    Exit strategy manager:
    - Partial take-profit (1R: 60%, 2R: 30%, 3R: 10%)
    - Trailing stops (structure-based)
    - EOD exits (3:10 PM IST for options)
    """
    
    def __init__(self, logger=None, timezone='Asia/Kolkata'):
        self.logger = logger
        self.timezone = pytz.timezone(timezone)
        
        # Partial exit configuration (user-specified)
        self.tp_config = {
            '1R': {'r_multiple': 1.0, 'exit_pct': 0.60},  # 60% at 1R
            '2R': {'r_multiple': 2.0, 'exit_pct': 0.30},  # 30% at 2R
            '3R': {'r_multiple': 3.0, 'exit_pct': 0.10}   # 10% at 3R
        }
    
    def calculate_r_targets(
        self,
        entry_price: float,
        stop_price: float,
        side: str
    ) -> Dict[str, float]:
        """
        Calculate R-multiple target prices.
        
        Args:
            entry_price: Entry price
            stop_price: Stop-loss price
            side: 'buy' or 'sell'
        
        Returns:
            Dict with 1R, 2R, 3R target prices
        """
        risk = abs(entry_price - stop_price)
        
        if side.lower() == 'buy':
            return {
                '1R': entry_price + (1 * risk),
                '2R': entry_price + (2 * risk),
                '3R': entry_price + (3 * risk)
            }
        else:  # sell/short
            return {
                '1R': entry_price - (1 * risk),
                '2R': entry_price - (2 * risk),
                '3R': entry_price - (3 * risk)
            }
    
    def check_partial_tp(
        self,
        position: Dict,
        current_price: float
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Check if any partial take-profit targets hit.
        
        Args:
            position: Position dict with entry_price, stop_price, side, tp_hits
            current_price: Current market price
        
        Returns:
            (should_exit: bool, tp_level: str, exit_pct: float)
        """
        side = position['side']
        tp_targets = self.calculate_r_targets(
            position['entry_price'],
            position['stop_price'],
            side
        )
        
        # Track which TPs have already been hit
        tp_hits = position.get('tp_hits', {'1R': False, '2R': False, '3R': False})
        
        # Check in order: 1R, 2R, 3R
        for level in ['1R', '2R', '3R']:
            if tp_hits.get(level, False):
                continue  # Already hit
            
            target_price = tp_targets[level]
            
            # Check if target reached
            if side.lower() == 'buy':
                if current_price >= target_price:
                    exit_pct = self.tp_config[level]['exit_pct']
                    
                    if self.logger:
                        self.logger.info(
                            f" TP {level} HIT: Price={current_price:.2f} >= "
                            f"Target={target_price:.2f}, exiting {exit_pct*100:.0f}%"
                        )
                    
                    return True, level, exit_pct
            
            else:  # sell
                if current_price <= target_price:
                    exit_pct = self.tp_config[level]['exit_pct']
                    
                    if self.logger:
                        self.logger.info(
                            f" TP {level} HIT: Price={current_price:.2f} <= "
                            f"Target={target_price:.2f}, exiting {exit_pct*100:.0f}%"
                        )
                    
                    return True, level, exit_pct
        
        return False, None, None
    
    def update_trailing_stop(
        self,
        position: Dict,
        bars_1m: pd.DataFrame
    ) -> float:
        """
        Update trailing stop based on price structure.
        
        BUY: Trail below last higher low (last 5 candles)
        SELL: Trail above last lower high (last 5 candles)
        
        Args:
            position: Position dict
            bars_1m: Recent 1m bars
        
        Returns:
            Updated trailing stop price
        """
        if len(bars_1m) < 3:
            return position.get('trailing_stop', position['stop_price'])
        
        current_trailing = position.get('trailing_stop', position['stop_price'])
        side = position['side']
        
        # Look at last 5 candles for structure
        lookback = min(5, len(bars_1m))
        recent_bars = bars_1m.iloc[-lookback:]
        
        if side.lower() == 'buy':
            # Trail below last higher low
            recent_lows = recent_bars['Low'].values
            last_higher_low = max(recent_lows)
            
            # Only move stop UP (never down for long)
            new_stop = max(current_trailing, last_higher_low)
        
        elif side.lower() == 'sell':
            # Trail above last lower high
            recent_highs = recent_bars['High'].values
            last_lower_high = min(recent_highs)
            
            # Only move stop DOWN (never up for short)
            new_stop = min(current_trailing, last_lower_high)
        
        else:
            return current_trailing
        
        # Log if stop moved
        if new_stop != current_trailing and self.logger:
            self.logger.info(
                f" Trailing stop updated ({side.upper()}): "
                f"{current_trailing:.2f}  {new_stop:.2f}"
            )
        
        return new_stop
    
    def check_eod_exit(
        self,
        current_time: Optional[datetime] = None,
        eod_time_str: str = "15:10"
    ) -> bool:
        """
        Check if end-of-day exit time reached.
        
        Force close all options positions at 3:10 PM IST.
        
        Args:
            current_time: Current datetime (defaults to now)
            eod_time_str: EOD time in HH:MM format
        
        Returns:
            True if past EOD time, False otherwise
        """
        if current_time is None:
            current_time = datetime.now(self.timezone)
        
        # Parse EOD time
        eod_hour, eod_minute = map(int, eod_time_str.split(':'))
        eod_time = time(eod_hour, eod_minute)
        
        # Check if current time >= EOD time
        if current_time.time() >= eod_time:
            if self.logger:
                self.logger.warning(
                    f" EOD EXIT: Current time {current_time.strftime('%H:%M')} >= "
                    f"EOD cutoff {eod_time_str}"
                )
            return True
        
        return False
    
    def execute_partial_exit(
        self,
        position: Dict,
        exit_pct: float,
        tp_level: str
    ) -> int:
        """
        Calculate exit quantity for partial TP.
        
        Args:
            position: Position dict with original_qty, current_qty
            exit_pct: Percentage to exit (0.60 = 60%)
            tp_level: TP level hit (1R, 2R, 3R)
        
        Returns:
            Quantity to exit
        """
        current_qty = position.get('current_qty', position.get('original_qty', 0))
        
        if current_qty <= 0:
            if self.logger:
                self.logger.warning(f"No quantity remaining for partial exit at {tp_level}")
            return 0
        
        # Calculate exit quantity based on ORIGINAL position size
        original_qty = position['original_qty']
        exit_qty = int(original_qty * exit_pct)
        
        # Ensure we don't exit more than current qty
        exit_qty = min(exit_qty, current_qty)
        
        # Always exit at least 1 if there's quantity remaining
        if exit_qty == 0 and current_qty > 0:
            exit_qty = 1
        
        if self.logger:
            self.logger.info(
                f"Partial exit at {tp_level}: {exit_qty} lots "
                f"({exit_pct*100:.0f}% of {original_qty}), "
                f"remaining: {current_qty - exit_qty}"
            )
        
        return exit_qty
    
    def should_move_to_breakeven(
        self,
        position: Dict,
        current_price: float
    ) -> bool:
        """
        Check if position should move stop to breakeven.
        
        Move to BE after 1R target hit.
        
        Args:
            position: Position dict
            current_price: Current price
        
        Returns:
            True if should move to BE
        """
        if position.get('moved_to_be', False):
            return False  # Already moved
        
        tp_targets = self.calculate_r_targets(
            position['entry_price'],
            position['stop_price'],
            position['side']
        )
        
        # Check if 1R hit
        if position['side'].lower() == 'buy':
            if current_price >= tp_targets['1R']:
                return True
        else:
            if current_price <= tp_targets['1R']:
                return True
        
        return False
    
    def get_exit_summary(self, position: Dict, current_price: float) -> Dict:
        """
        Generate exit summary for position.
        
        Returns:
            Dict with TP targets, trailing stop, EOD status
        """
        tp_targets = self.calculate_r_targets(
            position['entry_price'],
            position['stop_price'],
            position['side']
        )
        
        return {
            'entry_price': position['entry_price'],
            'current_price': current_price,
            'stop_price': position.get('trailing_stop', position['stop_price']),
            'tp_targets': tp_targets,
            'tp_hits': position.get('tp_hits', {'1R': False, '2R': False, '3R': False}),
            'current_qty': position.get('current_qty', position.get('original_qty', 0)),
            'original_qty': position['original_qty'],
            'unrealized_pnl': self._calculate_pnl(position, current_price)
        }
    
    def _calculate_pnl(self, position: Dict, current_price: float) -> float:
        """Calculate unrealized P&L."""
        current_qty = position.get('current_qty', position.get('original_qty', 0))
        
        if position['side'].lower() == 'buy':
            pnl = (current_price - position['entry_price']) * current_qty
        else:
            pnl = (position['entry_price'] - current_price) * current_qty
        
        return pnl

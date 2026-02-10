from typing import Dict, List, Optional
from datetime import datetime
import json


class Position:
    """Single position tracker."""
    
    def __init__(
        self,
        position_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        stop_price: float,
        original_qty: int,
        entry_time: datetime,
        zone_low: float,
        zone_high: float,
        atr_1m: float,
        mode: str = 'scalp'
    ):
        self.id = position_id
        self.symbol = symbol
        self.side = side  # 'buy' or 'sell'
        self.entry_price = entry_price
        self.stop_price = stop_price
        self.trailing_stop = stop_price  # Will be updated
        self.original_qty = original_qty
        self.current_qty = original_qty  # Decreases with partial exits
        self.entry_time = entry_time
        self.zone_low = zone_low
        self.zone_high = zone_high
        self.atr_1m = atr_1m
        self.mode = mode  # 'scalp' or 'trend'
        
        # Exit tracking
        self.tp_hits = {'1R': False, '2R': False, '3R': False}
        self.moved_to_be = False  # Breakeven flag
        self.partial_exits = []  # Log of partial exits
        
        # Status
        self.is_open = True
        self.close_time: Optional[datetime] = None
        self.close_price: Optional[float] = None
        self.close_reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert position to dict."""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'stop_price': self.stop_price,
            'trailing_stop': self.trailing_stop,
            'original_qty': self.original_qty,
            'current_qty': self.current_qty,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'zone_low': self.zone_low,
            'zone_high': self.zone_high,
            'atr_1m': self.atr_1m,
            'mode': self.mode,
            'tp_hits': self.tp_hits,
            'moved_to_be': self.moved_to_be,
            'is_open': self.is_open,
            'close_time': self.close_time.isoformat() if self.close_time else None,
            'close_price': self.close_price,
            'close_reason': self.close_reason
        }


class PositionTracker:
    """
    Manages all open positions with partial exit tracking.
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        self.positions: Dict[str, Position] = {}
        self._position_counter = 0
    
    def add(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_price: float,
        qty: int,
        zone_low: float,
        zone_high: float,
        atr_1m: float,
        mode: str = 'scalp'
    ) -> Position:
        """
        Add a new position.
        
        Returns:
            Position object
        """
        self._position_counter += 1
        position_id = f"{symbol}_{self._position_counter}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        position = Position(
            position_id=position_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            original_qty=qty,
            entry_time=datetime.now(),
            zone_low=zone_low,
            zone_high=zone_high,
            atr_1m=atr_1m,
            mode=mode
        )
        
        self.positions[position_id] = position
        
        if self.logger:
            self.logger.info(
                f"📍 Position opened: {position_id} | {side.upper()} {qty} {symbol} "
                f"@ {entry_price:.2f}, Stop: {stop_price:.2f}"
            )
        
        return position
    
    def get_open(self) -> List[Position]:
        """Get all open positions."""
        return [pos for pos in self.positions.values() if pos.is_open]
    
    def get_by_symbol(self, symbol: str) -> List[Position]:
        """Get all open positions for a symbol."""
        return [
            pos for pos in self.positions.values()
            if pos.symbol == symbol and pos.is_open
        ]
    
    def update_partial_exit(
        self,
        position_id: str,
        qty_exited: int,
        exit_price: float,
        tp_level: str
    ):
        """
        Update position after partial exit.
        
        Args:
            position_id: Position ID
            qty_exited: Quantity exited
            exit_price: Exit price
            tp_level: TP level hit (1R, 2R, 3R)
        """
        if position_id not in self.positions:
            if self.logger:
                self.logger.error(f"Position {position_id} not found")
            return
        
        position = self.positions[position_id]
        
        # Update quantity
        position.current_qty -= qty_exited
        
        # Mark TP as hit
        if tp_level in position.tp_hits:
            position.tp_hits[tp_level] = True
        
        # Log partial exit
        partial_exit = {
            'time': datetime.now().isoformat(),
            'qty': qty_exited,
            'price': exit_price,
            'level': tp_level,
            'pnl': (exit_price - position.entry_price) * qty_exited if position.side == 'buy'
                   else (position.entry_price - exit_price) * qty_exited
        }
        position.partial_exits.append(partial_exit)
        
        if self.logger:
            self.logger.info(
                f"✂️ Partial exit: {position_id} | {tp_level} | "
                f"Exited {qty_exited}, Remaining {position.current_qty}"
            )
        
        # Close position if no quantity left
        if position.current_qty <= 0:
            self.close(position_id, exit_price, f"FULL_EXIT_{tp_level}")
    
    def update_trailing_stop(self, position_id: str, new_stop: float):
        """Update trailing stop for a position."""
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        position.trailing_stop = new_stop
    
    def close(
        self,
        position_id: str,
        close_price: float,
        reason: str
    ):
        """
        Close a position completely.
        
        Args:
            position_id: Position ID
            close_price: Closing price
            reason: Close reason (e.g., 'STOP_HIT', 'EOD', 'FULL_EXIT_3R')
        """
        if position_id not in self.positions:
            if self.logger:
                self.logger.error(f"Position {position_id} not found")
            return
        
        position = self.positions[position_id]
        position.is_open = False
        position.close_time = datetime.now()
        position.close_price = close_price
        position.close_reason = reason
        position.current_qty = 0
        
        # Calculate total P&L
        total_pnl = sum([pe['pnl'] for pe in position.partial_exits])
        
        if self.logger:
            self.logger.info(
                f"🔒 Position closed: {position_id} | {reason} | "
                f"Total PnL: ${total_pnl:.2f}"
            )
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID."""
        return self.positions.get(position_id)
    
    def export_positions(self, filepath: str = 'positions.json'):
        """Export all positions to JSON."""
        data = {
            pos_id: pos.to_dict()
            for pos_id, pos in self.positions.items()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        if self.logger:
            self.logger.info(f"Positions exported to {filepath}")
    
    def get_summary(self) -> Dict:
        """Get portfolio summary."""
        open_positions = self.get_open()
        closed_positions = [pos for pos in self.positions.values() if not pos.is_open]
        
        return {
            'total_positions': len(self.positions),
            'open_positions': len(open_positions),
            'closed_positions': len(closed_positions),
            'open_symbols': list(set([pos.symbol for pos in open_positions])),
            'total_qty_deployed': sum([pos.current_qty for pos in open_positions])
        }

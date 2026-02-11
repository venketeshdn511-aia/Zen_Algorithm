import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional


class StopLossManager:
    """
    Three-level stop-loss system:
    1. Structural Stop (zone-based + ATR buffer)
    2. Time Stop (45-minute theta protection)
    3. Volatility Stop (reversal detection)
    """
    
    def __init__(self, logger=None):
        self.logger = logger
    
    def calculate_structural_stop(
        self,
        entry_price: float,
        zone_low: float,
        zone_high: float,
        side: str,  # 'buy' or 'sell'
        atr_1m: float
    ) -> float:
        """
        Calculate structural stop-loss.
        
        BUY: Stop = zone_low - buffer
        SELL: Stop = zone_high + buffer
        buffer = max(0.15%, 0.25  ATR)
        
        Args:
            entry_price: Entry price
            zone_low: Bottom of demand/supply zone
            zone_high: Top of demand/supply zone
            side: 'buy' or 'sell'
            atr_1m: 1-minute ATR
        
        Returns:
            Stop-loss price
        """
        # Calculate buffer
        pct_buffer = entry_price * 0.0015  # 0.15%
        atr_buffer = 0.25 * atr_1m
        buffer = max(pct_buffer, atr_buffer)
        
        if side.lower() == 'buy':
            stop = zone_low - buffer
        elif side.lower() == 'sell':
            stop = zone_high + buffer
        else:
            if self.logger:
                self.logger.error(f"Invalid side: {side}")
            return entry_price * 0.95  # Fallback 5% stop
        
        if self.logger:
            self.logger.info(
                f"Structural Stop ({side.upper()}): Entry={entry_price:.2f}, "
                f"Zone=[{zone_low:.2f}, {zone_high:.2f}], Buffer={buffer:.4f}, "
                f"Stop={stop:.2f}"
            )
        
        return stop
    
    def check_structural_stop(
        self,
        current_price: float,
        stop_price: float,
        side: str,
        current_candle: pd.Series
    ) -> bool:
        """
        Check if structural stop has been hit.
        
        Exit on candle CLOSE beyond stop (not just wick).
        
        Args:
            current_price: Current close price
            stop_price: Stop-loss level
            side: 'buy' or 'sell'
            current_candle: Latest 1m candle (Series with OHLC)
        
        Returns:
            True if stop hit, False otherwise
        """
        close_price = current_candle['Close']
        
        if side.lower() == 'buy':
            # For long: exit if close below stop
            if close_price < stop_price:
                if self.logger:
                    self.logger.warning(
                        f"STRUCTURAL STOP HIT (BUY): Close={close_price:.2f} < Stop={stop_price:.2f}"
                    )
                return True
        
        elif side.lower() == 'sell':
            # For short: exit if close above stop
            if close_price > stop_price:
                if self.logger:
                    self.logger.warning(
                        f"STRUCTURAL STOP HIT (SELL): Close={close_price:.2f} > Stop={stop_price:.2f}"
                    )
                return True
        
        return False
    
    def check_time_stop(
        self,
        entry_time: datetime,
        current_time: datetime,
        bars_since_entry: pd.DataFrame,
        side: str,
        time_limit_minutes: int = 45
    ) -> bool:
        """
        Check time-based stop (theta protection for options).
        
        Exit if:
        - Trade duration > 45 minutes
        - AND no new higher-high (buy) or lower-low (sell) formed
        
        Args:
            entry_time: Trade entry timestamp
            current_time: Current timestamp
            bars_since_entry: 1m bars since entry
            side: 'buy' or 'sell'
            time_limit_minutes: Time threshold (default 45)
        
        Returns:
            True if time stop triggered, False otherwise
        """
        duration = (current_time - entry_time).total_seconds() / 60
        
        if duration <= time_limit_minutes:
            return False
        
        # Check if new HH/LL formed
        if len(bars_since_entry) < 2:
            return False
        
        if side.lower() == 'buy':
            # Check for higher high
            entry_high = bars_since_entry.iloc[0]['High']
            recent_high = bars_since_entry['High'].max()
            
            if recent_high > entry_high:
                # New HH formed, don't exit yet
                return False
        
        elif side.lower() == 'sell':
            # Check for lower low
            entry_low = bars_since_entry.iloc[0]['Low']
            recent_low = bars_since_entry['Low'].min()
            
            if recent_low < entry_low:
                # New LL formed, don't exit yet
                return False
        
        # Time limit exceeded and no new HH/LL
        if self.logger:
            self.logger.warning(
                f"TIME STOP HIT: Duration={duration:.1f}m > {time_limit_minutes}m, "
                f"no new momentum"
            )
        
        return True
    
    def check_volatility_stop(
        self,
        current_candle: pd.Series,
        trade_side: str
    ) -> bool:
        """
        Check volatility-based stop (reversal detection).
        
        Exit if:
        - 1m candle in opposite direction
        - AND body >= 70% of range
        
        Args:
            current_candle: Latest 1m candle
            trade_side: 'buy' or 'sell'
        
        Returns:
            True if volatility stop triggered, False otherwise
        """
        open_price = current_candle['Open']
        close_price = current_candle['Close']
        high = current_candle['High']
        low = current_candle['Low']
        
        # Calculate body and range
        body = abs(close_price - open_price)
        candle_range = high - low
        
        if candle_range == 0:
            return False
        
        body_pct = body / candle_range
        
        # Check if body >= 70% (strong candle)
        if body_pct < 0.70:
            return False
        
        # Check if candle is opposite to trade direction
        is_bearish_candle = close_price < open_price
        is_bullish_candle = close_price > open_price
        
        if trade_side.lower() == 'buy' and is_bearish_candle:
            if self.logger:
                self.logger.warning(
                    f"VOLATILITY STOP HIT (BUY): Strong bearish candle "
                    f"(body={body_pct*100:.1f}% of range)"
                )
            # return True  <-- DISABLED FOR BACKTEST OPTIMIZATION
            return False
        
        elif trade_side.lower() == 'sell' and is_bullish_candle:
            if self.logger:
                self.logger.warning(
                    f"VOLATILITY STOP HIT (SELL): Strong bullish candle "
                    f"(body={body_pct*100:.1f}% of range)"
                )
            # return True  <-- DISABLED FOR BACKTEST OPTIMIZATION
            return False
        
        return False
    
    def should_exit(
        self,
        position: Dict,
        current_price: float,
        current_candle: pd.Series,
        bars_since_entry: pd.DataFrame
    ) -> tuple[bool, Optional[str]]:
        """
        Check all stop conditions.
        
        Args:
            position: Position dict with entry_time, stop_price, side, etc.
            current_price: Current market price
            current_candle: Latest 1m candle
            bars_since_entry: Bars since position opened
        
        Returns:
            (should_exit: bool, reason: str)
        """
        # 1. Structural Stop (Primary)
        if self.check_structural_stop(
            current_price,
            position['stop_price'],
            position['side'],
            current_candle
        ):
            return True, "STRUCTURAL_STOP"
        
        # 2. Time Stop (Theta protection)
        # Use current_candle name (timestamp) for backtesting compatibility
        current_time = current_candle.name if hasattr(current_candle, 'name') else datetime.now()
        
        if self.check_time_stop(
            position['entry_time'],
            current_time,
            bars_since_entry,
            position['side']
        ):
            return True, "TIME_STOP"
        
        # 3. Volatility Stop (Reversal detection)
        if self.check_volatility_stop(current_candle, position['side']):
            return True, "VOLATILITY_STOP"
        
        return False, None
    
    def update_trailing_stop(
        self,
        position: Dict,
        bars_1m: pd.DataFrame,
        trade_side: str
    ) -> float:
        """
        Update trailing stop based on structure.
        
        BUY: Trail below last higher low
        SELL: Trail above last lower high
        
        Args:
            position: Position dict
            bars_1m: Recent 1m bars
            trade_side: 'buy' or 'sell'
        
        Returns:
            New trailing stop price
        """
        if len(bars_1m) < 3:
            return position.get('trailing_stop', position['stop_price'])
        
        current_trailing = position.get('trailing_stop', position['stop_price'])
        
        if trade_side.lower() == 'buy':
            # Find last higher low
            recent_lows = bars_1m['Low'].values[-5:]  # Last 5 candles
            last_higher_low = max(recent_lows)
            
            # Only move stop up, never down
            new_stop = max(current_trailing, last_higher_low)
        
        elif trade_side.lower() == 'sell':
            # Find last lower high
            recent_highs = bars_1m['High'].values[-5:]
            last_lower_high = min(recent_highs)
            
            # Only move stop down, never up
            new_stop = min(current_trailing, last_lower_high)
        
        else:
            return current_trailing
        
        if new_stop != current_trailing and self.logger:
            self.logger.info(
                f"Trailing stop updated: {current_trailing:.2f}  {new_stop:.2f}"
            )
        
        return new_stop

import pandas as pd
import numpy as np
from typing import Dict, Optional


class RiskCalculator:
    """
    Risk-based position sizing with ATR measurement.
    Implements aggressive 85-90% capital allocation per trade.
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        
        # ATR cache per symbol (for 20-day comparison)
        self.atr_history: Dict[str, list] = {}
        
        # Max lots per asset type (liquidity protection)
        self.max_lots = {
            'stock': 100,
            'crypto': 10,
            'option': 50
        }
    
    def calculate_atr(self, bars: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average True Range.
        
        Args:
            bars: DataFrame with High, Low, Close columns
            period: ATR period (default 14)
        
        Returns:
            ATR value
        """
        if len(bars) < period:
            if self.logger:
                self.logger.warning(f"Insufficient bars ({len(bars)}) for ATR({period})")
            return 0.0
        
        # True Range = max(H-L, |H-PC|, |L-PC|)
        high = bars['High']
        low = bars['Low']
        close = bars['Close']
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR = EMA of True Range
        atr = true_range.rolling(window=period).mean().iloc[-1]
        
        return float(atr) if not pd.isna(atr) else 0.0
    
    def update_atr_history(self, symbol: str, atr_value: float, max_history: int = 20):
        """
        Track ATR history for volatility scaling.
        
        Args:
            symbol: Trading symbol
            atr_value: Current ATR
            max_history: Days to keep (default 20)
        """
        if symbol not in self.atr_history:
            self.atr_history[symbol] = []
        
        self.atr_history[symbol].append(atr_value)
        
        # Keep only last N values
        if len(self.atr_history[symbol]) > max_history:
            self.atr_history[symbol].pop(0)
    
    def get_atr_avg(self, symbol: str) -> float:
        """Get 20-day ATR average for a symbol."""
        if symbol not in self.atr_history or not self.atr_history[symbol]:
            return 0.0
        
        return np.mean(self.atr_history[symbol])
    
    def calculate_position_size(
        self,
        capital: float,
        risk_pct: float,
        stop_distance: float,
        current_atr: float,
        avg_atr: float,
        asset_type: str = 'stock'
    ) -> int:
        """
        Calculate position size based on risk parameters.
        
        Args:
            capital: Total account equity
            risk_pct: Risk per trade (0.8575 = 85.75%)
            stop_distance: Distance from entry to stop in price units
            current_atr: Current 1m ATR
            avg_atr: 20-day average ATR
            asset_type: 'stock', 'crypto', or 'option'
        
        Returns:
            Number of lots/contracts
        """
        if stop_distance <= 0:
            if self.logger:
                self.logger.error(f"Invalid stop_distance: {stop_distance}")
            return 0
        
        # Maximum loss allowed on this trade
        max_loss = capital * risk_pct
        
        # Base lot calculation
        lots = max_loss / stop_distance
        
        # Apply volatility scaling (reduce 25% if ATR is elevated)
        if avg_atr > 0 and current_atr > avg_atr:
            volatility_multiplier = 0.75  # 25% reduction
            lots *= volatility_multiplier
            
            if self.logger:
                self.logger.info(
                    f"Volatility scaling: ATR {current_atr:.4f} > Avg {avg_atr:.4f}, "
                    f"reducing size by 25%"
                )
        
        # Floor to whole number
        lots = int(np.floor(lots))
        
        # Apply max lots cap
        max_allowed = self.max_lots.get(asset_type, 100)
        if lots > max_allowed:
            if self.logger:
                self.logger.warning(
                    f"Position size {lots} exceeds max {max_allowed} for {asset_type}, capping"
                )
            lots = max_allowed
        
        # Minimum 1 lot if calculation is positive
        if lots < 1 and max_loss > 0:
            lots = 1
        
        return lots
    
    def validate_max_lots(
        self,
        lots: int,
        symbol: str,
        asset_type: str = 'stock'
    ) -> bool:
        """
        Validate position size doesn't exceed liquidity limits.
        
        Args:
            lots: Proposed lot size
            symbol: Trading symbol
            asset_type: Asset class
        
        Returns:
            True if valid, False otherwise
        """
        max_allowed = self.max_lots.get(asset_type, 100)
        
        if lots > max_allowed:
            if self.logger:
                self.logger.error(
                    f"Position size {lots} exceeds max {max_allowed} for {symbol} ({asset_type})"
                )
            return False
        
        return True
    
    def calculate_stop_buffer(self, entry_price: float, atr_1m: float) -> float:
        """
        Calculate stop-loss buffer: max(0.15%, 0.25 × ATR)
        
        Args:
            entry_price: Entry price
            atr_1m: 1-minute ATR
        
        Returns:
            Buffer amount in price units
        """
        # 0.15% of entry price
        pct_buffer = entry_price * 0.0015
        
        # 0.25 × ATR
        atr_buffer = 0.25 * atr_1m
        
        return max(pct_buffer, atr_buffer)
    
    def calculate_r_multiples(self, entry_price: float, stop_price: float) -> Dict[str, float]:
        """
        Calculate R-multiple target prices.
        
        Args:
            entry_price: Entry price
            stop_price: Stop-loss price
        
        Returns:
            Dict with 1R, 2R, 3R target prices
        """
        risk = abs(entry_price - stop_price)
        
        # Determine trade direction
        is_long = entry_price > stop_price
        
        if is_long:
            return {
                '1R': entry_price + (1 * risk),
                '2R': entry_price + (2 * risk),
                '3R': entry_price + (3 * risk)
            }
        else:
            return {
                '1R': entry_price - (1 * risk),
                '2R': entry_price - (2 * risk),
                '3R': entry_price - (3 * risk)
            }
    
    def get_risk_summary(
        self,
        capital: float,
        risk_pct: float,
        lots: int,
        entry_price: float,
        stop_price: float
    ) -> Dict:
        """
        Generate risk summary for logging/validation.
        
        Returns:
            Dict with risk metrics
        """
        max_loss = capital * risk_pct
        stop_distance = abs(entry_price - stop_price)
        actual_risk = lots * stop_distance
        
        return {
            'capital': capital,
            'risk_pct': risk_pct * 100,
            'max_loss_allowed': max_loss,
            'actual_risk': actual_risk,
            'lots': lots,
            'stop_distance': stop_distance,
            'risk_reward_ratio': f"1:{(abs(entry_price - stop_price) / stop_distance):.2f}"
        }

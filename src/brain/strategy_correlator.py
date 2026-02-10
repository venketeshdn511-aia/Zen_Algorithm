"""
Strategy Correlator
Analyzes correlations between strategies to detect risk concentration.
"""

import logging
from typing import Dict, List
from collections import defaultdict
import math

class StrategyCorrelator:
    """
    Computes correlation matrix of strategy performance.
    Helps prevent over-exposure to correlated risks.
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        # Store daily PnL history: { "StrategyA": [100, -50, 200, ...], ... }
        # All lists should be aligned by day
        self.daily_returns = defaultdict(list)
        self.dates = []
        
    def update_daily_pnl(self, date_str: str, strategy_pnls: Dict[str, float]):
        """
        Record end-of-day PnL for all active strategies.
        Args:
            date_str: "YYYY-MM-DD"
            strategy_pnls: {"StrategyA": 500.0, "StrategyB": -100.0}
        """
        self.dates.append(date_str)
        seen_strategies = set(strategy_pnls.keys())
        
        # Add new data
        for strat, pnl in strategy_pnls.items():
            self.daily_returns[strat].append(pnl)
            
        # Handle missing strategies (0 PnL for that day)
        for strat in self.daily_returns.keys():
            if strat not in seen_strategies:
                self.daily_returns[strat].append(0.0)
                
        # Keep window manageable (last 60 days)
        if len(self.dates) > 60:
            self.dates.pop(0)
            for strat in self.daily_returns:
                self.daily_returns[strat].pop(0)
                
    def get_correlation(self, strat_a: str, strat_b: str) -> float:
        """Get Pearson correlation between two strategies (-1.0 to 1.0)."""
        returns_a = self.daily_returns.get(strat_a, [])
        returns_b = self.daily_returns.get(strat_b, [])
        
        if len(returns_a) < 5 or len(returns_b) < 5:
            return 0.0 # Not enough data
            
        return self._pearson(returns_a, returns_b)
        
    def get_risky_pairs(self, threshold: float = 0.7) -> List[str]:
        """Identify highly correlated strategy pairs."""
        risky = []
        strategies = list(self.daily_returns.keys())
        for i in range(len(strategies)):
            for j in range(i+1, len(strategies)):
                s1, s2 = strategies[i], strategies[j]
                corr = self.get_correlation(s1, s2)
                if corr > threshold:
                    risky.append(f"{s1} & {s2} (Corr: {corr:.2f})")
        return risky
        
    def _pearson(self, x: List[float], y: List[float]) -> float:
        n = len(x)
        if n != len(y): return 0.0
        
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(i*j for i, j in zip(x, y))
        sum_x2 = sum(i**2 for i in x)
        sum_y2 = sum(i**2 for i in y)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2))
        
        if denominator == 0: return 0.0
        return numerator / denominator

    def get_state(self) -> Dict:
        return {
            'daily_returns': dict(self.daily_returns),
            'dates': self.dates
        }

    def set_state(self, state: Dict):
        if 'daily_returns' in state:
            self.daily_returns = defaultdict(list, state['daily_returns'])
        if 'dates' in state:
            self.dates = state['dates']

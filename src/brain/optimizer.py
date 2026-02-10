"""
Parameter Optimizer
Autonomously suggests improvements to strategy parameters (Risk, RR, Stops)
based on performance history.
"""

import logging
from typing import Dict, List

class ParameterOptimizer:
    """
    Optimizes trading parameters over time.
    Suggestions are bounded to ensure safety.
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.suggestions = {} # { "StrategyName": { "risk_mult": 1.0, ... } }
        
    def analyze_strategy(self, strategy_name: str, trades: List[Dict]):
        """
        Analyze recent trades for a strategy and update optimization suggestions.
        Requires at least 15 recent trades.
        """
        if len(trades) < 15:
            return
            
        # Filter trades for this strategy
        strat_trades = [t for t in trades if t.get('strategy') == strategy_name]
        recent = strat_trades[-20:] # Analyze last 20
        
        if not recent: return
        
        # 1. Calculate Metrics
        wins = sum(1 for t in recent if float(t.get('pnl', 0)) > 0)
        total = len(recent)
        win_rate = wins / total
        
        # Stop loss analysis
        stop_hits = sum(1 for t in recent if 'stop' in str(t.get('reason', '')).lower())
        stop_hit_rate = stop_hits / total
        
        # Current settings (default)
        risk_mult = 1.0
        widen_stops = False
        
        # 2. Optimization Logic
        
        # Risk Scaling
        # If consistenly winning, slowly increase size
        if win_rate > 0.60:
            risk_mult = 1.15
        elif win_rate > 0.70:
            risk_mult = 1.25
        elif win_rate < 0.35:
            risk_mult = 0.8 # Defend capital
            
        # Stop Loss Tuning
        # If stopped out too often (>60%), market noise might be high. Suggest wider stops
        if stop_hit_rate > 0.60:
            widen_stops = True
            
        self.suggestions[strategy_name] = {
            'risk_mult': risk_mult,
            'widen_stops': widen_stops,
            'win_rate': round(win_rate, 2),
            'sample_size': total
        }
        
    def get_suggestion(self, strategy_name: str) -> Dict:
        return self.suggestions.get(strategy_name, {
            'risk_mult': 1.0, 'widen_stops': False
        })
        
    def get_state(self) -> Dict:
        return {'suggestions': self.suggestions}
        
    def set_state(self, state: Dict):
        if 'suggestions' in state:
            self.suggestions = state['suggestions']

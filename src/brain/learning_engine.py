"""
Learning Engine - Core adaptive learning logic for trading bot
Manages trade pattern memory, feedback loops, and parameter suggestions
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pytz

from .trade_analyzer import TradeAnalyzer
from .confidence_scorer import ConfidenceScorer
from .bayesian_learner import BayesianPatternLearner
from .strategy_correlator import StrategyCorrelator
from .optimizer import ParameterOptimizer
from .ml_predictor import MLPredictor


class LearningEngine:
    """
    Core brain of the trading bot.
    
    Features:
    - Records trade outcomes and updates pattern weights
    - Provides confidence scores for new trade setups
    - Suggests parameter adjustments based on performance
    - Persists learning state across restarts
    """
    
    # Cooling-off settings
    LOSING_STREAK_THRESHOLD = 3
    COOLING_OFF_MINUTES = 30
    
    # Parameter adjustment bounds (for safety)
    RISK_PCT_BOUNDS = (0.01, 0.20)  # 1% to 20% max
    RR_RATIO_BOUNDS = (1.0, 4.0)    # 1:1 to 4:1 max
    
    def __init__(self, data_dir: str = None, logger: Optional[logging.Logger] = None):
        """
        Initialize the Learning Engine.
        
        Args:
            data_dir: Directory for persistence (default: ./data)
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Set data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent / "data"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "brain_state.json"
        
        # Initialize Database Handler
        try:
            from src.db.mongodb_handler import get_db_handler
            self.db_handler = get_db_handler()
        except ImportError:
            self.db_handler = None
            self.logger.warning("MongoDB handler import failed - Brain running in local mode only")
        
        # Initialize components
        self.analyzer = TradeAnalyzer(logger=self.logger)
        self.scorer = ConfidenceScorer(logger=self.logger)
        
        # Advanced AI Components
        self.bayesian = BayesianPatternLearner(logger=self.logger)
        self.correlator = StrategyCorrelator(logger=self.logger)
        self.optimizer = ParameterOptimizer(logger=self.logger)
        self.ml_predictor = MLPredictor(logger=self.logger)
        
        # State
        self.state = self._default_state()
        self.insights = {}
        self.cooling_off_until = None
        
        # Load saved state
        self.load_state()
        
        self.logger.info(f"🧠 Brain initialized with {self.state['trade_count']} recorded trades")
    
    def _default_state(self) -> Dict:
        """Default brain state structure."""
        return {
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'last_updated': None,
            'trade_count': 0,
            'trades_today': 0,
            'trades_skipped_today': 0,
            'patterns': {
                'time_windows': {},
                'regime_performance': {},
                'strategy_adjustments': {}
            },
            'trade_history': [],  # Last N trades for analysis
            'daily_stats': {},
            'cooling_off_until': None
        }
    
    def load_state(self) -> bool:
        """Load saved brain state from MongoDB (Cloud) or Disk (Local)."""
        loaded_state = None
        source = "None"
        
        try:
            # 1. Try MongoDB (Cloud Source - Priority)
            if self.db_handler and self.db_handler.connected:
                loaded_state = self.db_handler.load_brain_state()
                if loaded_state:
                    source = "MongoDB"
            
            # 2. Fallback to Local Disk if MongoDB failed or empty
            if not loaded_state and self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    loaded_state = json.load(f)
                    if loaded_state:
                        source = "Local Disk"
            
            if loaded_state:
                # Merge with defaults (handles new fields)
                self.state = {**self._default_state(), **loaded_state}
                
                # Restore cooling-off if active
                if self.state.get('cooling_off_until'):
                    try:
                        self.cooling_off_until = datetime.fromisoformat(self.state['cooling_off_until'])
                    except:
                        self.cooling_off_until = None
                
                # Refresh insights from trade history
                if self.state.get('trade_history'):
                    self.insights = self.analyzer.analyze_trades(self.state['trade_history'])
                    self.scorer.update_insights(self.insights)
                    
                    # Restore Advanced Component States if available
                    if 'bayesian_state' in self.state:
                        self.bayesian.set_state(self.state['bayesian_state'])
                    
                    if 'correlator_state' in self.state:
                        self.correlator.set_state(self.state['correlator_state'])
                        
                    if 'optimizer_state' in self.state:
                        self.optimizer.set_state(self.state['optimizer_state'])
                        
                    # Load ML Model
                    ml_path = self.data_dir / "ml_model.pkl"
                    self.ml_predictor.load(str(ml_path))
                
                self.logger.info(f"🧠 Brain state loaded from {source}: {len(self.state.get('trade_history', []))} trades in history")
                return True
                
        except Exception as e:
            self.logger.warning(f"Could not load brain state: {e}")
            
        return False
    
    def save_state(self) -> bool:
        """Save brain state to MongoDB (Cloud) and Disk (Local)."""
        try:
            self.state['last_updated'] = datetime.now().isoformat()
            self.state['cooling_off_until'] = self.cooling_off_until.isoformat() if self.cooling_off_until else None
            
            # Persist Component States
            self.state['bayesian_state'] = self.bayesian.get_state()
            self.state['correlator_state'] = self.correlator.get_state()
            self.state['optimizer_state'] = self.optimizer.get_state()
            
            # Save ML Model
            ml_path = self.data_dir / "ml_model.pkl"
            self.ml_predictor.save(str(ml_path))

            # 1. Save to Local Disk (Always as backup/cache)
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
                
            # 2. Save to MongoDB (Cloud Persistence)
            if self.db_handler and self.db_handler.connected:
                self.db_handler.save_brain_state(self.state)
                
            return True
        except Exception as e:
            self.logger.error(f"Failed to save brain state: {e}")
            return False
    
    def record_trade_outcome(self, trade: Dict) -> None:
        """
        Record a completed trade and update learning.
        
        Args:
            trade: Dict with at minimum: strategy, pnl, entry_price, exit_price, reason
        """
        # Enrich trade with timestamp if not present
        ist = pytz.timezone('Asia/Kolkata')
        if 'exit_time' not in trade:
            trade['exit_time'] = datetime.now(ist).isoformat()
        if 'entry_time' not in trade:
            trade['entry_time'] = trade['exit_time']  # Fallback
            
        trade_pnl = trade.get('pnl', 0)
        
        # Add to history
        self.state['trade_history'].append(trade)
        self.state['trade_count'] += 1
        self.state['trades_today'] += 1
        
        # Keep history manageable (last 200 trades)
        if len(self.state['trade_history']) > 200:
            self.state['trade_history'] = self.state['trade_history'][-200:]
        
        # Re-analyze patterns
        self.insights = self.analyzer.analyze_trades(self.state['trade_history'])
        self.scorer.update_insights(self.insights)
        
        # Note: Cooling-off feature disabled by user request
        # streak = self.insights.get('streak_analysis', {})
        # if streak.get('is_losing_streak'):
        #     self._trigger_cooling_off(streak.get('consecutive_losses', 3))
        
        # Update AI Components
        is_win = trade_pnl > 0
        self.bayesian.learn(trade, is_win)
        self.optimizer.analyze_strategy(trade.get('strategy', 'Unknown'), self.state['trade_history'])
        
        # Update Correlations (End of Day mostly, but can track live)
        # self.correlator.update_daily_pnl(...) # Handled in TradingEngine daily reset ideally
        
        # Train ML periodically (every 10 trades)
        if self.state['trade_count'] % 10 == 0:
            self.ml_predictor.train(self.state['trade_history'])
        
        # Update strategy-specific adjustments
        self._update_strategy_adjustments(trade)
        
        # Save state
        self.save_state()
        
        self.logger.info(f"🧠 Trade recorded: {trade.get('strategy', 'Unknown')} PnL: ₹{trade_pnl:.2f}")
    
    def _trigger_cooling_off(self, consecutive_losses: int):
        """Trigger cooling-off period after losing streak."""
        ist = pytz.timezone('Asia/Kolkata')
        minutes = self.COOLING_OFF_MINUTES + (consecutive_losses - 3) * 10  # Extra time for longer streaks
        self.cooling_off_until = datetime.now(ist) + timedelta(minutes=minutes)
        
        self.logger.warning(f"🧠 Cooling-off triggered for {minutes} mins ({consecutive_losses} consecutive losses)")
    
    def _update_strategy_adjustments(self, trade: Dict):
        """Update learned parameter adjustments for strategies."""
        strategy = trade.get('strategy', 'Unknown')
        pnl = trade.get('pnl', 0)
        reason = trade.get('reason', '').lower()
        
        if strategy not in self.state['patterns']['strategy_adjustments']:
            self.state['patterns']['strategy_adjustments'][strategy] = {
                'risk_adjustment': 1.0,
                'recent_pnl': [],
                'stop_hit_ratio': 0
            }
        
        adj = self.state['patterns']['strategy_adjustments'][strategy]
        
        # Track recent PnL
        adj['recent_pnl'].append(pnl)
        if len(adj['recent_pnl']) > 20:
            adj['recent_pnl'] = adj['recent_pnl'][-20:]
        
        # Calculate recent performance
        if adj['recent_pnl']:
            recent_wins = sum(1 for p in adj['recent_pnl'] if p > 0)
            recent_win_rate = recent_wins / len(adj['recent_pnl'])
            
            # Adjust risk based on performance
            if recent_win_rate >= 0.65 and len(adj['recent_pnl']) >= 10:
                adj['risk_adjustment'] = min(1.25, adj['risk_adjustment'] + 0.05)
            elif recent_win_rate < 0.40 and len(adj['recent_pnl']) >= 5:
                # USER REQUEST: Do not reduce below base risk (1.0)
                adj['risk_adjustment'] = max(1.0, adj['risk_adjustment'] - 0.1)
            else:
                # Gradual return to normal
                adj['risk_adjustment'] = 0.9 * adj['risk_adjustment'] + 0.1 * 1.0
        
        # Track stop-loss hits
        if 'stop' in reason:
            adj['stop_hit_ratio'] = 0.9 * adj.get('stop_hit_ratio', 0) + 0.1 * 1.0
        else:
            adj['stop_hit_ratio'] = 0.9 * adj.get('stop_hit_ratio', 0)
    
    def get_confidence_score(self, conditions: Dict) -> int:
        """
        Get confidence score for a potential trade.
        
        Args:
            conditions: Dict with current market conditions
        
        Returns:
            Score 0-100
        """
        base_score = self.scorer.score_trade_setup(conditions)
        
        # 1. Bayesian Probability Impact
        # "What is the raw probability of this condition winning?"
        prob, conf, _ = self.bayesian.get_probability(conditions)
        # Shift score by up to +/- 20 points based on probability, scaled by confidence
        bayes_impact = (prob - 0.5) * 40 * conf # (0.2 * 40 * conf) = +8 points etc.
        
        # 2. ML Prediction Impact
        # "What does the AI model predict?"
        ml_prob = self.ml_predictor.predict(conditions) # returns 0.5 if not ready
        ml_impact = (ml_prob - 0.5) * 40 # +/- 20 points max
        
        final_score = base_score + bayes_impact + ml_impact
        return max(0, min(100, int(final_score)))
    
    def should_skip_trade(self, conditions: Dict) -> Tuple[bool, str]:
        """
        Determine if a trade should be skipped.
        
        Returns:
            Tuple of (should_skip: bool, reason: str)
        """
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        # Note: Cooling-off feature disabled by user request
        # if self.cooling_off_until and now < self.cooling_off_until:
        #     remaining = (self.cooling_off_until - now).seconds // 60
        #     self.state['trades_skipped_today'] += 1
        #     return (True, f"Cooling-off period active ({remaining} mins remaining)")
        # else:
        #     self.cooling_off_until = None
        
        # Check confidence score
        score = self.get_confidence_score(conditions)
        recommendation, _ = self.scorer.get_recommendation(score)
        
        if recommendation == "SKIP":
            self.state['trades_skipped_today'] += 1
            explanation = self.scorer.explain_score(conditions)
            return (True, f"Low confidence ({score}/100): {explanation}")
        
        return (False, "")
    
    def get_size_multiplier(self, conditions: Dict) -> float:
        """
        Get position size multiplier based on confidence.
        
        Returns:
            Multiplier (0.5 = half size, 1.0 = normal, 1.25 = larger)
        """
        score = self.get_confidence_score(conditions)
        _, multiplier = self.scorer.get_recommendation(score)
        
        # Also factor in strategy-specific adjustments
        strategy = conditions.get('strategy')
        if strategy and strategy in self.state['patterns']['strategy_adjustments']:
            strat_adj = self.state['patterns']['strategy_adjustments'][strategy].get('risk_adjustment', 1.0)
            multiplier = multiplier * strat_adj
        
        # Bound the multiplier for safety
        # USER REQUEST: Do not reduce quantity below 1 lot. Min multiplier = 1.0
        return max(1.0, min(1.5, multiplier))
    
    def suggest_parameter_adjustments(self, strategy_name: str) -> Dict:
        """
        Get suggested parameter adjustments for a strategy.
        
        Returns:
            Dict with suggested adjustments (risk_pct_multiplier, widen_stops, etc.)
        """
        suggestions = {
            'risk_multiplier': 1.0,
            'widen_stops': False,
            'reason': None
        }
        
        if strategy_name not in self.state['patterns']['strategy_adjustments']:
            return suggestions
        
        # Check Optimizer suggestions first
        opt_sugg = self.optimizer.get_suggestion(strategy_name)
        if opt_sugg:
             suggestions['risk_multiplier'] = opt_sugg.get('risk_mult', 1.0)
             if opt_sugg.get('widen_stops'):
                  suggestions['widen_stops'] = True
                  suggestions['reason'] = "Optimizer: High stop hit rate"
                  return suggestions

        adj = self.state['patterns']['strategy_adjustments'][strategy_name]
        
        # Risk adjustment
        suggestions['risk_multiplier'] = adj.get('risk_adjustment', 1.0)
        
        # Stop-loss adjustment
        if adj.get('stop_hit_ratio', 0) > 0.6:
            suggestions['widen_stops'] = True
            suggestions['reason'] = f"High stop-loss hit rate ({adj['stop_hit_ratio']*100:.0f}%)"
        
        return suggestions
    
    def get_insights(self) -> Dict:
        """
        Get all brain insights for dashboard display.
        
        Returns:
            Dict with all insights and learning progress
        """
        return {
            'confidence_available': bool(self.insights),
            'trade_count': self.state['trade_count'],
            'trades_today': self.state['trades_today'],
            'trades_skipped_today': self.state['trades_skipped_today'],
            'is_cooling_off': self.cooling_off_until is not None,
            'cooling_off_remaining': self._get_cooling_off_remaining(),
            'insights': self.insights,
            'strategy_adjustments': self.state['patterns']['strategy_adjustments'],
            'last_updated': self.state['last_updated']
        }
    
    def _get_cooling_off_remaining(self) -> Optional[int]:
        """Get remaining cooling-off time in minutes."""
        if not self.cooling_off_until:
            return None
        
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        if now >= self.cooling_off_until:
            self.cooling_off_until = None
            return None
        
        return (self.cooling_off_until - now).seconds // 60
    
    def reset_daily_counters(self):
        """Reset daily counters (call at market open)."""
        self.state['trades_today'] = 0
        self.state['trades_skipped_today'] = 0
        self.save_state()
    
    def get_trade_explanation(self, conditions: Dict) -> str:
        """Get human-readable explanation for trade decision."""
        return self.scorer.explain_score(conditions)


# Singleton instance
_brain_instance = None


def get_brain(data_dir: str = None) -> LearningEngine:
    """
    Get or create the brain singleton.
    
    Args:
        data_dir: Optional data directory override
    
    Returns:
        LearningEngine instance
    """
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = LearningEngine(data_dir=data_dir)
    return _brain_instance

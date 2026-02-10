"""
Bayesian Pattern Learner
Uses Bayesian inference to estimate win probabilities for various market conditions.
Learns conditional probabilities: P(Win | Condition)
"""

import logging
from typing import Dict, List, Tuple
from collections import defaultdict
import json

class BayesianPatternLearner:
    """
    Learns the probability of winning trades under specific conditions using Bayesian updates.
    
    The belief is modeled as a Beta distribution (alpha, beta), where:
    - alpha = 1 + wins (prior + evidence)
    - beta = 1 + losses (prior + evidence)
    - P(Win) = alpha / (alpha + beta)
    
    This naturally handles sparse data:
    - 0 wins, 0 losses -> 50% (Weak confidence)
    - 5 wins, 0 losses -> 85% (Stronger confidence)
    - 100 wins, 100 losses -> 50% (Very strong confidence)
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        # Dictionary mapping condition keys to {alpha, beta}
        self.priors = defaultdict(lambda: {'alpha': 1.0, 'beta': 1.0})
        
    def learn(self, conditions: Dict, is_win: bool):
        """
        Update beliefs based on new trade outcome.
        
        Args:
            conditions: Dictionary of discrete conditions (e.g., {'RSI': 'Oversold', 'Regime': 'TREND'})
            is_win: True if trade was profitable
        """
        # Feature extraction
        features = self._extract_features(conditions)
        
        # Update each single feature
        for feature in features:
            if is_win:
                self.priors[feature]['alpha'] += 1.0
            else:
                self.priors[feature]['beta'] += 1.0
                
        # Update combination features (pairs) for higher order interactions
        # We limit to pairs to avoid combinatorial explosion
        sorted_features = sorted(features)
        for i in range(len(sorted_features)):
            for j in range(i+1, len(sorted_features)):
                pair_key = f"{sorted_features[i]}&{sorted_features[j]}"
                if is_win:
                    self.priors[pair_key]['alpha'] += 1.0
                else:
                    self.priors[feature]['beta'] += 1.0
                    
    def get_probability(self, conditions: Dict) -> Tuple[float, float, List[str]]:
        """
        Get the estimated win probability for these conditions.
        
        Returns:
            Tuple: (Probability, Confidence, Reasoning)
            Probability: 0.0 to 1.0
            Confidence: 0.0 to 1.0 (based on sample size)
            Reasoning: List of strings explaining factors
        """
        features = self._extract_features(conditions)
        probabilities = []
        
        # Naive Bayes assumption: combine independent probabilities
        # Actually, let's stick to the strongest EVIDENCE for now to be robust
        # We look for the most specific matching pattern with high confidence
        
        best_prob = 0.5
        max_confidence = 0.0
        influential_factors = []
        
        for feature in features:
            prior = self.priors.get(feature, {'alpha': 1.0, 'beta': 1.0})
            alpha, beta = prior['alpha'], prior['beta']
            total = alpha + beta
            
            prob = alpha / total
            confidence = total / (total + 10) # Simple saturation func, 10 samples ~ 50% conf
            
            if abs(prob - 0.5) > abs(best_prob - 0.5) and total > 5:
                best_prob = prob
                max_confidence = confidence
                influential_factors.append(f"{feature} ({int(prob*100)}% WinRate)")
                
        # Check pairs too
        sorted_features = sorted(features)
        for i in range(len(sorted_features)):
            for j in range(i+1, len(sorted_features)):
                pair_key = f"{sorted_features[i]}&{sorted_features[j]}"
                if pair_key in self.priors:
                    prior = self.priors[pair_key]
                    alpha, beta = prior['alpha'], prior['beta']
                    total = alpha + beta
                    if total > 5:
                         prob = alpha / total
                         if abs(prob - 0.5) > abs(best_prob - 0.5):
                             best_prob = prob
                             max_confidence = total / (total + 10)
                             influential_factors.append(f"{pair_key} ({int(prob*100)}% WR)")

        return best_prob, max_confidence, influential_factors
        
    def _extract_features(self, conditions: Dict) -> List[str]:
        """Convert continuous/complex conditions into discrete feature strings."""
        features = []
        
        # 1. Strategy
        if 'strategy' in conditions:
            features.append(f"Strat={conditions['strategy']}")
            
        # 2. Regime
        if 'regime' in conditions:
            features.append(f"Regime={conditions['regime']}")
            
        # 3. Indicators (Discretized)
        if 'rsi' in conditions and conditions['rsi'] is not None:
            rsi = conditions['rsi']
            if rsi < 30: features.append("RSI=Oversold")
            elif rsi > 70: features.append("RSI=Overbought")
            elif 40 <= rsi <= 60: features.append("RSI=Neutral")
            
        if 'adx' in conditions and conditions['adx'] is not None:
            adx = conditions['adx']
            if adx > 25: features.append("ADX=StrongTrend")
            else: features.append("ADX=WeakTrend")
                
        # 4. Time
        if 'hour' in conditions:
            h = conditions['hour']
            if h < 11: features.append("Time=Morning")
            elif h >= 14: features.append("Time=Closing")
            
        # 5. Volatility
        if 'atr_ratio' in conditions and conditions['atr_ratio'] is not None:
            atr = conditions['atr_ratio']
            if atr > 1.5: features.append("Vol=High")
            elif atr < 0.8: features.append("Vol=Low")
            
        return features
        
    def get_state(self) -> Dict:
        """Serializable state."""
        return {'priors': dict(self.priors)}
        
    def set_state(self, state: Dict):
        """Restore state."""
        if 'priors' in state:
            for k, v in state['priors'].items():
                self.priors[k] = v

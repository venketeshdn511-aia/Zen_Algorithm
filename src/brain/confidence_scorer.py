"""
Confidence Scorer - Scores trade setups based on historical patterns
Provides actionable recommendations: TAKE, SKIP, or REDUCE_SIZE
"""

import logging
from typing import Dict, Optional, Tuple


class ConfidenceScorer:
    """
    Scores each potential trade setup 0-100 based on historical patterns.
    
    Scoring Factors:
    - Time-of-day win rate (25%)
    - Current regime alignment (20%)
    - Recent streak (15%)
    - Indicator alignment (25%)
    - Volatility match (15%)
    """
    
    # Scoring weights
    WEIGHTS = {
        'time_of_day': 25,
        'regime_alignment': 20,
        'streak': 15,
        'indicators': 25,
        'volatility': 15
    }
    
    # Thresholds
    SKIP_THRESHOLD = 30      # Below this = skip trade
    REDUCE_THRESHOLD = 50    # Below this = reduce size
    CONFIDENT_THRESHOLD = 75 # Above this = increase size
    
    def __init__(self, insights: Dict = None, logger: Optional[logging.Logger] = None):
        """
        Initialize scorer with historical insights.
        
        Args:
            insights: Output from TradeAnalyzer.analyze_trades()
        """
        self.logger = logger or logging.getLogger(__name__)
        self.insights = insights or {}
        
    def update_insights(self, insights: Dict):
        """Update the insights used for scoring."""
        self.insights = insights
        
    def score_trade_setup(self, conditions: Dict) -> int:
        """
        Score a potential trade setup.
        
        Args:
            conditions: Dict with keys like:
                - hour: Current hour (0-23)
                - regime: Market regime (TREND, RANGE, REVERSAL)
                - strategy: Strategy name
                - adx: Current ADX value
                - rsi: Current RSI value
                - atr_ratio: Current ATR vs avg ATR ratio
        
        Returns:
            Score 0-100
        """
        if not self.insights:
            # No history = neutral score
            return 50
        
        score = 0
        
        # 1. Time of day score (25 points max)
        score += self._score_time_of_day(conditions.get('hour'))
        
        # 2. Regime alignment score (20 points max)
        score += self._score_regime(conditions.get('regime'), conditions.get('strategy'))
        
        # 3. Streak score (15 points max)
        score += self._score_streak()
        
        # 4. Indicator alignment score (25 points max)
        score += self._score_indicators(conditions)
        
        # 5. Volatility score (15 points max)
        score += self._score_volatility(conditions.get('atr_ratio', 1.0))
        
        return max(0, min(100, int(score)))
    
    def _score_time_of_day(self, hour: Optional[int]) -> float:
        """Score based on historical win rate at this hour."""
        if hour is None:
            return self.WEIGHTS['time_of_day'] * 0.5  # Neutral
        
        time_patterns = self.insights.get('time_patterns', {})
        best_hour = time_patterns.get('best_hour')
        worst_hour = time_patterns.get('worst_hour')
        best_rate = time_patterns.get('best_hour_win_rate', 50)
        worst_rate = time_patterns.get('worst_hour_win_rate', 50)
        
        if hour == best_hour and best_rate > 60:
            return self.WEIGHTS['time_of_day']  # Full points
        elif hour == worst_hour and worst_rate < 40:
            return 0  # No points
        
        # Check hourly stats
        hourly_stats = time_patterns.get('hourly_stats', {})
        hour_key = f"{hour:02d}:00-{hour+1:02d}:00"
        
        if hour_key in hourly_stats:
            win_rate = hourly_stats[hour_key].get('win_rate', 50)
            # Scale: 40% = 0 points, 50% = half, 60%+ = full
            scaled = max(0, (win_rate - 40) / 20) * self.WEIGHTS['time_of_day']
            return min(self.WEIGHTS['time_of_day'], scaled)
        
        return self.WEIGHTS['time_of_day'] * 0.5  # Neutral if no data
    
    def _score_regime(self, regime: Optional[str], strategy: Optional[str]) -> float:
        """Score based on how well strategy performs in this regime."""
        if not regime:
            return self.WEIGHTS['regime_alignment'] * 0.5
        
        regime_perf = self.insights.get('regime_performance', {})
        strategy_perf = self.insights.get('strategy_performance', {})
        
        # Check regime performance
        if regime in regime_perf:
            regime_win_rate = regime_perf[regime].get('win_rate', 50)
            regime_score = max(0, (regime_win_rate - 40) / 20) * (self.WEIGHTS['regime_alignment'] * 0.6)
        else:
            regime_score = self.WEIGHTS['regime_alignment'] * 0.3
        
        # Check strategy performance
        if strategy and strategy in strategy_perf:
            strat_win_rate = strategy_perf[strategy].get('win_rate', 50)
            strat_score = max(0, (strat_win_rate - 40) / 20) * (self.WEIGHTS['regime_alignment'] * 0.4)
        else:
            strat_score = self.WEIGHTS['regime_alignment'] * 0.2
        
        return min(self.WEIGHTS['regime_alignment'], regime_score + strat_score)
    
    def _score_streak(self) -> float:
        """Score based on current winning/losing streak."""
        streak_analysis = self.insights.get('streak_analysis', {})
        current_streak = streak_analysis.get('current_streak', 0)
        is_losing_streak = streak_analysis.get('is_losing_streak', False)
        consecutive_losses = streak_analysis.get('consecutive_losses', 0)
        
        if is_losing_streak or consecutive_losses >= 3:
            # Heavy penalty for losing streaks
            return 0
        elif consecutive_losses == 2:
            return self.WEIGHTS['streak'] * 0.3
        elif current_streak >= 3:
            # Bonus for winning streaks (but not too much - regression to mean)
            return self.WEIGHTS['streak'] * 0.8
        elif current_streak >= 1:
            return self.WEIGHTS['streak'] * 0.7
        elif current_streak <= -1:
            return self.WEIGHTS['streak'] * 0.4
        
        return self.WEIGHTS['streak'] * 0.5  # Neutral
    
    def _score_indicators(self, conditions: Dict) -> float:
        """Score based on indicator values alignment with historical winners."""
        score = 0
        max_score = self.WEIGHTS['indicators']
        
        adx = conditions.get('adx')
        rsi = conditions.get('rsi')
        regime = conditions.get('regime', '')
        
        # ADX alignment
        if adx is not None:
            if regime == 'TREND' and adx > 25:
                score += max_score * 0.4  # Strong trend = good for trend strategies
            elif regime == 'RANGE' and adx < 20:
                score += max_score * 0.4  # Weak trend = good for range strategies
            elif adx >= 20 and adx <= 30:
                score += max_score * 0.3  # Moderate = neutral
            else:
                score += max_score * 0.2
        else:
            score += max_score * 0.2  # No data = partial credit
        
        # RSI alignment
        if rsi is not None:
            if 40 <= rsi <= 60:
                score += max_score * 0.3  # Neutral RSI = balanced
            elif (30 <= rsi < 40) or (60 < rsi <= 70):
                score += max_score * 0.25  # Slightly overbought/oversold
            else:
                score += max_score * 0.1  # Extreme = risky
        else:
            score += max_score * 0.15
        
        # Volume/confirmation (placeholder - can be enhanced)
        score += max_score * 0.15  # Base credit
        
        return min(max_score, score)
    
    def _score_volatility(self, atr_ratio: float) -> float:
        """Score based on current volatility vs historical average."""
        max_score = self.WEIGHTS['volatility']
        
        if atr_ratio is None:
            return max_score * 0.5
        
        # Ideal: slightly elevated but not extreme (1.0 to 1.5x normal)
        if 0.8 <= atr_ratio <= 1.3:
            return max_score  # Normal volatility = full points
        elif 1.3 < atr_ratio <= 1.8:
            return max_score * 0.7  # Elevated = moderate
        elif atr_ratio > 1.8:
            return max_score * 0.3  # Too volatile = risky
        elif atr_ratio < 0.8:
            return max_score * 0.6  # Low volatility = might not move
        
        return max_score * 0.5
    
    def get_recommendation(self, score: int) -> Tuple[str, float]:
        """
        Get recommendation based on score.
        
        Returns:
            Tuple of (recommendation, size_multiplier)
            - "SKIP": Don't take the trade
            - "REDUCE_SIZE": Take with smaller position
            - "TAKE": Normal position
            - "CONFIDENT": Slightly larger position
        """
        if score < self.SKIP_THRESHOLD:
            return ("SKIP", 0.0)
        elif score < self.REDUCE_THRESHOLD:
            return ("REDUCE_SIZE", 0.5)
        elif score < self.CONFIDENT_THRESHOLD:
            return ("TAKE", 1.0)
        else:
            return ("CONFIDENT", 1.25)
    
    def explain_score(self, conditions: Dict) -> str:
        """
        Get human-readable explanation of the score.
        
        Returns explanation string for Telegram/dashboard.
        """
        score = self.score_trade_setup(conditions)
        recommendation, multiplier = self.get_recommendation(score)
        
        explanations = []
        
        # Time explanation
        hour = conditions.get('hour')
        if hour is not None:
            time_patterns = self.insights.get('time_patterns', {})
            if hour == time_patterns.get('best_hour'):
                explanations.append(f"✅ Peak hour ({hour}:00)")
            elif hour == time_patterns.get('worst_hour'):
                explanations.append(f"⚠️ Weak hour ({hour}:00)")
        
        # Streak explanation
        streak = self.insights.get('streak_analysis', {})
        if streak.get('is_losing_streak'):
            explanations.append(f"🔴 Losing streak ({streak.get('consecutive_losses', 0)} losses)")
        elif streak.get('current_streak', 0) >= 3:
            explanations.append(f"🟢 Winning streak")
        
        # Regime explanation
        regime = conditions.get('regime')
        regime_perf = self.insights.get('regime_performance', {})
        if regime and regime in regime_perf:
            wr = regime_perf[regime].get('win_rate', 0)
            if wr >= 60:
                explanations.append(f"✅ Strong in {regime} ({wr}% WR)")
            elif wr < 45:
                explanations.append(f"⚠️ Weak in {regime} ({wr}% WR)")
        
        if not explanations:
            explanations.append("Neutral conditions")
        
        summary = f"Score: {score}/100 → {recommendation}"
        if multiplier != 1.0 and multiplier > 0:
            summary += f" (Size: {int(multiplier*100)}%)"
        
        return f"{summary}\n" + " | ".join(explanations)

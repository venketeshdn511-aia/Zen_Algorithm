"""
Trade Analyzer - Extracts patterns from historical trades
Analyzes time patterns, regime performance, exit reasons, and indicator correlations
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class TradeAnalyzer:
    """
    Analyzes historical trades to extract actionable patterns.
    
    Key Analysis:
    - Time-of-day win rates
    - Market regime performance
    - Exit reason distribution
    - Indicator value correlations
    - Losing streak detection
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.trade_cache = []
        
    def analyze_trades(self, trades: List[Dict]) -> Dict:
        """
        Run all analyses on trade history.
        
        Returns comprehensive insights dictionary.
        """
        if not trades:
            return self._empty_insights()
            
        self.trade_cache = trades
        
        return {
            'time_patterns': self.analyze_time_patterns(trades),
            'regime_performance': self.analyze_regime_performance(trades),
            'exit_patterns': self.analyze_exit_patterns(trades),
            'strategy_performance': self.analyze_strategy_performance(trades),
            'streak_analysis': self.analyze_streaks(trades),
            'summary': self._compute_summary(trades)
        }
    
    def analyze_time_patterns(self, trades: List[Dict]) -> Dict:
        """
        Analyze win rates by hour, day of week, session, and expiry proximity.
        """
        hourly_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
        weekday_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
        session_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
        
        for trade in trades:
            try:
                # Parse entry time
                entry_time = trade.get('entry_time', '')
                if isinstance(entry_time, str):
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%d %H:%M:%S']:
                        try:
                            dt = datetime.strptime(entry_time.split('+')[0], fmt)
                            break
                        except ValueError: continue
                    else: continue
                elif isinstance(entry_time, datetime):
                    dt = entry_time
                else: continue
                    
                pnl = float(trade.get('pnl', 0))
                is_win = pnl > 0
                
                # Hourly Stats
                hour = dt.hour
                hourly_stats[hour]['pnl'] += pnl
                hourly_stats[hour]['wins'] += 1 if is_win else 0
                hourly_stats[hour]['losses'] += 1 if not is_win else 0
                
                # Weekday Stats (0=Mon, 6=Sun)
                weekday = dt.weekday()
                weekday_stats[weekday]['pnl'] += pnl
                weekday_stats[weekday]['wins'] += 1 if is_win else 0
                weekday_stats[weekday]['losses'] += 1 if not is_win else 0
                
                # Session Stats
                # Morning: 9:15 - 11:30
                # Mid: 11:30 - 13:30
                # Close: 13:30 - 15:30
                time_val = dt.hour * 100 + dt.minute
                if 915 <= time_val < 1130: session = "Morning"
                elif 1130 <= time_val < 1330: session = "Midday"
                elif 1330 <= time_val < 1530: session = "Closing"
                else: session = "Other"
                
                session_stats[session]['pnl'] += pnl
                session_stats[session]['wins'] += 1 if is_win else 0
                session_stats[session]['losses'] += 1 if not is_win else 0
                    
            except Exception as e:
                self.logger.debug(f"Error parsing trade time: {e}")
                continue
        
        # Calculate Hourly Results
        hourly_res = {}
        best_hour, worst_hour = None, None
        best_rate, worst_rate = 0, 100
        
        for hour, stats in hourly_stats.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                win_rate = (stats['wins'] / total) * 100
                hourly_res[f"{hour:02d}:00-{hour+1:02d}:00"] = {
                    'wins': stats['wins'], 'losses': stats['losses'],
                    'win_rate': round(win_rate, 1), 'total_pnl': round(stats['pnl'], 2)
                }
                if total >= 3:
                    if win_rate > best_rate: best_rate, best_hour = win_rate, hour
                    if win_rate < worst_rate: worst_rate, worst_hour = win_rate, hour
        
        # Calculate Weekday Results
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_res = {}
        for w, stats in weekday_stats.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                weekday_res[days[w]] = {
                    'wins': stats['wins'], 'losses': stats['losses'],
                    'win_rate': round((stats['wins']/total)*100, 1),
                    'total_pnl': round(stats['pnl'], 2)
                }
                
        # Calculate Session Results
        session_res = {}
        for s, stats in session_stats.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                session_res[s] = {
                    'wins': stats['wins'], 'losses': stats['losses'],
                    'win_rate': round((stats['wins']/total)*100, 1),
                    'total_pnl': round(stats['pnl'], 2)
                }

        return {
            'hourly_stats': hourly_res,
            'weekday_stats': weekday_res,
            'session_stats': session_res,
            'best_hour': best_hour,
            'best_hour_win_rate': best_rate,
            'worst_hour': worst_hour,
            'worst_hour_win_rate': worst_rate
        }
    
    def analyze_regime_performance(self, trades: List[Dict]) -> Dict:
        """
        Analyze performance by market regime (TREND, RANGE, REVERSAL).
        """
        regime_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
        
        for trade in trades:
            regime = trade.get('regime', 'UNKNOWN')
            pnl = float(trade.get('pnl', 0))
            
            regime_stats[regime]['pnl'] += pnl
            if pnl > 0:
                regime_stats[regime]['wins'] += 1
            else:
                regime_stats[regime]['losses'] += 1
        
        result = {}
        for regime, stats in regime_stats.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                result[regime] = {
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'win_rate': round((stats['wins'] / total) * 100, 1),
                    'total_pnl': round(stats['pnl'], 2),
                    'avg_pnl': round(stats['pnl'] / total, 2)
                }
        
        return result
    
    def analyze_exit_patterns(self, trades: List[Dict]) -> Dict:
        """
        Analyze exit reasons distribution.
        Identifies if we're hitting stops too often vs targets.
        """
        exit_stats = defaultdict(lambda: {'count': 0, 'pnl': 0})
        
        for trade in trades:
            reason = trade.get('reason', trade.get('exit_reason', 'unknown')).lower()
            pnl = float(trade.get('pnl', 0))
            
            # Normalize exit reasons
            if 'stop' in reason or 'sl' in reason:
                reason = 'stop_loss'
            elif 'target' in reason or 'tp' in reason or 'profit' in reason:
                reason = 'target_hit'
            elif 'time' in reason or 'sq' in reason or 'square' in reason:
                reason = 'time_exit'
            elif 'trail' in reason:
                reason = 'trailing_stop'
            else:
                reason = 'other'
            
            exit_stats[reason]['count'] += 1
            exit_stats[reason]['pnl'] += pnl
        
        total_trades = sum(s['count'] for s in exit_stats.values())
        
        result = {}
        for reason, stats in exit_stats.items():
            result[reason] = {
                'count': stats['count'],
                'percentage': round((stats['count'] / total_trades * 100) if total_trades > 0 else 0, 1),
                'total_pnl': round(stats['pnl'], 2),
                'avg_pnl': round(stats['pnl'] / stats['count'], 2) if stats['count'] > 0 else 0
            }
        
        # Calculate stop loss ratio (how often we hit stops)
        sl_count = exit_stats.get('stop_loss', {}).get('count', 0)
        target_count = exit_stats.get('target_hit', {}).get('count', 0)
        
        return {
            'breakdown': result,
            'stop_loss_ratio': round((sl_count / total_trades * 100) if total_trades > 0 else 0, 1),
            'target_hit_ratio': round((target_count / total_trades * 100) if total_trades > 0 else 0, 1),
            'suggestion': self._get_exit_suggestion(sl_count, target_count, total_trades)
        }
    
    def analyze_strategy_performance(self, trades: List[Dict]) -> Dict:
        """
        Analyze performance by strategy name.
        """
        strategy_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0, 'trades': []})
        
        for trade in trades:
            strategy = trade.get('strategy', 'Unknown')
            pnl = float(trade.get('pnl', 0))
            
            strategy_stats[strategy]['pnl'] += pnl
            strategy_stats[strategy]['trades'].append(pnl)
            if pnl > 0:
                strategy_stats[strategy]['wins'] += 1
            else:
                strategy_stats[strategy]['losses'] += 1
        
        result = {}
        for strategy, stats in strategy_stats.items():
            total = stats['wins'] + stats['losses']
            if total > 0:
                # Calculate max drawdown for strategy
                trades_pnl = stats['trades']
                cumulative = 0
                peak = 0
                max_dd = 0
                for p in trades_pnl:
                    cumulative += p
                    if cumulative > peak:
                        peak = cumulative
                    dd = peak - cumulative
                    if dd > max_dd:
                        max_dd = dd
                
                result[strategy] = {
                    'wins': stats['wins'],
                    'losses': stats['losses'],
                    'total_trades': total,
                    'win_rate': round((stats['wins'] / total) * 100, 1),
                    'total_pnl': round(stats['pnl'], 2),
                    'avg_pnl': round(stats['pnl'] / total, 2),
                    'max_drawdown': round(max_dd, 2)
                }
        
        return result
    
    def analyze_streaks(self, trades: List[Dict]) -> Dict:
        """
        Analyze winning/losing streaks.
        Detects patterns in consecutive outcomes.
        """
        if not trades:
            return {'current_streak': 0, 'max_win_streak': 0, 'max_loss_streak': 0}
        
        # Sort by exit time
        sorted_trades = sorted(trades, key=lambda x: x.get('exit_time', ''))
        
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        win_streak = 0
        loss_streak = 0
        
        for trade in sorted_trades:
            pnl = float(trade.get('pnl', 0))
            
            if pnl > 0:
                win_streak += 1
                loss_streak = 0
                if win_streak > max_win_streak:
                    max_win_streak = win_streak
            else:
                loss_streak += 1
                win_streak = 0
                if loss_streak > max_loss_streak:
                    max_loss_streak = loss_streak
        
        # Current streak (from most recent trades)
        if sorted_trades:
            last_pnl = float(sorted_trades[-1].get('pnl', 0))
            current_streak = win_streak if last_pnl > 0 else -loss_streak
        
        return {
            'current_streak': current_streak,
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak,
            'is_losing_streak': loss_streak >= 3,
            'consecutive_losses': loss_streak
        }
    
    def _compute_summary(self, trades: List[Dict]) -> Dict:
        """Compute overall summary statistics."""
        total = len(trades)
        if total == 0:
            return self._empty_summary()
        
        wins = sum(1 for t in trades if float(t.get('pnl', 0)) > 0)
        total_pnl = sum(float(t.get('pnl', 0)) for t in trades)
        
        profits = [float(t.get('pnl', 0)) for t in trades if float(t.get('pnl', 0)) > 0]
        losses = [abs(float(t.get('pnl', 0))) for t in trades if float(t.get('pnl', 0)) < 0]
        
        avg_win = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        profit_factor = (sum(profits) / sum(losses)) if losses and sum(losses) > 0 else 0
        
        return {
            'total_trades': total,
            'wins': wins,
            'losses': total - wins,
            'win_rate': round((wins / total) * 100, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(total_pnl / total, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy': round((avg_win * wins/total) - (avg_loss * (total-wins)/total), 2) if total > 0 else 0
        }
    
    def _get_exit_suggestion(self, sl_count: int, target_count: int, total: int) -> str:
        """Generate suggestion based on exit pattern analysis."""
        if total < 5:
            return "Not enough data for suggestions"
        
        sl_ratio = sl_count / total if total > 0 else 0
        
        if sl_ratio > 0.6:
            return "High stop-loss rate. Consider widening stops or improving entry timing."
        elif sl_ratio > 0.45:
            return "Moderate stop-loss rate. Fine-tune entry criteria."
        elif target_count / total > 0.5:
            return "Strong target hit rate. Consider increasing position sizes."
        else:
            return "Balanced exit distribution. Monitor for changes."
    
    def _empty_insights(self) -> Dict:
        """Return empty insights structure."""
        return {
            'time_patterns': {'hourly_stats': {}, 'best_hour': None, 'worst_hour': None},
            'regime_performance': {},
            'exit_patterns': {'breakdown': {}, 'stop_loss_ratio': 0, 'target_hit_ratio': 0},
            'strategy_performance': {},
            'streak_analysis': {'current_streak': 0, 'max_win_streak': 0, 'max_loss_streak': 0},
            'summary': self._empty_summary()
        }
    
    def _empty_summary(self) -> Dict:
        """Return empty summary structure."""
        return {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_pnl': 0,
            'profit_factor': 0
        }

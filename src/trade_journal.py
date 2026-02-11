"""
Trade Journal - JSON-based persistent storage for trade data.
Saves trades, positions, and stats to JSON files on disk.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path


class TradeJournal:
    """
    Persistent trade journal using JSON files.
    
    Files:
    - trades.json: All historical trades
    - state.json: Current bot state (positions, capital)
    - stats.json: Aggregated statistics
    """
    
    def __init__(self, data_dir: str = None, logger=None):
        """
        Initialize Trade Journal.
        
        Args:
            data_dir: Directory to store JSON files (default: ./data)
            logger: Optional logger
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Set data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent / "data"
        
        # Create directory if needed
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.trades_file = self.data_dir / "trades.json"
        self.state_file = self.data_dir / "state.json"
        self.stats_file = self.data_dir / "stats.json"
        
        # Load existing data
        self.trades = self._load_json(self.trades_file, [])
        self.state = self._load_json(self.state_file, {})
        self.stats = self._load_json(self.stats_file, self._default_stats())
        
        self.logger.info(f" TradeJournal initialized: {self.data_dir}")
        self.logger.info(f"   Loaded {len(self.trades)} historical trades")
    
    def _default_stats(self) -> Dict:
        """Default stats structure."""
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "peak_capital": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "last_updated": None
        }
    
    def _load_json(self, filepath: Path, default) -> any:
        """Load JSON file or return default."""
        try:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load {filepath}: {e}")
        return default
    
    def _save_json(self, filepath: Path, data) -> bool:
        """Save data to JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save {filepath}: {e}")
            return False
    
    # === Trade Logging ===
    
    def log_trade(
        self,
        symbol: str,
        side: str,
        strike: int,
        option_type: str,
        qty: int,
        entry_price: float,
        exit_price: float,
        pnl: float,
        entry_time: datetime,
        exit_time: datetime,
        exit_reason: str,
        oi_analysis: Dict = None
    ) -> bool:
        """
        Log a completed trade.
        
        Args:
            All trade details
        
        Returns:
            True if saved successfully
        """
        trade = {
            "id": len(self.trades) + 1,
            "symbol": symbol,
            "side": side,
            "strike": strike,
            "option_type": option_type,
            "qty": qty,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0,
            "entry_time": entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time,
            "exit_time": exit_time.isoformat() if isinstance(exit_time, datetime) else exit_time,
            "exit_reason": exit_reason,
            "oi_analysis": oi_analysis or {},
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        
        self.trades.append(trade)
        
        # Update stats
        self._update_stats(pnl)
        
        # Save to disk
        self._save_json(self.trades_file, self.trades)
        self._save_json(self.stats_file, self.stats)
        
        self.logger.info(f" Trade logged: {symbol} {strike}{option_type} | PnL: {pnl:+.2f}")
        
        return True
    
    def _update_stats(self, pnl: float):
        """Update running statistics."""
        self.stats["total_trades"] += 1
        self.stats["total_pnl"] += pnl
        
        if pnl > 0:
            self.stats["winning_trades"] += 1
        else:
            self.stats["losing_trades"] += 1
        
        # Best/worst
        if pnl > self.stats["best_trade"]:
            self.stats["best_trade"] = pnl
        if pnl < self.stats["worst_trade"]:
            self.stats["worst_trade"] = pnl
        
        # Win rate
        if self.stats["total_trades"] > 0:
            self.stats["win_rate"] = (self.stats["winning_trades"] / self.stats["total_trades"]) * 100
            self.stats["avg_pnl"] = self.stats["total_pnl"] / self.stats["total_trades"]
        
        # Profit factor
        gross_profit = sum(t["pnl"] for t in self.trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in self.trades if t["pnl"] < 0))
        if gross_loss > 0:
            self.stats["profit_factor"] = gross_profit / gross_loss
        
        self.stats["last_updated"] = datetime.now().isoformat()
    
    # === State Management ===
    
    def save_state(self, bot_state: Dict, positions: Dict = None):
        """Save current bot state for recovery."""
        self.state = {
            "capital": bot_state.get("capital", 0),
            "pnl_today": bot_state.get("pnl_today", 0),
            "trades_today": bot_state.get("trades_today", 0),
            "positions": positions or {},
            "last_saved": datetime.now().isoformat()
        }
        self._save_json(self.state_file, self.state)
    
    def load_state(self) -> Dict:
        """Load saved state for recovery after restart."""
        return self._load_json(self.state_file, {})
    
    # === Reports ===
    
    def get_daily_report(self, date: str = None) -> Dict:
        """Get report for a specific day."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        day_trades = [t for t in self.trades if t["date"] == date]
        
        if not day_trades:
            return {"date": date, "trades": 0, "pnl": 0, "message": "No trades"}
        
        pnl = sum(t["pnl"] for t in day_trades)
        wins = len([t for t in day_trades if t["pnl"] > 0])
        
        return {
            "date": date,
            "trades": len(day_trades),
            "pnl": pnl,
            "wins": wins,
            "losses": len(day_trades) - wins,
            "win_rate": (wins / len(day_trades) * 100) if day_trades else 0,
            "best_trade": max(t["pnl"] for t in day_trades),
            "worst_trade": min(t["pnl"] for t in day_trades)
        }
    
    def get_weekly_report(self) -> Dict:
        """Get report for current week."""
        week_start = datetime.now() - timedelta(days=datetime.now().weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")
        
        week_trades = [t for t in self.trades if t["date"] >= week_start_str]
        
        if not week_trades:
            return {"period": "This Week", "trades": 0, "pnl": 0}
        
        pnl = sum(t["pnl"] for t in week_trades)
        wins = len([t for t in week_trades if t["pnl"] > 0])
        
        return {
            "period": f"Week of {week_start_str}",
            "trades": len(week_trades),
            "pnl": pnl,
            "wins": wins,
            "losses": len(week_trades) - wins,
            "win_rate": (wins / len(week_trades) * 100) if week_trades else 0,
            "avg_pnl": pnl / len(week_trades) if week_trades else 0
        }
    
    def get_monthly_report(self) -> Dict:
        """Get report for current month."""
        month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        
        month_trades = [t for t in self.trades if t["date"] >= month_start]
        
        if not month_trades:
            return {"period": "This Month", "trades": 0, "pnl": 0}
        
        pnl = sum(t["pnl"] for t in month_trades)
        wins = len([t for t in month_trades if t["pnl"] > 0])
        
        # Calculate max drawdown
        running_pnl = 0
        peak = 0
        max_dd = 0
        for t in sorted(month_trades, key=lambda x: x["exit_time"]):
            running_pnl += t["pnl"]
            if running_pnl > peak:
                peak = running_pnl
            dd = peak - running_pnl
            if dd > max_dd:
                max_dd = dd
        
        return {
            "period": datetime.now().strftime("%B %Y"),
            "trades": len(month_trades),
            "pnl": pnl,
            "wins": wins,
            "losses": len(month_trades) - wins,
            "win_rate": (wins / len(month_trades) * 100) if month_trades else 0,
            "max_drawdown": max_dd,
            "avg_pnl": pnl / len(month_trades) if month_trades else 0,
            "profit_factor": self.stats.get("profit_factor", 0)
        }
    
    def get_all_time_stats(self) -> Dict:
        """Get all-time statistics."""
        return {
            **self.stats,
            "total_trades": len(self.trades)
        }
    
    def format_report(self, report: Dict, title: str = "Report") -> str:
        """Format report for display/Telegram."""
        lines = [f" *{title}*", "" * 20]
        
        for key, value in report.items():
            if key in ["period", "date", "message"]:
                continue
            
            # Format key
            label = key.replace("_", " ").title()
            
            # Format value
            if "pnl" in key.lower() or "trade" in key.lower() and isinstance(value, (int, float)):
                formatted = f"{value:+,.2f}" if "pnl" in key.lower() else str(value)
            elif "rate" in key.lower() or "factor" in key.lower():
                formatted = f"{value:.1f}%" if "rate" in key.lower() else f"{value:.2f}"
            else:
                formatted = str(value)
            
            lines.append(f"{label}: {formatted}")
        
        return "\n".join(lines)

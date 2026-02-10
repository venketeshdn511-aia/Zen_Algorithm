import threading
from datetime import datetime
from collections import defaultdict
import pandas as pd

class BarAggregator:
    """
    Aggregates real-time ticks into OHLC bars (1m, 5m intervals)
    Generic implementation extracted from FyersWSHandler.
    """
    def __init__(self, intervals=[1, 5]):
        """
        Args:
            intervals: List of minute intervals to aggregate (e.g., [1, 5])
        """
        self.intervals = intervals  # Minutes
        self.current_bars = {}  # {interval: {symbol: {'open':, 'high':, 'low':, 'close':, 'volume':, 'start_time':}}}
        self.completed_bars = {}  # {interval: {symbol: [list of completed bars]}}
        self.lock = threading.Lock()
        
        for interval in intervals:
            self.current_bars[interval] = {}
            self.completed_bars[interval] = defaultdict(list)
    
    def _get_bar_start_time(self, timestamp, interval_minutes):
        """Get the start time of the current bar interval"""
        dt = datetime.fromtimestamp(timestamp) if isinstance(timestamp, (int, float)) else timestamp
        # Round down to nearest interval
        minute = (dt.minute // interval_minutes) * interval_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)
    
    def process_tick(self, symbol, ltp, volume, timestamp):
        """
        Process incoming tick and update bars
        
        Args:
            symbol: Trading symbol
            ltp: Last traded price
            volume: Tick volume
            timestamp: Unix timestamp or datetime
        
        Returns:
            Dict of completed bars by interval if any bar closed, else None
        """
        completed = {}
        
        with self.lock:
            for interval in self.intervals:
                bar_start = self._get_bar_start_time(timestamp, interval)
                bar_key = bar_start.isoformat()
                
                if symbol not in self.current_bars[interval]:
                    # First tick for this symbol/interval
                    self.current_bars[interval][symbol] = {
                        'datetime': bar_start,
                        'open': ltp,
                        'high': ltp,
                        'low': ltp,
                        'close': ltp,
                        'volume': volume or 0,
                        'bar_key': bar_key
                    }
                else:
                    current = self.current_bars[interval][symbol]
                    
                    # Check if we're in a new bar
                    if bar_key != current['bar_key']:
                        # Complete the old bar
                        self.completed_bars[interval][symbol].append(current.copy())
                        
                        # Keep only last 1500 bars per symbol (approx 1 day for 1m)
                        if len(self.completed_bars[interval][symbol]) > 1500:
                            self.completed_bars[interval][symbol] = self.completed_bars[interval][symbol][-1500:]
                        
                        # Start new bar
                        self.current_bars[interval][symbol] = {
                            'datetime': bar_start,
                            'open': ltp,
                            'high': ltp,
                            'low': ltp,
                            'close': ltp,
                            'volume': volume or 0,
                            'bar_key': bar_key
                        }
                        
                        completed[interval] = current.copy()
                    else:
                        # Update current bar
                        current['high'] = max(current['high'], ltp)
                        current['low'] = min(current['low'], ltp)
                        current['close'] = ltp
                        current['volume'] += volume or 0
        
        return completed if completed else None
    
    def get_bars_df(self, symbol, interval, limit=100):
        """
        Get completed bars as DataFrame
        
        Args:
            symbol: Trading symbol
            interval: Bar interval in minutes
            limit: Number of bars to return
        
        Returns:
            DataFrame with OHLC data
        """
        with self.lock:
            bars = self.completed_bars.get(interval, {}).get(symbol, [])
            
            if not bars:
                # Return empty DF with correct columns
                return pd.DataFrame(columns=['open','high','low','close','volume'])
            
            # Include current bar if it exists (for live strategy?)
            # Usually strategies want COMPLETED bars.
            # But indicators might want current.
            # Include current bar if it exists (for live strategy?)
            # Usually strategies want COMPLETED bars.
            # But indicators might want current.
            # Let's include current for now as per original implementation.
            current = self.current_bars.get(interval, {}).get(symbol)
            all_bars = bars[-limit:] + ([current] if current else [])
            
            df = pd.DataFrame(all_bars)
            if 'datetime' in df.columns:
                df.set_index('datetime', inplace=True)
                df.drop(columns=['bar_key'], errors='ignore', inplace=True)
            
            return df.tail(limit)

"""
Fyers WebSocket Handler for Real-Time Market Data
Uses fyers_apiv3.FyersWebsocket for live ticks
"""
import os
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from queue import Queue

try:
    # Try Fyers API v3 (Standard path)
    from fyers_apiv3.FyersWebsocket import data_ws
    print("✅ FyersWebsocket imported successfully")
except ImportError as e1:
    try:
        # Try Fyers API v3 (Alternative path)
        from fyers_apiv3.FyersDataSocket import data_ws
        print("✅ FyersDataSocket imported successfully")
    except ImportError as e2:
        data_ws = None
        print(f"⚠️ WebSocket import failed:")
        print(f"   - FyersWebsocket: {e1}")
        print(f"   - FyersDataSocket: {e2}")
        print("   Bot will use REST polling instead (non-critical).")


class BarAggregator:
    """
    Aggregates real-time ticks into OHLC bars (1m, 5m intervals)
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
                        
                        # Keep only last 500 bars per symbol
                        if len(self.completed_bars[interval][symbol]) > 500:
                            self.completed_bars[interval][symbol] = self.completed_bars[interval][symbol][-500:]
                        
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
                return pd.DataFrame()
            
            # Include current bar if it exists
            current = self.current_bars.get(interval, {}).get(symbol)
            all_bars = bars[-limit:] + ([current] if current else [])
            
            df = pd.DataFrame(all_bars)
            if 'datetime' in df.columns:
                df.set_index('datetime', inplace=True)
                df.drop(columns=['bar_key'], errors='ignore', inplace=True)
            
            return df.tail(limit)

    def prime_history(self, symbol, df, interval):
        """Populate completed bars from historical DataFrame"""
        with self.lock:
            # Convert DF to list of dicts
            bar_list = []
            for dt, row in df.iterrows():
                # Ensure we have required fields
                if not all(k in row for k in ['open', 'high', 'low', 'close']):
                     continue
                     
                bar = {
                    'datetime': dt,
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row.get('volume', 0)),
                    'bar_key': dt.isoformat()
                }
                bar_list.append(bar)
            
            # Keep last 500
            if len(bar_list) > 500:
                bar_list = bar_list[-500:]
            
            # Initialize dict for symbol if needed
            if symbol not in self.completed_bars[interval]:
                 self.completed_bars[interval][symbol] = []
                 
            self.completed_bars[interval][symbol] = bar_list
            print(f"✅ WebSocket Memory Primed: {len(bar_list)} bars for {symbol} ({interval}m)")


class FyersWebSocketHandler:
    """
    Manages Fyers WebSocket connection for real-time data
    """
    def __init__(self, access_token=None, symbols=None, on_bar_complete=None, on_tick=None, logger=None):
        """
        Args:
            access_token: Fyers access token (format: "appid:token")
            symbols: List of symbols to subscribe (e.g., ["NSE:NIFTY50-INDEX"])
            on_bar_complete: Callback function when a bar completes
            on_tick: Callback function for every tick (for limit orders)
            logger: Logger instance
        """
        self.access_token = access_token or os.getenv('FYERS_ACCESS_TOKEN')
        self.app_id = os.getenv('FYERS_APP_ID', '')
        self.symbols = symbols or ["NSE:NIFTY50-INDEX"]
        self.on_bar_complete = on_bar_complete
        self.on_tick = on_tick
        self.logger = logger
        
        self.ws = None
        self.connected = False
        self.running = False
        self.thread = None
        
        # Bar aggregator for 1m and 5m bars
        self.aggregator = BarAggregator(intervals=[1, 5])
        
        # Latest prices cache
        self.latest_prices = {}
        self.last_update = None
    
    def _log(self, message, level='info'):
        """Log with prefix"""
        msg = f"[WebSocket] {message}"
        if self.logger:
            getattr(self.logger, level)(msg)
        else:
            print(msg)
    
    def _on_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            if isinstance(message, dict):
                # Parse tick data
                # Fyers format: {'symbol': 'NSE:NIFTY50-INDEX', 'ltp': 21450.5, 'vol_traded_today': 1000, ...}
                symbol = message.get('symbol', '')
                ltp = message.get('ltp') or message.get('last_price') or message.get('lp')
                volume = message.get('vol_traded_today', 0)
                timestamp = message.get('timestamp') or time.time()
                
                if ltp:
                    ltp = float(ltp)
                    self.latest_prices[symbol] = ltp
                    self.last_update = datetime.now()
                    
                    # [FEATURE] Limit Order Simulation: Trigger callback instantly
                    if self.on_tick:
                        # process in try-except to not block WS thread
                        try:
                            self.on_tick(symbol, ltp)
                        except Exception as e:
                            self._log(f"on_tick callback error: {e}", 'error')
                    
                    # Process tick into bars
                    completed = self.aggregator.process_tick(symbol, ltp, volume, timestamp)
                    
                    if completed and self.on_bar_complete:
                        # Notify callback with completed bar info
                        for interval, bar in completed.items():
                            self.on_bar_complete(symbol, interval, bar)
            
            elif isinstance(message, list):
                # Batch of ticks
                for tick in message:
                    self._on_message(tick)
                    
        except Exception as e:
            self._log(f"Error processing message: {e}", 'error')
    
    def _on_error(self, error):
        """Handle WebSocket errors"""
        self._log(f"WebSocket error: {error}", 'error')
    
    def _on_close(self, code, reason):
        """Handle WebSocket close"""
        self._log(f"WebSocket closed: {code} - {reason}", 'warning')
        self.connected = False
        
        # Auto-reconnect if still running
        if self.running:
            self._log("Attempting reconnect in 5 seconds...", 'info')
            time.sleep(5)
            self._connect()
    
    def _on_open(self):
        """Handle WebSocket open - subscribe to symbols"""
        self._log("WebSocket connected!", 'info')
        self.connected = True
        
        # Subscribe to symbols
        try:
            if self.ws:
                self.ws.subscribe(
                    symbols=self.symbols,
                    data_type="SymbolUpdate"  # Full tick data (LTP, volume, etc.)
                )
                self._log(f"Subscribed to: {self.symbols}", 'info')
        except Exception as e:
            self._log(f"Subscribe error: {e}", 'error')
    
    def _connect(self):
        """Establish WebSocket connection"""
        if not data_ws:
            self._log("FyersWebsocket not available", 'error')
            return False
        
        if not self.access_token:
            self._log("No access token provided", 'error')
            return False
        
        try:
            # Format token: "appid:accesstoken"
            if ':' not in self.access_token:
                token = f"{self.app_id}:{self.access_token}"
            else:
                token = self.access_token
            
            self.ws = data_ws.FyersDataSocket(
                access_token=token,
                log_path="",
                litemode=False,  # Full data mode
                write_to_file=False,
                reconnect=True,
                on_connect=self._on_open,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_message
            )
            
            return True
            
        except Exception as e:
            self._log(f"Connection error: {e}", 'error')
            return False
    
    def start(self):
        """Start WebSocket in background thread"""
        if self.running:
            self._log("Already running", 'warning')
            return
        
        self.running = True
        
        def run():
            if self._connect():
                try:
                    self.ws.connect()
                    self.ws.keep_running()
                except Exception as e:
                    self._log(f"WebSocket run error: {e}", 'error')
            
            self.running = False
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self._log("WebSocket thread started", 'info')
    
    def stop(self):
        """Stop WebSocket connection"""
        self.running = False
        self.connected = False
        
        if self.ws:
            try:
                self.ws.close_connection()
            except:
                pass
        
        self._log("WebSocket stopped", 'info')
    
    def get_latest_price(self, symbol):
        """Get latest price from cache"""
        return self.latest_prices.get(symbol, 0.0)
    
    def get_bars(self, symbol, interval, limit=100):
        """
        Get aggregated bars as DataFrame
        
        Args:
            symbol: Trading symbol
            interval: 1 or 5 (minutes)
            limit: Number of bars
        
        Returns:
            DataFrame with OHLC data
        """
        return self.aggregator.get_bars_df(symbol, interval, limit)
    
    def is_connected(self):
        """Check if WebSocket is connected and receiving data"""
        if not self.connected:
            return False
        
        # Check if we received data recently (within 10 seconds)
        if self.last_update:
            age = (datetime.now() - self.last_update).total_seconds()
            return age < 10
        
        return False
        
    def prime_history(self, symbol, df, interval=1):
        """Prime the aggregator with historical data"""
        self.aggregator.prime_history(symbol, df, interval)

# Singleton instance
_ws_handler = None

def get_ws_handler(access_token=None, symbols=None, on_bar_complete=None, on_tick=None, logger=None):
    """Get or create WebSocket handler singleton"""
    global _ws_handler
    
    if _ws_handler is None:
        _ws_handler = FyersWebSocketHandler(
            access_token=access_token,
            symbols=symbols,
            on_bar_complete=on_bar_complete,
            on_tick=on_tick,
            logger=logger
        )
    
    return _ws_handler

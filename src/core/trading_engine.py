import json
import os
import time
import threading
import sys
import logging
import pytz
import signal
import traceback
from datetime import datetime, timedelta
import pandas as pd
from fyers_apiv3 import fyersModel

# Local Imports
from src.core.base_strategy import INITIAL_CAPITAL, LOT_SIZE
# from src.brokers.fyers_paper_broker import FyersPaperBroker # Removed
from src.brokers.kotak_paper_broker import KotakPaperBroker
from src.brokers.kotak_broker import KotakBroker # <--- Added Real Broker
from src.brokers.fyers_broker import FyersBroker
from src.regime_detector import MarketRegimeGovernor
from src.strategies.adapters_basic import (
    EnhancedORBStrategy, RSIPullbackStrategy, TripleEMAStrategy, 
    MomentumSurgeStrategy, BandReversionStrategy, EMARegimeStrategy, 
    MACDMomentumStrategy
)
from src.strategies.adapters_advanced_p1 import (
    NiftyV2Adapter, BuyerSellerZoneAdapter, MeanReversionMomentumAdapter, 
    StatisticalStatArbAdapter
)
from src.strategies.adapters_advanced_p2 import (
    FailedAuctionAdapter, InsideBarBreakoutAdapter, InstitutionalStrategyAdapter,
    BearishBreakerAdapter, CompositeOperatorAdapter, AMDSetupAdapter,
    PoorLowAdapter, PDHSweepAdapter, ORBBreakoutShortAdapter
)
from src.strategies.ema_crossover_15m_1m_adapter import EMACrossover15m1mAdapter
from src.strategies.ema_crossover_short_15m_5m_adapter import EMACrossoverShort15m5mAdapter
from src.strategies.failed_auction_strategy import FailedAuctionStrategy
from src.strategies.amd_setup_strategy import AMDSetupStrategy

# Optional Imports (Graceful Fallback)
try:
    from src.websocket.fyers_ws_handler import FyersWebSocketHandler, get_ws_handler
    WS_AVAILABLE = True
    # WS_AVAILABLE = False
except ImportError:
    WS_AVAILABLE = False
    print("Warning: WebSocket handler not available")

try:
    from src.db.mongodb_handler import get_db_handler
    db_handler = get_db_handler()
except ImportError:
    db_handler = None
    print("Warning: MongoDB handler not available")

try:
    from src.brain.learning_engine import get_brain
    brain = get_brain()
    BRAIN_AVAILABLE = True
except ImportError:
    brain = None

DATA_FILE = 'strategy_state.json'

class TradingEngine:
    def __init__(self):
        self.lock = threading.Lock()
        # Initialize Kotak Broker (REAL TRADING)
        # self.broker = KotakPaperBroker()
        self.broker = KotakBroker()
        print(" [WARNING] REAL TRADING MODE ACTIVE ")
        
        self.strategies = [
            FailedAuctionStrategy(broker=self.broker),
            AMDSetupStrategy(broker=self.broker)
        ]
        
        self.df = None
        self.last_update = None
        self.running = True
        self.ws_handler = None
        self.last_reset_date = None
        self.use_websocket = WS_AVAILABLE
        
        # Dedicated History Broker (Industrial Grade)
        self.history_broker = FyersBroker()
        try:
            self.history_broker.connect()
        except Exception:
            print(" Warning: Fyers History Broker connection failed on init")

        print("[INIT] Initializing Market Regime Governor...")
        self.governor = MarketRegimeGovernor(self.history_broker)
        
        # Strategy Regime Mapping
        self.strategy_regimes = {}
        
        self.strategy_overrides = {}
        self.load_state()

    def check_fast_exits(self, symbol, ltp):
        if not self.running: return
        with self.lock:
            for strategy in self.strategies:
                if strategy.position and strategy.position.get('symbol') == symbol:
                    pos = strategy.position
                    entry_price = pos.get('entry', 0)
                    
                    # BAD TICK PROTECTION
                    if ltp <= 0:
                        print(f" BAD TICK IGNORED: {symbol} LTP={ltp}")
                        continue
                    
                    # Reject if deviation > 30% from entry
                    if entry_price > 0:
                        deviation = abs(ltp - entry_price) / entry_price
                        if deviation > 0.30:
                            print(f" BAD TICK IGNORED: {symbol} LTP={ltp} deviates {deviation*100:.1f}% from entry {entry_price}")
                            continue
                    
                    # NORMAL EXIT CHECKS
                    if pos['side'] == 'buy' and ltp >= pos['target']:
                        print(f" Fast Exit: {strategy.name} Target Hit! LTP: {ltp}, Tgt: {pos['target']}")
                        strategy.close_trade(ltp, 'target (Fast)')
                        continue
                    if pos['side'] == 'buy' and ltp <= pos['stop']:
                        print(f" Fast Exit: {strategy.name} Stop Hit! LTP: {ltp}, Stop: {pos['stop']}")
                        strategy.close_trade(ltp, 'stop (Fast)')
                        continue

    def start_websocket(self):
        if self.use_websocket:
            try:
                # Need valid access token for Fyers WS
                access_token = None
                if self.history_broker and self.history_broker.access_token:
                    access_token = self.history_broker.access_token
                
                if access_token:
                    self.ws_handler = get_ws_handler(
                        access_token=access_token,
                        symbols=["NSE:NIFTY50-INDEX"],
                        on_bar_complete=self._on_bar_complete,
                        on_tick=self.check_fast_exits,
                        logger=None
                    )
                    self.ws_handler.start()
                    print("[WS] WebSocket started with Fast Exit Trigger")
                else:
                    print("[WS] Skipped: No Fyers Access Token availability")
                    self.use_websocket = False
                self.ws_handler.start()
                print("[WS] WebSocket started with Fast Exit Trigger")
            except Exception as e:
                print(f"WebSocket init error: {e}")
                self.use_websocket = False
    
    def stop_websocket(self):
        if self.ws_handler:
            self.ws_handler.stop()
            print(" WebSocket stopped")

    def update_live_positions(self):
        """
        Active polling for open positions.
        Fetches latest LTP from Broker and checks for Exits.
        """
        if not self.running: return

        # Loop through strategies
        for strategy in self.strategies:
            if strategy.position:
                symbol = strategy.position.get('symbol')
                if not symbol: continue
                
                # Fetch live price via REST (Active Polling)
                ltp = self.broker.get_current_price(symbol)
                
                if ltp and ltp > 0:
                    # Update internal state
                    strategy.position['ltp'] = ltp
                    
                    # Check for Exits (Target / SL)
                    # Re-use the existing logic
                    self.check_fast_exits(symbol, ltp)
                    
                    # Update Trailing Stops if applicable
                    if hasattr(strategy, 'update_trailing_stop') and self.df is not None:
                        strategy.update_trailing_stop(self.df)


    def _on_bar_complete(self, symbol, interval, bar):
        print(f" Bar Complete: {symbol} {interval}m - Close: {bar['close']}")

    def validate_token(self, token=None):
        """
        Validate Kotak Broker connection.
        If token is provided, we might use it for specialized sessions,
        but typically we rely on env vars for Kotak.
        """
        try:
            if not self.broker.connected:
                self.broker.connect()
            return self.broker.connected
        except Exception as e:
            print(f"Validation error: {e}")
            return False
            
    def save_state(self):
        strategies_data = [s.get_stats() for s in self.strategies]
        ist = pytz.timezone('Asia/Kolkata')
        full_state = {
            'last_update': datetime.now(ist).isoformat(),
            'last_reset_date': self.last_reset_date,
            'running': self.running,
            'strategy_overrides': self.strategy_overrides,
            'strategies': strategies_data
        }
        if db_handler and db_handler.connected:
            db_handler.save_strategy_state(full_state)
            try:
                db_handler.db["system_config"].update_one(
                    {"_id": "bot_state"},
                    {"$set": {"running": self.running, "last_reset_date": self.last_reset_date}},
                    upsert=True
                )
            except: pass
        else:
            with open(DATA_FILE, 'w') as f:
                json.dump(full_state, f, indent=2)
    
    def load_state(self):
        data = None
        if db_handler and db_handler.connected:
            data = db_handler.load_strategy_state()
        if not data and os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
            except: pass
            
        if data:
            self.running = data.get('running', True) # Default to True for easier startup
            self.last_reset_date = data.get('last_reset_date')
            self.strategy_overrides = data.get('strategy_overrides', {})
            if db_handler and db_handler.connected:
                try:
                    conf = db_handler.db["system_config"].find_one({"_id": "bot_state"})
                    if conf: 
                        self.running = conf.get('running', False)
                        self.last_reset_date = conf.get('last_reset_date')
                except: pass

            if 'strategies' in data:
                saved_map = {s.get('name'): s for s in data['strategies']}
                for strategy in self.strategies:
                    if strategy.name in saved_map:
                        saved = saved_map[strategy.name]
                        strategy.capital = saved.get('capital', INITIAL_CAPITAL)
                        strategy.daily_start_capital = saved.get('daily_start_capital', strategy.capital)
                        strategy.wins = saved.get('wins', 0)
                        strategy.losses = saved.get('losses', 0)
                        if saved.get('position'):
                            strategy.position = saved.get('position')
                            print(f" Recovered open position for {strategy.name}: {strategy.position['symbol']}")
                        strategy.trades = saved.get('trades', [])
                        print(f" Loaded {len(strategy.trades)} trades for {strategy.name}")

    def sync_run_status(self):
        try:
            if db_handler and db_handler.connected:
                conf = db_handler.db["system_config"].find_one({"_id": "bot_state"})
                if conf:
                    external_running = conf.get('running', False)
                    if not external_running and self.running:
                        print(" External Stop Signal Detected (MongoDB)")
                        self.running = False
            elif os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r') as f:
                        data = json.load(f)
                        external_running = data.get('running', False)
                        if not external_running and self.running:
                             print(" External Stop Signal Detected (File)")
                             self.running = False
                except: pass
        except Exception: pass

    def fetch_data(self):
        if self.use_websocket and self.ws_handler and self.ws_handler.is_connected():
            try:
                df = self.ws_handler.get_bars("NSE:NIFTY50-INDEX", 1, limit=1000)
                if df is not None and len(df) >= 100:
                    df.columns = [c.lower() for c in df.columns]
                    ist = pytz.timezone('Asia/Kolkata')
                    self.df = df
                    self.last_update = datetime.now(ist)
                    return True
            except Exception as e:
                print(f"WebSocket data error: {e}")
        
        try:
            if not self.broker or not self.broker.connected:
                self.broker.connect()
            if not self.broker.connected: return False
                
            ist = pytz.timezone('Asia/Kolkata')
            
            df = self.broker.get_latest_bars("NSE:NIFTY50-INDEX", timeframe="1", limit=1000)
            if df is not None and not df.empty:
                self.df = df
                self.last_update = datetime.now(ist)
                return True
            else:
                 # print(f" Data fetch failed via Broker") # Reduce spam
                 return False

        except Exception as e: 
            print(f" Data fetch error: {e}")
            return False

    def run_strategies(self):
        if not self.running: return
        
        for strategy in self.strategies:
            # Check for overrides
            override = self.strategy_overrides.get(strategy.name)
            if override == 'PAUSED':
                strategy.paused = True
            elif override == 'ACTIVE':
                strategy.paused = False
            
            # Skip if paused
            if hasattr(strategy, 'paused') and strategy.paused:
                 if strategy.position:
                     # Manage exit for paused strategies if needed, or just monitor
                     pass
                 continue

            try:
                # Pass market regime if strategy supports it
                if hasattr(strategy, 'set_regime'):
                    strategy.set_regime(self.governor.get_regime())
                
                strategy.process(self.df, len(self.df))
            except Exception as e:
                print(f" Strategy {strategy.name} error: {e}")

    # ...

    def preload_history(self):
        if not self.broker: return
        print(f"[HISTORY] Pre-loading history (Industrial Warmup via Fyers API)... [DEBUG: Strategies={len(self.strategies)}]", flush=True)
        if not self.broker.connected:
             self.broker.connect()
             
        # Connect History Broker
        if not self.history_broker.connected:
             print("[HISTORY] Connecting History Broker...", flush=True)
             self.history_broker.connect()
             
        try:
            # Fetch Nifty 50 History for Warmup via Fyers (Professional Grade)
            print("[HISTORY] Fetching Nifty 50 history (1200 bars)...", flush=True)
            df = self.history_broker.get_latest_bars("NSE:NIFTY50-INDEX", timeframe='1', limit=1200)
            
            if df is not None and not df.empty:
                print(f"[HISTORY] Data received: {len(df)} bars. Columns: {df.columns.tolist()}", flush=True)
                # Ensure columns lower case
                df.columns = [c.lower() for c in df.columns]
                
                # Prime the broker's aggregator
                if hasattr(self.broker, 'prime_aggregator'):
                    print("[HISTORY] Priming Broker Aggregator...", flush=True)
                    self.broker.prime_aggregator("NSE:NIFTY50-INDEX", df)
                
                # Update Engine State
                self.df = df
                ist = pytz.timezone('Asia/Kolkata')
                self.last_update = datetime.now(ist)
                
                print(f"[HISTORY] SUCCESS: Historical data loaded via Fyers: {len(df)} bars", flush=True)
                print("[HISTORY] Warming up strategies...", flush=True)
                for strategy in self.strategies:
                    try: 
                        print(f"   - Processing {strategy.name}...", flush=True)
                        strategy.process(self.df, len(self.df))
                        print(f"   - {strategy.name} Status Update: {strategy.status}", flush=True)
                    except Exception as e: 
                        print(f"   - {strategy.name} Warmup Error: {e}", flush=True)
                        traceback.print_exc()
                print("[HISTORY] SUCCESS: All strategies primed and ready.", flush=True)
            else:
                print("[HISTORY] WARNING: Fyers history returned no data.", flush=True)
        except Exception as e:
            print(f"[HISTORY] ERROR: History pre-load error: {e}", flush=True)
            traceback.print_exc()
            
        self.save_state()

    # ...

    def run(self):
        print(" Trading loop started!", flush=True)
        if self.broker:
            print(" Connecting to Broker...")
            self.broker.connect()
            try:
                print(" Fetching Market Regime...")
                self.governor.update_regime()
            except Exception as e: print(f"Regime init error: {e}")
            self.preload_history()
            
        ist = pytz.timezone('Asia/Kolkata')
        from src.utils.notifications import send_telegram_message
        start_msg = (
            f" <b>Trading Bot Online</b>\n"
            f"\n"
            f" <b>Status:</b> Active\n"
            f" <b>Strategies:</b> {len(self.strategies)}\n"
            f" <b>Time:</b> {datetime.now(ist).strftime('%H:%M:%S')}\n"
            f"\n"
            f" <i>Good luck with today's trades!</i>"
        )
        send_telegram_message(start_msg)

        self.start_websocket()
        loop_count = 0
        last_token_check = datetime.now(ist) - timedelta(hours=7)  # Force check on startup
        
        while self.running:
            try:
                now = datetime.now(ist)
                loop_count += 1
                self.check_daily_reset()
                self.sync_run_status()
                
                # Periodic token health check (every 6 hours)
                hours_since_check = (now - last_token_check).total_seconds() / 3600
                if hours_since_check >= 6:
                    print(f" [{now.strftime('%H:%M:%S')}] Running token health check...")
                    try:
                        if self.broker:
                             health = self.broker.check_token_health()
                             if health.get('warnings'):
                                 print(f" Token health warnings: {health['warnings']}")
                             else:
                                 print(" Tokens are healthy")
                        last_token_check = now
                    except Exception as e:
                        print(f" Token health check error: {e}")
                
                if loop_count % 10 == 0:
                    print(f" [{now.strftime('%H:%M:%S')}] Heartbeat - Engine running: {self.running}", flush=True)
                
                market_time = now.hour * 100 + now.minute
                
                # 1. SHUTDOWN CHECK (15:15 PM)
                # Allow dry run after market if configured
                allow_after_market = os.getenv('ALLOW_AFTER_MARKET', '0') == '1'
                
                if market_time >= 1515 and not allow_after_market:
                    print(f" [{now.strftime('%H:%M:%S')}] Market Closing Shift (15:15). Shutting down.")
                    self.emergency_close_all()
                    self.running = False
                    break

                # 2. MARKET HOURS CHECK (09:15 - 15:30)
                if 915 <= market_time <= 1530:
                    if self.fetch_data():
                        if not self.running: break
                        print(f" [{now.strftime('%H:%M:%S')}] Data fetched...", flush=True)
                        
                        # 3. WARMUP ONLY CHECK (Before 09:20)
                        if market_time < 920:
                            print(f" [{now.strftime('%H:%M:%S')}] Warmup Mode (No Trade Entries)")
                            # We update indicators via fetch_data but skip strategy execution
                            self.save_state()
                            continue

                        self.run_strategies()
                        self.update_live_positions()
                        self.update_live_positions() # <--- Added Active Monitoring
                        self.save_state()
                    else:
                        if loop_count % 8 == 0: print(f" [{now.strftime('%H:%M:%S')}] Data fetch failed")
                else:
                    if loop_count % 20 == 0: print(f"[{now.strftime('%H:%M:%S')}] Outside market hours")
                
                for _ in range(15):
                    if not self.running: break
                    time.sleep(1)
            except Exception as e:
                print(f" Trading loop error: {e}")
                traceback.print_exc()
                for _ in range(30):
                    if not self.running: break
                    time.sleep(1)
        
        self.save_state()

    def get_portfolio_stats(self, mode='PAPER'):
        total_initial = INITIAL_CAPITAL * len(self.strategies)
        print(f" get_portfolio_stats: Mode={mode}, Strategies={len(self.strategies)}, Initial={total_initial}")
        
        # Base stats from strategies
        total_capital = sum(s.capital for s in self.strategies)
        total_pnl = total_capital - total_initial
        total_pnl_pct = (total_pnl / total_initial) * 100 if total_initial > 0 else 0
        
        if mode == 'REAL':
            if not self.broker.connected:
                print(" REAL mode requested, connecting broker...")
                try:
                    self.broker.connect()
                except Exception as e:
                    print(f" Broker connection failed: {e}")
            
            if self.broker.connected:
                try:
                    real_bal = self.broker.get_real_balance()
                    print(f" Real Balance Fetched: {real_bal}")
                    total_capital = real_bal
                    total_pnl = 0 # In real mode, PnL is often relative to start of session or day
                    total_pnl_pct = 0
                except Exception as e:
                    print(f" Real balance fetch failed: {e}")
        
        # Calculate Real Equity Curve from Trades
        equity_curve = []
        recent_trades = []
        
        if db_handler and db_handler.connected:
            try:
                raw_trades = db_handler.get_recent_trades(limit=100)
                # Sort Chronologically
                raw_trades.reverse()
                recent_trades = raw_trades
                
                curr_eq = total_initial
                equity_curve.append({'x': 0, 'y': curr_eq})
                
                for i, t in enumerate(raw_trades):
                    curr_eq += t.get('pnl', 0)
                    equity_curve.append({'x': i + 1, 'y': round(curr_eq, 2)})
            except Exception as e:
                print(f" Error building equity curve: {e}")
        
        # Fallback if no trades or history
        if not equity_curve:
            equity_curve = [
                {'x': 0, 'y': total_initial},
                {'x': 1, 'y': total_capital}
            ]

        total_today_pnl = sum(s.capital - s.daily_start_capital for s in self.strategies)
        total_wins = sum(s.wins for s in self.strategies)
        total_losses = sum(s.losses for s in self.strategies)
        total_trades = total_wins + total_losses
        total_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'total_capital': round(total_capital, 2),
            'total_initial': round(total_initial, 2),
            'total_pnl': round(total_pnl, 2),
            'total_today_pnl': round(total_today_pnl, 2),
            'total_pnl_pct': round(total_pnl_pct, 2),
            'total_wins': total_wins,
            'total_losses': total_losses,
            'total_trades': total_trades,
            'total_win_rate': round(total_win_rate, 1),
            'equity_curve': equity_curve,
            'recent_trades': recent_trades[:10], # Top 10 for dashboard
            'last_update': self.last_update.isoformat() if self.last_update else datetime.now().isoformat(),
            'running': self.running,
            'regime': self.governor.get_regime_status(),
            'strategies': [
                {**s.get_stats(), 'override_status': self.strategy_overrides.get(s.name, 'AUTO')} 
                for s in self.strategies
            ]
        }

    def reset_portfolio_state(self):
        self.running = False
        self.last_reset_date = None
        self.strategy_overrides = {}
        print(" PERFORMING HARD RESET OF PORTFOLIO ")
        if db_handler and db_handler.connected:
            try:
                db_handler.db["strategy_states"].delete_many({})
                db_handler.db["trades"].delete_many({})
                db_handler.db["system_config"].delete_many({"_id": "bot_state"})
                db_handler.db["brain_states"].delete_many({})
                print(" Database cleared")
            except Exception as e:
                print(f" Database clear failed: {e}")
        if os.path.exists(DATA_FILE):
            try: os.remove(DATA_FILE)
            except: pass
            
        # Re-initialize strategies
        for strategy in self.strategies:
            strategy.capital = INITIAL_CAPITAL
            strategy.daily_start_capital = INITIAL_CAPITAL
            strategy.wins = 0
            strategy.losses = 0
            strategy.position = None
            strategy.trades = []
        
        self.save_state()
        print(" Hard Reset Complete.")

    def check_daily_reset(self):
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        today_str = now.strftime("%Y-%m-%d")
        if self.last_reset_date != today_str:
            if now.hour >= 9:
                print(f" Daily Reset performing for {today_str}...")
                for strategy in self.strategies:
                    strategy.daily_start_capital = strategy.capital
                self.last_reset_date = today_str
                self.save_state()
                return True
        return False
        

    def emergency_close_all(self):
        print("\n EMERGENCY SHUTDOWN INITIATED ")
        self.running = False
        for strategy in self.strategies:
            if strategy.position:
                try:
                    symbol = strategy.position.get('symbol')
                    if symbol and self.broker:
                        self.broker.close_position(symbol)
                    strategy.close_trade(strategy.position.get('entry', 0), "SHUTDOWN_FORCE_CLOSE")
                except Exception as e: print(f" Failed to close {strategy.name}: {e}")
        self.save_state()
        print(" All strategies halted.")

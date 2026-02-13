import os
import sys
import threading
import signal
import logging
import traceback
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load env before imports that might need it
load_dotenv()

# NOTE: TradingEngine import is deferred to initialize_engine() to avoid
# blocking Gunicorn startup with heavy module-level imports
from src.api.server import app, init_app, socketio

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)

print("[MAIN] Starting Multi-Strategy Trading Engine (Refactored)...")
print(" VERIFYING STDOUT: Logs should appear here.", flush=True)


# Global engine reference (will be initialized in background)
engine = None
engine_ready = False

def initialize_engine():
    """Initialize TradingEngine in background with retry logic"""
    global engine, engine_ready
    import time as _time
    
    MAX_RETRIES = 3
    RETRY_DELAYS = [10, 30, 60]  # seconds between retries
    
    for attempt in range(MAX_RETRIES):
        try:
            t0 = _time.time()
            print(f"[INIT] Attempt {attempt+1}/{MAX_RETRIES}: Importing TradingEngine...", flush=True)
            from src.core.trading_engine import TradingEngine
            print(f"[INIT] Import done in {_time.time()-t0:.1f}s. Creating instance...", flush=True)
            engine = TradingEngine()
            init_app(engine)
            engine_ready = True
            print(f"[INIT] TradingEngine ready! Total init: {_time.time()-t0:.1f}s", flush=True)
            
            # Start trading loop if engine is running
            if engine.running:
                print("[INIT] Starting trading loop thread...", flush=True)
                threading.Thread(target=engine.run, daemon=True, name='trading_loop').start()
            
            # Start broker auto-reconnect in background
            if engine.broker and not engine.broker.connected:
                print("[INIT] Broker not connected, starting auto-reconnect thread...", flush=True)
                threading.Thread(target=_broker_reconnect_loop, args=(engine,), daemon=True, name='broker_reconnect').start()
            
            return  # Success - exit retry loop
            
        except Exception as e:
            error_msg = f"[INIT] Attempt {attempt+1} failed: {e}"
            print(error_msg, flush=True)
            traceback.print_exc()
            
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"[INIT] Retrying in {delay}s...", flush=True)
                _time.sleep(delay)
            else:
                print("[INIT] All retries exhausted. Storing error.", flush=True)
                engine_ready = False
                error_details = f"Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                app.config['STARTUP_ERROR'] = error_details
                app.config['ENGINE_STATUS'] = 'FAILED'

def _broker_reconnect_loop(engine_instance):
    """Background thread to retry broker connection with exponential backoff"""
    import time as _time
    delays = [30, 60, 120, 300]  # seconds
    attempt = 0
    while not engine_instance.broker.connected:
        delay = delays[min(attempt, len(delays) - 1)]
        print(f"[RECONNECT] Broker reconnect attempt {attempt+1} in {delay}s...", flush=True)
        _time.sleep(delay)
        try:
            engine_instance.broker.connect()
            if engine_instance.broker.connected:
                print("[RECONNECT] Broker connected successfully!", flush=True)
                # Start trading loop if not already running
                if engine_instance.running and not any(t.name == 'trading_loop' for t in threading.enumerate()):
                    threading.Thread(target=engine_instance.run, daemon=True, name='trading_loop').start()
                return
        except Exception as e:
            print(f"[RECONNECT] Broker reconnect failed: {e}", flush=True)
        attempt += 1
        if attempt >= 20:  # Give up after ~20 attempts
            print("[RECONNECT] Max reconnect attempts reached. Giving up.", flush=True)
            return

# Start engine initialization in background thread
print("[MAIN] Starting background engine initialization...", flush=True)
init_thread = threading.Thread(target=initialize_engine, daemon=True, name='engine_init')
init_thread.start()

# Expose app for Gunicorn immediately (even before engine is ready)
application = socketio

def signal_handler(sig, frame):
    print(f"\n Signal {sig} received. Shutting down...")
    try:
        engine.running = False
        engine.emergency_close_all()
    except: pass
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def main():
    try:
        # Start Flask immediately (Engine inits in background)
        port = int(os.environ.get("PORT", 8080))
        print(f" Dashboard available at http://localhost:{port}")
        
        # Use socketio.run instead of app.run for real-time support
        socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f" Main Loop Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()

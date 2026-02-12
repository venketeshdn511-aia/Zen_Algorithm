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
from src.api.server import app, init_app

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
    """Initialize TradingEngine in background to avoid blocking Flask startup"""
    global engine, engine_ready
    try:
        import time as _time
        t0 = _time.time()
        print("[INIT] Importing TradingEngine...", flush=True)
        from src.core.trading_engine import TradingEngine
        print(f"[INIT] Import done in {_time.time()-t0:.1f}s. Creating instance...", flush=True)
        engine = TradingEngine()
        init_app(engine)
        engine_ready = True
        print(f"[INIT] TradingEngine ready! Total init: {_time.time()-t0:.1f}s", flush=True)
        
        # Start trading loop if engine is running (handled in bg now)
        if engine.running:
            print("[INIT] Starting trading loop thread...", flush=True)
            threading.Thread(target=engine.run, daemon=True, name='trading_loop').start()
    except Exception as e:
        print(f"[INIT] Critical Startup Error: {e}", flush=True)
        traceback.print_exc()
        engine_ready = False

# Start engine initialization in background thread
print("[MAIN] Starting background engine initialization...", flush=True)
init_thread = threading.Thread(target=initialize_engine, daemon=True, name='engine_init')
init_thread.start()

# Expose app for Gunicorn immediately (even before engine is ready)
application = app

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
        
        # Disable Flask reloader to avoid duplicate threads
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f" Main Loop Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()

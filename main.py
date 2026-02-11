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

from src.core.trading_engine import TradingEngine
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
        print("[INIT] Starting TradingEngine initialization in background...", flush=True)
        engine = TradingEngine()
        init_app(engine)
        engine_ready = True
        print("[INIT] TradingEngine ready!", flush=True)
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
        # Wait for engine to be ready
        print("[MAIN] Waiting for engine initialization...", flush=True)
        while not engine_ready:
            import time
            time.sleep(1)
        
        print("[MAIN] Engine ready, starting trading loop...", flush=True)
        
        # If running directly, start thread and server
        if not engine.running:
            print(" [DEBUG] Engine start forced for verification...", flush=True)
            engine.running = True
            
        if engine.running: 
            print(" Auto-resuming trading loop...")
            thread = threading.Thread(target=engine.run, daemon=True, name='trading_loop')
            thread.start()
            
        port = int(os.environ.get("PORT", 8080))
        print(f" Dashboard available at http://localhost:{port}")
        
        # Disable Flask reloader to avoid duplicate threads
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f" Main Loop Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()

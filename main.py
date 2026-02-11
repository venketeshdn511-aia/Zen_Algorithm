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

# Initialize Engine
try:
    engine = TradingEngine()
    
    # Initialize API
    init_app(engine)
    
    # Expose app for Gunicorn
    application = app 
except Exception as e:
    print(f" Critical Startup Error: {e}")
    traceback.print_exc()
    sys.exit(1)

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

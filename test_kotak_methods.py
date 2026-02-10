import os
import logging
from dotenv import load_dotenv
from src.brokers.kotak_broker import KotakBroker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Env
load_dotenv()

def test_kotak_methods():
    logger.info("🚀 Testing KotakBroker Methods...")
    broker = KotakBroker(logger=logger)
    
    # 1. Connect
    broker.connect()
    if not broker.connected:
        logger.error("❌ Connection Failed")
        return

    # 2. Check Health
    logger.info("🩺 Checking Token Health...")
    health = broker.check_token_health()
    logger.info(f"Health: {health}")

    # 3. Get Positions
    logger.info("💼 Fetching Positions...")
    positions = broker.get_positions()
    logger.info(f"Positions: {positions}")

    # 4. Get Latest Bars (History) - Wait for WS data
    symbol = "Nifty 50" # Uses map logic inside
    logger.info(f"📈 Fetching History for {symbol} (Waiting for WS accumulation)...")
    
    # Needs some time to get ticks and form partial bar
    import time
    for i in range(10):
        time.sleep(2) 
        
        ltp = broker.get_current_price(symbol)
        logger.info(f"Current Price for {symbol}: {ltp}")
        
        df = broker.get_latest_bars(symbol, timeframe="1", limit=100)
        if df is not None and not df.empty:
            logger.info(f"✅ History Received (Attempt {i+1}):\n{df.head()}")
            logger.info(f"Columns: {df.columns}")
            break
        else:
            logger.info(f"⏳ Waiting for data... (Attempt {i+1})")
            
    if df is None or df.empty:
        logger.error("❌ History Fetch Failed or Empty after waiting")

if __name__ == "__main__":
    test_kotak_methods()

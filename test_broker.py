
import os
import sys
import time
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.brokers.kotak_broker import KotakBroker
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_broker():
    print(" Testing KotakBroker...")
    broker = KotakBroker()
    broker.connect()
    
    if not broker.connected:
        print(" Connection Failed")
        return
        
    print(" Connected.")
    
    # Test Nifty 50 (Index) -> Should fail REST and use WS
    print("\n Fetching Nifty 50 (Expected: WS)...")
    nifty_ltp = broker.get_current_price("Nifty 50")
    print(f" Nifty 50 LTP: {nifty_ltp}")
    
    # Test SBIN (Equity) -> Should use REST (or WS if REST fails)
    print("\n Fetching SBIN (Expected: REST)...")
    sbin_ltp = broker.get_current_price("SBIN")
    print(f" SBIN LTP: {sbin_ltp}")
    
    # Wait a bit to see if WS updates cache
    print("\nWaiting 25s for WS updates...")
    time.sleep(25)
    
    nifty_ltp_2 = broker.get_current_price("Nifty 50")
    print(f" Nifty 50 LTP (After 25s): {nifty_ltp_2}")

if __name__ == "__main__":
    test_broker()

import os
import sys
import logging
from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Setup Logging to see everything
logging.basicConfig(level=logging.INFO)

from src.brokers.kotak_broker import KotakBroker

print("🚀 Starting Kotak Connection Test...")

broker = KotakBroker()
print(f"Mobile: {broker.MOBILE_NUMBER[:4]}****" if broker.MOBILE_NUMBER else "Mobile: MISSING")
print(f"Key: {broker.CONSUMER_KEY[:4]}****" if broker.CONSUMER_KEY else "Key: MISSING")

try:
    broker.connect()
    if broker.connected:
        print("✅ SUCCESS: Connected to Kotak!")
        print("🔍 Debugging Limits API...")
        limits = broker.api.limits()
        import json
        print(f"📦 Full Limits Response: {json.dumps(limits, indent=2)}")
        
        # Check specific fields
        if isinstance(limits, dict) and 'data' in limits:
            data = limits['data']
            print(f"📊 Data Keys: {list(data.keys())}")
            for k in ['cashBalance', 'availMar', 'curMar', 'marginUsed']:
                if k in data:
                    print(f"🔹 {k}: {data[k]}")
        
        balance = broker.get_real_balance()
        print(f"💰 Extracted Real Balance: {balance}")
    else:
        print("❌ FAILED: Could not connect to Kotak.")
except Exception as e:
    print(f"🚨 CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()

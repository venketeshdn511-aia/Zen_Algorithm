"""
Push local strategy_data.json to MongoDB Atlas
This ensures MongoDB has the correct trade history
"""
import os
import sys
import json

# Load environment FIRST
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.getcwd())

from src.db.mongodb_handler import MongoDBHandler

def push_to_mongodb():
    print("🔌 Connecting to MongoDB Atlas...")
    db = MongoDBHandler()
    
    if not db.connected:
        print("❌ Failed to connect to MongoDB. Check MONGODB_URI env var.")
        return False

    # Load local JSON
    if not os.path.exists('strategy_data.json'):
        print("❌ No local strategy_data.json found!")
        return False
        
    with open('strategy_data.json', 'r') as f:
        local_data = json.load(f)
    
    print(f"📄 Loaded {len(local_data.get('strategies', []))} strategies from local file")
    
    # Count trades to verify
    for s in local_data.get('strategies', []):
        print(f"   - {s['name']}: {len(s.get('trades', []))} trades")
    
    # Push to MongoDB
    print("📤 Pushing to MongoDB...")
    success = db.save_strategy_state(local_data.get('strategies', []))
    
    if success:
        print("✅ Successfully pushed local data to MongoDB Atlas!")
        return True
    else:
        print("❌ Failed to push data to MongoDB")
        return False

if __name__ == "__main__":
    push_to_mongodb()

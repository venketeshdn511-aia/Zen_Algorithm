"""
Reset all strategy overrides to AUTO in MongoDB
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.getcwd())
from src.db.mongodb_handler import get_db_handler

def reset_overrides():
    print("🔌 Connecting to MongoDB...")
    db = get_db_handler()
    
    if not db.connected:
        print("❌ Not connected to MongoDB")
        return
    
    # Reset strategy_overrides to empty dict
    result = db.db['system_config'].update_one(
        {'_id': 'bot_state'},
        {'$set': {'strategy_overrides': {}}},
        upsert=True
    )
    
    print(f"✅ Reset all strategy overrides to AUTO")
    print(f"   Modified: {result.modified_count}, Upserted: {result.upserted_id is not None}")

if __name__ == "__main__":
    reset_overrides()

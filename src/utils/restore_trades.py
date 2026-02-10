
import os
import sys
import json
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv

# Load env immediately
load_dotenv()

# Add project root to path
sys.path.append(os.getcwd())

from src.db.mongodb_handler import MongoDBHandler

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def restore_trades():
    """
    Fetches trade history from MongoDB and reconstructs strategy_data.json
    """
    logger.info("🔌 Connecting to MongoDB...")
    db = MongoDBHandler()
    
    if not db.connected:
        logger.error("❌ Failed to connect to MongoDB. Cannot restore data.")
        return

    logger.info("📥 Fetching recent trades from Atlas...")
    trades = db.get_recent_trades(limit=500) # Fetch last 500 trades
    
    if not trades:
        logger.warning("⚠️ No trades found in MongoDB.")
        return

    logger.info(f"✅ Found {len(trades)} trades. Grouping by strategy...")

    # Group trades by strategy
    strategy_trades = {}
    for trade in trades:
        strat_name = trade.get('strategy')
        if not strat_name: continue
        
        if strat_name not in strategy_trades:
            strategy_trades[strat_name] = []
        
        # Normalize trade keys if needed (Mongo vs Local format)
        # Ensure minimal required fields present
        strategy_trades[strat_name].append(trade)

    # Load existing local state to preserve capital/settings
    local_data = {}
    if os.path.exists('strategy_data.json'):
        try:
            with open('strategy_data.json', 'r') as f:
                local_data = json.load(f)
                logger.info("📂 Loaded existing local state.")
        except Exception as e:
            logger.warning(f"⚠️ Could not load existing local state: {e}")

    # Update strategies in local state
    if 'strategies' not in local_data:
        local_data['strategies'] = []

    # Map existing strategies for easy updates
    existing_strats = {s['name']: s for s in local_data['strategies']}
    
    updated_count = 0
    
    for strat_name, trades_list in strategy_trades.items():
        # Sort trades by time
        trades_list.sort(key=lambda x: x.get('exit_time') or x.get('entry_time') or '', reverse=False)
        
        if strat_name in existing_strats:
            # Update existing
            existing_strats[strat_name]['trades'] = trades_list
            logger.info(f"🔄 Restored {len(trades_list)} trades for {strat_name}")
            updated_count += 1
        else:
            # Create new entry if missing (less likely but possible)
            new_strat = {
                'name': strat_name,
                'capital': 15000.0, # Default
                'position': None,
                'trades': trades_list,
                'wins': sum(1 for t in trades_list if t.get('pnl', 0) > 0),
                'losses': sum(1 for t in trades_list if t.get('pnl', 0) <= 0)
            }
            local_data['strategies'].append(new_strat)
            logger.info(f"➕ Created new state entry for {strat_name} with {len(trades_list)} trades")
            updated_count += 1

    # Save back to strategy_data.json
    try:
        with open('strategy_data.json', 'w') as f:
            json.dump(local_data, f, indent=2)
        logger.info(f"💾 Successfully saved restored data to strategy_data.json")
    except Exception as e:
        logger.error(f"❌ Failed to write strategy_data.json: {e}")

if __name__ == "__main__":
    restore_trades()

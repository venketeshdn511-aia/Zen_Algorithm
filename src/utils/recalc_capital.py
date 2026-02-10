"""
Recalculate strategy capitals from trade PnL and push to MongoDB
"""
import os
import sys
import json

from dotenv import load_dotenv
load_dotenv()

sys.path.append(os.getcwd())

from src.db.mongodb_handler import MongoDBHandler

INITIAL_CAPITAL = 15000.0

def recalculate_and_push():
    print("🔌 Connecting to MongoDB Atlas...")
    db = MongoDBHandler()
    
    if not db.connected:
        print("❌ Failed to connect to MongoDB.")
        return False

    # Load local JSON
    if not os.path.exists('strategy_data.json'):
        print("❌ No local strategy_data.json found!")
        return False
        
    with open('strategy_data.json', 'r') as f:
        local_data = json.load(f)
    
    print(f"📄 Processing {len(local_data.get('strategies', []))} strategies...")
    
    for s in local_data.get('strategies', []):
        # Calculate total PnL from trades
        total_pnl = 0
        wins = 0
        losses = 0
        
        for t in s.get('trades', []):
            pnl = t.get('pnl', 0) or 0
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            total_pnl += pnl
        
        # Update capital based on PnL
        old_capital = s.get('capital', INITIAL_CAPITAL)
        new_capital = INITIAL_CAPITAL + total_pnl
        
        s['capital'] = round(new_capital, 2)
        s['wins'] = wins
        s['losses'] = losses
        s['daily_start_capital'] = s.get('daily_start_capital', INITIAL_CAPITAL)
        
        print(f"   {s['name']}: {len(s.get('trades', []))} trades, PnL: ₹{total_pnl:.2f}, Capital: ₹{old_capital:.2f} → ₹{new_capital:.2f}")
    
    # Save locally first
    with open('strategy_data.json', 'w') as f:
        json.dump(local_data, f, indent=2)
    print("💾 Updated local strategy_data.json")
    
    # Push to MongoDB
    print("📤 Pushing corrected data to MongoDB...")
    success = db.save_strategy_state(local_data.get('strategies', []))
    
    if success:
        print("✅ Successfully pushed corrected capitals to MongoDB!")
        return True
    else:
        print("❌ Failed to push to MongoDB")
        return False

if __name__ == "__main__":
    recalculate_and_push()

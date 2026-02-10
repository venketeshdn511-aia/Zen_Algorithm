"""
MongoDB Atlas Handler for Trading Bot
Stores strategy states and trade history in MongoDB
"""
import os
from datetime import datetime
import pytz
from typing import Dict, List, Optional
import json

try:
    from pymongo import MongoClient
    from pymongo.server_api import ServerApi
    from bson import ObjectId
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    print("Warning: pymongo not installed. Using local JSON storage.")


class MongoDBHandler:
    """
    Handles MongoDB Atlas connection and data operations.
    Falls back to local JSON if MongoDB is unavailable.
    """
    
    def __init__(self, connection_string: Optional[str] = None, db_name: str = "trading_bot"):
        self.db_name = db_name
        self.connection_string = connection_string or os.getenv("MONGODB_URI")
        self.client = None
        self.db = None
        self.connected = False
        self.local_file = "strategy_data.json"
        
        # Initial connection attempt
        self.connect()

    def connect(self) -> bool:
        """Attempt to connect to MongoDB Atlas"""
        if self.connected:
            return True
            
        uri = self.connection_string
        
        if uri and MONGO_AVAILABLE:
            try:
                # Python 3.13 has stricter SSL validation
                # Try multiple connection strategies
                
                # Strategy 1: Use certifi CA bundle
                try:
                    import certifi
                    ca = certifi.where()
                except ImportError:
                    ca = None
                
                connection_successful = False
                
                # Strategy 1: With certifi
                if ca and not connection_successful:
                    try:
                        self.client = MongoClient(
                            uri, 
                            server_api=ServerApi('1'),
                            tlsCAFile=ca,
                            serverSelectionTimeoutMS=10000
                        )
                        self.client.admin.command('ping')
                        connection_successful = True
                        print("✅ Connected with certifi CA")
                    except Exception as e1:
                        print(f"Certifi strategy failed: {e1}")
                
                # Strategy 2: Allow invalid certificates (less secure but works on Render)
                if not connection_successful:
                    try:
                        self.client = MongoClient(
                            uri,
                            server_api=ServerApi('1'),
                            tlsAllowInvalidCertificates=True,
                            serverSelectionTimeoutMS=10000
                        )
                        self.client.admin.command('ping')
                        connection_successful = True
                        print("✅ Connected with relaxed SSL")
                    except Exception as e2:
                        print(f"Relaxed SSL strategy failed: {e2}")
                
                # Strategy 3: Direct connection (no SRV lookup)
                if not connection_successful:
                    try:
                        # Convert SRV URI to direct connection
                        direct_uri = uri.replace("mongodb+srv://", "mongodb://")
                        self.client = MongoClient(
                            direct_uri,
                            tls=True,
                            tlsAllowInvalidCertificates=True,
                            serverSelectionTimeoutMS=10000
                        )
                        self.client.admin.command('ping')
                        connection_successful = True
                        print("✅ Connected with direct connection")
                    except Exception as e3:
                        print(f"Direct connection strategy failed: {e3}")
                
                if connection_successful:
                    self.db = self.client[self.db_name]
                    self.connected = True
                    print(f"✅ Connected to MongoDB Atlas: {self.db_name}")
                    return True
                else:
                    raise Exception("All connection strategies failed")
            except Exception as e:
                print(f"⚠️ MongoDB connection failed: {e}")
                self.connected = False
                return False
        else:
            if not MONGO_AVAILABLE:
                print("⚠️ pymongo not installed. Using local JSON storage.")
            else:
                print("⚠️ No MONGODB_URI provided. Using local JSON storage.")
            return False
    
    def _stringify_ids(self, obj):
        """Helper to convert BSON ObjectIds to strings recursively"""
        if isinstance(obj, dict):
            return {k: self._stringify_ids(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._stringify_ids(i) for i in obj]
        elif MONGO_AVAILABLE and isinstance(obj, ObjectId):
            return str(obj)
        return obj
    
    def save_strategy_state(self, state: Dict) -> bool:
        """Save full strategy state to MongoDB or local JSON"""
        ist = pytz.timezone('Asia/Kolkata')
        # Ensure last_update is set if not present
        if "last_update" not in state:
            state["last_update"] = datetime.now(ist).isoformat()
        
        data = state
        
        if self.connected:
            try:
                collection = self.db["strategy_states"]
                # Sanitize data before saving to avoid BSON/JSON conflicts downstream
                clean_data = self._stringify_ids(data)
                # Upsert the current state
                collection.update_one(
                    {"_id": "current_state"},
                    {"$set": clean_data},
                    upsert=True
                )
                return True
            except Exception as e:
                print(f"MongoDB save error: {e}")
                # Fall back to local
                return self._save_local(data)
        else:
            return self._save_local(data)
    
    def load_strategy_state(self) -> Optional[Dict]:
        """Load strategy states from MongoDB or local JSON"""
        if not self.connected:
            self.connect()
            
        if self.connected:
            try:
                collection = self.db["strategy_states"]
                doc = collection.find_one({"_id": "current_state"})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception as e:
                print(f"MongoDB load error: {e}")
        
        # Fall back to local
        return self._load_local()

    def save_brain_state(self, state: Dict) -> bool:
        """Save brain state to MongoDB"""
        if self.connected:
            try:
                collection = self.db["brain_states"]
                # Upsert the global brain state
                collection.update_one(
                    {"_id": "global_brain"},
                    {"$set": state},
                    upsert=True
                )
                return True
            except Exception as e:
                print(f"MongoDB brain save error: {e}")
        return False

    def load_brain_state(self) -> Optional[Dict]:
        """Load brain state from MongoDB"""
        if self.connected:
            try:
                collection = self.db["brain_states"]
                doc = collection.find_one({"_id": "global_brain"})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception as e:
                print(f"MongoDB brain load error: {e}")
        return None
    
    def save_trade(self, trade: Dict) -> bool:
        """Save a single trade to MongoDB"""
        ist = pytz.timezone('Asia/Kolkata')
        trade["timestamp"] = datetime.now(ist).isoformat()
        
        if self.connected:
            try:
                collection = self.db["trades"]
                collection.insert_one(trade)
                return True
            except Exception as e:
                print(f"MongoDB trade save error: {e}")
                return False
        return False
    
    def get_recent_trades(self, limit: int = 50) -> List[Dict]:
        """Get recent trades from MongoDB"""
        if not self.connected:
            self.connect()
            
        if self.connected:
            try:
                collection = self.db["trades"]
                # Only include EXIT trades (completed trades with PnL) for the dashboard
                trades = list(collection.find().sort("timestamp", -1).limit(limit))
                for trade in trades:
                    trade.pop("_id", None)
                    # Convert timestamp object to string if it's not already
                    if 'timestamp' in trade and not isinstance(trade['timestamp'], str):
                         trade['timestamp'] = trade['timestamp'].isoformat()
                return trades
            except Exception as e:
                print(f"MongoDB trades fetch error: {e}")
        return []
    
    def _save_local(self, data: Dict) -> bool:
        """Save to local JSON file"""
        try:
            with open(self.local_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Local save error: {e}")
            return False
    
    def _load_local(self) -> Optional[Dict]:
        """Load from local JSON file"""
        try:
            if os.path.exists(self.local_file):
                with open(self.local_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Local load error: {e}")
        return None
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            print("MongoDB connection closed")


# Singleton instance
_db_handler = None

def get_db_handler() -> MongoDBHandler:
    """Get or create the MongoDB handler singleton"""
    global _db_handler
    if _db_handler is None:
        _db_handler = MongoDBHandler()
    return _db_handler

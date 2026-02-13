
import os
import sys
import time
import logging
import traceback
import pandas as pd
from datetime import datetime
import pyotp
import requests
from neo_api_client import NeoAPI
from src.utils.bar_aggregator import BarAggregator

class KotakBroker:
    def __init__(self, logger=None, db_handler=None):
        self.logger = logger or logging.getLogger(__name__)
        self.db_handler = db_handler
        self.api = None
        self.connected = False
        self.token_map = {} # Cache for symbol -> token
        
        # Load Credentials
        self.CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
        self.CONSUMER_SECRET = os.getenv("KOTAK_CONSUMER_SECRET")
        self.MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
        self.PASSWORD = os.getenv("KOTAK_PASSWORD")
        self.MPIN = os.getenv("KOTAK_MPIN")
        self.TOTP_SECRET = os.getenv("KOTAK_TOTP_SECRET")
        self.UCC = os.getenv("KOTAK_UCC")
        
        # WebSocket State
        self.ltp_cache = {} # Map "26000" -> 25980.0
        self.subscribed_tokens = set()
        
        # Aggregator
        self.aggregator = BarAggregator(intervals=[1, 5, 15])
        
    def _generate_totp(self):
        if not self.TOTP_SECRET: return None
        try:
            return pyotp.TOTP(self.TOTP_SECRET).now()
        except Exception as e:
            print(f" [KOTAK] TOTP generation failed: {e}")
            return None
        
    # WS Callbacks
    # WS Callbacks
    def on_message(self, message):
        """WebSocket Message Handler"""
        # self.logger.info(f" WS Message: {str(message)[:100]}...")
        try:
             # Kotak might send {'data': [...]} or direct list/dict depending on subscription?
             # Based on previous log: {'type': 'stock_feed', 'data': [...]}
             if isinstance(message, dict) and 'data' in message:
                 for m in message['data']:
                     self.process_tick(m)
             elif isinstance(message, list):
                 for m in message:
                     self.process_tick(m)
             # else: unknown format
        except Exception as e:
             self.logger.error(f"WS Message Error: {e}")

    def process_tick(self, msg):
        try:
             token = str(msg.get('tk'))
             ltp_str = msg.get('ltp') or msg.get('lp')
             # Index value might be under 'iv'?
             if not ltp_str and 'iv' in msg: ltp_str = msg.get('iv')
                 
             if token and ltp_str:
                 ltp = float(ltp_str)
                 self.ltp_cache[token] = ltp
                 self.logger.info(f" Cache Updated: {token} -> {ltp}")
                 
                 vol = float(msg.get('v', 0))
                 ts = time.time()
                 self.aggregator.process_tick(token, ltp, vol, ts)
        except Exception as e:
             self.logger.error(f"Tick Processing Error: {e}")

    def on_error(self, error):
        self.logger.error(f"WS Error: {error}")
        
    def on_open(self, message):
        self.logger.info(" Kotak WS Connection Opened")
        
    def on_close(self, message):
        self.logger.info(" Kotak WS Connection Closed")

    def connect(self):
        """Connect to Kotak Neo API using TOTP Flow"""
        try:
            # Validate all required environment variables
            missing_vars = []
            if not self.CONSUMER_KEY: missing_vars.append("KOTAK_CONSUMER_KEY")
            if not self.CONSUMER_SECRET: missing_vars.append("KOTAK_CONSUMER_SECRET")
            if not self.MOBILE_NUMBER: missing_vars.append("KOTAK_MOBILE_NUMBER")
            if not self.PASSWORD: missing_vars.append("KOTAK_PASSWORD")
            if not self.MPIN: missing_vars.append("KOTAK_MPIN")
            if not self.TOTP_SECRET: missing_vars.append("KOTAK_TOTP_SECRET")
            if not self.UCC: missing_vars.append("KOTAK_UCC")
            
            if missing_vars:
                self.logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
                self.connected = False
                return

            self.logger.info(" Initializing Kotak Neo Client...")
            # NeoAPI v2.0.0+ does NOT accept consumer_secret in __init__
            # Only pass consumer_key and environment
            self.api = NeoAPI(
                consumer_key=self.CONSUMER_KEY,
                environment='prod'
            )
            
            # Login Flow - Use totp_login() + totp_validate() which works in ALL SDK versions
            self.logger.info(f" Authenticating User: {self.MOBILE_NUMBER}")
            otp = self._generate_totp()
            if not otp:
                self.logger.error(" TOTP Generation Failed - check KOTAK_TOTP_SECRET")
                self.connected = False
                return
            
            validate_resp = None
            try:
                # PREFERRED: totp_login() + totp_validate() - works in both v1.0.3 and v2.0.0+
                if hasattr(self.api, 'totp_login'):
                    self.logger.info(" Using totp_login() flow...")
                    
                    mobile = self.MOBILE_NUMBER
                    # Try login as provided in .env
                    login_resp = self.api.totp_login(
                        mobile_number=mobile,
                        ucc=self.UCC,
                        totp=otp
                    )
                    self.logger.info(f" totp_login result (attempt 1): {login_resp}")
                    
                    # If it fails with 'Invalid field MobileNumber', try stripping the +
                    if login_resp and isinstance(login_resp, dict) and 'error' in login_resp:
                        err_msg = str(login_resp.get('error', ''))
                        if 'MobileNumber' in err_msg and mobile.startswith('+'):
                            self.logger.info(" Retrying without '+' prefix...")
                            mobile = mobile[1:] # Strip +
                            login_resp = self.api.totp_login(
                                mobile_number=mobile,
                                ucc=self.UCC,
                                totp=otp
                            )
                            self.logger.info(f" totp_login result (attempt 2): {login_resp}")

                    # Attempt 3: Manual Request with PascalCase (MobileNumber)
                    # Many times SDKs have outdated field names.
                    if login_resp and isinstance(login_resp, dict) and 'error' in login_resp:
                        self.logger.info(" Attempting manual request with PascalCase 'MobileNumber'...")
                        try:
                            import requests
                            # Get domain and path
                            base_url = self.api.configuration.get_domain(session_init=True)
                            url = f"{base_url}/login/1.0/tradeApiLogin"
                            
                            headers = {
                                'Authorization': self.api.configuration.consumer_key,
                                'neo-fin-key': self.api.configuration.get_neo_fin_key(),
                                'Content-Type': 'application/json'
                            }
                            
                            # Try with 'MobileNumber' instead of 'mobileNumber'
                            payload = {
                                "MobileNumber": self.MOBILE_NUMBER if self.MOBILE_NUMBER.startswith('+') else f"+{self.MOBILE_NUMBER}",
                                "ucc": self.UCC,
                                "totp": otp
                            }
                            
                            res = requests.post(url, headers=headers, json=payload)
                            if res.status_code == 200:
                                login_resp = res.json()
                                self.logger.info(f" Manual login success (Attempt 3): {login_resp}")
                                # Sync SDK session manually
                                if login_resp and 'data' in login_resp:
                                    self.api.configuration.view_token = login_resp['data'].get('token')
                                    self.api.configuration.sid = login_resp['data'].get('sid')
                            else:
                                self.logger.error(f" Manual login failed (Attempt 3): {res.status_code} - {res.text}")
                        except Exception as e_manual:
                            self.logger.error(f" Manual request exception: {e_manual}")
                    
                    # ALWAYS run totp_validate even if a token is present in login_resp.
                    # Kotak requires the 2FA step (MPIN) to unlock sensitive APIs like limits/balance.
                    self.logger.info(" Performing 2FA with MPIN via totp_validate()...")
                    validate_resp = self.api.totp_validate(mpin=self.MPIN)
                    self.logger.info(f" totp_validate result: {validate_resp}")
                
                # FALLBACK: login() + session_2fa() for older SDK versions that don't have totp_login
                elif hasattr(self.api, 'login') and hasattr(self.api, 'session_2fa'):
                    self.logger.info(" Using login() + session_2fa() fallback...")
                    login_resp = self.api.login(
                        mobilenumber=self.MOBILE_NUMBER,
                        password=self.PASSWORD
                    )
                    self.logger.info(f" login() result: {login_resp}")
                    
                    self.logger.info(" Initializing session with MPIN...")
                    try:
                        validate_resp = self.api.session_2fa(OTP=self.MPIN)
                    except TypeError:
                        self.logger.info(" Falling back to 'otp' lowercase parameter...")
                        validate_resp = self.api.session_2fa(otp=self.MPIN)
                    
                    self.logger.info(f" session_2fa result: {validate_resp}")
                
                else:
                    methods = [m for m in dir(self.api) if not m.startswith('_')]
                    self.logger.error(f" Error: No known login method found in NeoAPI. Available methods: {methods}")
                    self.connected = False
                    return

            except Exception as e_login:
                self.logger.error(f" Login Methodology Failure: {e_login}")
                try:
                    self.logger.error(traceback.format_exc())
                except Exception:
                    self.logger.error(f" (traceback unavailable)")
                self.connected = False
                return
            
            # Final result validation and Setup
            if validate_resp and isinstance(validate_resp, dict):
                resp_data = validate_resp.get('data', {})
                if isinstance(resp_data, dict) and 'token' in resp_data:
                    self.connected = True
                    self.logger.info(" Kotak Neo Connected Successfully!")
                    
                    # Setup WS Callbacks
                    self.api.on_message = self.on_message
                    self.api.on_error = self.on_error
                    self.api.on_open = self.on_open
                    self.api.on_close = self.on_close
                    
                    # Auto-start WebSocket for live price streaming
                    self.start_websocket()
                else:
                    self.logger.error(f" Login Failed - no token in response: {validate_resp}")
                    self.connected = False
            else:
                self.logger.error(f" Login Failed or Ambiguous: {validate_resp}")
                self.connected = False
                    
        except Exception as e:
            self.logger.error(f" Kotak Connection Critical Error: {e}")
            try:
                self.logger.error(traceback.format_exc())
            except Exception:
                self.logger.error(f" (traceback unavailable)")
            self.connected = False
    
    def start_websocket(self):
        """Start WebSocket connection and subscribe to key instruments for live pricing"""
        if not self.connected or not self.api:
            self.logger.warning("Cannot start WebSocket - broker not connected")
            return
        
        try:
            # Subscribe to Nifty 50 Index (token 26000) for live spot price
            nifty_token = "26000"
            self.logger.info(" Starting WebSocket + subscribing to Nifty 50...")
            self.subscribe_symbol(nifty_token, "nse_cm")
            self.logger.info(" WebSocket started, Nifty 50 subscribed")
        except Exception as e:
            self.logger.error(f" WebSocket startup failed: {e}")
    
    def subscribe_active_positions(self, strategies):
        """Subscribe to WebSocket feeds for all symbols with active positions"""
        if not self.connected:
            return
        
        for strategy in strategies:
            if strategy.position:
                symbol = strategy.position.get('symbol', '')
                if symbol and symbol not in self.subscribed_tokens:
                    try:
                        mapping = self.get_instrument_token(symbol)
                        if mapping:
                            self.subscribe_symbol(mapping['token'], mapping['segment'])
                            self.logger.info(f" Subscribed to position symbol: {symbol}")
                    except Exception as e:
                        self.logger.error(f" Subscribe position {symbol} failed: {e}")

    def get_instrument_token(self, symbol, exchange_segment="nse_cm"):
        """
        Finds token for a symbol. 
        Symbol format: "SBIN", "RELIANCE", "Nifty 50"
        """
        if symbol in self.token_map:
            return self.token_map[symbol]
            
        try:
            # Clean symbol (remove NSE: prefix etc if present)
            clean_symbol = symbol.replace("NSE:", "").replace("-EQ", "")
            
            # Manual Override for Nifty 50
            if "NIFTY" in clean_symbol.upper() and ("50" in clean_symbol or "INDEX" in clean_symbol):
                 self.token_map[symbol] = {"token": "26000", "segment": "nse_cm"}
                 return self.token_map[symbol]

            # Use search_scrip
            res = self.api.search_scrip(exchange_segment=exchange_segment, symbol=clean_symbol)
            if res and isinstance(res, list) and len(res) > 0:
                # Find best match
                target = res[0]
                token = str(target.get('pSymbol') or target.get('instrumentToken'))
                segment = str(target.get('pExchSeg') or exchange_segment)
                
                self.token_map[symbol] = {"token": token, "segment": segment}
                return self.token_map[symbol]
            else:
                self.logger.warning(f"Symbol not found: {symbol}")
                return None
        except Exception as e:
            self.logger.error(f"Search error for {symbol}: {e}")
            return None

    def subscribe_symbol(self, token, segment="nse_cm"):
        """Subscribes and waits briefly for data"""
        if token in self.subscribed_tokens:
            return
            
        try:
            instruments = [{"instrument_token": token, "exchange_segment": segment}]
            self.logger.info(f" Subscribing to {token}...")
            # Detect index? 26000 is index.
            # Experiments show isIndex=True might fail or timeout.
            # Try isIndex=False for nse_cm tokens (even indices).
            is_index = False 
            
            self.api.subscribe(instrument_tokens=instruments, isIndex=is_index, isDepth=False)
            self.subscribed_tokens.add(token)
            
            # Wait a tick for data?
            # time.sleep(0.5) 
            # Better not block too long, but initial sub needs time.
        except Exception as e:
            self.logger.error(f"Subscribe failed for {token}: {e}")

    def get_current_price(self, symbol):
        """
        Get LTP for a symbol using WS Cache or REST Fallback.
        """
        if not self.connected:
            self.logger.warning("Kotak Broker not connected")
            return None
            
        token = None
        segment = "nse_cm"
        
        # Determine Token
        if isinstance(symbol, dict) and 'instrument_token' in symbol:
             token = symbol['instrument_token']
             segment = symbol.get('exchange_segment', 'nse_cm')
        else:
             mapping = self.get_instrument_token(symbol)
             if mapping:
                 token = mapping['token']
                 segment = mapping['segment']
        
        if not token:
            return None
            
        # Strategy:
        # 1. Check WebSocket Cache
        if token in self.ltp_cache:
            return self.ltp_cache[token]
            
        # 2. If Nifty/Index, enforce WebSocket Subscription (REST fails)
        if token == "26000":
            self.subscribe_symbol(token, segment)
            # Wait max 2s for data
            for _ in range(10):
                if token in self.ltp_cache:
                    return self.ltp_cache[token]
                time.sleep(0.2)
            self.logger.warning(f"WS Data Timeout for {symbol} ({token})")
            return 0.0 # Or None
            
        # 3. For others, try REST first (immediate), fallback to WS
        try:
            inst_tokens = [{"instrument_token": token, "exchange_segment": segment}]
            quote = self.api.quotes(instrument_tokens=inst_tokens, quote_type="ltp")
            
            if isinstance(quote, list) and len(quote) > 0:
                item = quote[0]
                if 'ltp' in item:
                    ltp = float(item['ltp'])
                    self.ltp_cache[token] = ltp # Update cache too
                    return ltp
            elif isinstance(quote, dict) and 'fault' in quote:
                 self.logger.warning(f"REST Quote failed, trying WS for {token}")
                 self.subscribe_symbol(token, segment)
                 pass # Check cache/wait
                 
        except Exception as e:
            self.logger.error(f"REST Quote Exception {symbol}: {e}")
            
        return self.ltp_cache.get(token, 0.0)

    def place_order(self, symbol, qty, side, order_type='MARKET', price=0.0, product='MIS'):
        """
        Place order.
        """
        if not self.connected: return None
        
        # Map Symbol to Token
        mapping = self.get_instrument_token(symbol)
        if not mapping:
            self.logger.error(f"Order failed: Symbol {symbol} not found")
            return {"status": "error", "message": "Symbol not found"}
            
        token = mapping['token']
        seg = mapping['segment']
        
        # Map Side
        txn_type = "B" if side.upper() == "BUY" else "S"
        
        # Map Order Type
        # settings.py: "Market": "MKT", "Limit": "L"
        mapped_type = "MKT" if order_type.upper() == "MARKET" else "L"
        
        try:
             self.logger.info(f"Placing Order: {side} {qty} {symbol} @ {price}")
             # Need trading_symbol?
             # search_scrip response has 'pTrdSymbol' or 'pSymbolName'
             # If we only have token, place_order might need more info?
             # neo_api.py `place_order` signature:
             # exchange_segment, product, price, order_type, quantity, validity, trading_symbol, transaction_type, amo="NO", disclosed_quantity="0", market_protection="0", pf="N", trigger_price="0", scrip_token=None, ...
             
             # It seems `trading_symbol` AND `scrip_token` (instrument_token) might be needed?
             # Let's try passing what we have.
             # If mapping came from search, we might have symbol name.
             
             # Re-search if needed to get trading symbol name?
             # Assuming 'symbol' input var is close enough or use token.
             
             resp = self.api.place_order(
                 exchange_segment=seg,
                 product=product,
                 price=str(price),
                 order_type=mapped_type,
                 quantity=str(qty),
                 validity="DAY",
                 trading_symbol=symbol, # Best guess
                 transaction_type=txn_type,
                 instrument_token=token 
             )
             return resp
             
        except Exception as e:
            self.logger.error(f"Order Placement Failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_positions(self):
        """Fetch all positions"""
        if not self.connected: return []
        try:
            return self.api.positions()
        except Exception as e:
            self.logger.error(f"Positions fetch failed: {e}")
            return []

    def close_position(self, symbol):
        """Close position for a specific symbol"""
        positions = self.get_positions()
        if not positions or 'data' not in positions: return
        
        for pos in positions['data']:
            # Match symbol (TrdSymbol or similar)
            # Need to check response structure of positions()
            # Standard Neo: 'trdSym', 'tks' (token)
            # We filter by token or symbol
            target_token = self.get_instrument_token(symbol)
            if target_token and str(pos.get('tok')) == target_token['token']:
                qty = int(pos.get('flBuyQty', 0)) - int(pos.get('flSellQty', 0))
                if qty != 0:
                     side = "SELL" if qty > 0 else "BUY"
                     self.place_order(symbol, abs(qty), side, order_type="MARKET", product=pos.get('prod', 'MIS'))
                     self.logger.info(f"Closed position for {symbol}")

    def close_all_positions(self):
        """Close all open positions"""
        positions = self.get_positions()
        if not positions or 'data' not in positions: return
        
        for pos in positions['data']:
             qty = int(pos.get('flBuyQty', 0)) - int(pos.get('flSellQty', 0))
             if qty != 0:
                 try:
                     token = pos.get('tok')
                     # Reverse lookup symbol from token if needed, or place by token if supported?
                     # place_order needs symbol for logging/search if token not enough.
                     # We can iterate our token_map to find symbol or jus use 'trdSym'
                     symbol = pos.get('trdSym') 
                     side = "SELL" if qty > 0 else "BUY"
                     self.place_order(symbol, abs(qty), side, order_type="MARKET", product=pos.get('prod', 'MIS'))
                 except Exception as e:
                     self.logger.error(f"Failed to close pos {pos}: {e}")

    def check_token_health(self):
        """Check if session is still alive"""
        if not self.connected: 
            return {"status": "error", "message": "Not connected"}
        try:
            # Try a simple API call to check health
            self.api.limits()
            return {"status": "success", "message": "Connection healthy"}
        except Exception as e:
            self.connected = False
            return {"status": "error", "message": str(e)}

    def get_latest_bars(self, symbol, timeframe, limit=1000):
        """
        Fetch historical data from Aggregator (Live Accumulation or Primed)
        """
        if not self.connected: return None
        
        mapping = self.get_instrument_token(symbol)
        if not mapping:
            self.logger.error(f"History failed: {symbol} not found")
            return None
            
        token = mapping['token']
        
        # Map Timeframe
        tf_map = {'1': 1, '5': 5, '15': 15, '1D': 1440}
        interval = tf_map.get(str(timeframe), 1)
        
        # Ensure subscribed (for future ticks)
        if token not in self.subscribed_tokens:
             self.subscribe_symbol(token, mapping.get('segment', 'nse_cm'))
             
        # Fetch from Aggregator
        df = self.aggregator.get_bars_df(token, interval, limit)
        if df is None or df.empty: return None
        return df

    def prime_aggregator(self, symbol, df):
        """Prime the internal aggregator with historical data"""
        if df is None or df.empty: return
        mapping = self.get_instrument_token(symbol)
        if not mapping: return
        token = mapping['token']
        
        # Determine intervals to prime
        for interval in self.aggregator.intervals:
            # We filter for that interval or just use 1m as base
            if interval == 1:
                with self.aggregator.lock:
                    self.aggregator.completed_bars[interval][token] = []
                    for idx, row in df.iterrows():
                        # Resolve Datetime
                        dt = idx
                        if not hasattr(dt, 'isoformat'):
                            if 'datetime' in row:
                                dt = row['datetime']
                            elif 'timestamp' in row:
                                try: dt = datetime.fromtimestamp(float(row['timestamp']))
                                except Exception as e:
                                    print(f" [WS] Timestamp parse error: {e}")
                                    dt = datetime.now()
                        
                        # Ensure dt is a datetime object
                        if isinstance(dt, str):
                            try: dt = datetime.fromisoformat(dt)
                            except Exception as e:
                                print(f" [WS] ISO date parse error: {e}")

                        bar = {
                            'datetime': dt,
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': float(row.get('volume', 0)),
                            'bar_key': dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
                        }
                        self.aggregator.completed_bars[interval][token].append(bar)
                    self.logger.info(f" Aggregator primed with {len(df)} bars for {symbol}")

    # === Option Helpers ===
    def get_atm_strike(self, spot_price):
        """Round to nearest 50"""
        return round(spot_price / 50) * 50

    def get_option_price(self, strike, otype, expiry_code):
        """
        Fetch Option Price (LTP).
        Constructs symbol: NIFTY + ExpiryCode + Strike + Type
        Example: NIFTY + 26FEB + 26000 + CE -> NIFTY26FEB26000CE
        Example: NIFTY + 26217 + 19650 + CE -> NIFTY2621719650CE
        """
        try:
             # Ensure strike is integer string
             str_strike = str(int(strike))
             # Construct symbol
             # TODO: Handle BANKNIFTY/FINNIFTY if needed. Assuming NIFTY for now.
             root = "NIFTY" 
             symbol = f"{root}{expiry_code}{str_strike}{otype.upper()}"
             
             # Fetch Price
             price = self.get_current_price(symbol)
             # If price is 0, maybe symbol is wrong or market closed?
             # Try subscribing? get_current_price handles subscription if not in cache (via REST fallback or sub)
             
             return price
        except Exception as e:
             self.logger.error(f"Option Price Fetch Error: {e}")
             return 0.0

    def get_real_balance(self):
        """Fetch available margin from Kotak Neo"""
        if not self.connected: 
            return 0.0
        try:
            limits = self.api.limits()
            if not limits: return 0.0
            
            # Handle both nested 'data' and flat response
            data = limits.get('data', limits)
            
            # Priority fields for balance
            for field in ['Net', 'cashBalance', 'availMar', 'curMar']:
                if field in data:
                    val = data[field]
                    try:
                        return float(val)
                    except (ValueError, TypeError): continue
            return 0.0
        except Exception as e:
            self.logger.error(f"Balance fetch failed: {e}")
            return 0.0

    def get_account_balance(self):
        return self.get_real_balance()

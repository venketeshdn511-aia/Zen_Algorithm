"""
Fyers Broker Implementation
Connects to Fyers API v3 for LIVE Nifty data and option chain
"""

from fyers_apiv3 import fyersModel
import pandas as pd
import os
import logging
from datetime import datetime, timedelta
import pyotp
import json
import base64
import time
import jwt

# Import auto-login module
try:
    from src.brokers import fyers_auto_login
except ImportError:
    import fyers_auto_login

class FyersBroker:
    def __init__(self, logger=None, db_handler=None):
        """
        Initialize Fyers broker connection
        
        Requires in .env:
        - FYERS_APP_ID
        - FYERS_SECRET_ID
        - FYERS_TOTP_SECRET (for auto PIN generation)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.db_handler = db_handler
        self.api = None
        self.connected = False
        self.access_token = None
        self.refresh_token = None
        self._last_prices = {}  # Cache for last successful prices to filter bad ticks
        
        # Nifty symbol on Fyers
        self.NIFTY_SYMBOL = "NSE:NIFTY50-INDEX"
        
        # NOTE: Do NOT connect automatically in __init__ to avoid blocking imports
        # self.connect()
    
    def _get_token_expiry(self, token):
        """Extract expiry from JWT access token"""
        try:
            # Decode without verification to access claims
            decoded = jwt.decode(token, options={"verify_signature": False})
            if 'exp' in decoded:
                return datetime.utcfromtimestamp(decoded['exp'])
        except Exception as e:
            self.logger.debug(f"Could not extract token expiry: {e}")
        return None

    def _send_token_expiry_alert(self, token_type, expiry, expired=False):
        """Log or alert on token expiry"""
        msg = f"Fyers {token_type} token {'EXPIRED' if expired else 'expiring soon'}: {expiry}"
        if expired:
            self.logger.error(msg)
        else:
            self.logger.warning(msg)

    def _refresh_access_token(self, app_id, refresh_token):
        """Attempt to refresh access token using refresh_token"""
        secret_id = os.getenv('FYERS_SECRET_ID')
        pin = os.getenv('FYERS_PIN')
        
        if not secret_id or not pin:
            self.logger.error("Cannot refresh token: Missing Secret ID or PIN")
            return None
            
        new_access_token, new_refresh_token = fyers_auto_login.refresh_access_token(
            refresh_token, app_id, secret_id, pin
        )
        
        if new_refresh_token:
            self.refresh_token = new_refresh_token
            # Update env for current session
            os.environ['FYERS_REFRESH_TOKEN'] = new_refresh_token
            # Persist refresh token to file so it survives restarts
            try:
                with open('.fyers_refresh_token', 'w') as f:
                    f.write(new_refresh_token)
                self.logger.info("Refresh token saved to .fyers_refresh_token")
            except Exception as e:
                self.logger.warning(f"Could not save refresh token to file: {e}")
            
        return new_access_token

    def connect(self):
        """Connect to Fyers API using credentials or saved token"""
        try:
            app_id = os.getenv('FYERS_APP_ID')
            if not app_id:
                self.logger.warning("FYERS_APP_ID not set")
                return
            
            # Standardize App ID suffix
            if len(app_id) == 10:
                app_id += "-100"
            
            # Priority 1: Check Environment/Config for Tokens
            self.logger.info(" Priority 1: Check Token Persistence")
            
            access_token = os.getenv('FYERS_ACCESS_TOKEN')
            refresh_token = os.getenv('FYERS_REFRESH_TOKEN')
            self.refresh_token = refresh_token
            
            # If no access token in env, try loading from file
            if not access_token and os.path.exists('.fyers_token'):
                with open('.fyers_token', 'r') as f:
                    access_token = f.read().strip()
            
            # If no refresh token in env, try loading from file
            if not refresh_token and os.path.exists('.fyers_refresh_token'):
                with open('.fyers_refresh_token', 'r') as f:
                    refresh_token = f.read().strip()
                    self.refresh_token = refresh_token
            
            # Case A: We have an access token, try it
            if access_token:
                self.access_token = access_token
                self.api = fyersModel.FyersModel(
                    client_id=app_id,
                    token=self.access_token,
                    log_path=""
                )
                
                try:
                    test_response = self.api.get_profile()
                    if test_response.get('s') == 'ok':
                        self.connected = True
                        self.logger.info(f" Connected to Fyers API (using existing token)")
                        return
                    else:
                        self.logger.warning(f" Access token invalid: {test_response}")
                except Exception as e:
                    self.logger.warning(f" Access token expired or error: {e}")

            # Case B: Access token failed or missing, but we have a refresh token
            if self.refresh_token:
                # Check if refresh token is expired before attempting refresh
                refresh_expiry = self._get_token_expiry(self.refresh_token)
                if refresh_expiry:
                    time_until_expiry = (refresh_expiry - datetime.utcnow()).total_seconds()
                    if time_until_expiry <= 0:
                        self.logger.error(" Refresh token has EXPIRED")
                        self.logger.error(f"   Expired on: {refresh_expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        self._send_token_expiry_alert("refresh", refresh_expiry, expired=True)
                        # Skip refresh attempt, go to next fallback
                    else:
                        days_until_expiry = time_until_expiry / 86400
                        self.logger.info(f" Refresh token valid for {days_until_expiry:.1f} more days")
                        
                        # Proactive alert if refresh token expires soon (< 2 days)
                        if days_until_expiry < 2:
                            self._send_token_expiry_alert("refresh", refresh_expiry, expired=False)
                        
                        self.logger.info(" Attempting token refresh using refresh_token...")
                        new_token = self._refresh_access_token(app_id, self.refresh_token)
                        if new_token:
                            self.access_token = new_token
                            self.api = fyersModel.FyersModel(
                                client_id=app_id,
                                token=self.access_token,
                                log_path=""
                            )
                            
                            # Verify the new token with retry logic
                            max_retries = 3
                            for attempt in range(max_retries):
                                try:
                                    test_response = self.api.get_profile()
                                    if test_response.get('s') == 'ok':
                                        self.connected = True
                                        self.logger.info(" Connected using refreshed token!")
                                        
                                        # Save the new access token to file
                                        try:
                                            with open('.fyers_token', 'w') as f:
                                                f.write(self.access_token)
                                        except Exception as e:
                                            self.logger.warning(f"Could not save token to file: {e}")
                                        
                                        # Save to environment
                                        os.environ['FYERS_ACCESS_TOKEN'] = self.access_token
                                        
                                        # Save to MongoDB with expiry metadata
                                        if self.db_handler and hasattr(self.db_handler, 'connected') and self.db_handler.connected:
                                            try:
                                                access_expiry = self._get_token_expiry(self.access_token)
                                                refresh_expiry = self._get_token_expiry(self.refresh_token)
                                                
                                                self.db_handler.db["system_config"].update_one(
                                                    {"_id": "fyers_session"},
                                                    {"$set": {
                                                        "access_token": self.access_token,
                                                        "refresh_token": self.refresh_token,
                                                        "access_token_expiry": access_expiry.isoformat() if access_expiry else None,
                                                        "refresh_token_expiry": refresh_expiry.isoformat() if refresh_expiry else None,
                                                        "updated_at": datetime.utcnow().isoformat(),
                                                        "last_refresh_success": datetime.utcnow().isoformat()
                                                    }},
                                                    upsert=True
                                                )
                                                self.logger.info(" Token saved to MongoDB with expiry tracking")
                                                
                                                # Log expiry info
                                                if access_expiry:
                                                    self.logger.info(f" Access token expires: {access_expiry.strftime('%Y-%m-%d %H:%M UTC')}")
                                                if refresh_expiry:
                                                    self.logger.info(f" Refresh token expires: {refresh_expiry.strftime('%Y-%m-%d %H:%M UTC')}")
                                            except Exception as e:
                                                self.logger.warning(f"Could not save token to MongoDB: {e}")
                                        
                                        return
                                    else:
                                        self.logger.warning(f" Token verification failed (attempt {attempt + 1}/{max_retries}): {test_response}")
                                        if attempt < max_retries - 1:
                                            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                                except Exception as e:
                                    self.logger.warning(f" Token verification error (attempt {attempt + 1}/{max_retries}): {e}")
                                    if attempt < max_retries - 1:
                                        time.sleep(2 ** attempt)
                                    else:
                                        self.logger.error(f" Token verification failed after {max_retries} attempts")
                        else:
                            self.logger.warning(" Refresh token API call failed")
                else:
                    self.logger.info(" Attempting token refresh using refresh_token... (No expiry check)")
                    new_token = self._refresh_access_token(app_id, self.refresh_token)
                    if new_token:
                        self.access_token = new_token
                        self.api = fyersModel.FyersModel(
                            client_id=app_id,
                            token=self.access_token,
                            log_path=""
                        )
                        
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                test_response = self.api.get_profile()
                                if test_response.get('s') == 'ok':
                                    self.connected = True
                                    self.logger.info(" Connected using refreshed token!")
                                    # Save logic (simplified)
                                    try:
                                        with open('.fyers_token', 'w') as f:
                                            f.write(self.access_token)
                                        os.environ['FYERS_ACCESS_TOKEN'] = self.access_token
                                    except Exception as e:
                                        self.logger.warning(f"Could not save refreshed token: {e}")
                                    return
                                else:
                                    if attempt < max_retries - 1: time.sleep(1)
                            except Exception as e:
                                self.logger.warning(f"Token verification error (attempt): {e}")
                                if attempt < max_retries - 1: time.sleep(1)
            
            # Priority 2: Try to load from MongoDB (Cloud Persistence)
            # NOTE: Priority 2 was previously re-reading .fyers_token which was already
            # tried in Priority 1. Skipping redundant file read.
            self.logger.info(" Priority 2: Check MongoDB Token")
            if not self.connected and self.db_handler and self.db_handler.connected:
                try:
                    conf = self.db_handler.db["system_config"].find_one({"_id": "fyers_session"})
                    if conf and conf.get('access_token'):
                        self.access_token = conf['access_token']
                        self.api = fyersModel.FyersModel(
                            client_id=app_id,
                            token=self.access_token,
                            log_path=""
                        )
                        test_response = self.api.get_profile()
                        if test_response.get('s') == 'ok':
                            self.connected = True
                            self.logger.info(" Connected using MongoDB token")
                            return
                except Exception as e:
                    self.logger.warning(f"MongoDB token load failed: {e}")
            
            # Priority 3: Full auto-login as final fallback
            if not self.connected:
                self.logger.info(" Priority 3: Attempting full auto-login...")
                try:
                    new_access_token, new_refresh_token = fyers_auto_login.auto_login()
                    if new_access_token:
                        self.access_token = new_access_token
                        self.refresh_token = new_refresh_token
                        self.api = fyersModel.FyersModel(
                            client_id=app_id,
                            token=self.access_token,
                            log_path=""
                        )
                        test_response = self.api.get_profile()
                        if test_response.get('s') == 'ok':
                            self.connected = True
                            self.logger.info(" Connected via auto-login!")
                            # Persist tokens
                            os.environ['FYERS_ACCESS_TOKEN'] = self.access_token
                            try:
                                with open('.fyers_token', 'w') as f:
                                    f.write(self.access_token)
                            except Exception:
                                pass
                            if new_refresh_token:
                                os.environ['FYERS_REFRESH_TOKEN'] = new_refresh_token
                                try:
                                    with open('.fyers_refresh_token', 'w') as f:
                                        f.write(new_refresh_token)
                                except Exception:
                                    pass
                            return
                        else:
                            self.logger.warning(f" Auto-login token verification failed: {test_response}")
                    else:
                        self.logger.warning(" Auto-login returned no token")
                except Exception as e:
                    self.logger.error(f" Auto-login failed: {e}")
                
                self.logger.error(" ALL CONNECTION METHODS FAILED. MANUAL LOGIN REQUIRED.")
                
        except Exception as e:
            self.logger.error(f"Fyers Connect Error: {e}")

    def get_current_price(self, symbol):
        """Get LATEST price for a symbol"""
        if not self.connected or not self.api:
            return None
            
        try:
            # Fyers quotes expects comma separated string
            data = {"symbols": symbol}
            response = self.api.quotes(data=data)
            
            if response.get('s') == 'ok' and 'd' in response:
                return response['d'][0]['v']['lp'] # Last Traded Price
            else:
                self.logger.warning(f"Quote failed for {symbol}: {response}")
                return None
        except Exception as e:
            self.logger.error(f"Get Price Error {symbol}: {e}")
            return None

    def get_history(self, symbol, resolution, range_from, range_to, cont_flag="1", date_format="0"):
        """
        Fetch historical data from Fyers
        range_from/to: epoch timestamp (if date_format=0) or yyyy-mm-dd (if date_format=1)
        """
        if not self.connected or not self.api:
            return None
            
        try:
            data = {
                "symbol": symbol,
                "resolution": str(resolution),
                "date_format": str(date_format),
                "range_from": str(range_from),
                "range_to": str(range_to),
                "cont_flag": cont_flag
            }
            
            response = self.api.history(data=data)
            
            if response.get('s') == 'ok':
                return response
            else:
                self.logger.warning(f"History fetch failed for {symbol}: {response}")
                return None
        except Exception as e:
            self.logger.error(f"History Error {symbol}: {e}")
            return None

    def get_latest_bars(self, symbol, timeframe='1', limit=100):
        """
        Get latest N bars for a symbol
        Calculates appropriate date range based on limit.
        """
        if not self.connected:
            return None
            
        try:
            # Calculate range
            # Assume 1 min bars for simplicity if timeframe is '1'
            # Convert timeframe to minutes roughly
            tf_map = {'1': 1, '5': 5, '15': 15, '30': 30, '60': 60, 'D': 375} # 375 mins in trading day
            minutes_per_candle = tf_map.get(str(timeframe), 1)
            
            # Add buffer for weekends/holidays (3x is safe)
            duration_minutes = limit * minutes_per_candle * 3
            
            to_date = int(time.time())
            from_date = to_date - (duration_minutes * 60)
            
            response = self.get_history(
                symbol=symbol, 
                resolution=timeframe, 
                range_from=from_date, 
                range_to=to_date
            )
            
            if response and 'candles' in response:
                candles = response['candles']
                # Fyers returns [timestamp, open, high, low, close, volume]
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # Convert timestamp from epoch to datetime
                # Handle timezone if needed (Fyers sends IST or UTC?)
                # Usually Fyers sends epoch in IST/Local
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
                df['datetime'] = df['timestamp'] # Alias
                
                # Sort and slice
                df = df.sort_values('timestamp')
                if len(df) > limit:
                    df = df.iloc[-limit:]
                
                return df
                
            return pd.DataFrame()
            
        except Exception as e:
            self.logger.error(f"Get Latest Bars Error {symbol}: {e}")
            return pd.DataFrame()

    def get_option_chain(self, strike, option_type, expiry_date):
        """
        Get option premium for a specific strike.
        Constructs symbol based on Nifty standard format.
        Format: NSE:NIFTY{yy}{M}{dd}{strike}{type} e.g. NSE:NIFTY24DEC27000CE
        Wait, Fyers format might be different for weekly?
        Paper broker uses: NSE:NIFTY{exp}{strike}{type}
        """
        try:
            # exp is usually formatted by caller (e.g. 24208 -> 24 Feb 08? No)
            # Fyers paper broker expects 'exp' to be prepared string like "24208" (YYMDD)
            # symbol = f"NSE:NIFTY{expiry_date}{strike}{option_type}"
            
            symbol = f"NSE:NIFTY{expiry_date}{strike}{option_type}"
            
            # Use quotes to get LTP
            price = self.get_current_price(symbol)
            return price
            
        except Exception as e:
            self.logger.error(f"Option Chain Error: {e}")
            return None

    def place_order(self, symbol, qty, side, order_type='MARKET', price=0.0, product='MIS', instrument=None):
        """
        Place real order on Fyers
        """
        if not self.connected or not self.api:
            return {"status": "error", "message": "Not connected"}
            
        try:
            # Map side
            # Fyers: 1 => Buy, -1 => Sell
            side_int = 1 if side.upper() == 'BUY' else -1
            
            # Map type
            # 1 => Limit, 2 => Market, 3 => Stop, 4 => Stop Limit
            type_int = 2
            if order_type.upper() == 'LIMIT':
                type_int = 1
            
            data = {
                "symbol": symbol,
                "qty": qty,
                "type": type_int,
                "side": side_int,
                "productType": "INTRADAY", # or MARGIN/CNC
                "limitPrice": price,
                "stopPrice": 0,
                "validity": "DAY",
                "disclosedQty": 0,
                "offlineOrder": False,
                "stopLoss": 0,
                "takeProfit": 0
            }
            
            response = self.api.place_order(data=data)
            
            if response.get('s') == 'ok':
                return {
                    "status": "success", 
                    "order_id": response.get('id'), 
                    "message": response.get('message')
                }
            else:
                return {
                    "status": "error", 
                    "message": response.get('message')
                }
                
        except Exception as e:
            self.logger.error(f"Place Order Error: {e}")
            return {"status": "error", "message": str(e)}

    def get_positions(self):
        """Get current positions"""
        if not self.connected or not self.api:
            return None
            
        try:
            response = self.api.positions()
            if response.get('s') == 'ok':
                return response.get('netPositions', [])
            return []
        except Exception as e:
            self.logger.error(f"Get Positions Error: {e}")
            return []

    def check_token_health(self):
        """Check if token is valid"""
        if not self.connected or not self.api:
            return {"status": "expired", "message": "Not connected"}
            
        try:
            response = self.api.get_profile()
            if response.get('s') == 'ok':
                return {"status": "active", "message": "Token valid"}
            else:
                return {"status": "expired", "message": response.get('message')}
        except Exception as e:
            return {"status": "error", "message": str(e)}
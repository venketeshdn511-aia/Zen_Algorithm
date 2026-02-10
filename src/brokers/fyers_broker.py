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
        self._last_prices = {}  # Cache for last successful prices to filter bad ticks
        
        # Nifty symbol on Fyers
        self.NIFTY_SYMBOL = "NSE:NIFTY50-INDEX"
        
        # NOTE: Do NOT connect automatically in __init__ to avoid blocking imports
        # self.connect()
    
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
            self.logger.info("👉 Priority 1: Check Token Persistence")
            
            access_token = os.getenv('FYERS_ACCESS_TOKEN')
            refresh_token = os.getenv('FYERS_REFRESH_TOKEN')
            
            # If no access token in env, try loading from file
            if not access_token and os.path.exists('.fyers_token'):
                with open('.fyers_token', 'r') as f:
                    access_token = f.read().strip()
            
            # If no refresh token in env, try loading from file
            if not refresh_token and os.path.exists('.fyers_refresh_token'):
                with open('.fyers_refresh_token', 'r') as f:
                    refresh_token = f.read().strip()
            
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
                        self.logger.info(f"✅ Connected to Fyers API (using existing token)")
                        return
                    else:
                        self.logger.warning(f"⚠️ Access token invalid: {test_response}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Access token expired or error: {e}")

            # Case B: Access token failed or missing, but we have a refresh token
            if refresh_token:
                # Check if refresh token is expired before attempting refresh
                refresh_expiry = self._get_token_expiry(refresh_token)
                if refresh_expiry:
                    time_until_expiry = (refresh_expiry - datetime.utcnow()).total_seconds()
                    if time_until_expiry <= 0:
                        self.logger.error("❌ Refresh token has EXPIRED")
                        self.logger.error(f"   Expired on: {refresh_expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        self._send_token_expiry_alert("refresh", refresh_expiry, expired=True)
                        # Skip refresh attempt, go to next fallback
                    else:
                        days_until_expiry = time_until_expiry / 86400
                        self.logger.info(f"🔄 Refresh token valid for {days_until_expiry:.1f} more days")
                        
                        # Proactive alert if refresh token expires soon (< 2 days)
                        if days_until_expiry < 2:
                            self._send_token_expiry_alert("refresh", refresh_expiry, expired=False)
                        
                        self.logger.info("🔄 Attempting token refresh using refresh_token...")
                        new_token = self._refresh_access_token(app_id, refresh_token)
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
                                        self.logger.info("✅ Connected using refreshed token!")
                                        
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
                                                refresh_expiry = self._get_token_expiry(refresh_token)
                                                
                                                self.db_handler.db["system_config"].update_one(
                                                    {"_id": "fyers_session"},
                                                    {"$set": {
                                                        "access_token": self.access_token,
                                                        "refresh_token": refresh_token,
                                                        "access_token_expiry": access_expiry.isoformat() if access_expiry else None,
                                                        "refresh_token_expiry": refresh_expiry.isoformat() if refresh_expiry else None,
                                                        "updated_at": datetime.utcnow().isoformat(),
                                                        "last_refresh_success": datetime.utcnow().isoformat()
                                                    }},
                                                    upsert=True
                                                )
                                                self.logger.info("☁️ Token saved to MongoDB with expiry tracking")
                                                
                                                # Log expiry info
                                                if access_expiry:
                                                    self.logger.info(f"📅 Access token expires: {access_expiry.strftime('%Y-%m-%d %H:%M UTC')}")
                                                if refresh_expiry:
                                                    self.logger.info(f"📅 Refresh token expires: {refresh_expiry.strftime('%Y-%m-%d %H:%M UTC')}")
                                            except Exception as e:
                                                self.logger.warning(f"Could not save token to MongoDB: {e}")
                                        
                                        return
                                    else:
                                        self.logger.warning(f"⚠️ Token verification failed (attempt {attempt + 1}/{max_retries}): {test_response}")
                                        if attempt < max_retries - 1:
                                            import time
                                            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                                except Exception as e:
                                    self.logger.warning(f"⚠️ Token verification error (attempt {attempt + 1}/{max_retries}): {e}")
                                    if attempt < max_retries - 1:
                                        import time
                                        time.sleep(2 ** attempt)
                                    else:
                                        self.logger.error(f"❌ Token verification failed after {max_retries} attempts")
                        else:
                            self.logger.warning("⚠️ Refresh token API call failed")
                else:
                    self.logger.info("🔄 Attempting token refresh using refresh_token...")
                    new_token = self._refresh_access_token(app_id, refresh_token)
                    if new_token:
                        # Same logic as above but without expiry checks
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
                                    self.logger.info("✅ Connected using refreshed token!")
                                    
                                    try:
                                        with open('.fyers_token', 'w') as f:
                                            f.write(self.access_token)
                                    except Exception as e:
                                        self.logger.warning(f"Could not save token to file: {e}")
                                    
                                    os.environ['FYERS_ACCESS_TOKEN'] = self.access_token
                                    
                                    if self.db_handler and hasattr(self.db_handler, 'connected') and self.db_handler.connected:
                                        try:
                                            self.db_handler.db["system_config"].update_one(
                                                {"_id": "fyers_session"},
                                                {"$set": {
                                                    "access_token": self.access_token,
                                                    "refresh_token": refresh_token,
                                                    "updated_at": datetime.utcnow().isoformat()
                                                }},
                                                upsert=True
                                            )
                                            self.logger.info("☁️ Token saved to MongoDB")
                                        except Exception as e:
                                            self.logger.warning(f"Could not save token to MongoDB: {e}")
                                    
                                    return
                                else:
                                    self.logger.warning(f"⚠️ Token verification failed (attempt {attempt + 1}/{max_retries}): {test_response}")
                                    if attempt < max_retries - 1:
                                        import time
                                        time.sleep(2 ** attempt)
                            except Exception as e:
                                self.logger.warning(f"⚠️ Token verification error (attempt {attempt + 1}/{max_retries}): {e}")
                                if attempt < max_retries - 1:
                                    import time
                                    time.sleep(2 ** attempt)
                                else:
                                    self.logger.error(f"❌ Token verification failed after {max_retries} attempts")
                    else:
                        self.logger.warning("⚠️ Refresh token API call failed")
            
            # Priority 2: Try to load saved token file
            self.logger.info("👉 Priority 2: Check Local Token File")
            if os.path.exists('.fyers_token'):
                with open('.fyers_token', 'r') as f:
                    self.access_token = f.read().strip()
                
                self.api = fyersModel.FyersModel(
                    client_id=app_id,
                    token=self.access_token,
                    log_path=""
                )
                
                # Verify token validity
                try:
                    test_response = self.api.get_profile()
                    if test_response.get('s') == 'ok':
                        self.connected = True
                        self.logger.info(f"✅ Connected to Fyers API (using saved token)")
                        return
                except:
                    self.logger.warning("Saved token expired or invalid")
            
            # Priority 3: Try to load from MongoDB (Cloud Persistence)
            self.logger.info("👉 Priority 3: Check MongoDB Token")
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
                            self.logger.info("✅ Connected using MongoDB token")
                            return
                except: pass
            
            # Priority 4: Try TOTP Auto-Login (Zero-Touch Authentication)
            # DISABLED ON RENDER: Cloudflare blocks automated login attempts
            if not self.connected:
                # Check if running on Render (cloud environment)
                is_render = os.getenv('RENDER') is not None
                
                if is_render:
                    self.logger.error("❌ Authentication failed on Render")
                    self.logger.error("⚠️ TOTP auto-login is disabled on Render to prevent Cloudflare rate limiting")
                    self.logger.error("📋 Action required: Regenerate tokens manually and update environment variables")
                    self.logger.error("   1. Run locally: python fyers_auth.py")
                    self.logger.error("   2. Copy FYERS_ACCESS_TOKEN and FYERS_REFRESH_TOKEN")
                    self.logger.error("   3. Update on Render Dashboard → Environment tab")
                    
                    # Send Telegram alert
                    try:
                        import requests
                        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                        chat_id = os.getenv('TELEGRAM_CHAT_ID')
                        if bot_token and chat_id:
                            msg = (
                                "🚨 <b>CRITICAL: Fyers Authentication Failed on Render</b>\n\n"
                                "❌ All token refresh attempts failed\n"
                                "⚠️ TOTP auto-login disabled (prevents Cloudflare bans)\n\n"
                                "<b>Action Required:</b>\n"
                                "1. Run <code>python fyers_auth.py</code> locally\n"
                                "2. Copy new tokens to Render environment variables\n\n"
                                "Bot will retry connection automatically once tokens are updated."
                            )
                            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
                            self.logger.info("📱 Telegram alert sent")
                    except Exception as e:
                        self.logger.warning(f"Could not send Telegram alert: {e}")
                else:
                    # Local environment: TOTP auto-login is allowed
                    self.logger.info("👉 Priority 4: Attempting TOTP Auto-Login (Zero-Touch Config)")
                    self.logger.info("🔐 All previous methods failed. Initializing Auto-Login protocol...")
                    try:
                        from src.brokers.fyers_auto_login import validate_and_refresh_token
                        is_valid, new_token = validate_and_refresh_token(self.db_handler)
                        
                        if is_valid and new_token:
                            self.access_token = new_token
                            self.api = fyersModel.FyersModel(
                                client_id=app_id,
                                token=self.access_token,
                                log_path=""
                            )
                            self.connected = True
                            self.logger.info("✅ Connected using TOTP auto-login!")
                            return
                        else:
                            self.logger.warning("❌ TOTP auto-login failed. Manual intervention required.")
                    except ImportError as e:
                        self.logger.warning(f"Auto-login module not available: {e}")
                    except Exception as e:
                        self.logger.error(f"TOTP auto-login error: {e}")
        
        except Exception as e:
            self.logger.error(f"Fyers connection error: {e}")
    
    def _refresh_access_token(self, app_id, refresh_token):
        """
        Use refresh_token to get a new access_token
        This avoids the need for manual re-authentication
        """
        try:
            import requests
            import time
            
            secret_id = os.getenv('FYERS_SECRET_ID')
            if not secret_id:
                self.logger.error("FYERS_SECRET_ID required for token refresh")
                return None
            
            # Fyers token refresh API
            url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
            
            # Add User-Agent to appear more legitimate
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
            
            # Create hash for API
            import hashlib
            app_id_hash = hashlib.sha256(f"{app_id}:{secret_id}".encode()).hexdigest()
            
            payload = {
                "grant_type": "refresh_token",
                "appIdHash": app_id_hash,
                "refresh_token": refresh_token,
                "pin": os.getenv('FYERS_PIN', '')  # Optional PIN
            }
            
            # Add delay to avoid rate limiting (2 seconds)
            time.sleep(2)
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            # Check if response is JSON (not Cloudflare HTML)
            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                # Cloudflare returned HTML (rate limiting or error page)
                if "cloudflare" in response.text.lower() or "error 1015" in response.text.lower():
                    self.logger.error("❌ Cloudflare rate limiting detected on token refresh API")
                    self.logger.error("⚠️ This usually means too many requests from this IP address")
                else:
                    self.logger.error(f"❌ Non-JSON response from Fyers API: {response.text[:200]}")
                return None
            
            if data.get('s') == 'ok' and data.get('access_token'):
                self.logger.info("✅ Token refreshed successfully!")
                return data['access_token']
            else:
                self.logger.error(f"Token refresh failed: {data}")
                return None
                
        except requests.exceptions.Timeout:
            self.logger.error("Token refresh timeout - API took too long to respond")
            return None
        except Exception as e:
            self.logger.error(f"Token refresh error: {e}")
            return None
    
    def _get_token_expiry(self, token):
        """
        Decode JWT token and extract expiry timestamp
        
        Args:
            token: JWT token string
            
        Returns:
            datetime object of expiry time (UTC) or None if cannot decode
        """
        try:
            # JWT tokens have 3 parts separated by '.'
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # Decode the payload (second part)
            payload = parts[1]
            
            # Add padding if needed (JWT base64 doesn't use padding)
            padding = len(payload) % 4
            if padding:
                payload += '=' * (4 - padding)
            
            # Decode base64
            decoded = base64.urlsafe_b64decode(payload)
            payload_data = json.loads(decoded)
            
            # Extract 'exp' field (expiry timestamp in seconds since epoch)
            exp_timestamp = payload_data.get('exp')
            if exp_timestamp:
                return datetime.utcfromtimestamp(exp_timestamp)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Could not decode token expiry: {e}")
            return None
    
    def _send_token_expiry_alert(self, token_type, expiry_time, expired=False):
        """
        Send Telegram alert about token expiry
        
        Args:
            token_type: 'access' or 'refresh'
            expiry_time: datetime object of expiry
            expired: True if already expired, False if warning
        """
        try:
            import requests
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            
            if not bot_token or not chat_id:
                return
            
            if expired:
                emoji = "🚨"
                status = "EXPIRED"
                action = (
                    "<b>Action Required NOW:</b>\n"
                    "1. Run <code>python fyers_auth.py</code> locally\n"
                    "2. Copy new tokens\n"
                    "3. Update Render environment variables\n"
                    "4. Restart Render service"
                )
            else:
                emoji = "⚠️"
                status = "EXPIRING SOON"
                time_left = expiry_time - datetime.utcnow()
                days_left = time_left.total_seconds() / 86400
                action = (
                    f"<b>Time remaining:</b> {days_left:.1f} days\n\n"
                    "<b>Action Required:</b>\n"
                    "1. Run <code>python fyers_auth.py</code> locally\n"
                    "2. Copy new tokens\n"
                    "3. Update Render environment variables\n"
                    "4. Restart Render service\n\n"
                    "Do this before the token expires to avoid downtime."
                )
            
            msg = (
                f"{emoji} <b>Fyers {token_type.upper()} Token {status}</b>\n\n"
                f"<b>Expiry:</b> {expiry_time.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"{action}"
            )
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
            self.logger.info(f"📱 Token expiry alert sent for {token_type} token")
            
        except Exception as e:
            self.logger.warning(f"Could not send token expiry alert: {e}")
    
    def check_token_health(self):
        """
        Check health of current tokens and send proactive alerts
        Call this periodically (e.g., daily) to monitor token status
        
        Returns:
            dict with token health status
        """
        health = {
            "access_token_valid": False,
            "refresh_token_valid": False,
            "access_token_expiry": None,
            "refresh_token_expiry": None,
            "warnings": []
        }
        
        try:
            access_token = os.getenv('FYERS_ACCESS_TOKEN')
            refresh_token = os.getenv('FYERS_REFRESH_TOKEN')
            
            # Check access token
            if access_token:
                access_expiry = self._get_token_expiry(access_token)
                if access_expiry:
                    health["access_token_expiry"] = access_expiry.isoformat()
                    time_until_expiry = (access_expiry - datetime.utcnow()).total_seconds()
                    
                    if time_until_expiry > 0:
                        health["access_token_valid"] = True
                        hours_left = time_until_expiry / 3600
                        
                        # Access tokens expire in ~24 hours, warn if < 2 hours left
                        if hours_left < 2:
                            warning = f"Access token expires in {hours_left:.1f} hours"
                            health["warnings"].append(warning)
                            self.logger.warning(f"⚠️ {warning}")
                    else:
                        health["warnings"].append("Access token has expired")
            
            # Check refresh token
            if refresh_token:
                refresh_expiry = self._get_token_expiry(refresh_token)
                if refresh_expiry:
                    health["refresh_token_expiry"] = refresh_expiry.isoformat()
                    time_until_expiry = (refresh_expiry - datetime.utcnow()).total_seconds()
                    
                    if time_until_expiry > 0:
                        health["refresh_token_valid"] = True
                        days_left = time_until_expiry / 86400
                        
                        # Refresh tokens expire in 15 days, warn if < 2 days left
                        if days_left < 2:
                            warning = f"Refresh token expires in {days_left:.1f} days - ACTION REQUIRED"
                            health["warnings"].append(warning)
                            self.logger.warning(f"🚨 {warning}")
                            self._send_token_expiry_alert("refresh", refresh_expiry, expired=False)
                    else:
                        health["warnings"].append("Refresh token has EXPIRED - IMMEDIATE ACTION REQUIRED")
                        self._send_token_expiry_alert("refresh", refresh_expiry, expired=True)
            
            # Save health check to MongoDB
            if self.db_handler and hasattr(self.db_handler, 'connected') and self.db_handler.connected:
                try:
                    self.db_handler.db["system_config"].update_one(
                        {"_id": "fyers_token_health"},
                        {"$set": {
                            **health,
                            "last_check": datetime.utcnow().isoformat()
                        }},
                        upsert=True
                    )
                except Exception as e:
                    self.logger.debug(f"Could not save token health to MongoDB: {e}")
            
            return health
            
        except Exception as e:
            self.logger.error(f"Token health check error: {e}")
            return health
    
    def get_current_price(self, symbol, last_known_price=None):
        """
        Get LIVE price for ANY symbol with BAD TICK protection.
        
        Args:
            symbol: Symbol string (e.g. "NSE:NIFTY50-INDEX" or "NSE:NIFTY26JAN...CE")
            last_known_price: Optional. Used to reject bad ticks (>30% deviation).
            
        Returns: Current LTP (float) or None if fetch failed or bad tick detected.
        """
        if not self.connected:
            self.logger.warning(f"⚠️ get_current_price: Not connected")
            return None  # CRITICAL: Return None, not 0.0
        
        try:
            target_symbol = symbol
            if symbol == 'NIFTY':
                target_symbol = self.NIFTY_SYMBOL
                
            data = {"symbols": target_symbol}
            response = self.api.quotes(data)
            
            if response and response.get('s') == 'ok':
                d = response.get('d', [])
                if d:
                    quote = d[0]
                    v = quote.get('v', {})
                    ltp = v.get('lp') or v.get('ltp')
                    
                    if ltp:
                        price = float(ltp)
                        
                        # BAD TICK FILTER 1: Zero or Negative
                        if price <= 0:
                            self.logger.warning(f"🚨 BAD TICK: {target_symbol} returned price {price}")
                            return None
                        
                        # BAD TICK FILTER 2: >30% deviation from last known
                        if last_known_price and last_known_price > 0:
                            deviation = abs(price - last_known_price) / last_known_price
                            
                            
                            # Relax threshold for Options (CE/PE symbols)
                            # Increase to 1000% (10.0) as entry-based validation can be very wide
                            threshold = 0.30
                            if "CE" in target_symbol or "PE" in target_symbol:
                                threshold = 10.0  # 1000% threshold for options
                                
                            if deviation > threshold:
                                self.logger.warning(f"🚨 BAD TICK: {target_symbol} price {price} deviates {deviation*100:.1f}% from {last_known_price}")
                                return None
                            
                        # Store last valid price
                        self._last_prices[target_symbol] = price
                        return price
            
            self.logger.warning(f"⚠️ Could not fetch price for {target_symbol}: {response}")
            
        except Exception as e:
            self.logger.error(f"Price fetch error for {symbol}: {e}")
        
        return None  # CRITICAL: Return None on any failure

    
    def get_latest_bars(self, symbol, timeframe='1', limit=100):
        """
        Get historical OHLC data from Fyers
        
        Args:
            symbol: 'NIFTY'
            timeframe: '1' (1min), '5' (5min), '15' (15min)
            limit: Number of candles
        
        Returns: DataFrame with OHLC data
        """
        if not self.connected:
            return pd.DataFrame()
        
        try:
            # Fyers timeframe format
            tf_map = {
                '1': '1',
                '1m': '1',
                '1Min': '1',
                '5': '5',
                '5m': '5',
                '5Min': '5',
                '15': '15',
                '15m': '15',
                '15Min': '15'
            }
            
            fyers_tf = tf_map.get(timeframe, '1')
            
            # Calculate date range
            from datetime import timedelta
            end_date = datetime.now()
            
            # For 1m: max 7 days, 5m: max 60 days
            if fyers_tf == '1':
                days_back = 7
            else:
                days_back = 60
            
            start_date = end_date - timedelta(days=days_back)
            
            # Fetch historical data
            data = {
                "symbol": self.NIFTY_SYMBOL,
                "resolution": fyers_tf,
                "date_format": "1",  # Unix timestamp
                "range_from": start_date.strftime("%Y-%m-%d"),
                "range_to": end_date.strftime("%Y-%m-%d"),
                "cont_flag": "1"
            }
            
            response = self.api.history(data)
            
            if response and response['s'] == 'ok':
                candles = response['candles']
                
                # Convert to DataFrame
                df = pd.DataFrame(candles, columns=['datetime', 'Open', 'High', 'Low', 'Close', 'Volume'])
                
                # Convert timestamp to datetime
                df['datetime'] = pd.to_datetime(df['datetime'], unit='s')
                df.set_index('datetime', inplace=True)
                
                # Return last 'limit' bars
                return df.tail(limit)
            
        except Exception as e:
            self.logger.error(f"Historical data error: {e}")
        
        return pd.DataFrame()
    
    def get_option_chain(self, strike, option_type, expiry_date=None):
        """
        Get REAL Nifty option premium from Fyers
        
        Args:
            strike: Option strike (e.g., 21450)
            option_type: 'CE' or 'PE'
            expiry_date: Expiry date (various formats supported)
        
        Returns: Option premium (LTP) in ₹
        """
        if not self.connected:
            return None
        
        # Try multiple symbol formats (Fyers can use both NFO and NSE)
        # NSE works better for NIFTY options based on testing
        exchanges = ["NSE", "NFO"]
        
        # Get current date for dynamic expiry calculation
        from datetime import datetime, timedelta
        now = datetime.now()
        
        # Build list of expiry formats to try
        expiry_formats = []
        if expiry_date:
            expiry_formats.append(expiry_date)
        
        day = now.day
        month = now.month
        year = now.year % 100  # 2-digit year
        
        # NIFTY weekly expiry is usually Thursday, but can shift due to holidays
        # Try dates starting from today going forward, then backwards
        
        # Format: YYMDD (single digit month) - confirmed working format
        # Order: today, +1, +2, ... +7, -1, -2, -3 (prioritize upcoming expiry)
        day_offsets = list(range(0, 8)) + list(range(-1, -4, -1))
        
        for day_offset in day_offsets:
            check_date = now + timedelta(days=day_offset)
            exp_day = check_date.day
            exp_month = check_date.month
            exp_year = check_date.year % 100
            
            # Primary format: YYMDD (e.g., 26113 for Jan 13)
            m_code = str(exp_month)
            if exp_month == 10: m_code = "O"
            elif exp_month == 11: m_code = "N"
            elif exp_month == 12: m_code = "D"
            
            expiry_formats.append(f"{exp_year}{m_code}{exp_day:02d}")
            
            # Alternate format: YYMMDD (some systems uses 260113)
            expiry_formats.append(f"{exp_year}{exp_month:02d}{exp_day:02d}")
        
        # Also try monthly expiry: YYMON (e.g., 26JAN)
        month_codes = ['', 'JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 
                       'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        monthly_expiry = f"{year}{month_codes[month]}"
        expiry_formats.append(monthly_expiry)
        
        # Remove duplicates while preserving order
        expiry_formats = list(dict.fromkeys(expiry_formats))
        
        self.logger.debug(f"Trying expiry formats: {expiry_formats}")
        
        for exchange in exchanges:
            for exp in expiry_formats:
                try:
                    # Construct Fyers option symbol
                    option_symbol = f"{exchange}:NIFTY{exp}{strike}{option_type}"
                    
                    # Get quote
                    data = {
                        "symbols": option_symbol
                    }
                    
                    response = self.api.quotes(data)
                    
                    if response and response.get('s') == 'ok':
                        quote_data = response.get('d', [])
                        if quote_data and len(quote_data) > 0:
                            quote = quote_data[0]
                            v = quote.get('v', {})
                            
                            # Try multiple price fields
                            ltp = v.get('lp') or v.get('last_price') or v.get('ltp') or v.get('close')
                            
                            if ltp and float(ltp) > 0:
                                self.logger.debug(f"✅ Fyers option {option_symbol}: ₹{ltp}")
                                return float(ltp)
                            else:
                                # Market might be closed - use previous close
                                prev_close = v.get('prev_close_price') or v.get('close') or v.get('pc')
                                if prev_close and float(prev_close) > 0:
                                    self.logger.debug(f"📊 Using prev close for {option_symbol}: ₹{prev_close}")
                                    return float(prev_close)
                    
                except Exception as e:
                    # Silently continue to next format
                    continue
        
        # Log only once if all attempts failed
        self.logger.warning(f"⚠️ Could not fetch option price for strike {strike} {option_type} (market may be closed)")
        return None
    
    def submit_order(self, symbol, qty, side, order_type='MARKET'):
        """
        Submit order to Fyers (LIVE TRADING)
        
        For paper trading, use FyersPaperBroker instead
        """
        self.logger.warning("Live order execution not implemented - use paper trading")
        return None
    
    def get_account_balance(self):
        """Get account balance from Fyers"""
        if not self.connected:
            return 0.0
        
        try:
            response = self.api.funds()
            
            if response and response['s'] == 'ok':
                # Return available balance
                balance = response['fund_limit'][0]['equityAmount']
                return float(balance)
            
        except Exception as e:
            self.logger.error(f"Balance fetch error: {e}")
        
        return 0.0
    
    def close_all_positions(self):
        """Close all open positions"""
        self.logger.info("Close all positions - not implemented (use paper trading)")
        pass
    
    def get_atm_option(self, symbol, signal_type):
        """Get ATM option symbol"""
        # For compatibility with existing code
        spot_price = self.get_current_price(symbol)
        atm_strike = round(spot_price / 50) * 50
        
        option_type = 'CE' if signal_type == 'buy' else 'PE'
        
        return f"NIFTY_{atm_strike}_{option_type}"

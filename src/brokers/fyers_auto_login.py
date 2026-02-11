"""
Fyers Auto-Login Module
Automatically generates access tokens using TOTP for zero-touch authentication.

Required Environment Variables:
- FYERS_APP_ID: Your Fyers App ID (e.g., "XXXXXXX-100")
- FYERS_SECRET_ID: Your Fyers Secret Key
- FYERS_USERNAME: Your Fyers Client ID (e.g., "AB12345")
- FYERS_PIN: Your 4-digit PIN
- FYERS_TOTP_SECRET: Your TOTP secret key from Fyers 2FA setup

Note: First-time use requires manual browser authorization to grant app permissions.
After that, this module handles daily token regeneration automatically.
"""

import os
import re
import json
import hashlib
import base64
import logging
import requests
import pyotp
from urllib.parse import urlparse, parse_qs
from datetime import datetime

logger = logging.getLogger("FyersAutoLogin")

# Fyers API Endpoints
API_BASE = "https://api-t2.fyers.in/vagator/v2"
TOKEN_API = "https://api-t1.fyers.in/api/v3/token"

def generate_totp(secret):
    """Generate TOTP code from secret"""
    try:
        totp = pyotp.TOTP(secret)
        return totp.now()
    except Exception as e:
        logger.error(f"TOTP generation failed: {e}")
        return None

def send_login_otp(username, app_id):
    """
    Step 1: Send login OTP request to Fyers
    Returns request_key for next steps
    """
    try:
        url = f"{API_BASE}/send_login_otp_v2"
        
        # Encode fy_id as base64 (required by Fyers API)
        fy_id_encoded = base64.b64encode(username.encode()).decode()
        
        payload = {
            "fy_id": fy_id_encoded,
            "app_id": "2"  # Fyers internal app identifier
        }
        
        response = requests.post(url, json=payload, timeout=30)
        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.error(f" send_login_otp failed (Non-JSON response): {response.text}")
            return None
        
        if data.get('s') == 'ok':
            request_key = data.get('request_key')
            logger.info(" Login OTP sent successfully")
            return request_key
        else:
            logger.error(f" send_login_otp failed: {data}")
            return None
            
    except Exception as e:
        logger.error(f" send_login_otp error: {e}")
        return None

def verify_pin(request_key, pin):
    """
    Step 3: Verify PIN (after TOTP)
    Returns access_token after successful verification
    """
    try:
        url = f"{API_BASE}/verify_pin_v2"
        
        # Try initial attempt (some servers expect plain, some expect hash)
        payload = {
            "request_key": request_key,
            "identity_type": "pin",
            "identifier": str(pin)
        }
        
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        
        if data.get('s') == 'ok':
            access_token = data.get('data', {}).get('access_token')
            logger.info(" PIN verified successfully (plain)")
            return access_token
        
        # If failed due to Invalid PIN, try hashed PIN
        if data.get('code') == -1006 or "Invalid PIN" in data.get('message', ''):
            logger.info(" Retrying PIN verification with hashed PIN...")
            payload["identifier"] = hashlib.sha256(str(pin).encode()).hexdigest()
            
            response = requests.post(url, json=payload, timeout=30)
            data = response.json()
            
            if data.get('s') == 'ok':
                access_token = data.get('data', {}).get('access_token')
                logger.info(" PIN verified successfully (hashed)")
                return access_token
        
        logger.error(f" verify_pin failed: {data}")
        return None
            
    except Exception as e:
        logger.error(f" verify_pin error: {e}")
        return None

def verify_totp(request_key, totp_code):
    """
    Step 2: Verify TOTP code
    Returns new request_key for PIN verification
    """
    try:
        url = f"{API_BASE}/verify_otp"
        
        payload = {
            "request_key": request_key,
            "otp": totp_code
        }
        
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        
        if data.get('s') == 'ok':
            new_request_key = data.get('request_key')
            logger.info(" TOTP verified successfully")
            return new_request_key
        else:
            logger.error(f" verify_totp failed: {data}")
            return None
            
    except Exception as e:
        logger.error(f" verify_totp error: {e}")
        return None

def get_auth_code(access_token, app_id, redirect_uri, secret_id):
    """
    Step 4: Exchange access token for auth code
    """
    try:
        url = f"{API_BASE}/token"
        
        # Create URL-encoded hash
        app_hash = hashlib.sha256(f"{app_id}:{secret_id}".encode()).hexdigest()
        
        payload = {
            "fyers_id_token": access_token,
            "app_id": app_id[:-4],  # Remove "-100" suffix
            "redirect_uri": redirect_uri,
            "appType": "100",
            "code_challenge": "",
            "state": "sample_state",
            "scope": "",
            "nonce": "",
            "response_type": "code",
            "create_cookie": True
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        data = response.json()
        
        if data.get('s') == 'ok' or 'Url' in data:
            # Extract auth code from redirect URL
            auth_url = data.get('Url', '')
            if auth_url:
                parsed = urlparse(auth_url)
                params = parse_qs(parsed.query)
                auth_code = params.get('auth_code', [None])[0]
                if auth_code:
                    logger.info(" Auth code obtained successfully")
                    return auth_code
        
        logger.error(f" get_auth_code failed: {data}")
        return None
            
    except Exception as e:
        logger.error(f" get_auth_code error: {e}")
        return None

def generate_access_token(auth_code, app_id, secret_id, redirect_uri):
    """
    Step 5: Exchange auth code for final access token
    """
    try:
        from fyers_apiv3 import fyersModel
        
        session = fyersModel.SessionModel(
            client_id=app_id,
            secret_key=secret_id,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )
        
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response.get('s') == 'ok' or response.get('code') == 200:
            access_token = response.get('access_token')
            refresh_token = response.get('refresh_token', '')
            logger.info(" Final access token generated successfully!")
            return access_token, refresh_token
        else:
            logger.error(f" generate_access_token failed: {response}")
            return None, None
            
    except Exception as e:
        logger.error(f" generate_access_token error: {e}")
        return None, None

def refresh_access_token(refresh_token, app_id, secret_id, pin):
    """
    Use refresh token to get a new access token.
    Refresh tokens are valid for 15 days and can generate new access tokens.
    Uses direct REST API call as it's more reliable for v3 refresh.
    """
    try:
        import time
        
        url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
        
        # Standardize App ID for hashing
        app_id_clean = app_id.replace("-100", "")
        app_id_hash = hashlib.sha256(f"{app_id_clean}:{secret_id}".encode()).hexdigest()
        
        # Add User-Agent to appear more legitimate
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        payload = {
            "grant_type": "refresh_token",
            "appIdHash": app_id_hash,
            "refresh_token": refresh_token,
            "pin": str(pin) # Fyers v3 API takes plain PIN here or hash? 
                            # Research says plain for this specific endpoint.
        }
        
        # Add delay to avoid rate limiting
        time.sleep(2)
        
        logger.info(f" Requesting new access token via refresh_token...")
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response_data = response.json()
        except requests.exceptions.JSONDecodeError:
            # Cloudflare returned HTML instead of JSON
            if "cloudflare" in response.text.lower() or "error 1015" in response.text.lower():
                logger.error(" Cloudflare rate limiting detected")
                logger.error(" Too many requests from this IP address")
            else:
                logger.error(f" Non-JSON response: {response.text[:200]}")
            return None, None
        
        if response_data.get('s') == 'ok':
            new_access_token = response_data.get('access_token')
            new_refresh_token = response_data.get('refresh_token', refresh_token)
            logger.info(" Token refreshed successfully!")
            return new_access_token, new_refresh_token
        
        # Fallback: Try hashed PIN if plain failed
        logger.info(" Retrying refresh with hashed PIN...")
        payload["pin"] = hashlib.sha256(str(pin).encode()).hexdigest()
        
        time.sleep(2)  # Add delay before retry
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response_data = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error(" Non-JSON response on retry")
            return None, None
        
        if response_data.get('s') == 'ok':
            new_access_token = response_data.get('access_token')
            new_refresh_token = response_data.get('refresh_token', refresh_token)
            logger.info(" Token refreshed successfully using hashed PIN!")
            return new_access_token, new_refresh_token
        else:
            logger.warning(f" Refresh failed: {response_data.get('message', 'Unknown error')}")
            return None, None

            
    except Exception as e:
        logger.error(f" Refresh token error: {e}")
        return None, None


def auto_login():
    """
    Complete automated login flow
    Returns (access_token, refresh_token) or (None, None) on failure
    """
    # Load credentials from environment
    username = (os.getenv('FYERS_USERNAME') or os.getenv('FYERS_CLIENT_ID') or "").strip()
    pin = (os.getenv('FYERS_PIN') or "").strip()
    totp_secret = (os.getenv('FYERS_TOTP_SECRET') or "").strip()
    app_id = (os.getenv('FYERS_APP_ID') or "").strip()
    secret_id = (os.getenv('FYERS_SECRET_ID') or "").strip()
    redirect_uri = (os.getenv('FYERS_REDIRECT_URI', 'https://my-trading-bot-ms7q.onrender.com') or "").strip()
    
    # Validate credentials
    missing = []
    if not username: missing.append('FYERS_USERNAME')
    if not pin: missing.append('FYERS_PIN')
    if not totp_secret: missing.append('FYERS_TOTP_SECRET')
    if not app_id: missing.append('FYERS_APP_ID')
    if not secret_id: missing.append('FYERS_SECRET_ID')
    
    if missing:
        logger.error(f" Missing credentials: {', '.join(missing)}")
        return None, None
    
    # Standardize App ID
    if len(app_id) == 10:
        app_id += "-100"
    
    logger.info(f" Starting auto-login for {username}...")
    
    # Step 1: Send login OTP
    request_key = send_login_otp(username, app_id)
    if not request_key:
        return None, None
    
    # Step 2: Generate and verify TOTP (must be before PIN)
    totp_code = generate_totp(totp_secret)
    if not totp_code:
        return None, None
    
    logger.info(f" Generated TOTP: {totp_code}")
    
    request_key = verify_totp(request_key, totp_code)
    if not request_key:
        return None, None
    
    # Step 3: Verify PIN (after TOTP)
    temp_token = verify_pin(request_key, pin)
    if not temp_token:
        return None, None
    
    # Step 4: Get auth code
    auth_code = get_auth_code(temp_token, app_id, redirect_uri, secret_id)
    if not auth_code:
        return None, None
    
    # Step 5: Generate final access token
    access_token, refresh_token = generate_access_token(auth_code, app_id, secret_id, redirect_uri)
    
    if access_token:
        logger.info(" Auto-login completed successfully!")
        return access_token, refresh_token
    
    return None, None

def _save_tokens(access_token, refresh_token, db_handler=None):
    """Helper function to save tokens to file and MongoDB."""
    # Save to file
    try:
        with open('.fyers_token', 'w') as f:
            f.write(access_token)
        logger.info(" Token saved to .fyers_token")
    except Exception as e:
        logger.warning(f"Could not save token to file: {e}")
    
    # Save to MongoDB
    if db_handler and hasattr(db_handler, 'connected') and db_handler.connected:
        try:
            db_handler.db["system_config"].update_one(
                {"_id": "fyers_session"},
                {"$set": {
                    "access_token": access_token,
                    "refresh_token": refresh_token or "",
                    "updated_at": datetime.utcnow().isoformat()
                }},
                upsert=True
            )
            logger.info(" Token saved to MongoDB")
        except Exception as e:
            logger.warning(f"Could not save token to MongoDB: {e}")

def validate_and_refresh_token(db_handler=None):
    """
    Check if current token is valid, if not, try refresh token, then auto-login.
    Refresh tokens are valid for 15 days, enabling autonomous operation.
    Saves new token to MongoDB if db_handler is provided.
    
    Returns: (is_valid, access_token)
    """
    from fyers_apiv3 import fyersModel
    
    app_id = os.getenv('FYERS_APP_ID')
    secret_id = os.getenv('FYERS_SECRET_ID')
    current_token = os.getenv('FYERS_ACCESS_TOKEN')
    current_refresh_token = os.getenv('FYERS_REFRESH_TOKEN')
    pin = os.getenv('FYERS_PIN')
    
    if not app_id:
        return False, None
    
    # Standardize App ID
    if len(app_id) == 10:
        app_id += "-100"
    
    # Try current token first
    if current_token:
        try:
            fyers = fyersModel.FyersModel(client_id=app_id, token=current_token, log_path="")
            profile = fyers.get_profile()
            if profile.get('s') == 'ok':
                logger.info(" Existing token is valid")
                return True, current_token
            else:
                logger.info(f" Token validation failed (will try auto-login): {profile}")
        except Exception as e:
            logger.info(f" Existing token expired or invalid: {e}")
    
    # Try refresh token (valid for 15 days - enables autonomous operation)
    if current_refresh_token and secret_id and pin:
        logger.info(" Attempting token refresh using refresh_token...")
        new_access_token, new_refresh_token = refresh_access_token(
            current_refresh_token, app_id, secret_id, pin
        )
        
        if new_access_token:
            # Save to environment (for current session)
            os.environ['FYERS_ACCESS_TOKEN'] = new_access_token
            if new_refresh_token:
                os.environ['FYERS_REFRESH_TOKEN'] = new_refresh_token
            
            # Save tokens
            _save_tokens(new_access_token, new_refresh_token, db_handler)
            return True, new_access_token
        else:
            logger.warning(f" Token refresh failed. This usually means the FYERS_REFRESH_TOKEN in .env is expired or invalid.")

    
    # Fallback: Try full auto-login (may fail due to Fyers limitations)
    logger.info(" Attempting full auto-login...")
    
    access_token, refresh_token = auto_login()
    
    if access_token:
        # Save to environment (for current session)
        os.environ['FYERS_ACCESS_TOKEN'] = access_token
        if refresh_token:
            os.environ['FYERS_REFRESH_TOKEN'] = refresh_token
        
        # Save to file (for persistence)
        try:
            with open('.fyers_token', 'w') as f:
                f.write(access_token)
            logger.info(" Token saved to .fyers_token")
        except Exception as e:
            logger.warning(f"Could not save token to file: {e}")
        
        # Save to MongoDB (for cloud persistence)
        if db_handler and db_handler.connected:
            try:
                db_handler.db["system_config"].update_one(
                    {"_id": "fyers_session"},
                    {"$set": {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "updated_at": datetime.utcnow().isoformat()
                    }},
                    upsert=True
                )
                logger.info(" Token saved to MongoDB")
            except Exception as e:
                logger.warning(f"Could not save token to MongoDB: {e}")
        
        return True, access_token
    
    logger.error(" Auto-login failed. Manual intervention required.")
    
    # Send Emergency Alert (Standalone to avoid circular imports)
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if bot_token and chat_id:
            msg = " <b>CRITICAL: Auto-Login Failed</b>\nBot could not regenerate access token.\nManual intervention required immediately."
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        
    return False, None


# Test function
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    from dotenv import load_dotenv
    load_dotenv()
    
    print("=" * 60)
    print("  FYERS AUTO-LOGIN TEST")
    print("=" * 60)
    
    is_valid, token = validate_and_refresh_token()
    
    if is_valid:
        print(f"\n SUCCESS!")
        print(f"Token: {token[:50]}...")
    else:
        print(f"\n FAILED - Check credentials")
    
    print("=" * 60)

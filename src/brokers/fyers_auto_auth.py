"""
Fyers Token Manager
Handles token validation for Render deployment
"""
import os
import logging
from fyers_apiv3 import fyersModel

logger = logging.getLogger("FyersTokenManager")

def validate_token():
    """
    Check if current token is valid
    Returns: (is_valid, token or error message)
    """
    token = os.getenv('FYERS_ACCESS_TOKEN')
    app_id = os.getenv('FYERS_APP_ID')
    
    if not token:
        # Try loading from file
        if os.path.exists('.fyers_token'):
            with open('.fyers_token', 'r') as f:
                token = f.read().strip()
                os.environ['FYERS_ACCESS_TOKEN'] = token
    
    if not token or not app_id:
        return False, "Missing token or app_id"
    
    try:
        fyers = fyersModel.FyersModel(client_id=app_id, token=token, log_path="")
        profile = fyers.get_profile()
        if profile.get('s') == 'ok':
            logger.info(" Token is valid")
            return True, token
        else:
            return False, f"Token invalid: {profile}"
    except Exception as e:
        return False, f"Token check failed: {e}"

def refresh_token_if_needed():
    """
    Validate token, return it if valid.
    For Render: Set FYERS_ACCESS_TOKEN in env vars
    For local: Uses .fyers_token file
    """
    is_valid, result = validate_token()
    
    if is_valid:
        return result
    else:
        logger.error(f" Token validation failed: {result}")
        logger.error("Run 'python fyers_auth.py' locally and update FYERS_ACCESS_TOKEN in Render")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv
    load_dotenv()
    
    is_valid, result = validate_token()
    print(f"Valid: {is_valid}")
    if is_valid:
        print(f"Token: {result[:50]}...")

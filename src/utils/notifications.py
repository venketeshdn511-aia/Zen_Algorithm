import os
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

def send_telegram_message(message):
    """
    Send notification to Telegram with robust retry logic.
    Handles transient network errors common on cloud platforms.
    """
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=3,  # Total retries
        backoff_factor=1,  # Wait 1s, 2s, 4s between retries
        status_forcelist=[429, 500, 502, 503, 504],  # Retry on these errors
        allowed_methods=["POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    try:
        # Use session.post instead of requests.post
        response = session.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f" Telegram send error: {e}")
    finally:
        session.close()

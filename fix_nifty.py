
import os
import sys
import time
import requests
import pyotp
import urllib.parse
from dotenv import load_dotenv
from neo_api_client import NeoAPI

# Load environment variables
load_dotenv()

# Credentials
CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
PASSWORD = os.getenv("KOTAK_PASSWORD")
MPIN = os.getenv("KOTAK_MPIN")
TOTP_SECRET = os.getenv("KOTAK_TOTP_SECRET")
UCC = os.getenv("KOTAK_UCC")

def get_totp(secret):
    try:
        return pyotp.TOTP(secret).now()
    except: return None

def login_kotak():
    print("Initializing Kotak Neo Client...")
    try:
        client = NeoAPI(consumer_key=CONSUMER_KEY, environment='prod')
        otp = get_totp(TOTP_SECRET)
        login_resp = client.totp_login(mobile_number=MOBILE_NUMBER, ucc=UCC, totp=otp)
        validate_resp = client.totp_validate(mpin=MPIN)
        if validate_resp and 'data' in validate_resp and 'token' in validate_resp['data']:
            print("Login Success")
            return client
    except Exception as e:
        print(f"Login Failed: {e}")
    return None

def on_message(message):
    print(f"WS Message Received: {message}")

def on_error(error):
    print(f"WS Error: {error}")

def on_open(message):
    print(f"WS Opened: {message}")

def on_close(message):
    print(f"WS Closed: {message}")

def test_nifty_ws(client):
    print("\nTesting Nifty 50 WebSocket Subscription...")
    
    # Setup Callbacks
    client.on_message = on_message
    client.on_error = on_error
    client.on_open = on_open
    client.on_close = on_close
    
    # Subscribe to Nifty 50 AND SBIN
    try:
        res = client.search_scrip(exchange_segment="nse_cm", symbol="SBIN")
        sbin_token = None
        if res:
             sbin_token = res[0]['pSymbol']
             print(f"Found SBIN Token: {sbin_token}")
        else:
             print("SBIN Search Failed, using default 3045")
             sbin_token = "3045"
             
        instruments = [
            {"instrument_token": "26000", "exchange_segment": "nse_cm"},
            {"instrument_token": sbin_token, "exchange_segment": "nse_cm"}
        ]
        print(f"Subscribing to: {instruments}")
        
        client.subscribe(instrument_tokens=instruments, isIndex=False, isDepth=False)
        
        print("Subscribed (isIndex=False). Waiting 10s...")
        time.sleep(10)
        
        print("Switching to isIndex=True for Nifty Only...")
        client.un_subscribe(instrument_tokens=instruments, isIndex=False)
        
        nifty_only = [{"instrument_token": "26000", "exchange_segment": "nse_cm"}]
        client.subscribe(instrument_tokens=nifty_only, isIndex=True, isDepth=False)
        print("Subscribed Nifty (isIndex=True). Waiting 10s...")
        time.sleep(10)

        print("WebSocket Test Complete.")
        
    except Exception as e:
        print(f"WS Subscription Failed: {e}")

if __name__ == "__main__":
    client = login_kotak()
    if client:
        # test_nifty(client) # Skip REST for now
        test_nifty_ws(client)

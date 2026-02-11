import os
import logging
from dotenv import load_dotenv
from neo_api_client import NeoAPI
import pandas as pd
from datetime import datetime, timedelta

load_dotenv()

def test_history():
    api = NeoAPI(consumer_key=os.getenv("KOTAK_CONSUMER_KEY"), environment='prod')
    api.totp_login(mobile_number=os.getenv("KOTAK_MOBILE_NUMBER"), ucc=os.getenv("KOTAK_UCC"), totp=input("Enter TOTP: ") if not os.getenv("KOTAK_TOTP_SECRET") else None)
    # If TOTP secret is in env, we might need a way to generate it here to be fully auto, but let's assume we can run it.
    
    # Simple test for Nifty 50 (Token 26000)
    try:
        # Based on standard Neo V2 history params:
        # instrumentToken, interval, fromDate, toDate
        # Interval: 1, 5, 15, 30, 60, 1D
        
        now = datetime.now()
        yesterday = now - timedelta(days=2)
        
        # Test 1: Try common param names
        print("Testing history call...")
        try:
            res = api.history(
                instrument_token="26000",
                exchange_segment="nse_cm",
                from_date=yesterday.strftime("%d/%m/%Y"),
                to_date=now.strftime("%d/%m/%Y"),
                interval="1"
            )
            print(f"Response: {str(res)[:500]}")
        except Exception as e:
            print(f"Method 1 failed: {e}")

    except Exception as e:
        print(f"Critical error: {e}")

if __name__ == "__main__":
    test_history()

from src.brokers.fyers_broker import FyersBroker
import pandas as pd

from dotenv import load_dotenv
import os

import logging

load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

def check_fyers():
    broker = FyersBroker()
    print("Connecting to Fyers...")
    if not broker.connect():
        print("Failed to connect to Fyers.")
        return
    
    print("Fetching History...")
    df = broker.get_latest_bars("NSE:NIFTY50-INDEX", timeframe='1', limit=1200)
    if df is not None and not df.empty:
        print(f"Success! Rows: {len(df)}")
        print(f"Columns: {df.columns.tolist()}")
        print(df.head())
    else:
        print("Failed to fetch history or empty data.")

if __name__ == "__main__":
    check_fyers()

import os
import pandas as pd
import time
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel
from dotenv import load_dotenv

load_dotenv()

def fetch_data(symbol, start_date, end_date, interval='1m'):
    """
    Fetches historical data from Fyers API.
    """
    print(f" Fetching data for {symbol} from {start_date} to {end_date} (Interval: {interval}) via Fyers...")
    
    # Map backtest intervals to Fyers resolution
    resolution_map = {
        '1m': '1',
        '5m': '5',
        '15m': '15',
        '1h': '60',
        '1d': 'D'
    }
    resolution = resolution_map.get(interval, '1')
    
    # Try to load token from .fyers_token or ENV
    token = None
    if os.path.exists('.fyers_token'):
        with open('.fyers_token', 'r') as f:
            token = f.read().strip()
    
    if not token:
        token = os.getenv('FYERS_ACCESS_TOKEN')
        
    if not token:
        print(" Error: No Fyers token found (.fyers_token or FYERS_ACCESS_TOKEN env).")
        return pd.DataFrame()

    app_id = os.getenv('FYERS_APP_ID')
    if app_id and len(app_id) == 10 and not app_id.endswith('-100'):
        app_id += "-100"
        
    if not app_id:
        print(" Error: FYERS_APP_ID not found in environment.")
        return pd.DataFrame()

    fyers = fyersModel.FyersModel(client_id=app_id, token=token, log_path="")
    
    # Fyers historical API has limits on range per request (e.g., 100 days for 1m)
    # For backtesting, we might need to chunk it, but for now let's try a single request
    # and add basic chunking logic if it's a long range.
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    all_candles = []
    current_start = start_dt
    
    # Max days per request for different resolutions (conservative estimates)
    max_days = {
        '1': 60,
        '5': 100,
        '15': 100,
        '60': 100,
        'D': 365
    }
    delta_step = max_days.get(resolution, 60)
    
    while current_start < end_dt:
        current_end = min(current_start + timedelta(days=delta_step), end_dt)
        
        data = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": current_start.strftime("%Y-%m-%d"),
            "range_to": current_end.strftime("%Y-%m-%d"),
            "cont_flag": "1"
        }
        
        try:
            response = fyers.history(data)
            if response and response.get('s') == 'ok':
                all_candles.extend(response['candles'])
            else:
                print(f" Fyers API Error for range {data['range_from']} to {data['range_to']}: {response}")
                break
        except Exception as e:
            print(f" Exception during Fyers fetch: {e}")
            break
            
        current_start = current_end + timedelta(days=1)
        time.sleep(0.5) # Avoid rate limits
        
    if not all_candles:
        print(f" No data fetched for {symbol}.")
        return pd.DataFrame()
        
    df = pd.DataFrame(all_candles, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
    df.drop_duplicates(subset='datetime', inplace=True)
    
    # Convert epoch to datetime
    df['datetime'] = pd.to_datetime(df['datetime'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)
    df.set_index('datetime', inplace=True)
    df.sort_index(inplace=True)
    
    # Capitalize columns to match the project's expected format (OHLCV)
    df.columns = [c.capitalize() for c in df.columns]
    
    print(f" Successfully fetched {len(df)} rows via Fyers.")
    return df

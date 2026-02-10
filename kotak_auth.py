
import os
import time
import pyotp
from dotenv import load_dotenv
from neo_api_client import NeoAPI
import requests
import pandas as pd
from io import StringIO
import traceback
import sys

# Load environment variables
load_dotenv()

# Credentials
CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY")
MOBILE_NUMBER = os.getenv("KOTAK_MOBILE_NUMBER")
PASSWORD = os.getenv("KOTAK_PASSWORD")
MPIN = os.getenv("KOTAK_MPIN")
TOTP_SECRET = os.getenv("KOTAK_TOTP_SECRET")

def get_totp(secret):
    """Generate TOTP from secret"""
    if not secret:
        print("❌ No TOTP Secret provided!")
        return None
    try:
        totp = pyotp.TOTP(secret)
        return totp.now()
    except Exception as e:
        print(f"❌ Error generating TOTP: {e}")
        return None

def login_kotak():
    print("🚀 Initializing Kotak Neo Login...")
    
    # Initialize API
    try:
        print(f"🔑 Initializing NeoAPI with Consumer Key: {CONSUMER_KEY[:4]}... and Env: prod")
        client = NeoAPI(
            consumer_key=CONSUMER_KEY,
            environment='prod'
        )
        print("✅ NeoAPI Initialized")
    except Exception as e:
        print(f"❌ Failed to init NeoAPI: {e}")
        return None

    # Login Flow: TOTP Login -> TOTP Validate (MPIN)
    try:
        UCC = os.getenv("KOTAK_UCC")
        if not UCC:
            print("❌ KOTAK_UCC is missing in .env")
            return None
            
        print(f"🔐 Generating TOTP for login...")
        otp = get_totp(TOTP_SECRET)
        if not otp:
            print("❌ TOTP Generation failed")
            return None
            
        print(f"🚀 Calling totp_login(mobile={MOBILE_NUMBER}, ucc={UCC}, totp={otp})...")
        # Step 1: TOTP Login
        login_resp = client.totp_login(
            mobile_number=MOBILE_NUMBER,
            ucc=UCC,
            totp=otp
        )
        print(f"📋 TOTP Login Response: {login_resp}")
        
        # Step 2: Validate with MPIN
        print(f"🔐 Validating with MPIN...")
        validate_resp = client.totp_validate(mpin=MPIN)
        print(f"📋 Validate Response: {validate_resp}")
        
        # Check if session is established
        if validate_resp and 'data' in validate_resp and 'token' in validate_resp['data']:
             print("✅ Login Sequence Complete! Session Established.")
             return client
        else:
             print("⚠️ Login might have failed. Check response.")
             return client 

    except Exception as e:
        print(f"❌ Login Critical Error: {e}")
        return None

if __name__ == "__main__":
    client = login_kotak()
    if client:
        try:
             print(f"\n🌍 API Host: {client.configuration.host}")
             
             print("\n📥 Fetching Scrip Master URL for NSE_CM...")
             scrip_url = client.scrip_master(exchange_segment="nse_cm")
             print(f"📋 Scrip Master URL: {scrip_url}")
             
             if isinstance(scrip_url, str):
                 
                 base_url = "https://lapi.kotaksecurities.com" if client.configuration.host != 'uat' else "https://napi.kotaksecurities.com"
                 full_url = scrip_url
                 if not scrip_url.startswith("http"):
                     full_url = f"{base_url}/{scrip_url}"
                 
                 print(f"🔗 Downloading Scrip Master from: {full_url}")
                 sys.stdout.flush()
                 
                 try:
                     resp = requests.get(full_url)
                     print(f"📡 Response Status: {resp.status_code}")
                     sys.stdout.flush()
                     
                     if resp.status_code == 200:
                         print("✅ Download Success. Parsing CSV...")
                         sys.stdout.flush()
                         
                         csv_data = StringIO(resp.text)
                         df = pd.read_csv(csv_data)
                         print(f"🔢 Total Rows: {len(df)}")
                         cols = df.columns.tolist()
                         print(f"📊 Columns: {cols}")
                         sys.stdout.flush()
                         
                         # Identify correct columns
                         # Common variations: pSymbol, pSymbolName, pExchSeg
                         # If not present, print what we have
                         
                         # Test Cases: SBIN and Reliance
                         targets = ["SBIN", "RELIANCE"] 
                         
                         for target_name in targets:
                             print(f"\n🔎 Searching for {target_name}...")
                             # Filter
                             if 'pSymbolName' in df.columns and 'pSymbol' in df.columns:
                                 mask = df['pSymbolName'].astype(str).str.contains(target_name, case=False, regex=False) | \
                                        df['pSymbol'].astype(str).str.contains(target_name, case=False, regex=False)
                                 matches = df[mask]
                             else:
                                 print(f"⚠️ Columns pSymbolName/pSymbol missing. Columns: {df.columns.tolist()}")
                                 matches = pd.DataFrame()
                                 
                             if not matches.empty:
                                 # Pick the first EQUITY match (EQ)
                                 # Usually pSeries or similar indicates EQ. or pSymbol ends with -EQ
                                 # Let's inspect first 3 matches
                                 print(f"✅ Found {len(matches)} matches. First 3:")
                                 print(matches.head(3).to_string())
                                 
                                 row = matches.iloc[0]
                                 token = str(row.get('pSymbol', ''))
                                 seg = str(row.get('pExchSeg', 'nse_cm'))
                                 name = str(row.get('pSymbolName', ''))
                                 
                                 print(f"👉 Attempting Quote for {name} with Token: {token}, Seg: {seg}")
                                 sys.stdout.flush()
                                 
                                 try:
                                     # Payload variation: Standard
                                     payload = [{"instrument_token": token, "exchange_segment": seg}]
                                     print(f"   Payload: {payload}")
                                     q = client.quotes(instrument_tokens=payload, quote_type="ltp")
                                     print(f"   Result: {q}")
                                     
                                 except Exception as eq:
                                     print(f"   ❌ Quote Error: {eq}")
                                     traceback.print_exc()
                             else:
                                 print(f"❌ {target_name} not found in CSV.")
                                 
                     else:
                         print(f"❌ Download Failed: {resp.status_code}")
                 except Exception as e:
                     print(f"❌ Download/Parse Error: {e}")
                     traceback.print_exc()
             
        except Exception as e:
            print(f"❌ Detailed Test Failed: {e}")
            traceback.print_exc()

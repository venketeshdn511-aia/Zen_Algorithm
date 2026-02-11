import yfinance as yf
import pandas as pd

def check_yf():
    print("Fetching Nifty 50 history...")
    nifty = yf.Ticker("^NSEI")
    df = nifty.history(period="5d", interval="1m")
    if df is not None and not df.empty:
        print(f" Success! Rows: {len(df)}")
        print(f"Columns: {df.columns.tolist()}")
        print(f"Sample Index: {df.index[0]} (Type: {type(df.index[0])})")
        print(f"Head:\n{df.head()}")
    else:
        print(" Failed to fetch data.")

if __name__ == "__main__":
    check_yf()

import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import backtrader as bt
from src.backtesting.data_fetcher import fetch_data

# Define the Strategy
class RsiStrategy(bt.Strategy):
    params = (
        ('rsi_period', 14),
        ('rsi_low', 30),
        ('rsi_high', 70),
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)

    def next(self):
        if not self.position:
            if self.rsi < self.params.rsi_low:
                self.buy()
        else:
            if self.rsi > self.params.rsi_high:
                self.sell()

def run_backtrader(symbol='AAPL', start_date='2024-01-01', end_date='2025-01-01'):
    print("--- Starting Backtrader ---")
    
    # 1. Setup Cerebro
    cerebro = bt.Cerebro()
    
    # 2. Add Strategy
    cerebro.addstrategy(RsiStrategy)
    
    # 3. Get Data (Pandas Datafeed)
    df = fetch_data(symbol, start_date, end_date)
    
    if df.empty:
        print("No data fetched.")
        return

    # Backtrader expects a slightly different index/format sometimes, but PandasData usually handles it
    # We just need to make sure index is datetime
    # Fyers returns datetime index, so we are good.
    
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)
    
    # 4. Set Cash
    cerebro.broker.setcash(100000.0)
    
    # 5. Run
    print(f'Starting Portfolio Value: {cerebro.broker.getvalue():.2f}')
    cerebro.run()
    final_value = cerebro.broker.getvalue()
    print(f'Final Portfolio Value: {final_value:.2f}')
    
    # 6. Plot (Optional, might fail in non-GUI envs, but let's try safely)
    try:
        # Check if we are in environment that supports plotting
        print("Attempting to plot...")
        # cerebro.plot() # Commented out by default to avoid hanging in non-interactive shell
        # Instead, we can save figure if user wants, but for now just console output is enough
        print("Plotting skipped for console mode.")
    except Exception as e:
        print(f"Plotting failed: {e}")

if __name__ == "__main__":
    run_backtrader()

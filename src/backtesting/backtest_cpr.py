import sys
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.strategies.cpr_strategy import CPRBreakoutLongStrategy
from src.brokers.fyers_broker import FyersBroker

def run_cpr_backtest():
    print("--- Starting CPR Breakout Long Strategy Backtest (Fyers Data) ---")
    
    symbol = "NSE:NIFTY50-INDEX" 
    timeframe = '5' # Fyers Broker uses '5' for 5min
    
    print("Connecting to Fyers...")
    fyers = FyersBroker()
    fyers.connect()
    
    df = pd.DataFrame()
    
    if fyers.connected:
        print(f"✅ Connected to Fyers. Fetching data for {symbol}...")
        df = fyers.get_latest_bars(symbol, timeframe=timeframe, limit=10000)
    else:
        print("⚠️ Could not connect to Fyers API. Checking for local Fyers CSV data...")
    
    # Fallback to local CSV if API failed or returned empty
    if df.empty:
        csv_file = 'nifty_5m_fyers_30d.csv'
        if os.path.exists(csv_file):
            print(f"✅ Loading data from local file: {csv_file}")
            df = pd.read_csv(csv_file)
            # Standardize columns
            df.columns = [c.capitalize() for c in df.columns]
            # Ensure index is datetime
            if 'Datetime' in df.columns:
                df['Datetime'] = pd.to_datetime(df['Datetime'])
                df.set_index('Datetime', inplace=True)
        else:
            print(f"❌ Local file {csv_file} not found. Cannot proceed.")
            return

    if df.empty:
        print("❌ No data available.")
        return

    print(f"✅ Data ready: {len(df)} candles from {df.index[0]} to {df.index[-1]}")

    strategy = CPRBreakoutLongStrategy()
    
    # Portfolio params
    initial_cash = 15000  # Matched PDF/User request
    cash = initial_cash
    position = 0
    entry_price = 0
    stop_loss = 0
    take_profit = 0
    
    trades = []
    equity_curve = []
    dates_tracked = []
    
    # Pre-calculate signals
    print("Pre-calculating CPR levels...")
    df_with_cpr = strategy.calculate_cpr(df)
    
    # Resample to 15m for RSI
    df_15m = df.resample('15min').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last'
    }).dropna()
    
    import pandas_ta as ta
    df_15m['RSI'] = ta.rsi(df_15m['Close'], length=14)
    
    print("Running Simulation...")
    
    # Iterate over original 5m DF (proxy for 1m in "15m-1m")
    # We need to map 5m timestamp to the LATEST AVAILABLE 15m RSI.
    # If time is 09:20, latest closed 15m is 09:15.
    
    for i in range(20, len(df)):
        candle = df.iloc[i]
        curr_date = candle.name
        curr_close = candle['Close']
        
        # Get CPR (Daily)
        day_date = curr_date.normalize()
        # Optimization: lookup by date. 
        # Since df_with_cpr has index matching df (because of the merge in calculate_cpr?),
        # wait, calculate_cpr returns merged_df with index same as input df.
        # So we can just look up df_with_cpr.iloc[i]!
        
        # But wait, did I assign df_with_cpr back to a variable aligned with df?
        # Yes: returned `merged_df` has same index as `df`.
        
        cpr_row = df_with_cpr.iloc[i]
        cpr_tc = cpr_row['TC']
        cpr_bc = cpr_row['BC']
        cpr_top = max(cpr_tc, cpr_bc)
        
        # Get RSI (15m)
        # Find 15m candle ending before or at curr_date.
        # resample '15min' yields timestamps like 09:15, 09:30.
        # 09:15 candle covers 09:15-09:30.
        # At 09:20, the 09:15 candle is forming. At 09:30, it is closed.
        # If we require "Analysis Timeframe: 15m", we typically implicitly mean "wait for signal bar close" if strictly 15m.
        # BUT if "15m-1m", maybe we use the "Developing RSI" or "Previous 15m RSI".
        # Let's use PREVIOUS COMPLETED 15m RSI to be safe/conservative (no lookahead).
        # floor curr_date to nearest 15m, then subtract 15m.
        
        prev_15m_ts = curr_date.floor('15min') - timedelta(minutes=15)
        
        if prev_15m_ts in df_15m.index:
            rsi = df_15m.loc[prev_15m_ts]['RSI']
        else:
            # Need RSI to proceed
            continue
            
        # Missing RSI check
        # Intraday Square Off
        if curr_date.time() >= datetime.strptime("15:15", "%H:%M").time():
            if position > 0:
                # Force Exit
                exit_price = curr_close
                pnl = (exit_price - entry_price) * position
                cash += (exit_price * position)
                trades.append({
                    'date': curr_date, 'type': 'SELL (SQ)', 'price': exit_price, 
                    'pnl': pnl, 'reason': 'Square Off'
                })
                position = 0
            # Update equity
            equity = cash 
            equity_curve.append(equity)
            dates_tracked.append(curr_date)
            continue

        # Exit Logic
        if position > 0:
            # Check SL / TP
            if candle['Low'] <= stop_loss:
                # SL Hit
                exit_price = stop_loss
                pnl = (exit_price - entry_price) * position
                cash += (exit_price * position)
                trades.append({
                    'date': curr_date, 'type': 'SELL (SL)', 'price': exit_price, 
                    'pnl': pnl, 'reason': 'Stop Loss'
                })
                position = 0
            elif candle['High'] >= take_profit:
                # TP Hit
                exit_price = take_profit
                pnl = (exit_price - entry_price) * position
                cash += (exit_price * position)
                trades.append({
                    'date': curr_date, 'type': 'SELL (TP)', 'price': exit_price, 
                    'pnl': pnl, 'reason': 'Take Profit'
                })
                position = 0
            
            # Update equity
            equity = cash + (position * curr_close)
            equity_curve.append(equity)
            dates_tracked.append(curr_date)
            continue

        # Entry Logic
        # Trigger: 5m Close > CPR Top
        # Filter: RSI (15m) between 40 and 60
        
        if curr_close > cpr_top and rsi >= strategy.rsi_lower and curr_date.time() < datetime.strptime("14:45", "%H:%M").time():
            # Check if we are already far above? 
            # Breakout usually means "Cross Over".
            # If we just check ">", we enter late in the trend.
            # We should check if Previous 5m Close was <= CPR Top (Cross Over).
            
            # Valid Entry
            current_atr = 0 
            
            sl_price = curr_close * (1 - strategy.sl_pct)
            risk = curr_close - sl_price
            tp_price = curr_close + (risk * strategy.risk_reward)
            
            # Allocation: 1 Unit
            shares = 1
            cost = shares * curr_close
            
            position = shares
            entry_price = curr_close
            stop_loss = sl_price
            take_profit = tp_price
            
            trades.append({
                'date': curr_date, 'type': 'BUY', 'price': curr_close, 
                'shares': shares, 'sl': stop_loss, 'tp': take_profit
            })
                
        # Update Equity (Mark to Market)
        # If position == 0, equity = cash.
        # If position > 0, equity = cash + Unrealized PnL? 
        # Since I didn't subtract cost, Equity = Initial + Realized + Unrealized.
        
        # Recalculate equity properly
        realized_pnl = sum([t['pnl'] for t in trades if 'pnl' in t])
        unrealized_pnl = (curr_close - entry_price) * position if position > 0 else 0
        equity = initial_cash + realized_pnl + unrealized_pnl
        
        equity_curve.append(equity)
        dates_tracked.append(curr_date)
        
    # Final Stats
    final_value = equity_curve[-1] if equity_curve else initial_cash
    roi = ((final_value - initial_cash) / initial_cash) * 100
    
    print(f"\n--- Strategy Results ---")
    print(f"Total Trades: {len(trades)}")
    print(f"Final Value: {final_value:.2f}")
    print(f"ROI: {roi:.2f}%")
    
    # Save Log
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df.to_csv("cpr_backtest_trades.csv", index=False)
        print("Trades saved to cpr_backtest_trades.csv")

if __name__ == "__main__":
    run_cpr_backtest()

import sys
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.backtesting.data_fetcher import fetch_data

from datetime import datetime, timedelta

def get_strategy(name):
    # Dynamic import map
    if name == 'RsiStrategy':
        from src.strategies.rsi_strategy import RsiStrategy
        return RsiStrategy()
    elif name == 'SupplyDemandRetest':
        from src.strategies.supply_demand import SupplyDemandRetest
        return SupplyDemandRetest()
    elif name == 'NiftyOptionsStrategyV2':
        from src.strategies.nifty_options_v2 import NiftyOptionsStrategyV2
        return NiftyOptionsStrategyV2()
    return None

def run_custom_backtest(symbol=None, start_date=None, end_date=None):
    print("--- Starting Custom Backtest with Visuals ---")
    
    # Load Config to get active strategy/symbol if not provided
    try:
        with open('config.json', 'r') as f:
            CONFIG = json.load(f)
            if not symbol: symbol = CONFIG['trading_symbol']
            strategy_name = CONFIG['active_strategy']
            timeframe = CONFIG.get('timeframe', '1Min')
    except Exception as e:
        print(f"Config load failed ({e}), defaulting.")
        if not symbol: symbol = 'AAPL'
        strategy_name = 'RsiStrategy'
        timeframe = '1Min'

    # Resolution mapping for Fyers
    resolution_map = {'1Min': '1m', '5Min': '5m', '15Min': '15m', '1Day': '1d'}
    fetch_interval = resolution_map.get(timeframe, '1m')

    if not start_date:
        # Default to last 30 days
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')

    print(f"Testing Strategy: {strategy_name} on {symbol} ({timeframe})")


    # 1. Get Data via Fyers
    df = fetch_data(symbol, start_date, end_date, interval=fetch_interval)
    
    if df.empty:
        print("No data fetched.")
        return

    # 2. Setup Strategy
    strategy = get_strategy(strategy_name)
    if not strategy:
        print(f"Strategy {strategy_name} not found.")
        return
    
    # 3. Initialize Portfolio
    initial_cash = 100000
    cash = initial_cash
    position = 0
    
    # Track Performance
    equity_curve = []
    dates_tracked = []
    trades = []
    
    print("Running simulation...")
    
    # Iterate row by row (simulating real-time)
    for i in range(len(df)):
        # We need at least some history for indicators
        if i < 20:
            continue
            
        current_slice = df.iloc[:i+1].copy()
        current_date = df.index[i]
        current_price = df['Close'].iloc[i]
        
        # Calculate Signal
        try:
            signal = strategy.calculate_signal(current_slice)
        except TypeError:
             # For strategies requiring major/minor TFs, pass same slice for test
            signal = strategy.calculate_signal(current_slice, current_slice)
        
        # Execute Logic
        if signal == 'buy' and position == 0:
            shares_to_buy = int(cash // current_price)
            if shares_to_buy > 0:
                cost = shares_to_buy * current_price
                cash -= cost
                position += shares_to_buy
                trades.append({'date': current_date, 'type': 'BUY', 'price': current_price, 'shares': shares_to_buy})
                
        elif signal == 'sell' and position > 0:
            revenue = position * current_price
            cash += revenue
            trades.append({'date': current_date, 'type': 'SELL', 'price': current_price, 'shares': position})
            position = 0
            
        # Update Equity
        equity = cash + (position * current_price)
        equity_curve.append(equity)
        dates_tracked.append(current_date)

    # Final Stats
    final_value = equity_curve[-1] if equity_curve else initial_cash
    roi = ((final_value - initial_cash) / initial_cash) * 100
    
    print(f"\n--- Results for {symbol} ---")
    print(f"Initial Cash: ${initial_cash}")
    print(f"Final Value:  ${final_value:.2f}")
    print(f"Total Return: {roi:.2f}%")
    print(f"Total Trades: {len(trades)}")
    
    if trades:
        print("\nLast 5 Trades:")
        for t in trades[-5:]:
            print(f"{t['date'].date()} {t['type']} @ {t['price']:.2f}")

    # --- PLOTTING ---
    print("\nGenerating Chart...")
    try:
        # Create a figure with two subplots: Price and Equity
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        
        # Plot 1: Price and Signals
        price_line = ax1.plot(dates_tracked, df.loc[dates_tracked, 'Close'], label='Price', color='black', alpha=0.5, linewidth=1)
        
        # Segment trades
        buys = [t for t in trades if t['type'] == 'BUY']
        sells = [t for t in trades if t['type'] == 'SELL']
        
        if buys:
            ax1.scatter([b['date'] for b in buys], [b['price'] for b in buys], 
                        marker='^', color='green', label='Buy Signal', s=100, zorder=5)
        if sells:
            ax1.scatter([s['date'] for s in sells], [s['price'] for s in sells], 
                        marker='v', color='red', label='Sell Signal', s=100, zorder=5)
        
        ax1.set_title(f"Backtest Analysis: {symbol} | Strategy: {strategy_name}", fontsize=14)
        ax1.set_ylabel("Price ($)", fontsize=12)
        ax1.legend(loc='upper left')
        ax1.grid(True, linestyle='--', alpha=0.5)
        
        # Plot 2: Portfolio Value (Equity Curve)
        ax2.plot(dates_tracked, equity_curve, label='Portfolio Value (Equity)', color='#1f77b4', linewidth=2)
        
        # Color fill for Profit/Loss area
        ax2.fill_between(dates_tracked, initial_cash, equity_curve, where=(pd.Series(equity_curve) >= initial_cash), color='green', alpha=0.15)
        ax2.fill_between(dates_tracked, initial_cash, equity_curve, where=(pd.Series(equity_curve) < initial_cash), color='red', alpha=0.15)
        
        ax2.axhline(y=initial_cash, color='grey', linestyle='--', alpha=0.7)
        ax2.set_ylabel("Account Value ($)", fontsize=12)
        ax2.set_xlabel("Date", fontsize=12)
        ax2.legend(loc='upper left')
        ax2.grid(True, linestyle='--', alpha=0.5)
        
        # Formatting
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gcf().autofmt_xdate()
        
        plt.tight_layout()
        
        # Save the result
        output_file = f"backtest_result_{symbol}.png"
        plt.savefig(output_file)
        print(f"Visualization saved to: {output_file}")
        
    except Exception as e:
        print(f"Plotting Error: {e}")

if __name__ == "__main__":
    run_custom_backtest()

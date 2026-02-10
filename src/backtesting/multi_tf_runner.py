import sys
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.backtesting.data_fetcher import fetch_data
from src.strategies.multi_tf_supply_demand import MultiTimeframeSupplyDemand
from src.strategies.nifty_options_v2 import NiftyOptionsStrategyV2

def run_multi_tf_backtest(symbol='^NSEI'):
    print(f"--- Starting Multi-Timeframe Backtest (5m Zones + 1m Entry) for {symbol} ---")
    
    # Fyers data ranges
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date_1m = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    start_date_5m = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    print(f"Fetching High-Res (1m) Entry data for the last 7 days...")
    df_1m = fetch_data(symbol, start_date_1m, end_date, interval='1m')
    
    print(f"Fetching Context (5m) Zone data for the last 60 days...")
    df_5m = fetch_data(symbol, start_date_5m, end_date, interval='5m')
    
    if df_1m.empty or df_5m.empty:
        print("Data fetch failed. Ensure markets are open or symbols are correct.")
        return

    # Normalize columns
    df_1m.columns = [c.capitalize() for c in df_1m.columns]
    df_5m.columns = [c.capitalize() for c in df_5m.columns]

    # Initialize Strategy
    # Detect asset type or use specific strategy
    if symbol == '^NSEI':
        strategy = NiftyOptionsStrategyV2()
        print("Strategy: NiftyOptionsStrategyV2 (Indian Options Logic)")
    else:
        # Default Logic
        asset_type = 'stock'
        if 'BTC' in symbol or 'ETH' in symbol or '/' in symbol:
            asset_type = 'crypto'
        strategy = MultiTimeframeSupplyDemand(asset_type=asset_type)
        print(f"Strategy: MultiTimeframeSupplyDemand ({asset_type})")
    
    # 3. Portfolio
    initial_capital = 100000
    cash = initial_capital
    position_lots = 0
    equity_curve = []
    dates_tracked = []
    trades = []
    
    # Nifty Option Specs (Restored)
    LOT_SIZE = 75
    LOT_COST_EST = 12000 
    OPTION_DELTA = 0.5 
    
    # Generic Spot Mode (BTC)
    is_option_mode = True
    
    print(f"Running Multi-TF Simulation for {symbol} (Options Trend/Scalp Mode)...")
    print(f"Capital: ${initial_capital}")
    print(f"1m Start: {df_1m.index[0]} | 5m Start: {df_5m.index[0]}")
    
    for i in range(len(df_1m)):
        current_time = df_1m.index[i]
        
        # Determine 5m context
        context_5m = df_5m[df_5m.index < current_time]
        if len(context_5m) < 50: continue
            
        # Parse Signal
        signal_raw = 'none'
        signal_mode = 'scalp' # default
        
        try:
            res = strategy.calculate_signal(context_5m, df_1m.iloc[:i+1], symbol=symbol)
            if res:
                if '_' in res:
                    parts = res.split('_')
                    signal_raw = parts[0]
                    signal_mode = parts[1]
                else:
                    signal_raw = res
        except Exception as e:
            print(f"CRITICAL ERROR at {current_time}: {e}")
            break
            
        current_price = df_1m['Close'].iloc[i]
        
        # --- DYNAMIC DELTA ---
        # Trend Mode = 0.6 (ITM), Scalp Mode = 0.5 (ATM)
        current_delta = 0.6 if signal_mode == 'trend' else 0.5
        
        # --- HARD TIME STOP (15:00 IST Check) ---
        # Assuming Data is UTC, 15:00 IST is 09:30 UTC
        # If time > 09:30 UTC and we hold a position, checking validity
        # User Rule: "If holding ATM (Scalp) and time > 15:00 -> EXIT FULL"
        
        is_late = False
        if current_time.hour >= 9 and current_time.minute >= 30:
             is_late = True
             
        if is_late and position_lots > 0 and signal_mode == 'scalp':
             # FORCE EXIT SCALP
             signal_raw = 'sell' if trades[-1]['type'] == 'BUY' else 'buy' # Flip logic
             print(f"[{current_time}] HARD TIME STOP (Scalp)")

        # Current Equity (Cash + PnL of open position)
        if position_lots > 0:
             pass 

        # Execution
        if signal_raw == 'buy' and position_lots == 0:
             # SIZING Logic...
             effective_equity = cash 
             risk_budget = min(effective_equity, initial_capital)
             
             lots = int(risk_budget // LOT_COST_EST)
             
             if lots >= 1:
                 position_lots = lots
                 entry_price = current_price
                 
                 trades.append({'date': current_time, 'type': 'BUY', 'price': current_price, 'lots': lots, 'mode': signal_mode})
                 print(f"[{current_time}] BUY {lots} Lots ({signal_mode.upper()}) at {current_price:.2f}")

        elif signal_raw == 'sell' and position_lots > 0:
             # Check if we are holding a Long
             last_trade = trades[-1]
             if last_trade['type'] == 'BUY':
                 exit_price = current_price
                 
                 # Use Delta from Entry Mode
                 entry_mode = last_trade.get('mode', 'scalp')
                 exit_delta = 0.6 if entry_mode == 'trend' else 0.5
                 
                 index_points = exit_price - entry_price
                 option_points = index_points * exit_delta
                 pnl = option_points * LOT_SIZE * position_lots
                 
                 cash += pnl
                 print(f"[{current_time}] SELL {position_lots} Lots at {current_price:.2f}. PnL: ${pnl:.2f}")
                 
                 trades.append({'date': current_time, 'type': 'SELL_EXIT', 'price': current_price, 'pnl': pnl})
                 position_lots = 0
                 entry_price = 0
                 
        # Track Equity...

        # Track Equity
        current_eq = cash
        if position_lots > 0:
             # Unrealized PnL
             # Use generic 0.5 Delta for simplicity in curve, or use refined logic?
             # Let's use 0.5 for unrealized to smooth the curve.
             unrealized = (current_price - entry_price) * OPTION_DELTA * LOT_SIZE * position_lots
             current_eq += unrealized
             
        equity_curve.append(current_eq)
        dates_tracked.append(current_time)

    # 4. Results & Statistics
    final_val = equity_curve[-1] if equity_curve else initial_capital
    total_pnl = final_val - initial_capital
    pct_return = (total_pnl / initial_capital) * 100
    
    # 4a. Max Drawdown
    peak = initial_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
        
    # 4b. Trade Stats
    closed_trades = [t for t in trades if t['type'] == 'SELL_EXIT']
    winning_trades = [t for t in closed_trades if t['pnl'] > 0]
    losing_trades = [t for t in closed_trades if t['pnl'] <= 0]
    
    num_trades = len(closed_trades)
    num_wins = len(winning_trades)
    num_losses = len(losing_trades)
    
    win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0
    loss_rate = (num_losses / num_trades * 100) if num_trades > 0 else 0
    
    avg_win = sum(t['pnl'] for t in winning_trades) / num_wins if num_wins > 0 else 0
    avg_loss = sum(t['pnl'] for t in losing_trades) / num_losses if num_losses > 0 else 0
    
    best_trade = max([t['pnl'] for t in closed_trades]) if closed_trades else 0
    worst_trade = min([t['pnl'] for t in closed_trades]) if closed_trades else 0
    
    gross_profit = sum(t['pnl'] for t in winning_trades)
    gross_loss = abs(sum(t['pnl'] for t in losing_trades))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    
    # 4c. Duration & Frequency
    # We need to link BUY to SELL to get duration. 
    # Current structure allows simple pairing since we don't scale in/out (Wait, we might if logic changed, but currently it's 1-in-1-out).
    # Re-scan trades explicitly to pair types.
    durations = []
    entry_time = None
    for t in trades:
        if t['type'] == 'BUY':
            entry_time = t['date']
        elif 'SELL' in t['type'] and entry_time:
            durations.append(t['date'] - entry_time)
            entry_time = None
            
    avg_duration_hrs = 0
    if durations:
        avg_seconds = sum([d.total_seconds() for d in durations]) / len(durations)
        avg_duration_hrs = avg_seconds / 3600
        
    # Time window frequency
    days_tracked = (df_1m.index[-1] - df_1m.index[0]).days
    if days_tracked == 0: days_tracked = 1
    trades_per_day = num_trades / days_tracked
    trades_per_week = trades_per_day * 5 # Trading days approximation
    trades_per_month = trades_per_day * 20
    
    print("\n" + "="*70)
    print("  BACKTEST RESULTS (Refined Strategy)")
    print("="*70)
    print(f"\n  PERFORMANCE:")
    print(f"    Starting Balance:  ${initial_capital:,.2f}")
    print(f"    Ending Balance:    ${final_val:,.2f}")
    print(f"    Total P&L:         ${total_pnl:,.2f} ({pct_return:+.2f}%)")
    print(f"    Max Drawdown:      {max_dd*100:.2f}%")
    
    print(f"\n  TRADE STATISTICS:")
    print(f"    Total Trades:      {num_trades}")
    print(f"    Winning Trades:    {num_wins} ({win_rate:.1f}%)")
    print(f"    Losing Trades:     {num_losses} ({loss_rate:.1f}%)")
    print(f"    Average Win:       ${avg_win:,.2f}")
    print(f"    Average Loss:      ${avg_loss:,.2f}")
    print(f"    Best Trade:        ${best_trade:,.2f}")
    print(f"    Worst Trade:       ${worst_trade:,.2f}")
    print(f"    Profit Factor:     {profit_factor:.2f}")
    
    print(f"\n  TRADE FREQUENCY:")
    print(f"    Avg Trade Duration: {avg_duration_hrs:.1f} hours")
    print(f"    Trades per Week:    {trades_per_week:.1f}")
    print(f"    Trades per Month:   {trades_per_month:.1f}")
    print("\n" + "="*70)

    # 5. Plot
    import matplotlib.pyplot as plt
    
    # Prepare Trade Markers
    buy_times = [t['date'] for t in trades if t['type'] == 'BUY']
    buy_prices = [t['price'] for t in trades if t['type'] == 'BUY']
    sell_times = [t['date'] for t in trades if 'SELL' in t['type']]
    sell_prices = [t['price'] for t in trades if 'SELL' in t['type']]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    # Plot 1: Price & Trades
    ax1.plot(df_1m.index, df_1m['Close'], label='Price', color='gray', alpha=0.6, linewidth=0.8)
    
    # Overlay Buy/Sell types if any
    if buy_times:
        ax1.scatter(buy_times, buy_prices, marker='^', color='green', s=100, label='Buy Signal', zorder=5)
    if sell_times:
        ax1.scatter(sell_times, sell_prices, marker='v', color='red', s=100, label='Sell Signal', zorder=5)
        
    ax1.set_title(f"Backtest Analysis: {symbol} | Strategy: SupplyDemandRetest")
    ax1.set_ylabel("Price ($)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Equity
    ax2.plot(dates_tracked, equity_curve, label='Portfolio Value (Equity)', linewidth=2)
    ax2.fill_between(dates_tracked, initial_capital, equity_curve, alpha=0.15, color='green')
    ax2.axhline(y=initial_capital, color='gray', linestyle='--')
    ax2.set_ylabel("Account Value ($)")
    ax2.set_xlabel("Date")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('nifty_multitf_backtest.png', dpi=300)
    print("Chart saved: nifty_multitf_backtest.png")

if __name__ == "__main__":
    target_symbol = '^NSEI'
    if len(sys.argv) > 1:
        target_symbol = sys.argv[1]
    run_multi_tf_backtest(target_symbol)

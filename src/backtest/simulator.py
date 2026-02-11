"""
Unified Backtest Simulator
Runs the LIVE TradingEngine against historical data.
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.core.trading_engine import TradingEngine
from src.brokers.backtest_broker import BacktestBroker

class Simulator:
    def __init__(self, data_path: str, symbol: str, strategy_name: str = None):
        self.logger = self._setup_logger()
        self.symbol = symbol
        self.data = self._load_data(data_path)
        
        # Initialize Broker
        self.broker = BacktestBroker(initial_capital=100000.0, logger=self.logger)
        
        # Initialize Engine with Override
        self.engine = TradingEngine()
        self.engine.broker = self.broker # Dependency Injection
        self.engine.GO_LIVE = True # Enable trading logic
        self.engine.strategies = [] # Clear default strategies
        
        # Load specific strategy to test
        if strategy_name:
            self._load_strategy(strategy_name)
            
    def _setup_logger(self):
        logger = logging.getLogger("Simulator")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger
        
    def _load_data(self, path: str) -> pd.DataFrame:
        """Load CSV data."""
        self.logger.info(f"Loading data from {path}...")
        df = pd.read_csv(path)
        # Parse dates
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            # Ensure localized if needed, or naive
        return df.sort_index()

    def _load_strategy(self, name: str):
        """Dynamically load strategy."""
        # Use existing adapters
        # For prototype, we'll manually add one or use engine's list
        # For now, let's just use what's in 'adapters_basic' if possible
        # Or rely on user to pass a Strategy Class
        pass

    def run(self):
        """Run the simulation loop."""
        self.logger.info(" Starting Simulation...")
        
        # Pre-feed broker with full data (for get_history slicer)
        # TODO: Implement get_history in BacktestBroker properly
        # For now, simplistic approach: Simulator calls strategy.process directly
        
        total_bars = len(self.data)
        
        for i in range(50, total_bars): # Need warm-up
            # 1. Update Time & Price
            current_bar = self.data.iloc[i]
            current_time = self.data.index[i]
            close_price = current_bar['close']
            
            self.broker.update_market_status(self.symbol, close_price, current_time)
            
            # 2. Prepare Data Slice (Simulate Fetch)
            # Last 50 candles up to now
            df_slice = self.data.iloc[i-50:i+1].copy()
            
            # 3. Step Engine
            # We bypass fetch_data loop and call process directly for efficiency
            # But to be "Unified", we should let Engine do it.
            # Let's interact with the strategies directly for now to prove concept
            
            for strategy in self.engine.strategies:
                # Update strategy state
                strategy.process(df_slice, current_bar)
                
        self.logger.info(" Simulation Complete")
        self._print_results()

    def _print_results(self):
        print("\n=== Simulation Results ===")
        total_pnl = 0
        
        for strat in self.engine.strategies:
            stats = strat.get_stats()
            print(f"\nStrategy: {stats['name']}")
            print(f"PnL: {stats['pnl']}")
            print(f"Trades: {stats['wins'] + stats['losses']}")
            print(f"Win Rate: {stats['win_rate']}%")
            total_pnl += stats['pnl']
            
            # Print last few trades
            if stats['trades']:
                print("Last 3 Trades:")
                for t in stats['trades'][-3:]:
                    print(f"  {t['side']} {t['entry']} -> {t['exit']} ({t['reason']}) PnL: {t['pnl']}")

        print(f"\nTotal Portfolio PnL: {total_pnl:.2f}")


if __name__ == "__main__":
    # Example Usage
    sim = Simulator("sample_data.csv", "NSE:NIFTY50-INDEX")
    sim.run()

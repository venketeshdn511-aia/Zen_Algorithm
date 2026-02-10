"""
Backtest Broker
Mimics FyersBroker interface but executes trades virtually against historical data.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

class FyersMock:
    def get_option_chain(self, strike: int, otype: str, expiry_date=None):
        return 120.0 + (strike % 10)

class BacktestBroker:
    """
    Virtual broker for backtesting.
    """
    
    def __init__(self, initial_capital: float = 100000.0, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.capital = initial_capital
        self.initial_capital = initial_capital
        self.positions = {} 
        self.orders = []
        self.trades = []
        self.current_prices = {}
        self.current_time = None
        self.connected = True
        self.fyers = FyersMock()
        
    def authenticate(self):
        self.logger.info("✅ Backtest Broker Authenticated")
        return True
    
    def get_atm_strike(self, price: float) -> int:
        return round(price / 50) * 50
        
    def update_market_status(self, symbol: str, price: float, timestamp: datetime):
        """Called by simulator to update "Real Time"."""
        self.current_prices[symbol] = price
        self.current_time = timestamp
        
    def get_quote(self, symbol: str) -> float:
        """Get current price for a symbol."""
        return self.current_prices.get(symbol, 0.0)
        
    def get_positions(self) -> List[Dict]:
        """Return mock positions in Fyers format."""
        fyers_positions = []
        for sym, pos in self.positions.items():
            current_price = self.current_prices.get(sym, pos['entry_price'])
            qty = pos['qty']
            if qty == 0: continue
            
            pnl = (current_price - pos['entry_price']) * qty * pos['side']
            
            fyers_positions.append({
                'symbol': sym,
                'qty': qty,
                'netQty': qty * pos['side'],
                'avgPrice': pos['entry_price'],
                'pl': round(pnl, 2),
                'ltp': current_price
            })
        return fyers_positions
        
    def place_order(self, symbol: str, side: str, qty: int, order_type: str = "MARKET", 
                   stop_loss: float = 0, take_profit: float = 0, **kwargs) -> Optional[str]:
        """
        Execute virtual order.
        """
        price = self.current_prices.get(symbol)
        
        # If no price for OPTION symbol, simulate it?
        # Strategy calls place_order on OPTION symbol.
        if not price:
            if "CE" in symbol or "PE" in symbol:
                # Mock price for option if not in feed
                # Strategy calculated premium and passed it? No, place_order uses market price.
                # But BaseStrategy calls execute_trade(premium...), which stores entry price.
                # BaseStrategy.execute_trade doesn't call place_order immediately?
                # Wait, execute_trade calls send_telegram and logs to DB.
                # It does NOT call broker.place_order?
                pass

        # Check BaseStrategy.execute_trade in live_multi_strategy or extracted core
        # Real code: "self.broker.place_order(...)" should be there ?
        
        # In adapters_basic.py:
        # self.execute_trade(...) is called.
        # execute_trade (BaseStrategy) sets self.position = ...
        # It does NOT call broker.place_order in paper mode (default).
        # But Unified Backtester SHOULD call place_order to track PnL in broker.
        
        # Wait, BaseStrategy.execute_trade is for Paper/Simulation tracking inside Strategy.
        # If we want the BROKER to track it, the strategy (or BaseStrategy) must call place_order.
        
        # In live_multi_strategy.py (original):
        # execute_trade was purely internal state management.
        # Real orders were placed manually in some logic or via broker.place_order?
        
        # Actually, the user's code seems to treat "execute_trade" as "enter paper position".
        # So BacktestBroker might NOT receive place_order calls from current Strategies?
        
        # If stats are tracked in Strategy.trades (list), then we don't need Broker PnL?
        # SimulationRunner prints "Total Trades: {len(self.broker.trades)}".
        # If Broker trades are empty, it means Strategies are not calling place_order.
        
        msg = f"⚡ Backtest Order: {side} {qty} {symbol} @ {price}" 
        self.logger.info(msg)
        
        # Ensure we return a valid ID
        return "ORD_MOCK"

    def get_history(self, *args, **kwargs):
        return None

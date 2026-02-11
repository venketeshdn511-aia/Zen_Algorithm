"""
Fyers Paper Trading Broker
Uses LIVE Fyers data for 100% accurate simulation
"""
from src.brokers.fyers_broker import FyersBroker
from datetime import datetime
import json
import logging
import math
import time
import random

class FyersPaperBroker:
    def __init__(self, logger=None, initial_capital=100000, db_handler=None):
        self.logger = logger or logging.getLogger(__name__)
        
        # Connect to Fyers
        self.fyers = FyersBroker(logger, db_handler=db_handler)
        
        # Paper trading state
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions = {}
        self.closed_trades = []
        self.order_id_counter = 1
        
        # Real-world Brokerage & Taxes
        self.BROKERAGE_PER_ORDER = 20.0
        self.TAX_ESTIMATE_PCT = 0.0006  # 0.06% for STT, SEBI, GST etc.
        
        # Nifty constants (Weekly Options)
        self.LOT_SIZE = 65 
        self.STRIKE_INTERVAL = 50
        
        # === NEW: Slippage & Execution Config ===
        self.slippage_pct = 0.001  # 0.1% slippage for market orders
        self.retry_config = {
            'max_retries': 3,
            'base_delay': 1.0,  # seconds
            'backoff_multiplier': 2.0
        }
        
        # Stats
        self.stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'peak_capital': initial_capital,
            'api_retries': 0,  # NEW: Track retry count
            'slippage_total': 0  # NEW: Track total slippage
        }
        
        # Expiry (default to None, set by main script)
        self.expiry_date = None
        
        # Note: Fyers connection is now lazy (happens in background thread)
        self.logger.info(f" Fyers Paper Trading initialized: {initial_capital:,.2f} (Connection pending)")

    # === NEW: Slippage Modeling ===
    def _apply_slippage(self, price: float, side: str) -> float:
        """Apply realistic slippage to market orders."""
        if price <= 0:
            return price
        
        # Random slippage between 0.05% and 0.15%
        actual_slippage = self.slippage_pct * (0.5 + random.random())
        
        if side.lower() == 'buy':
            slipped_price = price * (1 + actual_slippage)  # Buy higher
        else:
            slipped_price = price * (1 - actual_slippage)  # Sell lower
        
        slippage_amount = abs(slipped_price - price)
        self.stats['slippage_total'] += slippage_amount
        
        self.logger.debug(f" Slippage: {price:.2f}  {slipped_price:.2f} ({actual_slippage*100:.3f}%)")
        
        return round(slipped_price, 2)
    
    # === NEW: Retry Logic ===
    def _execute_with_retry(self, fn, *args, **kwargs):
        """Execute function with exponential backoff retry."""
        max_retries = self.retry_config['max_retries']
        base_delay = self.retry_config['base_delay']
        multiplier = self.retry_config['backoff_multiplier']
        
        for attempt in range(max_retries):
            try:
                result = fn(*args, **kwargs)
                if result is not None:
                    return result
            except Exception as e:
                self.stats['api_retries'] += 1
                delay = base_delay * (multiplier ** attempt)
                self.logger.warning(f" API call failed (attempt {attempt+1}/{max_retries}): {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
        
        self.logger.error(f" API call failed after {max_retries} retries")
        return None

    def get_current_price(self, symbol, last_known_price=None):
        """Get current price with retry logic. Returns None on failure (not 0)."""
        result = self._execute_with_retry(self.fyers.get_current_price, symbol, last_known_price)
        # CRITICAL: Return None on failure, not 0. 
        # 0 would bypass the "if not curr_premium" checks in adapters.
        return result if result and result > 0 else None
        
    def get_latest_bars(self, symbol, timeframe='1', limit=100):
        """Get latest bars with retry logic."""
        import pandas as pd
        result = self._execute_with_retry(self.fyers.get_latest_bars, symbol, timeframe, limit)
        return result if result is not None else pd.DataFrame()

    def get_atm_strike(self, spot_price):
        return round(spot_price / self.STRIKE_INTERVAL) * self.STRIKE_INTERVAL

    def _get_default_expiry(self):
        """Get near-term Tuesday expiry in Fyers format"""
        from src.utils.date_utils import get_next_tuesday_expiry
        return get_next_tuesday_expiry()

    def submit_order(self, symbol, qty, side, order_type='MARKET', price=None, instrument=None):
        """
        Execute paper trade using REAL Fyers option chain data.
        
        Args:
            symbol: Trading symbol
            qty: Number of lots
            side: 'buy' or 'sell'
            order_type: 'MARKET' or 'LIMIT'
            price: Limit price (required for LIMIT orders)
            instrument: 'CE' or 'PE' (if creating fresh option position)
        
        Returns:
            Order result dict or None if failed
        """
        if not self.fyers.connected:
            self.logger.error("Cannot submit order - Fyers not connected")
            return None

        # 1. Get Nifty Spot
        spot_price = self.get_current_price("NIFTY")
        if spot_price == 0: 
            self.logger.error("Cannot get spot price")
            return None
        
        # 2. Determine Option
        atm_strike = self.get_atm_strike(spot_price)
        
        # Determine Instrument (CE/PE)
        if instrument:
            option_type = instrument
        else:
            option_type = 'CE' if side == 'buy' else 'PE'
        
        # Set expiry
        exp = self.expiry_date if self.expiry_date else self._get_default_expiry()
        option_symbol = f"NSE:NIFTY{exp}{atm_strike}{option_type}"
        
        # 3. Get REAL Premium (with retry)
        premium = self._execute_with_retry(
            self.fyers.get_option_chain, strike=atm_strike, option_type=option_type, expiry_date=exp
        )
        
        if not premium:
            premium = self._estimate_premium(spot_price, atm_strike, option_type)
            source = "ESTIMATED"
        else:
            source = "REAL_FYERS"

        # 4. LIMIT ORDER HANDLING
        if order_type.upper() == 'LIMIT':
            if price is None:
                self.logger.error("LIMIT order requires price parameter")
                return None
            
            # For limit orders, check if market price is favorable
            if side == 'buy' and premium > price:
                self.logger.info(f" LIMIT BUY pending: Market {premium:.2f} > Limit {price:.2f}")
                return {'status': 'pending', 'order_type': 'LIMIT', 'limit_price': price}
            elif side == 'sell' and premium < price:
                self.logger.info(f" LIMIT SELL pending: Market {premium:.2f} < Limit {price:.2f}")
                return {'status': 'pending', 'order_type': 'LIMIT', 'limit_price': price}
            
            # Limit order can be filled at limit price
            execution_price = price
            self.logger.info(f" LIMIT order filled at {price:.2f}")
        else:
            # MARKET ORDER: Apply slippage
            execution_price = self._apply_slippage(premium, side)
            self.logger.debug(f"Market order: Premium {premium:.2f}  Execution {execution_price:.2f}")

        # 5. Execute Logic
        total_shares = qty  # Expected to be absolute shares (lots * lot_size)
        order_value = total_shares * execution_price
        
        timestamp = datetime.now()
        order_id = f"PAPER_{self.order_id_counter}"
        self.order_id_counter += 1
        
        if side == 'buy':
            # Deduct Brokerage and Taxes on Entry
            entry_costs = self.BROKERAGE_PER_ORDER + (order_value * self.TAX_ESTIMATE_PCT)
            self.current_capital -= (order_value + entry_costs)
            
            self.positions[option_symbol] = {
                'order_id': order_id,
                'entry_price': premium,
                'qty': qty,
                'shares': total_shares,
                'spot_entry': spot_price,
                'entry_time': timestamp,
                'strike': atm_strike,
                'type': option_type,
                'entry_costs': entry_costs
            }
            self.logger.info(f" [BUY] {qty} lots {option_symbol} @ {premium:.2f} | Costs: {entry_costs:.2f}")

        elif side == 'sell':
            # Closing position
            if option_symbol in self.positions:
                pos = self.positions[option_symbol]
                
                # Check current premium or use execution price if provided
                exit_premium = premium if premium else self.fyers.get_option_chain(strike=pos['strike'], option_type=pos['type'])
                if not exit_premium: exit_premium = self._estimate_premium(spot_price, pos['strike'], pos['type'])
                
                # Calculate Exit Costs
                exit_value = exit_premium * pos['shares']
                exit_costs = self.BROKERAGE_PER_ORDER + (exit_value * self.TAX_ESTIMATE_PCT)
                
                pnl = exit_value - (pos['entry_price'] * pos['shares']) - pos['entry_costs'] - exit_costs
                self.current_capital += (exit_value - exit_costs)
                
                self.logger.info(f" [SELL] {option_symbol} @ {exit_premium:.2f} | Net PnL: {pnl:+.2f} (Total Costs: {pos['entry_costs'] + exit_costs:.2f})")
                
                # Update stats...
                del self.positions[option_symbol]
                
        return {'status': 'filled', 'order_id': order_id, 'price': premium}

    def _estimate_premium(self, spot, strike, otype):
        """
        Fallback premium estimation using simplified Black-Scholes
        Used when Fyers API doesn't return option prices (market closed)
        """
        import math
        
        # Approximate ATM option premium as % of spot
        # ATM options typically trade at 0.8-1.5% of spot for weekly expiry
        
        moneyness = abs(spot - strike) / spot
        
        if moneyness < 0.01:  # ATM
            base_premium = spot * 0.008  # 0.8% of spot
        elif moneyness < 0.02:  # Near ATM
            base_premium = spot * 0.005
        else:  # OTM
            base_premium = spot * 0.003
        
        # Add some volatility premium
        vol_premium = spot * 0.002 * (0.5 + 0.5 * math.exp(-moneyness * 50))
        
        premium = base_premium + vol_premium
        
        # Minimum premium floor
        premium = max(premium, 10.0)
        
        self.logger.info(f" Using estimated premium for {strike}{otype}: {premium:.2f} (market may be closed)")
        
        return round(premium, 2)

    def get_account_balance(self):
        return self.current_capital

    def get_total_pnl(self):
        """Get total PnL including both realized and unrealized from open positions."""
        # Realized PnL from closed trades
        realized = self.stats['total_pnl']
        
        # Unrealized PnL from open positions
        unrealized = 0
        for sym, pos in self.positions.items():
            try:
                current_premium = self.fyers.get_option_chain(strike=pos['strike'], option_type=pos['type'])
                if current_premium:
                    unrealized += (current_premium - pos['entry_price']) * pos['shares']
            except:
                pass  # Skip if can't get current price
        
        return realized + unrealized

    def close_all_positions(self):
        for symbol in list(self.positions.keys()):
            self.close_position(symbol)

    def close_position(self, option_symbol, qty=None):
        """
        Close a specific position by symbol directly.
        Supports partial exit if qty < position qty.
        """
        if option_symbol not in self.positions:
            self.logger.warning(f" Cannot close {option_symbol} - not found in positions")
            return False
            
        pos = self.positions[option_symbol]
        current_qty = pos['qty']
        
        # Determine exit quantity
        exit_qty = qty if qty and qty < current_qty else current_qty
        
        # Get current price for exit
        spot_price = self.get_current_price("NIFTY")
        exit_premium = self.fyers.get_option_chain(strike=pos['strike'], option_type=pos['type'])
        
        if not exit_premium: 
            exit_premium = self._estimate_premium(spot_price, pos['strike'], pos['type'])
            
        # Calculate PnL
        shares_to_close = exit_qty * self.LOT_SIZE
        pnl = (exit_premium - pos['entry_price']) * shares_to_close
        
        # Update Capital
        self.current_capital += (exit_premium * shares_to_close)
        
        self.logger.info(f" [SELL/CLOSE] {option_symbol} | Qty: {exit_qty} | @ {exit_premium:.2f} | PnL: {pnl:+.2f}")
        
        # Update stats
        self.stats['total_pnl'] += pnl
        if pnl > 0: self.stats['winning_trades'] += 1
        else: self.stats['losing_trades'] += 1
        
        if qty is None or exit_qty == current_qty:
             # Full Close
             self.stats['total_trades'] += 1 
             del self.positions[option_symbol]
        else:
             # Partial Close
             self.positions[option_symbol]['qty'] -= exit_qty
             self.positions[option_symbol]['shares'] = self.positions[option_symbol]['qty'] * self.LOT_SIZE
             self.logger.info(f" Partial Exit complete. Remaining: {self.positions[option_symbol]['qty']} lots")
        
        return True
        
    def check_token_health(self):
        """Proxy health check to underlying FyersBroker"""
        if hasattr(self, 'fyers') and self.fyers:
            return self.fyers.check_token_health()
        return {"status": "error", "message": "FyersBroker not initialized"}

    def print_daily_summary(self):
        print(f"Capital: {self.current_capital}")


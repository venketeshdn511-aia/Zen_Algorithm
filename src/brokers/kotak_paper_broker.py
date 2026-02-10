from src.brokers.kotak_broker import KotakBroker
import logging

class KotakPaperBroker(KotakBroker):
    """
    Paper Trading Wrapper for Kotak Broker.
    Uses generic KotakBroker for Data (LTP, Bars),
    but overrides Execution to be simulated (or relies on BaseStrategy).
    """
    def __init__(self, logger=None, db_handler=None, initial_capital=100000.0):
        super().__init__(logger, db_handler)
        self.paper_capital = initial_capital
        self.logger.info(f"💰 Kotak Paper Broker Initialized. Capital: {initial_capital}")

    def place_order(self, symbol, qty, side, order_type='MARKET', price=0.0, product='MIS', *args, **kwargs):
        """
        Simulate Order Placement.
        Does NOT call API.
        """
        self.logger.info(f"📝 [PAPER ORDER] {side.upper()} {qty} {symbol} @ {order_type} (Price: {price})")
        # Return a fake order response
        return {'status': 'success', 'order_id': f'PAPER_{symbol}_{side}', 'message': 'Paper Order Placed'}

    def get_account_balance(self):
        return self.paper_capital

    def check_token_health(self):
        # Still need to check connection for DATA
        super().check_token_health()

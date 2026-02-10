import alpaca_trade_api as tradeapi

class ExecutionHandler:
    def __init__(self, api: tradeapi.REST):
        self.api = api

    def submit_order(self, symbol, qty, side, order_type='market', time_in_force='gtc'):
        """Wraps the Alpaca submit_order function."""
        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force=time_in_force
            )
            print(f"Order submitted: {side} {qty} {symbol}")
            return order
        except Exception as e:
            print(f"Order failed: {e}")
            return None

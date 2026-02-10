import alpaca_trade_api as tradeapi
from datetime import datetime, timedelta

class DataHandler:
    def __init__(self, api: tradeapi.REST, symbol: str):
        self.api = api
        self.symbol = symbol

    def get_latest_bars(self, timeframe='1Min', limit=100):
        """Fetches the latest bars for the symbol."""
        # Alpaca's get_barset is deprecated in some versions, using get_bars ideally
        # But 'get_barset' is the classic trade-api way. Let's use v2 API via REST.
        # Check if we need to account for updated SDK methods.
        
        # Using the standard V2 methods
        bars = self.api.get_bars(self.symbol, timeframe, limit=limit).df
        return bars

    def get_current_price(self):
        """Fetches the latest trade price."""
        trade = self.api.get_latest_trade(self.symbol)
        return trade.price

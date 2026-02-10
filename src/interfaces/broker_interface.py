from abc import ABC, abstractmethod
import pandas as pd

class BrokerInterface(ABC):
    """
    Abstract Base Class for all Brokers (Alpaca, Zerodha, Shoonya, etc.)
    """

    @abstractmethod
    def connect(self):
        """Authenticates with the broker API."""
        pass

    @abstractmethod
    def get_latest_bars(self, symbol: str, timeframe: str = '1Min', limit: int = 100) -> pd.DataFrame:
        """Fetches historical/live bars."""
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Fetches the current LTP."""
        pass

    @abstractmethod
    def get_account_balance(self) -> float:
        """Returns the current available trading capital/equity."""
        pass

    @abstractmethod
    def submit_order(self, symbol: str, qty: int, side: str, order_type: str = 'market'):
        """Submits a buy/sell order."""
        pass
    
    @abstractmethod
    def close_all_positions(self):
        """Liquidates all open positions (Kill Switch)."""
        pass

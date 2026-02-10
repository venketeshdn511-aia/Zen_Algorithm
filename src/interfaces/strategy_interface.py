from abc import ABC, abstractmethod
import pandas as pd

class StrategyInterface(ABC):
    """
    Abstract Base Class for all Strategies.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def calculate_signal(self, df: pd.DataFrame) -> str:
        """
        Analyzes the data and returns a signal.
        Returns: 'buy', 'sell', or None
        """
        pass

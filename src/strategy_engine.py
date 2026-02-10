import pandas as pd
# # import pandas_ta as ta

class StrategyEngine:
    def __init__(self):
        pass

    def calculate_signals(self, df):
        """
        Calculates indicators and returns a signal.
        Returns: 'buy', 'sell', or None
        """
        if df.empty:
            return None

        # Calculate a simple indicator, e.g., RSI
        # pandas-ta appends to the dataframe
        df.ta.rsi(length=14, append=True)
        
        # Get latest RSI
        latest_rsi = df['RSI_14'].iloc[-1]
        
        # Simple Logic
        if latest_rsi < 30:
            return 'buy'
        elif latest_rsi > 70:
            return 'sell'
        
        return None

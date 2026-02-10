"""
Failed Auction b2 (Market Profile) - 15m
Algorithmic Logic & Concepts

User Definition: 
"Failed Auction Bullish" -> Price tries to go Up (Bullish), Fails, Breaks range but returns inside.
Action: SHORT the market.

Logic:
- Entry: Short (Sell)
- Pattern: Sweep Swing High (Resistance) + Close Below (Rejection)
- Zone: Premium Zone (Upper 50% implied by testing High)
- Trend: Price > VWAP (Reversion trade? or Failure of uptrend)
- RSI: 40-60
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class FailedAuctionStrategy(StrategyInterface):
    def __init__(self, rsi_period=14, lookback_period=20, range_period=50):
        super().__init__("Failed Auction b2")
        self.rsi_period = rsi_period
        self.lookback_period = lookback_period
        self.range_period = range_period
        self.current_status = "Initializing..."
        self.last_signal_data = {}

    def get_status(self):
        return self.current_status

    def _calculate_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calculate_vwap(self, df):
        df = df.copy()
        if 'date' not in df.columns:
            df['date'] = df.index.date
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['pv'] = df['typical_price'] * df['Volume']
        df['cum_pv'] = df.groupby('date')['pv'].cumsum()
        df['cum_vol'] = df.groupby('date')['Volume'].cumsum()
        return df['cum_pv'] / df['cum_vol']

    def detect_failed_auction_bullish(self, df):
        """
        User Definition: Failed Bullish Auction = Failed Up Move.
        Logic: Sweep Swing High & Close Below.
        """
        curr = df.iloc[-1]
        # Lookback excluding current
        past_df = df.iloc[-(self.lookback_period+1):-1]
        
        resistance_level = past_df['High'].max()
        
        # Bullish break attempt
        swept = curr['High'] > resistance_level
        # Failed to hold (Close below)
        rejected = curr['Close'] < resistance_level
        
        return (swept and rejected), resistance_level

    def detect_premium_zone(self, df):
        """Price in upper 50% of recent range (Required to test Highs)"""
        curr_price = df['Close'].iloc[-1]
        recent_df = df.iloc[-self.range_period:]
        r_high = recent_df['High'].max()
        r_low = recent_df['Low'].min()
        r_mid = (r_high + r_low) / 2
        
        is_premium = curr_price > r_mid
        return is_premium, r_low, r_high

    def calculate_signal(self, df):
        if len(df) < max(self.range_period, self.lookback_period, 50):
            self.current_status = f"Warming up ({len(df)} bars)"
            return None
        
        df = df.copy()
        df['rsi'] = self._calculate_rsi(df['Close'], self.rsi_period)
        df['vwap'] = self._calculate_vwap(df)
        
        curr = df.iloc[-1]
        close_p = curr['Close']
        rsi = curr['rsi']
        vwap = curr['vwap']
        
        # 1. RSI (40-60)
        if not (40 <= rsi <= 60):
            self.current_status = f"RSI {rsi:.1f} not in 40-60 range."
            return None
            
        # 2. VWAP (Price > VWAP as per request)
        if not (close_p > vwap):
            self.current_status = "Price below VWAP (Trend Filter)."
            return None
        
        # 3. Zone Check (Premium implied by High test)
        is_premium, r_low, r_high = self.detect_premium_zone(df)
        if not is_premium:
             self.current_status = "Price not in Premium Zone (Cannot fail high)."
             return None
             
        # 4. Failed Auction Check
        is_failed_auction, resistance_level = self.detect_failed_auction_bullish(df)
        
        self.current_status = f"Scanning... RSI:{rsi:.1f} VWAP:{vwap:.1f} Premium:Yes"

        if is_failed_auction:
            # SHORT Signal
            stop_loss = max(curr['High'], resistance_level)
            risk = stop_loss - close_p
            if risk <= 0: risk = close_p * 0.001
            target = close_p - (risk * 2.0)
            
            self.last_signal_data = {
                'side': 'sell', 'entry': close_p, 'stop_loss': stop_loss,
                'take_profit': target, 'risk': risk, 'pattern': 'Failed Auction (Bullish Failure)'
            }
            return 'sell'
            
        return None

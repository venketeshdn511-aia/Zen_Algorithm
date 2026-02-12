from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_rsi, calculate_vwap, calculate_atr
import pandas as pd
import numpy as np
import re

class FailedAuctionStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Failed Auction b2", INITIAL_CAPITAL)
        self.allowed_regimes = ['REVERSAL']
        self.risk_pct = 0.02
        self.rr_ratio = 2.0
        self.broker = broker
        self.lookback_period = 20
        self.range_period = 50
        
    def detect_premium_zone(self, df):
        """Price in upper 50% of recent range (Required to test Highs)"""
        # We need at least range_period bars
        if len(df) < self.range_period: return False, 0, 0
        
        recent_df = df.iloc[-self.range_period:]
        r_high = recent_df['high'].max()
        r_low = recent_df['low'].min()
        r_mid = (r_high + r_low) / 2
        
        curr_price = df['close'].iloc[-1]
        is_premium = curr_price > r_mid
        return is_premium, r_low, r_high

    def detect_failed_auction_bullish(self, df):
        """
        Logic: Sweep Swing High & Close Below.
        """
        if len(df) < self.lookback_period + 2: return False, 0
        
        curr = df.iloc[-1]
        # Lookback excluding current bar for resistance
        past_df = df.iloc[-(self.lookback_period+1):-1]
        
        resistance_level = past_df['high'].max()
        
        # Bullish break attempt: High > Resistance
        swept = curr['high'] > resistance_level
        # Failed to hold: Close < Resistance
        rejected = curr['close'] < resistance_level
        
        return (swept and rejected), resistance_level

    def process(self, df, current_bar):
        if len(df) < max(self.range_period, self.lookback_period, 50): 
            self.status = f"Warming up ({len(df)} bars)"
            return

        # 1. Indicators
        df['rsi'] = calculate_rsi(df['close'], 14)
        df['vwap'] = calculate_vwap(df)
        atr_series = calculate_atr(df, 14)
        atr = atr_series.iloc[-1]
        
        # Market Narrative Update
        spot_price, rsi, trend = self.update_market_status(df)
        vwap = df['vwap'].iloc[-1]
        
        if self.position is None:
            # Entry Logic
            
            # 1. RSI Filter (40-60)
            if not (40 <= rsi <= 60):
                self.status = f"{self.market_narrative} | Logic: Waiting for RSI Compression (40-60)."
                return

            # 2. VWAP Filter (Price > VWAP)
            if not (spot_price > vwap):
                self.status = f"{self.market_narrative} | Logic: Underlying below VWAP (Trend Filter)."
                return

            # 3. Premium Zone Check
            is_premium, _, r_high = self.detect_premium_zone(df)
            if not is_premium:
                self.status = f"{self.market_narrative} | Logic: Waiting for Premium Rejection near {r_high:.1f}."
                return

            # 4. Pattern Check: Failed Auction
            is_failed_auction, resistance_level = self.detect_failed_auction_bullish(df)
            
            if is_failed_auction and self.broker:
                self.status = f"Failed Auction Detected at {resistance_level:.1f}!"
                
                # Logic says SHORT the market -> Buy PE
                premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker) # side='sell' for strategy logic means we want to short underlying
                if not premium: return
                
                # Stop Loss: Resistance Level (Swing High)
                # We need to translate Spot Stop to Option Stop
                
                # Risk in Spot
                stop_loss_spot = max(curr['high'], resistance_level)
                risk_spot = stop_loss_spot - spot_price
                if risk_spot <= 0: risk_spot = spot_price * 0.001
                
                # Estimate Option Risk (Delta approx 0.5)
                risk_premium = risk_spot * 0.5
                
                stop = premium - risk_premium
                target = premium + (risk_premium * self.rr_ratio)
                
                # Size based on risk
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (risk_premium * LOT_SIZE)))
                
                self.current_strike = strike
                self.status = f"Short Signal (Failed Auction). Buying {symbol}."
                
                # We store the spot stop for trailing
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
                if self.position:
                    self.position['spot_stop'] = stop_loss_spot
                    self.position['strike'] = strike
                    
        else:
            # Exit Management
            self.update_trailing_stop(df)
            pos = self.position
            current_spot = float(df['close'].iloc[-1])
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            
            if match and self.broker:
                strike = int(match.group(1))
                otype = match.group(2)
                expiry = self.get_fyers_expiry_code()
                curr_premium = self.broker.get_option_price(strike, otype, expiry)
                if not curr_premium:
                    self.status = f"Waiting for option price: {pos['symbol']}"
                    return
                
                spot_stop = pos.get('spot_stop', 0)
                self.status = f"Active {pos['symbol']}: {curr_premium:.1f} | Spot: {current_spot:.1f}"

                # Check Spot Stop (Hard/Structural Stop)
                if current_spot >= spot_stop: # For PE Buy, if Spot goes UP to Stop
                     self.status = f"Spot Stop Hit @ {spot_stop:.1f}"
                     self.close_trade(curr_premium, 'spot_sl')
                     return

                # Check Option Targets/Stops
                if curr_premium <= pos['sl']: 
                    self.close_trade(pos['sl'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')
                else:
                    self.position['ltp'] = curr_premium

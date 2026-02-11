from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_rsi, calculate_atr
import pandas as pd
import numpy as np
import re

class AMDSetupStrategy(BaseStrategy):
    """
    AMD (Accumulation-Manipulation-Distribution) Setup Strategy.
    Detects 'Judas Swings' where price sweeps highs/lows before reversing.
    """
    
    def __init__(self, broker=None):
        super().__init__("AMD Setup", INITIAL_CAPITAL)
        self.allowed_regimes = ['ALL']
        self.risk_pct = 0.02
        self.rr_ratio = 2.0
        self.broker = broker
        self.rsi_period = 14
        self.lookback_period = 20
        self.range_period = 50
        
    def detect_amd_setup_bearish(self, df):
        """Detect Bearish AMD Pattern (Judas Swing UP then Distribution DOWN)."""
        if len(df) < self.lookback_period + 10:
            return False, 0
        
        recent = df.iloc[-self.lookback_period:]
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        range_high = recent['high'].max()
        
        # Manipulation: Recent high sweep (last 5 bars)
        last_5 = df.iloc[-5:]
        manipulation_high = last_5['high'].max()
        swept_high = manipulation_high >= range_high
        
        # Distribution: Reversal
        distributing = curr['close'] < prev['close'] and curr['close'] < manipulation_high
        
        # Rejection confirmation (Upper Wick)
        curr_body = abs(curr['close'] - curr['open'])
        curr_upper_wick = curr['high'] - max(curr['open'], curr['close'])
        rejection = curr_upper_wick > curr_body * 0.5
        
        return (swept_high and distributing and rejection), manipulation_high

    def detect_amd_setup_bullish(self, df):
        """Detect Bullish AMD Pattern (Judas Swing DOWN then Distribution UP)."""
        if len(df) < self.lookback_period + 10:
            return False, 0
        
        recent = df.iloc[-self.lookback_period:]
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        range_low = recent['low'].min()
        
        # Manipulation: Recent low sweep
        last_5 = df.iloc[-5:]
        manipulation_low = last_5['low'].min()
        swept_low = manipulation_low <= range_low
        
        # Distribution: Reversal
        distributing = curr['close'] > prev['close'] and curr['close'] > manipulation_low
        
        # Rejection confirmation (Lower Wick)
        curr_body = abs(curr['close'] - curr['open'])
        curr_lower_wick = min(curr['open'], curr['close']) - curr['low']
        rejection = curr_lower_wick > curr_body * 0.5
        
        return (swept_low and distributing and rejection), manipulation_low

    def detect_premium_zone(self, df):
        """Price in upper 50% of recent range."""
        curr_price = df['close'].iloc[-1]
        recent = df.iloc[-self.range_period:]
        r_high = recent['high'].max()
        r_low = recent['low'].min()
        r_mid = (r_high + r_low) / 2
        return curr_price > r_mid

    def detect_discount_zone(self, df):
        """Price in lower 50% of recent range."""
        curr_price = df['close'].iloc[-1]
        recent = df.iloc[-self.range_period:]
        r_high = recent['high'].max()
        r_low = recent['low'].min()
        r_mid = (r_high + r_low) / 2
        return curr_price < r_mid

    def process(self, df, current_bar):
        min_bars = max(self.range_period, self.lookback_period, 60)
        if len(df) < min_bars:
            self.status = f"Warming up ({len(df)}/{min_bars})"
            return
            
        # Indicators
        df['rsi'] = calculate_rsi(df['close'], self.rsi_period)
        atr_series = calculate_atr(df, 14)
        
        # Market Narrative Update
        spot_price, rsi, trend = self.update_market_status(df)
        atr = atr_series.iloc[-1]
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev_rsi = prev['rsi']
        
        if self.position is None:
            # SHORT (Bearish) Setup
            rsi_crossed_below_70 = prev_rsi >= 70 and rsi < 70
            is_premium = self.detect_premium_zone(df)
            is_bearish_amd, manip_high = self.detect_amd_setup_bearish(df)
            
            if rsi_crossed_below_70 and is_premium and is_bearish_amd and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker)
                if not premium: return
                
                # SL above manipulation high
                stop_loss_spot = manip_high + (atr * 0.5)
                risk_spot = stop_loss_spot - spot_price
                if risk_spot <= 0: risk_spot = atr
                
                risk_premium = risk_spot * 0.5
                stop_opt = premium - risk_premium
                target_opt = premium + (risk_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                qty = max(LOT_SIZE, int(risk_amount / (risk_premium * LOT_SIZE)) * LOT_SIZE)
                
                self.current_strike = strike
                self.status = f"AMD Bearish Signal! Shorting via {symbol}"
                self.execute_trade(premium, 'buy', stop_opt, target_opt, qty, symbol=symbol)
                if self.position: 
                    self.position['spot_stop'] = stop_loss_spot
                    self.position['strike'] = strike

            # LONG (Bullish) Setup
            rsi_crossed_above_30 = prev_rsi <= 30 and rsi > 30
            is_discount = self.detect_discount_zone(df)
            is_bullish_amd, manip_low = self.detect_amd_setup_bullish(df)
            
            if rsi_crossed_above_30 and is_discount and is_bullish_amd and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                # SL below manipulation low
                stop_loss_spot = manip_low - (atr * 0.5)
                risk_spot = spot_price - stop_loss_spot
                if risk_spot <= 0: risk_spot = atr
                
                risk_premium = risk_spot * 0.5
                stop_opt = premium - risk_premium
                target_opt = premium + (risk_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                qty = max(LOT_SIZE, int(risk_amount / (risk_premium * LOT_SIZE)) * LOT_SIZE)
                
                self.current_strike = strike
                self.status = f"AMD Bullish Signal! Longing via {symbol}"
                self.execute_trade(premium, 'buy', stop_opt, target_opt, qty, symbol=symbol)
                if self.position: 
                    self.position['spot_stop'] = stop_loss_spot
                    self.position['strike'] = strike
            
            # Scanning status: Cinematic Logic
            if is_premium:
                self.status = f"{self.market_narrative} | Pattern: Premium Sweep Zone Identified."
            elif is_discount:
                self.status = f"{self.market_narrative} | Pattern: Discount Sweep Opportunity."
            else:
                self.status = f"{self.market_narrative} | Logic: Scanning for Expansion Gaps."
            
        else:
            # Exit Management
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                
                spot_stop = pos.get('spot_stop', 0)
                current_spot = float(df['close'].iloc[-1])
                
                # Check Spot SL
                is_long = 'CE' in pos['symbol']
                if (is_long and current_spot <= spot_stop) or (not is_long and current_spot >= spot_stop):
                    self.status = f"Spot SL Hit @ {spot_stop:.1f}"
                    self.close_trade(curr_premium, 'spot_sl')
                    return

                # Check Option Targets
                if curr_premium <= pos['sl']: 
                    self.close_trade(pos['sl'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')
                else:
                    self.position['ltp'] = curr_premium
                    self.status = f"Active {pos['symbol']}: {curr_premium:.1f} | Spot: {current_spot:.1f}"

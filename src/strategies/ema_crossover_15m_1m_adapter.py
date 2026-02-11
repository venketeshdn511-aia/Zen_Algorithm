import pandas as pd
import numpy as np
import re
from datetime import datetime, time
import pytz
from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_atr, calculate_ema

class EMACrossover15m1mAdapter(BaseStrategy):
    """
    EMA Crossover Long 15m-1m Strategy Adapter for Live Engine.
    
    Logic:
    - 15m Analysis: EMA 13 > EMA 21 (Bullish Trend)
    - 15m Price > Both EMAs
    - 1m Entry: Bullish Candle (Close > Open)
    - Kill Zones: 09:15-11:00 & 13:30-15:00
    - Flexible Target: R:R 3.0 (Simplified for live)
    - Stop Loss: Entry Candle Volatility or 1m ATR
    """
    
    def __init__(self, broker=None):
        super().__init__("EMA Crossover 15m", INITIAL_CAPITAL)
        self.allowed_regimes = ['TREND']
        self.risk_pct = 0.05
        self.rr_ratio = 3.0
        self.broker = broker
        
        # Parameters
        self.ema_fast_period = 13
        self.ema_slow_period = 21
        self.mtf_resample = '15min'
        
        # State
        self.last_trade_time = None
        
    def detect_kill_zone(self, current_dt):
        """Check if time is within high-volume execution zones."""
        t = current_dt.time()
        am_start = time(9, 15)
        am_end = time(11, 0)
        pm_start = time(13, 30)
        pm_end = time(15, 0)
        
        is_am = am_start <= t <= am_end
        is_pm = pm_start <= t <= pm_end
        return is_am or is_pm

    def process(self, df, current_bar):
        """
        Process live 1-minute data 'df'.
        """
        if len(df) < 100:
            self.status = f"Warming up ({len(df)}/100 bars)..."
            return

        # 1. Resample to 15m for Analysis
        # We need completed 15m bars to be safe, or forming for aggressive.
        # Standard: Use last completed 15m bar structure.
        df_15m = df.resample(self.mtf_resample).agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()
        
        if len(df_15m) < 30:
            self.status = f"Warming 15m data ({len(df_15m)}/30)..."
            return
            
        # 2. Calculate 15m Indicators
        df_15m['ema_fast'] = calculate_ema(df_15m['close'], self.ema_fast_period)
        df_15m['ema_slow'] = calculate_ema(df_15m['close'], self.ema_slow_period)
        
        # Get latest 15m data (Last closed/forming)
        # Using iloc[-1] gives the currently forming 15m bar which updates live.
        # This is good for "Signal on 15m" in real-time.
        row_15m = df_15m.iloc[-1]
        ema_f = row_15m['ema_fast']
        ema_s = row_15m['ema_slow']
        close_15m = row_15m['close']
        
        # 3. Live 1m Data
        row_1m = df.iloc[-1]
        spot_price = float(row_1m['close'])
        
        # Update Status with "Thinking"
        trend_status = "BULLISH" if ema_f > ema_s else "BEARISH"
        condition_status = "WAIT"
        
        if self.position is None:
            # Entry Logic
            in_kill_zone = self.detect_kill_zone(row_1m.name)
            
            # Formulate thinking status
            status_msg = f"15m: {trend_status} (F:{ema_f:.0f}/S:{ema_s:.0f}) | Spot: {spot_price:.0f}"
            
            if not in_kill_zone:
                status_msg += " |  Outside Kill Zone"
            elif ema_f <= ema_s:
                status_msg += " |  No Trend Setup"
            elif spot_price <= ema_f or spot_price <= ema_s:
                status_msg += " |  Price below EMA"
            else:
                # Setup is Valid!
                # Check Confirmation: 1m Bullish Candle
                is_bullish_1m = row_1m['close'] > row_1m['open']
                if not is_bullish_1m:
                    status_msg += " |  Waiting 1m Green Candle"
                else:
                    status_msg += " |  TRIGGER: Bullish 1m"
                    condition_status = "TRIGGER"
            
            self.status = status_msg
            
            # Execute if Triggered
            if condition_status == "TRIGGER" and self.broker:
                # Calculate Stop (Entry Candle Volatility)
                c_high = row_1m['high']
                c_low = row_1m['low']
                c_close = row_1m['close']
                risk_per_share = max(abs(c_close - c_low), abs(c_high - c_close))
                risk_per_share = max(5.0, risk_per_share) # Min 5 pts
                
                # Option Selection
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium:
                    self.status += " |  Option Chain Error"
                    return
                
                # Map Spot Risk to Premium Risk (Delta approx 0.5)
                premium_stop_dist = risk_per_share * 0.5
                stop = premium - premium_stop_dist
                target = premium + (premium_stop_dist * self.rr_ratio)
                
                # Position Sizing
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (premium_stop_dist * LOT_SIZE)))
                qty = lots * LOT_SIZE
                
                self.status = f" Executing {symbol} @ {premium:.1f} | Tgt: {target:.1f}"
                self.execute_trade(premium, 'buy', stop, target, qty, symbol=symbol)
                
        else:
            # Manage Position
            # Use Spot-Based Trailing from BaseStrategy
            self.update_trailing_stop(df)
            
            pos = self.position
            symbol = pos['symbol']
            entry = pos['entry']
            
            # Fetch Current Premium
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                # Use base strategy helper if available or raw call
                curr_premium = self.broker.get_current_price(symbol, entry)
                if not curr_premium: return
                
                spot_stop = pos.get('spot_stop', 0)
                
                self.status = (
                    f" {symbol}: {curr_premium:.1f} (Entry: {entry:.1f}) | "
                    f"Spot Trail: {spot_stop:.0f} | " 
                    f"15m Trend: {trend_status}"
                )
                
                # Exits
                # 1. Spot Trail
                if self.check_spot_trailing_stop(df):
                    self.status = f" Spot Trail Hit @ {spot_stop:.0f}. Exiting."
                    self.close_trade(curr_premium, 'trailing_stop')
                    return
                
                # 2. Hard Stop/Target (Premium based)
                if curr_premium <= pos['stop']:
                    self.close_trade(curr_premium, 'stop_loss')
                elif curr_premium >= pos['target']:
                    self.close_trade(curr_premium, 'target_hit')

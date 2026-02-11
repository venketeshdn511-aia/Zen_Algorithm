import pandas as pd
import numpy as np
import re
from datetime import datetime, time
import pytz
from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_atr, calculate_ema

class EMACrossoverShort15m5mAdapter(BaseStrategy):
    """
    EMA Crossover Short 15m-5m Strategy Adapter for Live Engine.
    
    Logic:
    - 15m Analysis: EMA 8 < EMA 50 (Bearish Trend)
    - 15m Price < Both EMAs
    - 5m Entry: Bearish Candle (Close < Open)
    - Risk/Reward: 4.9
    - Trailing SL: Enabled (Spot based)
    """
    
    def __init__(self, broker=None):
        super().__init__("EMA Crossover Short 15m", INITIAL_CAPITAL)
        self.allowed_regimes = ['TREND']
        self.risk_pct = 0.05
        self.rr_ratio = 4.9
        self.broker = broker
        
        # Parameters
        self.ema_fast_period = 8
        self.ema_slow_period = 50
        self.mtf_resample = '15min'
        self.entry_resample = '5min'
        
    def detect_kill_zone(self, current_dt):
        """Check if time is within high-volume execution zones."""
        t = current_dt.time()
        # Same as Long strategy for consistency unless specified
        am_start = time(9, 15)
        am_end = time(11, 0)
        pm_start = time(13, 30)
        pm_end = time(15, 0)
        
        return (am_start <= t <= am_end) or (pm_start <= t <= pm_end)

    def process(self, df, current_bar):
        """
        Process live 1-minute data 'df'.
        """
        if len(df) < 150:
            self.status = f"Warming up ({len(df)}/150 bars)..."
            return

        # 1. Resample to 15m for Analysis
        df_15m = df.resample(self.mtf_resample).agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()
        
        if len(df_15m) < 60:
            self.status = f"Warming 15m data ({len(df_15m)}/60)..."
            return
            
        # 2. Resample to 5m for Entry Confirmation
        df_5m = df.resample(self.entry_resample).agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna()

        # 3. Calculate 15m Indicators
        df_15m['ema_fast'] = calculate_ema(df_15m['close'], self.ema_fast_period)
        df_15m['ema_slow'] = calculate_ema(df_15m['close'], self.ema_slow_period)
        
        row_15m = df_15m.iloc[-1]
        ema_f = row_15m['ema_fast']
        ema_s = row_15m['ema_slow']
        
        # 4. Live 1m Data
        row_1m = df.iloc[-1]
        spot_price = float(row_1m['close'])
        
        # Trend State
        trend_status = "BEARISH" if ema_f < ema_s else "BULLISH"
        
        if self.position is None:
            # Entry Logic
            in_kill_zone = self.detect_kill_zone(row_1m.name)
            
            # Formulate thinking status
            status_msg = f"15m: {trend_status} (F:{ema_f:.0f}/S:{ema_s:.0f}) | Spot: {spot_price:.0f}"
            
            if not in_kill_zone:
                status_msg += " |  Outside Kill Zone"
            elif ema_f >= ema_s:
                status_msg += " |  No Short Setup"
            elif spot_price >= ema_f or spot_price >= ema_s:
                status_msg += " |  Price above EMA"
            else:
                # Setup is Valid!
                # Check 5m Confirmation: Bearish Candle
                row_5m = df_5m.iloc[-1]
                is_bearish_5m = row_5m['close'] < row_5m['open']
                if not is_bearish_5m:
                    status_msg += " |  Waiting 5m Red Candle"
                else:
                    status_msg += " |  TRIGGER: Bearish 5m"
                    # Execution
                    if self.broker:
                        # Stop Loss (Entry Candle Volatility)
                        c_high = row_1m['high']
                        c_low = row_1m['low']
                        c_close = row_1m['close']
                        risk_per_share = max(abs(c_close - c_low), abs(c_high - c_close))
                        risk_per_share = max(5.0, risk_per_share)
                        
                        # Selection: PE for Short
                        premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker) # sell side means PE
                        if not premium:
                            self.status = status_msg + " |  Option Chain Error"
                            return
                        
                        premium_stop_dist = risk_per_share * 0.5
                        stop = premium - premium_stop_dist
                        target = premium + (premium_stop_dist * self.rr_ratio)
                        
                        risk_amount = self.capital * self.risk_pct
                        lots = max(1, int(risk_amount / (premium_stop_dist * LOT_SIZE)))
                        
                        self.status = f" Executing {symbol} @ {premium:.1f}"
                        # Note: We buy PE for a Short setup in this engine's current structure
                        self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
            
            self.status = status_msg
            
        else:
            # Manage Position
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.get_current_price(symbol, pos['entry'])
                if not curr_premium: return
                
                spot_stop = pos.get('spot_stop', 0)
                self.status = f" {symbol}: {curr_premium:.1f} | Trail: {spot_stop:.0f}"
                
                if self.check_spot_trailing_stop(df):
                    self.close_trade(curr_premium, 'trailing_stop')
                    return
                
                if curr_premium <= pos['stop']:
                    self.close_trade(curr_premium, 'stop_loss')
                elif curr_premium >= pos['target']:
                    self.close_trade(curr_premium, 'target_hit')

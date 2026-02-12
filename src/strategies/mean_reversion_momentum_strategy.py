"""
Mean Reversion + Momentum Strategy for Nifty 50 Options
Target: 70% Win Rate with 1:2 Risk-Reward Ratio

Core Components (Optimized v3):
- RSI Mean Reversion (14 period): Oversold (<30) / Overbought (>70)
- VWAP Confirmation: Price above/below fair value
- EMA Crossover (9/21): Momentum direction confirmation
- Trend Filter: EMA 200 (Long > EMA200, Short < EMA200)
- Volume Filter: 1.1x average volume validation
- ADX Filter: Only trade in trending markets (ADX > 20)
- ATR-based Risk Management: SL=1.5x ATR, TP=3x ATR
- Time Filter: Avoid 2:30-3:00 PM high volatility period
"""
from src.interfaces.strategy_interface import StrategyInterface
import pandas as pd
import numpy as np
from datetime import datetime, time
import pytz


class MeanReversionMomentumStrategy(StrategyInterface):
    """
    Mean Reversion + Momentum Confirmation Strategy.
    
    Entry Logic:
    - LONG: RSI crosses above 35 (from oversold) + Price > VWAP + EMA9 > EMA21 + Volume > 1.2x avg
    - SHORT: RSI crosses below 65 (from overbought) + Price < VWAP + EMA9 < EMA21 + Volume > 1.2x avg
    
    Risk Management:
    - Stop Loss: 1x ATR
    - Target 1: 2x ATR (1:2 RR) - Exit 50%
    - Target 2: 3x ATR (1:3 RR) - Exit remaining 50%
    """
    
    def __init__(self, rsi_period=14, ema_fast=9, ema_slow=21, atr_period=14,
                 volume_ma_period=20, volume_threshold=1.1, rsi_oversold=30, 
                 rsi_overbought=70, max_trades_per_day=3, use_scaled_exit=False,
                 backtest_mode=False, adx_period=14, adx_threshold=20,
                 atr_stop_multiplier=1.5, atr_target_multiplier=3.0,
                 ema_trend=200):
        super().__init__("MeanReversionMomentum")
        
        # Backtest mode disables time filters and uses bar dates for counters
        self.backtest_mode = backtest_mode
        
        # Indicator Parameters
        self.rsi_period = rsi_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.ema_trend = ema_trend  # EMA 200 for Trend Filter
        self.atr_period = atr_period
        self.volume_ma_period = volume_ma_period
        self.volume_threshold = volume_threshold
        
        # RSI Thresholds
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        
        # Trade Management
        self.max_trades_per_day = max_trades_per_day
        self.use_scaled_exit = use_scaled_exit  # Future: 50/50 exit at T1/T2
        
        # ADX Filter Parameters
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        
        # ATR Multipliers (Optimized)
        self.atr_stop_multiplier = atr_stop_multiplier  # 1.5x ATR for SL
        self.atr_target_multiplier = atr_target_multiplier  # 3x ATR for TP
        
        # State Tracking
        self.current_status = "Initializing..."
        self.daily_trades = 0
        self.last_trade_date = None
        self.last_stop_loss = None
        self.last_take_profit = None
        self.last_take_profit_2 = None  # For scaled exits
        
        # IST Timezone for time filters
        self.ist = pytz.timezone('Asia/Kolkata')
        
        # Trading Hours (IST) - Optimized to avoid high volatility
        self.market_open = time(9, 30)    # 9:30 AM
        self.market_close = time(15, 15)  # 3:15 PM
        self.entry_start = time(9, 45)    # Avoid first 15 min
        self.entry_end = time(14, 30)     # Avoid 2:30-3:00 PM high volatility
        
    def get_status(self):
        return self.current_status
    
    def get_stop_loss(self):
        return self.last_stop_loss
    
    def get_take_profit(self):
        return self.last_take_profit
    
    def get_take_profit_2(self):
        return self.last_take_profit_2
        
    # ============= INDICATOR CALCULATIONS =============
    
    def _calculate_rsi(self, series, period=14):
        """Calculate Relative Strength Index."""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 0.0001)  # Avoid division by zero
        return 100 - (100 / (1 + rs))
    
    def _calculate_ema(self, series, period):
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()
    
    def _calculate_vwap(self, df):
        """
        Calculate Volume Weighted Average Price.
        Uses simple cumulative VWAP for stability.
        """
        # Typical price
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        
        # Simple cumulative VWAP (more robust for backtesting)
        cum_tpv = (tp * df['Volume']).cumsum()
        cum_vol = df['Volume'].cumsum()
        
        vwap = cum_tpv / (cum_vol + 0.0001)
        return vwap

    
    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range."""
        high = df['High']
        low = df['Low']
        close = df['Close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def _calculate_adx(self, df, period=14):
        """
        Calculate Average Directional Index (ADX) for trend strength.
        ADX > 20 indicates a trending market.
        """
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        # Calculate +DM and -DM
        plus_dm = high.diff()
        minus_dm = low.diff().abs() * -1
        
        plus_dm = plus_dm.where((plus_dm > minus_dm.abs()) & (plus_dm > 0), 0)
        minus_dm = minus_dm.abs().where((minus_dm.abs() > plus_dm) & (minus_dm < 0), 0)
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Smoothed values
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / (atr + 0.0001))
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / (atr + 0.0001))
        
        # DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    def _check_time_filter(self, current_time=None):
        """
        Check if current time is within valid trading window.
        Avoids first/last 15 minutes of market hours.
        """
        if current_time is None:
            current_time = datetime.now(self.ist).time()
        
        # Must be within entry window
        return self.entry_start <= current_time <= self.entry_end
    
    def _reset_daily_counter(self, current_date):
        """Reset daily trade counter at start of new day."""
        if self.last_trade_date != current_date:
            self.daily_trades = 0
            self.last_trade_date = current_date
    
    # ============= MAIN SIGNAL CALCULATION =============
    
    def calculate_signal(self, df, minor_df=None, symbol=None):
        """
        Main signal calculation with multi-confirmation logic.
        
        df: DataFrame with OHLCV data (5-minute timeframe recommended)
        minor_df: Optional lower timeframe for precise entry (not used currently)
        symbol: Optional symbol identifier
        
        Returns: 'buy', 'sell', or None
        """
        if df.empty or len(df) < max(self.rsi_period, self.ema_slow, self.atr_period) + 5:
            self.current_status = f"Warming indicators ({len(df)}/{self.ema_slow + 5} bars needed)"
            return None
        
        # Create working copy
        df = df.copy()
        
        # Normalize column names to Title Case if needed
        if 'close' in df.columns:
            df = df.rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low',
                'close': 'Close', 'volume': 'Volume'
            })
        
        # Check time filter
        current_time = None
        if isinstance(df.index, pd.DatetimeIndex):
            try:
                last_bar_time = df.index[-1]
                if hasattr(last_bar_time, 'time'):
                    current_time = last_bar_time.time()
            except Exception as e:
                print(f" [MRM] Time extraction error: {e}")
        
        # Time filter (skip in backtest mode, use bar time for live)
        if not self.backtest_mode:
            if not self._check_time_filter(current_time):
                self.current_status = "Outside trading window (9:45 AM - 3:00 PM)"
                return None
        else:
            # In backtest, check bar time is within trading hours
            if current_time is not None:
                if not (self.entry_start <= current_time <= self.entry_end):
                    return None
        
        # Reset daily trade counter (use bar date in backtest, current date in live)
        if self.backtest_mode and isinstance(df.index, pd.DatetimeIndex):
            current_date = df.index[-1].date()
        else:
            current_date = datetime.now(self.ist).date()
        self._reset_daily_counter(current_date)
        
        # Check max trades limit
        if self.daily_trades >= self.max_trades_per_day:
            self.current_status = f"Max daily trades reached ({self.max_trades_per_day})"
            return None
        
        # ============= CALCULATE ALL INDICATORS =============
        
        # RSI
        df['RSI'] = self._calculate_rsi(df['Close'], self.rsi_period)
        
        # EMAs
        df['EMA_Fast'] = self._calculate_ema(df['Close'], self.ema_fast)
        df['EMA_Slow'] = self._calculate_ema(df['Close'], self.ema_slow)
        df['EMA_Trend'] = self._calculate_ema(df['Close'], self.ema_trend)
        
        # VWAP
        df['VWAP'] = self._calculate_vwap(df)
        
        # ATR
        df['ATR'] = self._calculate_atr(df, self.atr_period)
        
        # ADX (Trend Strength Filter)
        df['ADX'] = self._calculate_adx(df, self.adx_period)
        
        # Volume Moving Average
        df['Volume_MA'] = df['Volume'].rolling(window=self.volume_ma_period).mean()
        
        # Get current and previous bar values
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        current_price = float(curr['Close'])
        current_rsi = float(curr['RSI'])
        prev_rsi = float(prev['RSI'])
        current_vwap = float(curr['VWAP'])
        ema_fast = float(curr['EMA_Fast'])
        ema_slow = float(curr['EMA_Slow'])
        ema_trend = float(curr['EMA_Trend'])
        current_volume = float(curr['Volume'])
        avg_volume = float(curr['Volume_MA'])
        current_atr = float(curr['ATR'])
        current_adx = float(curr['ADX']) if not pd.isna(curr['ADX']) else 0
        
        # ============= CHECK CONDITIONS =============
        
        signal = None
        
        # ADX Trend Filter - Only trade in trending markets
        adx_confirmed = current_adx >= self.adx_threshold
        
        # Trend Regime Filter (EMA 200)
        bullish_regime = current_price > ema_trend
        bearish_regime = current_price < ema_trend
        
        # Volume Confirmation
        volume_confirmed = current_volume > (avg_volume * self.volume_threshold)
        
        # EMA Momentum
        ema_bullish = ema_fast > ema_slow
        ema_bearish = ema_fast < ema_slow
        
        # VWAP Position
        above_vwap = current_price > current_vwap
        below_vwap = current_price < current_vwap
        
        # RSI Crossover Conditions
        rsi_oversold_cross = prev_rsi < self.rsi_oversold and current_rsi >= self.rsi_oversold
        rsi_overbought_cross = prev_rsi > self.rsi_overbought and current_rsi <= self.rsi_overbought
        
        # Build status message
        status_parts = []
        status_parts.append(f"RSI: {current_rsi:.1f}")
        status_parts.append(f"{'Above' if above_vwap else 'Below'} VWAP")
        status_parts.append(f"EMA: {'Bull' if ema_bullish else 'Bear'}")
        status_parts.append(f"ADX: {current_adx:.1f}{'*' if adx_confirmed else ''}")
        status_parts.append(f"Vol: {'OK' if volume_confirmed else 'X'}")
        
        self.current_status = " | ".join(status_parts)
        
        # ADX must confirm trending market for all entries
        if not adx_confirmed:
            self.current_status = f"ADX too low ({current_adx:.1f} < {self.adx_threshold}). Waiting for trend..."
            return None
        
        # ============= LONG SIGNAL =============
        # RSI crosses above oversold + At least 2 of 3 confirmations (VWAP, EMA, Volume)
        
        if rsi_oversold_cross:
            # Check Regime First
            if not bullish_regime:
                self.current_status = f"Long filtered: Counter-trend (Price < EMA{self.ema_trend})"
                return None
            confirmations = sum([above_vwap, ema_bullish, volume_confirmed])
            self.current_status = f"RSI Oversold Reclaim ({current_rsi:.1f}). Confirmations: {confirmations}/3"
            
            if confirmations >= 2:
                # At least 2 confirmations - go!
                self.current_status = f">>> BUY Signal: RSI {current_rsi:.1f} + {confirmations}/3 confirmations"
                
                # Calculate ATR-based SL/TP (Optimized: 1.5x SL, 3x TP)
                self.last_stop_loss = current_price - (self.atr_stop_multiplier * current_atr)
                self.last_take_profit = current_price + (self.atr_target_multiplier * current_atr)
                self.last_take_profit_2 = current_price + (self.atr_target_multiplier * 1.5 * current_atr)
                
                self.daily_trades += 1
                signal = 'buy'
                
            else:
                missing = []
                if not above_vwap: missing.append("VWAP")
                if not ema_bullish: missing.append("EMA")
                if not volume_confirmed: missing.append("Vol")
                self.current_status = f"RSI Reclaim filtered: Need 2/3 confirmations, missing {', '.join(missing)}"
        
        # ============= SHORT SIGNAL =============
        # RSI crosses below overbought + At least 2 of 3 confirmations
        
        elif rsi_overbought_cross:
            # Check Regime First
            if not bearish_regime:
                self.current_status = f"Short filtered: Counter-trend (Price > EMA{self.ema_trend})"
                return None
            confirmations = sum([below_vwap, ema_bearish, volume_confirmed])
            self.current_status = f"RSI Overbought Rejection ({current_rsi:.1f}). Confirmations: {confirmations}/3"
            
            if confirmations >= 2:
                # At least 2 confirmations - go!
                self.current_status = f">>> SELL Signal: RSI {current_rsi:.1f} + {confirmations}/3 confirmations"
                
                # Calculate ATR-based SL/TP (Optimized: 1.5x SL, 3x TP)
                self.last_stop_loss = current_price + (self.atr_stop_multiplier * current_atr)
                self.last_take_profit = current_price - (self.atr_target_multiplier * current_atr)
                self.last_take_profit_2 = current_price - (self.atr_target_multiplier * 1.5 * current_atr)
                
                self.daily_trades += 1
                signal = 'sell'
                
            else:
                missing = []
                if not below_vwap: missing.append("VWAP")
                if not ema_bearish: missing.append("EMA")
                if not volume_confirmed: missing.append("Vol")
                self.current_status = f"RSI Rejection filtered: Need 2/3 confirmations, missing {', '.join(missing)}"
        
        # ============= ALTERNATIVE: RSI ZONE ENTRIES =============
        # When RSI is in deep oversold/overbought zones with momentum confirmation
        
        elif current_rsi < 30 and ema_bullish and volume_confirmed and bullish_regime:
            # Deep oversold + bullish momentum = accumulation
            self.current_status = f">>> BUY Signal: Deep Oversold RSI {current_rsi:.1f} + EMA Bull + Volume"
            
            self.last_stop_loss = current_price - (self.atr_stop_multiplier * current_atr)
            self.last_take_profit = current_price + (self.atr_target_multiplier * current_atr)
            self.last_take_profit_2 = current_price + (self.atr_target_multiplier * 1.5 * current_atr)
            
            self.daily_trades += 1
            signal = 'buy'
            
        elif current_rsi > 70 and ema_bearish and volume_confirmed and bearish_regime:
            # Deep overbought + bearish momentum = distribution
            self.current_status = f">>> SELL Signal: Deep Overbought RSI {current_rsi:.1f} + EMA Bear + Volume"
            
            self.last_stop_loss = current_price + (self.atr_stop_multiplier * current_atr)
            self.last_take_profit = current_price - (self.atr_target_multiplier * current_atr)
            self.last_take_profit_2 = current_price - (self.atr_target_multiplier * 1.5 * current_atr)
            
            self.daily_trades += 1
            signal = 'sell'
        
        # ============= PROXIMITY ALERTS =============
        
        elif current_rsi < 40 and current_rsi > self.rsi_oversold:
            self.current_status = f"RSI approaching oversold ({current_rsi:.1f}). Monitoring for entry..."
        elif current_rsi > 60 and current_rsi < self.rsi_overbought:
            self.current_status = f"RSI approaching overbought ({current_rsi:.1f}). Monitoring for entry..."
        
        return signal
    
    def get_signal_details(self):
        """Return detailed signal information for logging/debugging."""
        return {
            'status': self.current_status,
            'stop_loss': self.last_stop_loss,
            'take_profit_1': self.last_take_profit,
            'take_profit_2': self.last_take_profit_2,
            'daily_trades': self.daily_trades,
            'max_trades': self.max_trades_per_day
        }

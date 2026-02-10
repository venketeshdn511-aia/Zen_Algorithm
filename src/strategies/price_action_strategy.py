"""
Price Action Intraday Strategy for Nifty50 Options
Based on pure price-action methodology inspired by "The Indian Trader" channel.

Setup Types:
1. Breakouts - Clean breaks above resistance or below support with volume
2. Reversals - Reversal candles (hammer, engulfing) at key S/R levels
3. Range Bounces - Trades within well-defined support/resistance ranges
4. Fake-outs (Traps) - Failed breakouts that quickly reverse

Entry Triggers:
- Reversal candles at pivot points
- Volume-confirmed breakouts
- Touches of intraday pivot zones (P, S1, S2, R1, R2)

Exit Logic:
- Profit targets at next S/R level (1:2 R:R minimum)
- Trailing stops after 50% move achieved
- Time-based exit at 3:00 PM IST (avoid EOD risk)

Risk Management:
- 1-2% risk per trade
- Daily loss limit: 2% of capital
- Position sizing based on stop distance
"""
from src.interfaces.strategy_interface import StrategyInterface
import pandas as pd
import numpy as np
from datetime import time


class PriceActionStrategy(StrategyInterface):
    """
    Pure Price-Action Intraday Strategy for Nifty50.
    Focuses on S/R zones, pivot points, candlestick patterns, and volume.
    """
    
    def __init__(self, min_rr_ratio=2.0, use_volume_filter=True, pivot_buffer_pct=0.001):
        """
        Initialize the Price Action Strategy.
        
        Args:
            min_rr_ratio: Minimum reward:risk ratio for entries (default 2.0)
            use_volume_filter: Require volume confirmation for breakouts
            pivot_buffer_pct: Buffer around pivot levels (0.1% default)
        """
        super().__init__("PriceActionStrategy")
        
        self.min_rr_ratio = min_rr_ratio
        self.use_volume_filter = use_volume_filter
        self.pivot_buffer_pct = pivot_buffer_pct
        
        # State
        self.current_status = "Initializing..."
        self.pivots = {}  # {symbol: {'P': x, 'R1': x, 'R2': x, 'S1': x, 'S2': x}}
        self.swing_levels = {}  # {symbol: {'swing_highs': [], 'swing_lows': []}}
        self.last_signal_info = {}  # Store entry details for SL/TP
        
        # Exit times (IST)
        self.exit_time = time(15, 0)  # 3:00 PM IST
        self.no_new_trades_after = time(14, 30)  # No new trades after 2:30 PM
        
    def get_status(self):
        return self.current_status
    
    def get_stop_loss(self):
        return self.last_signal_info.get('stop_loss')
    
    def get_take_profit(self):
        return self.last_signal_info.get('take_profit')
    
    # ===================== PIVOT CALCULATIONS =====================
    
    def _calculate_pivots(self, df, sym_key):
        """
        Calculate Standard Pivot Points from Previous Day's Range (PDR).
        Pivot = (H + L + C) / 3
        R1 = 2 * P - L, R2 = P + (H - L)
        S1 = 2 * P - H, S2 = P - (H - L)
        """
        if df.empty or len(df) < 2:
            return
        
        # Group by date
        df_copy = df.copy()
        df_copy['date'] = df_copy.index.date
        daily_groups = df_copy.groupby('date')
        
        sorted_dates = sorted(list(daily_groups.groups.keys()))
        if len(sorted_dates) < 2:
            return
        
        # Get yesterday's data
        yesterday = sorted_dates[-2]
        yesterday_df = daily_groups.get_group(yesterday)
        
        h = yesterday_df['High'].max()
        l = yesterday_df['Low'].min()
        c = yesterday_df['Close'].iloc[-1]
        
        # Calculate pivots
        p = (h + l + c) / 3
        r1 = 2 * p - l
        r2 = p + (h - l)
        r3 = r1 + (h - l)
        s1 = 2 * p - h
        s2 = p - (h - l)
        s3 = s1 - (h - l)
        
        self.pivots[sym_key] = {
            'P': p, 'R1': r1, 'R2': r2, 'R3': r3,
            'S1': s1, 'S2': s2, 'S3': s3,
            'PDH': h, 'PDL': l
        }
    
    def _get_nearest_pivot(self, price, sym_key, direction='any'):
        """
        Get the nearest pivot level to the current price.
        direction: 'above', 'below', or 'any'
        """
        if sym_key not in self.pivots:
            return None, None
        
        pivots = self.pivots[sym_key]
        min_dist = float('inf')
        nearest_level = None
        nearest_name = None
        
        for name, level in pivots.items():
            if direction == 'above' and level <= price:
                continue
            if direction == 'below' and level >= price:
                continue
            
            dist = abs(price - level)
            if dist < min_dist:
                min_dist = dist
                nearest_level = level
                nearest_name = name
        
        return nearest_name, nearest_level
    
    # ===================== SWING LEVEL DETECTION =====================
    
    def _detect_swing_levels(self, df, sym_key, lookback=20):
        """
        Detect recent swing highs and lows.
        A swing high is a high surrounded by lower highs.
        A swing low is a low surrounded by higher lows.
        """
        if len(df) < lookback + 2:
            return
        
        swing_highs = []
        swing_lows = []
        
        # Look for swings in recent data
        for i in range(-lookback, -2):
            try:
                prev_high = df['High'].iloc[i-1]
                curr_high = df['High'].iloc[i]
                next_high = df['High'].iloc[i+1]
                
                prev_low = df['Low'].iloc[i-1]
                curr_low = df['Low'].iloc[i]
                next_low = df['Low'].iloc[i+1]
                
                # Swing High
                if curr_high > prev_high and curr_high > next_high:
                    swing_highs.append({
                        'level': curr_high,
                        'time': df.index[i],
                        'tested': False
                    })
                
                # Swing Low
                if curr_low < prev_low and curr_low < next_low:
                    swing_lows.append({
                        'level': curr_low,
                        'time': df.index[i],
                        'tested': False
                    })
            except IndexError:
                continue
        
        # Keep most recent 5 swings
        self.swing_levels[sym_key] = {
            'swing_highs': swing_highs[-5:],
            'swing_lows': swing_lows[-5:]
        }
    
    def _get_nearest_swing(self, price, sym_key, swing_type='high'):
        """Get nearest untested swing level."""
        if sym_key not in self.swing_levels:
            return None
        
        swings = self.swing_levels[sym_key]
        levels = swings['swing_highs'] if swing_type == 'high' else swings['swing_lows']
        
        min_dist = float('inf')
        nearest = None
        
        for swing in levels:
            if swing['tested']:
                continue
            dist = abs(price - swing['level'])
            if dist < min_dist:
                min_dist = dist
                nearest = swing
        
        return nearest
    
    # ===================== CANDLESTICK PATTERN DETECTION =====================
    
    def _is_hammer(self, candle, direction='bullish'):
        """
        Detect Hammer (bullish) or Shooting Star (bearish).
        Hammer: Small body at top, long lower wick (>60% of range)
        Shooting Star: Small body at bottom, long upper wick
        """
        o, h, l, c = float(candle['Open']), float(candle['High']), float(candle['Low']), float(candle['Close'])
        
        range_val = h - l
        if range_val == 0:
            return False
        
        body = abs(c - o)
        body_pct = body / range_val
        
        if body_pct > 0.35:  # Body too large
            return False
        
        if direction == 'bullish':
            # Long lower wick, close near high
            lower_wick = min(o, c) - l
            upper_wick = h - max(o, c)
            return (lower_wick / range_val >= 0.60) and (upper_wick / range_val <= 0.15)
        else:
            # Long upper wick, close near low
            upper_wick = h - max(o, c)
            lower_wick = min(o, c) - l
            return (upper_wick / range_val >= 0.60) and (lower_wick / range_val <= 0.15)
    
    def _is_engulfing(self, curr, prev, direction='bullish'):
        """
        Detect Engulfing Pattern.
        Bullish: Red candle followed by larger green candle that engulfs it
        Bearish: Green candle followed by larger red candle that engulfs it
        """
        c_o, c_c = float(curr['Open']), float(curr['Close'])
        p_o, p_c = float(prev['Open']), float(prev['Close'])
        
        if direction == 'bullish':
            prev_red = p_c < p_o
            curr_green = c_c > c_o
            engulfs = c_o <= p_c and c_c >= p_o
            return prev_red and curr_green and engulfs
        else:
            prev_green = p_c > p_o
            curr_red = c_c < c_o
            engulfs = c_o >= p_c and c_c <= p_o
            return prev_green and curr_red and engulfs
    
    def _is_reversal_candle(self, curr, prev, direction='bullish'):
        """Check for any reversal candle pattern."""
        if direction == 'bullish':
            return self._is_hammer(curr, 'bullish') or self._is_engulfing(curr, prev, 'bullish')
        else:
            return self._is_hammer(curr, 'bearish') or self._is_engulfing(curr, prev, 'bearish')
    
    # ===================== BREAKOUT & FAKE-OUT DETECTION =====================
    
    def _is_breakout(self, df, level, direction='up', lookback=3):
        """
        Detect clean breakout with volume confirmation.
        - Price closes beyond level
        - Current volume > 1.5x average volume
        - Strong body (>50% of candle range)
        """
        if len(df) < lookback + 20:
            return False
        
        curr = df.iloc[-1]
        c = float(curr['Close'])
        o = float(curr['Open'])
        h = float(curr['High'])
        l = float(curr['Low'])
        
        range_val = h - l
        if range_val == 0:
            return False
        
        body_pct = abs(c - o) / range_val
        
        # Volume check
        vol_avg = df['Volume'].rolling(20).mean().iloc[-1]
        vol_curr = float(curr['Volume'])
        vol_spike = (vol_curr > vol_avg * 1.5) if self.use_volume_filter and vol_avg > 0 else True
        
        if direction == 'up':
            # Close above level with strong green candle
            return c > level and c > o and body_pct >= 0.50 and vol_spike
        else:
            # Close below level with strong red candle
            return c < level and c < o and body_pct >= 0.50 and vol_spike
    
    def _is_fakeout(self, df, level, direction='up', lookback=3):
        """
        Detect fake-out (bull/bear trap).
        - Recent bar(s) broke beyond level
        - Current bar reverses back inside
        - Ideally with decreasing volume on breakout
        """
        if len(df) < lookback + 1:
            return False
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        c_c = float(curr['Close'])
        c_o = float(curr['Open'])
        p_h = float(prev['High'])
        p_l = float(prev['Low'])
        p_c = float(prev['Close'])
        
        if direction == 'up':
            # Bull trap: Previous bar broke above, current reverses back
            prev_broke = p_h > level
            curr_back = c_c < level
            curr_red = c_c < c_o
            return prev_broke and curr_back and curr_red
        else:
            # Bear trap: Previous bar broke below, current reverses back
            prev_broke = p_l < level
            curr_back = c_c > level
            curr_green = c_c > c_o
            return prev_broke and curr_back and curr_green
    
    # ===================== RANGE DETECTION =====================
    
    def _is_range_market(self, df, lookback=20):
        """
        Detect if market is ranging (sideways).
        Range = High-Low range < 0.5% AND no clear trend.
        """
        if len(df) < lookback:
            return False, None, None
        
        recent = df.iloc[-lookback:]
        range_high = recent['High'].max()
        range_low = recent['Low'].min()
        
        range_pct = (range_high - range_low) / range_low
        
        # Check for lack of trend (closing prices oscillate)
        closes = recent['Close'].values
        ups = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
        downs = len(closes) - 1 - ups
        
        # Range if: small range AND mixed direction
        is_ranging = range_pct < 0.008 and (0.35 < ups / len(closes) < 0.65)
        
        return is_ranging, range_high, range_low
    
    # ===================== TIME FILTERS =====================
    
    def _is_trading_allowed(self, timestamp):
        """Check if current time allows new trades."""
        try:
            curr_time = timestamp.time()
            return curr_time < self.no_new_trades_after
        except:
            return True
    
    def _should_exit_by_time(self, timestamp):
        """Check if position should be closed due to time."""
        try:
            curr_time = timestamp.time()
            return curr_time >= self.exit_time
        except:
            return False
    
    # ===================== INDICATORS (ATR & ADX) =====================

    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range (ATR)."""
        if len(df) < period + 1:
            return 0.0
        
        df = df.copy()
        df['h-l'] = df['High'] - df['Low']
        df['h-pc'] = abs(df['High'] - df['Close'].shift(1))
        df['l-pc'] = abs(df['Low'] - df['Close'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        return df['tr'].rolling(period).mean().iloc[-1]

    def _calculate_adx(self, df, period=14):
        """
        Calculate ADX and DI+, DI- to gauge trend strength and direction.
        Returns: (adx, plus_di, minus_di)
        """
        if len(df) < period * 2:
            return 0.0, 0.0, 0.0
            
        df = df.copy()
        
        # True Range
        df['h-l'] = df['High'] - df['Low']
        df['h-pc'] = abs(df['High'] - df['Close'].shift(1))
        df['l-pc'] = abs(df['Low'] - df['Close'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        
        # Directional Movement
        df['up_move'] = df['High'] - df['High'].shift(1)
        df['down_move'] = df['Low'].shift(1) - df['Low']
        
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
        
        # Smoothed
        tr_smooth = df['tr'].rolling(period).sum()
        plus_dm_smooth = df['plus_dm'].rolling(period).sum()
        minus_dm_smooth = df['minus_dm'].rolling(period).sum()
        
        # DI
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean().iloc[-1]
        
        return adx, plus_di.iloc[-1], minus_di.iloc[-1]

    # ===================== SIGNAL CALCULATION =====================
    
    def calculate_signal(self, major_df, minor_df=None, symbol=None):
        """
        Main signal calculation.
        """
        if major_df.empty or len(major_df) < 60:
            return None
        
        major_df = major_df.copy()
        execution_df = minor_df.copy() if minor_df is not None and not minor_df.empty else major_df
        
        sym_key = symbol if symbol else 'DEFAULT'
        
        # Get current price and timestamp
        current_bar = execution_df.iloc[-1]
        prev_bar = execution_df.iloc[-2] if len(execution_df) > 1 else current_bar
        current_price = float(current_bar['Close'])
        timestamp = execution_df.index[-1]
        
        # Time filter
        if not self._is_trading_allowed(timestamp):
            self.current_status = "No new trades after 2:30 PM"
            return None
        
        # Calculate pivots and swing levels
        self._calculate_pivots(major_df, sym_key)
        self._detect_swing_levels(major_df, sym_key)
        
        if sym_key not in self.pivots:
            self.current_status = "Waiting for pivot data..."
            return None
        
        pivots = self.pivots[sym_key]
        
        # --- NEW: Calculate Indicators for Optimization ---
        atr = self._calculate_atr(execution_df, 14)
        adx, di_plus, di_minus = self._calculate_adx(execution_df, 14)
        
        is_strong_trend = adx > 25
        is_bullish_trend = is_strong_trend and (di_plus > di_minus)
        is_bearish_trend = is_strong_trend and (di_minus > di_plus)
        
        # Calculate volume MA for confirmation
        if 'VOL_MA_20' not in major_df.columns:
            major_df['VOL_MA_20'] = major_df['Volume'].rolling(20).mean()
        
        signal = None
        
        # ============ SETUP 1: REVERSAL AT SUPPORT ============
        # Filter: Don't catch falling knife in strong bearish trend
        if not is_bearish_trend:
            support_levels = [pivots['S1'], pivots['S2'], pivots['PDL']]
            for support in support_levels:
                buffer = support * self.pivot_buffer_pct
                
                # Price near support
                if abs(current_price - support) <= buffer or current_bar['Low'] <= support:
                    if self._is_reversal_candle(current_bar, prev_bar, 'bullish'):
                        target_name, target = self._get_nearest_pivot(current_price, sym_key, 'above')
                        if target:
                            # OPTIMIZED: ATR-based Stop
                            stop_loss = current_bar['Low'] - (1.5 * atr) 
                            risk = current_price - stop_loss
                            reward = target - current_price
                            
                            if risk > 0 and reward / risk >= self.min_rr_ratio:
                                self.last_signal_info = {
                                    'stop_loss': stop_loss,
                                    'take_profit': target,
                                    'entry': current_price,
                                    'setup': 'reversal_at_support',
                                    'risk_reward': reward / risk
                                }
                                self.current_status = f"BUY: Reversal at support {support:.0f} (ADX: {adx:.1f})"
                                signal = 'buy'
                                break
        
        if signal: return signal
        
        # ============ SETUP 2: REVERSAL AT RESISTANCE ============
        # Filter: Don't short strong bullish trend
        if not is_bullish_trend:
            resistance_levels = [pivots['R1'], pivots['R2'], pivots['PDH']]
            for resistance in resistance_levels:
                buffer = resistance * self.pivot_buffer_pct
                
                if abs(current_price - resistance) <= buffer or current_bar['High'] >= resistance:
                    if self._is_reversal_candle(current_bar, prev_bar, 'bearish'):
                        target_name, target = self._get_nearest_pivot(current_price, sym_key, 'below')
                        if target:
                            # OPTIMIZED: ATR-based Stop
                            stop_loss = current_bar['High'] + (1.5 * atr)
                            risk = stop_loss - current_price
                            reward = current_price - target
                            
                            if risk > 0 and reward / risk >= self.min_rr_ratio:
                                self.last_signal_info = {
                                    'stop_loss': stop_loss,
                                    'take_profit': target,
                                    'entry': current_price,
                                    'setup': 'reversal_at_resistance',
                                    'risk_reward': reward / risk
                                }
                                self.current_status = f"SELL: Reversal at resistance {resistance:.0f} (ADX: {adx:.1f})"
                                signal = 'sell'
                                break
        
        if signal: return signal
        
        # ============ SETUP 3: BREAKOUT ============
        # Check for breakout above PDH or R1
        # Filter: Prefer breakouts in trend direction
        if not is_bearish_trend:
            for res in [pivots['PDH'], pivots['R1']]:
                if self._is_breakout(execution_df, res, 'up'):
                    target_name, target = self._get_nearest_pivot(current_price, sym_key, 'above')
                    if target and target > current_price * 1.002:
                        # OPTIMIZED: ATR-based Stop
                        stop_loss = current_price - (1.5 * atr)
                        risk = current_price - stop_loss
                        reward = target - current_price
                        
                        if risk > 0 and reward / risk >= self.min_rr_ratio:
                            self.last_signal_info = {
                                'stop_loss': stop_loss,
                                'take_profit': target,
                                'entry': current_price,
                                'setup': 'breakout_up',
                                'risk_reward': reward / risk
                            }
                            self.current_status = f"BUY: Breakout above {res:.0f}"
                            signal = 'buy'
                            break
        
        if signal: return signal
        
        # Check for breakdown below PDL or S1
        if not is_bullish_trend:
            for sup in [pivots['PDL'], pivots['S1']]:
                if self._is_breakout(execution_df, sup, 'down'):
                    target_name, target = self._get_nearest_pivot(current_price, sym_key, 'below')
                    if target and target < current_price * 0.998:
                        # OPTIMIZED: ATR-based Stop
                        stop_loss = current_price + (1.5 * atr)
                        risk = stop_loss - current_price
                        reward = current_price - target
                        
                        if risk > 0 and reward / risk >= self.min_rr_ratio:
                            self.last_signal_info = {
                                'stop_loss': stop_loss,
                                'take_profit': target,
                                'entry': current_price,
                                'setup': 'breakout_down',
                                'risk_reward': reward / risk
                            }
                            self.current_status = f"SELL: Breakdown below {sup:.0f}"
                            signal = 'sell'
                            break
        
        if signal: return signal
        
        # ============ SETUP 4: FAKE-OUT (TRAP) ============
        # Failures of breakouts against the trend are high probability
        
        # Bull trap at resistance (Bearish signal)
        # Ideal if trend is Down or Neutral
        if not is_bullish_trend:
            for res in [pivots['PDH'], pivots['R1']]:
                if self._is_fakeout(execution_df, res, 'up'):
                    target = pivots['S1']
                    # OPTIMIZED: ATR-based Stop
                    stop_loss = current_bar['High'] + (1.0 * atr) # Tight stop for traps
                    risk = stop_loss - current_price
                    reward = current_price - target
                    
                    if risk > 0 and reward / risk >= self.min_rr_ratio:
                        self.last_signal_info = {
                            'stop_loss': stop_loss,
                            'take_profit': target,
                            'entry': current_price,
                            'setup': 'bull_trap',
                            'risk_reward': reward / risk
                        }
                        self.current_status = f"SELL: Bull trap at {res:.0f}"
                        signal = 'sell'
                        break
        
        if signal: return signal
        
        # Bear trap at support (Bullish signal)
        # Ideal if trend is Up or Neutral
        if not is_bearish_trend:
            for sup in [pivots['PDL'], pivots['S1']]:
                if self._is_fakeout(execution_df, sup, 'down'):
                    target = pivots['R1']
                    # OPTIMIZED: ATR-based Stop
                    stop_loss = current_bar['Low'] - (1.0 * atr)
                    risk = current_price - stop_loss
                    reward = target - current_price
                    
                    if risk > 0 and reward / risk >= self.min_rr_ratio:
                        self.last_signal_info = {
                            'stop_loss': stop_loss,
                            'take_profit': target,
                            'entry': current_price,
                            'setup': 'bear_trap',
                            'risk_reward': reward / risk
                        }
                        self.current_status = f"BUY: Bear trap at {sup:.0f}"
                        signal = 'buy'
                        break
        
        if signal: return signal
        
        # ============ SETUP 5: RANGE BOUNCE ============
        # Filter: STRICT NO TRADE if Strong Trend (ADX > 25)
        if not is_strong_trend:
            is_ranging, range_high, range_low = self._is_range_market(execution_df, 30)
            
            if is_ranging:
                buffer = (range_high - range_low) * 0.1
                
                # Buy at range low
                if current_bar['Low'] <= range_low + buffer:
                    if self._is_reversal_candle(current_bar, prev_bar, 'bullish'):
                        # OPTIMIZED: ATR-based Stop
                        stop_loss = current_bar['Low'] - (1.0 * atr)
                        target = range_high - buffer
                        risk = current_price - stop_loss
                        reward = target - current_price
                        
                        if risk > 0 and reward / risk >= 1.5:
                            self.last_signal_info = {
                                'stop_loss': stop_loss,
                                'take_profit': target,
                                'entry': current_price,
                                'setup': 'range_bounce_buy',
                                'risk_reward': reward / risk
                            }
                            self.current_status = f"BUY: Range bounce at {range_low:.0f}"
                            signal = 'buy'
                
                # Sell at range high
                elif current_bar['High'] >= range_high - buffer:
                    if self._is_reversal_candle(current_bar, prev_bar, 'bearish'):
                        # OPTIMIZED: ATR-based Stop
                        stop_loss = current_bar['High'] + (1.0 * atr)
                        target = range_low + buffer
                        risk = stop_loss - current_price
                        reward = current_price - target
                        
                        if risk > 0 and reward / risk >= 1.5:
                            self.last_signal_info = {
                                'stop_loss': stop_loss,
                                'take_profit': target,
                                'entry': current_price,
                                'setup': 'range_bounce_sell',
                                'risk_reward': reward / risk
                            }
                            self.current_status = f"SELL: Range bounce at {range_high:.0f}"
                            signal = 'sell'
        
        if not signal:
            self.current_status = f"Scanning... Price: {current_price:.0f}, ADX: {adx:.1f}"
        
        return signal
    
    def get_pivot_summary(self, symbol=None):
        """Return current pivot levels for debugging/dashboard."""
        sym_key = symbol if symbol else 'DEFAULT'
        return self.pivots.get(sym_key, {})

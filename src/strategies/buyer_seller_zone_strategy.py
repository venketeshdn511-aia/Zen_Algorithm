"""
Buyer/Seller Zone (Supply/Demand) Strategy for Nifty 50
Identifies institutional buying/selling zones and trades bounces, rejections, and breakout-retests.
"""
from src.interfaces.strategy_interface import StrategyInterface
import pandas as pd
import numpy as np


class BuyerSellerZoneStrategy(StrategyInterface):
    """
    Supply/Demand Zone Strategy with RSI/MACD/Volume confirmations.
    
    Entry Types:
    1. Bounce/Rejection: Price enters zone, forms reversal candle, exits zone
    2. Breakout + Retest: Price breaks zone, retests, fails to reclaim
    """
    
    def __init__(self, rsi_period=14, ema_period=50, volume_ma_period=20, 
                 use_ema_filter=False, min_rr_ratio=2.0): # Default EMA filter to False
        super().__init__("BuyerSellerZoneStrategy")
        
        # Parameters
        self.rsi_period = rsi_period
        self.ema_period = ema_period
        self.volume_ma_period = volume_ma_period
        self.use_ema_filter = use_ema_filter
        self.min_rr_ratio = min_rr_ratio
        
        # Zone storage: {symbol: [zone_dict, ...]}
        self.buyer_zones = {}  # Demand zones (support)
        self.seller_zones = {}  # Supply zones (resistance)
        
        # For breakout+retest tracking
        self.broken_buyer_zones = {}  # Zones that were broken down
        self.broken_seller_zones = {}  # Zones that were broken up
        
        # Status for dashboard
        self.current_status = "Initializing..."
        
        # SL/TP outputs
        self.last_stop_loss = 0.0
        self.last_take_profit = 0.0
        self.last_entry_price = 0.0
    
    def get_status(self):
        return self.current_status
    
    def get_stop_loss(self):
        return self.last_stop_loss
    
    def get_take_profit(self):
        return self.last_take_profit
    
    # ==================== INDICATOR CALCULATIONS ====================
    
    def _calculate_rsi(self, series, period=14):
        """Calculate RSI indicator."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        return 100 - (100 / (1 + rs))
    
    def _calculate_ema(self, series, period):
        """Calculate Exponential Moving Average."""
        return series.ewm(span=period, adjust=False).mean()
    
    def _calculate_macd(self, series, fast=12, slow=26, signal=9):
        """Calculate MACD, Signal line, and Histogram."""
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range."""
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    # ==================== ZONE DETECTION ====================
    
    def _detect_zones(self, df, sym_key):
        """
        Detect Buyer (Demand) and Seller (Supply) zones from impulse moves.
        
        Buyer Zone: Area before large bullish impulse candle with volume spike.
        Seller Zone: Area before large bearish impulse candle with volume spike.
        """
        if len(df) < 5:
            return
        
        # Initialize zone lists if needed
        if sym_key not in self.buyer_zones:
            self.buyer_zones[sym_key] = []
        if sym_key not in self.seller_zones:
            self.seller_zones[sym_key] = []
        if sym_key not in self.broken_buyer_zones:
            self.broken_buyer_zones[sym_key] = []
        if sym_key not in self.broken_seller_zones:
            self.broken_seller_zones[sym_key] = []
        
        # Calculate volume moving average
        vol_ma = df['Volume'].rolling(self.volume_ma_period).mean()
        
        # Look at the impulse candle (-2) and base candle (-3)
        if len(df) < 4:
            return
            
        impulse = df.iloc[-2]
        base = df.iloc[-3]
        
        # Impulse candle metrics
        imp_open = float(impulse['Open'])
        imp_close = float(impulse['Close'])
        imp_high = float(impulse['High'])
        imp_low = float(impulse['Low'])
        imp_volume = float(impulse['Volume'])
        
        imp_range = imp_high - imp_low
        if imp_range == 0:
            return
            
        imp_body = abs(imp_close - imp_open)
        body_pct = imp_body / imp_range
        
        # Volume check
        avg_vol = float(vol_ma.iloc[-2]) if not pd.isna(vol_ma.iloc[-2]) else imp_volume
        vol_ratio = imp_volume / avg_vol if avg_vol > 0 else 1.0
        
        # Ultra-relaxed impulse criteria: >40% body and 1.2x volume for maximum frequency
        is_impulse = body_pct >= 0.40 and vol_ratio >= 1.2
        
        # Minimum impulse size: at least 0.1% move (25 points on Nifty ~25000)
        min_impulse_size = float(df['Close'].iloc[-5:].mean()) * 0.001
        if imp_body < min_impulse_size:
            return
        
        if not is_impulse:
            return
        
        # Base candle metrics
        base_open = float(base['Open'])
        base_close = float(base['Close'])
        base_high = float(base['High'])
        base_low = float(base['Low'])
        
        # === BULLISH IMPULSE -> Create BUYER Zone ===
        if imp_close > imp_open:
            zone = {
                'type': 'BUYER',
                'top': base_high,  # Include upper wick
                'bottom': base_low,
                'created_at': impulse.name,
                'tested': False,
                'status': 'active',
                'retest_count': 0
            }
            # Avoid duplicates
            if not any(z['created_at'] == zone['created_at'] for z in self.buyer_zones[sym_key]):
                self.buyer_zones[sym_key].append(zone)
        
        # === BEARISH IMPULSE -> Create SELLER Zone ===
        elif imp_close < imp_open:
            zone = {
                'type': 'SELLER',
                'top': base_high,
                'bottom': base_low,  # Include lower wick
                'created_at': impulse.name,
                'tested': False,
                'status': 'active',
                'retest_count': 0
            }
            if not any(z['created_at'] == zone['created_at'] for z in self.seller_zones[sym_key]):
                self.seller_zones[sym_key].append(zone)
        
        # Cleanup old zones (keep last 20)
        if len(self.buyer_zones[sym_key]) > 20:
            self.buyer_zones[sym_key] = self.buyer_zones[sym_key][-20:]
        if len(self.seller_zones[sym_key]) > 20:
            self.seller_zones[sym_key] = self.seller_zones[sym_key][-20:]
    
    def _check_zone_breaks(self, df, sym_key):
        """
        Check if any zones have been broken and move them to broken lists.
        A zone is broken when price closes strongly beyond it.
        """
        if len(df) < 2:
            return
            
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        curr_close = float(curr['Close'])
        curr_open = float(curr['Open'])
        curr_high = float(curr['High'])
        curr_low = float(curr['Low'])
        prev_close = float(prev['Close'])
        
        curr_range = curr_high - curr_low
        curr_body = abs(curr_close - curr_open)
        is_strong_candle = (curr_body / curr_range >= 0.60) if curr_range > 0 else False
        
        # Check BUYER zone breaks (price breaks below)
        for zone in list(self.buyer_zones.get(sym_key, [])):
            if zone['status'] != 'active':
                continue
            
            close_below = curr_close < zone['bottom']
            prev_close_below = prev_close < zone['bottom']
            
            # Strong break or consecutive closes below
            if (close_below and is_strong_candle) or (close_below and prev_close_below):
                zone['status'] = 'broken'
                zone['broken_at'] = curr.name
                self.broken_buyer_zones.setdefault(sym_key, []).append(zone)
                self.buyer_zones[sym_key].remove(zone)
        
        # Check SELLER zone breaks (price breaks above)
        for zone in list(self.seller_zones.get(sym_key, [])):
            if zone['status'] != 'active':
                continue
            
            close_above = curr_close > zone['top']
            prev_close_above = prev_close > zone['top']
            
            if (close_above and is_strong_candle) or (close_above and prev_close_above):
                zone['status'] = 'broken'
                zone['broken_at'] = curr.name
                self.broken_seller_zones.setdefault(sym_key, []).append(zone)
                self.seller_zones[sym_key].remove(zone)
        
        # Cleanup old broken zones
        for key in [sym_key]:
            if key in self.broken_buyer_zones and len(self.broken_buyer_zones[key]) > 10:
                self.broken_buyer_zones[key] = self.broken_buyer_zones[key][-10:]
            if key in self.broken_seller_zones and len(self.broken_seller_zones[key]) > 10:
                self.broken_seller_zones[key] = self.broken_seller_zones[key][-10:]
    
    # ==================== SIGNAL DETECTION ====================
    
    def _is_bullish_reversal(self, curr, prev):
        """
        Check for bullish reversal candle patterns:
        - Bullish engulfing
        - Pin bar / hammer
        """
        c_open = float(curr['Open'])
        c_close = float(curr['Close'])
        c_high = float(curr['High'])
        c_low = float(curr['Low'])
        
        p_open = float(prev['Open'])
        p_close = float(prev['Close'])
        
        # Must be green candle
        if c_close <= c_open:
            return False
        
        c_range = c_high - c_low
        if c_range == 0:
            return False
        
        c_body = c_close - c_open
        lower_wick = c_open - c_low
        upper_wick = c_high - c_close
        
        # Pin bar / Hammer: Long lower wick, close in upper 40%
        close_position = (c_close - c_low) / c_range
        is_pin_bar = lower_wick > c_body * 1.5 and close_position >= 0.60
        
        # Bullish engulfing: Current body engulfs previous
        is_engulfing = (p_close < p_open) and (c_close > p_open) and (c_open < p_close)
        
        return is_pin_bar or is_engulfing
    
    def _is_bearish_reversal(self, curr, prev):
        """
        Check for bearish reversal candle patterns:
        - Bearish engulfing
        - Shooting star
        """
        c_open = float(curr['Open'])
        c_close = float(curr['Close'])
        c_high = float(curr['High'])
        c_low = float(curr['Low'])
        
        p_open = float(prev['Open'])
        p_close = float(prev['Close'])
        
        # Must be red candle
        if c_close >= c_open:
            return False
        
        c_range = c_high - c_low
        if c_range == 0:
            return False
        
        c_body = c_open - c_close
        lower_wick = c_close - c_low
        upper_wick = c_high - c_open
        
        # Shooting star: Long upper wick, close in lower 40%
        close_position = (c_close - c_low) / c_range
        is_shooting_star = upper_wick > c_body * 1.5 and close_position <= 0.40
        
        # Bearish engulfing
        is_engulfing = (p_close > p_open) and (c_close < p_open) and (c_open > p_close)
        
        return is_shooting_star or is_engulfing
    
    def calculate_signal(self, major_df, minor_df=None, symbol=None):
        """
        Main signal calculation.
        
        major_df: Higher timeframe for zone identification (5m/15m)
        minor_df: Lower timeframe for execution (optional, uses major if None)
        
        Returns: 'buy', 'sell', or None
        """
        if major_df.empty or len(major_df) < 60:
            self.current_status = f"Warming indicators ({len(major_df)}/60 bars)"
            return None
        
        major_df = major_df.copy()
        exec_df = minor_df.copy() if minor_df is not None and not minor_df.empty else major_df
        
        sym_key = symbol if symbol else 'DEFAULT'
        
        # Time Filter: Only trade between 09:30 and 15:00
        curr_time = exec_df.iloc[-1].name.time()
        if curr_time < pd.Timestamp("09:30").time() or curr_time > pd.Timestamp("15:00").time():
            self.current_status = "Market hours filter (09:30-15:00)"
            return None
        
        # === CALCULATE INDICATORS ===
        if 'RSI' not in major_df.columns:
            major_df['RSI'] = self._calculate_rsi(major_df['Close'], self.rsi_period)
        
        if 'EMA_50' not in major_df.columns:
            major_df['EMA_50'] = self._calculate_ema(major_df['Close'], self.ema_period)
        
        if 'Volume_MA' not in major_df.columns:
            major_df['Volume_MA'] = major_df['Volume'].rolling(self.volume_ma_period).mean()
        
        macd, macd_signal, macd_hist = self._calculate_macd(major_df['Close'])
        major_df['MACD'] = macd
        major_df['MACD_Signal'] = macd_signal
        major_df['MACD_Hist'] = macd_hist
        
        if 'ATR' not in major_df.columns:
            major_df['ATR'] = self._calculate_atr(major_df)
        
        # === DETECT NEW ZONES ===
        self._detect_zones(major_df, sym_key)
        
        # === CHECK FOR ZONE BREAKS ===
        self._check_zone_breaks(exec_df, sym_key)
        
        # === GET CURRENT VALUES ===
        curr = exec_df.iloc[-1]
        prev = exec_df.iloc[-2] if len(exec_df) > 1 else curr
        
        current_price = float(curr['Close'])
        current_low = float(curr['Low'])
        current_high = float(curr['High'])
        current_volume = float(curr['Volume'])
        
        rsi = float(major_df['RSI'].iloc[-1])
        ema_50 = float(major_df['EMA_50'].iloc[-1])
        macd_hist_curr = float(major_df['MACD_Hist'].iloc[-1])
        macd_hist_prev = float(major_df['MACD_Hist'].iloc[-2]) if len(major_df) > 1 else 0
        avg_volume = float(major_df['Volume_MA'].iloc[-1]) if not pd.isna(major_df['Volume_MA'].iloc[-1]) else current_volume
        atr = float(major_df['ATR'].iloc[-1]) if not pd.isna(major_df['ATR'].iloc[-1]) else 20.0
        
        # Trend determination
        trend = "Bullish" if current_price > ema_50 else "Bearish"
        self.current_status = f"Scanning zones (Trend: {trend}, RSI: {rsi:.1f})"
        
        signal = None
        
        # ==================== BOUNCE/REJECTION TRADES ====================
        
        # === CHECK BUYER ZONES (Long on bounce) ===
        for zone in self.buyer_zones.get(sym_key, []):
            if zone['status'] != 'active' or zone['tested']:
                continue
            
            # EMA filter (optional)
            if self.use_ema_filter and current_price < ema_50:
                continue
            
            # Check if price entered zone
            entered_zone = current_low <= zone['top']
            
            if entered_zone:
                self.current_status = f"Price in BUYER Zone ({zone['bottom']:.0f}-{zone['top']:.0f})"
                
                # Conditions for BUY signal (STRICTER):
                # 1. Bullish reversal candle (required)
                # 2. RSI oversold (< 35) - intraday threshold
                # 3. Close above zone (rejection) - required
                # 4. MACD bullish + Volume confirmation - need 2 of 3
                
                is_reversal = self._is_bullish_reversal(curr, prev)
                rsi_oversold = rsi < 45  # Ultra aggressive: was 40
                closed_above = current_price > zone['top']
                volume_ok = current_volume > avg_volume * 0.8  # Relaxed: was 1.0x
                
                # MACD confirmation (histogram turning up)
                macd_bullish = macd_hist_curr > macd_hist_prev
                
                # Relaxed: Only Reversal + RSI OR Reversal + Momentum
                if is_reversal and closed_above and (rsi_oversold or macd_bullish or volume_ok):
                    # v6: Structural SL using 1.5x ATR for better noise tolerance
                    sl_buffer = max(atr * 1.5, (zone['top'] - zone['bottom']) * 0.3)
                    self.last_stop_loss = zone['bottom'] - sl_buffer
                    risk = current_price - self.last_stop_loss
                    self.last_take_profit = current_price + (risk * self.min_rr_ratio)
                    self.last_entry_price = current_price
                    
                    zone['tested'] = True
                    zone['status'] = 'filled'
                    signal = 'buy'
                    self.current_status = f"BUY Signal: Buyer Zone Bounce at {current_price:.0f}"
                    return signal
        
        # === CHECK SELLER ZONES (Short on rejection) ===
        for zone in self.seller_zones.get(sym_key, []):
            if zone['status'] != 'active' or zone['tested']:
                continue
            
            # EMA filter
            if self.use_ema_filter and current_price > ema_50:
                continue
            
            # Check if price entered zone
            entered_zone = current_high >= zone['bottom']
            
            if entered_zone:
                self.current_status = f"Price in SELLER Zone ({zone['bottom']:.0f}-{zone['top']:.0f})"
                
                # Conditions for SELL signal (STRICTER):
                # 1. Bearish reversal candle (required)
                # 2. RSI overbought (> 65) - intraday threshold
                # 3. Close below zone (rejection) - required
                # 4. MACD bearish + Volume confirmation - need momentum
                
                is_reversal = self._is_bearish_reversal(curr, prev)
                rsi_overbought = rsi > 55  # Ultra aggressive: was 60
                closed_below = current_price < zone['bottom']
                volume_ok = current_volume > avg_volume * 0.8  # Relaxed: was 1.0x
                
                # MACD confirmation (histogram turning down)
                macd_bearish = macd_hist_curr < macd_hist_prev
                
                # Relaxed: Only Reversal + RSI OR Reversal + Momentum
                if is_reversal and closed_below and (rsi_overbought or macd_bearish or volume_ok):
                    # v6: Structural SL using 1.5x ATR
                    sl_buffer = max(atr * 1.5, (zone['top'] - zone['bottom']) * 0.3)
                    self.last_stop_loss = zone['top'] + sl_buffer
                    risk = self.last_stop_loss - current_price
                    self.last_take_profit = current_price - (risk * self.min_rr_ratio)
                    self.last_entry_price = current_price
                    
                    zone['tested'] = True
                    zone['status'] = 'filled'
                    signal = 'sell'
                    self.current_status = f"SELL Signal: Seller Zone Rejection at {current_price:.0f}"
                    return signal
        
        # ==================== BREAKOUT + RETEST TRADES ====================
        
        # === BROKEN BUYER ZONES (Short on failed retest) ===
        for zone in self.broken_buyer_zones.get(sym_key, []):
            if zone.get('retest_traded'):
                continue
            
            # Wait for retest: price rallies back to zone
            retesting = current_high >= zone['bottom'] and current_price < zone['top']
            
            if retesting:
                zone['retest_count'] = zone.get('retest_count', 0) + 1
                
                # Check for rejection on retest
                is_rejection = self._is_bearish_reversal(curr, prev)
                failed_reclaim = current_price < zone['bottom']
                
                if is_rejection and failed_reclaim:
                    buffer = (zone['top'] - zone['bottom']) * 0.1
                    self.last_stop_loss = zone['top'] + buffer
                    risk = self.last_stop_loss - current_price
                    self.last_take_profit = current_price - (risk * self.min_rr_ratio)
                    self.last_entry_price = current_price
                    
                    zone['retest_traded'] = True
                    signal = 'sell'
                    self.current_status = f"SELL Signal: Failed Retest of Broken Buyer Zone"
                    return signal
        
        # === BROKEN SELLER ZONES (Long on failed retest) ===
        for zone in self.broken_seller_zones.get(sym_key, []):
            if zone.get('retest_traded'):
                continue
            
            # Wait for retest: price pulls back to zone
            retesting = current_low <= zone['top'] and current_price > zone['bottom']
            
            if retesting:
                zone['retest_count'] = zone.get('retest_count', 0) + 1
                
                # Check for rejection on retest
                is_rejection = self._is_bullish_reversal(curr, prev)
                failed_breakdown = current_price > zone['top']
                
                if is_rejection and failed_breakdown:
                    buffer = (zone['top'] - zone['bottom']) * 0.1
                    self.last_stop_loss = zone['bottom'] - buffer
                    risk = current_price - self.last_stop_loss
                    self.last_take_profit = current_price + (risk * self.min_rr_ratio)
                    self.last_entry_price = current_price
                    
                    zone['retest_traded'] = True
                    signal = 'buy'
                    self.current_status = f"BUY Signal: Failed Retest of Broken Seller Zone"
                    return signal
        
        return signal
    
    def get_zones_summary(self, symbol=None):
        """Return summary of active zones for debugging/dashboard."""
        sym_key = symbol if symbol else 'DEFAULT'
        return {
            'buyer_zones': len(self.buyer_zones.get(sym_key, [])),
            'seller_zones': len(self.seller_zones.get(sym_key, [])),
            'broken_buyer_zones': len(self.broken_buyer_zones.get(sym_key, [])),
            'broken_seller_zones': len(self.broken_seller_zones.get(sym_key, []))
        }

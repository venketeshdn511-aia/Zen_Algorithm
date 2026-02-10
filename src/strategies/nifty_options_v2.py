
from src.interfaces.strategy_interface import StrategyInterface
import pandas as pd
# import pandas_ta as ta

class NiftyOptionsStrategyV2(StrategyInterface):
    """
    Nifty Options V2 Strategy - Pure Price Action / Institutional Logic.
    Focus: Impulse Moves, Unmitigated Zones, Liquidity Sweeps.
    """
    def __init__(self):
        super().__init__("NiftyOptionsStrategyV2")
        self.zones = {} # {symbol: [{'type': 'BUY/SELL', 'top': float, 'bottom': float, 'created_at': time, 'tested': bool}]}
        self.current_status = "Initializing..."
        
    def get_status(self):
        return self.current_status
        
    def _get_pdr(self, df):
        """Get Previous Day Range (High, Low)"""
        if df.empty: return None, None
        # Group by Date
        daily_groups = df.groupby(df.index.date)
        # Get yesterday (sorted dates)
        sorted_dates = sorted(list(daily_groups.groups.keys()))
        if len(sorted_dates) < 2: return None, None
        
        yesterday_df = daily_groups.get_group(sorted_dates[-2])
        return yesterday_df['High'].max(), yesterday_df['Low'].min()

    def _is_strong_trend(self, last_candles):
        """
        Check for 2 consecutive strong candles (>60% body) in same direction.
        Expects last 2 candles as DataFrame slice.
        """
        if len(last_candles) < 2: return False
        
        c1 = last_candles.iloc[-2] # Previous
        c2 = last_candles.iloc[-1] # Current
        
        # Check Direction Match
        c1_green = c1['Close'] > c1['Open']
        c2_green = c2['Close'] > c2['Open']
        
        if c1_green != c2_green: return False # Direction must match
        
        # Check Body %
        def body_pct(c):
            range_val = c['High'] - c['Low']
            body_val = abs(c['Close'] - c['Open'])
            return (body_val / range_val) if range_val > 0 else 0
            
        return body_pct(c1) >= 0.60 and body_pct(c2) >= 0.60

    def _is_stall(self, last_candles):
        """
        Check for Stall: 2 small candles (<30% body) OR Inside Bar.
        """
        if len(last_candles) < 2: return False
        c1 = last_candles.iloc[-2]
        c2 = last_candles.iloc[-1]
        
        # Inside Bar Check
        inside_bar = c2['High'] <= c1['High'] and c2['Low'] >= c1['Low']
        
        # Small Body Check
        def body_pct(c):
            range_val = c['High'] - c['Low']
            body_val = abs(c['Close'] - c['Open'])
            return (body_val / range_val) if range_val > 0 else 0
            
        small_bodies = body_pct(c1) < 0.30 and body_pct(c2) < 0.30
        
        return inside_bar or small_bodies

    def calculate_signal(self, major_df, minor_df, symbol=None):
        """
        major_df: 5-minute/15-minute timeframe (Zone Creation & Trend)
        minor_df: 1-minute/5-minute timeframe (Entry Trigger)
        """
        if major_df.empty or len(major_df) < 50:
            return None
            
        # Avoid SettingWithCopyWarning/Error by explicit copy
        major_df = major_df.copy()
        
        # Use Minor TF for Execution if available, else Major
        execution_df = minor_df if (minor_df is not None and not minor_df.empty) else major_df
        execution_df = execution_df.copy()
        
        sym_key = symbol if symbol else 'DEFAULT'
        
        # --- 1. PREPARE INDICATORS (MAJOR TF) ---
        if 'EMA_50' not in major_df.columns:
            major_df['EMA_50'] = major_df['Close'].ewm(span=50, adjust=False).mean()
            
        # Volume Moving Average for Impulse check
        if 'VOL_MA_20' not in major_df.columns:
            major_df['VOL_MA_20'] = major_df['Volume'].rolling(20).mean()

        # Update Zones (MAJOR TF)
        self._update_zones(major_df, sym_key)
        
        # --- 2. CHECK EXECUTION (MINOR TF) ---
        # Current price comes from Execution DF (1m)
        current_price = execution_df['Close'].iloc[-1] 
        
        # Trend is determined by MAJOR TF (50 EMA)
        # We need to compare current price to Major TF EMA
        # Use the last known Major EMA
        ema_50 = major_df['EMA_50'].iloc[-1]
        
        signal = None
        
        # Determine Trend Status
        trend = "Neutral"
        if float(current_price) > float(ema_50): trend = "Bullish (>50EMA)"
        elif float(current_price) < float(ema_50): trend = "Bearish (<50EMA)"
        
        self.current_status = f"Scanning (Trend: {trend})"
        
        if sym_key in self.zones:
            # Check for invalidations first (on MAJOR TF - Structure Break)
            # A zone is invalidated if Major TF candle breaks it strongly
            # But we are iterating 1m bars? 
            # Ideally zones are invalidated by 1m closes too? 
            # Structure breaks usually on formation TF. 
            # For backtest speed, let's assume invalidation logic remains on Major TF or check explicitly?
            # Let's check Invalidation on Execution TF (Acceptance beyond zone)
            
            for zone in self.zones[sym_key]:
                if zone.get('status', 'active') != 'active': continue
                
                try:
                    # INVALIDATION CHECKS (Execution DF)
                    current_candle = execution_df.iloc[-1]
                    prev_candle = execution_df.iloc[-2] if len(execution_df) > 1 else current_candle
                    
                    # Rule 1: Strong Breakdown/Breakout Candle (>60% Body)
                    o = float(current_candle['Open'])
                    c = float(current_candle['Close'])
                    h = float(current_candle['High'])
                    l = float(current_candle['Low'])
                    
                    body_size = abs(c - o)
                    candle_range = h - l
                    is_solid_body = (body_size / candle_range >= 0.60) if candle_range > 0 else False
                    
                    # Rule 2: Consecutive Closes (Acceptance)
                    
                    if zone['type'] == 'BUY':
                        # Breakdown Check
                        close_below = c < zone['bottom']
                        prev_close_below = float(prev_candle['Close']) < zone['bottom']
                        
                        strong_break = close_below and is_solid_body
                        consecutive_break = close_below and prev_close_below
                        
                        if strong_break or consecutive_break:
                            zone['status'] = 'invalid'
                            continue
                            
                    elif zone['type'] == 'SELL':
                        # Breakout Check
                        close_above = c > zone['top']
                        prev_close_above = float(prev_candle['Close']) > zone['top']
                        
                        strong_break = close_above and is_solid_body
                        consecutive_break = close_above and prev_close_above
                        
                        if strong_break or consecutive_break:
                            zone['status'] = 'invalid'
                            continue
                except Exception as e:
                    pass

            # EXECUTION CHECKS (Only on Active Zones)
            curr_candle = execution_df.iloc[-1]
            prev_candle = execution_df.iloc[-2] if len(execution_df) > 1 else curr_candle
            
            for zone in self.zones[sym_key]:
                if zone.get('status', 'active') != 'active': continue
                if zone['tested']: continue
                
                # BUYER ZONE LOGIC
                if zone['type'] == 'BUY':
                    # Filter: Trend (Price > 50 EMA)
                    if float(current_price) < float(ema_50): 
                        # self.current_status = "Ignored Buy Zone (Trend Bearish)" # Optional: Too noisy?
                        continue
                        
                    # Detailed Status: Monitoring
                    dist_to_zone = abs(float(curr_candle['Low']) - zone['top'])
                    if dist_to_zone / float(current_price) < 0.0015: # Close to zone (0.15%)
                         self.current_status = "Monitoring BUY Zone (Waiting for Sweep)"
                        
                    # Proximity Check
                    if float(curr_candle['Low']) <= zone['top']:
                        # Pre-calc floats
                        c_low = float(curr_candle['Low'])
                        c_high = float(curr_candle['High'])
                        c_close = float(curr_candle['Close'])
                        c_open = float(curr_candle['Open'])
                        
                        p_close = float(prev_candle['Close'])
                        p_open = float(prev_candle['Open'])
                        
                        # Trigger A: Sweep
                        has_wick_below = c_low < zone['bottom']
                        closes_inside = c_close >= zone['bottom']
                        is_green = c_close > c_open
                        
                        # Fake Pin Bar Filter
                        range_len = c_high - c_low
                        close_pos = (c_close - c_low) / range_len if range_len > 0 else 0
                        is_strong_close = close_pos >= 0.60
                        
                        is_sweep_valid = has_wick_below and closes_inside and is_green and is_strong_close
                        
                        # Trigger B: Displacement
                        body_size = abs(c_close - c_open)
                        prev_body = abs(p_close - p_open)
                        is_displacement = is_green and (body_size > prev_body * 1.5) and (c_close >= zone['bottom'])
                        
                        if is_sweep_valid or is_displacement:
                            # --- ROOM TO RUN CHECK ---
                            nearest_seller = self._get_nearest_opposite_zone(current_price, 'SELL', sym_key)
                            if nearest_seller:
                                # Distance to the bottom of the resistance
                                dist_to_res = (nearest_seller['bottom'] - current_price) / current_price
                                # If price is INSIDE the zone, dist_to_res will be <= 0
                                if dist_to_res < 0.003: # 0.3% Room required OR inside zone
                                    self.current_status = f"Filtered: BUY too close to/inside Resistance"
                                    return None

                            signal = 'buy'
                            zone['tested'] = True
                            zone['status'] = 'filled'
                
                # SELLER ZONE LOGIC
                elif zone['type'] == 'SELL':
                    # Filter: Trend
                    if float(current_price) > float(ema_50):
                         # self.current_status = "Ignored Sell Zone (Trend Bullish)"
                         continue

                    # Detailed Status: Monitoring
                    dist_to_zone = abs(float(curr_candle['High']) - zone['bottom'])
                    if dist_to_zone / float(current_price) < 0.0015:
                         self.current_status = "Monitoring SELL Zone (Waiting for Sweep)"
                        
                    if float(curr_candle['High']) >= zone['bottom']:
                        c_low = float(curr_candle['Low'])
                        c_high = float(curr_candle['High'])
                        c_close = float(curr_candle['Close'])
                        c_open = float(curr_candle['Open'])
                        
                        p_close = float(prev_candle['Close'])
                        p_open = float(prev_candle['Open'])
                        
                        # Trigger A: Sweep
                        has_wick_above = c_high > zone['top']
                        closes_inside = c_close <= zone['top']
                        is_red = c_close < c_open
                        
                        # Fake Pin Filter
                        range_len = c_high - c_low
                        close_pos = (c_close - c_low) / range_len if range_len > 0 else 0
                        is_strong_close = close_pos <= 0.40
                        
                        is_sweep_valid = has_wick_above and closes_inside and is_red and is_strong_close
                        
                        # Trigger B: Displacement
                        body_size = abs(c_close - c_open)
                        prev_body = abs(p_close - p_open)
                        is_displacement = is_red and (body_size > prev_body * 1.5) and (c_close <= zone['top'])
                        
                        if is_sweep_valid or is_displacement:
                            # --- ROOM TO RUN CHECK ---
                            nearest_buyer = self._get_nearest_opposite_zone(current_price, 'BUY', sym_key)
                            if nearest_buyer:
                                # Distance to the top of the support
                                dist_to_supp = (current_price - nearest_buyer['top']) / current_price
                                # If price is INSIDE the zone, dist_to_supp will be <= 0
                                if dist_to_supp < 0.003:
                                    self.current_status = f"Filtered: SELL too close to/inside Support"
                                    return None

                            signal = 'sell'
                            zone['tested'] = True
                            zone['status'] = 'filled'
                            
        return signal

    def _get_nearest_opposite_zone(self, price, zone_type, sym_key):
        """Find the closest zone of zone_type to the current price, even if mitigated or currently inside"""
        if sym_key not in self.zones: return None
        
        nearest = None
        min_dist = float('inf')
        
        for z in self.zones[sym_key]:
            if z['type'] != zone_type: continue
            
            if zone_type == 'SELL' and z['top'] > price:
                # Catch zones above OR zones we are currently inside
                # If price is inside, distance is 0
                dist = max(0, z['bottom'] - price)
                if dist < min_dist:
                    min_dist = dist
                    nearest = z
            elif zone_type == 'BUY' and z['bottom'] < price:
                dist = max(0, price - z['top'])
                if dist < min_dist:
                    min_dist = dist
                    nearest = z
        return nearest

    def _update_zones(self, df, sym_key):
        if sym_key not in self.zones:
            self.zones[sym_key] = []
            
        # Analysis Window: Look at last concluded candle setup (e.g., -3 and -2)
        # We need an Impulse Candle (Candle B) and a Base/Zone Candle (Candle A)
        
        candle_impulse = df.iloc[-2] 
        candle_base = df.iloc[-3]
        
        # 1. IMPULSE CHECK
        # Explicit float casting to handle potential Series/MultiIndex issues
        h = float(candle_impulse['High'])
        l = float(candle_impulse['Low'])
        c = float(candle_impulse['Close'])
        o = float(candle_impulse['Open'])
        
        range_impulse = h - l
        if range_impulse == 0: return
        
        body_impulse = abs(c - o)
        body_pct = body_impulse / range_impulse
        
        vol_impulse = float(candle_impulse['Volume'])
        vol_avg = float(df['VOL_MA_20'].iloc[-2]) if not pd.isna(df['VOL_MA_20'].iloc[-2]) else vol_impulse
        
        # Validate Volume (if available)
        vol_ratio = 1.6
        if vol_avg > 0:
            vol_ratio = vol_impulse / vol_avg
        else:
            vol_ratio = 2.0 # Pass if no volume data (assume breakout)
            
        # Nifty often has wicks. 70% is very perfect marubozu. Trying 0.5 (50%)
        is_impulse_candle = (body_pct >= 0.50) and (vol_ratio > 1.5 or vol_avg == 0)
        
        if not is_impulse_candle:
            return

        # 2. IDENTIFY ZONES
        
        # BULLISH IMPULSE (Green) using pre-calculated floats c, o
        if c > o:
            # Create Buyer Zone from Base Candle
            b_open = float(candle_base['Open'])
            b_close = float(candle_base['Close'])
            b_low = float(candle_base['Low'])
            
            new_zone = {
                'type': 'BUY',
                'top': max(b_open, b_close), 
                'bottom': b_low,
                'created_at': candle_impulse.name, # Time of impulse completion
                'tested': False,
                'status': 'active'
            }
            # Basic duplicate check by time
            if not any(z['created_at'] == new_zone['created_at'] for z in self.zones[sym_key]):
                self.zones[sym_key].append(new_zone)
            
        # BEARISH IMPULSE (Red)
        elif c < o:
            # Create Seller Zone
            b_open = float(candle_base['Open'])
            b_close = float(candle_base['Close'])
            b_high = float(candle_base['High'])
            
            new_zone = {
                'type': 'SELL',
                'top': b_high,
                'bottom': min(b_open, b_close),
                'created_at': candle_impulse.name,
                'tested': False,
                'status': 'active'
            }
             # Basic duplicate check by time
            if not any(z['created_at'] == new_zone['created_at'] for z in self.zones[sym_key]):
                self.zones[sym_key].append(new_zone)
        
        # Cleanup old zones
        if len(self.zones[sym_key]) > 20:
             self.zones[sym_key] = self.zones[sym_key][-20:]

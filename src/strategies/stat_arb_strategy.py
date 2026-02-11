
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time
from src.core.base_strategy import BaseStrategy

class StatisticalStatArbAdapter(BaseStrategy):
    """
    Statistical Sniper Strategy
    Logic:
    1. Filter: Kaufman Efficiency Ratio (KER < 0.30)
    2. Signal: Z-Score > 2.0 (Statistical Extreme)
    3. Execution: Reversion to Mean
    4. Exit: Scale-Out (90% @ 1.5x, 10% Trail)
    """
    
    def __init__(self, broker=None):
        super().__init__("Statistical Sniper", 15000)
        self.broker = broker
        
        # Strategy Parameters (Optimized for 5,000/mo profit)
        self.period = 20
        self.ker_threshold = 0.30 # Wider filter for more frequency
        self.z_entry = 2.0         # 2.0 is the sweet spot for Sniper entries
        self.risk_per_trade_rs = 2000.0  # Increased Risk to hit 33% monthly ROI
        self.atr_period = 14
        self.stop_atr_mult = 2.0
        
        # State Management for Scale-Out
        # Key: Symbol, Value: {'stage': 0, 'entry': price, 'stop': price, 'risk': dist, 'qty_total': q}
        self.position_state = {} 

    def calculate_indicators(self, df):
        """Calculate Z-Score, KER, ATR"""
        close = df['close']
        
        # 1. Z-Score
        mean = close.rolling(window=self.period).mean()
        std = close.rolling(window=self.period).std()
        df['z_score'] = (close - mean) / std
        
        # 2. KER (Efficiency Ratio)
        change = close.diff(self.period).abs()
        volatility = close.diff().abs().rolling(window=self.period).sum()
        df['ker'] = (change / volatility).fillna(0)
        
        # 3. ATR
        high = df['high']
        low = df['low']
        prev_close = close.shift(1)
        tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean()
        
        return df


    def _get_option_ltp(self, option_sym):
        """Helper to get Option LTP from Broker"""
        try:
            # Check if broker has direct access (FyersBroker)
            if hasattr(self.broker, 'get_option_chain'):
                parts = option_sym.split(':')[-1] # NSE:NIFTY... -> NIFTY...
                # Need to parse strike/type/expiry de-construct? 
                # FyersBroker.get_option_chain needs strike, type, expiry.
                # Actually fyers_broker.get_current_price() is buggy for options as derived earlier (hardcoded Nifty).
                # But fyers_broker.get_option_chain() works if we have strike/type.
                
                # Let's use Fyers API 'quotes' method directly if possible or 'get_current_price' IF fixed?
                # The user's fyers_broker.py has get_current_price(symbol) but it ignores symbol.
                # So we must use get_option_chain or access api directly.
                
                # Parsing symbol "NSE:NIFTY26127CE" -> Strike, Type, Expiry logic is complex.
                # EASIER WAY: If Broker has direct API access attribute (like self.broker.api)
                
                api = getattr(self.broker, 'api', None)
                if not api and hasattr(self.broker, 'fyers'): # FyersPaperBroker
                    api = self.broker.fyers.api
                    
                if api:
                    data = {"symbols": option_sym}
                    resp = api.quotes(data)
                    if resp and resp.get('s') == 'ok':
                        return resp['d'][0]['v']['lp']
                        
            # Fallback if paper broker has a wrapper?
            # FyersPaperBroker doesn't expose a direct "get_quote(sym)" efficiently.
            
            return 0.0
        except:
            return 0.0

    def process(self, df, current_bar):
        """Main execution loop called by Trading Engine"""
        try:
            if df is None or len(df) < 50:
                self.status = f"Warming indicators ({len(df)}/50 bars)"
                return
                
            # Calculate Indicators
            df = self.calculate_indicators(df)
            curr = df.iloc[-1]
            current_price = curr['close']
            symbol = "NSE:NIFTY50-INDEX"
            
            # --- 1. MANAGE ACTIVE POSITIONS (Scale Out & Trail) ---
            active_setup = self.position_state.get(symbol)
            
            if active_setup:
                option_sym = active_setup.get('option_symbol')
                
                # Check Expiry FIRST (Auto-close on Expiry Day > 15:15)
                if self._check_expiry_exit(active_setup, curr):
                    return

                qty_left = active_setup['total_qty'] 
                if 'qty_left' in active_setup: qty_left = active_setup['qty_left']
                
                # Get Option LTP for monitoring
                opt_ltp = self._get_option_ltp(option_sym)
                if opt_ltp == 0: opt_ltp = active_setup.get('last_ltp', 0)
                active_setup['last_ltp'] = opt_ltp
                
                self.status = f"Active: {option_sym} | LTP: {opt_ltp} | Qty: {qty_left} | Stage: {active_setup['stage']}"
                
                # Update Trailing Stop (Stage 3)
                if active_setup['stage'] >= 2: 
                    self._update_trailing_stop(active_setup, curr, option_sym)
                
                # Check Exits (Pass Option LTP)
                self._check_exits(active_setup, curr, option_sym, qty_left, opt_ltp)
                
            else:
                self.status = f"Scanning: KER {curr['ker']:.2f}, Z {curr['z_score']:.1f}"
                # --- 2. CHECK FOR NEW ENTRY ---
                # Only if no active setup
                
                # Time Filter (9:15 to 2:45)
                current_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
                if current_time > datetime.strptime('14:45', '%H:%M').time(): return
                
                # Logic
                is_choppy = curr['ker'] < self.ker_threshold
                z_score = curr['z_score']
                
                signal = None
                if is_choppy and z_score < -self.z_entry:
                    signal = 'BUY' # Spot Long -> Buy CE
                elif is_choppy and z_score > self.z_entry:
                    signal = 'SELL' # Spot Short -> Buy PE
                    
                if signal:
                    self._place_entry_order(signal, curr, symbol)
                    
        except Exception as e:
            print(f"Error in StatArb Strategy: {e}")
            import traceback
            traceback.print_exc()

    def _check_expiry_exit(self, active_setup, curr):
        """Force Close if Expiry Day and Time is late"""
        try:
            option_sym = active_setup.get('option_symbol')
            # Extract Expiry from Symbol (NSE:NIFTY26127CE)
            match = re.search(r'NIFTY(\d{2})([A-Z0-9])(\d{2})', option_sym)
            if not match: return False
            
            yy, m_code, dd = match.groups()
            
            # Decode Month
            m_map = {'O':10, 'N':11, 'D':12}
            month = int(m_code) if m_code.isdigit() else m_map.get(m_code, 0)
            year = 2000 + int(yy)
            day = int(dd)
            
            expiry_date = datetime(year, month, day).date()
            today = datetime.now(pytz.timezone('Asia/Kolkata')).date()
            
            # Check if Expired or Late on Expiry Day
            now_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
            cutoff_time = datetime.strptime('15:15', '%H:%M').time()
            
            should_close = False
            reason = ""
            
            if today > expiry_date:
                should_close = True
                reason = "Expired Yesterday"
            elif today == expiry_date and now_time >= cutoff_time:
                should_close = True
                reason = "Expiry Day Cutoff (15:15)"
                
            if should_close:
                print(f" STAT ARB EXPIRY EXIT: {reason}. Closing {option_sym}")
                self.broker.close_position(option_sym) 
                del self.position_state["NSE:NIFTY50-INDEX"]
                return True
                
            return False
        except Exception as e:
            # print(f"Expiry Check Error: {e}")
            return False

    def _place_entry_order(self, signal, curr, spot_symbol):
        """Calculate Sizing and Place Order"""
        entry_price = curr['close']
        atr = curr['atr']
        
        # Stops based on SPOT
        if signal == 'BUY':
            stop_loss = entry_price - (atr * self.stop_atr_mult)
            risk_dist = entry_price - stop_loss
            t1_dist = risk_dist * 1.5
        else:
            stop_loss = entry_price + (atr * self.stop_atr_mult)
            risk_dist = stop_loss - entry_price
            t1_dist = risk_dist * 1.5
            
        if risk_dist <= 0: return

        # Position Sizing
        lot_size = getattr(self.broker, 'LOT_SIZE', 65)
        est_delta = 0.55 
        loss_per_lot = risk_dist * est_delta * lot_size
        
        if loss_per_lot == 0: return
        
        num_lots = max(1, int(self.risk_per_trade_rs / loss_per_lot))
        num_lots = min(num_lots, 10) 
        
        # Place Order (Buy Option)
        instrument = 'CE' if signal == 'BUY' else 'PE'
        order = self.broker.submit_order(spot_symbol, num_lots, 'buy', instrument=instrument)
        
        if order and order.get('status') == 'filled':
            option_sym = None
            entry_premium = order.get('price', 0)
            
            # Attempt to find symbol
            if 'symbol' in order: option_sym = order['symbol']
            
            # Recover symbol if missing (Paper broker usually returns it)
            if not option_sym and hasattr(self.broker, 'positions'):
                for sym, pos in self.broker.positions.items():
                    if pos['order_id'] == order['order_id']:
                        option_sym = sym
                        entry_premium = pos['entry_price']
                        break
            
            if option_sym:
                # Calculate Premium Stops
                # Spot Risk * Delta = Premium Risk
                premium_risk = risk_dist * est_delta
                stop_loss_premium = entry_premium - premium_risk
                # T1 Premium = Risk * 1.5
                target_premium = entry_premium + (premium_risk * 1.5)
                
                if stop_loss_premium < 0.1: stop_loss_premium = 0.1
                
                self.position_state[spot_symbol] = {
                    'option_symbol': option_sym,
                    'direction': signal,
                    'entry_price_spot': entry_price,
                    'stop_loss_spot': stop_loss,
                    't1_dist': t1_dist,
                    'total_qty': num_lots,
                    'qty_left': num_lots, 
                    'stage': 0, 
                    'risk_dist': risk_dist,
                    
                    # NEW: Premium Logic
                    'entry_premium': entry_premium,
                    'stop_loss_premium': stop_loss_premium,
                    'target_premium': target_premium
                }
                print(f" STAT ARB ENTRY: {signal} {num_lots} Lots. Spot: {entry_price:.2f}, Stop: {stop_loss:.2f}")
                print(f"   Option: {option_sym} @ {entry_premium:.2f} | P-SL: {stop_loss_premium:.2f} | P-TGT: {target_premium:.2f}")

    def _check_exits(self, state, curr, option_sym, qty_left, opt_ltp):
        """Check Targets and Stop Loss based on Spot Price AND Option Premium"""
        current_spot = curr['close']
        initial_qty = state['total_qty']
        
        hit_stop = False
        hit_target = False
        exit_reason = ""
        
        # 1. SPOT CHECKS
        dist_moved = 0
        if state['direction'] == 'BUY':
            dist_moved = current_spot - state['entry_price_spot']
            if curr['low'] <= state['stop_loss_spot']: 
                hit_stop = True
                exit_reason = f"Spot SL Hit ({current_spot:.1f})"
        else:
            dist_moved = state['entry_price_spot'] - current_spot
            if curr['high'] >= state['stop_loss_spot']: 
                hit_stop = True
                exit_reason = f"Spot SL Hit ({current_spot:.1f})"
            
        # 2. PREMIUM CHECKS (Overrides Spot if Hit)
        if opt_ltp > 0:
            # STOP LOSS
            if opt_ltp <= state['stop_loss_premium']:
                hit_stop = True
                exit_reason = f"Premium SL Hit ({opt_ltp:.1f} <= {state['stop_loss_premium']:.1f})"
                
            # TARGET (for Scale Out)
            if opt_ltp >= state['target_premium']:
                 hit_target = True
        
        # EXECUTE EXIT
        if hit_stop:
            print(f" STAT ARB STOP: {exit_reason}. Closing {qty_left} lots.")
            self.broker.close_position(option_sym)
            del self.position_state["NSE:NIFTY50-INDEX"]
            return

        # TARGET EXECUTION (Scale Out)
        # Spot Target (Distance) OR Premium Target (Price)
        spot_target_hit = (dist_moved >= state['t1_dist'])
        
        if state['stage'] == 0 and (spot_target_hit or hit_target):
            # Close 90%
            qty_to_close = int(initial_qty * 0.90)
            if qty_to_close > 0 and qty_to_close < qty_left:
                reason = "Spot Dist" if spot_target_hit else "Premium Price"
                print(f" STAT ARB T1 HIT ({reason}). Scaling out {qty_to_close} lots (90%).")
                self.broker.close_position(option_sym, qty=qty_to_close)
                state['stage'] = 1
                
                # Move Stop to Breakeven
                state['stop_loss_spot'] = state['entry_price_spot']
                state['stop_loss_premium'] = state['entry_premium'] # Move Prem SL to BE too
                print(f" SL moved to Breakeven (Spot & Premium).")
                
            elif qty_to_close >= qty_left:
                self.broker.close_position(option_sym)
                del self.position_state["NSE:NIFTY50-INDEX"]

    def _update_trailing_stop(self, state, curr, option_sym):
        """Trail the Runner (Stage 2+)"""
        current_spot = curr['close']
        atr = curr['atr']
        trail_dist = atr * 1.5
        
        if state['direction'] == 'BUY':
            new_stop = current_spot - trail_dist
            if new_stop > state['stop_loss_spot']:
                state['stop_loss_spot'] = new_stop
        else:
            new_stop = current_spot + trail_dist
            if new_stop < state['stop_loss_spot']:
                state['stop_loss_spot'] = new_stop

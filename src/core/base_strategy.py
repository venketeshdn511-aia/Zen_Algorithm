import os
import pandas as pd
import pytz
from datetime import datetime
from src.utils.date_utils import get_next_nifty_expiry
from src.utils.notifications import send_telegram_message

# MongoDB Integration
try:
    from src.db.mongodb_handler import get_db_handler
    db_handler = get_db_handler()
except ImportError:
    db_handler = None

# Brain Module Integration
try:
    from src.brain.learning_engine import get_brain
    brain = get_brain()
    BRAIN_AVAILABLE = True
except ImportError:
    brain = None
    BRAIN_AVAILABLE = False

INITIAL_CAPITAL = 15000.0
LOT_SIZE = 65

class BaseStrategy:
    def __init__(self, name, capital):
        self.name = name
        self.capital = capital
        self.initial_capital = capital
        self.position = None
        self.trades = []
        self.wins = 0
        self.losses = 0
        self.daily_start_capital = capital
        self.status = "Monitoring..."
        self.paused = False
        self.allowed_regimes = ['ALL']
        self.broker = None  # Set by subclass or trading engine
        
    def get_fyers_expiry_code(self):
        return get_next_nifty_expiry()

    def update_market_status(self, df):
        if df is None or len(df) < 2: return
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        spot = float(row['close'])
        rsi = float(row.get('rsi', 50))
        
        trend = "Bullish" if spot > row.get('vwap', spot) else "Bearish"
        rsi_state = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
        
        # Base Narrative
        self.market_narrative = f"Nifty: {spot:.1f} ({trend}) | RSI: {rsi:.1f} ({rsi_state})"
        return spot, rsi, trend

    def get_stats(self):
        pnl = self.capital - self.initial_capital
        today_pnl = self.capital - self.daily_start_capital
        pnl_pct = (pnl / self.initial_capital) * 100
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        return {
            'name': self.name,
            'status': 'Paused' if self.paused else self.status,
            'paused': self.paused,
            'capital': round(self.capital, 2),
            'pnl': round(pnl, 2),
            'today_pnl': round(today_pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': round(win_rate, 1),
            'position': self.position,
            'daily_start_capital': self.daily_start_capital,
            'trades': self.trades,
            'allowed_regimes': self.allowed_regimes
        }
    
    def get_option_params(self, spot_price, side, broker):
        if not broker: return None, None, None
        
        atm_strike = broker.get_atm_strike(spot_price)
        otype = 'CE' if side == 'buy' else 'PE'
        exp = self.get_fyers_expiry_code()
        
        premium = broker.get_option_price(atm_strike, otype, expiry_code=exp)
        # Reconstruct symbol if broker doesn't return it? 
        # Actually broker.get_option_price should probably return symbol too?
        # But current BaseStrategy expects 'symbol' string.
        # KotakBroker constructs it as: f"{root}{expiry_code}{str_strike}{otype.upper()}"
        # Let's replicate this construction here OR assume Broker knows best.
        # But BaseStrategy uses this symbol for execute_trade logs.
        # So we should construct it to match what Kotak uses.
        symbol = f"NIFTY{exp}{int(atm_strike)}{otype}"
        
        return premium, symbol, atm_strike
    
    def resample_to_5m(self, df):
        try:
            return df.resample('5min').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
        except Exception as e:
            print(f" [RESAMPLE] 5m resample failed: {e}")
            return df
            
    def get_recent_swing(self, df, side, lookback=20):
        if len(df) < 5: return None
        
        if side == 'buy':
            lows = df['low'].values
            for i in range(len(lows) - 2, max(0, len(lows) - lookback - 1), -1):
                curr = lows[i]
                prev = lows[i-1]
                next_val = lows[i+1]
                if curr < prev and curr < next_val:
                     return curr
            return df['low'].iloc[-10:-1].min()

        elif side == 'sell':
            highs = df['high'].values
            for i in range(len(highs) - 2, max(0, len(highs) - lookback - 1), -1):
                curr = highs[i]
                prev = highs[i-1]
                next_val = highs[i+1]
                if curr > prev and curr > next_val:
                     return curr
            return df['high'].iloc[-10:-1].max()
            
        return None

    def update_trailing_stop(self, df):
        if not self.position: return
        if len(df) < 10: return
        
        side = self.position['side']
        symbol = self.position.get('symbol', '')
        is_option = 'CE' in symbol or 'PE' in symbol
        
        if is_option and 'spot_stop' not in self.position:
            current_spot = float(df['close'].iloc[-1])
            if side == 'buy':
                self.position['spot_stop'] = current_spot - (current_spot * 0.005)
            else:
                self.position['spot_stop'] = current_spot + (current_spot * 0.005)
        
        # Get Recent Swing Structure (Support for Long, Resistance for Short)
        swing_side = side
        if is_option and 'PE' in symbol:
            swing_side = 'sell' # For Put Buy (Short), look for Swing Highs
            
        structural_level = self.get_recent_swing(df, swing_side, lookback=20)
        if not structural_level: return

        if is_option:
            current_spot_stop = self.position.get('spot_stop', structural_level)
            new_spot_stop = current_spot_stop
            
            if side == 'buy':
                if 'PE' in symbol: # Put Buy (Short) -> Trail DOWN
                    if structural_level < current_spot_stop:
                        current_high = df['high'].iloc[-1]
                        if structural_level > current_high:
                            new_spot_stop = structural_level
                else: # Call Buy (Long) -> Trail UP
                    if structural_level > current_spot_stop:
                        current_low = df['low'].iloc[-1]
                        if structural_level < current_low:
                            new_spot_stop = structural_level
            else: # This 'else' is for side == 'sell'
                if structural_level < current_spot_stop:
                    current_high = df['high'].iloc[-1]
                    if structural_level > current_high:
                        new_spot_stop = structural_level
            
            if new_spot_stop != current_spot_stop:
                change = abs(new_spot_stop - current_spot_stop)
                if change > 5:
                    self.status = f"Spot Trail: {current_spot_stop:.1f}  {new_spot_stop:.1f}"
                    self.position['spot_stop'] = new_spot_stop
        else:
            current_stop = self.position['stop']
            new_stop = current_stop
            
            if side == 'buy':
                if structural_level > current_stop:
                    current_low = df['low'].iloc[-1]
                    if structural_level < current_low:
                        new_stop = structural_level
            elif side == 'sell':
                if structural_level < current_stop:
                    current_high = df['high'].iloc[-1]
                    if structural_level > current_high:
                        new_stop = structural_level
                        
            if new_stop != current_stop:
                change = abs(new_stop - current_stop)
                if change > 0.5:
                    self.status = f"Trailing Stop Updated: {current_stop:.1f} -> {new_stop:.1f} (Structure)"
                    self.position['stop'] = new_stop
    
    def check_spot_trailing_stop(self, df):
        if not self.position: return False
        symbol = self.position.get('symbol', '')
        is_option = 'CE' in symbol or 'PE' in symbol
        if not is_option: return False
        
        spot_stop = self.position.get('spot_stop')
        if not spot_stop: return False
        
        current_spot = float(df['close'].iloc[-1])
        side = self.position['side']
        
        if side == 'buy':
            if 'PE' in symbol:
                if current_spot >= spot_stop: # Put Buy (Short) -> Exit if price RISES to stop
                    return True
            else: # Call Buy (Long) -> Exit if price FALLS to stop
                if current_spot <= spot_stop:
                    return True
        else: # Spot Short
            if current_spot >= spot_stop:
                return True
        return False

    def _get_current_conditions(self, df=None) -> dict:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        conditions = {
            'strategy': self.name,
            'hour': now.hour,
            'regime': getattr(self, 'current_regime', None),
        }
        if df is not None and len(df) > 0:
            try:
                row = df.iloc[-1]
                if 'adx' in df.columns: conditions['adx'] = float(row.get('adx', 0))
                if 'rsi' in df.columns: conditions['rsi'] = float(row.get('rsi', 50))
                if 'atr' in df.columns and len(df) > 20:
                    current_atr = float(row.get('atr', 0))
                    avg_atr = float(df['atr'].tail(20).mean())
                    conditions['atr_ratio'] = current_atr / avg_atr if avg_atr > 0 else 1.0
            except Exception as e:
                print(f" [BRAIN] Condition extraction error: {e}")
        return conditions
    
    def execute_trade(self, entry_price, side, stop, target, size, symbol=None, df=None, skip_brain=False):
        ist = pytz.timezone('Asia/Kolkata')
        if BRAIN_AVAILABLE and brain and not skip_brain:
            conditions = self._get_current_conditions(df)
            should_skip, skip_reason = brain.should_skip_trade(conditions)
            if should_skip:
                self.status = f" Warning (Ignored): {skip_reason}"
                msg = f" <b>{self.name}</b>: Low Confidence Warning (Ignored)\n{skip_reason}"
                send_telegram_message(msg)
                # return None  <-- DISABLED BY USER REQUEST
        
        size = LOT_SIZE

        if self.position:
            self.status = " Duplicate Entry Blocked: Position already exists."
            return None
            
        # Time-based throttle (1 minute)
        if self.trades:
            last_trade = self.trades[-1]
            last_entry_str = last_trade.get('entry_time')
            if last_entry_str:
                try:
                    last_entry = datetime.fromisoformat(last_entry_str)
                    if (datetime.now(ist) - last_entry).total_seconds() < 60:
                        self.status = " Throttle: Entry blocked (Min 60s between trades)."
                        return None
                except Exception as e:
                    print(f" [THROTTLE] Time parse error: {e}")

        self.position = {
            'side': side,
            'entry': entry_price,
            'sl': stop,
            'target': target,
            'size': size,
            'symbol': symbol or self.name,
            'strike': getattr(self, 'current_strike', 'N/A'),
            'ltp': entry_price,
            'entry_time': datetime.now(ist).isoformat()
        }
        
        if BRAIN_AVAILABLE and brain:
            self.position['conditions'] = self._get_current_conditions(df)

        display_name = symbol if symbol else self.name
        
        # === LIVE ORDER PLACEMENT ===
        broker_order_id = None
        if self.broker and hasattr(self.broker, 'place_order') and self.broker.connected:
            try:
                broker_side = 'BUY' if side == 'buy' else 'SELL'
                order_resp = self.broker.place_order(
                    symbol=display_name,
                    qty=size,
                    side=broker_side,
                    order_type='MARKET',
                    product='MIS'
                )
                print(f" [BROKER] Entry Order Response: {order_resp}")
                if order_resp and isinstance(order_resp, dict):
                    broker_order_id = order_resp.get('nOrdNo') or order_resp.get('order_id')
                    self.position['broker_order_id'] = broker_order_id
            except Exception as e:
                print(f" [BROKER] Entry Order FAILED: {e}")
                # Continue with internal tracking even if broker order fails
        
        # Attractive Telegram Signal
        side_emoji = " BUY" if side == 'buy' else " SELL"
        msg = (
            f" <b>{self.name}</b>\n"
            f"\n"
            f" <b>{side_emoji} SIGNAL</b>\n"
            f" <b>Asset:</b> <code>{display_name}</code>\n"
            f"\n"
            f" <b>Entry:</b> {entry_price:.2f}\n"
            f" <b>Stop Loss:</b> {stop:.2f}\n"
            f" <b>Target:</b> {target:.2f}\n"
            f" <b>Size:</b> {size}\n"
        )
        
        if BRAIN_AVAILABLE and brain:
            try:
                confidence = brain.get_confidence_score(self.position.get('conditions', {}))
                conf_emoji = "" if confidence > 80 else ""
                msg += f"\n"
                msg += f" <b>AI Confidence:</b> {confidence}% {conf_emoji}"
            except Exception as e:
                print(f" [BRAIN] Confidence score error: {e}")

        send_telegram_message(msg)
        
        # Log to MongoDB
        if db_handler and db_handler.connected:
            try:
                # Detect trade type from broker class
                trade_type = "LIVE" if self.broker and "Kotak" in self.broker.__class__.__name__ else "PAPER"
                
                db_handler.save_trade({
                    "strategy": self.name,
                    "action": "ENTRY",
                    "side": side,
                    "price": entry_price,
                    "size": size,
                    "symbol": display_name,
                    "type": trade_type
                })
            except Exception as e:
                print(f" [DB] Trade ENTRY save failed: {e}")

        return True

    def close_trade(self, exit_price, reason):
        if self.position:
            ist = pytz.timezone('Asia/Kolkata')
            
            # === LIVE EXIT ORDER ===
            if self.broker and hasattr(self.broker, 'place_order') and self.broker.connected:
                try:
                    exit_side = 'SELL' if self.position['side'] == 'buy' else 'BUY'
                    exit_symbol = self.position.get('symbol', self.name)
                    exit_qty = self.position.get('size', LOT_SIZE)
                    order_resp = self.broker.place_order(
                        symbol=exit_symbol,
                        qty=exit_qty,
                        side=exit_side,
                        order_type='MARKET',
                        product='MIS'
                    )
                    print(f" [BROKER] Exit Order Response: {order_resp}")
                except Exception as e:
                    print(f" [BROKER] Exit Order FAILED: {e}")
            
            if self.position['side'] == 'buy':
                pnl = (exit_price - self.position['entry']) * self.position['size']
            else:
                pnl = (self.position['entry'] - exit_price) * self.position['size']
            
            # Brokerage (Approx 60 per round trip)
            brokerage = 60
            pnl -= brokerage
            
            self.capital += pnl
            if pnl > 0: self.wins += 1
            else: self.losses += 1
            
            trade_record = {
                'entry_time': self.position['entry_time'],
                'exit_time': datetime.now(ist).isoformat(),
                'side': self.position['side'],
                'entry': self.position['entry'],
                'exit': exit_price,
                'pnl': round(pnl, 2),
                'reason': reason,
                'strategy': self.name
            }
            self.trades.append(trade_record)
            
            if len(self.trades) > 5000:
                self.trades = self.trades[-5000:]
            
            pnl_status = "PROFIT " if pnl > 0 else "LOSS "
            status_emoji = "" if pnl > 0 else ""
            
            msg = (
                f"{status_emoji} <b>{self.name} - Trade Closed</b>\n"
                f"\n"
                f" <b>Result:</b> {pnl_status}\n"
                f" <b>Net PnL:</b> {pnl:.2f}\n"
                f" <b>Exit Price:</b> {exit_price:.2f}\n"
                f" <b>Reason:</b> {reason}\n"
                f"\n"
                f" <b>Updated Capital:</b> {self.capital:.2f}"
            )
            send_telegram_message(msg)
            
            # Log to MongoDB
            if db_handler and db_handler.connected:
                try:
                    # Detect trade type from broker class
                    trade_type = "LIVE" if self.broker and "Kotak" in self.broker.__class__.__name__ else "PAPER"
                    
                    db_handler.save_trade({
                        "strategy": self.name,
                        "action": "EXIT",
                        "side": self.position['side'],
                        "entry_price": self.position['entry'],
                        "exit_price": exit_price,
                        "pnl": round(pnl, 2),
                        "reason": reason,
                        "symbol": self.position.get('symbol', self.name),
                        "type": trade_type
                    })
                except Exception as e:
                    print(f" [DB] Trade EXIT save failed: {e}")

            # Brain Feedback
            if BRAIN_AVAILABLE and brain:
                try:
                    brain_trade = {
                        **trade_record,
                        'conditions': self.position.get('conditions', {})
                    }
                    brain.record_trade_outcome(brain_trade)
                except Exception as e:
                    print(f" [BRAIN] Trade outcome record failed: {e}")

            self.position = None
            self.status = "Scanning alpha vectors..."
            return pnl
        return 0

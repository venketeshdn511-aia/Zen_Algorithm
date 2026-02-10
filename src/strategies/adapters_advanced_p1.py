from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_atr
from src.strategies.nifty_options_v2 import NiftyOptionsStrategyV2
from src.strategies.buyer_seller_zone_strategy import BuyerSellerZoneStrategy
from src.strategies.mean_reversion_momentum_strategy import MeanReversionMomentumStrategy
import re
import pandas as pd
from datetime import datetime
import pytz

class NiftyV2Adapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Nifty Options V2", INITIAL_CAPITAL)
        self.allowed_regimes = ["TREND", "REVERSAL", "RANGE"]
        self.risk_pct = 0.05
        self.rr_ratio = 2.0
        self.broker = broker
        self.strategy = NiftyOptionsStrategyV2()
        
    def process(self, df, current_bar):
        if len(df) < 50: return
        df_adapter = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        signal = self.strategy.calculate_signal(df_adapter, df_adapter)
        
        row = df.iloc[-1]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = self.strategy.get_status() or "Scanning Supply/Demand zones."
            if signal in ['buy', 'sell'] and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                if not premium: return
                
                atr = calculate_atr(df, 14).iloc[-1]
                stop_dist_premium = (atr * 1.5) * 0.5 
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Executed {symbol} at {premium} (Zone Entry)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.get_current_price(symbol, pos.get('entry'))
                if not curr_premium: return
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}. Zone intact."
                if curr_premium <= pos['stop']:
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']:
                    self.close_trade(pos['target'], 'target')

class BuyerSellerZoneAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Buyer/Seller Zone", INITIAL_CAPITAL)
        self.allowed_regimes = ["TREND", "REVERSAL", "RANGE"]
        self.risk_pct = 0.12
        self.rr_ratio = 2.5
        self.broker = broker
        self.strategy = BuyerSellerZoneStrategy(rsi_period=14, ema_period=50, volume_ma_period=20, use_ema_filter=False, min_rr_ratio=2.5)
        
    def process(self, df, current_bar):
        if len(df) < 60: return
        df_adapter = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        signal = self.strategy.calculate_signal(df_adapter, df_adapter, "NIFTY")
        row = df.iloc[-1]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = self.strategy.get_status() or "Scanning Buyer/Seller zones."
            if signal in ['buy', 'sell'] and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                if not premium: return
                
                if self.strategy.last_stop_loss > 0:
                    spot_risk = abs(spot_price - self.strategy.last_stop_loss)
                    stop_dist_premium = spot_risk * 0.5
                else:
                    atr = calculate_atr(df, 14).iloc[-1]
                    stop_dist_premium = (atr * 1.5) * 0.5
                
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Executed {symbol} at {premium}."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.get_current_price(symbol, pos.get('entry'))
                if not curr_premium: return
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}."
                if curr_premium <= pos['stop']:
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']:
                    self.close_trade(pos['target'], 'target')

class MeanReversionMomentumAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Mean Reversion", INITIAL_CAPITAL)
        self.risk_pct = 0.05
        self.rr_ratio = 2.0
        self.strategy = MeanReversionMomentumStrategy(
            rsi_period=14, ema_fast=9, ema_slow=21, atr_period=14, volume_ma_period=20,
            volume_threshold=1.1, rsi_oversold=30, rsi_overbought=70, max_trades_per_day=3,
            backtest_mode=False, adx_period=14, adx_threshold=20, atr_stop_multiplier=1.5,
            atr_target_multiplier=3.0, ema_trend=200
        )
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 30: return
        df_adapter = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        signal = self.strategy.calculate_signal(df_adapter, None, "NIFTY")
        row = df.iloc[-1]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = self.strategy.get_status() or "Scanning RSI + VWAP + EMA conditions."
            if signal in ['buy', 'sell'] and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                if not premium: return
                
                atr = calculate_atr(df, 14).iloc[-1]
                stop_dist_premium = (atr * 1.0) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Executed {symbol} at {premium} ({signal})."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.get_current_price(symbol, pos.get('entry'))
                if not curr_premium: return
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}"
                if curr_premium <= pos['stop']:
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']:
                    self.close_trade(pos['target'], 'target')

class StatisticalStatArbAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Statistical Sniper", 15000)
        self.broker = broker
        self.period = 20
        self.ker_threshold = 0.30
        self.z_entry = 2.0
        self.risk_per_trade_rs = 2000.0
        self.atr_period = 14
        self.stop_atr_mult = 2.0
        self.position_state = {} 

    def calculate_indicators(self, df):
        close = df['close']
        mean = close.rolling(window=self.period).mean()
        std = close.rolling(window=self.period).std()
        df['z_score'] = (close - mean) / std
        change = close.diff(self.period).abs()
        volatility = close.diff().abs().rolling(window=self.period).sum()
        df['ker'] = (change / volatility).fillna(0)
        high = df['high']
        low = df['low']
        prev_close = close.shift(1)
        tr = pd.concat([high-low, abs(high-prev_close), abs(low-prev_close)], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean()
        return df

    def process(self, df, current_bar):
        try:
            if df is None or len(df) < 50: return
            df = self.calculate_indicators(df)
            curr = df.iloc[-1]
            current_price = curr['close']
            symbol = "NSE:NIFTY50-INDEX"
            
            active_setup = self.position_state.get(symbol)
            
            if active_setup:
                if self.position is None:
                    del self.position_state[symbol]
                    self.status = "Monitoring..."
                    return
                sl = active_setup['stop_loss_spot']
                entry = active_setup['entry_price_spot']
                tgt = entry + active_setup['t1_dist'] if active_setup['direction'] == 'BUY' else entry - active_setup['t1_dist']
                self.status = f"{active_setup['option_symbol']} | Spot: {current_price:.1f} | Entry: {entry:.1f} | SL: {sl:.1f} | T1: {tgt:.1f}"
                if active_setup['stage'] >= 1: 
                    self._update_trailing_stop(active_setup, curr)
                self._check_exits(active_setup, curr)
            else:
                self.status = f"Scanning: KER {curr['ker']:.2f}, Z {curr['z_score']:.1f}"
                current_time = datetime.now(pytz.timezone('Asia/Kolkata')).time()
                if current_time > datetime.strptime('14:45', '%H:%M').time(): return
                
                is_choppy = curr['ker'] < self.ker_threshold
                z_score = curr['z_score']
                signal = None
                if is_choppy and z_score < -self.z_entry: signal = 'BUY'
                elif is_choppy and z_score > self.z_entry: signal = 'SELL'
                if signal: self._place_entry_order(signal, curr, symbol)
        except Exception as e: print(f"Error in StatArb: {e}")

    def _place_entry_order(self, signal, curr, spot_symbol):
        entry_price = curr['close']
        atr = curr['atr']
        if signal == 'BUY':
            stop_loss = entry_price - (atr * self.stop_atr_mult)
            risk_dist = entry_price - stop_loss
        else:
            stop_loss = entry_price + (atr * self.stop_atr_mult)
            risk_dist = stop_loss - entry_price
        if risk_dist <= 0: return
        lot_size = LOT_SIZE 
        est_delta = 0.55
        loss_per_lot = risk_dist * est_delta * lot_size
        if loss_per_lot == 0: return
        num_lots = max(1, int(self.risk_per_trade_rs / loss_per_lot))
        num_lots = min(num_lots, 10)
        premium, symbol, strike = self.get_option_params(entry_price, signal.lower(), self.broker)
        if not premium: return
        self.execute_trade(premium, 'buy', premium-20, premium+40, num_lots * lot_size, symbol=symbol)
        if self.position:
            self.position_state[spot_symbol] = {
                'option_symbol': symbol,
                'direction': signal,
                'entry_price_spot': entry_price,
                'stop_loss_spot': stop_loss,
                't1_dist': risk_dist * 1.5,
                'total_qty': num_lots * lot_size,
                'stage': 0,
                'risk_dist': risk_dist
            }

    def _check_exits(self, state, curr):
        current_spot = curr['close']
        initial_qty = state['total_qty']
        hit_stop = False
        if state['direction'] == 'BUY':
            if curr['low'] <= state['stop_loss_spot']: hit_stop = True
            dist_moved = current_spot - state['entry_price_spot']
        else:
            if curr['high'] >= state['stop_loss_spot']: hit_stop = True
            dist_moved = state['entry_price_spot'] - current_spot
        if hit_stop:
            self._final_close("Stop Hit")
            return
        if state['stage'] == 0 and dist_moved >= state['t1_dist']:
            qty_to_close = int(initial_qty * 0.90)
            if qty_to_close > 0:
                if self.broker and hasattr(self.broker, 'close_position'):
                    self.broker.close_position(state['option_symbol'], qty=qty_to_close)
                state['stage'] = 1
                state['stop_loss_spot'] = state['entry_price_spot']
                self.status = "T1 Hit. Runner active with BE stop."

    def _update_trailing_stop(self, state, curr):
        current_spot = curr['close']
        atr = curr['atr']
        trail_dist = atr * 1.5
        if state['direction'] == 'BUY':
            new_stop = current_spot - trail_dist
            if new_stop > state['stop_loss_spot']: state['stop_loss_spot'] = new_stop
        else:
            new_stop = current_spot + trail_dist
            if new_stop < state['stop_loss_spot']: state['stop_loss_spot'] = new_stop

    def _final_close(self, reason):
        if self.position and self.broker:
            sym = self.position['symbol']
            curr_price = self.broker.get_current_price(sym) or self.position['entry']
            self.close_trade(curr_price, reason)
        self.position_state = {}

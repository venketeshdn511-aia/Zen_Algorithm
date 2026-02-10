from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_rsi, calculate_atr, calculate_ema, calculate_adx, calculate_macd
import re
from datetime import datetime

class EnhancedORBStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Enhanced ORB", INITIAL_CAPITAL)
        self.allowed_regimes = ['TREND', 'RANGE']
        self.risk_pct = 0.15
        self.rr_ratio = 2.5
        self.broker = broker
        self.orb_high = None
        self.orb_low = None
        
    def process(self, df, current_bar):
        row = df.iloc[-1]
        
        if len(df) >= 3 and self.orb_high is None:
            first_3 = df.iloc[:3]
            self.orb_high = first_3['high'].max()
            self.orb_low = first_3['low'].min()
            self.status = f"ORB Level established: {self.orb_low:.1f} - {self.orb_high:.1f}."
        
        if self.orb_high is None:
            self.status = f"Calculating initial range ({len(df)}/3 bars)."
            return
        
        spot_price = float(row['close'])
        
        if self.position is None:
            if spot_price > self.orb_high - 10 and spot_price <= self.orb_high:
                self.status = f"Nifty at {spot_price:.1f} near ORB High. Monitoring."
            elif spot_price > self.orb_high:
                self.status = "High-side breakout detected."
            elif spot_price < self.orb_low:
                self.status = "Breakdown below ORB Low detected (Filter: Long Only)."
            else:
                self.status = f"Nifty ({spot_price:.1f}) within range."

            if spot_price > self.orb_high and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist = spot_price - self.orb_low
                stop_dist_premium = stop_dist * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Executed {symbol} at {premium}. Tgt: {target:.1f}."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                
                spot_stop = pos.get('spot_stop', 0)
                current_spot = float(df['close'].iloc[-1])
                self.status = f"Long {symbol}: ₹{curr_premium:.1f} | Trail: {spot_stop:.0f}"
                
                if self.check_spot_trailing_stop(df):
                    self.status = f"Spot Trail Hit @ {spot_stop:.0f}. Exit at ₹{curr_premium:.1f}"
                    self.close_trade(curr_premium, 'trailing_stop')
                    return
                
                if curr_premium <= pos['stop']:
                    self.close_trade(curr_premium, 'stop')
                elif curr_premium >= pos['target']:
                    self.close_trade(curr_premium, 'target')

class RSIPullbackStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("RSI Pullback", INITIAL_CAPITAL)
        self.allowed_regimes = ['REVERSAL']
        self.risk_pct = 0.10
        self.rr_ratio = 2.0
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 60: return
        
        df['sma50'] = df['close'].rolling(window=50).mean()
        df['rsi'] = calculate_rsi(df['close'], 14)
        atr = calculate_atr(df, 14).iloc[-1]
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        spot_price = float(row['close'])
        rsi = row['rsi']
        
        if self.position is None:
            self.status = f"RSI: {rsi:.1f}. SMA50 alignment confirmed. Scan active."
            # Long: RSI crosses above 35 + Price > SMA50
            if (prev['rsi'] < 35 and row['rsi'] >= 35 and 
                row['close'] > df['sma50'].iloc[-1] and self.broker):
                
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist_premium = (atr * 2) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Long {symbol} at {premium} (RSI 35 Confirmation)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                
                self.status = f"Active {pos['symbol']}: Premium {curr_premium:.1f}. RSI: {rsi:.1f}."
                if curr_premium <= pos['stop']: 
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')

class TripleEMAStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Triple EMA", INITIAL_CAPITAL)
        self.allowed_regimes = ['TREND']
        self.risk_pct = 0.05
        self.rr_ratio = 2.0
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 40: return
        df['ema5'] = calculate_ema(df['close'], 5)
        df['ema13'] = calculate_ema(df['close'], 13)
        df['ema34'] = calculate_ema(df['close'], 34)
        atr = calculate_atr(df, 14).iloc[-1]
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = "Trend aligned (Bullish). Scanning for entry." if row['ema5'] > row['ema13'] > row['ema34'] else "Wait."
            if (row['ema5'] > row['ema13'] > row['ema34'] and
                prev['ema5'] <= prev['ema13'] and self.broker):
                
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist_premium = (atr * 2) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Long {symbol} at {premium} (Trend Follow)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                self.status = f"Active {pos['symbol']}: Premium {curr_premium:.1f}."
                if curr_premium <= pos['stop']: 
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')

class MomentumSurgeStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Momentum Surge", INITIAL_CAPITAL)
        self.allowed_regimes = ['TREND']
        self.risk_pct = 0.025
        self.rr_ratio = 1.3
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 30: return
        df['momentum'] = df['close'].pct_change(5) * 100
        df['sma20'] = df['close'].rolling(window=20).mean()
        atr = calculate_atr(df, 14).iloc[-1]
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = f"Momentum: {row['momentum']:.2f}%"
            if (prev['momentum'] < 0.5 and row['momentum'] >= 0.5 and
                row['close'] > df['sma20'].iloc[-1] and self.broker):
                
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist_premium = (atr * 1.5) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Long {symbol} at {premium} (Surge)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                self.status = f"Active {pos['symbol']}: Premium {curr_premium:.1f}."
                if curr_premium <= pos['stop']: 
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')

class BandReversionStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Band Reversion", INITIAL_CAPITAL)
        self.allowed_regimes = ['REVERSAL', 'RANGE']
        self.risk_pct = 0.015
        self.rr_ratio = 1.2
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 110: return
        df['sma20'] = df['close'].rolling(window=20).mean()
        df['std20'] = df['close'].rolling(window=20).std()
        df['lower_band'] = df['sma20'] - (2.5 * df['std20'])
        df['sma100'] = df['close'].rolling(window=100).mean()
        atr = calculate_atr(df, 14).iloc[-1]
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = "Scanning for Lower Band oversold."
            if (prev['low'] < prev['lower_band'] and
                row['close'] > row['lower_band'] and
                row['close'] > df['sma100'].iloc[-1] and self.broker):
                
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist_premium = (atr * 1.5) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Long {symbol} at {premium} (Reversion)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                self.status = f"Active {pos['symbol']}: Premium {curr_premium:.1f}."
                if curr_premium <= pos['stop']: 
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')

class EMARegimeStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("EMA Regime", INITIAL_CAPITAL)
        self.risk_pct = 0.015
        self.rr_ratio = 1.3
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 60: return
        df['ema5'] = calculate_ema(df['close'], 5)
        df['ema13'] = calculate_ema(df['close'], 13)
        df['ema50'] = calculate_ema(df['close'], 50)
        df['adx'] = calculate_adx(df, 14)
        atr = calculate_atr(df, 14).iloc[-1]
        
        row = df.iloc[-1]
        prev = df.iloc[-2]
        spot_price = float(row['close'])
        
        ema50_rising = row['ema50'] > df['ema50'].iloc[-10]
        adx_strength = row['adx'] > 20
        dist_filter = row['close'] > (row['ema50'] * 1.0005)
        
        if self.position is None:
            self.status = f"Trend: {row['adx']:.1f}"
            if (prev['ema5'] <= prev['ema13'] and 
                row['ema5'] > row['ema13'] and 
                ema50_rising and
                row['close'] > row['ema50'] and
                adx_strength and
                dist_filter and
                self.broker):
                
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist_premium = (atr * 1.5) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Long {symbol} at {premium} (Regime Breakout v2)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                self.status = f"Active {pos['symbol']}: Premium {curr_premium:.1f}."
                if curr_premium <= pos['stop']: 
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')

class MACDMomentumStrategy(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("MACD Momentum", INITIAL_CAPITAL)
        self.risk_pct = 0.05
        self.rr_ratio = 1.5
        self.broker = broker
        
    def process(self, df, current_bar):
        if len(df) < 30: return
        row = df.iloc[-1]
        spot_price = float(row['close'])
        
        macd, signal, histogram = calculate_macd(df['close'])
        df['macd'] = macd
        df['signal'] = signal
        df['histogram'] = histogram
        atr = calculate_atr(df, 14).iloc[-1]
        
        if self.position is None:
            self.status = "MACD Scan."
            if (df['macd'].iloc[-2] <= df['signal'].iloc[-2] and 
                df['macd'].iloc[-1] > df['signal'].iloc[-1] and 
                df['histogram'].iloc[-1] > 0 and self.broker):
                
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                
                stop_dist_premium = (atr * 2) * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                
                self.status = f"Long {symbol} at {premium} (MACD)."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', pos['symbol'])
            if match and self.broker:
                curr_premium = self.broker.fyers.get_option_chain(int(match.group(1)), match.group(2))
                if not curr_premium: return
                self.status = f"Active {pos['symbol']}: Premium {curr_premium:.1f}"
                if curr_premium <= pos['stop']: 
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: 
                    self.close_trade(pos['target'], 'target')

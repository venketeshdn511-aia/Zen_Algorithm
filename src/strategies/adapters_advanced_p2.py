from src.core.base_strategy import BaseStrategy, INITIAL_CAPITAL, LOT_SIZE
from src.utils.indicators import calculate_atr
from src.strategies.failed_auction_strategy import FailedAuctionStrategy
from src.strategies.inside_bar_breakout_strategy import InsideBarBreakoutStrategy
from src.strategies.institutional_strategy import InstitutionalStrategy
from src.strategies.bearish_breaker_strategy import BearishBreakerStrategy
from src.strategies.composite_operator_strategy import CompositeOperatorStrategy
from src.strategies.amd_setup_strategy import AMDSetupStrategy
from src.strategies.poor_low_strategy import PoorLowStrategy
from src.strategies.pdh_sweep_strategy import PDHSweepStrategy
from src.strategies.orb_breakout_short_strategy import ORBBreakoutShortStrategy
import re
import pandas as pd
from datetime import datetime
import pytz

class FailedAuctionAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Failed Auction b2", INITIAL_CAPITAL)
        self.allowed_regimes = ["REVERSAL"] 
        self.risk_pct = 0.02
        self.rr_ratio = 2.0
        self.broker = broker
        self.strategy = FailedAuctionStrategy()
        
    def process(self, df, current_bar):
        if len(df) < 200: return
        try:
             logic_df = df.resample('15min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        except: return
        logic_df = logic_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        signal = self.strategy.calculate_signal(logic_df)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        
        if self.position is None:
             self.status = self.strategy.get_status()
             if signal in ['buy', 'sell'] and self.broker:
                 premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                 if not premium: return
                 entry_data = self.strategy.last_signal_data
                 spot_risk = entry_data['risk']
                 stop_dist_premium = spot_risk * 0.5
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
                 if curr_premium <= pos['stop']: self.close_trade(pos['stop'], 'stop')
                 elif curr_premium >= pos['target']: self.close_trade(pos['target'], 'target')

class InsideBarBreakoutAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Inside Bar Breakout", INITIAL_CAPITAL)
        self.allowed_regimes = ["REVERSAL", "TREND"]
        self.risk_pct = 0.02
        self.rr_ratio = 2.0
        self.broker = broker
        self.strategy = InsideBarBreakoutStrategy()
    def process(self, df, current_bar):
        if len(df) < 200: return
        try: logic_df = df.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        except: return
        logic_df = logic_df.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        signal = self.strategy.calculate_signal(logic_df)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status()
            if signal == 'sell' and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                spot_risk = entry_data['risk']
                stop_dist_premium = spot_risk * 0.5
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
                if curr_premium <= pos['stop']: self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: self.close_trade(pos['target'], 'target')

class InstitutionalStrategyAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Institutional VWAP", INITIAL_CAPITAL)
        self.allowed_regimes = ['REVERSAL']
        self.risk_pct = 0.02
        self.rr_ratio = 2.0
        self.broker = broker
        self.strategy = InstitutionalStrategy()
    def process(self, df, current_bar):
        if len(df) < 50: return
        resampled_5m = self.resample_to_5m(df)
        df_adapter = resampled_5m.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        signal = self.strategy.calculate_signal(df_adapter)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status()
            if signal in ['buy', 'sell'] and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                spot_risk = abs(spot_price - entry_data['stop_loss'])
                stop_dist_premium = spot_risk * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                self.status = f"Executed {symbol} at {premium}."
                self.execute_trade(premium, 'buy', stop, target, LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.get_current_price(symbol, pos.get('entry'))
                if not curr_premium: return
                spot_stop = pos.get('spot_stop', 0)
                current_spot = float(df['close'].iloc[-1])
                self.status = f"Long {symbol}: {curr_premium:.1f} | Trail: {spot_stop:.0f}"
                if signal == 'exit_reversal':
                    self.close_trade(curr_premium, 'ema_reversal')
                    return
                if self.check_spot_trailing_stop(df):
                    self.close_trade(curr_premium, 'trailing_stop')
                    return
                if curr_premium <= pos['stop']: self.close_trade(curr_premium, 'stop')
                elif curr_premium >= pos['target']: self.close_trade(curr_premium, 'target')

class BearishBreakerAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Bearish Breaker", INITIAL_CAPITAL)
        self.allowed_regimes = ["REVERSAL", "TREND"]
        self.risk_pct = 0.02
        self.rr_ratio = 2.5
        self.broker = broker
        self.strategy = BearishBreakerStrategy(rr_ratio=self.rr_ratio)
    def process(self, df, current_bar):
        if len(df) < 50: return
        resampled_5m = self.resample_to_5m(df)
        df_adapter = resampled_5m.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        signal = self.strategy.calculate_signal(df_adapter)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status()
            if signal == 'sell' and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                spot_risk = entry_data['risk']
                stop_dist_premium = spot_risk * 0.5 
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
                if curr_premium <= pos['stop']: self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: self.close_trade(pos['target'], 'target')

class CompositeOperatorAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Composite Operator", INITIAL_CAPITAL)
        self.allowed_regimes = ["TREND", "REVERSAL", "RANGE"]
        self.risk_pct = 0.02
        self.broker = broker
        self.strategy = CompositeOperatorStrategy()
    def process(self, df, current_bar):
        if len(df) < 50: return
        df_adapter = df.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        if 'datetime' not in df_adapter.columns and isinstance(df_adapter.index, pd.DatetimeIndex):
             df_adapter['datetime'] = df_adapter.index
        signal = self.strategy.calculate_signal(df_adapter)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status()
            if signal == 'buy' and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'buy', self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                stop_dist_spot = entry_data['entry'] - entry_data['stop_loss']
                stop_dist_premium = stop_dist_spot * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.strategy.rr)
                risk_amt = self.capital * self.risk_pct
                qty = int(risk_amt / stop_dist_premium) if stop_dist_premium > 0 else LOT_SIZE
                lots = max(1, qty // LOT_SIZE)
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
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}"
                if curr_premium <= pos['stop']: self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: self.close_trade(pos['target'], 'target')

class AMDSetupAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("AMD Setup", INITIAL_CAPITAL)
        self.allowed_regimes = ["REVERSAL", "TREND"]
        self.risk_pct = 0.02
        self.rr_ratio = 2.0
        self.broker = broker
        self.strategy = AMDSetupStrategy()
    def process(self, df, current_bar):
        if len(df) < 70: return
        df_adapter = df.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        signal = self.strategy.calculate_signal(df_adapter)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status() or "Scanning for AMD setup."
            if signal in ['buy', 'sell'] and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                spot_risk = abs(spot_price - entry_data.get('stop_loss', spot_price))
                stop_dist_premium = spot_risk * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                pattern = entry_data.get('pattern', 'AMD Pattern')
                self.status = f"Executed {symbol} at {premium} ({pattern})."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            self.update_trailing_stop(df)
            pos = self.position
            symbol = pos['symbol']
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                curr_premium = self.broker.get_current_price(symbol, pos.get('entry'))
                if not curr_premium: return
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}. SL: {pos['stop']:.1f}"
                if curr_premium <= pos['stop']: self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: self.close_trade(pos['target'], 'target')

class PoorLowAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("Poor Low Target", INITIAL_CAPITAL)
        self.allowed_regimes = ["REVERSAL", "TREND"]
        self.risk_pct = 0.02
        self.rr_ratio = 4.8
        self.broker = broker
        self.strategy = PoorLowStrategy()
    def process(self, df, current_bar):
        resampled_5m = self.resample_to_5m(df)
        logic_df = resampled_5m.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        if len(logic_df) < 50: return
        signal = self.strategy.calculate_signal(logic_df)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status()
            if signal in ['buy', 'sell'] and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, signal, self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                spot_risk = entry_data.get('risk', 10)
                stop_dist_premium = spot_risk * 0.5
                stop = premium - stop_dist_premium
                target = premium + (stop_dist_premium * self.rr_ratio)
                risk_amount = self.capital * self.risk_pct
                lots = max(1, int(risk_amount / (stop_dist_premium * LOT_SIZE)))
                self.status = f"Executed {symbol} at {premium}."
                self.execute_trade(premium, 'buy', stop, target, lots * LOT_SIZE, symbol=symbol)
        else:
            pos = self.position
            symbol = pos['symbol']
            match = re.search(r'NIFTY[A-Z0-9]+?(\d{5})(CE|PE)', symbol)
            if match and self.broker:
                # Use exact symbol for pricing to avoid expiry mismatch
                curr_premium = self.broker.get_current_price(symbol, pos.get('entry'))
                if not curr_premium: return
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}. Target: {pos['target']:.1f}"
                if signal == 'exit_reversal':
                    self.close_trade(curr_premium, 'ema_reversal')
                elif curr_premium <= pos['stop']:
                    self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']:
                    self.close_trade(pos['target'], 'target')

class PDHSweepAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("PDH Sweep", INITIAL_CAPITAL)
        self.broker = broker
        self.strategy = PDHSweepStrategy()
        self.risk_pct = 0.01
        self.rr_ratio = 2.5
        self.allowed_regimes = ["REVERSAL", "TREND"]
    def process(self, df, current_bar):
        if len(df) < 50: return
        resampled_5m = self.resample_to_5m(df)
        logic_df = resampled_5m.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
        if len(logic_df) < 50: return
        signal = self.strategy.calculate_signal(logic_df)
        row = df.iloc[-1]
        spot_price = float(row['close'])
        if self.position is None:
            self.status = self.strategy.get_status()
            if signal == 'sell' and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker)
                if not premium: return
                entry_data = self.strategy.last_signal_data
                spot_risk = entry_data.get('risk', 20)
                stop_dist_premium = spot_risk * 0.5
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
                self.status = f"Long {symbol}: Premium {curr_premium:.1f}. Target: {pos['target']:.1f}"
                if curr_premium <= pos['stop']: self.close_trade(pos['stop'], 'stop')
                elif curr_premium >= pos['target']: self.close_trade(pos['target'], 'target')

class ORBBreakoutShortAdapter(BaseStrategy):
    def __init__(self, broker=None):
        super().__init__("ORB Breakout Short", INITIAL_CAPITAL)
        self.allowed_regimes = ["TREND"]
        self.risk_pct = 0.02
        self.rr_ratio = 4.4
        self.broker = broker
        self.strategy = ORBBreakoutShortStrategy()
        
    def process(self, df, current_bar):
        if len(df) < 50: return
        df_adapter = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        signal = self.strategy.calculate_signal(df_adapter)
        
        row = df.iloc[-1]
        spot_price = float(row['close'])
        
        if self.position is None:
            self.status = "Scanning for ORB breakdown (30m)."
            if signal == 'sell' and self.broker:
                premium, symbol, strike = self.get_option_params(spot_price, 'sell', self.broker)
                if not premium: return
                
                entry_data = self.strategy.last_signal_data
                spot_risk = entry_data['risk']
                stop_dist_premium = spot_risk * 0.5 
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

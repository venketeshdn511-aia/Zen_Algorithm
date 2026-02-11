"""
Composite Operator Accumulation Strategy_15m_5
Differs from standard price action by focusing on Volume Spread Analysis (VSA)
to detect institutional accumulation footprints.

Entry Logic:
- detect_composite_operator_bullish:
    - Relative Volume > 1.5 (High Effort)
    - Price stability or rejection of lows (Result matches Effort? No, looking for Absorption)
    - Pattern: High Volume + (Hammer OR Doji OR Bullish Engulfing)
        - Condition A (Stopping Volume): Red Candle, High Vol, Long Lower Wick checking new lows.
        - Condition B (Accumulation): Green Candle, High Vol, Closing near Highs.
- price_below_vwap: Price is in "Value" territory (Institutional buying usually happens here).
- rsi_above_30: Not in freefall/oversold extreme (Momentum validation).

Exit Logic:
- Stop Loss: Below recent Swing Low or Candle Low.
- Take Profit: RR 1:2 or VWAP Reversion.
"""
import pandas as pd
import numpy as np
from src.interfaces.strategy_interface import StrategyInterface

class CompositeOperatorStrategy(StrategyInterface):
    """
    Composite Operator Accumulation Strategy
    Focuses on High Volume "Footprints" in Value Areas (Below VWAP)
    """
    
    def __init__(self, risk_reward=2.0, rsi_period=14, vol_ma_period=20):
        super().__init__("Composite Operator Accumulation")
        self.rr = risk_reward
        self.rsi_period = rsi_period
        self.vol_ma_period = vol_ma_period
        self.current_status = "Initializing..."
        self.last_signal_data = {}
        
    def get_status(self):
        return self.current_status

    def _calc_rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calc_vwap(self, df):
        """Standard Intraday VWAP"""
        # Ensure we work on a copy to avoid side effects
        temp_df = df.copy()
        
        # Determine Grouping Key (Date)
        if isinstance(temp_df.index, pd.DatetimeIndex):
            temp_df['date_grp'] = temp_df.index.date
        elif 'datetime' in temp_df.columns:
            # If datetime column exists but not index
            if pd.api.types.is_datetime64_any_dtype(temp_df['datetime']):
                temp_df['date_grp'] = temp_df['datetime'].dt.date
            else:
                 # Try parsing? Or fallback
                 try:
                     temp_df['date_grp'] = pd.to_datetime(temp_df['datetime']).dt.date
                 except:
                     return (temp_df['Close'].rolling(50).mean()) # Fallback
        else:
            return (temp_df['Close'].rolling(50).mean()) 

        # Vectorized VWAP Calculation (No Apply)
        # 1. Calculate TPV for every row
        temp_df['tp'] = (temp_df['High'] + temp_df['Low'] + temp_df['Close']) / 3
        temp_df['tpv'] = temp_df['tp'] * temp_df['Volume']
        
        # 2. Cumulative Sums reset by Date Group
        # groupby().cumsum() is efficient and doesn't trigger the 'apply on grouping cols' warning
        temp_df['cum_tpv'] = temp_df.groupby('date_grp')['tpv'].cumsum()
        temp_df['cum_vol'] = temp_df.groupby('date_grp')['Volume'].cumsum()
        
        # 3. VWAP
        return temp_df['cum_tpv'] / temp_df['cum_vol']

    def calculate_signal(self, df):
        if len(df) < 50:
            return None
            
        # 1. Indicators
        # Ensure we work on a copy to avoid SettingWithCopy warnings
        df = df.copy()
        
        # RSI
        df['rsi'] = self._calc_rsi(df['Close'], self.rsi_period)
        
        # Volume MA
        df['vol_ma'] = df['Volume'].rolling(self.vol_ma_period).mean()
        df['rel_vol'] = df['Volume'] / df['vol_ma']
        
        # VWAP
        try:
            df['vwap'] = self._calc_vwap(df)
        except Exception as e:
            # Fallback for small slices without date info
            df['vwap'] = df['Close'].rolling(20).mean()
        
        # Current Candle (Last completed usually, or current forming? 
        # Strategy generator usually implies 'completed' bars if backtesting.
        # But 'live' sends current snapshot. We usually check the -1 (last closed) bar for signals.)
        
        current = df.iloc[-1] # This is the "Latest" bar.
        # If live, this might be partial. Standard practice: Check confirmed candles (-2 if -1 is forming, or -1 if -1 is completed).
        # We'll assume function is called on "Completed Bars" or we check the last one.
        
        idx = -1
        row = df.iloc[idx]
        
        # 2. Conditions
        
        # A. Detect Composite Operator (High Volume Accumulation)
        # Condition: High Relative Volume (> 1.5)
        is_high_volume = row['rel_vol'] > 1.5
        
        # Structure:
        # 1. Stopping Volume (Hammer / Pinbar at lows)
        body_size = abs(row['Close'] - row['Open'])
        candle_range = row['High'] - row['Low']
        lower_wick = min(row['Close'], row['Open']) - row['Low']
        
        is_hammer = (lower_wick > 2 * body_size) and (lower_wick > 0.4 * candle_range)
        is_bullish_close = row['Close'] > row['Open']
        
        # Accumulation Logic:
        # - Rejecting lows (Hammer) with High Volume
        # - Strong Bullish Close (Green) with High Volume
        # - "Effort to rise": Price is moving up on high volume
        
        composite_bullish = False
        
        if is_high_volume:
            if is_hammer:
                 composite_bullish = True
                 pattern_name = "CO: Stopping Volume (Hammer)"
            elif is_bullish_close and (body_size > 0.5 * candle_range): # Strong green candle
                 composite_bullish = True
                 pattern_name = "CO: High Vol Accumulation"
            
        # B. Price Below VWAP (Value Zone)
        # We want to buy when Institutions buy - cheaply.
        is_below_vwap = row['Close'] < row['vwap']
        
        # C. RSI Above 30 (Not dead)
        is_rsi_valid = row['rsi'] > 30
        
        # D. Combined Trigger
        if composite_bullish and is_below_vwap and is_rsi_valid:
            
            # Entry Params
            atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
            entry_price = row['Close']
            
            # Stop Loss below the Low of the setup candle (minus buffer)
            stop_loss = row['Low'] - (atr * 0.2)
            
            risk = entry_price - stop_loss
            if risk < (entry_price * 0.001): # Min risk 0.1% to avoid huge size
                risk = entry_price * 0.001
                stop_loss = entry_price - risk
                
            take_profit = entry_price + (risk * self.rr)
            
            self.last_signal_data = {
                'side': 'buy',
                'pattern': pattern_name,
                'entry': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk': risk,
                'rsi': row['rsi'],
                'rel_vol': row['rel_vol']
            }
            
            self.current_status = f" BUY SIGNAL: {pattern_name} @ {entry_price:.2f}"
            return 'buy'
            
        self.current_status = f"Monitoring.. Vol: {row['rel_vol']:.1f}x | RSI: {row['rsi']:.0f} | <VWAP: {is_below_vwap}"
        return None

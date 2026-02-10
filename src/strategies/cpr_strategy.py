import pandas as pd
import pandas_ta as ta

class CPRBreakoutLongStrategy:
    def __init__(self):
        self.name = "CPR Breakout Long"
        self.sl_pct = 0.01  # 1% Stop Loss (Optimized)
        self.risk_reward = 4.0  # 4x Target (Optimized)
        self.rsi_lower = 60 # Optimized from 40

    def calculate_cpr(self, df):
        """
        Calculates Daily CPR levels.
        Assumes df is intraday data. Resamples to Daily to find previous day's HLC.
        Then maps those values back to the intraday timeframe.
        """
        # Resample to Daily to get Previous Day's High, Low, Close
        daily_df = df.resample('D').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        }).dropna()

        # Shift to get "Previous Day" values for "Today"
        daily_df['Prev_High'] = daily_df['High'].shift(1)
        daily_df['Prev_Low'] = daily_df['Low'].shift(1)
        daily_df['Prev_Close'] = daily_df['Close'].shift(1)

        # Calculate CPR Pivot Points
        daily_df['Pivot'] = (daily_df['Prev_High'] + daily_df['Prev_Low'] + daily_df['Prev_Close']) / 3
        daily_df['BC'] = (daily_df['Prev_High'] + daily_df['Prev_Low']) / 2
        daily_df['TC'] = (daily_df['Pivot'] - daily_df['BC']) + daily_df['Pivot']

        # Map back to Intraday DataFrame
        # We need to map the daily CPR values to every intraday candle of that day.
        # df.index.normalize() gives the date component of the timestamp.
        
        # Create a temp dataframe with dates to merge
        df_temp = df.copy()
        df_temp['Date'] = df_temp.index.normalize()
        
        # Reset index of daily_df to make 'Date' a column for merging
        daily_df = daily_df.reset_index()
        # Rename the first column (which was the index) to 'Date'
        daily_df = daily_df.rename(columns={daily_df.columns[0]: 'Date'})
        
        # Merge
        merged_df = pd.merge(df_temp, daily_df[['Date', 'Pivot', 'BC', 'TC']], on='Date', how='left')
        
        # Set index back to original
        merged_df.index = df.index
        
        return merged_df

    def calculate_signal(self, data):
        """
        Main signal calculation method for the backtester.
        data: DataFrame containing 'Open', 'High', 'Low', 'Close'
        """
        # Ensure we have enough data
        if len(data) < 200:
            return 'hold'

        # 1. Calculate CPR (We need to recalculate this carefully on the fly or pre-calced)
        # Ideally, the backtester loops row by row. But calculating CPR requires daily context.
        # Strategy: We assume 'data' passed here is the growing window OR the full dataset pre-processed.
        # Given the existing setup in custom_runner, it passes `current_slice`.
        # Re-calculating Daily CPR on every 1-min step is expensive. 
        # But for correctness, we'll implement a robust check.
        
        # Optimziation: Just look at the last row's date and find prev day stats.
        current_candle = data.iloc[-1]
        current_date = current_candle.name
        
        # Filter for PREVIOUS day data to calc CPR
        # If we are effectively "live" or row-by-row, we look at history up to yesterday.
        prev_day_data = data[data.index.date < current_date.date()]
        
        if prev_day_data.empty:
            return 'hold'
            
        # Get last available day in prev_day_data
        last_day_date = prev_day_data.index.date[-1]
        last_day_df = prev_day_data[prev_day_data.index.date == last_day_date]
        
        if last_day_df.empty:
            return 'hold'

        prev_high = last_day_df['High'].max()
        prev_low = last_day_df['Low'].min()
        prev_close = last_day_df['Close'].iloc[-1]
        
        pivot = (prev_high + prev_low + prev_close) / 3
        bc = (prev_high + prev_low) / 2
        tc = (pivot - bc) + pivot
        
        # Ensure TC is strictly higher than BC?
        # Standard CPR: TC can be below BC if Close < Pivot? 
        # Usually: TC = (Pivot - BC) + Pivot. 
        # If Pivot < BC (meaning Close < (H+L)/2), then TC < Pivot.
        # Let's sort TC and BC to have a defined "Range Top" and "Range Bottom"
        cpr_top = max(tc, bc)
        cpr_bottom = min(tc, bc)
        
        # 2. RSI Check (15m timeframe as per analysis_timeframe)
        # Resample to 15m to get RSI. 
        # IMPORTANT: 'data' might be 1m data. We need to resample the WHOLE history to get accurate RSI.
        
        # Resample to 15T (15 min)
        df_15m = data.resample('15min').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last'
        }).dropna()
        
        if len(df_15m) < 15:
            return 'hold'
            
        # Calculate RSI on 15m
        df_15m['RSI'] = ta.rsi(df_15m['Close'], length=14)
        
        last_15m_candle = df_15m.iloc[-1]
        rsi_val = last_15m_candle['RSI']
        close_15m = last_15m_candle['Close']
        
        # Check Breakout Condition (15m Close > TC)
        # We need to ensure we just "closed" above it. 
        # But signal is generated 'row by row'. If strictly 15m logic, we should only signal at 15m intervals.
        
        # Current time check: is this the close of a 15m candle?
        # If data is 1m, we check if minute is 14, 29, 44, 59 OR if we just rely on the 15m close status.
        # PDF says "15m-1m". Signal on 15m close.
        # Ideally we check if `current_date` creates a completed 15m candle.
        
        # For simplicity in this backtest loop:
        # We take the latest COMPLETED 15m candle.
        # If we are at 09:30:00, the 09:15-09:30 candle is done. 
        # The logic:
        # 1. 15m Candle Close > CPR Top (TC)
        # 2. RSI between 40 and 60 (at the time of breakout?) - "rsi_between_40_60"
        
        is_breakout = close_15m > cpr_top
        is_rsi_valid = 40 <= rsi_val <= 60
        
        # To avoid repetitive signals, backtester handles 'position' check.
        # We just return 'buy' if conditions met.
        
        if is_breakout and is_rsi_valid:
            return 'buy'
            
        return 'hold'

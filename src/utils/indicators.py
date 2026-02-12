import pandas as pd
import numpy as np

# ============= INDICATOR CALCULATIONS =============
def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 0.0001)
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_adx(df, period=14):
    """Calculate Average Directional Index (ADX)"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr = pd.concat([
        high - low, 
        abs(high - close.shift(1)), 
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    plus_di = 100 * (plus_dm.ewm(alpha=1/period).mean() / atr)
    minus_di = 100 * (abs(minus_dm).ewm(alpha=1/period).mean() / atr)
    dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
    adx = dx.rolling(window=period).mean()
    return adx

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line

def calculate_vwap(df):
    """
    Calculate VWAP (Volume Weighted Average Price) that resets per trading day.
    This prevents cumulative VWAP across multiple days which would bias the indicator.
    """
    import pandas as pd
    
    v = df['volume']
    tp = (df['high'] + df['low'] + df['close']) / 3
    
    # Try to group by date for per-day VWAP
    try:
        # If index is DatetimeIndex, extract date
        if isinstance(df.index, pd.DatetimeIndex):
            date_col = df.index.date
        elif 'datetime' in df.columns:
            date_col = pd.to_datetime(df['datetime']).dt.date
        else:
            # Fallback to cumulative if no date info
            return (tp * v).cumsum() / v.cumsum()
        
        # Calculate VWAP per day
        df_temp = df.copy()
        df_temp['date_grp'] = date_col
        df_temp['tp'] = tp
        df_temp['tpv'] = tp * v
        
        # Group by date and calculate cumulative within each day
        vwap = df_temp.groupby('date_grp').apply(
            lambda x: x['tpv'].cumsum() / x['volume'].cumsum()
        ).reset_index(level=0, drop=True)
        
        return vwap
        
    except Exception as e:
        print(f" [VWAP] Per-day calculation failed: {e}, using cumulative fallback")
        return (tp * v).cumsum() / v.cumsum()

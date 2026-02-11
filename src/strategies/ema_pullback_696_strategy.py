import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

def ema(prices: np.ndarray, period: int) -> np.ndarray:
    if len(prices) < period:
        return np.full_like(prices, np.nan)
    result = np.full_like(prices, np.nan, dtype=float)
    multiplier = 2.0 / (period + 1)
    result[period - 1] = np.mean(prices[:period])
    for i in range(period, len(prices)):
        result[i] = (prices[i] - result[i - 1]) * multiplier + result[i - 1]
    return result

def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    if len(high) < period + 1:
        return np.full_like(high, np.nan)
    result = np.full_like(high, np.nan, dtype=float)
    tr = np.zeros(len(high))
    tr[0] = high[0] - low[0]
    for i in range(1, len(high)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)
    result[period - 1] = np.mean(tr[:period])
    for i in range(period, len(high)):
        result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result

def detect_kill_zone(current_timestamp: datetime, market: str = "NSE") -> bool:
    t = current_timestamp.time()
    am_start = datetime.strptime("09:15", "%H:%M").time()
    am_end = datetime.strptime("11:00", "%H:%M").time()
    pm_start = datetime.strptime("13:30", "%H:%M").time()
    pm_end = datetime.strptime("15:00", "%H:%M").time()
    return (am_start <= t <= am_end) or (pm_start <= t <= pm_end)

class EMAPullback696Strategy:
    """
    EMA Pullback Short 696 Strategy (Production Version)
    - Timeframe: 15m-1m MTF
    - Logic: Rally to Fast EMA in bearish trend + Kill Zone
    - Parameters: EMA Fast (9), EMA Slow (50)
    - Risk: 4.2 RR with Trailing SL
    """
    def __init__(self):
        self.name = "EMA Pullback Short 696"
        self.ema_fast_len = 9
        self.ema_slow_len = 50
        self.risk_reward = 4.2
        self.trailing_sl = True
        self.last_signal_data = {}
        self._status = "Initializing..."

    def get_status(self):
        return self._status

    def calculate_signal(self, df: pd.DataFrame) -> Optional[str]:
        if len(df) < self.ema_slow_len:
            self._status = f"Warmup ({len(df)}/{self.ema_slow_len})"
            return None

        # Standardize columns
        df.columns = [c.lower() for c in df.columns]
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        ema_fast = ema(close, self.ema_fast_len)
        ema_slow = ema(close, self.ema_slow_len)
        atr_vals = atr(high, low, close, 14)
        
        idx = -1
        p_close = close[idx]
        p_high = high[idx]
        p_low = low[idx]
        f_ema = ema_fast[idx]
        s_ema = ema_slow[idx]
        curr_atr = atr_vals[idx]

        if np.isnan(f_ema) or np.isnan(s_ema):
            return None

        # Check Kill Zone
        is_kz = detect_kill_zone(df.index[idx])
        if not is_kz:
            self._status = " Cooling off. Outside Kill Zone (Market is noisy right now)."
            return None

        # Trend and Pullback logic (SHORT)
        # Pullback: high touches or crosses above Fast EMA, close below it
        pullback = p_high >= f_ema and p_close < f_ema
        trend_bearish = f_ema < s_ema
        
        if trend_bearish:
            if pullback:
                risk = max(abs(p_close - p_low), abs(p_high - p_close))
                self.last_signal_data = {
                    'risk': risk,
                    'target_rr': self.risk_reward,
                    'stop_loss': p_close + risk,
                    'take_profit': p_close - (risk * self.risk_reward)
                }
                self._status = f" SETUP FOUND! Bearish pullback to {f_ema:.1f}. Entering Short at {p_close:.2f}."
                return 'buy'
            else:
                self._status = f" Trend is Bearish. Waiting for a rally towards EMA {f_ema:.1f} to sell high."
        else:
            self._status = f" Bearish trend lost. (EMA {f_ema:.1f} > {s_ema:.1f}). Looking for a structural flip."

        return None

    def check_exit(self, df: pd.DataFrame, position: dict) -> Tuple[bool, str]:
        # Engine handles TSL and Stop/Target by default
        # No pattern-based exit required for this strategy
        return False, ""

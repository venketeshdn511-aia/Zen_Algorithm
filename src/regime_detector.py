import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

class MarketRegimeGovernor:
    """
    Market Regime Governor
    
    Determines the market environment (TREND, RANGE, REVERSAL) based on statistical scoring
    smoothed over a rolling window (7-15 days).
    
    Regimes:
    - TREND: High ADX, strong directional consistency.
    - RANGE: Oscillating around mean (VWAP), low directional efficiency.
    - REVERSAL: High frequency of long wicks, failed breakouts.
    """
    
    def __init__(self, broker, logger=None, lookback_days=15):
        self.broker = broker
        self.logger = logger or logging.getLogger(__name__)
        self.lookback_days = lookback_days
        
        self.current_regime = "RANGE" # Default safe state
        self.confidence = 0.0
        self.regime_history = []
        
        # Scoring components
        self.trend_score = 0
        self.range_score = 0
        self.reversal_score = 0
        
        # Manual Override
        self.is_manual = False
        self.manual_regime = "RANGE"

    def fetch_historical_data(self):
        """Fetch last 60 days of daily data for robust indicator calculation"""
        try:
            now = datetime.now()
            # Fetch 60 days to ensure ADX/ATR warm up
            from_date = (now - timedelta(days=60)).strftime('%Y-%m-%d')
            to_date = now.strftime('%Y-%m-%d')
            
            # Fetch NIFTY Index data
            data = {
                "symbol": "NSE:NIFTY50-INDEX",
                "resolution": "D", # Daily for regime macro view
                "date_format": "1",
                "range_from": from_date,
                "range_to": to_date,
                "cont_flag": "1"
            }
            
            # Try different methods to fetch history
            response = None
            
            # Method 1: Direct broker.api.history (FyersBroker)
            if hasattr(self.broker, 'api') and self.broker.api and hasattr(self.broker.api, 'history'):
                try:
                    response = self.broker.api.history(data)
                    self.logger.info("Using broker.api.history() for regime detection")
                except Exception as e:
                    self.logger.warning(f"broker.api.history failed: {e}")
            
            # Method 2: Nested broker.fyers.api.history (legacy/paper broker path)
            if response is None and hasattr(self.broker, 'fyers') and hasattr(self.broker.fyers, 'api') and self.broker.fyers.api:
                try:
                    response = self.broker.fyers.api.history(data)
                    self.logger.info("Using broker.fyers.api.history() for regime detection")
                except Exception as e:
                    self.logger.warning(f"broker.fyers.api.history failed: {e}")
            
            # Method 3: Use broker.get_latest_bars (works with KotakBroker and FyersBroker)
            if response is None and hasattr(self.broker, 'get_latest_bars'):
                try:
                    self.logger.info("Using broker.get_latest_bars() for regime detection")
                    df = self.broker.get_latest_bars("NSE:NIFTY50-INDEX", timeframe="D", limit=60)
                    if df is not None and not df.empty:
                        df.columns = [c.lower() for c in df.columns]
                        if 'date' not in df.columns and df.index.name:
                            df = df.reset_index()
                            df.rename(columns={df.columns[0]: 'date'}, inplace=True)
                        return df
                except Exception as e:
                    self.logger.warning(f"broker.get_latest_bars failed: {e}")
            
            if response is None:
                self.logger.warning("No history method available on broker - using default RANGE regime")
                return None
                    
            if not isinstance(response, dict) or response.get('s') != 'ok':
                self.logger.error(f"History fetch failed or unexpected format: {response}")
                return None
                
            cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            df = pd.DataFrame(response['candles'], columns=cols)
            
            # Convert timestamp
            df['date'] = pd.to_datetime(df['date'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata')
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching historical data for regime: {e}")
            return None

    def calculate_indicators(self, df):
        """Calculate necessary indicators for scoring"""
        # ADX for Trend
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            )
        )
        df['atr'] = df['tr'].rolling(14).mean()
        
        df['up_move'] = df['high'] - df['high'].shift()
        df['down_move'] = df['low'].shift() - df['low']
        
        df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
        df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
        
        df['plus_di'] = 100 * (df['plus_dm'].rolling(14).mean() / df['atr'])
        df['minus_di'] = 100 * (df['minus_dm'].rolling(14).mean() / df['atr'])
        
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        df['adx'] = df['dx'].rolling(14).mean()
        
        # VWAP (Approximation for Daily/Intraday) or SMA comparison
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        # Simple directional efficiency: abs(Close - Open) / (High - Low)
        df['efficiency'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])
        
        return df

    def calculate_scores(self, df):
        """Calculate 0-100 scores for Trend, Range, Reversal based on last bar(s)"""
        last = df.iloc[-1]
        
        # --- 1. TREND SCORE ---
        # Signals: High ADX, EMA alignment, High Efficiency
        
        adx_score = min(last['adx'] * 2, 100) # ADX 20 -> 40, ADX 50 -> 100
        eff_score = last['efficiency'] * 100 # High efficiency = Trend
        
        # EMA Slope Check (if enough data)
        trend_score = (
            (0.6 * adx_score) + 
            (0.4 * eff_score)
        )
        
        # --- 2. RANGE SCORE ---
        # Signals: Low ADX, Low Efficiency, Price chopping around mean
        
        low_adx_score = max(0, 100 - (last['adx'] * 2.5)) # ADX 20 -> 50, ADX < 10 -> High
        chop_score = (1 - last['efficiency']) * 100 # Low efficiency = Range
        
        range_score = (
            (0.5 * low_adx_score) + 
            (0.5 * chop_score)
        )
        
        # --- 3. REVERSAL SCORE ---
        # Signals: Long wicks (Pinbars), Overextended Price
        
        body_size = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        wick_size = total_range - body_size
        wick_ratio = (wick_size / total_range) if total_range > 0 else 0
        
        wick_score = wick_ratio * 100
        
        # RSI Extremes calculation could go here too for Reversal
        
        reversal_score = wick_score # Simple for now
        
        return trend_score, range_score, reversal_score

    def update_regime(self):
        """
        Main function to call periodically (e.g., daily or hourly).
        Updates current_regime based on historical data analysis.
        """
        if self.is_manual:
            self.current_regime = self.manual_regime
            self.confidence = 100.0
            return self.current_regime
            
        df = self.fetch_historical_data()
        
        if df is None or len(df) < 15:
            self.logger.warning("Insufficient data for regime Governor. Defaulting to RANGE.")
            self.current_regime = "RANGE"
            self.confidence = 0.0
            return "RANGE"
            
        df = self.calculate_indicators(df)
        
        # Calculate scores for the last 5 days to get a smooth recent average
        recent_df = df.iloc[-5:] 
        
        avg_trend = 0
        avg_range = 0
        avg_rever = 0
        
        for idx, row in recent_df.iterrows():
            # Create a mini-df just to pass the single row structure if needed, 
            # or refactor calculate_scores to take a row. 
            # Here we just pass the full df and pick the specific index logic if complex,
            # but our simple scorer uses 'last'.
            # Let's just create a dummy DF of one row for our helper:
            single_row_df = df.loc[[idx]] 
            t, r, v = self.calculate_scores(single_row_df)
            avg_trend += t
            avg_range += r
            avg_rever += v
            
        avg_trend /= 5
        avg_range /= 5
        avg_rever /= 5
        
        self.trend_score = avg_trend
        self.range_score = avg_range
        self.reversal_score = avg_rever
        
        # Determine Winner
        scores = {
            "TREND": avg_trend,
            "RANGE": avg_range,
            "REVERSAL": avg_rever
        }
        
        winner = max(scores, key=scores.get)
        self.current_regime = winner
        
        # Confidence: How much did it win by?
        # (Winner - RunnerUp) / Winner
        sorted_scores = sorted(scores.values(), reverse=True)
        margin = sorted_scores[0] - sorted_scores[1]
        self.confidence = min(100, (margin / 100) * 100 + 40) # Normalize a bit
        
        self.logger.info(f"Regime Updated: {self.current_regime} (Conf: {self.confidence:.1f}%) | "
                         f"T:{avg_trend:.0f} R:{avg_range:.0f} V:{avg_rever:.0f}")
                         
        return self.current_regime

    def get_regime_status(self):
        """Return status dict for Dashboard"""
        return {
            "regime": self.current_regime,
            "confidence": round(self.confidence, 1),
            "is_manual": self.is_manual,
            "scores": {
                "trend": round(self.trend_score, 1),
                "range": round(self.range_score, 1),
                "reversal": round(self.reversal_score, 1)
            }
        }

    def set_manual_mode(self, mode, regime="RANGE"):
        """Override the governor"""
        self.is_manual = mode
        if mode:
            self.manual_regime = regime
            self.current_regime = regime # Apply immediately
            self.confidence = 100.0
            self.logger.info(f"Regime Governor set to MANUAL: {regime}")
        else:
            self.logger.info("Regime Governor set to AUTO")
            self.update_regime()

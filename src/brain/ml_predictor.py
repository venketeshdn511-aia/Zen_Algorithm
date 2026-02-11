"""
ML Trade Predictor
Uses Machine Learning (Random Forest) to predict trade outcomes.
Requires scikit-learn.
"""

import logging
from typing import Dict, List, Optional
import pickle
import os

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import LabelEncoder
    import numpy as np
    ml_available = True
except ImportError:
    ml_available = False

class MLPredictor:
    """
    Predicts trade success probability using a Random Forest model.
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.model = None
        self.le_strategy = None
        self.le_regime = None
        self.is_ready = False
        
        if not ml_available:
            self.logger.warning("scikit-learn not installed. ML Predictor disabled.")
            
    def train(self, trades: List[Dict]) -> bool:
        """
        Train the model on historical trades.
        Requires at least 20 trades.
        """
        if not ml_available or len(trades) < 20:
            return False
            
        try:
            X = []
            y = []
            
            # Initialize encoders
            if not self.le_strategy:
                # Pre-fit with common values + unknown
                self.le_strategy = LabelEncoder()
                self.le_strategy.fit([t.get('strategy', 'Unknown') for t in trades] + ['Unknown'])
                
            if not self.le_regime:
                self.le_regime = LabelEncoder()
                self.le_regime.fit(['TREND', 'RANGE', 'REVERSAL', 'UNKNOWN'])
                
            for trade in trades:
                features = self._extract_features(trade)
                outcome = 1 if float(trade.get('pnl', 0)) > 0 else 0
                
                if features is not None:
                    X.append(features)
                    y.append(outcome)
            
            if len(X) < 20: return False
            
            self.model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
            self.model.fit(X, y)
            self.is_ready = True
            self.logger.info(f" ML Model trained on {len(X)} trades")
            return True
            
        except Exception as e:
            self.logger.error(f"ML Training failed: {e}")
            return False

    def predict(self, conditions: Dict) -> float:
        """
        Predict probability of win (0.0 to 1.0).
        Returns 0.5 if model not ready.
        """
        if not self.is_ready or not self.model:
            return 0.5
            
        try:
            features = self._extract_features(conditions)
            if features is None: return 0.5
            
            # Reshape for single sample
            X = np.array(features).reshape(1, -1)
            probs = self.model.predict_proba(X)
            # return probability of class 1 (win)
            return probs[0][1]
            
        except Exception as e:
            self.logger.error(f"Prediction failed: {e}")
            return 0.5

    def _extract_features(self, data: Dict) -> Optional[List[float]]:
        """
        Extract numerical features from trade/condition dict.
        Feature vector: [Strategy_Idx, Regime_Idx, Hour, RSI, ADX, ATR_Ratio]
        """
        try:
            # 1. Strategy (Categorical)
            strat = data.get('strategy', 'Unknown')
            try:
                strat_idx = self.le_strategy.transform([strat])[0]
            except:
                self.le_strategy.classes_ = np.append(self.le_strategy.classes_, strat)
                strat_idx = self.le_strategy.transform([strat])[0]

            # 2. Regime (Categorical)
            regime = data.get('regime', 'UNKNOWN')
            try:
                regime_idx = self.le_regime.transform([regime])[0]
            except:
                regime_idx = 0 # Default

            # 3. Time (Hour)
            hour = data.get('hour', 9) 
            if 'entry_time' in data: # Extraction from Trade object
                 # Simplified parsing
                 pass 
            
            # 4. Indicators (handle None)
            rsi = data.get('rsi') if data.get('rsi') is not None else 50.0
            adx = data.get('adx') if data.get('adx') is not None else 20.0
            atr = data.get('atr_ratio') if data.get('atr_ratio') is not None else 1.0
            
            return [strat_idx, regime_idx, float(hour), float(rsi), float(adx), float(atr)]
            
        except Exception:
            return None

    def save(self, path: str):
        if self.is_ready and ml_available:
            try:
                with open(path, 'wb') as f:
                    pickle.dump({
                        'model': self.model,
                        'le_strategy': self.le_strategy,
                        'le_regime': self.le_regime
                    }, f)
            except Exception as e:
                self.logger.error(f"Failed to save ML model: {e}")

    def load(self, path: str):
        if ml_available and os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                    self.model = data['model']
                    self.le_strategy = data['le_strategy']
                    self.le_regime = data['le_regime']
                    self.is_ready = True
            except Exception as e:
                self.logger.warning(f"Failed to load ML model: {e}")

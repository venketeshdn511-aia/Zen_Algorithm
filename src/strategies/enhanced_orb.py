"""
Enhanced Opening Range Breakout with Sweep + Reversal
Combines first candle logic with liquidity sweep confirmation for higher win rate.

Key Enhancement:
- Wait for price to SWEEP the first candle level (fake breakout)
- Then enter on REVERSAL back inside the range
- This increases win rate by avoiding false breakouts
"""

import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List


class EnhancedORBStrategy:
    """
    Enhanced Opening Range Breakout with Sweep Reversal.
    """
    
    def __init__(self, use_sma: bool = True, rr_ratio: float = 2.0, 
                 sweep_pips: float = 0.002):
        self.use_sma = use_sma
        self.rr_ratio = rr_ratio
        self.sweep_pips = sweep_pips  # 0.2% default sweep threshold
        
        self.first_candle: Dict[str, dict] = {}
        self.daily_state: Dict[str, dict] = {}
        
    def calculate_signal(self, df: pd.DataFrame, symbol: str = 'NIFTY') -> Optional[str]:
        """Generate signal with sweep reversal logic."""
        if len(df) < 250:
            return None
            
        df = df.copy()
        
        # Calculate SMAs
        if self.use_sma:
            df['SMA_200'] = df['close'].rolling(200).mean()
            df['SMA_50'] = df['close'].rolling(50).mean()
            sma_200 = float(df['SMA_200'].iloc[-1]) if not pd.isna(df['SMA_200'].iloc[-1]) else None
        else:
            sma_200 = None
        
        current_bar = df.iloc[-1]
        prev_bar = df.iloc[-2] if len(df) > 1 else current_bar
        
        current_price = float(current_bar['close'])
        current_high = float(current_bar['high'])
        current_low = float(current_bar['low'])
        current_open = float(current_bar['open'])
        current_time = current_bar.name
        
        prev_close = float(prev_bar['close'])
        
        # Get date string
        if hasattr(current_time, 'date'):
            current_date = str(current_time.date())
        else:
            current_date = str(current_time)[:10]
        
        # Extract time
        if hasattr(current_time, 'time'):
            bar_time = current_time.time()
        else:
            bar_time = time(9, 15)
        
        # Initialize daily state
        if current_date not in self.daily_state:
            self.daily_state[current_date] = {
                'high_swept': False,
                'low_swept': False,
                'trade_taken': False
            }
        
        # Store first candle (9:15-9:20)
        is_first_candle = bar_time >= time(9, 15) and bar_time < time(9, 20)
        
        if is_first_candle:
            self.first_candle[current_date] = {
                'high': current_high,
                'low': current_low,
                'open': current_open,
                'close': current_price,
                'range': current_high - current_low
            }
            return None
        
        # Check for first candle data
        if current_date not in self.first_candle:
            return None
            
        if self.daily_state[current_date]['trade_taken']:
            return None
        
        fc = self.first_candle[current_date]
        state = self.daily_state[current_date]
        
        # Trading window: 9:20 to 14:30
        if bar_time < time(9, 20) or bar_time >= time(14, 30):
            return None
        
        sweep_threshold = fc['range'] * self.sweep_pips
        
        # Check for HIGH SWEEP (potential SELL setup)
        if current_high > fc['high'] + sweep_threshold:
            state['high_swept'] = True
        
        # Check for LOW SWEEP (potential BUY setup)
        if current_low < fc['low'] - sweep_threshold:
            state['low_swept'] = True
        
        # SELL Signal: High was swept, now reversal candle closes back inside
        if state['high_swept'] and not state['low_swept']:
            # Reversal: current close is below first candle high AND bearish candle
            if current_price < fc['high'] and current_price < current_open:
                # Trend filter
                if self.use_sma and sma_200 and current_price > sma_200:
                    return None  # Skip if still above 200 SMA
                    
                state['trade_taken'] = True
                return 'sell'
        
        # BUY Signal: Low was swept, now reversal candle closes back inside
        if state['low_swept'] and not state['high_swept']:
            if current_price > fc['low'] and current_price > current_open:
                # Trend filter
                if self.use_sma and sma_200 and current_price < sma_200:
                    return None
                    
                state['trade_taken'] = True
                return 'buy'
        
        return None
    
    def get_stop_and_target(self, signal: str, entry: float, date_str: str) -> tuple:
        """Calculate stop and target."""
        if date_str not in self.first_candle:
            return None, None
            
        fc = self.first_candle[date_str]
        
        if signal == 'buy':
            # Stop below the sweep low
            stop = fc['low'] - fc['range'] * 0.5
            risk = entry - stop
            target = entry + risk * self.rr_ratio
        else:
            stop = fc['high'] + fc['range'] * 0.5
            risk = stop - entry
            target = entry - risk * self.rr_ratio
        
        return stop, target


def run_enhanced_orb_backtest(df: pd.DataFrame, params: dict, 
                              initial_capital: float = 15000, verbose: bool = False) -> dict:
    """Run enhanced ORB strategy backtest."""
    
    strategy = EnhancedORBStrategy(
        use_sma=params.get('use_sma', True),
        rr_ratio=params.get('rr_ratio', 2.0),
        sweep_pips=params.get('sweep_pips', 0.002)
    )
    
    capital = initial_capital
    position = None
    trades = []
    risk_pct = params.get('risk_pct', 0.50)
    
    for i in range(250, len(df)):
        bars = df.iloc[:i+1].copy()
        current_bar = bars.iloc[-1]
        current_price = float(current_bar['close'])
        current_high = float(current_bar['high'])
        current_low = float(current_bar['low'])
        current_time = current_bar.name
        
        if hasattr(current_time, 'date'):
            current_date = str(current_time.date())
        else:
            current_date = str(current_time)[:10]
        
        # Position management
        if position:
            hit_stop = False
            hit_target = False
            
            if position['side'] == 'buy':
                if current_low <= position['stop']:
                    hit_stop = True
                    exit_price = position['stop']
                elif current_high >= position['target']:
                    hit_target = True
                    exit_price = position['target']
            else:
                if current_high >= position['stop']:
                    hit_stop = True
                    exit_price = position['stop']
                elif current_low <= position['target']:
                    hit_target = True
                    exit_price = position['target']
            
            if hit_stop or hit_target:
                if position['side'] == 'buy':
                    pnl = (exit_price - position['entry']) * position['qty']
                else:
                    pnl = (position['entry'] - exit_price) * position['qty']
                    
                capital += pnl
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': current_time,
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': exit_price,
                    'pnl': pnl,
                    'reason': 'TARGET' if hit_target else 'STOP'
                })
                
                if verbose:
                    emoji = "" if pnl > 0 else ""
                    print(f"{emoji} Exit @ {exit_price:.2f} | PnL: {pnl:.2f}")
                    
                position = None
        
        # New entry
        if position is None and capital > 100:
            signal = strategy.calculate_signal(bars, 'NIFTY')
            
            if signal:
                stop, target = strategy.get_stop_and_target(signal, current_price, current_date)
                
                if stop and target:
                    stop_dist = abs(current_price - stop)
                    if stop_dist < 5:
                        continue
                    
                    max_loss = capital * risk_pct
                    qty = int(max_loss / stop_dist)
                    qty = max(1, min(qty, 50))
                    
                    position = {
                        'side': signal,
                        'entry': current_price,
                        'stop': stop,
                        'target': target,
                        'qty': qty,
                        'entry_time': current_time
                    }
                    
                    if verbose:
                        print(f" {signal.upper()} @ {current_price:.2f} | SL: {stop:.2f} | TP: {target:.2f}")
    
    # Close remaining
    if position:
        final_price = float(df['close'].iloc[-1])
        if position['side'] == 'buy':
            pnl = (final_price - position['entry']) * position['qty']
        else:
            pnl = (position['entry'] - final_price) * position['qty']
        capital += pnl
        trades.append({
            'entry_time': position['entry_time'],
            'exit_time': df.index[-1],
            'side': position['side'],
            'entry': position['entry'],
            'exit': final_price,
            'pnl': pnl,
            'reason': 'END'
        })
    
    # Calculate metrics
    if not trades:
        return {'return_pct': 0, 'trades': 0, 'win_rate': 0, 'pf': 0, 'max_dd': 0, 'final_capital': initial_capital}
    
    total_pnl = sum(t['pnl'] for t in trades)
    final_capital = initial_capital + total_pnl
    return_pct = (total_pnl / initial_capital) * 100
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = (len(wins) / len(trades)) * 100 if trades else 0
    
    gross_win = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 1
    pf = gross_win / gross_loss if gross_loss > 0 else 0
    
    peak = initial_capital
    max_dd = 0
    running = initial_capital
    for t in trades:
        running += t['pnl']
        if running > peak:
            peak = running
        dd = (peak - running) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    return {
        'return_pct': return_pct,
        'final_capital': final_capital,
        'win_rate': win_rate,
        'trades': len(trades),
        'pf': pf,
        'max_dd': max_dd * 100,
        'trade_log': trades
    }

from flask import Flask, render_template, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from fpdf import FPDF
import pandas as pd
import requests
import os
import threading
from datetime import datetime, timedelta
import pytz
import json

# Resolve paths relative to this file (src/api/server.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up two levels to root, then into frontend/dist
STATIC_DIR = os.path.join(BASE_DIR, '../../frontend/dist')
TEMPLATE_DIR = os.path.join(BASE_DIR, '../../templates')

print(f" [DEBUG] Server starting...")
print(f" [DEBUG] BASE_DIR: {BASE_DIR}")
print(f" [DEBUG] STATIC_DIR: {os.path.abspath(STATIC_DIR)}")
print(f" [DEBUG] STATIC_DIR Exists? {os.path.exists(STATIC_DIR)}")
if os.path.exists(STATIC_DIR):
    print(f" [DEBUG] Files in STATIC_DIR: {os.listdir(STATIC_DIR)}")

# Configure Flask to serve React build
app = Flask(__name__, 
            template_folder=TEMPLATE_DIR, 
            static_folder=STATIC_DIR,
            static_url_path='')
CORS(app) # Enable CORS for all routes
engine_ref = None

# Lazy-initialized integrations (deferred to avoid blocking Gunicorn startup)
db_handler = None
_db_initialized = False
brain = None
_brain_initialized = False
BRAIN_AVAILABLE = False

def _get_db():
    global db_handler, _db_initialized
    if not _db_initialized:
        _db_initialized = True
        try:
            from src.db.mongodb_handler import get_db_handler
            db_handler = get_db_handler()
            print("[LAZY] MongoDB handler initialized", flush=True)
        except Exception as e:
            print(f"[LAZY] MongoDB init failed: {e}", flush=True)
            db_handler = None
    return db_handler

def _get_brain():
    global brain, _brain_initialized, BRAIN_AVAILABLE
    if not _brain_initialized:
        _brain_initialized = True
        try:
            from src.brain.learning_engine import get_brain
            brain = get_brain()
            BRAIN_AVAILABLE = True
            print("[LAZY] Brain engine initialized", flush=True)
        except Exception as e:
            print(f"[LAZY] Brain init skipped: {e}", flush=True)
            brain = None
            BRAIN_AVAILABLE = False
    return brain

import traceback

def init_app(engine_instance):
    global engine_ref
    engine_ref = engine_instance

# Helper to access engine safely
def get_engine():
    """Returns engine if ready, None otherwise"""
    return engine_ref


# Health check endpoint (must respond instantly for Render)
@app.route('/healthz')
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route('/api/stats')
def get_stats():
    engine = get_engine()
    if engine is None:
        return jsonify({
            'status': 'initializing',
            'total_capital': 0,
            'total_pnl_pct': 0,
            'equity_curve': [],
            'recent_trades': [],
            'strategies': [],
            'running': False
        })
    mode = request.args.get('mode', 'PAPER').upper()
    return jsonify(engine.get_portfolio_stats(mode=mode))

@app.route('/api/brain')
def get_brain_data():
    try:
        b = _get_brain()
        if b:
            return jsonify(b.get_insights())
        return jsonify({"status": "inactive", "message": "Brain not loaded yet"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/balance')
def get_balance():
    try:
        engine = get_engine()
        mode = request.args.get('mode', 'PAPER').upper()
        
        if mode == 'REAL':
            if not engine.broker.connected:
                engine.broker.connect()
            balance = engine.broker.get_real_balance()
        else:
            balance = engine.broker.get_account_balance()
            
        return jsonify({'status': 'success', 'balance': balance})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/history')
def get_history():
    engine = get_engine()
    db = _get_db()
    if db and db.connected:
        try:
            all_trades = db.get_recent_trades(limit=100)
            exit_trades = [t for t in all_trades if t.get('action') == 'EXIT' or t.get('pnl') is not None]
            return jsonify(exit_trades[:500])
        except: pass
    
    all_trades = []
    stats = engine.get_portfolio_stats()
    for s in stats['strategies']:
        for t in s['trades']:
            if t.get('pnl') is not None:
                all_trades.append({**t, 'strategy': s['name']})
    all_trades.sort(key=lambda x: x.get('exit_time', ''), reverse=True)
    return jsonify(all_trades[:500])

@app.route('/api/refresh')
def refresh_data():
    engine = get_engine()
    if engine.fetch_data():
        engine.run_strategies()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'})

@app.route('/api/save_token', methods=['POST'])
def save_token():
    engine = get_engine()
    data = request.json
    token = data.get('token')
    
    if token:
        try:
            with open('.fyers_token', 'w') as f:
                f.write(token)
            
            db = _get_db()
            if db and db.connected:
                try:
                    db.db["system_config"].update_one(
                        {"_id": "fyers_session"},
                        {"$set": {"access_token": token}},
                        upsert=True
                    )
                except: pass
            
            if engine.validate_token(token):
                engine.running = True
                if not any(t.name == 'trading_loop' for t in threading.enumerate()):
                    thread = threading.Thread(target=engine.run, daemon=True, name='trading_loop')
                    thread.start()
                return jsonify({'status': 'success', 'message': 'Token saved & Bot started!'})
            else:
                return jsonify({'status': 'error', 'message': 'Invalid token or connection failed'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
            
    return jsonify({'status': 'error', 'message': 'No token provided'})

@app.route('/api/test_telegram')
def test_telegram():
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": " Telegram Connection Verified!"}, timeout=5)
        return jsonify({"status": "success", "message": "Telegram ping sent"})
    return jsonify({"status": "error", "message": "Credentials missing"})

@app.route('/api/brain/insights')
def get_brain_insights():
    b = _get_brain()
    if b:
        try:
            insights = b.get_insights()
            return jsonify({'status': 'active', 'available': True, **insights})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e), 'available': False})
    return jsonify({'status': 'inactive', 'available': False, 'message': 'Brain module not loaded'})

@app.route('/api/brain/reset_cooling', methods=['POST'])
def reset_brain_cooling():
    b = _get_brain()
    if b:
        try:
            b.cooling_off_until = None
            b.save_state()
            return jsonify({'status': 'success', 'message': 'Cooling-off period reset'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Brain not available'})

@app.route('/debug')
def debug_app():
    return " Bot Core is Active"

@app.route('/api/start')
def start_trading():
    engine = get_engine()
    if engine is None:
        return jsonify({'status': 'initializing', 'message': 'Engine starting...'}), 503
        
    if not engine.running:
        engine.running = True
        engine.save_state()
        if not any(t.name == 'trading_loop' for t in threading.enumerate()):
            thread = threading.Thread(target=engine.run, daemon=True, name='trading_loop')
            thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/stop')
def stop_trading():
    engine = get_engine()
    if engine is None:
        return jsonify({'status': 'initializing', 'message': 'Engine starting...'}), 503
        
    print(f" STOP REQUESTED", flush=True)
    engine.running = False
    engine.save_state()
    return jsonify({'status': 'stopped'})

@app.route('/api/force_close')
def force_close():
    engine = get_engine()
    if engine is None:
         return jsonify({'status': 'initializing', 'message': 'Engine starting...'}), 503
         
    engine.running = False
    engine.emergency_close_all()
    return jsonify({'status': 'emergency_stop_triggered', 'message': 'All positions closed.'})

@app.route('/api/reset_hard')
def reset_hard():
    try:
        engine = get_engine()
        if engine:
            engine.reset_portfolio_state()
            return jsonify({'status': 'success', 'message': 'Portfolio Hard Reset Successful'})
        return jsonify({'status': 'initializing', 'message': 'Engine starting...'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/strategy/<path:strategy_name>')
def strategy_detail(strategy_name):
    engine = get_engine()
    if engine is None: return "Engine Initializing...", 503
    
    decoded_name = requests.utils.unquote(strategy_name)
    strategy = next((s for s in engine.strategies if s.name == decoded_name), None)
    if not strategy: return "Strategy not found", 404
    return render_template('strategy_detail.html', strategy=strategy)

@app.route('/api/strategy/<strategy_name>')
def get_strategy_details(strategy_name):
    engine = get_engine()
    if engine is None:
        return jsonify({'error': 'Engine Initializing'}), 503
        
    decoded_name = requests.utils.unquote(strategy_name)
    strategy = next((s for s in engine.strategies if s.name == decoded_name), None)
    if not strategy: return jsonify({'error': 'Strategy not found'}), 404
    
    trades_for_display = []
    equity_curve = []
    cumulative_pnl = 0
    equity_curve.append({'time': (datetime.now() - timedelta(days=30)).isoformat(), 'value': 0})
    
    exit_trades = [t for t in strategy.trades if t.get('pnl') is not None or t.get('action') == 'EXIT']
    def get_trade_time(t): return t.get('exit_time') or t.get('timestamp') or t.get('entry_time') or ''
    sorted_trades = sorted(exit_trades, key=get_trade_time)
    
    for t in sorted_trades:
        pnl = t.get('pnl', 0) or 0
        cumulative_pnl += pnl
        equity_curve.append({'time': get_trade_time(t), 'value': round(cumulative_pnl, 2)})
        trades_for_display.append({
            'side': t.get('side', 'buy'),
            'entry': t.get('entry') or t.get('entry_price') or t.get('price', 0),
            'exit': t.get('exit') or t.get('exit_price') or 0,
            'pnl': pnl,
            'exit_time': get_trade_time(t),
            'entry_time': t.get('entry_time') or t.get('timestamp') or ''
        })
        
    if len(equity_curve) == 1:
        equity_curve.append({'time': datetime.now().isoformat(), 'value': equity_curve[0]['value']})
        
    total_days_active = 1
    if sorted_trades:
        try:
            first_time = get_trade_time(sorted_trades[0])
            last_time = get_trade_time(sorted_trades[-1])
            if first_time and last_time:
                first_trade = datetime.fromisoformat(first_time.replace('+05:30', ''))
                last_trade = datetime.fromisoformat(last_time.replace('+05:30', ''))
                total_days_active = max(1, (last_trade - first_trade).days)
        except: pass
        
    daily_avg_pnl = cumulative_pnl / total_days_active
    projected_6mo = daily_avg_pnl * 20 * 6
    
    return jsonify({
        'name': strategy.name,
        'stats': strategy.get_stats(),
        'equity_curve': equity_curve,
        'trades': trades_for_display[::-1],
        'projections': {
            'daily_avg': round(daily_avg_pnl, 2),
            'monthly_projected': round(daily_avg_pnl * 20, 2),
            'six_month_projected': round(projected_6mo, 2)
        }
    })

@app.route('/api/regime', methods=['GET'])
def get_regime():
    engine = get_engine()
    if engine and hasattr(engine, 'governor'):
        return jsonify(engine.governor.get_regime_status())
    return jsonify({'status': 'initializing'}), 503

@app.route('/api/regime/update', methods=['POST'])
def update_regime_manual():
    engine = get_engine()
    if engine is None: return jsonify({'error': 'Engine starting...'}), 503
    
    data = request.json
    mode = data.get('mode')
    regime = data.get('regime')
    if mode == 'MANUAL':
        engine.governor.set_manual_mode(True, regime)
    else:
        engine.governor.set_manual_mode(False)
        engine.governor.update_regime()
    return jsonify({"message": "Regime updated", "status": engine.governor.get_regime_status()})

@app.route('/api/strategy/allocation', methods=['POST'])
def strategy_allocation():
    engine = get_engine()
    if engine is None: return jsonify({'error': 'Engine starting...'}), 503
    
    data = request.json
    strategy_name = data.get('strategy')
    new_capital = data.get('capital')
    
    if strategy_name and new_capital is not None:
        strategy = next((s for s in engine.strategies if s.name == strategy_name), None)
        if strategy:
            try:
                val = float(new_capital)
                strategy.capital = val
                strategy.initial_capital = val
                strategy.daily_start_capital = val
                engine.save_state()
                return jsonify({"message": f"Strategy {strategy_name} capital set to {val}"})
            except ValueError:
                return jsonify({"error": "Invalid capital value"}), 400
        return jsonify({"error": "Strategy not found"}), 404
    return jsonify({"error": "Invalid parameters"}), 400

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    engine = get_engine()
    if request.method == 'GET':
        settings = {"auto_login": True, "notifications": True, "max_risk": 5}
        db = _get_db()
        if db and db.connected:
            try:
                db_config = db.db["system_config"].find_one({"_id": "user_settings"})
                if db_config: settings.update(db_config.get('settings', {}))
            except Exception as e: print(f"Error loading settings: {e}")
        return jsonify(settings)
    elif request.method == 'POST':
        data = request.json
        db = _get_db()
        if db and db.connected:
            try:
                db.db["system_config"].update_one(
                    {"_id": "user_settings"},
                    {"$set": {"settings": data, "updated_at": datetime.utcnow().isoformat()}},
                    upsert=True
                )
                if 'max_risk' in data:
                    new_risk = float(data['max_risk'])
                    for strat in engine.strategies:
                        if hasattr(strat, 'risk_pct'): strat.risk_pct = new_risk / 100.0
                return jsonify({'status': 'success', 'message': 'Settings saved & applied'})
            except Exception as e: return jsonify({'status': 'error', 'message': str(e)}), 500
        else:
            if 'max_risk' in data:
                new_risk = float(data['max_risk'])
                for strat in engine.strategies:
                    if hasattr(strat, 'risk_pct'): strat.risk_pct = new_risk / 100.0
            return jsonify({'status': 'warning', 'message': 'Saved locally (applied to current session)'})
@app.route('/api/report/generate', methods=['POST'])
def generate_report():
    data = request.json
    strategy_name = data.get('strategy', 'Portfolio')
    
    # Simple PDF generation
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Strategy Report: {strategy_name}", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
    pdf.cell(200, 10, txt=f"Total Profit: {data.get('total_pnl', 'N/A')}", ln=True)
    pdf.cell(200, 10, txt=f"Win Rate: {data.get('win_rate', 'N/A')}", ln=True)
    
    report_path = f"reports/report_{strategy_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    os.makedirs("reports", exist_ok=True)
    pdf.output(report_path)
    
    return send_file(report_path, as_attachment=True)

@app.route('/api/strategy/toggle', methods=['POST'])
def toggle_strategy():
    engine = get_engine()
    if engine is None: return jsonify({'error': 'Engine starting...'}), 503
    
    data = request.json
    strategy_name = data.get('strategy')
    
    if strategy_name:
        strategy = next((s for s in engine.strategies if s.name == strategy_name), None)
        if strategy:
            # Toggle logic
            new_state = not getattr(strategy, 'paused', False)
            strategy.paused = new_state
            
            # Update overrides
            engine.strategy_overrides[strategy.name] = 'PAUSED' if new_state else 'ACTIVE'
            engine.save_state()
            
            return jsonify({
                "status": "success", 
                "message": f"Strategy {strategy_name} {'paused' if new_state else 'resumed'}",
                "paused": new_state
            })
        return jsonify({"error": "Strategy not found"}), 404
    return jsonify({"error": "Invalid parameters"}), 400

# Catch-all route for React Router (must be last)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    """Serve React app for all non-API routes"""
    if path.startswith('api/'):
        return jsonify({"error": "API endpoint not found"}), 404
    # Check if frontend build exists
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, 'index.html')
    else:
        return jsonify({
            "error": "Frontend not built",
            "static_folder": app.static_folder,
            "index_exists": False,
            "hint": "Run 'cd frontend && npm install && npm run build' first"
        }), 500

if __name__ == '__main__':
    # For testing purposes only
    app.run(port=8080)

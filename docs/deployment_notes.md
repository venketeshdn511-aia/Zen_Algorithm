# Deployment Notes — Kotak Algo Bot

## Known Limitations & Workarounds

### 1. Gunicorn Signal Handling (BUG-17)

**Issue**: The custom signal handlers in `main.py` (lines 78-79) may not work correctly when running under Gunicorn.

```python
# main.py
signal.signal(signal.SIGINT, lambda s, f: engine.emergency_close_all())
signal.signal(signal.SIGTERM, lambda s, f: engine.emergency_close_all())
```

**Why**: Gunicorn has its own signal handling for worker process management. When Gunicorn receives SIGTERM, it may terminate workers before the custom handler executes.

**Impact**: The `emergency_close_all()` function may not fire on shutdown, potentially leaving open positions.

**Workarounds**:
1. **Use Gunicorn hooks** instead of signal handlers:
   ```python
   # gunicorn.conf.py
   def on_exit(server):
       # Called when Gunicorn is shutting down
       if hasattr(server, 'engine'):
           server.engine.emergency_close_all()
   ```

2. **Manual shutdown**: Before redeploying on Render, use the `/api/shutdown` endpoint to gracefully close positions.

3. **Monitor positions**: Set up external monitoring to detect and close orphaned positions.

---

### 2. MongoDB Handler Thread Safety (BUG-18)

**Issue**: The `db_handler` is a module-level singleton imported by both `trading_engine.py` and `base_strategy.py`.

```python
# Both files do this at module level:
from src.db.mongodb_handler import get_db_handler
db_handler = get_db_handler()
```

**Why**: Under concurrent imports (e.g., Gunicorn pre-loading), multiple threads might call `get_db_handler()` simultaneously, potentially creating race conditions.

**Impact**: Low risk in practice because:
- Connection is lazy (deferred to first operation)
- MongoDB client is thread-safe once created
- Most operations happen in the main trading loop (single-threaded)

**Best Practices**:
1. **Pre-load in main thread**: Ensure `db_handler` is initialized before Gunicorn workers start
2. **Use Gunicorn's `--preload` flag**: This loads the app in the main process before forking workers
3. **Monitor connection logs**: Watch for duplicate "Connected to MongoDB" messages

---

### 3. Render Deployment Checklist

**Environment Variables Required**:
```yaml
# Database
MONGODB_URI=mongodb+srv://...

# Kotak Neo API
KOTAK_CONSUMER_KEY=...
KOTAK_CONSUMER_SECRET=...
KOTAK_ACCESS_TOKEN=...
KOTAK_MOBILE_NUMBER=...
KOTAK_PASSWORD=...
KOTAK_MPIN=...
KOTAK_TOTP_SECRET=...
KOTAK_UCC=...

# Telegram Notifications
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Optional
PORT=5000
ALLOW_AFTER_MARKET=false
```

**Startup Sequence**:
1. Flask app binds to port (immediate)
2. TradingEngine initializes in background thread (10-30s)
3. Broker authentication (depends on Kotak API response time)
4. Strategies load and start processing

**Health Check**:
- Render pings `/` every 30s
- Engine may not be ready for first 30-60s
- API routes have null-safety checks for `engine is None`

---

### 4. Debugging Silent Failures

**Common Issues**:

| Symptom | Likely Cause | Check |
|---------|--------------|-------|
| No trades in dashboard | Strategy NameError or broker.fyers call | Check logs for exceptions |
| Positions never exit | broker.get_current_price() failing | Verify option symbol format |
| State lost on redeploy | MONGODB_URI not set | Check env vars in Render dashboard |
| Telegram not working | Missing TELEGRAM_* vars | Verify bot token and chat ID |

**Debugging Steps**:
1. Check Render logs for startup errors
2. Use `/api/debug` endpoint to see engine status
3. Verify all env vars are set in Render dashboard
4. Test broker connection with `/api/balance`

---

### 5. Performance Considerations

**Rate Limits**:
- Kotak Neo API: ~3 requests/second
- MongoDB Atlas: 100 connections (M0 free tier)
- Render free tier: 750 hours/month

**Optimization**:
- `update_live_positions()` runs every loop iteration
- WebSocket for real-time data (reduces REST calls)
- VWAP now calculates per-day (more efficient than cumulative)

---

## Deployment Workflow

### Initial Deploy
```bash
# 1. Push to GitHub
git add .
git commit -m "Deploy to Render"
git push origin main

# 2. Render auto-deploys from main branch
# 3. Wait 2-3 minutes for build + startup
# 4. Check logs for "TradingEngine initialized"
```

### Updating Strategies
```bash
# 1. Test locally first
python main.py

# 2. Push changes
git push origin main

# 3. Render redeploys automatically
# 4. Positions are saved to MongoDB (persist across deploys)
```

### Emergency Shutdown
```bash
# Option 1: API endpoint
curl -X POST https://your-app.onrender.com/api/shutdown

# Option 2: Render dashboard
# Click "Suspend" to stop the service

# Option 3: Manual
# SSH into Render shell and kill process
```

---

## Monitoring Checklist

- [ ] Check `/api/balance` shows connected broker
- [ ] Verify `/api/strategies` lists all strategies
- [ ] Confirm `/api/history` shows trade records
- [ ] Test Telegram notifications are working
- [ ] Monitor Render logs for errors
- [ ] Verify MongoDB connection in logs

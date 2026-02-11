"""
Real-time alert system for Telegram notifications.

Sends instant alerts for:
- Trade entries/exits
- Stop-loss hits
- Circuit breaker triggers
- Daily P&L summaries
"""

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from typing import Optional
from datetime import datetime


class TelegramAlerts:
    """
    Telegram bot integration for real-time alerts.
    """
    
    def __init__(self, bot_token: str, chat_id: str, logger=None):
        """
        Initialize Telegram alerts.
        
        Args:
            bot_token: Telegram bot token (from @BotFather)
            chat_id: Your Telegram chat ID
            logger: Optional logger
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.logger = logger
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # Alert preferences
        self.enabled = bool(bot_token and chat_id)
        self.rate_limit_seconds = 2  # Min time between messages
        self.last_alert_time = None

        # Setup persistent session with retries
        self._setup_session()

    def _setup_session(self):
        """Configure requests session with retry logic."""
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def send_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """
        Send message to Telegram.
        
        Args:
            message: Message text (supports Markdown)
            parse_mode: 'Markdown' or 'HTML'
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        # Rate limiting
        if self.last_alert_time:
            elapsed = (datetime.now() - self.last_alert_time).total_seconds()
            if elapsed < self.rate_limit_seconds:
                if self.logger:
                    self.logger.debug(f"Alert rate-limited ({elapsed:.1f}s since last)")
                return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = self.session.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                self.last_alert_time = datetime.now()
                return True
                
            # Retry logic for Markdown framing errors (400)
            elif response.status_code == 400 and parse_mode:
                if self.logger:
                    self.logger.warning(f"Markdown parse failed, retrying as plain text. Error: {response.text}")
                
                # Retry without parse_mode
                payload.pop('parse_mode', None)
                response = self.session.post(url, json=payload, timeout=10)
                
                if response.status_code == 200:
                    self.last_alert_time = datetime.now()
                    return True
                else:
                    if self.logger:
                        self.logger.error(f"Telegram retry failed: {response.status_code} - {response.text}")
                    return False
            else:
                if self.logger:
                    self.logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to send Telegram alert: {e}")
            return False
    
    def alert_trade_entry(self, symbol: str, side: str, qty: int, price: float, stop: float):
        """Alert on trade entry."""
        message = (
            f" *ENTRY*\n"
            f"Symbol: `{symbol}`\n"
            f"Side: *{side.upper()}*\n"
            f"Qty: {qty}\n"
            f"Price: {price:.2f}\n"
            f"Stop: {stop:.2f}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_trade_exit(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        pnl: float,
        reason: str
    ):
        """Alert on trade exit."""
        emoji = "" if pnl > 0 else ""
        message = (
            f"{emoji} *EXIT*\n"
            f"Symbol: `{symbol}`\n"
            f"Side: *{side.upper()}*\n"
            f"Qty: {qty}\n"
            f"Price: {price:.2f}\n"
            f"P&L: {pnl:+.2f}\n"
            f"Reason: {reason}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_stop_hit(self, symbol: str, stop_type: str, price: float, loss: float):
        """Alert on stop-loss hit."""
        message = (
            f" *STOP HIT*\n"
            f"Symbol: `{symbol}`\n"
            f"Type: {stop_type}\n"
            f"Price: {price:.2f}\n"
            f"Loss: {loss:.2f}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_partial_tp(self, symbol: str, tp_level: str, qty: int, price: float, pnl: float):
        """Alert on partial take-profit."""
        message = (
            f" *PARTIAL TP*\n"
            f"Symbol: `{symbol}`\n"
            f"Level: {tp_level}\n"
            f"Qty: {qty}\n"
            f"Price: {price:.2f}\n"
            f"P&L: {pnl:+.2f}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_circuit_breaker(self, level: str, action: str, dd_pct: float):
        """Alert on circuit breaker trigger."""
        message = (
            f" *CIRCUIT BREAKER*\n"
            f"Level: {level}\n"
            f"Action: *{action}*\n"
            f"Drawdown: {dd_pct*100:.2f}%\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_anomaly(self, anomaly_type: str, details: str):
        """Alert on anomaly detection."""
        message = (
            f" *ANOMALY DETECTED*\n"
            f"Type: {anomaly_type}\n"
            f"Details: {details}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_daily_summary(
        self,
        total_pnl: float,
        win_rate: float,
        trades_count: int,
        balance: float
    ):
        """Send daily P&L summary."""
        emoji = "" if total_pnl > 0 else ""
        message = (
            f"{emoji} *DAILY SUMMARY*\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"\n"
            f"P&L: {total_pnl:+.2f}\n"
            f"Trades: {trades_count}\n"
            f"Win Rate: {win_rate*100:.1f}%\n"
            f"Balance: {balance:,.2f}"
        )
        return self.send_message(message)
    
    def alert_eod_force_close(self, positions_closed: int):
        """Alert on EOD force-close."""
        message = (
            f" *EOD FORCE CLOSE*\n"
            f"Closed {positions_closed} position(s)\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_system_start(self, strategy: str, symbols: list):
        """Alert when bot starts."""
        message = (
            f" *BOT STARTED*\n"
            f"Strategy: {strategy}\n"
            f"Symbols: {', '.join(symbols[:5])}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def alert_system_stop(self, reason: str):
        """Alert when bot stops."""
        message = (
            f" *BOT STOPPED*\n"
            f"Reason: {reason}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        return self.send_message(message)
    
    def test_connection(self) -> bool:
        """Test Telegram connection."""
        if not self.enabled:
            if self.logger:
                self.logger.warning("Telegram alerts not enabled (missing token/chat_id)")
            return False
        
        success = self.send_message(" Telegram alerts connected successfully!")
        
        if success and self.logger:
            self.logger.info(" Telegram connection test passed")
        elif not success and self.logger:
            self.logger.error(" Telegram connection test failed")
        
        return success

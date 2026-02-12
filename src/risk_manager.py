import alpaca_trade_api as tradeapi

class RiskManager:
    def __init__(self, api: tradeapi.REST, logger=None):
        self.api = api
        self.logger = logger
        self.max_daily_loss = 500  # $500 max loss per day
        self.starting_balance = 0
        
        # Capture starting balance on init
        try:
            account = self.api.get_account()
            self.starting_balance = float(account.equity)
        except Exception as e:
            print(f" [RISK] Could not get starting balance: {e}")

    def check_pnl_stops(self):
        """Checks daily PnL violations. Returns False if trading should stop."""
        try:
            account = self.api.get_account()
            current_equity = float(account.equity)
            pnl = current_equity - self.starting_balance
            
            if pnl < -self.max_daily_loss:
                msg = f"CRITICAL: Max Daily Loss Exceeded (PnL: ${pnl:.2f}). Stopping Bot."
                if self.logger: self.logger.error(msg)
                else: print(msg)
                
                self.liquidate_all_positions()
                return False
        except Exception as e:
            if self.logger: self.logger.error(f"Error checking PnL: {e}")
            
        return True

    def liquidate_all_positions(self):
        """Closes all open positions immediately."""
        try:
            self.api.close_all_positions()
            msg = "All positions liquidated."
            if self.logger: self.logger.warning(msg)
            else: print(msg)
        except Exception as e:
            error_msg = f"Failed to liquidate positions: {e}"
            if self.logger: self.logger.error(error_msg)
            else: print(error_msg)

    def can_trade(self):
        """Checks if account triggers any risk limits."""
        # 1. Check PnL First
        if not self.check_pnl_stops():
            return False

        account = self.api.get_account()
        if account.trading_blocked:
            if self.logger: self.logger.warning("Trading is blocked.")
            return False
            
        # Example check: Ensure buying power is positive
        buying_power = float(account.buying_power)
        if buying_power <= 0:
            if self.logger: self.logger.warning(f"Insufficient buying power: ${buying_power}")
            return False
            
        return True

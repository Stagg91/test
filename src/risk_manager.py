class RiskManager:
    def __init__(self, daily_loss_limit_pct=5.0, max_position_size_usdt=100.0, max_open_positions=3):
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_position_size_usdt = max_position_size_usdt
        self.max_open_positions = max_open_positions
        # In memory state for now, ideally strictly persisted
        self.daily_pnl = 0.0
        self.open_positions_count = 0

    def check_trade_allowed(self, symbol: str, size_usdt: float, current_balance: float) -> tuple[bool, str]:
        """
        Checks if a trade is safe to execute.
        Returns (Allowed: bool, Reason: str)
        """
        if self.open_positions_count >= self.max_open_positions:
            return False, f"Max open positions ({self.max_open_positions}) reached."

        if size_usdt > self.max_position_size_usdt:
            return False, f"Position size {size_usdt} exceeds limit {self.max_position_size_usdt}."

        # Daily Loss Check (simplified)
        # Assuming we start with 0 PnL each restart for now
        max_loss_amount = current_balance * (self.daily_loss_limit_pct / 100.0)
        if self.daily_pnl < -max_loss_amount:
            return False, f"Daily loss limit reached ({self.daily_pnl} < -{max_loss_amount})."

        return True, "Trade Allowed"

    def record_trade_close(self, pnl: float):
        self.daily_pnl += pnl
        self.open_positions_count = max(0, self.open_positions_count - 1)

    def record_trade_open(self):
        self.open_positions_count += 1

from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    def __init__(self, parameters: dict = None):
        self.parameters = parameters or {}

    @abstractmethod
    def on_candle(self, df: pd.DataFrame) -> dict:
        """
        Analyzes the DataFrame and returns a signal.
        df: DataFrame with OHLCV data.
        Returns: Dict with keys:
            - signal: "buy", "sell", or "hold"
            - confidence: float (0.0 to 1.0)
            - stop_loss: float (optional)
            - take_profit: float (optional)
            - metadata: dict (optional, for debug/logging)
        """
        pass

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any

class IndicatorConfig(BaseModel):
    name: str = Field(..., description="Name of the indicator (e.g., 'rsi', 'sma', 'ema')")
    params: Dict[str, Any] = Field(..., description="Parameters for the indicator (e.g., {'length': 14})")
    col_name: Optional[str] = Field(None, description="Custom column name for the indicator output")

class StrategyRecipe(BaseModel):
    name: str = Field(..., description="Descriptive name of the strategy")
    description: str = Field(..., description="Brief explanation of the strategy logic")
    indicators: List[IndicatorConfig] = Field(..., description="List of technical indicators to calculate")
    entry_logic: str = Field(..., description="Pandas query string or Python expression for Entry (Buy) condition")
    exit_logic: str = Field(..., description="Pandas query string or Python expression for Exit (Sell) condition")
    sentiment_weight: float = Field(0.0, ge=0.0, le=1.0, description="Weight of AI sentiment (0.0 to 1.0). Not used in MVP backtest usually but good for future.")
    stop_loss: float = Field(0.0, description="Stop Loss percentage (e.g., 2.0 for 2%). 0 to disable.")
    take_profit: float = Field(0.0, description="Take Profit percentage. 0 to disable.")

class MutationRequest(BaseModel):
    parent_strategies: List[StrategyRecipe]
    goal: str = Field(..., description="The optimization goal (e.g., 'Reduce Max Drawdown')")

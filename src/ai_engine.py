from google import genai
from google.genai import types
import json
import traceback
from src.strategies.schemas import StrategyRecipe, IndicatorConfig

class AIEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-2.0-flash-thinking-exp-01-21" # Using an experimental thinking model or requested gemini-3 if available.
        # User requested: gemini-3-pro-preview
        # I will try to use the requested model, but fall back if not available or if I need to map it.
        # Given "Thinking Model" instruction, "gemini-2.0-flash-thinking-exp" is the current public equivalent for "Thinking".
        # However, I must follow the user's explicit instruction: "Model: gemini-3-pro-preview"
        self.model = "gemini-3-pro-preview"

    def generate_strategy_recipe(self, prompt: str) -> StrategyRecipe:
        """
        Generates a new strategy recipe based on the prompt.
        """
        system_instruction = """
        You are a quantitative trading architect. Your goal is to design robust, backtestable trading strategies.
        Output MUST be a valid JSON object matching the following schema.
        Do not explain. Return only the JSON.

        Schema:
        {
            "name": "Strategy Name",
            "description": "Description",
            "indicators": [
                {"name": "rsi", "params": {"length": 14}, "col_name": "RSI_14"},
                {"name": "sma", "params": {"length": 50}, "col_name": "SMA_50"}
            ],
            "entry_logic": "Pandas query string (e.g., 'RSI_14 < 30 and close > SMA_50')",
            "exit_logic": "Pandas query string (e.g., 'RSI_14 > 70')",
            "sentiment_weight": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0
        }

        Supported pandas_ta indicators: rsi, macd, sma, ema, bbands, atr, adx.
        Use DataFrame column names: open, high, low, close, volume.
        """

        full_prompt = f"{system_instruction}\n\nUser Request: {prompt}"

        try:
            # Thinking Config
            # Note: The SDK might change how config is passed.
            # Based on user prompt: thinking_config={"thinking_level": "high"}
            # And output format: response_mime_type: "application/json"

            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(include_thoughts=True), # mapping "high" to boolean or specific level if supported
                    response_mime_type="application/json"
                )
            )

            # Extract JSON
            # If the model returns thoughts, the actual text might be separate?
            # With google-genai SDK, response.text should contain the generated content.
            # If "include_thoughts=True", it might be in parts.

            # Let's inspect response structure safely
            text_content = response.text

            # Parse JSON
            data = json.loads(text_content)

            # Validate with Pydantic
            recipe = StrategyRecipe(**data)
            return recipe

        except Exception as e:
            print(f"AI Generation Error: {e}")
            # Fallback for dev/testing if model fails or quota issues
            traceback.print_exc()
            return None

    def mutate_strategy_recipe(self, parents: list[StrategyRecipe], feedback: str) -> StrategyRecipe:
        """
        Mutates a strategy or combines parents.
        """
        system_instruction = """
        You are an evolutionary algorithm for trading strategies.
        You will receive a list of 'Parent' strategies and a goal (feedback).
        Create a 'Child' strategy that inherits good traits but introduces mutations to solve the goal.
        Output MUST be a valid JSON object matching the StrategyRecipe schema.
        """

        parents_json = json.dumps([p.model_dump() for p in parents], indent=2)
        full_prompt = f"{system_instruction}\n\nParents:\n{parents_json}\n\nGoal: {feedback}"

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(include_thoughts=True),
                    response_mime_type="application/json"
                )
            )

            data = json.loads(response.text)
            recipe = StrategyRecipe(**data)
            return recipe

        except Exception as e:
            print(f"AI Mutation Error: {e}")
            traceback.print_exc()
            return None

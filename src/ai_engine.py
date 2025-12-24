from google import genai
from google.genai import types
import json
import traceback
from src.strategies.schemas import StrategyRecipe, IndicatorConfig
from src.logger import LabLogger

class AIEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-3-pro-preview"

    async def generate_strategy_recipe(self, prompt: str) -> StrategyRecipe:
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

        await LabLogger.log("AI", f"Requesting Generation: {prompt}")
        print("\n--- AI REQUEST (GENERATE) ---")
        print(full_prompt)
        print("-----------------------------\n")

        try:
            # Note: generate_content is sync. We can wrap it or just block briefly.
            # For true async, we'd need run_in_executor, but this is fine for now as it's a background thread.
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(include_thoughts=True),
                    response_mime_type="application/json"
                )
            )

            text_content = response.text
            await LabLogger.log("AI", f"Response received ({len(text_content)} chars)")
            print("\n--- AI RESPONSE ---")
            print(text_content)
            print("-------------------\n")

            data = json.loads(text_content)
            recipe = StrategyRecipe(**data)
            return recipe

        except Exception as e:
            err_msg = str(e)
            print(f"\n[AI ERROR] {err_msg}")
            await LabLogger.log("AI", f"Error: {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("!!! GEMINI QUOTA EXCEEDED !!!")
                await LabLogger.log("AI", "!!! GEMINI QUOTA EXCEEDED !!!")
            traceback.print_exc()
            return None

    async def mutate_strategy_recipe(self, parents: list[StrategyRecipe], feedback: str) -> StrategyRecipe:
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

        await LabLogger.log("AI", f"Requesting Mutation. Goal: {feedback}")
        print("\n--- AI REQUEST (MUTATE) ---")
        print(full_prompt)
        print("---------------------------\n")

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(include_thoughts=True),
                    response_mime_type="application/json"
                )
            )

            text_content = response.text
            await LabLogger.log("AI", f"Response received ({len(text_content)} chars)")
            print("\n--- AI RESPONSE ---")
            print(text_content)
            print("-------------------\n")

            data = json.loads(text_content)
            recipe = StrategyRecipe(**data)
            return recipe

        except Exception as e:
            err_msg = str(e)
            print(f"\n[AI ERROR] {err_msg}")
            await LabLogger.log("AI", f"Error: {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("!!! GEMINI QUOTA EXCEEDED !!!")
                await LabLogger.log("AI", "!!! GEMINI QUOTA EXCEEDED !!!")
            traceback.print_exc()
            return None

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

    async def generate_strategy_recipe(self, prompt: str, allowed_indicators: list = None) -> StrategyRecipe:
        """
        Generates a new strategy recipe based on the prompt.
        """
        ind_context = "Supported pandas_ta indicators: rsi, macd, sma, ema, bbands, atr, adx."
        if allowed_indicators:
             from src.database import SessionLocal, Indicator
             db = SessionLocal()
             inds = db.query(Indicator).filter(Indicator.name.in_(allowed_indicators)).all()
             db.close()

             ind_context = "Available Indicators (You MUST use one or more of these):\n"
             for ind in inds:
                 params = ind.params_json or {}
                 ind_context += f"- Name: {ind.name}\n  Description: {ind.description}\n  Parameters: {params}\n"

        system_instruction = f"""
        You are a quantitative trading architect. Your goal is to design robust, backtestable trading strategies.
        Output MUST be a valid JSON object matching the following schema.
        Do not explain. Return only the JSON.

        Schema:
        {{
            "name": "Strategy Name",
            "description": "Description",
            "indicators": [
                {{"name": "rsi", "params": {{"length": 14}}, "col_name": "RSI_14"}},
                {{"name": "sma", "params": {{"length": 50}}, "col_name": "SMA_50"}}
            ],
            "entry_logic": "Pandas query string (e.g., 'RSI_14 < 30 and close > SMA_50')",
            "exit_logic": "Pandas query string (e.g., 'RSI_14 > 70')",
            "sentiment_weight": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0
        }}

        {ind_context}
        Use DataFrame column names: open, high, low, close, volume.
        """

        full_prompt = f"{system_instruction}\n\nUser Request: {prompt}"

        await LabLogger.log("AI", f"Sending Request to Gemini...", {"prompt": prompt})
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
            await LabLogger.log("AI", f"Response received ({len(text_content)} chars)", {"raw_response": text_content})
            print("\n--- AI RESPONSE ---")
            print(text_content)
            print("-------------------\n")

            data = json.loads(text_content)
            recipe = StrategyRecipe(**data)

            # --- VALIDATION LOOP ---
            is_valid, validation_msg = self.validate_strategy(recipe)
            if not is_valid:
                await LabLogger.log("AI", f"Strategy Validation Failed: {validation_msg}. Retrying...")
                # We could implement a retry loop here (e.g. ask AI to fix).
                # For now, let's just log it and return None to prevent broken strats.
                # A better approach: "Recursively fix"
                return await self.attempt_fix_strategy(recipe, validation_msg)

            await LabLogger.log("AI", f"Strategy Validated: {recipe.name}")
            return recipe

        except Exception as e:
            err_msg = str(e)
            print(f"\n[AI ERROR] {err_msg}")
            await LabLogger.log("AI", f"Generation Error: {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("!!! GEMINI QUOTA EXCEEDED !!!")
                await LabLogger.log("AI", "!!! GEMINI QUOTA EXCEEDED !!!")
            traceback.print_exc()
            return None

    def validate_strategy(self, recipe: StrategyRecipe) -> tuple[bool, str]:
        """
        Runs a micro-backtest to ensure the strategy is executable.
        """
        from src.data_warehouse import DataWarehouse
        from src.backtester import Backtester

        # Load a small snippet of data (cached if possible)
        # We'll use a hardcoded small csv or fetch fresh if needed.
        # Ideally, we keep a "validation_dataset.parquet"
        try:
             # Just create a dummy DF or load real data? Real data is better.
             # Let's try loading from warehouse
             wh = DataWarehouse()
             # Try BTCUSDT, fallback to creating dummy data if fail
             try:
                 df = wh.load_data("BTCUSDT", "60", limit=500)
             except:
                 df = None

             if df is None or df.empty:
                 # Create dummy data
                 import pandas as pd
                 import numpy as np
                 dates = pd.date_range(start='2024-01-01', periods=200, freq='h')
                 df = pd.DataFrame({
                     'startTime': dates,
                     'open': np.random.rand(200)*100,
                     'high': np.random.rand(200)*100,
                     'low': np.random.rand(200)*100,
                     'close': np.random.rand(200)*100,
                     'volume': np.random.rand(200)*1000
                 })

             bt = Backtester(df)
             res = bt.run_vectorized_backtest(recipe)

             if "error" in res:
                 return False, res['error']

             # Optional: Check for 0 trades?
             # if res['total_trades'] == 0:
             #    return False, "Strategy produced 0 trades on validation data."

             return True, "OK"
        except Exception as e:
             return False, str(e)

    async def attempt_fix_strategy(self, failed_recipe: StrategyRecipe, error_msg: str) -> StrategyRecipe:
        """
        Asks AI to fix the broken strategy.
        """
        await LabLogger.log("AI", "Attempting self-correction...")
        prompt = f"""
        The following strategy failed backtesting validation.
        Error: {error_msg}

        Strategy JSON:
        {failed_recipe.model_dump_json()}

        Please fix the error and return the corrected JSON.
        """

        try:
             response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
             data = json.loads(response.text)
             new_recipe = StrategyRecipe(**data)

             # Re-validate
             is_valid, msg = self.validate_strategy(new_recipe)
             if is_valid:
                 await LabLogger.log("AI", "Self-correction successful!")
                 return new_recipe
             else:
                 await LabLogger.log("AI", f"Self-correction failed: {msg}")
                 return None
        except:
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

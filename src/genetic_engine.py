from src.database import SessionLocal, Strategy, BacktestResult, Settings
from src.ai_engine import AIEngine
from src.backtester import Backtester
from src.data_engine import DataEngine
from src.logger import LabLogger
from src.strategies.schemas import StrategyRecipe
import time
import json
import traceback

class GeneticBreeder:
    def __init__(self, gemini_api_key=None):
        self.db = SessionLocal()
        settings = self.db.query(Settings).first()

        self.api_key = gemini_api_key or (settings.gemini_api_key if settings else None)
        self.ai_engine = AIEngine(self.api_key) if self.api_key else None

    async def create_generation_zero(self, prompt="Create a robust profitable trend following strategy", count=3):
        """
        Creates the initial population of strategies.
        """
        if not self.ai_engine:
            await LabLogger.log("EVO", "No API Key for Gen0.")
            return []

        await LabLogger.log("EVO", f"Creating Generation 0 with {count} strategies. Prompt: {prompt}")
        strategies = []

        for i in range(count):
            try:
                recipe = self.ai_engine.generate_strategy_recipe(f"{prompt}. Variation {i+1}")
                if recipe:
                    s_ai = Strategy(
                        name=recipe.name,
                        code="", # No longer using raw python code for execution
                        content_json=recipe.model_dump(),
                        class_name="JSONStrategy",
                        type="ai_gen",
                        generation=0,
                        created_at=time.time()
                    )
                    strategies.append(s_ai)
                    await LabLogger.log("DB", f"Saved Strategy: {recipe.name}")
            except Exception as e:
                await LabLogger.log("ERROR", f"Gen0 Error: {e}")
                traceback.print_exc()

        # Save to DB
        for s in strategies:
            self.db.add(s)
        self.db.commit()
        return strategies

    async def evaluate_population(self, generation=0, symbol="BTCUSDT"):
        """
        Runs vectorized backtests on all strategies of a specific generation.
        """
        strategies = self.db.query(Strategy).filter(Strategy.generation == generation).all()
        await LabLogger.log("EVO", f"Evaluating {len(strategies)} strategies for Gen {generation} on {symbol}...")

        de = DataEngine()
        # Fetch data once (limit 1000 candles for speed)
        df = de.fetch_ohlcv(symbol, interval="60", limit=1000)

        if df.empty:
            await LabLogger.log("ERROR", f"No data for {symbol}")
            return []

        bt = Backtester(df, initial_balance=10000)
        results = []

        for s in strategies:
            try:
                # Load Recipe
                if not s.content_json:
                    # Legacy or empty?
                    continue

                recipe = StrategyRecipe(**s.content_json)

                # Run Backtest
                res = bt.run_vectorized_backtest(recipe)

                # Save Result
                br = BacktestResult(
                    strategy_id=s.id,
                    symbol=symbol,
                    start_date=str(df.iloc[0]['startTime']),
                    end_date=str(df.iloc[-1]['startTime']),
                    roi=res['roi_percent'],
                    sharpe=res['sharpe'],
                    max_drawdown=res['max_drawdown'],
                    win_rate=res['win_rate'],
                    trades_count=res['total_trades'],
                    metrics_json=json.dumps(res), # Full details including fitness
                    timestamp=time.time()
                )
                self.db.add(br)
                results.append((s, res))

                await LabLogger.log("EVO", f"Evaluated {s.name}: ROI={res['roi_percent']:.2f}%, DD={res['max_drawdown']:.2f}%, Fit={res['fitness']:.2f}")

            except Exception as e:
                await LabLogger.log("ERROR", f"Error evaluating strategy {s.id}: {e}")
                traceback.print_exc()

        self.db.commit()
        return results

    async def breed_next_generation(self, current_gen=0, symbol="BTCUSDT"):
        """
        Selects top performers (Fitness) and mutates them.
        """
        if not self.ai_engine:
            return

        # 1. Get Top 3 Results by Fitness
        # We need to calculate fitness manually or query?
        # Since 'fitness' isn't a column, we query all results for this gen and sort in python.

        results = self.db.query(BacktestResult, Strategy)\
            .join(Strategy, BacktestResult.strategy_id == Strategy.id)\
            .filter(Strategy.generation == current_gen)\
            .all()

        if not results:
            await LabLogger.log("EVO", "No results to breed from.")
            return

        # Calculate fitness and sort
        # Fitness = ROI / abs(MaxDD)
        def calc_fitness(br):
            dd = abs(br.max_drawdown)
            if dd < 0.001: dd = 0.001
            return br.roi / dd

        sorted_results = sorted(results, key=lambda x: calc_fitness(x[0]), reverse=True)
        top_performers = sorted_results[:3]

        parents = []
        for br, strat in top_performers:
            if strat.content_json:
                parents.append(StrategyRecipe(**strat.content_json))

        if not parents:
            return

        await LabLogger.log("EVO", f"Breeding from top {len(parents)} strategies (Gen {current_gen})...")

        next_gen = current_gen + 1

        # Request Mutation
        feedback = "Reduce Max Drawdown while maintaining profitability."

        # Create 3 Children
        for i in range(3):
            try:
                child_recipe = self.ai_engine.mutate_strategy_recipe(parents, feedback)

                if child_recipe:
                    # Rename to avoid duplicate names if AI forgets
                    child_recipe.name = f"Gen{next_gen}_Child_{i}_{child_recipe.name}"

                    child_strat = Strategy(
                        name=child_recipe.name,
                        code="",
                        content_json=child_recipe.model_dump(),
                        class_name="JSONStrategy",
                        type="evolved",
                        generation=next_gen,
                        parent_id=top_performers[0][1].id, # Mark top parent as primary
                        created_at=time.time()
                    )
                    self.db.add(child_strat)
                    await LabLogger.log("EVO", f"Created Child: {child_recipe.name}")

            except Exception as e:
                await LabLogger.log("ERROR", f"Mutation failed: {e}")

        self.db.commit()

        # Immediate Evaluation of New Gen?
        # The main loop calls evaluate, so we just finish here.
        await LabLogger.log("EVO", f"Generation {next_gen} created.")

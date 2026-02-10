from src.database import SessionLocal, Strategy, BacktestResult, Settings
from src.ai_engine import AIEngine
from src.backtester import Backtester
from src.data_engine import DataEngine
from src.logger import LabLogger
from src.strategies.schemas import StrategyRecipe
import time
import json
import traceback
import concurrent.futures
import asyncio

# Standalone wrapper for pickling
def evaluate_strategy_wrapper(strategy_json, df_dict, initial_balance=10000.0):
    """
    Wrapper for parallel execution.
    df_dict: dict of {col: series} or DataFrame turned to dict for safety?
    Actually DataFrame is picklable.
    """
    try:
        # Reconstruct recipe
        recipe = StrategyRecipe(**strategy_json)
        # Reconstruct Backtester
        # We pass DataFrame directly.
        bt = Backtester(df_dict, initial_balance)
        return bt.run_vectorized_backtest(recipe)
    except Exception as e:
        # traceback.print_exc()
        return {"error": str(e), "roi_percent": -100, "max_drawdown": -100, "fitness": -100}

class GeneticBreeder:
    def __init__(self, gemini_api_key=None):
        self.db = SessionLocal()
        settings = self.db.query(Settings).first()

        self.api_key = gemini_api_key or (settings.gemini_api_key if settings else None)
        self.ai_engine = AIEngine(self.api_key) if self.api_key else None
        self.settings = settings

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
                recipe = await self.ai_engine.generate_strategy_recipe(f"{prompt}. Variation {i+1}")
                if recipe:
                    s_ai = Strategy(
                        name=recipe.name,
                        code="",
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

        for s in strategies:
            self.db.add(s)
        self.db.commit()
        return strategies

    async def evaluate_population(self, generation=0, symbol="BTCUSDT", start_time=None):
        """
        Runs vectorized backtests on all strategies of a specific generation.
        Supports multiple symbols if configured in Settings.
        Uses ProcessPoolExecutor for parallel processing.
        """
        strategies = self.db.query(Strategy).filter(Strategy.generation == generation).all()

        # Determine target symbols
        target_symbols = [symbol]
        # Check settings
        # Note: 'backtest_pairs' might not exist yet on DB object until we reload/migrate
        # But we can try to access it if the object has it, or fetch raw
        if self.settings and hasattr(self.settings, 'backtest_pairs') and self.settings.backtest_pairs:
             # Expect comma separated
             target_symbols = [s.strip() for s in self.settings.backtest_pairs.split(",") if s.strip()]

        await LabLogger.log("EVO", f"Evaluating {len(strategies)} strategies for Gen {generation} on {target_symbols}...")

        de = DataEngine()
        results_summary = []

        for sym in target_symbols:
            await LabLogger.log("EVO", f"Processing Symbol: {sym}")

            # 1. Fetch Data
            if start_time:
                 df = de.fetch_ohlcv(sym, interval="60", start_time=start_time)
            else:
                 df = de.fetch_ohlcv(sym, interval="60", limit=1000)

            if df.empty:
                await LabLogger.log("ERROR", f"No data for {sym}")
                continue

            # 2. Prepare Parallel Execution
            valid_strats = [s for s in strategies if s.content_json]
            if not valid_strats:
                continue

            # Use ProcessPoolExecutor
            # We need to run sync code in process, so we use loop.run_in_executor
            loop = asyncio.get_running_loop()

            with concurrent.futures.ProcessPoolExecutor() as executor:
                tasks = []
                for s in valid_strats:
                    # Pass the JSON, not the object
                    task = loop.run_in_executor(
                        executor,
                        evaluate_strategy_wrapper,
                        s.content_json,
                        df,
                        10000.0
                    )
                    tasks.append(task)

                # Await all
                results = await asyncio.gather(*tasks)

            # 3. Save Results
            for i, res in enumerate(results):
                strat = valid_strats[i]

                # Check for error
                if "error" in res:
                     # await LabLogger.log("ERROR", f"Strat {strat.id} failed: {res['error']}")
                     continue

                # Save Result
                br = BacktestResult(
                    strategy_id=strat.id,
                    symbol=sym,
                    start_date=str(df.iloc[0]['startTime']),
                    end_date=str(df.iloc[-1]['startTime']),
                    roi=res.get('roi_percent', 0),
                    sharpe=res.get('sharpe', 0),
                    max_drawdown=res.get('max_drawdown', 0),
                    win_rate=res.get('win_rate', 0),
                    trades_count=res.get('total_trades', 0),
                    metrics_json=json.dumps(res),
                    timestamp=time.time()
                )
                self.db.add(br)
                results_summary.append((strat, res))

                # Log simplified
                # await LabLogger.log("EVO", f"Completed {strat.name} on {sym}: ROI={br.roi:.2f}%")

        self.db.commit()
        await LabLogger.log("EVO", f"Generation {generation} evaluation complete.")
        return results_summary

    async def breed_next_generation(self, current_gen=0, symbol="BTCUSDT"):
        """
        Selects top performers (Fitness) and mutates them.
        Fitness is averaged across all pairs if multiple were tested.
        """
        if not self.ai_engine:
            return

        # 1. Fetch all results for this generation
        results = self.db.query(BacktestResult).join(Strategy).filter(Strategy.generation == current_gen).all()

        if not results:
            await LabLogger.log("EVO", "No results to breed from.")
            return

        # 2. Aggregating Fitness per Strategy
        # Strategy ID -> [Results]
        strat_map = {}
        for br in results:
            if br.strategy_id not in strat_map:
                strat_map[br.strategy_id] = []
            strat_map[br.strategy_id].append(br)

        # Calculate Average Fitness
        # Fitness = ROI / abs(DD)
        fitness_scores = []
        for sid, br_list in strat_map.items():
            total_fitness = 0
            count = 0
            valid_strat = False

            for br in br_list:
                dd = abs(br.max_drawdown)
                if dd < 0.001: dd = 0.001
                fit = br.roi / dd
                total_fitness += fit
                count += 1
                # If ANY backtest had > 0 trades, considered valid?
                # Ideally we want robust strategies that trade.
                if br.trades_count > 0:
                    valid_strat = True

            avg_fitness = total_fitness / count if count > 0 else -100

            # Penalize if no trades?
            if not valid_strat:
                avg_fitness = -100

            fitness_scores.append((sid, avg_fitness))

        # Sort
        fitness_scores.sort(key=lambda x: x[1], reverse=True)

        # Get Top 3 Strategy IDs
        top_ids = [x[0] for x in fitness_scores[:3]]

        # Fetch Strategy Objects
        parents = []
        for sid in top_ids:
            s = self.db.query(Strategy).filter(Strategy.id == sid).first()
            if s and s.content_json:
                parents.append(StrategyRecipe(**s.content_json))

        if not parents:
            await LabLogger.log("EVO", "No valid parents found.")
            return

        await LabLogger.log("EVO", f"Breeding from top {len(parents)} strategies (Gen {current_gen})...")
        next_gen = current_gen + 1
        feedback = "Reduce Max Drawdown while maintaining profitability across multiple pairs."

        # Create 3 Children
        for i in range(3):
            try:
                child_recipe = await self.ai_engine.mutate_strategy_recipe(parents, feedback)

                if child_recipe:
                    child_recipe.name = f"Gen{next_gen}_Child_{i}_{child_recipe.name}"
                    child_strat = Strategy(
                        name=child_recipe.name,
                        code="",
                        content_json=child_recipe.model_dump(),
                        class_name="JSONStrategy",
                        type="evolved",
                        generation=next_gen,
                        parent_id=top_ids[0],
                        created_at=time.time()
                    )
                    self.db.add(child_strat)
                    await LabLogger.log("EVO", f"Created Child: {child_recipe.name}")

            except Exception as e:
                await LabLogger.log("ERROR", f"Mutation failed: {e}")

        self.db.commit()
        await LabLogger.log("EVO", f"Generation {next_gen} created.")

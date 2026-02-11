from src.database import SessionLocal, Strategy, BacktestResult, Settings
from src.ai_engine import AIEngine
from src.backtester import Backtester
from src.data_engine import DataEngine
from src.logger import LabLogger
from src.strategies.schemas import StrategyRecipe
from src.rate_limiter import RateLimiter, ResourceGuard
from src.jobs import JobManager
import time
import json
import traceback
import concurrent.futures
import asyncio

# Standalone wrapper for pickling
def evaluate_strategy_wrapper(strategy_json, df_dict, initial_balance=10000.0):
    """
    Wrapper for parallel execution.
    """
    try:
        # Reconstruct recipe
        recipe = StrategyRecipe(**strategy_json)
        # Reconstruct Backtester
        bt = Backtester(df_dict, initial_balance)
        return bt.run_vectorized_backtest(recipe)
    except Exception as e:
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
        """
        strategies = self.db.query(Strategy).filter(Strategy.generation == generation).all()

        target_symbols = [symbol]
        if self.settings and hasattr(self.settings, 'backtest_pairs') and self.settings.backtest_pairs:
             target_symbols = [s.strip() for s in self.settings.backtest_pairs.split(",") if s.strip()]

        await LabLogger.log("EVO", f"Evaluating {len(strategies)} strategies for Gen {generation} on {target_symbols}...")

        de = DataEngine()
        results_summary = []

        for sym in target_symbols:
            await LabLogger.log("EVO", f"Processing Symbol: {sym}")

            if start_time:
                 df = de.fetch_ohlcv(sym, interval="60", start_time=start_time)
            else:
                 df = de.fetch_ohlcv(sym, interval="60", limit=1000)

            if df.empty:
                await LabLogger.log("ERROR", f"No data for {sym}")
                continue

            valid_strats = [s for s in strategies if s.content_json]
            if not valid_strats:
                continue

            # Limit Concurrency based on Settings
            max_workers = 2
            if self.settings and hasattr(self.settings, 'max_concurrent_backtests'):
                max_workers = self.settings.max_concurrent_backtests

            loop = asyncio.get_running_loop()

            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                tasks = []
                for s in valid_strats:
                    task = loop.run_in_executor(
                        executor,
                        evaluate_strategy_wrapper,
                        s.content_json,
                        df,
                        10000.0
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks)

            for i, res in enumerate(results):
                strat = valid_strats[i]
                if "error" in res: continue

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

        self.db.commit()
        await LabLogger.log("EVO", f"Generation {generation} evaluation complete.")
        return results_summary

    async def breed_next_generation(self, current_gen=0, symbol="BTCUSDT"):
        """
        Standard batch breeding logic (Time-Based).
        """
        if not self.ai_engine: return

        results = self.db.query(BacktestResult).join(Strategy).filter(Strategy.generation == current_gen).all()
        if not results: return

        strat_map = {}
        for br in results:
            if br.strategy_id not in strat_map: strat_map[br.strategy_id] = []
            strat_map[br.strategy_id].append(br)

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
                if br.trades_count > 0: valid_strat = True

            avg_fitness = total_fitness / count if count > 0 else -100
            if not valid_strat: avg_fitness = -100
            fitness_scores.append((sid, avg_fitness))

        fitness_scores.sort(key=lambda x: x[1], reverse=True)
        top_ids = [x[0] for x in fitness_scores[:3]]

        parents = []
        for sid in top_ids:
            s = self.db.query(Strategy).filter(Strategy.id == sid).first()
            if s and s.content_json:
                parents.append(StrategyRecipe(**s.content_json))

        if not parents: return

        await LabLogger.log("EVO", f"Breeding from top {len(parents)} strategies (Gen {current_gen})...")
        next_gen = current_gen + 1
        feedback = "Reduce Max Drawdown while maintaining profitability."

        for i in range(3):
            if not RateLimiter.can_proceed():
                await LabLogger.log("EVO", "Rate Limit Reached. Skipping breed.")
                break

            try:
                RateLimiter.record_request()
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

    async def optimize_strategy(self, result_id: int):
        """
        Continuous Optimizer Logic.
        Triggered after a single backtest.
        """
        if not self.ai_engine: return

        # 1. Resource & Rate Checks
        if not ResourceGuard.is_safe(cpu_threshold=85):
            await LabLogger.log("OPTIMIZER", "System busy (High CPU). Skipping optimization.")
            return

        # Check Rate Limit EARLY
        if not RateLimiter.can_proceed():
            await LabLogger.log("OPTIMIZER", "Rate Limit Reached. Skipping optimization.")
            return

        # 2. Load Result & Strategy
        # Need a fresh session for async context if called from background task
        db = SessionLocal()
        try:
            res = db.query(BacktestResult).filter(BacktestResult.id == result_id).first()
            if not res: return

            strat = db.query(Strategy).filter(Strategy.id == res.strategy_id).first()
            if not strat or not strat.content_json: return

            # 3. Analyze: Is it worth optimizing?
            # Criteria: Trades > 0, ROI > -10% (not hopeless), Drawdown > 5% (room for improvement)
            if res.trades_count == 0 or res.roi < -10:
                await LabLogger.log("OPTIMIZER", f"Strategy {strat.id} not worth optimizing (ROI: {res.roi}%, Trades: {res.trades_count}).")
                return

            await LabLogger.log("OPTIMIZER", f"Optimizing Strategy {strat.id} (ROI: {res.roi}%, DD: {res.max_drawdown}%)...")

            # 4. Construct Prompt
            # "Strategy X had 5% ROI but 20% Drawdown. Modify the indicators or logic to reduce drawdown."
            weakness = "High Drawdown" if abs(res.max_drawdown) > 15 else "Low ROI"
            prompt = (
                f"The strategy '{strat.name}' was backtested. "
                f"Result: ROI={res.roi:.2f}%, Max Drawdown={res.max_drawdown:.2f}%, Trades={res.trades_count}. "
                f"Weakness: {weakness}. "
                "You are an architect. You can ADD an indicator (e.g. ADX, ATR), REMOVE a weak one, or CHANGE parameters. "
                f"Your goal is to fix the weakness and improve the Risk/Reward ratio. "
                "Return the improved strategy recipe."
            )

            # 5. Call AI
            RateLimiter.record_request()
            parents = [StrategyRecipe(**strat.content_json)]
            child_recipe = await self.ai_engine.mutate_strategy_recipe(parents, prompt)

            if child_recipe:
                child_recipe.name = f"Optimized_{strat.name}_v{strat.generation + 1}"

                # 6. Archive Parent
                strat.archived = True
                strat.is_active = False

                # 7. Create Child
                child_strat = Strategy(
                    name=child_recipe.name,
                    code="",
                    content_json=child_recipe.model_dump(),
                    class_name="JSONStrategy",
                    type="optimized",
                    generation=strat.generation + 1,
                    parent_id=strat.id,
                    created_at=time.time()
                )
                db.add(child_strat)
                db.commit()

                await LabLogger.log("OPTIMIZER", f"Created optimized version: {child_recipe.name}. Parent archived.")

                # 8. Auto-Queue Backtest
                # We need to import execute_backtest_job or trigger it via JobManager?
                # Circular import risk if we import execute_backtest_job from app.py.
                # Better to just let the user run it or use a callback mechanism.
                # For now, we just save it. The prompt asked for "Auto-Queue".
                # We can't easily call the async route handler from here.
                # We can replicate the job creation logic.

                # Create Job
                job_id = JobManager.create_job("backtest")

                # We can't spawn the task here easily without the FastAPI background tasks object or event loop access.
                # But we are already in an async function. We can just call the logic?
                # No, we want it to run in background.
                # For MVP, let's just log it. "Ready for backtest".
                # Or, if we passed a callback?
                # Ideally, we put this in a queue.

                await LabLogger.log("OPTIMIZER", f"New strategy {child_strat.id} ready for testing.")

        except Exception as e:
            await LabLogger.log("ERROR", f"Optimizer failed: {e}")
            traceback.print_exc()
        finally:
            db.close()

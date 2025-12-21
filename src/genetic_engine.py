from src.database import SessionLocal, Strategy, BacktestResult
from src.ai_sentiment import AISentimentAgent
from src.backtester import Backtester
from src.data_engine import DataEngine
import time
import random
import traceback
import textwrap

class GeneticBreeder:
    def __init__(self, gemini_api_key=None):
        self.ai_agent = AISentimentAgent(gemini_api_key)
        self.db = SessionLocal()

    def create_generation_zero(self, prompt="Create a robust profitable trend following strategy", count=3):
        """
        Creates the initial population of strategies.
        """
        print(f"Creating Generation 0 with {count} strategies...")
        strategies = []

        # 1. Hardcoded Strategies
        hardcoded_code = textwrap.dedent("""
        import sys
        import os
        # Ensure root is in path for imports
        if os.getcwd() not in sys.path:
            sys.path.append(os.getcwd())

        from src.strategies.base import BaseStrategy
        import pandas as pd
        import numpy as np

        class AIStrategy(BaseStrategy):
            def on_candle(self, df: pd.DataFrame) -> dict:
                if df.empty or len(df) < 20:
                     return {"signal": "hold", "confidence": 0.0}

                # Simple SMA Crossover
                df['sma_short'] = df['close'].rolling(window=10).mean()
                df['sma_long'] = df['close'].rolling(window=20).mean()

                last = df.iloc[-1]
                prev = df.iloc[-2]

                signal = "hold"
                if last['sma_short'] > last['sma_long'] and prev['sma_short'] <= prev['sma_long']:
                    signal = "buy"
                elif last['sma_short'] < last['sma_long'] and prev['sma_short'] >= prev['sma_long']:
                    signal = "sell"

                return {"signal": signal, "confidence": 0.8, "metadata": {"sma_s": last['sma_short'], "sma_l": last['sma_long']}}
        """)

        s_hard = Strategy(
            name="Gen0_Manual_SMA",
            code=hardcoded_code,
            class_name="AIStrategy",
            type="manual",
            generation=0,
            created_at=time.time()
        )
        strategies.append(s_hard)

        # 2. AI Generated Strategies
        for i in range(count):
            try:
                code = self.ai_agent.generate_strategy_code(prompt + f" Variation {i+1}")
                if code:
                    s_ai = Strategy(
                        name=f"Gen0_AI_{i+1}",
                        code=code,
                        class_name="AIStrategy",
                        type="ai_gen",
                        generation=0,
                        created_at=time.time()
                    )
                    strategies.append(s_ai)
            except Exception as e:
                print(f"Gen0 Error: {e}")

        # Save to DB
        for s in strategies:
            self.db.add(s)
        self.db.commit()
        return strategies

    def evaluate_population(self, generation=0, symbol="BTCUSDT"):
        """
        Runs backtests on all strategies of a specific generation.
        """
        strategies = self.db.query(Strategy).filter(Strategy.generation == generation).all()
        print(f"Evaluating {len(strategies)} strategies for Gen {generation}...")

        de = DataEngine()
        # Fetch data once
        df = de.fetch_ohlcv(symbol, interval="60", limit=500)

        results = []
        for s in strategies:
            try:
                # Dynamic Class Loading is tricky.
                # We need to execute the code and extract the class.
                local_scope = {}
                exec(s.code, {}, local_scope)
                StrategyClass = local_scope.get(s.class_name)

                if not StrategyClass:
                    print(f"Could not load class {s.class_name} for strategy {s.id}")
                    continue

                # Instantiate
                strategy_instance = StrategyClass()

                # Run Backtest with Walk-Forward Validation
                from src.backtester import Backtester # Lazy import to avoid cycle
                bt = Backtester(df, initial_balance=10000)

                # Use walk forward to prevent overfitting
                wf_res = bt.walk_forward_validation(strategy_instance, train_ratio=0.7)

                # We save the "Test" (Out of Sample) results as the primary metric,
                # but store full details in JSON.
                res = wf_res['test']

                # Save Result
                import json
                br = BacktestResult(
                    strategy_id=s.id,
                    symbol=symbol,
                    start_date=str(df.iloc[0]['startTime']),
                    end_date=str(df.iloc[-1]['startTime']),
                    roi=res['roi_percent'], # walk_forward returns dict with keys from calculate_metrics
                    sharpe=res['sharpe'],
                    max_drawdown=res['max_drawdown'],
                    win_rate=res['win_rate'] * 100, # Convert to percent for DB consistency if needed? Base calc returns ratio 0-1
                    trades_count=res['total_trades'],
                    metrics_json=json.dumps(wf_res), # Save full Walk Forward result
                    timestamp=time.time()
                )
                self.db.add(br)
                results.append((s, res))

            except Exception as e:
                print(f"Error evaluating strategy {s.id}: {e}")
                traceback.print_exc()

        self.db.commit()
        return results

    def breed_next_generation(self, current_gen=0, top_n=2):
        """
        Selects top performers and mutates them to create next generation.
        """
        # 1. Get Results
        results = self.db.query(BacktestResult, Strategy)\
            .join(Strategy, BacktestResult.strategy_id == Strategy.id)\
            .filter(Strategy.generation == current_gen)\
            .order_by(BacktestResult.roi.desc()).all()

        if not results:
            print("No results to breed from.")
            return

        top_performers = results[:top_n]
        print(f"Breeding from top {len(top_performers)} strategies...")

        next_gen = current_gen + 1

        for br, parent_strat in top_performers:
            # Create Mutations
            feedback = f"ROI: {br.roi}%, Sharpe: {br.sharpe}, Max DD: {br.max_drawdown}%. Win Rate: {br.win_rate}%."

            # Create 2 mutations per parent
            for i in range(2):
                try:
                    new_code = self.ai_agent.mutate_strategy_code(parent_strat.code, feedback)

                    child = Strategy(
                        name=f"Gen{next_gen}_Mutant_{parent_strat.id}_{i}",
                        code=new_code,
                        class_name=parent_strat.class_name,
                        type="evolved",
                        generation=next_gen,
                        parent_id=parent_strat.id,
                        created_at=time.time()
                    )
                    self.db.add(child)
                except Exception as e:
                    print(f"Mutation failed: {e}")

        self.db.commit()
        print(f"Generation {next_gen} created.")

import pandas as pd
import numpy as np
from src.database import SessionLocal, Indicator
import traceback

class IndicatorEngine:
    @staticmethod
    def add_indicators(df: pd.DataFrame):
        """
        Adds all indicators defined in the database to the DataFrame.
        """
        if df.empty:
            return df

        db = SessionLocal()
        indicators = db.query(Indicator).all()
        db.close()

        for ind in indicators:
            try:
                params = ind.params_json or {}

                # Execute Code
                result = IndicatorEngine.execute_indicator(df, ind.code, params)

                if result is not None:
                    if isinstance(result, pd.Series):
                        # Generate column name: NAME_Param1_Param2...
                        # Use sorted keys to ensure deterministic order if possible, or just values
                        # Python 3.7+ preserves insertion order.
                        vals = [str(v) for k, v in params.items()]
                        suffix = "_".join(vals)
                        if suffix:
                            col_name = f"{ind.name.upper()}_{suffix}"
                        else:
                            col_name = ind.name.upper()

                        df[col_name] = result

                    elif isinstance(result, pd.DataFrame):
                        # DataFrame usually has its own column names
                        df = pd.concat([df, result], axis=1)
            except Exception as e:
                print(f"Error executing indicator {ind.name}: {e}")
                traceback.print_exc()

        return df

    @staticmethod
    def execute_indicator(df: pd.DataFrame, code: str, params: dict):
        """
        Executes the python code string.
        Expects a function `def indicator(df, ...):` to be defined.
        """
        # We must pass imports in globals so the defined function can access them
        exec_globals = {'pd': pd, 'np': np}

        try:
            exec(code, exec_globals)
            if 'indicator' in exec_globals:
                func = exec_globals['indicator']
                return func(df, **params)
            else:
                print("Code must define 'def indicator(df, ...):'")
                return None
        except Exception as e:
            print(f"Exec Error: {e}")
            traceback.print_exc()
            return None

    @staticmethod
    def add_custom_indicator(df: pd.DataFrame, indicator_name: str, **kwargs):
        """
        Dynamically adds an indicator based on name from DB.
        """
        db = SessionLocal()
        ind = db.query(Indicator).filter(Indicator.name == indicator_name).first()
        db.close()

        if not ind:
            print(f"Indicator {indicator_name} not found in DB")
            return df

        # Merge defaults with kwargs
        params = ind.params_json.copy() if ind.params_json else {}
        params.update(kwargs)

        try:
            result = IndicatorEngine.execute_indicator(df, ind.code, params)
            if isinstance(result, pd.Series):
                vals = [str(v) for k, v in params.items()]
                suffix = "_".join(vals)
                col_name = f"{ind.name.upper()}_{suffix}"
                df[col_name] = result
            elif isinstance(result, pd.DataFrame):
                df = pd.concat([df, result], axis=1)
        except Exception as e:
            print(f"Error adding custom indicator {indicator_name}: {e}")

        return df

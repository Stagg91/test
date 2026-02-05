from src.ta_lib import TALib
import inspect

class LibraryManager:
    @staticmethod
    def get_available_indicators():
        """
        Reflects on TALib to list available indicators and their parameters.
        """
        indicators = []
        for name, func in inspect.getmembers(TALib, predicate=inspect.isfunction):
            if name.startswith("_"): continue

            sig = inspect.signature(func)
            params = []
            for param_name, param in sig.parameters.items():
                if param_name in ['series', 'high', 'low', 'close', 'volume']:
                    continue # Skip data inputs

                default_val = param.default if param.default != inspect.Parameter.empty else None
                params.append({
                    "name": param_name,
                    "default": default_val,
                    "type": str(param.annotation).replace("<class '", "").replace("'>", "")
                })

            indicators.append({
                "name": name,
                "params": params,
                "doc": inspect.getdoc(func) or "No description available."
            })

        return sorted(indicators, key=lambda x: x['name'])

    @staticmethod
    def get_source_code(indicator_name):
        if hasattr(TALib, indicator_name):
            func = getattr(TALib, indicator_name)
            return inspect.getsource(func)
        return "Source not found."

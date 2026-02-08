import sys
import os
import numpy as np

def get_resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def sanitize_json_types(obj):
    """
    Recursively converts numpy types and NaN/Inf to native Python types for JSON serialization.
    """
    if isinstance(obj, (float, np.floating, np.float64)):
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return float(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return sanitize_json_types(obj.tolist())
    elif isinstance(obj, dict):
        return {k: sanitize_json_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_types(v) for v in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj

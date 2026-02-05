import sys
import os
import inspect

# Ensure src is in path
sys.path.append(os.getcwd())

from src.ta_lib import TALib
from src.library_manager import LibraryManager

def verify_source():
    print("--- Verifying Source Code Retrieval ---")

    # Test getting source for 'sma'
    name = "sma"
    print(f"Testing '{name}'...")
    src = LibraryManager.get_source_code(name)
    print(f"Source length: {len(src)}")
    print(f"First 50 chars: {src[:50]}")

    if "def sma" in src or "@staticmethod" in src:
        print("SUCCESS: Source code retrieved.")
    else:
        print("FAILURE: Source code seems empty or wrong.")

if __name__ == "__main__":
    verify_source()

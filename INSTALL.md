# Staggs Hectic Trader Installation Guide

## Standalone Application (Windows/Linux)

You can build a standalone executable that includes all dependencies (Python, Libraries) so it can run on any compatible machine without pre-installed software.

### Prerequisites (For the Builder machine)
You need Python 3.10+ installed to build the app.

### Building on Windows

1.  Open `cmd` or PowerShell.
2.  Run `build_windows.bat`.
3.  This will:
    *   Install all requirements.
    *   Run PyInstaller to create a single-file executable.
4.  The output file is `dist\StaggsHecticTrader.exe`.
5.  **Running:**
    *   To run in **Desktop GUI Mode** (System Tray + Browser): Create a shortcut to the `.exe` and add `--gui` to the Target, or run via command line: `dist\StaggsHecticTrader.exe --gui`
    *   To run in **Server Mode** (Headless): Run `dist\StaggsHecticTrader.exe`. Access via browser at `http://localhost:8000`.

### Building on Linux

1.  Open Terminal.
2.  Run `./build_linux.sh`.
3.  The output file is `dist/StaggsHecticTrader`.
4.  **Running:** `./dist/StaggsHecticTrader --gui`

## Manual Installation (Source Code)

If you prefer to run from source:

1.  Install Python 3.12+.
2.  Install dependencies: `pip install -r requirements.txt`.
3.  Run: `python main.py --gui` (for Desktop App) or `python main.py` (for Server only).

## Data Location

The application database `trading_bot.db` is stored in your user data directory to ensure it persists even if you move the executable.
- **Windows:** `%APPDATA%\StaggsHecticTrader\trading_bot.db`
- **Linux:** `~/.staggshectictrader/trading_bot.db`

@echo off
echo Installing dependencies...
python -m pip install -r requirements.txt

echo Building Staggs Hectic Trader...
python build.py

echo Build complete!
echo You can find the executable in the "dist" folder.
echo To run the app, double click "dist\StaggsHecticTrader.exe" (pass --gui argument if running from cmd for desktop mode).
echo Recommended: Create a shortcut to dist\StaggsHecticTrader.exe with --gui to run in Tray Mode.
pause

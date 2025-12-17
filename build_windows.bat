@echo off
echo Installing dependencies...
python -m pip install -r requirements.txt

echo Building JulesBot...
python build.py

echo Build complete!
echo You can find the executable in the "dist" folder.
echo To run the app, double click "dist\JulesBot.exe" (pass --gui argument if running from cmd for desktop mode, or it defaults to console mode if --noconsole was not used).
echo Note: The build.py uses --noconsole, so double clicking the exe will open the GUI directly if main.py logic supports it without args or if we adjust args.
echo CURRENT LOGIC: main.py requires --gui for GUI mode.
echo For better experience, create a shortcut to dist\JulesBot.exe with --gui
pause

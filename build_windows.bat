@echo off
echo Staggs Hectic Trader Installer
echo ------------------------------

:: Check if user wants to install dependencies
set /p install_deps="Install dependencies? (y/n) [y]: "
if /i "%install_deps%"=="n" goto skip_install

echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Error installing dependencies.
    pause
    exit /b
)

:skip_install
echo Building Staggs Hectic Trader...
python build.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b
)

echo.
echo Build complete!
echo You can find the executable in the "dist" folder.
echo To run the app, double click "dist\StaggsHecticTrader.exe".
echo.
pause

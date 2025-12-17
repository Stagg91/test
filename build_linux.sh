#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Building Staggs Hectic Trader..."
python3 build.py

echo "Build complete!"
echo "Run with: ./dist/StaggsHecticTrader --gui"

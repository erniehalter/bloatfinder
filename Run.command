#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "=============================="
echo "  BloatFinder"
echo "=============================="
echo ""
echo "Scanning your disk — this takes about 30-60 seconds..."
echo ""

python3 bloatfinder.py

echo ""
read -p "Press Enter to close..."

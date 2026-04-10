#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "=============================="
echo "  BloatFinder"
echo "=============================="
echo ""
echo "Scanning your disk for bloat..."
echo ""

python3 bloatfinder.py

echo ""
read -p "Press Enter to close..."

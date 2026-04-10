# BloatFinder

A macOS disk bloat scanner that finds the biggest space hogs and tells you whether each one is safe to remove. Outputs a clean HTML report that opens in your browser automatically.

## Stack
- Pure Python 3 (stdlib only — no pip installs needed)
- Single script: `bloatfinder.py`
- HTML report output (dark UI, color-coded safety ratings)

## Run
Double-click `Run.command`, or:
```bash
python3 bloatfinder.py
```

## What it scans
- **Known bloat locations**: Library/Caches, Logs, Xcode DerivedData, iOS Simulators, Trash, Downloads, Docker, Homebrew cache, iPhone Backups, Photos Library
- **Nested folders**: All `node_modules` and `.venv` / `venv` folders found in your home directory
- **Large items**: Biggest files/folders in your home directory not covered above

## Safety ratings
- ✓ **Safe to remove** — rebuilds automatically (caches, logs, simulator data)
- ⚠ **Review first** — your files or things you may need (Downloads, backups)
- ✗ **Keep this** — don't delete (Photos library, etc.)

## Key files
- `bloatfinder.py` — main script
- `Run.command` — double-click launcher
- `reports/report.html` — generated report (gitignored)

## Notes
- No hardcoded paths — safe to move this folder anywhere
- No dependencies beyond Python 3 (comes with macOS)
- Nothing is ever deleted automatically

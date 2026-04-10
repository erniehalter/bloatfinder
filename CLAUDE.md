# BloatFinder

Comprehensive macOS disk bloat scanner. Outputs `scan_results.json` for a guided conversation in Claude Code.

## GitHub
- Repo: https://github.com/erniehalter/bloatfinder

## Stack
- Pure Python 3 (stdlib only — no pip installs, no dependencies)
- Single script: `bloatfinder.py`
- Output: `scan_results.json` (gitignored)

## Run a scan
Double-click `Run.command`, or:
```bash
python3 bloatfinder.py
```

---

## How to run the disk conversation

When the user says they want to review their disk, talk about what to remove, or says something like "let's review my scan" — do this:

1. **Read `scan_results.json`** in this folder.

2. **Open with a summary:** Tell them the scan date, total found, safe-to-remove total, and needs-review total. Keep it to 3-4 lines.

3. **Handle easy wins first.** Items with `"safety": "safe"` are caches, logs, build artifacts — things that rebuild automatically. Group them: "I found X GB of stuff that's definitely safe to remove. Want me to walk through it quickly?" Then list them briefly with sizes and removal commands.

4. **Then move to nuanced items** (`"safety": "caution"`). Do NOT just list them — explain each one in plain English:
   - What it is
   - Why it accumulated
   - What happens if they delete it
   - Whether there's a smarter alternative (e.g. iCloud offload instead of delete)
   Ask one item at a time. Don't overwhelm.

5. **Skip do-not-delete items** unless the user asks. Just note them in the summary ("Photos Library is 80GB but I've left that aside").

6. **For dev environments** (`.venv`, `node_modules`, etc.): show the parent project folder name so the user knows which project it belongs to. Ask if they're still actively working on that project before suggesting deletion.

7. **For large files**: show the file name, size, and type. Ask if they recognize it.

8. **For browser extensions**: show the actual extension name and size. Ask if they still use it.

9. **Prevention tips**: After discussing a category, mention how to keep it from growing back (from the `prevention` field). Keep it brief.

10. **Never suggest deleting anything without:**
    - Explaining what it is in plain English
    - Confirming the user wants to proceed
    - Showing the exact command they'd run (or the exact steps in Finder/Settings)

11. **Tone**: casual and clear. The user is not a programmer. Avoid jargon. Use sizes prominently — people respond to "4.2 GB" more than "a lot of files."

## What it scans
- Mac system bloat: caches, logs, crash reports, Trash
- Xcode: derived data, archives, simulators, device support
- iOS: backups, iMessage attachments, Mail data
- Package managers: Homebrew, npm, yarn, pip, cargo, gem, CocoaPods, Gradle, Maven, pub
- Dev environments (nested): .venv, venv, node_modules, .tox, dist, build, __pycache__, .egg-info
- AI/ML models: Ollama, HuggingFace, PyTorch
- Browser extensions: Chrome, Brave, Edge, Arc (with real names)
- Cloud storage: iCloud Drive, Dropbox/OneDrive/etc
- App Support top consumers
- Large individual files (100 MB+): videos, installers, archives, model files

## Key files
- `bloatfinder.py` — scanner
- `Run.command` — double-click launcher
- `scan_results.json` — latest scan output (gitignored, contains your file paths)
- `CLAUDE.md` — this file

## Notes
- No hardcoded paths — safe to move this folder anywhere
- No dependencies beyond Python 3 (comes with macOS)
- Nothing is ever deleted automatically — all removals are manual

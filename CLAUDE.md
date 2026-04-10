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

---

## What we know about this machine (updated April 10, 2026)

This section saves time — where the real bloat lives on this specific Mac and what's already been handled.

### Already cleaned (April 10, 2026) — ~24 GB freed
- **iMessage attachments** — cleared 8 GB. iCloud Messages is ON so attachments are backed up. Safe to clear periodically.
- **App caches, logs, npm, pip, Homebrew** — cleared ~4.7 GB. pip and Homebrew set to not re-cache.
- **venvs** — all projects migrated to `uv`. Freed ~2 GB. Old orphan venv at `~/venv` deleted.
- **Archived project venvs** — VRBO, Inquiry-New (in `99 Archive`) deleted.
- **Old Claude Code versions** — `~/.local/share/claude/versions/` accumulates old binaries. Only keep newest.
- **VS Code extensions** — `~/.vscode/extensions/` wiped (~1.4 GB). User is CLI-only now (Claude Code + Antigravity).
- **Downloads** — IU Health CSVs (1.66 GB), UAD installer, Cloudflare Windows installer, video deleted.
- **Homebrew packages** — removed dotnet (632 MB), heroku (226 MB), Python 3.11/3.13/3.14. Only 3.12 remains.
- **App Support** — deleted ProApps/FCP (437 MB), Microsoft/Office (294 MB), com.openai.atlas/ChatGPT (266 MB), pyinstaller cache (458 MB), wallpaper cache (598 MB).
- **pipx** — removed (uv handles everything pipx did).

### Known recurring bloat — check these first
1. **`~/Library/Messages/Attachments`** — grows as iMessages come in. Safe to clear anytime (iCloud is on).
2. **`~/.local/share/claude/versions/`** — Claude Code leaves old binaries. Delete all but newest.
3. **`~/Library/Caches`** — normal Mac cache churn. Clear when low on space.
4. **AdBlock filter lists** — `~/Library/Application Support/Google/Chrome/Default/Extensions/gighmmpiobklfepjocnamgkkbiglidom/` — sits at ~350 MB, can't reduce without Premium. Monitor but don't delete.
5. **Homebrew Python versions** — user pins to 3.12 only. Flag any `python@X.X` other than 3.12 in `/opt/homebrew/Cellar/`.
6. **`.venv` folders in archived projects** — check `99 Archive/` for stale venvs.

### What NOT to touch
- `~/Library/Application Support/Google` (3.4 GB) — Chrome profile, rebuilds fast
- `~/Library/Messages` (2+ GB) — message history, irreplaceable
- `~/Library/Application Support/Universal Audio` — audio plugin data, actively used
- `~/Library/Application Support/iZotope` — audio plugins, actively used
- `~/playwright-browsers/` — actively used for scraping projects
- `~/.antigravity/` — Google Antigravity IDE extensions, used occasionally
- `~/.rustup/` — Rust toolchain, installed intentionally
- `~/.local/share/heroku/` — already removed from Homebrew but may linger

### User profile (relevant to disk decisions)
- Uses **Gmail in Chrome**, not Apple Mail — skip Mail Data
- Uses **Claude Code CLI** and **Antigravity**, not VS Code
- Uses **uv** for all Python projects (Python 3.12 only)
- Uses **Playwright** for scraping — keep browser installs
- Uses **Universal Audio / iZotope** for music production — keep plugin data
- Does NOT use: Final Cut Pro, Microsoft Office, ChatGPT desktop app, Heroku, dotnet

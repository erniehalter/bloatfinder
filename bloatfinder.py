#!/usr/bin/env python3
"""BloatFinder — Find what's eating your disk and whether it's safe to remove."""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

HOME = Path.home()

# ── Known bloat locations ────────────────────────────────────────────────────

def _brew_cache() -> Path:
    if subprocess.run(["which", "brew"], capture_output=True).returncode == 0:
        result = subprocess.run(["brew", "--cache"], capture_output=True, text=True)
        p = Path(result.stdout.strip())
        if p.exists():
            return p
    return HOME / ".nonexistent_brew_cache_placeholder"


KNOWN = [
    {
        "label": "App Caches",
        "path": HOME / "Library/Caches",
        "safety": "safe",
        "why": "Apps rebuild these automatically when needed.",
        "how_cmd": f"rm -rf ~/Library/Caches/*",
    },
    {
        "label": "App Logs",
        "path": HOME / "Library/Logs",
        "safety": "safe",
        "why": "Old log files. Apps create fresh ones as needed.",
        "how_cmd": f"rm -rf ~/Library/Logs/*",
    },
    {
        "label": "iMessage Attachments",
        "path": HOME / "Library/Messages/Attachments",
        "safety": "caution",
        "why": "Photos, videos, and files received via iMessage. Deleting removes them from Messages on this Mac only — they stay on your phone.",
        "how_cmd": None,
    },
    {
        "label": "Xcode Derived Data",
        "path": HOME / "Library/Developer/Xcode/DerivedData",
        "safety": "safe",
        "why": "Xcode build artifacts. Xcode recreates them when you build again.",
        "how_cmd": "rm -rf ~/Library/Developer/Xcode/DerivedData/*",
    },
    {
        "label": "Xcode Archives",
        "path": HOME / "Library/Developer/Xcode/Archives",
        "safety": "caution",
        "why": "App archives. Safe if you no longer need to re-submit these versions.",
        "how_cmd": None,
    },
    {
        "label": "iOS Simulators",
        "path": HOME / "Library/Developer/CoreSimulator/Devices",
        "safety": "safe",
        "why": "iOS/tvOS/watchOS simulator images. Xcode can redownload them.",
        "how_cmd": "xcrun simctl delete unavailable",
    },
    {
        "label": "iPhone Backups",
        "path": HOME / "Library/Application Support/MobileSync/Backup",
        "safety": "caution",
        "why": "Local iPhone/iPad backups. Only delete if you have iCloud Backup on or don't need them.",
        "how_cmd": None,
    },
    {
        "label": "Trash",
        "path": HOME / ".Trash",
        "safety": "safe",
        "why": "Files you've already deleted. Empty the Trash to reclaim space.",
        "how_cmd": "Empty Trash in Finder (⌘+Shift+Delete)",
    },
    {
        "label": "Downloads",
        "path": HOME / "Downloads",
        "safety": "caution",
        "why": "Your Downloads folder. Review before deleting — you may still need some files.",
        "how_cmd": None,
    },
    {
        "label": "Docker Data",
        "path": HOME / "Library/Containers/com.docker.docker",
        "safety": "caution",
        "why": "Docker images and volumes. Use 'docker system prune' to clean unused ones.",
        "how_cmd": "docker system prune -a",
    },
    {
        "label": "Mail Data",
        "path": HOME / "Library/Mail",
        "safety": "caution",
        "why": "Mail app data including cached attachments. Use Mail → Mailbox → Erase Deleted Items.",
        "how_cmd": None,
    },
    {
        "label": "Photos Library",
        "path": HOME / "Pictures/Photos Library.photoslibrary",
        "safety": "do-not-delete",
        "why": "Your Photos library. Don't delete unless you have a full backup.",
        "how_cmd": None,
    },
    {
        "label": "Homebrew Cache",
        "path": _brew_cache(),
        "safety": "safe",
        "why": "Homebrew package download cache. Safe to clear.",
        "how_cmd": "brew cleanup --prune=all",
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def dir_size(path: Path) -> int:
    """Return total bytes under path, skipping errors."""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += dir_size(Path(entry.path))
            except OSError:
                continue
    except OSError:
        pass
    return total


def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def find_nested(name: str, root: Path, max_depth: int = 6) -> list[Path]:
    """Find directories named `name` up to max_depth levels deep."""
    results = []
    def _walk(p: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for entry in os.scandir(p):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        ep = Path(entry.path)
                        if entry.name == name:
                            results.append(ep)
                        else:
                            _walk(ep, depth + 1)
                except OSError:
                    continue
        except OSError:
            pass
    _walk(root, 0)
    return results


def top_items(root: Path, skip_names: set, n: int = 20) -> list[tuple[Path, int]]:
    """Return top-n largest direct children of root by size."""
    items = []
    try:
        for entry in os.scandir(root):
            try:
                if entry.name.startswith(".") and entry.name not in (".Trash",):
                    continue
                if entry.name in skip_names:
                    continue
                if entry.is_symlink():
                    continue
                p = Path(entry.path)
                if entry.is_file(follow_symlinks=False):
                    sz = entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    sz = dir_size(p)
                else:
                    continue
                items.append((p, sz))
            except OSError:
                continue
    except OSError:
        pass
    return sorted(items, key=lambda x: -x[1])[:n]


def find_large_files(root: Path, min_bytes: int, skip_dirs: set, max_depth: int = 8) -> list[tuple[Path, int]]:
    """Find individual files larger than min_bytes anywhere under root."""
    results = []
    def _walk(p: Path, depth: int):
        if depth > max_depth:
            return
        if str(p) in skip_dirs:
            return
        try:
            for entry in os.scandir(p):
                try:
                    if entry.is_symlink():
                        continue
                    ep = Path(entry.path)
                    if entry.is_file(follow_symlinks=False):
                        sz = entry.stat(follow_symlinks=False).st_size
                        if sz >= min_bytes:
                            results.append((ep, sz))
                    elif entry.is_dir(follow_symlinks=False):
                        _walk(ep, depth + 1)
                except OSError:
                    continue
        except OSError:
            pass
    _walk(root, 0)
    return sorted(results, key=lambda x: -x[1])[:30]


def scan_browser_extensions() -> list[dict]:
    """Scan Chrome/Brave/Edge extensions and resolve their names from manifest.json."""
    results = []
    browsers = {
        "Chrome": HOME / "Library/Application Support/Google/Chrome",
        "Brave": HOME / "Library/Application Support/BraveSoftware/Brave-Browser",
        "Edge": HOME / "Library/Application Support/Microsoft Edge",
        "Chromium": HOME / "Library/Application Support/Chromium",
    }
    for browser_name, browser_path in browsers.items():
        for profile_dir in [browser_path / "Default"] + list((browser_path).glob("Profile *")):
            ext_root = profile_dir / "Extensions"
            if not ext_root.exists():
                continue
            try:
                for ext_entry in os.scandir(ext_root):
                    if not ext_entry.is_dir(follow_symlinks=False):
                        continue
                    ext_id = ext_entry.name
                    ext_path = Path(ext_entry.path)
                    sz = dir_size(ext_path)
                    if sz < 5 * 1024 * 1024:  # skip < 5 MB
                        continue
                    # Try to get name from manifest.json inside version subfolders
                    name = ext_id
                    try:
                        for ver_entry in sorted(os.scandir(ext_path), key=lambda e: e.name, reverse=True):
                            manifest = Path(ver_entry.path) / "manifest.json"
                            if manifest.exists():
                                data = json.loads(manifest.read_text(encoding="utf-8", errors="ignore"))
                                raw_name = data.get("name", "")
                                # Some names are message keys like __MSG_appName__
                                if raw_name and not raw_name.startswith("__MSG_"):
                                    name = raw_name
                                break
                    except (OSError, json.JSONDecodeError, StopIteration):
                        pass
                    results.append({
                        "label": f"{browser_name} Extension: {name}",
                        "path": ext_path,
                        "size": sz,
                        "safety": "caution",
                        "why": f"Browser extension data. Remove via {browser_name} → Extensions if you no longer use it.",
                        "how_cmd": f"Open {browser_name} → Extensions (chrome://extensions) and remove it there.",
                    })
            except OSError:
                continue
    return sorted(results, key=lambda x: -x["size"])


# ── Scanning ─────────────────────────────────────────────────────────────────

def scan():
    print("Scanning known bloat locations...", flush=True)

    known_results = []
    known_paths = set()
    for item in KNOWN:
        path = item["path"]
        if not path.exists():
            continue
        sz = dir_size(path)
        if sz == 0:
            continue
        known_results.append({**item, "size": sz})
        known_paths.add(str(path))

    known_results.sort(key=lambda x: -x["size"])

    print("Scanning for nested node_modules and .venv folders...", flush=True)
    nested = []
    for folder_name, safety, why in [
        ("node_modules", "safe", "npm/yarn packages. Reinstall with 'npm install'. Safe to delete."),
        (".venv", "safe", "Python virtual environment. Reinstall with 'pip install -r requirements.txt'."),
        ("venv", "safe", "Python virtual environment. Reinstall with pip to restore."),
    ]:
        found = find_nested(folder_name, HOME)
        for p in found:
            sz = dir_size(p)
            if sz < 10 * 1024 * 1024:  # skip < 10 MB
                continue
            nested.append({
                "label": folder_name,
                "path": p,
                "safety": safety,
                "why": why,
                "how_cmd": f"rm -rf \"{p}\"",
                "size": sz,
            })
    nested.sort(key=lambda x: -x["size"])

    print("Scanning browser extensions...", flush=True)
    extensions = scan_browser_extensions()

    print("Finding large individual files...", flush=True)
    skip_dirs = known_paths | {str(HOME / "Library")}
    large_files = find_large_files(HOME, min_bytes=100 * 1024 * 1024, skip_dirs=skip_dirs)

    print("Finding largest top-level items in home folder...", flush=True)
    skip_names = {Path(p).name for p in known_paths} | {"Library"}
    top = top_items(HOME, skip_names=skip_names, n=20)

    return known_results, nested, extensions, large_files, top


# ── HTML ─────────────────────────────────────────────────────────────────────

SAFETY_BADGE = {
    "safe": '<span class="badge safe">✓ Safe to remove</span>',
    "caution": '<span class="badge caution">⚠ Review first</span>',
    "do-not-delete": '<span class="badge danger">✗ Keep this</span>',
}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f1117; color: #e2e8f0; padding: 2rem; max-width: 900px; margin: 0 auto; }
h1 { font-size: 1.8rem; font-weight: 700; margin-bottom: 0.25rem; }
.subtitle { color: #94a3b8; margin-bottom: 2rem; font-size: 0.95rem; }
h2 { font-size: 1.1rem; font-weight: 600; color: #94a3b8; text-transform: uppercase;
     letter-spacing: 0.05em; margin: 2rem 0 0.75rem; }
.card { background: #1e2330; border-radius: 12px; padding: 1rem 1.25rem;
        margin-bottom: 0.5rem; display: flex; align-items: flex-start;
        gap: 1rem; border: 1px solid #2d3448; }
.card:hover { border-color: #4a5568; }
.size { font-size: 1.4rem; font-weight: 700; min-width: 90px; text-align: right;
        color: #f8fafc; flex-shrink: 0; padding-top: 0.1rem; }
.info { flex: 1; }
.label { font-weight: 600; font-size: 1rem; margin-bottom: 0.2rem; }
.path { font-size: 0.78rem; color: #64748b; font-family: monospace;
        word-break: break-all; margin-bottom: 0.4rem; }
.why { font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.4rem; }
.cmd { font-size: 0.8rem; font-family: monospace; background: #0f1117;
       padding: 0.3rem 0.6rem; border-radius: 6px; color: #7dd3fc;
       display: inline-block; margin-top: 0.25rem; }
.badge { font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.6rem;
         border-radius: 99px; display: inline-block; margin-bottom: 0.35rem; }
.badge.safe { background: #14532d; color: #86efac; }
.badge.caution { background: #451a03; color: #fcd34d; }
.badge.danger { background: #450a0a; color: #fca5a5; }
.summary-bar { display: flex; gap: 2rem; flex-wrap: wrap;
               background: #1e2330; border-radius: 12px; padding: 1.25rem 1.5rem;
               margin-bottom: 2rem; border: 1px solid #2d3448; }
.stat { text-align: center; }
.stat-val { font-size: 2rem; font-weight: 800; color: #f8fafc; }
.stat-lbl { font-size: 0.8rem; color: #64748b; margin-top: 0.1rem; }
.empty { color: #4a5568; font-style: italic; padding: 0.5rem 0; }
"""

def render_card(label, path, size, safety, why, how_cmd=None):
    badge_html = SAFETY_BADGE.get(safety, SAFETY_BADGE["caution"])
    cmd_html = f'<div class="cmd">{how_cmd}</div>' if how_cmd else ""
    return f"""
<div class="card">
  <div class="size">{fmt_size(size)}</div>
  <div class="info">
    {badge_html}
    <div class="label">{label}</div>
    <div class="path">{path}</div>
    <div class="why">{why}</div>
    {cmd_html}
  </div>
</div>"""


def build_html(known_results, nested, extensions, large_files, top):
    total_known = sum(r["size"] for r in known_results)
    safe_total = sum(r["size"] for r in known_results if r["safety"] == "safe")
    safe_total += sum(r["size"] for r in nested)
    generated = datetime.now().strftime("%B %d, %Y at %-I:%M %p")

    known_html = "".join(
        render_card(r["label"], r["path"], r["size"], r["safety"], r["why"], r.get("how_cmd"))
        for r in known_results
    ) or '<div class="empty">Nothing found.</div>'

    nested_html = "".join(
        render_card(r["label"], r["path"], r["size"], r["safety"], r["why"], r.get("how_cmd"))
        for r in nested
    ) or '<div class="empty">No large node_modules or .venv folders found.</div>'

    ext_html = "".join(
        render_card(r["label"], r["path"], r["size"], r["safety"], r["why"], r.get("how_cmd"))
        for r in extensions
    ) or '<div class="empty">No large browser extensions found (or no Chrome/Brave/Edge installed).</div>'

    large_files_html = "".join(
        render_card(p.name, p, sz, "caution",
                    f"Large file ({p.suffix or 'no extension'}) — review before deleting.")
        for p, sz in large_files
    ) or '<div class="empty">No individual files over 100 MB found outside known locations.</div>'

    top_html = "".join(
        render_card(p.name, p, sz, "caution", "Large folder — review before deleting.")
        for p, sz in top
        if sz > 50 * 1024 * 1024
    ) or '<div class="empty">No large items found outside known locations.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BloatFinder Report</title>
<style>{CSS}</style>
</head>
<body>
<h1>BloatFinder</h1>
<p class="subtitle">Generated {generated}</p>

<div class="summary-bar">
  <div class="stat">
    <div class="stat-val">{fmt_size(total_known)}</div>
    <div class="stat-lbl">Found in known locations</div>
  </div>
  <div class="stat">
    <div class="stat-val" style="color:#86efac">{fmt_size(safe_total)}</div>
    <div class="stat-lbl">Safely removable</div>
  </div>
  <div class="stat">
    <div class="stat-val">{len(known_results) + len(nested) + len(extensions)}</div>
    <div class="stat-lbl">Items found</div>
  </div>
</div>

<h2>Known Bloat Locations</h2>
{known_html}

<h2>node_modules &amp; Python Environments</h2>
{nested_html}

<h2>Browser Extensions</h2>
{ext_html}

<h2>Large Files (100 MB+)</h2>
{large_files_html}

<h2>Other Large Folders in Home</h2>
{top_html}

</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    script_dir = Path(__file__).parent
    report_dir = script_dir / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "report.html"

    known_results, nested, extensions, large_files, top = scan()

    html = build_html(known_results, nested, extensions, large_files, top)
    report_path.write_text(html, encoding="utf-8")

    print(f"\nReport saved to: {report_path}")
    subprocess.run(["open", str(report_path)])


if __name__ == "__main__":
    main()

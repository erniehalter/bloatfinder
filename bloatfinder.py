#!/usr/bin/env python3
"""
BloatFinder — Comprehensive disk bloat scanner for macOS.
Outputs scan_results.json for a guided conversation in Claude Code.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
MB = 1024 * 1024
GB = 1024 * MB

# ── Utilities ─────────────────────────────────────────────────────────────────

def dir_size(path: Path) -> int:
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


def fmt(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def item(label, path, size_bytes, safety, category, why, how_to_remove=None, prevention=None):
    return {
        "label": label,
        "path": str(path),
        "size_bytes": size_bytes,
        "size_human": fmt(size_bytes),
        "safety": safety,           # "safe" | "caution" | "do-not-delete"
        "category": category,
        "why": why,
        "how_to_remove": how_to_remove,
        "prevention": prevention,
    }


def brew_cache_path() -> Path:
    if subprocess.run(["which", "brew"], capture_output=True).returncode == 0:
        r = subprocess.run(["brew", "--cache"], capture_output=True, text=True)
        p = Path(r.stdout.strip())
        if p.exists():
            return p
    return HOME / ".nonexistent_placeholder_brew"


def find_nested_dirs(names: list[str], root: Path, max_depth: int = 8,
                     skip_prefixes: list[str] | None = None) -> list[Path]:
    """Find directories whose name is in `names`, up to max_depth deep."""
    skip_prefixes = skip_prefixes or []
    results = []
    name_set = set(names)

    def _walk(p: Path, depth: int):
        if depth > max_depth:
            return
        s = str(p)
        if any(s.startswith(sp) for sp in skip_prefixes):
            return
        try:
            for entry in os.scandir(p):
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    ep = Path(entry.path)
                    if entry.name in name_set:
                        results.append(ep)
                    else:
                        _walk(ep, depth + 1)
                except OSError:
                    continue
        except OSError:
            pass

    _walk(root, 0)
    return results


def find_large_files(root: Path, min_bytes: int, skip_dirs: set[str],
                     max_depth: int = 10) -> list[tuple[Path, int]]:
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
    return sorted(results, key=lambda x: -x[1])[:40]


def extension_name(ext_path: Path) -> str:
    try:
        for ver_entry in sorted(os.scandir(ext_path), key=lambda e: e.name, reverse=True):
            manifest = Path(ver_entry.path) / "manifest.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8", errors="ignore"))
                name = data.get("name", "")
                if name and not name.startswith("__MSG_"):
                    return name
    except (OSError, json.JSONDecodeError, StopIteration):
        pass
    return ext_path.name  # fall back to hash


# ── Scanners ──────────────────────────────────────────────────────────────────

def scan_known_locations() -> list[dict]:
    print("  Scanning known Mac bloat locations...", flush=True)
    locations = [
        (
            "App Caches", HOME / "Library/Caches", "safe", "mac_bloat",
            "Apps cache data here to load faster. They rebuild automatically — safe to clear anytime.",
            "rm -rf ~/Library/Caches/*",
            "Most apps let you set cache size limits. For browsers, set a max cache size in settings.",
        ),
        (
            "App Logs", HOME / "Library/Logs", "safe", "mac_bloat",
            "Log files from apps and system processes. Old ones accumulate silently.",
            "rm -rf ~/Library/Logs/*",
            "Logs are usually capped per app but crash reports can build up. Safe to clear monthly.",
        ),
        (
            "Diagnostic / Crash Reports", HOME / "Library/Logs/DiagnosticReports", "safe", "mac_bloat",
            "macOS crash reports. Useful for debugging but often never looked at.",
            "rm -rf ~/Library/Logs/DiagnosticReports/*",
            None,
        ),
        (
            "iOS Simulator Runtime (system-level)",
            Path("/System/Volumes/Data/System/Library/AssetsV2/com_apple_MobileAsset_iOSSimulatorRuntime"),
            "caution", "xcode",
            "iOS Simulator runtime downloaded by Xcode. Survives Xcode uninstall — Apple stores it separately. "
            "Cannot be deleted with rm (SIP protected). Must be removed via Xcode → Settings → Platforms → delete iOS. "
            "Requires Xcode to be installed to remove.",
            "Open Xcode → Settings → Platforms → select iOS → click minus button",
            "When reinstalling Xcode, immediately go to Settings → Platforms and remove any simulators you don't need.",
        ),
        (
            "Apple Developer Documentation (system-level)",
            Path("/System/Volumes/Data/System/Library/AssetsV2/com_apple_MobileAsset_AppleDeveloperDocumentation"),
            "caution", "xcode",
            "Xcode offline documentation. Also SIP-protected — remove via Xcode → Documentation (remove downloads).",
            "Open Xcode → Documentation → right-click → Remove",
            None,
        ),
        (
            "Xcode Derived Data", HOME / "Library/Developer/Xcode/DerivedData", "safe", "xcode",
            "Xcode build artifacts — indexes, compiled code, test results. Rebuilds automatically.",
            "rm -rf ~/Library/Developer/Xcode/DerivedData/*",
            "In Xcode: Preferences → Locations → Derived Data → delete old entries. Or set to Relative.",
        ),
        (
            "Xcode Archives", HOME / "Library/Developer/Xcode/Archives", "caution", "xcode",
            "App archive builds, often kept for App Store re-submissions. Safe if those versions are shipped.",
            None,
            "Keep only the most recent archive per app version. Delete old ones via Xcode → Window → Organizer.",
        ),
        (
            "iOS / tvOS Simulators", HOME / "Library/Developer/CoreSimulator/Devices", "safe", "xcode",
            "Simulator disk images for every OS version you've ever installed. Xcode redownloads as needed.",
            "xcrun simctl delete unavailable",
            "Run 'xcrun simctl delete unavailable' after each Xcode update to remove stale simulators.",
        ),
        (
            "Xcode Device Support", HOME / "Library/Developer/Xcode/iOS DeviceSupport", "caution", "xcode",
            "Debug symbols downloaded when you plugged in an iOS device. Old OS versions are rarely needed.",
            None,
            "Safe to delete folders for iOS versions you no longer test on.",
        ),
        (
            "iPhone / iPad Backups", HOME / "Library/Application Support/MobileSync/Backup", "caution", "backups",
            "Local iTunes/Finder backups of your iOS devices. Can be very large. Safe only if you have iCloud Backup enabled.",
            None,
            "Switch to iCloud Backup to avoid local backups accumulating. Or do it in Finder → your device → Manage Backups.",
        ),
        (
            "iMessage Attachments", HOME / "Library/Messages/Attachments", "caution", "messages",
            "Photos, videos, audio, and files sent/received via iMessage. Deleting removes them from Messages on this Mac — they stay on your iPhone.",
            None,
            "In Messages: Settings → General → Keep Messages → set to 1 Year instead of Forever.",
        ),
        (
            "iMessage Data", HOME / "Library/Messages", "caution", "messages",
            "Full Messages database including all chat history and attachments.",
            None,
            None,
        ),
        # Mail Data intentionally omitted — user uses Gmail in Chrome, not Apple Mail
        (
            "Trash", HOME / ".Trash", "safe", "mac_bloat",
            "Files you've already deleted but haven't emptied yet.",
            "Empty Trash: ⌘⇧Delete in Finder",
            "Enable 'Remove items from Trash after 30 days' in Finder → Settings → Advanced.",
        ),
        (
            "Downloads", HOME / "Downloads", "caution", "user_files",
            "Your Downloads folder. Often contains installers, zip files, and things you've forgotten about.",
            None,
            "Sort by size in Finder. Delete installers (.dmg, .pkg) after installing — you can always redownload.",
        ),
        (
            "Photos Library", HOME / "Pictures/Photos Library.photoslibrary", "do-not-delete", "user_files",
            "Your Photos library. Do NOT delete unless you have a full backup.",
            None,
            "Use Photos → Preferences → iCloud → Optimize Mac Storage to keep originals in iCloud and small previews locally.",
        ),
        (
            "Docker Data", HOME / "Library/Containers/com.docker.docker", "caution", "docker",
            "Docker images, containers, and volumes. Can grow to tens of GBs quickly.",
            "docker system prune -a  # removes unused images, containers, networks",
            "Run 'docker system prune' regularly. Use 'docker images' to audit what you have.",
        ),
        (
            "Homebrew Cache", brew_cache_path(), "safe", "package_managers",
            "Packages downloaded by Homebrew. Kept for re-installs but rarely needed.",
            "brew cleanup --prune=all",
            "Add 'HOMEBREW_NO_INSTALL_CLEANUP=1' to your shell if you want to control this manually.",
        ),
        (
            "npm Global Cache", HOME / ".npm", "safe", "package_managers",
            "npm package download cache. Safe to clear — npm redownloads as needed.",
            "npm cache clean --force",
            None,
        ),
        (
            "Yarn Cache", HOME / ".yarn/cache", "safe", "package_managers",
            "Yarn package cache.",
            "yarn cache clean",
            None,
        ),
        (
            "pip Cache", HOME / "Library/Caches/pip", "safe", "package_managers",
            "Python pip download cache.",
            "pip cache purge",
            None,
        ),
        (
            "Rust / Cargo Registry", HOME / ".cargo/registry", "caution", "package_managers",
            "Cached Rust crates. Large if you've built many Rust projects.",
            "rm -rf ~/.cargo/registry/cache",
            "Use 'cargo cache -a' (install with cargo install cargo-cache) to clean smartly.",
        ),
        (
            "Ruby Gems", HOME / ".gem", "caution", "package_managers",
            "Globally installed Ruby gems.",
            None,
            "Use rbenv or rvm to manage Ruby versions and avoid global gem sprawl.",
        ),
        (
            "CocoaPods Cache", HOME / "Library/Caches/CocoaPods", "safe", "package_managers",
            "CocoaPods download cache.",
            "pod cache clean --all",
            None,
        ),
        (
            "Gradle Cache", HOME / ".gradle/caches", "caution", "package_managers",
            "Gradle build cache and downloaded dependencies.",
            "rm -rf ~/.gradle/caches",
            None,
        ),
        (
            "Maven Cache", HOME / ".m2/repository", "caution", "package_managers",
            "Maven dependency cache.",
            None,
            None,
        ),
        (
            "Dart / Flutter Pub Cache", HOME / ".pub-cache", "caution", "package_managers",
            "Dart/Flutter package cache.",
            "flutter pub cache clean",
            None,
        ),
        (
            "Ollama AI Models", HOME / ".ollama/models", "caution", "ai_models",
            "Locally downloaded AI models via Ollama. Each model can be 4–70 GB.",
            "ollama list  # then: ollama rm <model-name>",
            "Only keep models you actively use. Run 'ollama list' to audit.",
        ),
        (
            "HuggingFace Model Cache", HOME / ".cache/huggingface", "caution", "ai_models",
            "AI models downloaded via the HuggingFace Python library.",
            None,
            "Set HF_HOME to a folder on an external drive if you use many models.",
        ),
        (
            "PyTorch Model Cache", HOME / ".cache/torch", "caution", "ai_models",
            "PyTorch pretrained model cache.",
            None,
            None,
        ),
        (
            "Cloud Storage (iCloud Drive)", HOME / "Library/Mobile Documents", "caution", "cloud",
            "iCloud Drive local cache. Files marked 'Keep on This Mac' live here.",
            None,
            "Right-click large folders in Finder → Remove Download to keep them in iCloud only.",
        ),
        (
            "Cloud Storage (Other)", HOME / "Library/CloudStorage", "caution", "cloud",
            "Dropbox, OneDrive, Google Drive, and other cloud sync folders.",
            None,
            "Enable 'selective sync' in each cloud app to avoid syncing everything locally.",
        ),
    ]

    results = []
    for label, path, safety, category, why, how_to_remove, prevention in locations:
        if not path.exists():
            continue
        sz = dir_size(path)
        if sz < MB:
            continue
        results.append(item(label, path, sz, safety, category, why, how_to_remove, prevention))

    return sorted(results, key=lambda x: -x["size_bytes"])


def scan_dev_environments() -> list[dict]:
    print("  Scanning for development environment folders...", flush=True)

    skip = [
        str(HOME / "Library"),
        str(HOME / ".Trash"),
    ]

    targets = {
        ".venv": (
            "safe", "python_env",
            "Python virtual environment. Reinstall with: python3 -m venv .venv && pip install -r requirements.txt",
            "Delete and recreate. Never commit .venv to git — add it to .gitignore.",
        ),
        "venv": (
            "safe", "python_env",
            "Python virtual environment.",
            "Delete and recreate. Add 'venv/' to .gitignore.",
        ),
        "env": (
            "caution", "python_env",
            "Likely a Python virtual environment, but 'env' is a generic name — confirm before deleting.",
            None,
        ),
        ".tox": (
            "safe", "python_env",
            "Tox test environment cache. Recreated when you run tox.",
            "rm -rf .tox",
        ),
        "node_modules": (
            "safe", "node_env",
            "npm/yarn packages. Reinstall with: npm install (or yarn). Safe to delete when not actively working on the project.",
            "Delete when not actively working on the project. Never commit to git.",
        ),
        ".gradle": (
            "caution", "build_cache",
            "Gradle build cache inside a project.",
            None,
        ),
        "dist": (
            "caution", "build_output",
            "Build output directory. Safe if you can rebuild — check if it's a Python dist or a compiled app.",
            None,
        ),
        "build": (
            "caution", "build_output",
            "Build output directory. Usually safe to delete if you can rebuild.",
            None,
        ),
        "__pycache__": (
            "safe", "python_cache",
            "Python bytecode cache. Python recreates it automatically.",
            "find . -type d -name __pycache__ -exec rm -rf {} +",
        ),
    }

    # Also find *.egg-info directories
    results = []
    found = find_nested_dirs(list(targets.keys()), HOME, max_depth=8, skip_prefixes=skip)

    for p in found:
        sz = dir_size(p)
        if sz < 5 * MB:
            continue
        name = p.name
        if name not in targets:
            continue
        safety, category, why, prevention = targets[name]
        how = f'rm -rf "{p}"'
        results.append(item(
            f"{name} ({p.parent.name})",
            p, sz, safety, category, why, how, prevention,
        ))

    # Find .egg-info dirs separately (pattern match)
    def find_egg_info(root: Path, depth: int = 0):
        if depth > 8:
            return
        try:
            for entry in os.scandir(root):
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    ep = Path(entry.path)
                    if entry.name.endswith(".egg-info"):
                        sz = dir_size(ep)
                        if sz >= MB:
                            results.append(item(
                                f".egg-info ({ep.parent.name})", ep, sz,
                                "safe", "python_cache",
                                "Python package metadata. Regenerated when you run pip install -e .",
                                f'rm -rf "{ep}"', None,
                            ))
                    elif entry.name not in {"Library", ".Trash", ".git"}:
                        find_egg_info(ep, depth + 1)
                except OSError:
                    continue
        except OSError:
            pass

    find_egg_info(HOME)

    return sorted(results, key=lambda x: -x["size_bytes"])


BLOATED_EXTENSIONS = {
    # Known extensions that store large filter lists in data/rules/
    "gighmmpiobklfepjocnamgkkbiglidom": "AdBlock",
    "cjpalhdlnbpafiamejdnhcphjbkeiagm": "uBlock Origin",
    "gighmmpiobklfepjocnamgkkbiglidom": "AdBlock",
    "cfhdojbkjhnklbpkdaibdccddilifddb": "Adblock Plus",
}

ADBLOCK_IDS = set(BLOATED_EXTENSIONS.keys())


def scan_browser_extensions() -> list[dict]:
    print("  Scanning browser extensions...", flush=True)
    results = []
    browsers = {
        "Chrome": HOME / "Library/Application Support/Google/Chrome",
        "Brave": HOME / "Library/Application Support/BraveSoftware/Brave-Browser",
        "Edge": HOME / "Library/Application Support/Microsoft Edge",
        "Chromium": HOME / "Library/Application Support/Chromium",
        "Arc": HOME / "Library/Application Support/Arc",
    }
    for browser_name, browser_path in browsers.items():
        for profile_dir in [browser_path / "Default"] + list(browser_path.glob("Profile *")):
            ext_root = profile_dir / "Extensions"
            if not ext_root.exists():
                continue
            try:
                for ext_entry in os.scandir(ext_root):
                    if not ext_entry.is_dir(follow_symlinks=False):
                        continue
                    ext_path = Path(ext_entry.path)
                    ext_id = ext_entry.name
                    sz = dir_size(ext_path)
                    if sz < 5 * MB:
                        continue
                    name = extension_name(ext_path)

                    # Special case: ad blockers with large filter rule folders
                    if ext_id in ADBLOCK_IDS or "adblock" in name.lower() or "ublock" in name.lower():
                        rules_path = None
                        for ver in ext_path.iterdir():
                            candidate = ver / "data" / "rules"
                            if candidate.exists():
                                rules_path = candidate
                                break
                        if rules_path:
                            rules_sz = dir_size(rules_path)
                            filter_count = sum(1 for _ in rules_path.glob("dnr/*") if not _.name.endswith(".map"))
                            results.append(item(
                                f"{browser_name}: {name} (filter lists)",
                                rules_path, rules_sz, "caution", "browser",
                                f"{name} is subscribed to {filter_count} filter lists taking {fmt(rules_sz)}. "
                                f"Most people only need 2-3. Reduce subscriptions in {name} Settings → Filter Lists "
                                f"to permanently shrink this. Deleting this folder just makes it redownload everything.",
                                f"Open {name} → Settings → Filter Lists → unsubscribe from unused lists",
                                f"Keep only: EasyList, EasyPrivacy, and one regional list if needed. Uncheck everything else.",
                            ))
                            continue

                    results.append(item(
                        f"{browser_name}: {name}",
                        ext_path, sz, "caution", "browser",
                        f"Browser extension data. If you don't use it, remove it via {browser_name} → Extensions.",
                        f"Open {browser_name} → chrome://extensions → remove the extension",
                        "Audit extensions periodically — unused ones still run and use disk space.",
                    ))
            except OSError:
                continue
    return sorted(results, key=lambda x: -x["size_bytes"])


def scan_large_files(skip_dirs: set[str]) -> list[dict]:
    print("  Scanning for large individual files (100 MB+)...", flush=True)
    found = find_large_files(HOME, min_bytes=100 * MB, skip_dirs=skip_dirs)
    results = []
    for p, sz in found:
        ext = p.suffix.lower()
        if ext in {".dmg", ".pkg", ".iso"}:
            safety, why = "safe", "Installer image. Safe to delete after you've installed the app."
        elif ext in {".zip", ".tar", ".gz", ".bz2", ".7z", ".rar"}:
            safety, why = "caution", "Archive file. Safe if you've already extracted what you need."
        elif ext in {".mov", ".mp4", ".avi", ".mkv", ".m4v"}:
            safety, why = "caution", "Video file. Review before deleting."
        elif ext in {".gguf", ".bin", ".safetensors", ".pt", ".pth"}:
            safety, why = "caution", "AI model file. Can be redownloaded if needed."
        else:
            safety, why = "caution", f"Large file ({ext or 'no extension'}). Review before deleting."
        results.append(item(p.name, p, sz, safety, "large_file", why, f'rm "{p}"', None))
    return results


def scan_claude_old_versions() -> list[dict]:
    """Flag old Claude Code versions — keep only the newest."""
    versions_dir = HOME / ".local/share/claude/versions"
    if not versions_dir.exists():
        return []
    try:
        entries = sorted(
            [e for e in versions_dir.iterdir() if e.is_file()],
            key=lambda e: [int(x) for x in e.name.split(".") if x.isdigit()],
            reverse=True,
        )
    except (OSError, ValueError):
        return []
    if len(entries) <= 1:
        return []
    results = []
    for old in entries[1:]:  # skip the newest
        try:
            sz = old.stat().st_size
        except OSError:
            continue
        results.append(item(
            f"Old Claude Code version: {old.name}",
            old, sz, "safe", "app_versions",
            f"Old Claude Code binary. Version {entries[0].name} is current — this one is unused.",
            f'rm "{old}"',
            "Claude Code auto-downloads updates but doesn't clean up old versions automatically.",
        ))
    return results


def scan_python_versions() -> list[dict]:
    """Warn if multiple Homebrew Python versions are installed."""
    cellar = Path("/opt/homebrew/Cellar")
    if not cellar.exists():
        return []
    try:
        pythons = sorted([
            e for e in cellar.iterdir()
            if e.name.startswith("python@") and e.is_dir()
        ], key=lambda e: e.name)
    except OSError:
        return []
    if len(pythons) <= 1:
        return []
    results = []
    for p in pythons:
        if p.name == "python@3.12":
            continue  # keep this one
        sz = dir_size(p)
        results.append(item(
            f"Extra Python version: {p.name}",
            p, sz, "safe", "python_versions",
            f"You only need Python 3.12. This version is unused and can be removed.",
            f"brew uninstall {p.name}",
            "Run 'brew uninstall <version>' to remove. Only keep python@3.12.",
        ))
    return results


def scan_app_support_top() -> list[dict]:
    """Find the largest items inside ~/Library/Application Support."""
    print("  Scanning Application Support top consumers...", flush=True)
    app_support = HOME / "Library/Application Support"
    if not app_support.exists():
        return []
    results = []
    try:
        entries = []
        for entry in os.scandir(app_support):
            try:
                if entry.is_symlink():
                    continue
                p = Path(entry.path)
                sz = dir_size(p) if entry.is_dir() else entry.stat().st_size
                if sz >= 100 * MB:
                    entries.append((p, sz))
            except OSError:
                continue
        entries.sort(key=lambda x: -x[1])
        for p, sz in entries[:20]:
            results.append(item(
                f"App Support: {p.name}", p, sz, "caution", "app_support",
                f"Data stored by '{p.name}'. May include caches, databases, or app content.",
                None, None,
            ))
    except OSError:
        pass
    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = Path(__file__).parent
    out_path = script_dir / "scan_results.json"

    print("\nBloatFinder — Comprehensive Disk Scan")
    print("=" * 40)

    known = scan_known_locations()
    dev_envs = scan_dev_environments()
    browsers = scan_browser_extensions()
    app_support = scan_app_support_top()
    claude_versions = scan_claude_old_versions()
    python_versions = scan_python_versions()

    # Build skip set for large-file scan (avoid recounting known dirs)
    skip_dirs = {r["path"] for r in known + dev_envs + browsers + app_support}
    skip_dirs.add(str(HOME / "Library"))

    large_files = scan_large_files(skip_dirs)

    all_items = known + dev_envs + browsers + app_support + claude_versions + python_versions + large_files
    total_bytes = sum(r["size_bytes"] for r in all_items)
    safe_bytes = sum(r["size_bytes"] for r in all_items if r["safety"] == "safe")
    caution_bytes = sum(r["size_bytes"] for r in all_items if r["safety"] == "caution")

    output = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "scanned_at_local": datetime.now().strftime("%B %d, %Y at %-I:%M %p"),
        "home_dir": str(HOME),
        "summary": {
            "total_found_human": fmt(total_bytes),
            "total_found_bytes": total_bytes,
            "safely_removable_human": fmt(safe_bytes),
            "safely_removable_bytes": safe_bytes,
            "review_needed_human": fmt(caution_bytes),
            "review_needed_bytes": caution_bytes,
            "item_count": len(all_items),
        },
        "sections": {
            "known_mac_bloat": known,
            "dev_environments": dev_envs,
            "browser_extensions": browsers,
            "app_support_consumers": app_support,
            "old_app_versions": claude_versions,
            "extra_python_versions": python_versions,
            "large_files": large_files,
        },
    }

    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"\n{'=' * 40}")
    print(f"Scan complete — {datetime.now().strftime('%-I:%M %p')}")
    print(f"  Found:            {fmt(total_bytes)} across {len(all_items)} items")
    print(f"  Safe to remove:   {fmt(safe_bytes)}")
    print(f"  Needs review:     {fmt(caution_bytes)}")
    print(f"\nResults saved to: scan_results.json")
    print("\nNow open Claude Code in this folder and say:")
    print('  "Let\'s review my disk scan"')
    print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RELEASE_ROOT = Path.home() / "Develop" / "AI Proxy Hub" / "releases"
SOURCE_SNAPSHOT_FILES = [
    ".gitignore",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "MANIFEST.in",
    "README.md",
    "pyproject.toml",
    "start.py",
    "router_server.py",
    "cli_modern.py",
]
SOURCE_SNAPSHOT_DIRS = [
    ".github",
    "ai_proxy_hub",
    "docs",
    "examples",
    "scripts",
    "tests",
    "web",
]
OPTIONAL_SOURCE_FILES = ["LICENSE", "LICENSE.md", "COPYING"]
SOURCE_IGNORE_PATTERNS = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "dist",
    "dist-*",
    "dist*",
    "build",
    "*.egg-info",
    "tmp",
    "*.tmp",
    "*.log",
    "*.backup",
    "*-state.json",
    "api-config.json",
    "api-config.local.json",
    "config_*.json",
)


def normalize_version_tag(version: str) -> str:
    text = str(version or "").strip()
    if not text:
        raise ValueError("version is required")
    return text if text.startswith("v") else f"v{text}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync the current dev tree into the local release snapshot directory")
    parser.add_argument("--version", required=True, help="Release version, with or without leading v")
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]), help="Source project root")
    parser.add_argument("--release-root", default=str(DEFAULT_RELEASE_ROOT), help="Root release directory")
    parser.add_argument("--keep-existing", action="store_true", help="Do not wipe the existing source-snapshot directory before sync")
    return parser.parse_args()


def sync_release_snapshot(source_root: Path, release_root: Path, version_tag: str, *, clean: bool = True) -> Path:
    version_dir = release_root / version_tag
    snapshot_dir = version_dir / "source-snapshot"
    if clean and snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (version_dir / "notes").mkdir(parents=True, exist_ok=True)

    copied_entries: list[str] = []
    snapshot_entries = [
        source_root / relative
        for relative in SOURCE_SNAPSHOT_FILES
        if (source_root / relative).exists()
    ]
    snapshot_entries.extend(
        source_root / relative
        for relative in SOURCE_SNAPSHOT_DIRS
        if (source_root / relative).exists()
    )
    snapshot_entries.extend(source_root / relative for relative in OPTIONAL_SOURCE_FILES if (source_root / relative).exists())
    for source in snapshot_entries:
        target = snapshot_dir / source.relative_to(source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=SOURCE_IGNORE_PATTERNS)
        else:
            shutil.copy2(source, target)
        copied_entries.append(str(source.relative_to(source_root)))

    manifest = {
        "version": version_tag,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source_root.resolve()),
        "release_root": str(release_root.resolve()),
        "entries": copied_entries,
    }
    (snapshot_dir / "SYNC_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return snapshot_dir


def main() -> None:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    release_root = Path(args.release_root).resolve()
    version_tag = normalize_version_tag(args.version)
    snapshot_dir = sync_release_snapshot(source_root, release_root, version_tag, clean=not args.keep_existing)
    print(snapshot_dir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_REPO_ROOT = Path.home() / "Develop" / "AI Proxy Hub" / "winget-staging"
DEFAULT_PACKAGE_ID = "AIProxyHub.AIProxyHub"
SOURCE_FILES = {
    "winget.yaml": ".yaml",
    "winget.installer.yaml": ".installer.yaml",
    "winget.locale.en-US.yaml": ".locale.en-US.yaml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync generated winget manifests into a repository checkout or staging tree")
    parser.add_argument("--source-dir", required=True, help="Directory containing winget.yaml, winget.installer.yaml, and winget.locale.en-US.yaml")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT), help="Root of a winget-pkgs checkout or local staging tree")
    parser.add_argument("--package-id", default=DEFAULT_PACKAGE_ID, help="winget package identifier")
    parser.add_argument("--version", required=True, help="Package version")
    return parser.parse_args()


def manifest_target_dir(repo_root: Path, package_id: str, version: str) -> Path:
    publisher, package = package_id.split(".", 1)
    return repo_root / "manifests" / publisher[:1].lower() / publisher / package / version


def winget_readme(package_id: str, version: str) -> str:
    return "\n".join(
        [
            f"# Winget Staging for {package_id}",
            "",
            f"Current staged version: `{version}`",
            "",
            "This directory mirrors the `winget-pkgs` manifest layout so the generated files can be reviewed locally before opening a public submission.",
            "",
            "Typical next step:",
            "",
            "```bash",
            "git clone https://github.com/microsoft/winget-pkgs.git",
            "# copy the staged manifests into that checkout or point --repo-root there directly",
            "```",
            "",
        ]
    )


def sync_winget_manifest(source_dir: Path, repo_root: Path, package_id: str, version: str) -> Path:
    source_dir = source_dir.resolve()
    repo_root = repo_root.resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Missing source dir: {source_dir}")
    target_dir = manifest_target_dir(repo_root, package_id, version)
    target_dir.mkdir(parents=True, exist_ok=True)
    for source_name, suffix in SOURCE_FILES.items():
        source_path = source_dir / source_name
        if not source_path.exists():
            raise FileNotFoundError(f"Missing manifest file: {source_path}")
        target_path = target_dir / f"{package_id}{suffix}"
        shutil.copy2(source_path, target_path)
    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        readme_path.write_text(winget_readme(package_id, version), encoding="utf-8")
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".DS_Store\n", encoding="utf-8")
    return target_dir


def main() -> None:
    args = parse_args()
    target_dir = sync_winget_manifest(
        Path(args.source_dir),
        Path(args.repo_root),
        str(args.package_id),
        str(args.version),
    )
    print(target_dir)


if __name__ == "__main__":
    main()

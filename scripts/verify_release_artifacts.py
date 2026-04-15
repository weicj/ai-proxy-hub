#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_release


REQUIRED_PATHS = [
    "LICENSE",
    "aiproxyhub.py",
    "ai_proxy_hub/__main__.py",
    "cli_modern.py",
    "ai_proxy_hub/__init__.py",
    "ai_proxy_hub/entrypoints.py",
    "web/index.html",
    "web/app-05-bootstrap.js",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify AI Proxy Hub release artifacts")
    parser.add_argument("--dist-dir", default="dist", help="Directory containing built release archives")
    parser.add_argument("--version", required=True, help="Release version used in archive names")
    return parser.parse_args()


def archive_paths(dist_dir: Path, version: str) -> tuple[Path, Path]:
    stem = f"{build_release.APP_SLUG}-{version}"
    return dist_dir / f"{stem}.tar.gz", dist_dir / f"{stem}.zip"


def read_archive_members(path: Path) -> list[str]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


def verify_members(path: Path, required_paths: list[str]) -> None:
    members = read_archive_members(path)
    missing = []
    for required in required_paths:
        if not any(member.endswith(required) for member in members):
            missing.append(required)
    if missing:
        raise RuntimeError(f"{path.name} is missing required files: {', '.join(missing)}")


def extract_archive(path: Path, target_dir: Path) -> Path:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            archive.extractall(target_dir)
    else:
        with tarfile.open(path, "r:gz") as archive:
            archive.extractall(target_dir)
    directories = [item for item in target_dir.iterdir() if item.is_dir()]
    if len(directories) != 1:
        raise RuntimeError(f"Expected exactly one extracted root in {path.name}, found {len(directories)}")
    return directories[0]


def smoke_test_runtime(extracted_root: Path) -> None:
    with tempfile.TemporaryDirectory() as temp_home:
        home = Path(temp_home)
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["APPDATA"] = str(home / "AppData")
        env["XDG_CONFIG_HOME"] = str(home / ".config")
        version_run = subprocess.run(
            [sys.executable, "-m", "ai_proxy_hub", "--version"],
            cwd=extracted_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        if not version_run.stdout.strip():
            raise RuntimeError("Version output was empty")
        paths_run = subprocess.run(
            [sys.executable, "-m", "ai_proxy_hub", "--print-paths"],
            cwd=extracted_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(paths_run.stdout)
        if payload.get("app_name") != build_release.APP_NAME:
            raise RuntimeError(f"Expected app_name {build_release.APP_NAME}, got {payload.get('app_name')}")
        expected_static_dir = str((extracted_root / "web").resolve())
        if payload.get("static_dir") != expected_static_dir:
            raise RuntimeError(
                f"Expected static_dir {expected_static_dir}, got {payload.get('static_dir')}"
            )


def main() -> None:
    args = parse_args()
    dist_dir = Path(args.dist_dir).resolve()
    tar_path, zip_path = archive_paths(dist_dir, args.version)
    for path in [tar_path, zip_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing release artifact: {path}")
        verify_members(path, REQUIRED_PATHS)
    with tempfile.TemporaryDirectory() as tempdir:
        extracted_root = extract_archive(tar_path, Path(tempdir))
        smoke_test_runtime(extracted_root)
    print(f"verified: {tar_path.name}, {zip_path.name}")


if __name__ == "__main__":
    main()

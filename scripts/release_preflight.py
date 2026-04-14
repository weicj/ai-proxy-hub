#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


APP_SLUG = "ai-proxy-hub"
REQUIRED_FILES = [
    "README.md",
    "README.zh-CN.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "NOTICE",
    "pyproject.toml",
    "start.py",
    "router_server.py",
    "cli_modern.py",
]
REQUIRED_DIRS = [
    "ai_proxy_hub",
    "docs",
    "scripts",
    "tests",
    "web",
]
REQUIRED_SCREENSHOTS = [
    "docs/screenshots/en/overview.png",
    "docs/screenshots/en/codex-workspace.png",
    "docs/screenshots/en/claude-workspace.png",
    "docs/screenshots/en/local-keys.png",
    "docs/screenshots/en/subscription-editor.png",
    "docs/screenshots/en/usage-analytics.png",
    "docs/screenshots/en/cli-main.svg",
    "docs/screenshots/zh/overview.png",
    "docs/screenshots/zh/codex-workspace.png",
    "docs/screenshots/zh/claude-workspace.png",
    "docs/screenshots/zh/local-keys.png",
    "docs/screenshots/zh/subscription-editor.png",
    "docs/screenshots/zh/usage-analytics.png",
    "docs/screenshots/zh/cli-main.svg",
]
PLACEHOLDER_RULES = {
    "CONTRIBUTING.md": [r"<owner>"],
    "CHANGELOG.md": [r"2024-01-XX", r"2023-XX-XX"],
}
TRACKED_RUNTIME_PATTERNS = [
    re.compile(r"(^|/)tmp(/|$)"),
    re.compile(r"(^|/)dist[^/]*(/|$)"),
    re.compile(r"(^|/)build(/|$)"),
    re.compile(r"(^|/).*\.log$"),
    re.compile(r"(^|/).*\.tmp$"),
    re.compile(r"(^|/).*\.backup$"),
    re.compile(r"(^|/).*?-state\.json$"),
    re.compile(r"(^|/)api-config(\.local)?\.json$"),
    re.compile(r"(^|/)config_.*\.json$"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run publish-readiness checks for AI Proxy Hub")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="Project root")
    parser.add_argument("--version", help="Expected project version")
    parser.add_argument(
        "--allow-missing-public-links",
        action="store_true",
        help="Allow repository and release URLs to remain empty",
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip unittest execution")
    parser.add_argument("--skip-build", action="store_true", help="Skip release build and artifact verification")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pyproject_version(root: Path) -> str:
    content = read_text(root / "pyproject.toml")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not detect version from pyproject.toml")
    return match.group(1).strip()


def constants_urls(root: Path) -> tuple[str, str]:
    content = read_text(root / "ai_proxy_hub" / "constants.py")
    repo_match = re.search(r'^APP_REPOSITORY_URL\s*=\s*"([^"]*)"', content, flags=re.MULTILINE)
    releases_match = re.search(r'^APP_RELEASES_URL\s*=\s*"([^"]*)"', content, flags=re.MULTILINE)
    repository_url = repo_match.group(1).strip() if repo_match else ""
    releases_url = releases_match.group(1).strip() if releases_match else ""
    return repository_url, releases_url


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def find_tracked_runtime_leaks(root: Path) -> list[str]:
    leaks: list[str] = []
    for relative in tracked_files(root):
        if any(pattern.search(relative) for pattern in TRACKED_RUNTIME_PATTERNS):
            leaks.append(relative)
    return leaks


def run_checked(cmd: list[str], root: Path) -> None:
    subprocess.run(cmd, cwd=root, check=True)


def directory_supports_writes(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    probe_path = path / f".{APP_SLUG}-preflight-write-test-{os.getpid()}"
    try:
        with probe_path.open("w", encoding="utf-8") as handle:
            handle.write("ok")
        return True
    except OSError:
        return False
    finally:
        try:
            probe_path.unlink()
        except OSError:
            pass


def resolve_preflight_output_dir(root: Path, requested: str = "dist-preflight") -> tuple[Path, tempfile.TemporaryDirectory | None]:
    preferred = (root / requested).resolve()
    if directory_supports_writes(preferred):
        return preferred, None
    temporary_dir = tempfile.TemporaryDirectory(prefix=f"{APP_SLUG}-preflight-")
    fallback = Path(temporary_dir.name).resolve()
    print(
        f"INFO {preferred} is not writable; using temporary preflight output dir {fallback}",
        file=sys.stderr,
    )
    return fallback, temporary_dir


def gather_failures(root: Path, args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing required file: {relative}")
    for relative in REQUIRED_DIRS:
        if not (root / relative).is_dir():
            failures.append(f"missing required directory: {relative}")
    for relative in REQUIRED_SCREENSHOTS:
        if not (root / relative).is_file():
            failures.append(f"missing required screenshot: {relative}")
    for relative, patterns in PLACEHOLDER_RULES.items():
        path = root / relative
        if not path.exists():
            continue
        content = read_text(path)
        for pattern in patterns:
            if re.search(pattern, content):
                failures.append(f"placeholder still present in {relative}: {pattern}")
    if args.version:
        current_version = pyproject_version(root)
        if current_version != args.version:
            failures.append(f"pyproject version mismatch: expected {args.version}, found {current_version}")
    repository_url, releases_url = constants_urls(root)
    if not args.allow_missing_public_links:
        if not repository_url:
            failures.append("APP_REPOSITORY_URL is empty")
        if not releases_url:
            failures.append("APP_RELEASES_URL is empty")
    leaks = find_tracked_runtime_leaks(root)
    for relative in leaks:
        failures.append(f"tracked runtime artifact should not be committed: {relative}")
    return failures


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    failures = gather_failures(root, args)
    if failures:
        for item in failures:
            print(f"FAIL {item}")
        raise SystemExit(1)
    if not args.skip_tests:
        run_checked([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], root)
    if not args.skip_build:
        version = args.version or pyproject_version(root)
        output_dir, temporary_dir = resolve_preflight_output_dir(root)
        try:
            output_dir_arg = str(output_dir)
            run_checked([sys.executable, "scripts/build_release.py", "--version", version, "--output-dir", output_dir_arg], root)
            run_checked([sys.executable, "scripts/verify_release_artifacts.py", "--dist-dir", output_dir_arg, "--version", version], root)
        finally:
            if temporary_dir is not None:
                temporary_dir.cleanup()
    print("PASS release preflight")


if __name__ == "__main__":
    main()

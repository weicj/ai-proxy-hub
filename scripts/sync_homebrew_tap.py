#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_TAP_ROOT = Path.home() / "Develop" / "AI Proxy Hub" / "homebrew-aiproxyhub"
DEFAULT_TAP_REPO = "weicj/homebrew-aiproxyhub"
FORMULA_FILE_NAME = "ai-proxy-hub.rb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync a generated Homebrew formula into a tap repository checkout")
    parser.add_argument("--formula", required=True, help="Path to the generated ai-proxy-hub.rb formula file")
    parser.add_argument("--tap-root", default=str(DEFAULT_TAP_ROOT), help="Local checkout path of the Homebrew tap repository")
    parser.add_argument("--tap-repo", default=DEFAULT_TAP_REPO, help="GitHub repository slug of the Homebrew tap")
    parser.add_argument("--version", help="Optional release version for README rendering")
    return parser.parse_args()


def tap_shorthand(tap_repo: str) -> str:
    shorthand = tap_repo
    if "/" in tap_repo:
        owner, repo = tap_repo.split("/", 1)
        shorthand = f"{owner}/{repo.removeprefix('homebrew-')}"
    return shorthand


def tap_readme(app_name: str, tap_repo: str, version: str = "") -> str:
    shorthand = tap_shorthand(tap_repo)
    lines = [
        f"# Homebrew Tap for {app_name}",
        "",
    ]
    if version:
        lines.extend(
            [
                f"Current packaged version: `{version}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Install",
            "",
            "```bash",
            f"brew tap {shorthand}",
            "brew install ai-proxy-hub",
            "```",
            "",
            "Or install directly without a separate `brew tap` step:",
            "",
            "```bash",
            f"brew install {shorthand}/ai-proxy-hub",
            "```",
            "",
            "## Update",
            "",
            "```bash",
            "brew update",
            "brew upgrade ai-proxy-hub",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def sync_homebrew_tap(formula_path: Path, tap_root: Path, tap_repo: str, *, version: str = "", app_name: str = "AI Proxy Hub") -> Path:
    formula_path = formula_path.resolve()
    tap_root = tap_root.resolve()
    if not formula_path.exists():
        raise FileNotFoundError(f"Missing formula file: {formula_path}")

    formula_dir = tap_root / "Formula"
    formula_dir.mkdir(parents=True, exist_ok=True)
    target_formula = formula_dir / FORMULA_FILE_NAME
    shutil.copy2(formula_path, target_formula)

    readme_path = tap_root / "README.md"
    readme_path.write_text(tap_readme(app_name, tap_repo, version), encoding="utf-8")

    gitignore_path = tap_root / ".gitignore"
    if not gitignore_path.exists():
      gitignore_path.write_text(".DS_Store\n", encoding="utf-8")

    return target_formula


def main() -> None:
    args = parse_args()
    target_formula = sync_homebrew_tap(
        Path(args.formula),
        Path(args.tap_root),
        str(args.tap_repo),
        version=str(args.version or ""),
    )
    print(target_formula)


if __name__ == "__main__":
    main()

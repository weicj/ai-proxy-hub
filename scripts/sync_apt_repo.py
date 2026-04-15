#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_REPO_ROOT = Path.home() / "Develop" / "AI Proxy Hub" / "apt-repo"
DEFAULT_DISTRIBUTION = "stable"
DEFAULT_COMPONENT = "main"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync a .deb artifact into a simple APT repository tree")
    parser.add_argument("--deb", required=True, help="Path to the built .deb artifact")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT), help="APT repository root")
    parser.add_argument("--distribution", default=DEFAULT_DISTRIBUTION, help="APT distribution, for example stable")
    parser.add_argument("--component", default=DEFAULT_COMPONENT, help="APT component, for example main")
    return parser.parse_args()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_deb_control_fields(deb_path: Path) -> dict[str, str]:
    result = subprocess.run(
        ["dpkg-deb", "-f", str(deb_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in result.stdout.splitlines():
        if raw_line.startswith(" ") and current_key:
            fields[current_key] = fields[current_key] + "\n" + raw_line[1:]
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        fields[current_key] = value.strip()
    return fields


def pool_target_path(repo_root: Path, deb_path: Path, package_name: str, component: str) -> Path:
    first_letter = (package_name[:1] or "a").lower()
    return repo_root / "pool" / component / first_letter / package_name / deb_path.name


def package_entry(relative_deb_path: Path, deb_path: Path, control_fields: dict[str, str]) -> str:
    lines = []
    preferred_keys = [
        "Package",
        "Version",
        "Section",
        "Priority",
        "Architecture",
        "Maintainer",
        "Depends",
        "Description",
    ]
    for key in preferred_keys:
        value = control_fields.get(key)
        if value:
            formatted_value = value.replace("\n", "\n ")
            lines.append(f"{key}: {formatted_value}")
    lines.append(f"Filename: {relative_deb_path.as_posix()}")
    lines.append(f"Size: {deb_path.stat().st_size}")
    lines.append(f"MD5sum: {md5_of(deb_path)}")
    lines.append(f"SHA256: {sha256_of(deb_path)}")
    return "\n".join(lines) + "\n"


def release_text(
    distribution: str,
    component: str,
    repo_root: Path,
    packages_path: Path,
    packages_gz_path: Path,
) -> str:
    paths = [packages_path, packages_gz_path]
    md5_lines = []
    sha256_lines = []
    for path in paths:
        relative = path.as_posix()
        file_path = repo_root / path
        md5_lines.append(f" {md5_of(file_path)} {file_path.stat().st_size:>16} {relative}")
        sha256_lines.append(f" {sha256_of(file_path)} {file_path.stat().st_size:>16} {relative}")
    return "\n".join(
        [
            "Origin: AI Proxy Hub",
            "Label: AI Proxy Hub",
            f"Suite: {distribution}",
            f"Codename: {distribution}",
            f"Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %Z')}",
            "Architectures: all",
            f"Components: {component}",
            "Description: AI Proxy Hub APT repository",
            "MD5Sum:",
            *md5_lines,
            "SHA256:",
            *sha256_lines,
            "",
        ]
    )


def apt_readme(distribution: str, component: str) -> str:
    return "\n".join(
        [
            "# APT Staging for AI Proxy Hub",
            "",
            "This is an unsigned APT repository staging tree intended for release preparation and local testing.",
            "",
            "For local testing on Debian/Ubuntu you can point `sources.list.d` at it with a trusted local source, for example:",
            "",
            "```bash",
            f"deb [trusted=yes] file:/absolute/path/to/apt-repo {distribution} {component}",
            "sudo apt update",
            "sudo apt install ai-proxy-hub",
            "```",
            "",
            "Do not advertise a public `apt install` command until this repository is hosted and signed.",
            "",
        ]
    )


def sync_apt_repo(deb_path: Path, repo_root: Path, distribution: str, component: str) -> Path:
    deb_path = deb_path.resolve()
    repo_root = repo_root.resolve()
    if not deb_path.exists():
        raise FileNotFoundError(f"Missing .deb artifact: {deb_path}")
    control_fields = read_deb_control_fields(deb_path)
    package_name = control_fields.get("Package")
    if not package_name:
        raise RuntimeError("dpkg-deb -f output did not include Package")

    target_deb_path = pool_target_path(repo_root, deb_path, package_name, component)
    target_deb_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(deb_path, target_deb_path)

    packages_dir = repo_root / "dists" / distribution / component / "binary-all"
    packages_dir.mkdir(parents=True, exist_ok=True)
    relative_deb_path = target_deb_path.relative_to(repo_root)
    packages_path = packages_dir / "Packages"
    packages_content = package_entry(relative_deb_path, target_deb_path, control_fields)
    packages_path.write_text(packages_content, encoding="utf-8")
    packages_gz_path = packages_dir / "Packages.gz"
    with gzip.open(packages_gz_path, "wt", encoding="utf-8") as handle:
        handle.write(packages_content)

    release_path = repo_root / "dists" / distribution / "Release"
    release_path.parent.mkdir(parents=True, exist_ok=True)
    release_path.write_text(
        release_text(
            distribution,
            component,
            repo_root,
            packages_path.relative_to(repo_root),
            packages_gz_path.relative_to(repo_root),
        ),
        encoding="utf-8",
    )

    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        readme_path.write_text(apt_readme(distribution, component), encoding="utf-8")
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".DS_Store\n", encoding="utf-8")
    return repo_root


def main() -> None:
    args = parse_args()
    repo_root = sync_apt_repo(
        Path(args.deb),
        Path(args.repo_root),
        str(args.distribution),
        str(args.component),
    )
    print(repo_root)


if __name__ == "__main__":
    main()

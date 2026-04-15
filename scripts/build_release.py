#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
import zipfile
from pathlib import Path


APP_NAME = "AI Proxy Hub"
APP_SLUG = "ai-proxy-hub"
APP_COMMAND_ALIASES = [APP_SLUG, "aiproxyhub"]
HOMEBREW_PYTHON_FORMULA = "python"
DEFAULT_FILES = [
    "aiproxyhub.py",
    "start.py",
    "router_server.py",
    "cli_modern.py",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "MANIFEST.in",
]
DEFAULT_DIRS = [
    "ai_proxy_hub",
    "web",
    "docs",
    "examples",
]
OPTIONAL_FILES = ["LICENSE", "NOTICE", "LICENSE.md", "COPYING"]
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_version(root: Path) -> str:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    for line in pyproject.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("Could not detect version from pyproject.toml")


def release_entries(root: Path) -> list[Path]:
    entries = [root / relative for relative in DEFAULT_FILES]
    entries.extend(root / relative for relative in DEFAULT_DIRS)
    entries.extend(root / relative for relative in OPTIONAL_FILES if (root / relative).exists())
    return entries


def copy_release_entry(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, ignore=IGNORE_PATTERNS)
        return
    shutil.copy2(source, target)


def stage_release_tree(root: Path, version: str, output_dir: Path) -> Path:
    staging_root = output_dir / f"{APP_SLUG}-{version}"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    for source in release_entries(root):
        target = staging_root / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_release_entry(source, target)
    bin_dir = staging_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for command_name in APP_COMMAND_ALIASES:
        unix_launcher = bin_dir / command_name
        unix_launcher.write_text(
            "#!/usr/bin/env sh\n"
            'SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
            'cd "$SCRIPT_DIR/.."\n'
            'exec python3 -m ai_proxy_hub "$@"\n',
            encoding="utf-8",
        )
        os.chmod(unix_launcher, 0o755)
        windows_launcher = bin_dir / f"{command_name}.cmd"
        windows_launcher.write_text(
            "@echo off\r\n"
            "set SCRIPT_DIR=%~dp0\r\n"
            'pushd "%SCRIPT_DIR%.."\r\n'
            "py -3 -m ai_proxy_hub %*\r\n"
            "set EXITCODE=%ERRORLEVEL%\r\n"
            "popd\r\n"
            "exit /b %EXITCODE%\r\n",
            encoding="utf-8",
        )
    return staging_root


def build_archives(staging_root: Path, output_dir: Path) -> tuple[Path, Path]:
    tar_path = output_dir / f"{staging_root.name}.tar.gz"
    zip_path = output_dir / f"{staging_root.name}.zip"
    with tarfile.open(tar_path, "w:gz") as archive:
        archive.add(staging_root, arcname=staging_root.name)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in staging_root.rglob("*"):
            archive.write(file_path, file_path.relative_to(staging_root.parent))
    return tar_path, zip_path


def build_deb(root: Path, version: str, output_dir: Path) -> Path | None:
    if shutil.which("dpkg-deb") is None:
        return None
    package_root = output_dir / "_deb_pkg"
    if package_root.exists():
        shutil.rmtree(package_root)
    control_dir = package_root / "DEBIAN"
    control_dir.mkdir(parents=True, exist_ok=True)
    (package_root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    runtime_root = package_root / "usr" / "lib" / APP_SLUG
    runtime_root.mkdir(parents=True, exist_ok=True)
    (package_root / "usr" / "share" / "doc" / APP_SLUG).mkdir(parents=True, exist_ok=True)

    (control_dir / "control").write_text(
        textwrap.dedent(
            f"""\
            Package: {APP_SLUG}
            Version: {version}
            Section: utils
            Priority: optional
            Architecture: all
            Maintainer: weicj
            Depends: python3 (>= 3.9)
            Description: Cross-platform local AI proxy hub with CLI and Web dashboard
            """
        ),
        encoding="utf-8",
    )
    for command_name in APP_COMMAND_ALIASES:
        launcher = package_root / "usr" / "bin" / command_name
        launcher.write_text(
            "#!/usr/bin/env sh\n"
            f'cd "/usr/lib/{APP_SLUG}"\n'
            'exec python3 -m ai_proxy_hub "$@"\n',
            encoding="utf-8",
        )
        os.chmod(launcher, 0o755)
    for source in release_entries(root):
        target = runtime_root / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_release_entry(source, target)
    for doc_name in ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", *OPTIONAL_FILES]:
        source = root / doc_name
        if source.exists():
            shutil.copy2(source, package_root / "usr" / "share" / "doc" / APP_SLUG / source.name)
    deb_path = output_dir / f"{APP_SLUG}_{version}_all.deb"
    subprocess.run(["dpkg-deb", "--build", str(package_root), str(deb_path)], check=True)
    shutil.rmtree(package_root)
    return deb_path


def homebrew_formula(version: str, homepage: str, download_url: str, sha256: str, install_entries: list[str]) -> str:
    install_clause = ", ".join(f'"{entry}"' for entry in install_entries)
    lines = [
        "class AiProxyHub < Formula",
        '  desc "Cross-platform local AI proxy hub with CLI and web dashboard"',
        f'  homepage "{homepage}"',
        f'  url "{download_url}"',
        f'  sha256 "{sha256}"',
        '  license "Apache-2.0"',
        f'  depends_on "{HOMEBREW_PYTHON_FORMULA}"',
        "",
        "  def install",
        f"    libexec.install {install_clause}",
    ]
    for command_name in APP_COMMAND_ALIASES:
        lines.extend(
            [
                f'    (bin/"{command_name}").write <<~EOS',
                "      #!/bin/bash",
                '      cd "#{libexec}"',
                f'      exec "#{{Formula["{HOMEBREW_PYTHON_FORMULA}"].opt_bin}}/python3" -m ai_proxy_hub "$@"',
                "    EOS",
            ]
        )
    lines.extend(
        [
            "  end",
            "",
            "  test do",
            '    output = shell_output("#{bin}/aiproxyhub --print-paths")',
            f'    assert_match "{APP_NAME}", output',
            '    assert_match "#{libexec}/web", output',
            "  end",
            "end",
        ]
    )
    return "\n".join(lines) + "\n"


def winget_manifest(version: str, homepage: str, download_url: str, sha256: str) -> tuple[str, str, str]:
    package_id = "AIProxyHub.AIProxyHub"
    locale = textwrap.dedent(
        f"""\
        PackageIdentifier: {package_id}
        PackageVersion: {version}
        PackageLocale: en-US
        Publisher: weicj
        PublisherUrl: {homepage}
        PackageName: {APP_NAME}
        ShortDescription: Cross-platform local AI proxy hub with CLI and Web dashboard
        Moniker: ai-proxy-hub
        ManifestType: defaultLocale
        ManifestVersion: 1.9.0
        """
    )
    installer = textwrap.dedent(
        f"""\
        PackageIdentifier: {package_id}
        PackageVersion: {version}
        Installers:
          - Architecture: x64
            InstallerType: zip
            NestedInstallerType: portable
            NestedInstallerFiles:
              - RelativeFilePath: bin\\{APP_SLUG}.cmd
                PortableCommandAlias: {APP_SLUG}
              - RelativeFilePath: bin\\aiproxyhub.cmd
                PortableCommandAlias: aiproxyhub
            InstallerUrl: {download_url}
            InstallerSha256: {sha256}
        ManifestType: installer
        ManifestVersion: 1.9.0
        """
    )
    version_manifest = textwrap.dedent(
        f"""\
        PackageIdentifier: {package_id}
        PackageVersion: {version}
        DefaultLocale: en-US
        ManifestType: version
        ManifestVersion: 1.9.0
        """
    )
    return locale, installer, version_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build release artifacts for AI Proxy Hub")
    parser.add_argument("--version", help="Override release version; defaults to pyproject.toml")
    parser.add_argument("--download-base-url", help="Base download URL used when generating Homebrew and winget metadata")
    parser.add_argument("--homepage", help="Project homepage URL for generated metadata")
    parser.add_argument("--output-dir", default="dist", help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    version = args.version or project_version(root)
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tempdir:
        staging_root = stage_release_tree(root, version, Path(tempdir))
        tar_path, zip_path = build_archives(staging_root, output_dir)

    tar_sha = sha256_of(tar_path)
    zip_sha = sha256_of(zip_path)
    deb_path = build_deb(root, version, output_dir)

    print(f"tar.gz: {tar_path} sha256={tar_sha}")
    print(f"zip:    {zip_path} sha256={zip_sha}")
    if deb_path:
        print(f"deb:    {deb_path} sha256={sha256_of(deb_path)}")
    else:
        print("deb:    skipped (dpkg-deb not available)")

    if args.download_base_url:
        if not args.homepage:
            raise SystemExit("--homepage is required when --download-base-url is set")
        release_dir = output_dir / "release-metadata"
        release_dir.mkdir(parents=True, exist_ok=True)
        tar_url = args.download_base_url.rstrip("/") + f"/{tar_path.name}"
        zip_url = args.download_base_url.rstrip("/") + f"/{zip_path.name}"
        install_entries = [path.name for path in release_entries(root)]
        (release_dir / "ai-proxy-hub.rb").write_text(
            homebrew_formula(version, args.homepage, tar_url, tar_sha, install_entries),
            encoding="utf-8",
        )
        locale, installer, version_manifest = winget_manifest(version, args.homepage, zip_url, zip_sha)
        (release_dir / "winget.locale.en-US.yaml").write_text(locale, encoding="utf-8")
        (release_dir / "winget.installer.yaml").write_text(installer, encoding="utf-8")
        (release_dir / "winget.yaml").write_text(version_manifest, encoding="utf-8")
        print(f"metadata: {release_dir}")


if __name__ == "__main__":
    main()

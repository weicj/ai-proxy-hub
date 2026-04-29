#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


DEFAULT_IMAGE = "python:3.12-slim-bookworm"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build AI Proxy Hub release artifacts in a Linux container so a .deb can be produced on non-Linux hosts")
    parser.add_argument("--source-root", default=str(Path(__file__).resolve().parents[1]), help="Project root mounted into the container")
    parser.add_argument("--output-dir", default="dist-container", help="Host output directory")
    parser.add_argument("--version", help="Release version override")
    parser.add_argument("--download-base-url", help="Optional release download base URL")
    parser.add_argument("--homepage", help="Optional project homepage URL")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Container image, for example ubuntu:24.04")
    parser.add_argument("--docker-binary", default="docker", help="Container runtime executable")
    return parser.parse_args()


def container_build_command(
    docker_binary: str,
    image: str,
    source_root: Path,
    output_dir: Path,
    *,
    version: str | None = None,
    download_base_url: str | None = None,
    homepage: str | None = None,
) -> list[str]:
    build_cmd = ["python3", "/work/scripts/build_release.py", "--output-dir", "/out"]
    if version:
        build_cmd.extend(["--version", version])
    if download_base_url:
        build_cmd.extend(["--download-base-url", download_base_url])
    if homepage:
        build_cmd.extend(["--homepage", homepage])
    apt_retry_flags = "-o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30"
    shell_script = " && ".join(
        [
            "set -eu",
            "export DEBIAN_FRONTEND=noninteractive",
            "mkdir -p /out",
            "touch /out/.write-test && rm -f /out/.write-test",
            (
                "if ! command -v python3 >/dev/null 2>&1 || ! command -v dpkg-deb >/dev/null 2>&1; then "
                "if command -v apt-get >/dev/null 2>&1; then "
                f"apt-get update {apt_retry_flags} && "
                f"apt-get install -y --no-install-recommends {apt_retry_flags} python3 dpkg ca-certificates; "
                "else echo 'The selected container image must provide python3 and dpkg-deb.' >&2; exit 1; fi; "
                "fi"
            ),
            "cp -a /src/. /work",
            "cd /work",
            " ".join(build_cmd),
        ]
    )
    return [
        docker_binary,
        "run",
        "--rm",
        "-v",
        f"{source_root.resolve()}:/src:ro",
        "-v",
        f"{output_dir.resolve()}:/out",
        image,
        "/bin/sh",
        "-lc",
        shell_script,
    ]


def ensure_container_runtime_available(docker_binary: str) -> None:
    try:
        subprocess.run(
            [docker_binary, "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise SystemExit(f"Container runtime not found: {docker_binary}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Container runtime is not available: {docker_binary}. "
            "Start Docker Desktop / the Docker daemon first, or use a remote Linux host."
        ) from exc


def main() -> None:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(output_dir, 0o777)
    except PermissionError:
        pass
    ensure_container_runtime_available(str(args.docker_binary))
    command = container_build_command(
        str(args.docker_binary),
        str(args.image),
        source_root,
        output_dir,
        version=str(args.version) if args.version else None,
        download_base_url=str(args.download_base_url) if args.download_base_url else None,
        homepage=str(args.homepage) if args.homepage else None,
    )
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple release smoke test on a remote Linux host over SSH")
    parser.add_argument("--ssh", required=True, help="SSH target, for example user@host")
    parser.add_argument("--artifact", required=True, help="Local .tar.gz release artifact to upload and test")
    parser.add_argument("--remote-dir", default="/tmp/ai-proxy-hub-smoke", help="Remote working directory")
    parser.add_argument("--python", default="python3", help="Remote Python executable")
    return parser.parse_args()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    args = parse_args()
    artifact = Path(args.artifact).resolve()
    if not artifact.exists():
        raise FileNotFoundError(f"Missing artifact: {artifact}")
    remote_artifact = f"{args.remote_dir}/{artifact.name}"
    quoted_remote_dir = shlex.quote(args.remote_dir)
    quoted_artifact_name = shlex.quote(artifact.name)
    run(["ssh", args.ssh, f"rm -rf {quoted_remote_dir} && mkdir -p {quoted_remote_dir}"])
    run(["scp", str(artifact), f"{args.ssh}:{remote_artifact}"])
    remote_script = (
        "set -eu; "
        f"cd {quoted_remote_dir}; "
        f"tar -xzf {quoted_artifact_name}; "
        "root_dir=$(find . -maxdepth 1 -type d -name 'ai-proxy-hub-*' | head -n 1); "
        "test -n \"$root_dir\"; "
        f"cd \"$root_dir\"; "
        f"{args.python} -m ai_proxy_hub --version; "
        f"{args.python} -m ai_proxy_hub --print-paths"
    )
    run(["ssh", args.ssh, remote_script])


if __name__ == "__main__":
    main()

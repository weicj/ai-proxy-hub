#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import textwrap
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple release smoke test on a remote Linux host over SSH")
    parser.add_argument("--ssh", required=True, help="SSH target, for example user@host")
    parser.add_argument("--artifact", required=True, help="Local .tar.gz release artifact to upload and test")
    parser.add_argument("--remote-dir", default="/tmp/ai-proxy-hub-smoke", help="Remote working directory")
    parser.add_argument("--python", default="python3", help="Remote Python executable")
    parser.add_argument("--identity-file", help="SSH identity file to use for both ssh and scp")
    parser.add_argument(
        "--ssh-option",
        action="append",
        default=[],
        help="Additional SSH option passed as -o <value>. Can be supplied multiple times.",
    )
    parser.add_argument("--bind-host", default="127.0.0.1", help="Remote bind host used for runtime health check")
    parser.add_argument("--runtime-port", type=int, default=18987, help="Remote port used for runtime health check")
    parser.add_argument(
        "--skip-runtime-check",
        action="store_true",
        help="Only verify extraction and metadata commands, without starting the remote service",
    )
    return parser.parse_args()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def build_ssh_common_args(identity_file: str | None, ssh_options: list[str]) -> list[str]:
    args: list[str] = []
    normalized_options = list(ssh_options)
    if identity_file:
        args.extend(["-i", str(Path(identity_file).expanduser().resolve())])
        if not any(option.lower().startswith("identitiesonly=") for option in normalized_options):
            normalized_options.insert(0, "IdentitiesOnly=yes")
    for option in normalized_options:
        args.extend(["-o", option])
    return args


def build_remote_health_script(bind_host: str, runtime_port: int) -> str:
    return textwrap.dedent(
        f"""
        import json
        import time
        import urllib.request

        url = "http://{bind_host}:{runtime_port}/health"
        last_error = None
        for _ in range(30):
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") != "ok":
                    raise SystemExit(f"unexpected health payload: {{payload}}")
                print(json.dumps(payload, ensure_ascii=True))
                break
            except Exception as exc:  # pragma: no cover - exercised via remote smoke
                last_error = exc
                time.sleep(0.5)
        else:
            raise SystemExit(f"health check failed for {{url}}: {{last_error}}")
        """
    ).strip()


def build_remote_script(args: argparse.Namespace, artifact_name: str) -> str:
    quoted_artifact_name = shlex.quote(artifact_name)
    quoted_python = shlex.quote(args.python)
    if args.skip_runtime_check:
        runtime_check = ""
    else:
        health_script = build_remote_health_script(args.bind_host, args.runtime_port)
        runtime_check = "\n".join(
            [
                'smoke_log="$PWD/.remote-smoke-server.log"',
                f'{quoted_python} -m ai_proxy_hub --serve --host {shlex.quote(args.bind_host)} --port {args.runtime_port} >"$smoke_log" 2>&1 &',
                "server_pid=$!",
                "cleanup() {",
                '  kill "$server_pid" >/dev/null 2>&1 || true',
                '  wait "$server_pid" >/dev/null 2>&1 || true',
                "}",
                "trap cleanup EXIT INT TERM",
                f"{quoted_python} - <<'PY'",
                health_script,
                "PY",
            ]
        )
    parts = [
        "set -eu",
        f"tar -xzf {quoted_artifact_name}",
        "root_dir=$(find . -maxdepth 1 -type d -name 'ai-proxy-hub-*' | head -n 1)",
        'test -n "$root_dir"',
        'cd "$root_dir"',
        f"{quoted_python} -m ai_proxy_hub --version",
        f"{quoted_python} -m ai_proxy_hub --print-paths",
    ]
    if runtime_check:
        parts.append(runtime_check)
    return "\n".join(parts)


def main() -> None:
    args = parse_args()
    artifact = Path(args.artifact).resolve()
    if not artifact.exists():
        raise FileNotFoundError(f"Missing artifact: {artifact}")
    remote_artifact = f"{args.remote_dir}/{artifact.name}"
    ssh_common_args = build_ssh_common_args(args.identity_file, args.ssh_option)
    remote_script = build_remote_script(args, artifact.name)
    quoted_remote_dir = shlex.quote(args.remote_dir)
    run(["ssh", *ssh_common_args, args.ssh, f"rm -rf {quoted_remote_dir} && mkdir -p {quoted_remote_dir}"])
    run(["scp", *ssh_common_args, str(artifact), f"{args.ssh}:{remote_artifact}"])
    run(["ssh", *ssh_common_args, args.ssh, f"cd {quoted_remote_dir} && {remote_script}"])


if __name__ == "__main__":
    main()

from __future__ import annotations

import errno
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import ADDRESS_IN_USE_ERRNOS
from .utils import safe_int


def is_address_in_use_error(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    if getattr(exc, "errno", None) in ADDRESS_IN_USE_ERRNOS:
        return True
    return "address already in use" in str(exc).lower()


def _read_process_command(pid: int) -> str:
    if pid <= 0 or os.name == "nt":
        return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return str(result.stdout or "").strip()


def _lsof_listening_rows(port: int) -> List[str]:
    lsof_path = shutil.which("lsof") or "/usr/sbin/lsof"
    if not lsof_path or not Path(lsof_path).exists():
        return []
    try:
        result = subprocess.run(
            [lsof_path, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpnc"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return result.stdout.splitlines()


def listening_pids(port: int) -> List[int]:
    rows = _lsof_listening_rows(port)
    pids: List[int] = []
    for raw_line in rows:
        if not raw_line.startswith("p"):
            continue
        pid = safe_int(raw_line[1:].strip(), 0)
        if pid > 0 and pid not in pids:
            pids.append(pid)
    if pids:
        return pids

    if os.name == "nt":
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE)
            for line in result.stdout.splitlines():
                match = pattern.match(line)
                if not match:
                    continue
                pid = safe_int(match.group(1), 0)
                if pid > 0 and pid not in pids:
                    pids.append(pid)
        except (OSError, subprocess.SubprocessError):
            pass
    return pids


def find_listening_process(port: int) -> Optional[Dict[str, Any]]:
    rows = _lsof_listening_rows(port)
    if rows:
        current: Dict[str, Any] = {}
        for raw_line in rows:
            if not raw_line:
                continue
            prefix, value = raw_line[:1], raw_line[1:].strip()
            if prefix == "p":
                if current.get("pid"):
                    if not current.get("command"):
                        current["command"] = _read_process_command(int(current["pid"]))
                    return current
                current = {"pid": safe_int(value, 0)}
            elif prefix == "c":
                current["command"] = value
            elif prefix == "n":
                current["endpoint"] = value
        if current.get("pid"):
            if not current.get("command"):
                current["command"] = _read_process_command(int(current["pid"]))
            return current

    pids = listening_pids(port)
    if pids:
        pid = int(pids[0])
        return {"pid": pid, "command": _read_process_command(pid), "endpoint": f"*:{port}"}
    return None


def terminate_process(pid: int) -> Dict[str, Any]:
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip() or "taskkill failed"
                return {"ok": False, "message": message}
            return {"ok": True}
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError as exc:
                if exc.errno == errno.ESRCH:
                    return {"ok": True}
                break
            time.sleep(0.1)
        return {"ok": False, "message": "process did not exit after SIGTERM"}
    except OSError as exc:
        return {"ok": False, "message": str(exc)}


def terminate_listening_processes(port: int) -> Dict[str, Any]:
    pids = listening_pids(port)
    if not pids:
        return {"ok": False, "message": "process_not_found", "terminated_pids": []}

    terminated: List[int] = []
    errors: List[str] = []
    for pid in pids:
        result = terminate_process(pid)
        if result.get("ok"):
            terminated.append(pid)
        else:
            errors.append(str(result.get("message") or f"terminate {pid} failed"))

    deadline = time.time() + 3
    while time.time() < deadline:
        if not listening_pids(port):
            return {
                "ok": True,
                "terminated_pids": terminated,
                "message": "terminated",
            }
        time.sleep(0.1)

    if terminated and not listening_pids(port):
        return {"ok": True, "terminated_pids": terminated, "message": "terminated"}
    if terminated:
        return {
            "ok": False,
            "terminated_pids": terminated,
            "message": "; ".join(errors) if errors else "port_still_in_use",
        }
    return {"ok": False, "terminated_pids": [], "message": "; ".join(errors) if errors else "process_not_found"}


__all__ = [
    "find_listening_process",
    "is_address_in_use_error",
    "listening_pids",
    "terminate_listening_processes",
    "terminate_process",
]

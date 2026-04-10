from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def platform_family() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    items: List[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        items.append(path)
    return items


def first_env_value(*names: str, env: Optional[Dict[str, str]] = None) -> str:
    source = dict(os.environ) if env is None else env
    for name in names:
        value = str(source.get(name) or "").strip()
        if value:
            return value
    return ""


__all__ = [
    "first_env_value",
    "now_iso",
    "platform_family",
    "safe_float",
    "safe_int",
    "unique_paths",
]

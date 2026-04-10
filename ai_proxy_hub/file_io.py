from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import DEFAULT_RUNTIME_STATE_SUFFIX


def _normalize_config(raw: Any) -> Dict[str, Any]:
    from .config_logic import normalize_config

    return normalize_config(raw)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    owner_uid: Optional[int] = None
    owner_gid: Optional[int] = None
    mode = 0o600
    probe = path
    while True:
        if probe.exists():
            stat_result = probe.stat()
            owner_uid = stat_result.st_uid
            owner_gid = stat_result.st_gid
            if probe == path:
                mode = stat_result.st_mode & 0o777
            break
        if probe.parent == probe:
            break
        probe = probe.parent

    temp_path = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    except PermissionError:
        if path.exists() and os.access(path, os.W_OK):
            with path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            try:
                os.chmod(path, mode)
            except (PermissionError, NotImplementedError, OSError):
                pass
            if owner_uid is not None and owner_gid is not None and hasattr(os, "chown"):
                try:
                    os.chown(path, owner_uid, owner_gid)
                except (PermissionError, NotImplementedError, OSError):
                    pass
            return
        raise
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
        try:
            os.chmod(path, mode)
        except (PermissionError, NotImplementedError, OSError):
            pass
        if owner_uid is not None and owner_gid is not None and hasattr(os, "chown"):
            try:
                os.chown(path, owner_uid, owner_gid)
            except (PermissionError, NotImplementedError, OSError):
                pass
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def seed_config_path(config_path: Path, legacy_path: Optional[Path] = None) -> None:
    if config_path.exists():
        return
    if legacy_path and legacy_path != config_path and legacy_path.exists():
        try:
            with legacy_path.open("r", encoding="utf-8") as handle:
                legacy_raw = json.load(handle)
            write_json(config_path, _normalize_config(legacy_raw))
            return
        except (OSError, json.JSONDecodeError, PermissionError):
            pass
    write_json(config_path, _normalize_config({}))


def load_config_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        config = _normalize_config({})
        write_json(path, config)
        return config
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    config = _normalize_config(raw)
    if config != raw:
        write_json(path, config)
    return config


def load_optional_json_file(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, PermissionError, json.JSONDecodeError):
        return {}


def runtime_state_path(config_path: Path) -> Path:
    return config_path.with_name(f"{config_path.stem}{DEFAULT_RUNTIME_STATE_SUFFIX}")


__all__ = [
    "load_config_file",
    "load_optional_json_file",
    "runtime_state_path",
    "seed_config_path",
    "write_json",
]

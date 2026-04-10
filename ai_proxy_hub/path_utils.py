from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Dict, List, Optional

from .constants import (
    APP_NAME,
    APP_SLUG,
    DEFAULT_CONFIG_FILENAME,
    LEGACY_APP_NAMES,
    LEGACY_APP_SLUGS,
)
from .utils import platform_family, unique_paths


def app_config_dir(*, home: Optional[Path] = None, env: Optional[Dict[str, str]] = None, family: Optional[str] = None) -> Path:
    env = dict(os.environ) if env is None else env
    home = (home or Path.home()).expanduser()
    family = family or platform_family()
    if family == "windows":
        appdata = str(env.get("APPDATA") or env.get("LOCALAPPDATA") or "").strip()
        base = Path(appdata) if appdata else (home / "AppData" / "Roaming")
        return base / APP_NAME
    if family == "macos":
        return home / "Library" / "Application Support" / APP_NAME
    xdg_root = str(env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg_root:
        return Path(xdg_root).expanduser() / APP_SLUG
    return home / ".config" / APP_SLUG


def app_config_dir_candidates(*, home: Optional[Path] = None, env: Optional[Dict[str, str]] = None, family: Optional[str] = None) -> List[Path]:
    env = dict(os.environ) if env is None else env
    home = (home or Path.home()).expanduser()
    family = family or platform_family()
    candidates = [app_config_dir(home=home, env=env, family=family)]
    if family in {"macos", "windows"}:
        candidates.extend(
            [
                home / ".config" / APP_SLUG,
                home / f".{APP_SLUG}",
            ]
        )
    else:
        candidates.append(home / f".{APP_SLUG}")
    return unique_paths(path.expanduser() for path in candidates)


def directory_supports_user_writes(path: Path) -> bool:
    path = path.expanduser()
    if path.exists() and hasattr(os, "getuid"):
        try:
            if path.stat().st_uid != os.getuid():
                return False
        except OSError:
            return False
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    probe_path = path / f".{APP_SLUG}-write-test-{os.getpid()}-{secrets.token_hex(4)}"
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


def preferred_app_config_dir(*, home: Optional[Path] = None, env: Optional[Dict[str, str]] = None, family: Optional[str] = None) -> Path:
    candidates = app_config_dir_candidates(home=home, env=env, family=family)
    for candidate in candidates:
        if directory_supports_user_writes(candidate):
            return candidate
    return candidates[0]


def legacy_config_locations(base_dir: Path, *, home: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> List[Path]:
    home = (home or Path.home()).expanduser()
    env = dict(os.environ) if env is None else env
    paths = [(base_dir / DEFAULT_CONFIG_FILENAME).resolve()]
    for slug in (APP_SLUG, *LEGACY_APP_SLUGS):
        paths.append(home / ".config" / slug / DEFAULT_CONFIG_FILENAME)
        paths.append(home / f".{slug}" / DEFAULT_CONFIG_FILENAME)
    for app_name in LEGACY_APP_NAMES:
        paths.append(home / "Library" / "Application Support" / app_name / DEFAULT_CONFIG_FILENAME)
    appdata = str(env.get("APPDATA") or env.get("LOCALAPPDATA") or "").strip()
    if appdata:
        for app_name in LEGACY_APP_NAMES:
            paths.append(Path(appdata).expanduser() / app_name / DEFAULT_CONFIG_FILENAME)
    else:
        for app_name in LEGACY_APP_NAMES:
            paths.append(home / "AppData" / "Roaming" / app_name / DEFAULT_CONFIG_FILENAME)
    return unique_paths(path.expanduser() for path in paths)


__all__ = [
    "app_config_dir",
    "app_config_dir_candidates",
    "directory_supports_user_writes",
    "legacy_config_locations",
    "preferred_app_config_dir",
]

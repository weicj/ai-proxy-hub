from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from .constants import (
    APP_SLUG,
    DEFAULT_CLAUDE_SWITCH_BACKUP_FILENAME,
    DEFAULT_CODEX_SWITCH_BACKUP_FILENAME,
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_GEMINI_SWITCH_BACKUP_FILENAME,
    LEGACY_APP_SLUGS,
    LEGACY_STATIC_DIR_ENV_VARS,
    STATIC_DIR_ENV_VAR,
)
from .path_utils import preferred_app_config_dir
from .utils import first_env_value, unique_paths


def default_user_config_path() -> Path:
    return preferred_app_config_dir() / DEFAULT_CONFIG_FILENAME


def legacy_user_config_path() -> Path:
    return (Path.home() / ".config" / LEGACY_APP_SLUGS[0] / DEFAULT_CONFIG_FILENAME).expanduser()


def codex_cli_config_path() -> Path:
    codex_home = str(os.environ.get("CODEX_HOME") or "").strip()
    base = Path(codex_home).expanduser() if codex_home else (Path.home() / ".codex").expanduser()
    return base / "config.toml"


def codex_cli_auth_path() -> Path:
    return codex_cli_config_path().with_name("auth.json")


def codex_switch_backup_path() -> Path:
    return preferred_app_config_dir() / DEFAULT_CODEX_SWITCH_BACKUP_FILENAME


def claude_cli_settings_path() -> Path:
    return (Path.home() / ".claude" / "settings.json").expanduser()


def claude_switch_backup_path() -> Path:
    return preferred_app_config_dir() / DEFAULT_CLAUDE_SWITCH_BACKUP_FILENAME


def gemini_cli_settings_path() -> Path:
    return (Path.home() / ".gemini" / "settings.json").expanduser()


def gemini_cli_auth_path() -> Path:
    xdg_root = str(os.environ.get("XDG_CONFIG_HOME") or "").strip()
    if xdg_root:
        return (Path(xdg_root).expanduser() / "gemini-cli" / "auth.json").expanduser()
    return (Path.home() / ".config" / "gemini-cli" / "auth.json").expanduser()


def gemini_switch_backup_path() -> Path:
    return preferred_app_config_dir() / DEFAULT_GEMINI_SWITCH_BACKUP_FILENAME


def resolve_static_dir(base_dir: Path) -> Path:
    candidates: List[Path] = []
    override = first_env_value(STATIC_DIR_ENV_VAR, *LEGACY_STATIC_DIR_ENV_VARS)
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append((base_dir / "web").resolve())
    share_relatives = [Path("share") / APP_SLUG / "web"]
    for legacy_slug in LEGACY_APP_SLUGS:
        share_relatives.append(Path("share") / legacy_slug / "web")
    for prefix in unique_paths(Path(item).expanduser() for item in [sys.prefix, sys.base_prefix]):
        for share_relative in share_relatives:
            candidates.append((prefix / share_relative).resolve())
    for candidate in unique_paths(candidates):
        if (candidate / "index.html").exists():
            return candidate
    return candidates[0]


__all__ = [
    "claude_cli_settings_path",
    "claude_switch_backup_path",
    "codex_cli_auth_path",
    "codex_cli_config_path",
    "codex_switch_backup_path",
    "default_user_config_path",
    "gemini_cli_auth_path",
    "gemini_cli_settings_path",
    "gemini_switch_backup_path",
    "legacy_user_config_path",
    "resolve_static_dir",
]

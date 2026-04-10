from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .app_paths import claude_cli_settings_path, claude_switch_backup_path
from .client_switch_common import (
    _binding_status_payload,
    _clone_json,
    _restore_json_backup,
    _write_backup_once,
)
from .file_io import write_json


def get_claude_cli_binding_status(
    local_base_url: str,
    local_api_key: str,
    *,
    settings_path: Optional[Path] = None,
    service_state: str = "running",
) -> Dict[str, Any]:
    settings_path = (settings_path or claude_cli_settings_path()).expanduser()
    try:
        if not settings_path.exists():
            return {
                "state": "not_switched",
                "message": f"Missing config: {settings_path}",
                "provider": "anthropic",
                "base_url": "",
                "dashboard_url": "",
                "auth_matches": False,
            }
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        env = settings.get("env") if isinstance(settings, dict) else {}
        if not isinstance(env, dict):
            env = {}
        active_base_url = str(env.get("ANTHROPIC_BASE_URL") or "").strip()
        token = str(env.get("ANTHROPIC_AUTH_TOKEN") or env.get("ANTHROPIC_API_KEY") or "").strip()
        auth_matches = token == local_api_key
        return _binding_status_payload("anthropic", active_base_url, local_base_url, auth_matches, service_state)
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"state": "error", "message": str(exc), "provider": "anthropic", "base_url": "", "dashboard_url": "", "auth_matches": False}


def switch_claude_cli_to_local_hub(
    local_base_url: str,
    local_api_key: str,
    *,
    settings_path: Optional[Path] = None,
    backup_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        settings_path = (settings_path or claude_cli_settings_path()).expanduser()
        backup_path = (backup_path or claude_switch_backup_path()).expanduser()
        if not settings_path.exists():
            return {"ok": False, "message": f"Claude config not found: {settings_path}"}

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            settings = {}
        _write_backup_once(
            backup_path,
            {
                "settings_path": str(settings_path),
                "settings_json": settings,
            },
        )

        env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        env = _clone_json(env)
        env["ANTHROPIC_BASE_URL"] = local_base_url
        env["ANTHROPIC_AUTH_TOKEN"] = local_api_key
        env["ANTHROPIC_API_KEY"] = local_api_key
        settings["env"] = env
        write_json(settings_path, settings)
        return {"ok": True, "provider": "anthropic"}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": str(exc)}


def restore_claude_cli_from_backup(*, backup_path: Optional[Path] = None) -> Dict[str, Any]:
    try:
        backup_path = (backup_path or claude_switch_backup_path()).expanduser()
        return _restore_json_backup(backup_path, path_key="settings_path", payload_key="settings_json")
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": str(exc)}

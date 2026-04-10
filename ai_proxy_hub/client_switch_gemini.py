from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .app_paths import gemini_cli_auth_path, gemini_switch_backup_path
from .client_switch_common import (
    _binding_status_payload,
    _restore_json_backup,
    _write_backup_once,
)
from .file_io import write_json
from .network import dashboard_url_from_api_base_url


def get_gemini_cli_binding_status(
    local_base_url: str,
    local_api_key: str,
    *,
    auth_path: Optional[Path] = None,
    service_state: str = "running",
) -> Dict[str, Any]:
    auth_path = (auth_path or gemini_cli_auth_path()).expanduser()
    try:
        if not auth_path.exists():
            return {
                "state": "not_switched",
                "message": f"Missing auth: {auth_path}",
                "provider": "gemini",
                "base_url": "",
                "dashboard_url": "",
                "auth_matches": False,
            }
        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
        active_base_url = str(auth_data.get("GOOGLE_GEMINI_BASE_URL") or "").strip()
        auth_matches = str(auth_data.get("GEMINI_API_KEY") or "").strip() == local_api_key
        return _binding_status_payload("gemini", active_base_url, local_base_url, auth_matches, service_state)
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"state": "error", "message": str(exc), "provider": "gemini", "base_url": "", "dashboard_url": "", "auth_matches": False}


def get_local_llm_cli_binding_status(
    local_base_url: str,
    local_api_key: str,
    *,
    service_state: str = "running",
) -> Dict[str, Any]:
    state = "external" if service_state == "external" else "switched" if service_state == "running" else "not_switched" if service_state == "stopped" else "error"
    return {
        "state": state,
        "message": "",
        "provider": "local_llm",
        "base_url": local_base_url,
        "dashboard_url": dashboard_url_from_api_base_url(local_base_url) if local_base_url else "",
        "auth_matches": True,
    }


def switch_gemini_cli_to_local_hub(
    local_base_url: str,
    local_api_key: str,
    *,
    auth_path: Optional[Path] = None,
    backup_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        auth_path = (auth_path or gemini_cli_auth_path()).expanduser()
        backup_path = (backup_path or gemini_switch_backup_path()).expanduser()
        if not auth_path.exists():
            return {"ok": False, "message": f"Gemini auth not found: {auth_path}"}

        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
        if not isinstance(auth_data, dict):
            auth_data = {}
        _write_backup_once(
            backup_path,
            {
                "auth_path": str(auth_path),
                "auth_json": auth_data,
            },
        )

        auth_data["GOOGLE_GEMINI_BASE_URL"] = local_base_url
        auth_data["GEMINI_API_KEY"] = local_api_key
        write_json(auth_path, auth_data)
        return {"ok": True, "provider": "gemini"}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": str(exc)}


def restore_gemini_cli_from_backup(*, backup_path: Optional[Path] = None) -> Dict[str, Any]:
    try:
        backup_path = (backup_path or gemini_switch_backup_path()).expanduser()
        return _restore_json_backup(backup_path, path_key="auth_path", payload_key="auth_json")
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": str(exc)}

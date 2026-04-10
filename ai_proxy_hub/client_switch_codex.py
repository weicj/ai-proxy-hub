from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .app_paths import (
    codex_cli_auth_path,
    codex_cli_config_path,
    codex_switch_backup_path,
)
from .client_switch_common import (
    _binding_status_payload,
    _safe_remove,
    _write_backup_once,
)
from .file_io import write_json


def upsert_toml_key(text: str, key: str, value_literal: str, *, section: Optional[str] = None) -> str:
    key_line = f'{key} = {value_literal}'
    if section is None:
        pattern = re.compile(rf'(?m)^({re.escape(key)}\s*=\s*).*$')
        if pattern.search(text):
            return pattern.sub(key_line, text, count=1)
        first_section = re.search(r'(?m)^\[', text)
        if first_section:
            return text[:first_section.start()] + key_line + "\n" + text[first_section.start():]
        suffix = "" if text.endswith("\n") else "\n"
        return text + suffix + key_line + "\n"

    section_pattern = re.compile(rf'(?ms)^(\[{re.escape(section)}\]\n)(.*?)(?=^\[|\Z)')
    match = section_pattern.search(text)
    if not match:
        suffix = "" if text.endswith("\n") else "\n"
        return text + suffix + f'[{section}]\n{key_line}\n'

    header, body = match.group(1), match.group(2)
    body_pattern = re.compile(rf'(?m)^({re.escape(key)}\s*=\s*).*$')
    if body_pattern.search(body):
        new_body = body_pattern.sub(key_line, body, count=1)
    else:
        body_suffix = "" if body.endswith("\n") or body == "" else "\n"
        new_body = body + body_suffix + key_line + "\n"
    return text[:match.start()] + header + new_body + text[match.end():]


def detect_active_codex_provider(config_text: str) -> Optional[str]:
    match = re.search(r'(?m)^model_provider\s*=\s*"([^"]+)"', config_text)
    if match:
        return match.group(1).strip()
    return None


def read_toml_string_value(text: str, key: str, *, section: Optional[str] = None) -> Optional[str]:
    if section is None:
        match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]*)"', text)
        return match.group(1) if match else None
    section_pattern = re.compile(rf'(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)')
    section_match = section_pattern.search(text)
    if not section_match:
        return None
    match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]*)"', section_match.group(1))
    return match.group(1) if match else None


def get_codex_cli_binding_status(
    local_base_url: str,
    local_api_key: str,
    *,
    config_path: Optional[Path] = None,
    auth_path: Optional[Path] = None,
    service_state: str = "running",
) -> Dict[str, Any]:
    config_path = (config_path or codex_cli_config_path()).expanduser()
    auth_path = (auth_path or codex_cli_auth_path()).expanduser()
    try:
        if not config_path.exists():
            return {"state": "not_switched", "message": f"Missing config: {config_path}", "provider": "", "base_url": "", "dashboard_url": "", "auth_matches": False}
        if not auth_path.exists():
            return {"state": "not_switched", "message": f"Missing auth: {auth_path}", "provider": "", "base_url": "", "dashboard_url": "", "auth_matches": False}
        config_text = config_path.read_text(encoding="utf-8")
        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))
        active_provider = detect_active_codex_provider(config_text)
        if not active_provider:
            return {"state": "error", "message": "model_provider missing", "provider": "", "base_url": "", "auth_matches": False}
        active_base_url = read_toml_string_value(config_text, "base_url", section=f"model_providers.{active_provider}") or ""
        auth_matches = str(auth_data.get("OPENAI_API_KEY") or "") == local_api_key
        return _binding_status_payload(active_provider, active_base_url, local_base_url, auth_matches, service_state)
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"state": "error", "message": str(exc), "provider": "", "base_url": "", "dashboard_url": "", "auth_matches": False}


def switch_codex_cli_to_local_hub(
    local_base_url: str,
    local_api_key: str,
    *,
    config_path: Optional[Path] = None,
    auth_path: Optional[Path] = None,
    backup_path: Optional[Path] = None,
) -> Dict[str, Any]:
    try:
        config_path = (config_path or codex_cli_config_path()).expanduser()
        auth_path = (auth_path or codex_cli_auth_path()).expanduser()
        backup_path = (backup_path or codex_switch_backup_path()).expanduser()

        if not config_path.exists():
            return {"ok": False, "message": f"Codex config not found: {config_path}"}
        if not auth_path.exists():
            return {"ok": False, "message": f"Codex auth not found: {auth_path}"}

        config_text = config_path.read_text(encoding="utf-8")
        active_provider = detect_active_codex_provider(config_text)
        if not active_provider:
            return {"ok": False, "message": "Could not detect model_provider in ~/.codex/config.toml"}

        auth_data = json.loads(auth_path.read_text(encoding="utf-8"))

        _write_backup_once(
            backup_path,
            {
                "config_path": str(config_path),
                "auth_path": str(auth_path),
                "config_text": config_text,
                "auth_json": auth_data,
                "active_provider": active_provider,
            },
        )

        section_name = f"model_providers.{active_provider}"
        updated_config = config_text
        updated_config = upsert_toml_key(updated_config, "base_url", json.dumps(local_base_url), section=section_name)
        updated_config = upsert_toml_key(updated_config, "wire_api", json.dumps("responses"), section=section_name)
        updated_config = upsert_toml_key(updated_config, "requires_openai_auth", "true", section=section_name)
        config_path.write_text(updated_config, encoding="utf-8")

        auth_data["OPENAI_API_KEY"] = local_api_key
        auth_data["auth_mode"] = "apikey"
        write_json(auth_path, auth_data)
        return {"ok": True, "provider": active_provider}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": str(exc)}


def restore_codex_cli_from_backup(*, backup_path: Optional[Path] = None) -> Dict[str, Any]:
    try:
        backup_path = (backup_path or codex_switch_backup_path()).expanduser()
        if not backup_path.exists():
            return {"ok": True, "restored": False}
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        config_path = Path(backup["config_path"]).expanduser()
        auth_path = Path(backup["auth_path"]).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(str(backup["config_text"]), encoding="utf-8")
        write_json(auth_path, backup["auth_json"])
        _safe_remove(backup_path)
        return {"ok": True, "restored": True}
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": str(exc)}

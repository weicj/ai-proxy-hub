from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from .file_io import write_json
from .network import dashboard_url_from_api_base_url
from .utils import now_iso


def _router_override(name: str, fallback):
    router_module = sys.modules.get("router_server")
    if router_module is None:
        return fallback
    candidate = getattr(router_module, name, None)
    if candidate is None or candidate is fallback:
        return fallback
    return candidate


def _clone_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _binding_state(active_base_url: str, local_base_url: str, auth_matches: bool, service_state: str) -> str:
    if active_base_url != local_base_url:
        return "not_switched"
    if not auth_matches:
        return "error"
    if service_state == "running":
        return "switched"
    if service_state == "external":
        return "external"
    return "error"


def _binding_status_payload(
    provider: str,
    active_base_url: str,
    local_base_url: str,
    auth_matches: bool,
    service_state: str,
) -> Dict[str, Any]:
    return {
        "state": _binding_state(active_base_url, local_base_url, auth_matches, service_state),
        "message": "",
        "provider": provider,
        "base_url": active_base_url,
        "dashboard_url": dashboard_url_from_api_base_url(active_base_url) if active_base_url else "",
        "auth_matches": auth_matches,
    }


def _safe_remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _write_backup_once(backup_path: Path, payload: Dict[str, Any]) -> None:
    if backup_path.exists():
        return
    write_json(backup_path, {**payload, "saved_at": now_iso()})


def _restore_json_backup(backup_path: Path, *, path_key: str, payload_key: str) -> Dict[str, Any]:
    if not backup_path.exists():
        return {"ok": True, "restored": False}
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    target_path = Path(backup[path_key]).expanduser()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(target_path, backup[payload_key])
    _safe_remove(backup_path)
    return {"ok": True, "restored": True}


def _client_handler(client_id: str, handlers: Dict[str, Any]):
    return handlers.get(str(client_id or "").strip().lower())

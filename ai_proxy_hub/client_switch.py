from __future__ import annotations

from typing import Dict, Optional

from .client_switch_claude import (
    get_claude_cli_binding_status,
    restore_claude_cli_from_backup,
    switch_claude_cli_to_local_hub,
)
from .client_switch_codex import (
    detect_active_codex_provider,
    get_codex_cli_binding_status,
    read_toml_string_value,
    restore_codex_cli_from_backup,
    switch_codex_cli_to_local_hub,
    upsert_toml_key,
)
from .client_switch_common import _client_handler, _router_override
from .client_switch_gemini import (
    get_gemini_cli_binding_status,
    get_local_llm_cli_binding_status,
    restore_gemini_cli_from_backup,
    switch_gemini_cli_to_local_hub,
)
from .network import client_protocol_id
from .protocols import normalize_upstream_protocol


def collect_client_binding_statuses(
    runtime_base_urls: Dict[str, str],
    local_api_key: str,
    *,
    service_state: str,
    service_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    active_protocols = {
        normalize_upstream_protocol(protocol)
        for protocol in (service_details or {}).get("active_protocols") or []
    }
    service_owner = str((service_details or {}).get("owner") or "")

    def client_service_state(client_id: str) -> str:
        protocol = client_protocol_id(client_id)
        if active_protocols:
            if protocol in active_protocols:
                return "external" if service_owner == "external" else "running"
            if service_state == "partial" or bool((service_details or {}).get("partially_started")):
                return "stopped"
        return service_state

    codex_status = _router_override("get_codex_cli_binding_status", get_codex_cli_binding_status)
    claude_status = _router_override("get_claude_cli_binding_status", get_claude_cli_binding_status)
    gemini_status = _router_override("get_gemini_cli_binding_status", get_gemini_cli_binding_status)
    local_llm_status = _router_override("get_local_llm_cli_binding_status", get_local_llm_cli_binding_status)

    statuses = {
        "codex": codex_status(runtime_base_urls["codex"], local_api_key, service_state=client_service_state("codex")),
        "claude": claude_status(runtime_base_urls["claude"], local_api_key, service_state=client_service_state("claude")),
        "gemini": gemini_status(runtime_base_urls["gemini"], local_api_key, service_state=client_service_state("gemini")),
    }
    local_llm_base_url = str(runtime_base_urls.get("local_llm") or "").strip()
    if local_llm_base_url:
        statuses["local_llm"] = local_llm_status(local_llm_base_url, local_api_key, service_state=client_service_state("local_llm"))
    return statuses


def switch_all_clients_to_local_hub(runtime_base_urls: Dict[str, str], local_api_key: str) -> Dict[str, Dict[str, Any]]:
    codex_switch = _router_override("switch_codex_cli_to_local_hub", switch_codex_cli_to_local_hub)
    claude_switch = _router_override("switch_claude_cli_to_local_hub", switch_claude_cli_to_local_hub)
    gemini_switch = _router_override("switch_gemini_cli_to_local_hub", switch_gemini_cli_to_local_hub)
    return {
        "codex": codex_switch(runtime_base_urls["codex"], local_api_key),
        "claude": claude_switch(runtime_base_urls["claude"], local_api_key),
        "gemini": gemini_switch(runtime_base_urls["gemini"], local_api_key),
    }


def restore_all_clients_from_backup() -> Dict[str, Dict[str, Any]]:
    codex_restore = _router_override("restore_codex_cli_from_backup", restore_codex_cli_from_backup)
    claude_restore = _router_override("restore_claude_cli_from_backup", restore_claude_cli_from_backup)
    gemini_restore = _router_override("restore_gemini_cli_from_backup", restore_gemini_cli_from_backup)
    return {
        "codex": codex_restore(),
        "claude": claude_restore(),
        "gemini": gemini_restore(),
    }


def switch_client_to_local_hub(client_id: str, runtime_base_urls: Dict[str, str], local_api_key: str) -> Dict[str, Any]:
    normalized = str(client_id or "").strip().lower()
    handler = _client_handler(
        normalized,
        {
            "codex": lambda: _router_override("switch_codex_cli_to_local_hub", switch_codex_cli_to_local_hub)(runtime_base_urls["codex"], local_api_key),
            "claude": lambda: _router_override("switch_claude_cli_to_local_hub", switch_claude_cli_to_local_hub)(runtime_base_urls["claude"], local_api_key),
            "gemini": lambda: _router_override("switch_gemini_cli_to_local_hub", switch_gemini_cli_to_local_hub)(runtime_base_urls["gemini"], local_api_key),
        },
    )
    if handler is not None:
        return handler()
    return {"ok": False, "message": f"Unsupported client: {client_id}"}


def restore_client_from_backup(client_id: str) -> Dict[str, Any]:
    handler = _client_handler(
        client_id,
        {
            "codex": lambda: _router_override("restore_codex_cli_from_backup", restore_codex_cli_from_backup)(),
            "claude": lambda: _router_override("restore_claude_cli_from_backup", restore_claude_cli_from_backup)(),
            "gemini": lambda: _router_override("restore_gemini_cli_from_backup", restore_gemini_cli_from_backup)(),
        },
    )
    if handler is not None:
        return handler()
    return {"ok": False, "message": f"Unsupported client: {client_id}"}


__all__ = [
    "collect_client_binding_statuses",
    "detect_active_codex_provider",
    "get_claude_cli_binding_status",
    "get_codex_cli_binding_status",
    "get_gemini_cli_binding_status",
    "get_local_llm_cli_binding_status",
    "read_toml_string_value",
    "restore_all_clients_from_backup",
    "restore_claude_cli_from_backup",
    "restore_client_from_backup",
    "restore_codex_cli_from_backup",
    "restore_gemini_cli_from_backup",
    "switch_all_clients_to_local_hub",
    "switch_claude_cli_to_local_hub",
    "switch_client_to_local_hub",
    "switch_codex_cli_to_local_hub",
    "switch_gemini_cli_to_local_hub",
    "upsert_toml_key",
]

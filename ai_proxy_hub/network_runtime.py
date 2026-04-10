from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from .constants import UPSTREAM_PROTOCOL_LABELS


def display_runtime_host(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "::", "") else host


def build_protocol_runtime_base_url(host: str, port: int, protocol: str) -> str:
    display_host = display_runtime_host(host)
    if protocol == "anthropic":
        return f"http://{display_host}:{port}/claude"
    if protocol == "gemini":
        return f"http://{display_host}:{port}/gemini"
    return f"http://{display_host}:{port}/openai"


def build_runtime_base_url(host: str, port: int) -> str:
    return build_protocol_runtime_base_url(host, port, "openai")


def build_dashboard_url(host: str, port: int) -> str:
    display_host = display_runtime_host(host)
    return f"http://{display_host}:{port}/"


def dashboard_url_from_api_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    for suffix in ("/v1beta", "/v1alpha", "/v1", "/openai", "/claude", "/anthropic", "/gemini"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path:
        path = "/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def client_display_name(client_id: str) -> str:
    return {
        "codex": "Codex",
        "claude": "Claude Code",
        "gemini": "Gemini CLI",
        "local_llm": "Local LLM",
    }.get(client_id, client_id)


def protocol_client_id(protocol: str) -> str:
    return {
        "openai": "codex",
        "anthropic": "claude",
        "gemini": "gemini",
    }.get(protocol, protocol)


def client_protocol_id(client_id: str) -> str:
    return {
        "codex": "openai",
        "claude": "anthropic",
        "gemini": "gemini",
        "local_llm": "local_llm",
    }.get(client_id, "openai")


def process_label(process_info: Optional[Dict[str, Any]]) -> str:
    if not process_info:
        return ""
    pid = process_info.get("pid")
    command = str(process_info.get("command") or "").strip()
    if pid and command:
        return f"{command} (PID {pid})"
    if pid:
        return f"PID {pid}"
    return command


def protocol_display_name(protocol: str) -> str:
    return UPSTREAM_PROTOCOL_LABELS.get(protocol, protocol)


__all__ = [
    "build_dashboard_url",
    "build_protocol_runtime_base_url",
    "build_runtime_base_url",
    "client_display_name",
    "client_protocol_id",
    "dashboard_url_from_api_base_url",
    "display_runtime_host",
    "process_label",
    "protocol_client_id",
    "protocol_display_name",
]

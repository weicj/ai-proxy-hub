from __future__ import annotations

from typing import Any, Dict

from .constants import (
    DEFAULT_ENDPOINT_MODE,
    DEFAULT_LISTEN_PORT,
    DEFAULT_SHARED_API_PREFIXES,
    DEFAULT_SPLIT_API_PORTS,
    DEFAULT_WEB_UI_PORT_OFFSET,
    NATIVE_API_PREFIXES,
    UPSTREAM_PROTOCOL_ORDER,
)
from .network_runtime import display_runtime_host
from .utils import safe_int


def normalize_endpoint_mode(value: Any) -> str:
    endpoint_mode = str(value or DEFAULT_ENDPOINT_MODE).strip().lower()
    if endpoint_mode not in {"shared", "split"}:
        return DEFAULT_ENDPOINT_MODE
    return endpoint_mode


def normalize_api_prefix(value: Any, default: str) -> str:
    prefix = str(value or default).strip() or default
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = prefix.rstrip("/") or "/"
    return prefix


def normalize_shared_api_prefixes(value: Any) -> Dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        protocol: normalize_api_prefix(raw.get(protocol), default)
        for protocol, default in DEFAULT_SHARED_API_PREFIXES.items()
    }


def normalize_split_api_ports(value: Any, default_port: int) -> Dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    normalized: Dict[str, int] = {}
    for protocol in UPSTREAM_PROTOCOL_ORDER:
        fallback = DEFAULT_SPLIT_API_PORTS[protocol] if protocol != "openai" else default_port
        parsed = safe_int(raw.get(protocol), fallback)
        if not 1 <= parsed <= 65535:
            parsed = fallback
        normalized[protocol] = parsed
    return normalized


def default_web_ui_port(api_ports: Dict[str, int]) -> int:
    preferred = int(api_ports.get("openai", DEFAULT_LISTEN_PORT)) + DEFAULT_WEB_UI_PORT_OFFSET
    if preferred in set(api_ports.values()):
        preferred = max([DEFAULT_LISTEN_PORT, *api_ports.values()]) + 1
    return preferred


def protocol_base_path_for_mode(config: Dict[str, Any], protocol: str) -> str:
    endpoint_mode = normalize_endpoint_mode(config.get("endpoint_mode"))
    if endpoint_mode == "split":
        return NATIVE_API_PREFIXES[protocol]
    shared_api_prefixes = normalize_shared_api_prefixes(config.get("shared_api_prefixes"))
    return shared_api_prefixes[protocol]


def protocol_port_from_config(config: Dict[str, Any], protocol: str) -> int:
    listen_port = safe_int(config.get("listen_port"), DEFAULT_LISTEN_PORT)
    endpoint_mode = normalize_endpoint_mode(config.get("endpoint_mode"))
    if endpoint_mode == "split":
        return normalize_split_api_ports(config.get("split_api_ports"), listen_port)[protocol]
    return listen_port


def web_ui_port_from_config(config: Dict[str, Any]) -> int:
    listen_port = safe_int(config.get("listen_port"), DEFAULT_LISTEN_PORT)
    endpoint_mode = normalize_endpoint_mode(config.get("endpoint_mode"))
    if endpoint_mode == "shared":
        return listen_port
    if endpoint_mode == "split":
        api_ports = normalize_split_api_ports(config.get("split_api_ports"), listen_port)
    else:
        api_ports = {"openai": listen_port}
    fallback = default_web_ui_port(api_ports)
    parsed = safe_int(config.get("web_ui_port"), fallback)
    if not 1 <= parsed <= 65535 or parsed in set(api_ports.values()):
        parsed = fallback
    return parsed


def protocol_runtime_base_url(config: Dict[str, Any], host: str, protocol: str) -> str:
    display_host = display_runtime_host(host)
    port = protocol_port_from_config(config, protocol)
    base_path = protocol_base_path_for_mode(config, protocol)
    return f"http://{display_host}:{port}{base_path}"


def dashboard_runtime_url(config: Dict[str, Any], host: str) -> str:
    display_host = display_runtime_host(host)
    return f"http://{display_host}:{web_ui_port_from_config(config)}/"


__all__ = [
    "dashboard_runtime_url",
    "default_web_ui_port",
    "normalize_api_prefix",
    "normalize_endpoint_mode",
    "normalize_shared_api_prefixes",
    "normalize_split_api_ports",
    "protocol_base_path_for_mode",
    "protocol_port_from_config",
    "protocol_runtime_base_url",
    "web_ui_port_from_config",
]

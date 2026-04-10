from __future__ import annotations

import http.client
import json
import socket
from typing import Any, Dict, Iterable, List

from .config_logic import (
    dashboard_runtime_url,
    normalize_api_prefix,
    normalize_endpoint_mode,
    normalize_shared_api_prefixes,
    normalize_split_api_ports,
    protocol_runtime_base_url,
    web_ui_port_from_config,
)
from .constants import DEFAULT_LISTEN_HOST, DEFAULT_LISTEN_PORT, NATIVE_API_PREFIXES, UPSTREAM_PROTOCOL_ORDER
from .network_runtime import display_runtime_host
from .protocols import normalize_upstream_protocol
from .utils import safe_int


def _mapping_copy(value: Any, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return dict(fallback)


def _tuple_copy(value: Any, fallback: Iterable[str] = ()) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        return tuple(value)
    return tuple(fallback)


def controller_runtime_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    listen_port = safe_int(config.get("listen_port"), DEFAULT_LISTEN_PORT)
    return {
        "config": config,
        "host": str(config.get("listen_host") or DEFAULT_LISTEN_HOST),
        "endpoint_mode": normalize_endpoint_mode(config.get("endpoint_mode")),
        "shared_api_prefixes": normalize_shared_api_prefixes(config.get("shared_api_prefixes")),
        "split_api_ports": normalize_split_api_ports(config.get("split_api_ports"), listen_port),
        "listen_port": listen_port,
        "web_ui_port": web_ui_port_from_config(config),
    }


def snapshot_payload(
    *,
    state: str,
    error: str,
    owner: str,
    active_server_names: List[str],
    active_protocols: List[str],
    dashboard_running: bool,
) -> Dict[str, Any]:
    return {
        "state": state,
        "error": error,
        "owner": owner,
        "active_server_names": active_server_names,
        "active_protocols": active_protocols,
        "all_protocols_started": len(active_protocols) == len(UPSTREAM_PROTOCOL_ORDER),
        "partially_started": 0 < len(active_protocols) < len(UPSTREAM_PROTOCOL_ORDER),
        "dashboard_running": dashboard_running,
    }


def ordered_protocols(protocols: Iterable[str]) -> tuple[str, ...]:
    normalized = {
        normalize_upstream_protocol(protocol)
        for protocol in protocols
        if normalize_upstream_protocol(protocol) in UPSTREAM_PROTOCOL_ORDER
    }
    return tuple(protocol for protocol in UPSTREAM_PROTOCOL_ORDER if protocol in normalized)


def build_server_specs(config: Dict[str, Any], shared_exposed_protocols: Iterable[str]) -> List[Dict[str, Any]]:
    settings = controller_runtime_settings(config)
    host = settings["host"]
    endpoint_mode = settings["endpoint_mode"]
    shared_api_prefixes = settings["shared_api_prefixes"]
    web_ui_port = settings["web_ui_port"]
    listen_port = settings["listen_port"]

    dashboard_spec = {
        "name": "dashboard",
        "host": host,
        "port": web_ui_port,
        "protocol_prefixes": shared_api_prefixes,
        "exposed_protocols": (),
        "dashboard_enabled": True,
    }
    if endpoint_mode == "split":
        return [
            dashboard_spec,
            *[
                {
                    "name": protocol,
                    "host": host,
                    "port": settings["split_api_ports"][protocol],
                    "protocol_prefixes": {protocol: NATIVE_API_PREFIXES[protocol]},
                    "exposed_protocols": (protocol,),
                    "dashboard_enabled": False,
                }
                for protocol in UPSTREAM_PROTOCOL_ORDER
            ],
        ]

    if web_ui_port == listen_port:
        return [
            {
                "name": "shared",
                "host": host,
                "port": listen_port,
                "protocol_prefixes": shared_api_prefixes,
                "exposed_protocols": tuple(shared_exposed_protocols),
                "dashboard_enabled": True,
            }
        ]

    return [
        dashboard_spec,
        {
            "name": "shared",
            "host": host,
            "port": listen_port,
            "protocol_prefixes": shared_api_prefixes,
            "exposed_protocols": tuple(shared_exposed_protocols),
            "dashboard_enabled": False,
        },
    ]


def build_server_specs_map(config: Dict[str, Any], shared_exposed_protocols: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    return {spec["name"]: spec for spec in build_server_specs(config, shared_exposed_protocols)}


def dashboard_spec_name(specs: Dict[str, Dict[str, Any]]) -> str:
    for name, spec in specs.items():
        if bool(spec.get("dashboard_enabled")):
            return name
    return ""


def api_spec_names(specs: Dict[str, Dict[str, Any]]) -> List[str]:
    return [name for name, spec in specs.items() if tuple(spec.get("exposed_protocols") or ())]


def endpoint_reachable(host: str, port: int) -> bool:
    check_host = "127.0.0.1" if str(host) in {"0.0.0.0", "::", ""} else str(host)
    try:
        with socket.create_connection((check_host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def is_ai_proxy_hub_running(host: str, port: int) -> bool:
    check_host = "127.0.0.1" if str(host) in {"0.0.0.0", "::", ""} else str(host)
    try:
        conn = http.client.HTTPConnection(check_host, int(port), timeout=1.0)
        conn.request("GET", "/health")
        response = conn.getresponse()
        body = response.read(1024).decode("utf-8", errors="ignore")
        conn.close()
        if response.status == 200:
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                return False
            return data.get("status") == "ok" and "time" in data
        return False
    except Exception:
        return False


def fetch_hub_status(host: str, port: int) -> Dict[str, Any] | None:
    check_host = "127.0.0.1" if str(host) in {"0.0.0.0", "::", ""} else str(host)
    try:
        conn = http.client.HTTPConnection(check_host, int(port), timeout=1.5)
        conn.request("GET", "/api/status")
        response = conn.getresponse()
        body = response.read(4 * 1024 * 1024).decode("utf-8", errors="ignore")
        conn.close()
        if response.status != 200:
            return None
        data = json.loads(body)
        runtime = data.get("runtime")
        service = data.get("service")
        if not isinstance(data, dict) or not isinstance(runtime, dict) or not isinstance(service, dict):
            return None
        return data
    except Exception:
        return None


def runtime_info_payload(
    config: Dict[str, Any],
    shared_exposed_protocols: Iterable[str],
    servers: Dict[str, Any],
) -> Dict[str, Any]:
    settings = controller_runtime_settings(config)
    specs = build_server_specs(config, shared_exposed_protocols)
    if not servers:
        host = settings["host"]
        return {
            "host": host,
            "port": settings["web_ui_port"],
            "base_url": protocol_runtime_base_url(config, host, "openai"),
            "openai_base_url": protocol_runtime_base_url(config, host, "openai"),
            "claude_base_url": protocol_runtime_base_url(config, host, "anthropic"),
            "gemini_base_url": protocol_runtime_base_url(config, host, "gemini"),
            "local_llm_base_url": protocol_runtime_base_url(config, host, "local_llm"),
            "dashboard_url": dashboard_runtime_url(config, host),
            "listen_host": settings["host"],
            "listen_port": settings["listen_port"],
            "endpoint_mode": settings["endpoint_mode"],
            "shared_api_prefixes": settings["shared_api_prefixes"],
            "split_api_ports": settings["split_api_ports"],
            "web_ui_port": settings["web_ui_port"],
            "listen_targets": specs,
        }

    ordered_names = [name for name in ["dashboard", "shared", *UPSTREAM_PROTOCOL_ORDER] if name in servers]
    first_server = servers[ordered_names[0]]
    host = str(first_server.server_address[0])
    display_host = display_runtime_host(host)
    listen_targets = [
        {
            "name": name,
            "host": str(servers[name].server_address[0]),
            "port": int(servers[name].server_address[1]),
            "protocol_prefixes": _mapping_copy(getattr(servers[name], "protocol_prefixes", {}), {}),
            "exposed_protocols": _tuple_copy(getattr(servers[name], "exposed_protocols", ())),
            "dashboard_enabled": bool(getattr(servers[name], "dashboard_enabled", False)),
        }
        for name in ordered_names
    ]

    if "shared" in servers:
        shared_server = servers["shared"]
        shared_port = int(shared_server.server_address[1])
        shared_prefixes = normalize_shared_api_prefixes(
            _mapping_copy(getattr(shared_server, "protocol_prefixes", settings["shared_api_prefixes"]), settings["shared_api_prefixes"])
        )
        dashboard_port = (
            shared_port
            if bool(getattr(shared_server, "dashboard_enabled", False))
            else int(servers["dashboard"].server_address[1]) if "dashboard" in servers else settings["web_ui_port"]
        )

        def build_base_url(protocol: str) -> str:
            path = normalize_api_prefix(shared_prefixes.get(protocol), NATIVE_API_PREFIXES[protocol])
            return f"http://{display_host}:{shared_port}{path}"

        return {
            "host": host,
            "port": dashboard_port,
            "base_url": build_base_url("openai"),
            "openai_base_url": build_base_url("openai"),
            "claude_base_url": build_base_url("anthropic"),
            "gemini_base_url": build_base_url("gemini"),
            "local_llm_base_url": build_base_url("local_llm"),
            "dashboard_url": f"http://{display_host}:{dashboard_port}/",
            "listen_host": host,
            "listen_port": shared_port,
            "endpoint_mode": "shared",
            "shared_api_prefixes": shared_prefixes,
            "split_api_ports": normalize_split_api_ports(settings["split_api_ports"], shared_port),
            "web_ui_port": dashboard_port,
            "listen_targets": listen_targets,
        }

    split_ports = normalize_split_api_ports(settings["split_api_ports"], settings["listen_port"])
    for protocol in UPSTREAM_PROTOCOL_ORDER:
        server = servers.get(protocol)
        if server is not None:
            split_ports[protocol] = int(server.server_address[1])
    dashboard_port = int(servers["dashboard"].server_address[1]) if "dashboard" in servers else settings["web_ui_port"]

    def build_split_base_url(protocol: str) -> str:
        server = servers.get(protocol)
        prefixes = (
            _mapping_copy(getattr(server, "protocol_prefixes", {protocol: NATIVE_API_PREFIXES[protocol]}), {protocol: NATIVE_API_PREFIXES[protocol]})
            if server else {protocol: NATIVE_API_PREFIXES[protocol]}
        )
        path = normalize_api_prefix(prefixes.get(protocol), NATIVE_API_PREFIXES[protocol])
        return f"http://{display_host}:{split_ports[protocol]}{path}"

    return {
        "host": host,
        "port": dashboard_port,
        "base_url": build_split_base_url("openai"),
        "openai_base_url": build_split_base_url("openai"),
        "claude_base_url": build_split_base_url("anthropic"),
        "gemini_base_url": build_split_base_url("gemini"),
        "local_llm_base_url": build_split_base_url("local_llm"),
        "dashboard_url": f"http://{display_host}:{dashboard_port}/",
        "listen_host": host,
        "listen_port": settings["listen_port"],
        "endpoint_mode": "split",
        "shared_api_prefixes": settings["shared_api_prefixes"],
        "split_api_ports": split_ports,
        "web_ui_port": dashboard_port,
        "listen_targets": listen_targets,
    }


def runtime_base_urls(runtime: Dict[str, Any]) -> Dict[str, str]:
    return {
        "codex": str(runtime.get("openai_base_url") or ""),
        "claude": str(runtime.get("claude_base_url") or ""),
        "gemini": str(runtime.get("gemini_base_url") or ""),
        "local_llm": str(runtime.get("local_llm_base_url") or ""),
    }

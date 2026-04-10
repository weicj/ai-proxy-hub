from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from .config_endpoints import (
    normalize_endpoint_mode,
    normalize_shared_api_prefixes,
    normalize_split_api_ports,
    web_ui_port_from_config,
)
from .constants import (
    CONFIG_VERSION,
    DEFAULT_COOLDOWN,
    DEFAULT_DEFAULT_MODEL_MODE,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_MODEL_MODE_LABELS,
    DEFAULT_RETRYABLE_STATUSES,
    DEFAULT_ROUTING_MODE,
    DEFAULT_TIMEOUT,
    LOCAL_LLM_UPSTREAM_PROTOCOLS,
    ROUTING_MODE_LABELS,
    SUPPORTED_CLI_THEME_MODES,
    SUPPORTED_THEME_MODES,
    SUPPORTED_UI_LANGUAGES,
    UPSTREAM_PROTOCOL_ORDER,
)
from .local_keys import normalize_local_api_keys, primary_local_api_key_entry
from .protocols import normalize_upstream_protocol
from .subscriptions import normalize_upstream_subscriptions
from .utils import safe_int


def normalize_base_url(value: Any) -> str:
    base_url = str(value or "").strip()
    return base_url.rstrip("/")


def normalize_extra_headers(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    headers: Dict[str, str] = {}
    for key, header_value in value.items():
        if not key:
            continue
        headers[str(key).strip()] = str(header_value).strip()
    return headers


def default_upstream(name: Optional[str] = None) -> Dict[str, Any]:
    upstream_name = name or "默认上游"
    return {
        "id": secrets.token_hex(6),
        "name": upstream_name,
        "protocol": "openai",
        "base_url": "",
        "api_key": "",
        "enabled": True,
        "notes": "",
        "default_model": "",
        "extra_headers": {},
        "upstream_protocol": "openai",
        "subscriptions": normalize_upstream_subscriptions([], upstream_name),
    }


def normalize_upstream(item: Any, index: int) -> Dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    protocol = normalize_upstream_protocol(item.get("protocol") or item.get("provider"))
    result = {
        "id": str(item.get("id") or secrets.token_hex(6)),
        "name": str(item.get("name") or f"上游 {index + 1}").strip() or f"上游 {index + 1}",
        "protocol": protocol,
        "base_url": normalize_base_url(item.get("base_url") or item.get("url")),
        "api_key": str(item.get("api_key") or item.get("token") or "").strip(),
        "enabled": bool(item.get("enabled", True)),
        "notes": str(item.get("notes") or "").strip(),
        "default_model": str(item.get("default_model") or item.get("model") or "").strip(),
        "extra_headers": normalize_extra_headers(item.get("extra_headers")),
        "subscriptions": normalize_upstream_subscriptions(item.get("subscriptions"), str(item.get("name") or f"上游 {index + 1}")),
    }
    if protocol == "local_llm":
        upstream_protocol = str(item.get("upstream_protocol") or "openai").strip().lower()
        if upstream_protocol not in LOCAL_LLM_UPSTREAM_PROTOCOLS:
            upstream_protocol = "openai"
        result["upstream_protocol"] = upstream_protocol
    return result


def normalize_routing_mode(value: Any) -> str:
    routing_mode = str(value or DEFAULT_ROUTING_MODE).strip().lower()
    if routing_mode not in ROUTING_MODE_LABELS:
        return DEFAULT_ROUTING_MODE
    return routing_mode


def normalize_default_model_mode(value: Any) -> str:
    mode = str(value or DEFAULT_DEFAULT_MODEL_MODE).strip().lower()
    if mode not in DEFAULT_MODEL_MODE_LABELS:
        return DEFAULT_DEFAULT_MODEL_MODE
    return mode


def normalize_ui_language(value: Any) -> str:
    language = str(value or "auto").strip().lower()
    if language not in SUPPORTED_UI_LANGUAGES:
        return "auto"
    return language


def normalize_theme_mode(value: Any) -> str:
    mode = str(value or "auto").strip().lower()
    if mode not in SUPPORTED_THEME_MODES:
        return "auto"
    return mode


def normalize_cli_theme_mode(value: Any) -> str:
    mode = str(value or "auto").strip().lower()
    if mode not in SUPPORTED_CLI_THEME_MODES:
        return "auto"
    return mode


def normalize_default_model_mode_map(value: Any, *, legacy_mode: Any = None) -> Dict[str, str]:
    section = value if isinstance(value, dict) else {}
    fallback = normalize_default_model_mode(legacy_mode)
    normalized: Dict[str, str] = {}
    for protocol in UPSTREAM_PROTOCOL_ORDER:
        raw_value = section.get(protocol, fallback)
        if protocol == "openai" and legacy_mode is not None:
            raw_value = legacy_mode
        normalized[protocol] = normalize_default_model_mode(raw_value)
    return normalized


def normalize_global_default_models_map(value: Any, *, legacy_model: Any = None) -> Dict[str, str]:
    section = value if isinstance(value, dict) else {}
    fallback = str(legacy_model or "").strip()
    normalized: Dict[str, str] = {}
    for protocol in UPSTREAM_PROTOCOL_ORDER:
        raw_value = section.get(protocol, fallback)
        if protocol == "openai" and legacy_model is not None:
            raw_value = legacy_model
        value_text = str(raw_value or "").strip()
        normalized[protocol] = value_text if value_text else fallback
    return normalized


def default_model_settings_from_config(config: Dict[str, Any], protocol: str = "openai") -> Dict[str, str]:
    normalized_protocol = normalize_upstream_protocol(protocol)
    mode_map = normalize_default_model_mode_map(
        config.get("default_model_mode_by_protocol"),
        legacy_mode=config.get("default_model_mode"),
    )
    model_map = normalize_global_default_models_map(
        config.get("global_default_models_by_protocol"),
        legacy_model=config.get("global_default_model"),
    )
    return {
        "mode": mode_map.get(normalized_protocol, mode_map["openai"]),
        "global_default_model": model_map.get(normalized_protocol, ""),
    }


def protocol_upstream_ids(upstreams: List[Dict[str, Any]], protocol: str) -> List[str]:
    return [item["id"] for item in upstreams if normalize_upstream_protocol(item.get("protocol")) == protocol]


def default_protocol_routing_settings(upstreams: List[Dict[str, Any]], protocol: str) -> Dict[str, Any]:
    protocol_ids = protocol_upstream_ids(upstreams, protocol)
    return {
        "auto_routing_enabled": True,
        "routing_mode": DEFAULT_ROUTING_MODE,
        "manual_active_upstream_id": protocol_ids[0] if protocol_ids else "",
    }


def normalize_protocol_routing_section(
    value: Any,
    *,
    protocol: str,
    upstreams: List[Dict[str, Any]],
    defaults: Dict[str, Any],
) -> Dict[str, Any]:
    section = value if isinstance(value, dict) else {}
    valid_ids = set(protocol_upstream_ids(upstreams, protocol))
    manual_id = str(section.get("manual_active_upstream_id") or defaults["manual_active_upstream_id"]).strip()
    if manual_id not in valid_ids:
        manual_id = defaults["manual_active_upstream_id"]
    return {
        "auto_routing_enabled": bool(section.get("auto_routing_enabled", defaults["auto_routing_enabled"])),
        "routing_mode": normalize_routing_mode(section.get("routing_mode", defaults["routing_mode"])),
        "manual_active_upstream_id": manual_id,
    }


def normalize_routing_by_protocol(raw: Dict[str, Any], upstreams: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    legacy_auto_enabled = bool(raw.get("auto_routing_enabled", True))
    legacy_routing_mode = normalize_routing_mode(raw.get("routing_mode"))
    legacy_manual_active = str(raw.get("manual_active_upstream_id") or "").strip()
    routing_map = raw.get("routing_by_protocol") if isinstance(raw.get("routing_by_protocol"), dict) else {}
    use_legacy_defaults_for_all = not isinstance(raw.get("routing_by_protocol"), dict)
    normalized: Dict[str, Dict[str, Any]] = {}

    for protocol in UPSTREAM_PROTOCOL_ORDER:
        defaults = default_protocol_routing_settings(upstreams, protocol)
        if use_legacy_defaults_for_all:
            defaults = {
                "auto_routing_enabled": legacy_auto_enabled,
                "routing_mode": legacy_routing_mode,
                "manual_active_upstream_id": legacy_manual_active or defaults["manual_active_upstream_id"],
            }
        section = normalize_protocol_routing_section(
            routing_map.get(protocol),
            protocol=protocol,
            upstreams=upstreams,
            defaults=defaults,
        )
        if protocol == "openai":
            valid_ids = set(protocol_upstream_ids(upstreams, protocol))
            section["auto_routing_enabled"] = bool(raw.get("auto_routing_enabled", section["auto_routing_enabled"]))
            section["routing_mode"] = normalize_routing_mode(raw.get("routing_mode", section["routing_mode"]))
            manual_id = str(raw.get("manual_active_upstream_id") or section["manual_active_upstream_id"]).strip()
            if manual_id not in valid_ids:
                manual_id = default_protocol_routing_settings(upstreams, protocol)["manual_active_upstream_id"]
            section["manual_active_upstream_id"] = manual_id
        normalized[protocol] = section
    return normalized


def protocol_routing_settings_from_config(config: Dict[str, Any], protocol: str) -> Dict[str, Any]:
    routing_map = config.get("routing_by_protocol") if isinstance(config.get("routing_by_protocol"), dict) else {}
    upstreams = [normalize_upstream(item, index) for index, item in enumerate(config.get("upstreams") or [])]
    defaults = default_protocol_routing_settings(upstreams, protocol)
    if isinstance(routing_map.get(protocol), dict):
        return normalize_protocol_routing_section(
            routing_map[protocol],
            protocol=protocol,
            upstreams=upstreams,
            defaults=defaults,
        )
    if protocol == "openai":
        defaults["auto_routing_enabled"] = bool(config.get("auto_routing_enabled", defaults["auto_routing_enabled"]))
        defaults["routing_mode"] = normalize_routing_mode(config.get("routing_mode", defaults["routing_mode"]))
        manual_id = str(config.get("manual_active_upstream_id") or defaults["manual_active_upstream_id"]).strip()
        if manual_id in set(protocol_upstream_ids(upstreams, protocol)):
            defaults["manual_active_upstream_id"] = manual_id
    return defaults


def normalize_config(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    if "upstreams" not in raw and any(key in raw for key in ("url", "token", "model")):
        raw = {
            "listen_host": raw.get("listen_host"),
            "listen_port": raw.get("listen_port"),
            "local_api_key": raw.get("local_api_key"),
            "request_timeout_sec": raw.get("request_timeout_sec"),
            "cooldown_seconds": raw.get("cooldown_seconds"),
            "upstreams": [
                {
                    "name": "默认上游",
                    "base_url": raw.get("url", ""),
                    "api_key": raw.get("token", ""),
                    "default_model": raw.get("model", ""),
                    "enabled": True,
                }
            ],
        }

    retryable_statuses = raw.get("retryable_statuses") or DEFAULT_RETRYABLE_STATUSES
    normalized_statuses = []
    for status in retryable_statuses:
        parsed = safe_int(status, -1)
        if 100 <= parsed <= 599 and parsed not in normalized_statuses:
            normalized_statuses.append(parsed)
    if not normalized_statuses:
        normalized_statuses = list(DEFAULT_RETRYABLE_STATUSES)

    upstreams_raw = raw.get("upstreams") or [default_upstream()]
    upstreams = [normalize_upstream(item, index) for index, item in enumerate(upstreams_raw)]
    listen_port = safe_int(raw.get("listen_port"), DEFAULT_LISTEN_PORT)
    if not 1 <= listen_port <= 65535:
        listen_port = DEFAULT_LISTEN_PORT
    endpoint_mode = normalize_endpoint_mode(raw.get("endpoint_mode"))
    split_api_ports = normalize_split_api_ports(raw.get("split_api_ports"), listen_port)
    web_ui_port = web_ui_port_from_config(
        {
            "endpoint_mode": endpoint_mode,
            "listen_port": listen_port,
            "split_api_ports": split_api_ports,
            "web_ui_port": raw.get("web_ui_port"),
        }
    )

    local_api_keys = normalize_local_api_keys(raw.get("local_api_keys"), raw.get("local_api_key"))
    primary_local_api_key = primary_local_api_key_entry(local_api_keys)
    routing_by_protocol = normalize_routing_by_protocol(raw, upstreams)
    openai_routing = routing_by_protocol["openai"]
    default_model_mode_by_protocol = normalize_default_model_mode_map(
        raw.get("default_model_mode_by_protocol"),
        legacy_mode=raw.get("default_model_mode"),
    )
    global_default_models_by_protocol = normalize_global_default_models_map(
        raw.get("global_default_models_by_protocol"),
        legacy_model=raw.get("global_default_model"),
    )

    return {
        "version": CONFIG_VERSION,
        "listen_host": str(raw.get("listen_host") or DEFAULT_LISTEN_HOST).strip() or DEFAULT_LISTEN_HOST,
        "listen_port": listen_port,
        "local_api_key": primary_local_api_key["key"],
        "local_api_keys": local_api_keys,
        "request_timeout_sec": max(5, safe_int(raw.get("request_timeout_sec"), DEFAULT_TIMEOUT)),
        "cooldown_seconds": max(0, safe_int(raw.get("cooldown_seconds"), DEFAULT_COOLDOWN)),
        "default_model_mode": default_model_mode_by_protocol["openai"],
        "global_default_model": global_default_models_by_protocol["openai"],
        "default_model_mode_by_protocol": default_model_mode_by_protocol,
        "global_default_models_by_protocol": global_default_models_by_protocol,
        "ui_language": normalize_ui_language(raw.get("ui_language")),
        "ui_language_initialized": bool(raw.get("ui_language_initialized", False)),
        "theme_mode": normalize_theme_mode(raw.get("theme_mode")),
        "cli_theme_mode": normalize_cli_theme_mode(raw.get("cli_theme_mode") or raw.get("theme_mode")),
        "endpoint_mode": endpoint_mode,
        "shared_api_prefixes": normalize_shared_api_prefixes(raw.get("shared_api_prefixes")),
        "split_api_ports": split_api_ports,
        "web_ui_port": web_ui_port,
        "auto_routing_enabled": openai_routing["auto_routing_enabled"],
        "routing_mode": openai_routing["routing_mode"],
        "manual_active_upstream_id": openai_routing["manual_active_upstream_id"],
        "routing_by_protocol": routing_by_protocol,
        "retryable_statuses": normalized_statuses,
        "upstreams": upstreams,
    }


def routing_strategy_from_config(config: Dict[str, Any], protocol: str = "openai") -> str:
    settings = protocol_routing_settings_from_config(config, protocol)
    if not bool(settings.get("auto_routing_enabled", True)):
        return "manual"
    return str(settings.get("routing_mode") or DEFAULT_ROUTING_MODE)


def ensure_routing_by_protocol(config: Dict[str, Any]) -> None:
    config["routing_by_protocol"] = normalize_routing_by_protocol(
        config,
        [normalize_upstream(item, index) for index, item in enumerate(config.get("upstreams") or [])],
    )
    openai = config["routing_by_protocol"]["openai"]
    config["auto_routing_enabled"] = openai["auto_routing_enabled"]
    config["routing_mode"] = openai["routing_mode"]
    config["manual_active_upstream_id"] = openai["manual_active_upstream_id"]


def apply_routing_strategy_to_config(config: Dict[str, Any], strategy: str, protocol: str = "openai") -> None:
    ensure_routing_by_protocol(config)
    if strategy == "manual":
        config["routing_by_protocol"][protocol]["auto_routing_enabled"] = False
        config["routing_by_protocol"][protocol]["routing_mode"] = DEFAULT_ROUTING_MODE
    else:
        config["routing_by_protocol"][protocol]["auto_routing_enabled"] = True
        config["routing_by_protocol"][protocol]["routing_mode"] = normalize_routing_mode(strategy)
    if protocol == "openai":
        config["auto_routing_enabled"] = config["routing_by_protocol"][protocol]["auto_routing_enabled"]
        config["routing_mode"] = config["routing_by_protocol"][protocol]["routing_mode"]
        config["manual_active_upstream_id"] = config["routing_by_protocol"][protocol]["manual_active_upstream_id"]


def set_manual_active_upstream(config: Dict[str, Any], protocol: str, upstream_id: str) -> None:
    ensure_routing_by_protocol(config)
    valid_ids = set(protocol_upstream_ids([normalize_upstream(item, index) for index, item in enumerate(config.get("upstreams") or [])], protocol))
    if upstream_id not in valid_ids:
        return
    config["routing_by_protocol"][protocol]["manual_active_upstream_id"] = upstream_id
    if protocol == "openai":
        config["manual_active_upstream_id"] = upstream_id


__all__ = [
    "apply_routing_strategy_to_config",
    "default_model_settings_from_config",
    "default_protocol_routing_settings",
    "default_upstream",
    "ensure_routing_by_protocol",
    "normalize_cli_theme_mode",
    "normalize_base_url",
    "normalize_config",
    "normalize_default_model_mode",
    "normalize_default_model_mode_map",
    "normalize_extra_headers",
    "normalize_global_default_models_map",
    "normalize_protocol_routing_section",
    "normalize_routing_by_protocol",
    "normalize_routing_mode",
    "normalize_theme_mode",
    "normalize_ui_language",
    "normalize_upstream",
    "protocol_routing_settings_from_config",
    "protocol_upstream_ids",
    "routing_strategy_from_config",
    "set_manual_active_upstream",
]

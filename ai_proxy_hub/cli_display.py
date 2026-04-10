from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List

from .constants import UPSTREAM_PROTOCOL_ORDER
from .local_keys import normalize_local_key_protocols
from .network import protocol_client_id, protocol_display_name
from .protocols import normalize_upstream_protocol


Translator = Callable[..., str]


def protocol_console_label(language: str, translate: Translator, protocol: str) -> str:
    return {
        "openai": translate("routing_codex"),
        "anthropic": translate("routing_claude"),
        "gemini": translate("routing_gemini"),
        "local_llm": "Local LLM" if language == "en" else "本地 LLM",
    }.get(protocol, protocol)


def format_client_status_line(language: str, client_name: str, info: Dict[str, Any]) -> str:
    if info["state"] == "switched":
        prefix = "🟢"
        text = "已切到 Hub" if language == "zh" else "switched to Hub"
    elif info["state"] == "external":
        prefix = "🟡"
        text = "已切到其他运行中的 Hub" if language == "zh" else "switched to another running Hub"
    elif info["state"] == "not_switched":
        prefix = "⚪"
        text = "未切换" if language == "zh" else "not switched"
    else:
        prefix = "🔴"
        text = "状态异常" if language == "zh" else "error"
    target = info.get("base_url") or ""
    suffix = f" @ {target}" if target and info["state"] in {"switched", "external"} else ""
    return f"{prefix} {client_name}: {text}{suffix}"


def routing_strategy_label(translate: Translator, strategy: str) -> str:
    mapping = {
        "manual": translate("routing_manual"),
        "priority": translate("routing_priority"),
        "round_robin": translate("routing_round_robin"),
        "latency": translate("routing_latency"),
    }
    return mapping.get(strategy, strategy)


def activation_label(
    translate: Translator,
    upstream_id: str,
    enabled: bool,
    snapshot: Dict[str, Any],
    protocol: str,
) -> str:
    routing = ((snapshot.get("routing") or {}).get("protocols") or {}).get(protocol, {})
    preview = routing.get("preview_order") or []
    preview_index = next((index for index, item in enumerate(preview) if item["id"] == upstream_id), -1)
    if not enabled:
        return translate("summary_disabled")
    if not routing.get("auto_routing_enabled", True):
        if routing["manual_active_upstream_id"] == upstream_id:
            return translate("summary_manual_active")
        return translate("summary_inactive")
    if preview_index == 0:
        return translate("summary_preferred")
    if preview_index > 0:
        return translate("summary_candidate", index=preview_index + 1)
    return translate("summary_standby")


def probe_label(translate: Translator, stats: Dict[str, Any]) -> str:
    if stats.get("last_probe_status"):
        return translate(
            "summary_probe_ok",
            status=stats["last_probe_status"],
            latency=stats.get("last_probe_latency_ms") or 0,
        )
    if stats.get("last_probe_error"):
        return translate("summary_probe_fail")
    return translate("summary_never_tested")


def protocol_label(language: str, protocol: str) -> str:
    if language == "zh":
        return {
            "openai": "OpenAI",
            "anthropic": "Claude/Anthropic",
            "gemini": "Gemini",
        }.get(protocol, protocol)
    return protocol_display_name(protocol)


def format_usage_label(usage_range: str, start_ts_ms: int) -> str:
    dt = datetime.fromtimestamp(start_ts_ms / 1000)
    if usage_range == "minute":
        return dt.strftime("%H:%M")
    if usage_range == "hour":
        return dt.strftime("%H:00")
    if usage_range == "day":
        return dt.strftime("%m/%d")
    return dt.strftime("%m/%d")


def theme_label(language: str, mode: str) -> str:
    labels = (
        {
            "auto": "系统",
            "dark": "深色",
            "light": "浅色",
            "blue": "蓝色",
            "green": "绿色",
            "amber": "琥珀",
            "rose": "玫瑰",
            "teal": "青绿",
        }
        if language == "zh"
        else {
            "auto": "System",
            "dark": "Dark",
            "light": "Light",
            "blue": "Blue",
            "green": "Green",
            "amber": "Amber",
            "rose": "Rose",
            "teal": "Teal",
        }
    )
    return labels.get(str(mode or "auto"), str(mode or "auto"))


def current_language_label(language: str, value: str) -> str:
    labels = (
        {
            "auto": "系统",
            "zh": "中文",
            "en": "English",
        }
        if language == "zh"
        else {
            "auto": "System",
            "zh": "Chinese",
            "en": "English",
        }
    )
    return labels.get(value, value)


def usage_scope_label(language: str, scope: str) -> str:
    if scope == "openai":
        return "Codex / OpenAI"
    if scope == "anthropic":
        return "Claude / Anthropic"
    if scope == "gemini":
        return "Gemini"
    return "全部" if language == "zh" else "All"


def protocol_runtime_url(runtime: Dict[str, Any], protocol: str) -> str:
    if protocol == "anthropic":
        return str(runtime.get("claude_base_url") or "-")
    if protocol == "gemini":
        return str(runtime.get("gemini_base_url") or "-")
    return str(runtime.get("openai_base_url") or "-")


def protocol_is_active(snapshot: Dict[str, Any], protocol: str) -> bool:
    service = snapshot.get("service") or {}
    active_protocols = {
        normalize_upstream_protocol(item)
        for item in (service.get("active_protocols") or [])
    }
    return normalize_upstream_protocol(protocol) in active_protocols


def protocol_service_status_label(language: str, snapshot: Dict[str, Any], protocol: str) -> str:
    service = snapshot.get("service") or {}
    state = str(service.get("state") or "stopped")
    owner = str(service.get("owner") or "local")
    if protocol_is_active(snapshot, protocol):
        if owner == "external":
            return "🟡 外部实例" if language == "zh" else "🟡 External"
        return "🟢 运行中" if language == "zh" else "🟢 Running"
    if state == "error":
        return "🔴 异常" if language == "zh" else "🔴 Error"
    return "⚪ 未启动" if language == "zh" else "⚪ Stopped"


def protocol_client_status_label(language: str, snapshot: Dict[str, Any], protocol: str) -> str:
    client_id = protocol_client_id(protocol)
    info = ((snapshot.get("clients") or {}).get(client_id) or {})
    state = str(info.get("state") or "not_switched")
    if state == "switched":
        return "🟢 本机启用" if language == "zh" else "🟢 Enabled here"
    if state == "external":
        return "🟡 外部 Hub" if language == "zh" else "🟡 External Hub"
    if state == "error":
        return "🔴 异常" if language == "zh" else "🔴 Error"
    return "⚪ 未启用" if language == "zh" else "⚪ Not enabled"


def runtime_mode_label(language: str, snapshot: Dict[str, Any]) -> str:
    service = snapshot.get("service") or {}
    active_protocols = {
        normalize_upstream_protocol(item)
        for item in (service.get("active_protocols") or [])
    }
    if not active_protocols:
        if str(service.get("state") or "") == "external":
            return "外部实例" if language == "zh" else "External instance"
        return "已停止" if language == "zh" else "Stopped"
    clients = snapshot.get("clients") or {}
    active_client_states = [
        str((clients.get(protocol_client_id(protocol)) or {}).get("state") or "not_switched")
        for protocol in active_protocols
    ]
    if active_client_states and all(state in {"switched", "external"} for state in active_client_states):
        return "代理模式" if language == "zh" else "Proxy mode"
    if any(state in {"switched", "external"} for state in active_client_states):
        return "混合模式" if language == "zh" else "Mixed mode"
    return "转发模式" if language == "zh" else "Forwarding mode"


def masked_secret(value: str) -> str:
    secret = str(value or "")
    if len(secret) <= 18:
        return secret or "-"
    return f"{secret[:12]}...{secret[-4:]}"


def format_protocol_list(protocols: List[str]) -> str:
    labels = []
    for protocol in normalize_local_key_protocols(protocols):
        if protocol == "openai":
            labels.append("Codex")
        elif protocol == "anthropic":
            labels.append("Claude")
        elif protocol == "gemini":
            labels.append("Gemini")
    return ", ".join(labels) or "-"


def normalize_usage_scope(scope: str) -> str:
    scope = str(scope or "all")
    if scope in {"all", *UPSTREAM_PROTOCOL_ORDER}:
        return scope
    return "all"


__all__ = [
    "activation_label",
    "current_language_label",
    "format_client_status_line",
    "format_protocol_list",
    "format_usage_label",
    "masked_secret",
    "normalize_usage_scope",
    "probe_label",
    "protocol_client_status_label",
    "protocol_console_label",
    "protocol_is_active",
    "protocol_label",
    "protocol_runtime_url",
    "protocol_service_status_label",
    "routing_strategy_label",
    "runtime_mode_label",
    "theme_label",
    "usage_scope_label",
]

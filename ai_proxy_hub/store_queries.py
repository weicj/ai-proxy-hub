from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .constants import DEFAULT_ROUTING_MODE, ROUTING_MODE_LABELS, UPSTREAM_PROTOCOL_ORDER
from .local_keys import normalize_local_key_protocols, primary_local_api_key_entry
from .project_meta import project_metadata_payload
from .protocols import normalize_upstream_protocol
from .store_helpers import status_runtime_payload, usage_series_payload


def partition_upstreams_locked(store: Any, upstreams: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ready: List[Dict[str, Any]] = []
    cooling: List[Dict[str, Any]] = []
    now = time.time()
    for upstream in upstreams:
        cooldown_until = float(store.stats.get(upstream["id"], {}).get("cooldown_until", 0.0))
        if cooldown_until > now:
            cooling.append(upstream)
        else:
            ready.append(upstream)
    return ready, cooling


def latency_sort_key_locked(store: Any, upstream_id: str, index: int) -> tuple[float, int]:
    stat = store.stats.get(upstream_id, store._default_stat())
    avg_latency = stat.get("avg_latency_ms")
    failure_count = int(stat.get("failure_count") or 0)
    latency_penalty = float(avg_latency) if avg_latency is not None else 1_000_000.0
    return (latency_penalty + (failure_count * 50.0), index)


def apply_routing_mode_locked(store: Any, upstreams: List[Dict[str, Any]], protocol: str, *, advance_cursor: bool) -> List[Dict[str, Any]]:
    if not upstreams:
        return []

    routing_mode = store._get_protocol_routing_locked(protocol)["routing_mode"]
    copied = [json.loads(json.dumps(item)) for item in upstreams]
    if routing_mode == "priority":
        return copied

    if routing_mode == "round_robin":
        start = store.round_robin_cursor_by_protocol[protocol] % len(copied)
        ordered = copied[start:] + copied[:start]
        if advance_cursor:
            store.round_robin_cursor_by_protocol[protocol] = (store.round_robin_cursor_by_protocol[protocol] + 1) % len(copied)
            store._save_runtime_state_locked()
        return ordered

    indexed = list(enumerate(copied))
    indexed.sort(key=lambda item: store._latency_sort_key_locked(item[1]["id"], item[0]))
    return [item for _, item in indexed]


def filter_upstreams_for_model_locked(store: Any, upstreams: List[Dict[str, Any]], requested_model: str) -> List[Dict[str, Any]]:
    model_id = str(requested_model or "").strip()
    if not model_id:
        return upstreams

    supported: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []
    for upstream in upstreams:
        stat = store.stats.get(upstream["id"], store._default_stat())
        probe_models = [
            str(candidate).strip()
            for candidate in (stat.get("last_probe_models") or [])
            if str(candidate).strip()
        ]
        if not probe_models:
            unknown.append(upstream)
            continue
        if model_id in probe_models:
            supported.append(upstream)
    if supported:
        return supported + unknown
    if unknown:
        return unknown
    return upstreams


def get_request_plan(
    store: Any,
    *,
    protocol: str = "openai",
    for_models: bool = False,
    advance_round_robin: bool = False,
    requested_model: str = "",
) -> Dict[str, Any]:
    upstreams = store._get_configured_upstreams_locked(protocol)
    routing = store._get_protocol_routing_locked(protocol)
    auto_enabled = bool(routing.get("auto_routing_enabled", True))
    routing_mode = str(routing.get("routing_mode") or DEFAULT_ROUTING_MODE)
    manual_candidates = [
        item
        for item in store.config["upstreams"]
        if item.get("enabled")
        and item.get("base_url")
        and item.get("api_key")
        and normalize_upstream_protocol(item.get("protocol")) == protocol
    ]
    manual = store._get_manual_upstream_locked(manual_candidates, protocol)

    if not upstreams:
        return {
            "upstreams": [],
            "protocol": protocol,
            "auto_routing_enabled": auto_enabled,
            "routing_mode": routing_mode,
            "manual_active_upstream_id": str(routing.get("manual_active_upstream_id") or ""),
            "can_failover": False,
        }

    if not auto_enabled:
        selected = json.loads(json.dumps(manual)) if manual else None
        selected_list = [selected] if selected else []
        return {
            "upstreams": selected_list,
            "protocol": protocol,
            "auto_routing_enabled": False,
            "routing_mode": "manual_lock",
            "manual_active_upstream_id": selected["id"] if selected else "",
            "can_failover": False,
        }

    candidate_upstreams = filter_upstreams_for_model_locked(store, upstreams, requested_model)
    ready, cooling = store._partition_upstreams_locked(candidate_upstreams)
    ordered_ready = store._apply_routing_mode_locked(ready, protocol, advance_cursor=advance_round_robin)
    ordered_cooling = (
        store._apply_routing_mode_locked(cooling, protocol, advance_cursor=False)
        if not ready
        else [json.loads(json.dumps(item)) for item in cooling]
    )
    ordered = ordered_ready + ordered_cooling

    if for_models and not ordered:
        ordered = store._apply_routing_mode_locked(upstreams, protocol, advance_cursor=False)

    return {
        "upstreams": ordered,
        "protocol": protocol,
        "auto_routing_enabled": True,
        "routing_mode": routing_mode,
        "manual_active_upstream_id": str(routing.get("manual_active_upstream_id") or ""),
        "can_failover": len(ordered) > 1,
    }


def upstream_name_locked(store: Any, upstream_id: str) -> str:
    for upstream in store.config["upstreams"]:
        if upstream["id"] == upstream_id:
            return upstream["name"]
    return ""


def protocol_upstream_counts_locked(store: Any, protocol: str) -> Dict[str, int]:
    upstreams = [item for item in store.config["upstreams"] if normalize_upstream_protocol(item.get("protocol")) == protocol]
    routable = 0
    for item in upstreams:
        summary = store._upstream_subscription_summary_locked(item)
        if item.get("enabled") and item.get("base_url") and item.get("api_key") and summary["available"]:
            routable += 1
    return {
        "total": len(upstreams),
        "enabled": len([item for item in upstreams if item.get("enabled")]),
        "routable": routable,
    }


def local_api_key_statuses_locked(store: Any) -> List[Dict[str, Any]]:
    primary_key_id = primary_local_api_key_entry(store.config["local_api_keys"])["id"]
    local_api_keys: List[Dict[str, Any]] = []
    for entry in store.config.get("local_api_keys") or []:
        local_api_keys.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "enabled": bool(entry.get("enabled", True)),
                "created_at": entry.get("created_at", ""),
                "allowed_protocols": normalize_local_key_protocols(entry.get("allowed_protocols") or entry.get("protocols")),
                "is_primary": entry["id"] == primary_key_id,
                "stats": store._clone(store._merged_local_key_stat_locked(entry["id"])),
            }
        )
    return local_api_keys


def routing_status_locked(store: Any) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    protocol_routing: Dict[str, Dict[str, Any]] = {}
    preview_order_by_protocol: Dict[str, List[Dict[str, Any]]] = {}
    for protocol in UPSTREAM_PROTOCOL_ORDER:
        plan = store.get_request_plan(protocol=protocol, for_models=False, advance_round_robin=False)
        preview_order = [{"id": item["id"], "name": item["name"]} for item in plan["upstreams"]]
        preview_order_by_protocol[protocol] = preview_order
        routing = store._get_protocol_routing_locked(protocol)
        manual_active_id = str(routing.get("manual_active_upstream_id") or "")
        last_used_id = store.last_used_upstream_id_by_protocol.get(protocol, "")
        counts = store._protocol_upstream_counts_locked(protocol)
        protocol_routing[protocol] = {
            "protocol": protocol,
            "auto_routing_enabled": bool(routing.get("auto_routing_enabled", True)),
            "routing_mode": str(routing.get("routing_mode") or DEFAULT_ROUTING_MODE),
            "routing_mode_label": ROUTING_MODE_LABELS.get(str(routing.get("routing_mode") or DEFAULT_ROUTING_MODE), ROUTING_MODE_LABELS[DEFAULT_ROUTING_MODE]),
            "manual_active_upstream_id": manual_active_id,
            "manual_active_upstream_name": store._upstream_name_locked(manual_active_id),
            "preview_order": preview_order,
            "last_used_upstream_id": last_used_id,
            "last_used_upstream_name": store._upstream_name_locked(last_used_id),
            "last_used_at": store.last_used_at_by_protocol.get(protocol, ""),
            "upstream_count": counts["total"],
            "enabled_upstream_count": counts["enabled"],
            "routable_upstream_count": counts["routable"],
        }
    return protocol_routing, preview_order_by_protocol


def get_status(
    store: Any,
    runtime_host: str,
    runtime_port: int,
    *,
    service_state: str = "running",
    service_error: str = "",
    service_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = time.time()
    upstreams: List[Dict[str, Any]] = []
    for upstream in store.config["upstreams"]:
        stat = store._clone(store._merged_upstream_stat_locked(upstream["id"]))
        stat["cooldown_remaining_sec"] = max(0, int(stat.get("cooldown_until", 0.0) - now))
        subscription_summary = store._upstream_subscription_summary_locked(upstream, now_ts=now)
        upstreams.append(
            {
                **store._clone(upstream),
                "stats": stat,
                "subscription_state": subscription_summary["state"],
                "subscription_available": bool(subscription_summary["available"]),
                "subscription_manual_enable_required": bool(subscription_summary["manual_enable_required"]),
                "subscription_next_reset_at": subscription_summary["next_reset_at"],
                "current_subscription_id": subscription_summary.get("current_subscription_id") or "",
                "current_subscription_name": subscription_summary.get("current_subscription_name") or "",
                "current_subscription_kind": subscription_summary.get("current_subscription_kind") or "",
                "subscriptions": subscription_summary["subscriptions"],
            }
        )
    protocol_routing, preview_order_by_protocol = store._routing_status_locked()
    openai_routing = protocol_routing["openai"]
    runtime_urls = store._runtime_urls_locked(runtime_host)
    clients = store.collect_client_binding_statuses(
        runtime_urls["runtime_base_urls"],
        str(store.config.get("local_api_key") or ""),
        service_state=service_state,
        service_details=service_details,
    )
    return {
        "app": project_metadata_payload(),
        "config": store.get_config(),
        "runtime": status_runtime_payload(store.config, runtime_host, runtime_urls),
        "service": {
            "state": service_state,
            "error": service_error,
            "dashboard_url": runtime_urls["dashboard_url"],
            "listen": f"{runtime_host}:{runtime_port}",
            **(store._clone(service_details) if isinstance(service_details, dict) else {}),
        },
        "clients": clients,
        "codex": clients["codex"],
        "local_api_keys": store._local_api_key_statuses_locked(),
        "routing": {
            "auto_routing_enabled": openai_routing["auto_routing_enabled"],
            "routing_mode": openai_routing["routing_mode"],
            "routing_mode_label": openai_routing["routing_mode_label"],
            "manual_active_upstream_id": openai_routing["manual_active_upstream_id"],
            "manual_active_upstream_name": openai_routing["manual_active_upstream_name"],
            "preview_order": openai_routing["preview_order"],
            "preview_order_by_protocol": preview_order_by_protocol,
            "last_used_upstream_id": openai_routing["last_used_upstream_id"],
            "last_used_upstream_name": openai_routing["last_used_upstream_name"],
            "last_used_at": openai_routing["last_used_at"],
            "protocols": protocol_routing,
        },
        "upstreams": upstreams,
    }


def get_usage_series(store: Any, range_key: str) -> Dict[str, Any]:
    store._prune_usage_events_locked()
    return usage_series_payload(range_key, store.usage_events, store.config["upstreams"], store.config.get("local_api_keys") or [])

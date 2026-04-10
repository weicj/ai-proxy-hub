from __future__ import annotations

import time
from typing import Any, Dict, List

from .config_logic import (
    dashboard_runtime_url,
    normalize_endpoint_mode,
    normalize_shared_api_prefixes,
    normalize_split_api_ports,
    protocol_runtime_base_url,
    web_ui_port_from_config,
)
from .constants import DEFAULT_LISTEN_PORT, UPSTREAM_PROTOCOL_ORDER, USAGE_RANGE_CONFIGS
from .network import normalize_usage_range, resolve_usage_window
from .protocols import normalize_upstream_protocol
from .subscriptions import default_subscription_runtime_state
from .utils import safe_float, safe_int


def default_upstream_stat() -> Dict[str, Any]:
    return {
        "success_count": 0,
        "failure_count": 0,
        "request_count": 0,
        "last_status": None,
        "last_error": "",
        "last_attempt_at": "",
        "last_success_at": "",
        "cooldown_until": 0.0,
        "last_latency_ms": None,
        "avg_latency_ms": None,
        "latency_sample_count": 0,
        "last_probe_at": "",
        "last_probe_status": None,
        "last_probe_error": "",
        "last_probe_latency_ms": None,
        "last_probe_models_count": None,
        "subscription_states": {},
        "subscription_manual_enable_required": False,
        "subscription_manual_enable_reason": "",
    }


def default_local_key_stat() -> Dict[str, Any]:
    return {
        "success_count": 0,
        "failure_count": 0,
        "request_count": 0,
        "last_used_at": "",
        "last_success_at": "",
        "last_error": "",
        "last_upstream_id": "",
    }


def merged_stat(current: Dict[str, Any] | None, *, local_key: bool = False) -> Dict[str, Any]:
    base = default_local_key_stat() if local_key else default_upstream_stat()
    base.update(current or {})
    return base


def ensure_stat(container: Dict[str, Dict[str, Any]], key: str, *, local_key: bool = False) -> Dict[str, Any]:
    stat = container.get(key)
    if stat is None:
        stat = default_local_key_stat() if local_key else default_upstream_stat()
        container[key] = stat
    return stat


def load_runtime_state(raw: Dict[str, Any]) -> Dict[str, Any]:
    usage_events: List[Dict[str, Any]] = []
    for event in raw.get("usage_events") or []:
        if not isinstance(event, dict):
            continue
        upstream_id = str(event.get("upstream_id") or "").strip()
        local_key_id = str(event.get("local_key_id") or "").strip()
        ts = safe_float(event.get("ts"), 0.0)
        if not upstream_id or ts <= 0:
            continue
        usage_events.append(
            {
                "ts": ts,
                "upstream_id": upstream_id,
                "local_key_id": local_key_id,
                "success": bool(event.get("success", False)),
            }
        )
    usage_events.sort(key=lambda item: float(item.get("ts", 0.0)))
    return {
        "stats": {
            str(key): {
                **value,
                "subscription_states": {
                    str(subscription_id): {
                        **default_subscription_runtime_state(),
                        **runtime_state,
                    }
                    for subscription_id, runtime_state in (value.get("subscription_states") or {}).items()
                    if isinstance(subscription_id, str) and isinstance(runtime_state, dict)
                },
                "subscription_manual_enable_required": bool(value.get("subscription_manual_enable_required", False)),
                "subscription_manual_enable_reason": str(value.get("subscription_manual_enable_reason") or "").strip(),
            }
            for key, value in (raw.get("stats") or {}).items()
            if isinstance(key, str) and isinstance(value, dict)
        },
        "local_key_stats": {
            str(key): value
            for key, value in (raw.get("local_key_stats") or {}).items()
            if isinstance(key, str) and isinstance(value, dict)
        },
        "usage_events": usage_events,
        "round_robin_cursor_by_protocol": {
            protocol: safe_int((raw.get("round_robin_cursor_by_protocol") or {}).get(protocol), 0)
            for protocol in UPSTREAM_PROTOCOL_ORDER
        },
        "last_used_upstream_id_by_protocol": {
            protocol: str((raw.get("last_used_upstream_id_by_protocol") or {}).get(protocol) or "").strip()
            for protocol in UPSTREAM_PROTOCOL_ORDER
        },
        "last_used_at_by_protocol": {
            protocol: str((raw.get("last_used_at_by_protocol") or {}).get(protocol) or "").strip()
            for protocol in UPSTREAM_PROTOCOL_ORDER
        },
    }


def prune_usage_events(usage_events: List[Dict[str, Any]], *, now_ts: float | None = None) -> List[Dict[str, Any]]:
    cutoff = (time.time() if now_ts is None else now_ts) - max(config["window_seconds"] for config in USAGE_RANGE_CONFIGS.values())
    return [event for event in usage_events if event["ts"] >= cutoff]


def runtime_state_payload(
    *,
    stats: Dict[str, Dict[str, Any]],
    local_key_stats: Dict[str, Dict[str, Any]],
    usage_events: List[Dict[str, Any]],
    round_robin_cursor_by_protocol: Dict[str, int],
    last_used_upstream_id_by_protocol: Dict[str, str],
    last_used_at_by_protocol: Dict[str, str],
) -> Dict[str, Any]:
    return {
        "version": 1,
        "stats": stats,
        "local_key_stats": local_key_stats,
        "usage_events": usage_events,
        "round_robin_cursor_by_protocol": round_robin_cursor_by_protocol,
        "last_used_upstream_id_by_protocol": last_used_upstream_id_by_protocol,
        "last_used_at_by_protocol": last_used_at_by_protocol,
    }


def sync_stats_state(
    config: Dict[str, Any],
    *,
    stats: Dict[str, Dict[str, Any]],
    local_key_stats: Dict[str, Dict[str, Any]],
    last_used_upstream_id_by_protocol: Dict[str, str],
    last_used_at_by_protocol: Dict[str, str],
    round_robin_cursor_by_protocol: Dict[str, int],
) -> Dict[str, Any]:
    next_stats: Dict[str, Dict[str, Any]] = {}
    for upstream in config["upstreams"]:
        stat = merged_stat(stats.get(upstream["id"]))
        subscription_ids = {
            str(subscription.get("id") or "").strip()
            for subscription in (upstream.get("subscriptions") or [])
            if isinstance(subscription, dict) and str(subscription.get("id") or "").strip()
        }
        current_states = stat.get("subscription_states") if isinstance(stat.get("subscription_states"), dict) else {}
        stat["subscription_states"] = {
            subscription_id: {
                **default_subscription_runtime_state(),
                **runtime_state,
            }
            for subscription_id, runtime_state in current_states.items()
            if subscription_id in subscription_ids and isinstance(runtime_state, dict)
        }
        for subscription_id in subscription_ids:
            stat["subscription_states"].setdefault(subscription_id, default_subscription_runtime_state())
        next_stats[upstream["id"]] = stat
    next_local_key_stats = {
        local_key["id"]: merged_stat(local_key_stats.get(local_key["id"]), local_key=True)
        for local_key in config.get("local_api_keys", [])
    }
    valid_ids_by_protocol = {
        protocol: {
            upstream["id"]
            for upstream in config["upstreams"]
            if normalize_upstream_protocol(upstream.get("protocol")) == protocol
        }
        for protocol in UPSTREAM_PROTOCOL_ORDER
    }
    next_last_used_ids = dict(last_used_upstream_id_by_protocol)
    next_last_used_at = dict(last_used_at_by_protocol)
    next_round_robin = {
        protocol: max(0, int(round_robin_cursor_by_protocol.get(protocol, 0)))
        for protocol in UPSTREAM_PROTOCOL_ORDER
    }
    for protocol in UPSTREAM_PROTOCOL_ORDER:
        if next_last_used_ids.get(protocol) not in valid_ids_by_protocol[protocol]:
            next_last_used_ids[protocol] = ""
            next_last_used_at[protocol] = ""
    return {
        "stats": next_stats,
        "local_key_stats": next_local_key_stats,
        "last_used_upstream_id_by_protocol": next_last_used_ids,
        "last_used_at_by_protocol": next_last_used_at,
        "round_robin_cursor_by_protocol": next_round_robin,
    }


def runtime_urls(config: Dict[str, Any], runtime_host: str) -> Dict[str, Any]:
    runtime_base_url = protocol_runtime_base_url(config, runtime_host, "openai")
    runtime_base_urls = {
        "codex": runtime_base_url,
        "claude": protocol_runtime_base_url(config, runtime_host, "anthropic"),
        "gemini": protocol_runtime_base_url(config, runtime_host, "gemini"),
        "local_llm": protocol_runtime_base_url(config, runtime_host, "local_llm"),
    }
    return {
        "runtime_base_url": runtime_base_url,
        "runtime_base_urls": runtime_base_urls,
        "dashboard_url": dashboard_runtime_url(config, runtime_host),
    }


def status_runtime_payload(config: Dict[str, Any], runtime_host: str, runtime_urls_payload: Dict[str, Any]) -> Dict[str, Any]:
    listen_port = safe_int(config.get("listen_port"), DEFAULT_LISTEN_PORT)
    return {
        "host": runtime_host,
        "port": web_ui_port_from_config(config),
        "base_url": runtime_urls_payload["runtime_base_url"],
        "dashboard_url": runtime_urls_payload["dashboard_url"],
        "openai_base_url": runtime_urls_payload["runtime_base_url"],
        "claude_base_url": runtime_urls_payload["runtime_base_urls"]["claude"],
        "gemini_base_url": runtime_urls_payload["runtime_base_urls"]["gemini"],
        "local_llm_base_url": runtime_urls_payload["runtime_base_urls"]["local_llm"],
        "listen_host": str(config.get("listen_host") or runtime_host or "127.0.0.1"),
        "listen_port": listen_port,
        "endpoint_mode": normalize_endpoint_mode(config.get("endpoint_mode")),
        "shared_api_prefixes": normalize_shared_api_prefixes(config.get("shared_api_prefixes")),
        "split_api_ports": normalize_split_api_ports(config.get("split_api_ports"), listen_port),
        "web_ui_port": web_ui_port_from_config(config),
    }


def usage_series_payload(
    range_key: str,
    usage_events: List[Dict[str, Any]],
    upstreams_config: List[Dict[str, Any]],
    local_keys_config: List[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_range = normalize_usage_range(range_key)
    window = resolve_usage_window(normalized_range)
    bucket_seconds = int(window["bucket_seconds"])
    bucket_count = int(window["bucket_count"])
    start = float(window["start"])
    end = float(window["end"])
    buckets = []
    upstream_lookup = {
        upstream["id"]: {
            "id": upstream["id"],
            "name": upstream["name"],
            "protocol": normalize_upstream_protocol(upstream.get("protocol")),
        }
        for upstream in upstreams_config
    }
    local_key_lookup = {
        local_key["id"]: {
            "id": local_key["id"],
            "name": local_key["name"],
        }
        for local_key in local_keys_config
    }
    for index in range(bucket_count):
        bucket_start = start + (index * bucket_seconds)
        bucket_end = bucket_start + bucket_seconds
        buckets.append(
            {
                "start_ts": int(bucket_start * 1000),
                "end_ts": int(bucket_end * 1000),
                "total": 0,
                "by_upstream": {},
                "by_local_key": {},
                "_pairs": {},
            }
        )

    for event in usage_events:
        if event["ts"] < start or event["ts"] >= end:
            continue
        bucket_index = int((event["ts"] - start) // bucket_seconds)
        if bucket_index < 0 or bucket_index >= bucket_count:
            continue
        bucket = buckets[bucket_index]
        local_key_id = str(event.get("local_key_id") or "")
        bucket["total"] += 1
        bucket["by_upstream"][event["upstream_id"]] = bucket["by_upstream"].get(event["upstream_id"], 0) + 1
        bucket["by_local_key"][local_key_id] = bucket["by_local_key"].get(local_key_id, 0) + 1
        pair_key = f"{local_key_id}\x1f{event['upstream_id']}"
        bucket["_pairs"][pair_key] = bucket["_pairs"].get(pair_key, 0) + 1

    for bucket in buckets:
        pairs = []
        for pair_key, count in bucket.pop("_pairs", {}).items():
            local_key_id, upstream_id = pair_key.split("\x1f", 1)
            pairs.append(
                {
                    "local_key_id": local_key_id,
                    "upstream_id": upstream_id,
                    "count": count,
                }
            )
        bucket["pairs"] = pairs

    max_total = max((bucket["total"] for bucket in buckets), default=0)
    upstreams = [
        {
            "id": upstream["id"],
            "name": upstream["name"],
            "protocol": normalize_upstream_protocol(upstream.get("protocol")),
        }
        for upstream in upstreams_config
        if upstream["id"] in upstream_lookup
    ]
    local_keys = [
        {
            "id": local_key["id"],
            "name": local_key["name"],
        }
        for local_key in local_keys_config
        if local_key["id"] in local_key_lookup
    ]
    return {
        "range": normalized_range,
        "metric": "requests",
        "bucket_seconds": bucket_seconds,
        "bucket_count": bucket_count,
        "window_seconds": int(end - start),
        "max_total": max_total,
        "upstreams": upstreams,
        "local_keys": local_keys,
        "buckets": buckets,
    }

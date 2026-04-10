from __future__ import annotations

import json
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import legacy_impl as _legacy
from .config_logic import (
    default_model_settings_from_config,
    default_protocol_routing_settings,
    normalize_config,
    normalize_protocol_routing_section,
    web_ui_port_from_config,
)
from .constants import (
    DEFAULT_ROUTING_MODE,
    ROUTING_MODE_LABELS,
    UPSTREAM_PROTOCOL_ORDER,
)
from .file_io import load_config_file, load_optional_json_file, runtime_state_path, write_json
from .local_keys import local_key_allows_protocol, normalize_local_key_protocols, primary_local_api_key_entry
from .network_proxy import is_subscription_exhaustion_signal
from .protocols import normalize_upstream_protocol
from .store_helpers import (
    default_local_key_stat,
    default_upstream_stat,
    ensure_stat,
    load_runtime_state,
    merged_stat,
    prune_usage_events,
    runtime_state_payload,
    runtime_urls,
    status_runtime_payload,
    sync_stats_state,
    usage_series_payload,
)
from .subscriptions import (
    choose_active_subscription,
    current_local_datetime,
    default_subscription_runtime_state,
    describe_subscription,
    record_subscription_failure,
    record_subscription_success,
)
from .store_queries import (
    apply_routing_mode_locked,
    get_request_plan as build_request_plan,
    get_status as build_status_payload,
    get_usage_series as build_usage_series,
    latency_sort_key_locked,
    local_api_key_statuses_locked,
    partition_upstreams_locked,
    protocol_upstream_counts_locked,
    routing_status_locked,
    upstream_name_locked,
)
from .utils import now_iso


def collect_client_binding_statuses(*args, **kwargs):
    return _legacy.collect_client_binding_statuses(*args, **kwargs)

class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.state_path = runtime_state_path(path)
        self.lock = threading.RLock()
        self.config = load_config_file(path)
        self.stats: Dict[str, Dict[str, Any]] = {}
        self.local_key_stats: Dict[str, Dict[str, Any]] = {}
        self.usage_events: List[Dict[str, Any]] = []
        self.round_robin_cursor_by_protocol = {protocol: 0 for protocol in UPSTREAM_PROTOCOL_ORDER}
        self.last_used_upstream_id_by_protocol = {protocol: "" for protocol in UPSTREAM_PROTOCOL_ORDER}
        self.last_used_at_by_protocol = {protocol: "" for protocol in UPSTREAM_PROTOCOL_ORDER}
        self._load_runtime_state_locked()
        self._sync_stats_locked()

    def collect_client_binding_statuses(self, *args, **kwargs):
        return collect_client_binding_statuses(*args, **kwargs)

    def _clone(self, value: Any) -> Any:
        return json.loads(json.dumps(value))

    def _default_stat(self) -> Dict[str, Any]:
        return default_upstream_stat()

    def _default_local_key_stat(self) -> Dict[str, Any]:
        return default_local_key_stat()

    def _merged_upstream_stat_locked(self, upstream_id: str) -> Dict[str, Any]:
        return merged_stat(self.stats.get(upstream_id))

    def _merged_local_key_stat_locked(self, local_key_id: str) -> Dict[str, Any]:
        return merged_stat(self.local_key_stats.get(local_key_id), local_key=True)

    def _ensure_upstream_stat_locked(self, upstream_id: str) -> Dict[str, Any]:
        return ensure_stat(self.stats, upstream_id)

    def _ensure_subscription_state_locked(self, upstream_id: str, subscription_id: str) -> Dict[str, Any]:
        stat = self._ensure_upstream_stat_locked(upstream_id)
        states = stat.setdefault("subscription_states", {})
        current = states.get(subscription_id)
        if not isinstance(current, dict):
            legacy_states = stat.get("subscription_stats") if isinstance(stat.get("subscription_stats"), dict) else {}
            legacy_state = legacy_states.get(subscription_id)
            if isinstance(legacy_state, dict):
                current = legacy_state
        if not isinstance(current, dict):
            current = {}
        next_state = {**default_subscription_runtime_state(), **current}
        states[subscription_id] = next_state
        return next_state

    def _ensure_local_key_stat_locked(self, local_key_id: str) -> Dict[str, Any]:
        return ensure_stat(self.local_key_stats, local_key_id, local_key=True)

    def _load_runtime_state_locked(self) -> None:
        raw = load_optional_json_file(self.state_path)
        loaded = load_runtime_state(raw)
        self.stats = loaded["stats"]
        self.local_key_stats = loaded["local_key_stats"]
        self.usage_events = loaded["usage_events"]
        self.round_robin_cursor_by_protocol = loaded["round_robin_cursor_by_protocol"]
        self.last_used_upstream_id_by_protocol = loaded["last_used_upstream_id_by_protocol"]
        self.last_used_at_by_protocol = loaded["last_used_at_by_protocol"]
        self._prune_usage_events_locked()

    def _runtime_state_payload_locked(self) -> Dict[str, Any]:
        self._prune_usage_events_locked()
        return runtime_state_payload(
            stats=self.stats,
            local_key_stats=self.local_key_stats,
            usage_events=self.usage_events,
            round_robin_cursor_by_protocol=self.round_robin_cursor_by_protocol,
            last_used_upstream_id_by_protocol=self.last_used_upstream_id_by_protocol,
            last_used_at_by_protocol=self.last_used_at_by_protocol,
        )

    def _save_runtime_state_locked(self) -> None:
        try:
            write_json(self.state_path, self._runtime_state_payload_locked())
        except (OSError, PermissionError):
            return

    def _sync_stats_locked(self) -> None:
        synced = sync_stats_state(
            self.config,
            stats=self.stats,
            local_key_stats=self.local_key_stats,
            last_used_upstream_id_by_protocol=self.last_used_upstream_id_by_protocol,
            last_used_at_by_protocol=self.last_used_at_by_protocol,
            round_robin_cursor_by_protocol=self.round_robin_cursor_by_protocol,
        )
        self.stats = synced["stats"]
        self.local_key_stats = synced["local_key_stats"]
        self.last_used_upstream_id_by_protocol = synced["last_used_upstream_id_by_protocol"]
        self.last_used_at_by_protocol = synced["last_used_at_by_protocol"]
        self.round_robin_cursor_by_protocol = synced["round_robin_cursor_by_protocol"]

    def _prune_usage_events_locked(self) -> None:
        self.usage_events = prune_usage_events(self.usage_events)

    def _find_upstream_locked(self, upstream_id: str) -> Optional[Dict[str, Any]]:
        for upstream in self.config["upstreams"]:
            if upstream["id"] == upstream_id:
                return upstream
        return None

    def _upstream_subscription_summary_locked(self, upstream: Dict[str, Any], *, now_ts: Optional[float] = None) -> Dict[str, Any]:
        upstream_id = upstream["id"]
        stat = self._ensure_upstream_stat_locked(upstream_id)
        manual_enable_required = bool(stat.get("subscription_manual_enable_required", False))
        descriptions: List[Dict[str, Any]] = []
        has_valid = False
        has_available = False
        has_unlimited_available = False
        next_reset_at = ""
        changed = False

        for subscription in upstream.get("subscriptions") or []:
            runtime_state = self._ensure_subscription_state_locked(upstream_id, subscription["id"])
            description = describe_subscription(subscription, runtime_state, now_ts=now_ts)
            if (
                subscription.get("kind") == "periodic"
                and description.get("state") == "ready"
                and str(runtime_state.get("exhausted_cycle_key") or "")
                and str(runtime_state.get("exhausted_cycle_key") or "") != str(description.get("cycle_key") or "")
            ):
                runtime_state["exhausted_cycle_key"] = ""
                runtime_state["exhausted_at"] = ""
                changed = True
            if description["valid"]:
                has_valid = True
            if description["available"]:
                has_available = True
                if description["kind"] == "unlimited":
                    has_unlimited_available = True
            next_reset_candidate = str(description.get("next_reset_at") or "")
            if description.get("state") in {"exhausted", "pending_refresh", "awaiting_probe"} and next_reset_candidate:
                if not next_reset_at or next_reset_candidate < next_reset_at:
                    next_reset_at = next_reset_candidate
            descriptions.append(
                {
                    **description,
                    "last_failure_at": str(runtime_state.get("last_failure_at") or ""),
                    "last_success_at": str(runtime_state.get("last_success_at") or ""),
                    "exhausted_at": str(runtime_state.get("exhausted_at") or ""),
                    "consecutive_failures": int(runtime_state.get("consecutive_failures") or 0),
                    "consecutive_failure_days": int(runtime_state.get("consecutive_failure_days") or 0),
                }
            )

        if not has_valid:
            if not manual_enable_required:
                stat["subscription_manual_enable_required"] = True
                stat["subscription_manual_enable_reason"] = "all_subscriptions_invalid"
                manual_enable_required = True
                changed = True
            state = "expired"
            available = False
        elif manual_enable_required and has_available:
            state = "manual_lock"
            available = False
        elif has_available:
            state = "ready"
            available = True
        elif next_reset_at:
            state = "temporary_exhausted"
            available = False
        else:
            state = "quota_exhausted"
            available = False

        if changed:
            self._save_runtime_state_locked()

        current_subscription = choose_active_subscription([item for item in descriptions if item.get("available")])

        return {
            "state": state,
            "available": available,
            "manual_enable_required": manual_enable_required,
            "next_reset_at": next_reset_at,
            "has_unlimited_available": has_unlimited_available,
            "current_subscription_id": str(current_subscription.get("id") or "") if current_subscription else "",
            "current_subscription_name": str(current_subscription.get("name") or "") if current_subscription else "",
            "current_subscription_kind": str(current_subscription.get("kind") or "") if current_subscription else "",
            "subscriptions": descriptions,
        }

    def _mark_subscription_success_locked(self, upstream_id: str) -> None:
        upstream = self._find_upstream_locked(upstream_id)
        if not upstream:
            return
        summary = self._upstream_subscription_summary_locked(upstream)
        current_subscription_id = str(summary.get("current_subscription_id") or "")
        success_at = now_iso()
        target_subscription_id = current_subscription_id
        if not target_subscription_id:
            recoverable = choose_active_subscription(
                [
                    item
                    for item in summary["subscriptions"]
                    if item.get("valid") and item.get("state") in {"awaiting_probe", "exhausted", "pending_refresh"}
                ]
            )
            target_subscription_id = str(recoverable.get("id") or "") if recoverable else ""
        if not target_subscription_id:
            return
        for subscription in upstream.get("subscriptions") or []:
            if subscription["id"] != target_subscription_id:
                continue
            runtime_state = self._ensure_subscription_state_locked(upstream_id, subscription["id"])
            runtime_state["last_success_at"] = success_at
            runtime_state["consecutive_failures"] = 0
            runtime_state["consecutive_failure_days"] = 0
            runtime_state["last_failure_day"] = ""
            runtime_state["exhausted"] = False
            runtime_state["exhausted_at"] = ""
            runtime_state["exhausted_cycle_key"] = ""
            return

    def _mark_subscription_failure_locked(self, upstream_id: str) -> None:
        upstream = self._find_upstream_locked(upstream_id)
        if not upstream:
            return
        summary = self._upstream_subscription_summary_locked(upstream)
        if summary["has_unlimited_available"]:
            return
        current_subscription_id = str(summary.get("current_subscription_id") or "")
        if not current_subscription_id:
            return
        current_time = now_iso()
        today = current_local_datetime().date()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_iso = today.isoformat()
        changed = False
        subscription_meta = {
            item["id"]: item
            for item in summary["subscriptions"]
            if isinstance(item, dict) and item.get("id")
        }
        for subscription in upstream.get("subscriptions") or []:
            if subscription["id"] != current_subscription_id or subscription.get("kind") not in {"periodic", "quota"}:
                continue
            runtime_state = self._ensure_subscription_state_locked(upstream_id, subscription["id"])
            runtime_state["last_failure_at"] = current_time
            runtime_state["consecutive_failures"] = int(runtime_state.get("consecutive_failures") or 0) + 1
            last_failure_day = str(runtime_state.get("last_failure_day") or "")
            if last_failure_day == today_iso:
                runtime_state["consecutive_failure_days"] = max(1, int(runtime_state.get("consecutive_failure_days") or 0))
            elif last_failure_day == yesterday:
                runtime_state["consecutive_failure_days"] = int(runtime_state.get("consecutive_failure_days") or 0) + 1
                runtime_state["last_failure_day"] = today_iso
            else:
                runtime_state["consecutive_failure_days"] = 1
                runtime_state["last_failure_day"] = today_iso

            mode = str(subscription.get("failure_mode") or "consecutive_failures")
            threshold = max(1, int(subscription.get("failure_threshold") or 1))
            should_exhaust = (
                int(runtime_state.get("consecutive_failure_days") or 0) >= threshold
                if mode == "consecutive_days"
                else int(runtime_state.get("consecutive_failures") or 0) >= threshold
            )
            if not should_exhaust:
                break
            if subscription["kind"] == "periodic":
                if not bool(runtime_state.get("exhausted")):
                    runtime_state["exhausted"] = True
                    changed = True
                cycle_key = str((subscription_meta.get(subscription["id"]) or {}).get("cycle_key") or "")
                if cycle_key and str(runtime_state.get("exhausted_cycle_key") or "") != cycle_key:
                    runtime_state["exhausted_cycle_key"] = cycle_key
                    changed = True
            else:
                if not bool(runtime_state.get("exhausted")):
                    runtime_state["exhausted"] = True
                    changed = True
            runtime_state["exhausted_at"] = current_time
            runtime_state["consecutive_failures"] = 0
            runtime_state["consecutive_failure_days"] = 0
            break

    def get_periodic_probe_candidates(self, *, protocol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            if protocol is not None and not bool(self._get_protocol_routing_locked(protocol).get("auto_routing_enabled", True)):
                return []
            now_ts = time.time()
            candidates: List[Dict[str, Any]] = []
            for upstream in self.config["upstreams"]:
                if (
                    not upstream.get("enabled")
                    or not upstream.get("base_url")
                    or not upstream.get("api_key")
                    or (protocol is not None and normalize_upstream_protocol(upstream.get("protocol")) != protocol)
                ):
                    continue
                summary = self._upstream_subscription_summary_locked(upstream, now_ts=now_ts)
                awaiting_probe = [item for item in summary["subscriptions"] if item.get("state") == "awaiting_probe"]
                if not awaiting_probe:
                    continue
                chosen = choose_active_subscription(awaiting_probe) or awaiting_probe[0]
                candidates.append(
                    {
                        "upstream": self._clone(upstream),
                        "subscription_id": str(chosen.get("id") or ""),
                        "subscription_name": str(chosen.get("name") or ""),
                        "cycle_key": str(chosen.get("cycle_key") or ""),
                    }
                )
            return candidates

    def record_periodic_probe_success(
        self,
        upstream_id: str,
        subscription_id: str,
        *,
        status: Optional[int],
        latency_ms: Optional[float] = None,
        models_count: Optional[int] = None,
    ) -> None:
        with self.lock:
            upstream = self._find_upstream_locked(upstream_id)
            if not upstream or not subscription_id:
                return
            stat = self._ensure_upstream_stat_locked(upstream_id)
            stat["last_probe_at"] = now_iso()
            stat["last_probe_status"] = status
            stat["last_probe_error"] = ""
            stat["last_probe_latency_ms"] = round(float(latency_ms), 2) if latency_ms is not None else None
            stat["last_probe_models_count"] = models_count
            stat["cooldown_until"] = 0.0
            record_subscription_success(upstream, stat, subscription_id)
            self._save_runtime_state_locked()

    def record_periodic_probe_failure(
        self,
        upstream_id: str,
        subscription_id: str,
        *,
        error: str,
        status: Optional[int] = None,
        latency_ms: Optional[float] = None,
        models_count: Optional[int] = None,
    ) -> None:
        with self.lock:
            upstream = self._find_upstream_locked(upstream_id)
            if not upstream or not subscription_id:
                return
            stat = self._ensure_upstream_stat_locked(upstream_id)
            stat["last_probe_at"] = now_iso()
            stat["last_probe_status"] = status
            stat["last_probe_error"] = str(error or "")
            stat["last_probe_latency_ms"] = round(float(latency_ms), 2) if latency_ms is not None else None
            stat["last_probe_models_count"] = models_count
            stat["cooldown_until"] = 0.0
            record_subscription_failure(upstream, stat, subscription_id, error=error, exhaustion_signal=True)
            self._save_runtime_state_locked()

    def get_config(self) -> Dict[str, Any]:
        with self.lock:
            return self._clone(self.config)

    def save_config(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        config = normalize_config(raw)
        with self.lock:
            previous_by_id = {
                upstream["id"]: upstream
                for upstream in self.config.get("upstreams") or []
                if isinstance(upstream, dict) and upstream.get("id")
            }
            self.config = config
            self._sync_stats_locked()
            for upstream in self.config.get("upstreams") or []:
                previous = previous_by_id.get(upstream["id"]) or {}
                if upstream.get("enabled") and not previous.get("enabled", True):
                    stat = self._ensure_upstream_stat_locked(upstream["id"])
                    stat["subscription_manual_enable_required"] = False
                    stat["subscription_manual_enable_reason"] = ""
            write_json(self.path, self.config)
            self._save_runtime_state_locked()
            return self.get_config()

    def get_retryable_statuses(self) -> List[int]:
        with self.lock:
            return list(self.config["retryable_statuses"])

    def get_timeout(self) -> int:
        with self.lock:
            return int(self.config["request_timeout_sec"])

    def get_local_api_key(self) -> str:
        with self.lock:
            return str(primary_local_api_key_entry(self.config["local_api_keys"])["key"])

    def get_local_api_keys(self) -> List[Dict[str, Any]]:
        with self.lock:
            return self._clone(self.config.get("local_api_keys") or [])

    def match_local_api_key(self, token: str, protocol: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.lock:
            for entry in self.config.get("local_api_keys") or []:
                if (
                    entry.get("enabled", True)
                    and str(entry.get("key") or "") == str(token or "")
                    and (protocol is None or local_key_allows_protocol(entry, protocol))
                ):
                    return self._clone(entry)
        return None

    def get_default_model_settings(self, protocol: str = "openai") -> Dict[str, str]:
        with self.lock:
            return default_model_settings_from_config(self.config, protocol)

    def record_success(
        self,
        upstream_id: str,
        status: int,
        latency_ms: Optional[float] = None,
        *,
        local_key_id: str = "",
    ) -> None:
        with self.lock:
            stat = self._ensure_upstream_stat_locked(upstream_id)
            stat["success_count"] += 1
            stat["request_count"] += 1
            stat["last_status"] = status
            stat["last_error"] = ""
            stat["last_attempt_at"] = now_iso()
            stat["last_success_at"] = stat["last_attempt_at"]
            stat["cooldown_until"] = 0.0
            if latency_ms is not None:
                rounded = round(float(latency_ms), 2)
                stat["last_latency_ms"] = rounded
                samples = int(stat.get("latency_sample_count") or 0)
                previous_avg = stat.get("avg_latency_ms")
                if previous_avg is None or samples <= 0:
                    stat["avg_latency_ms"] = rounded
                    stat["latency_sample_count"] = 1
                else:
                    stat["avg_latency_ms"] = round(((float(previous_avg) * samples) + rounded) / (samples + 1), 2)
                    stat["latency_sample_count"] = samples + 1
            protocol = self._upstream_protocol_locked(upstream_id)
            self.last_used_upstream_id_by_protocol[protocol] = upstream_id
            self.last_used_at_by_protocol[protocol] = stat["last_attempt_at"]
            self._mark_subscription_success_locked(upstream_id)
            self.usage_events.append(
                {
                    "ts": time.time(),
                    "upstream_id": upstream_id,
                    "local_key_id": str(local_key_id or ""),
                    "success": True,
                }
            )
            self._prune_usage_events_locked()
            self._save_runtime_state_locked()

    def record_failure(
        self,
        upstream_id: str,
        *,
        status: Optional[int],
        error: str,
        cooldown: bool,
        exhaustion_signal: Optional[bool] = None,
        local_key_id: str = "",
    ) -> None:
        with self.lock:
            stat = self._ensure_upstream_stat_locked(upstream_id)
            stat["failure_count"] += 1
            stat["request_count"] += 1
            stat["last_status"] = status
            stat["last_error"] = error
            stat["last_attempt_at"] = now_iso()
            should_mark_subscription_failure = (
                exhaustion_signal
                if exhaustion_signal is not None
                else is_subscription_exhaustion_signal(status, error)
            )
            if cooldown and should_mark_subscription_failure:
                self._mark_subscription_failure_locked(upstream_id)
            if cooldown:
                stat["cooldown_until"] = time.time() + int(self.config["cooldown_seconds"])
            self.usage_events.append(
                {
                    "ts": time.time(),
                    "upstream_id": upstream_id,
                    "local_key_id": str(local_key_id or ""),
                    "success": False,
                }
            )
            self._prune_usage_events_locked()
            self._save_runtime_state_locked()

    def record_probe_result(
        self,
        upstream_id: str,
        *,
        status: Optional[int],
        error: str = "",
        latency_ms: Optional[float] = None,
        models_count: Optional[int] = None,
    ) -> None:
        with self.lock:
            stat = self._ensure_upstream_stat_locked(upstream_id)
            stat["last_probe_at"] = now_iso()
            stat["last_probe_status"] = status
            stat["last_probe_error"] = error
            stat["last_probe_latency_ms"] = round(float(latency_ms), 2) if latency_ms is not None else None
            stat["last_probe_models_count"] = models_count
            self._save_runtime_state_locked()

    def record_local_key_result(self, local_key_id: str, *, success: bool, upstream_id: str = "", error: str = "") -> None:
        with self.lock:
            if not local_key_id:
                return
            stat = self._ensure_local_key_stat_locked(local_key_id)
            stat["request_count"] += 1
            stat["last_used_at"] = now_iso()
            stat["last_upstream_id"] = upstream_id
            stat["last_error"] = "" if success else str(error or "")
            if success:
                stat["success_count"] += 1
                stat["last_success_at"] = stat["last_used_at"]
            else:
                stat["failure_count"] += 1
            self._save_runtime_state_locked()

    def _get_configured_upstreams_locked(self, protocol: Optional[str] = None) -> List[Dict[str, Any]]:
        configured: List[Dict[str, Any]] = []
        for item in self.config["upstreams"]:
            if (
                not item["enabled"]
                or not item["base_url"]
                or not item["api_key"]
                or (protocol is not None and normalize_upstream_protocol(item.get("protocol")) != protocol)
            ):
                continue
            subscription_summary = self._upstream_subscription_summary_locked(item)
            if subscription_summary["available"]:
                configured.append(item)
        return configured

    def _get_protocol_routing_locked(self, protocol: str) -> Dict[str, Any]:
        routing_map = self.config.get("routing_by_protocol") if isinstance(self.config.get("routing_by_protocol"), dict) else {}
        defaults = default_protocol_routing_settings(self.config["upstreams"], protocol)
        return normalize_protocol_routing_section(
            routing_map.get(protocol),
            protocol=protocol,
            upstreams=self.config["upstreams"],
            defaults=defaults,
        )

    def _upstream_protocol_locked(self, upstream_id: str) -> str:
        for upstream in self.config["upstreams"]:
            if upstream["id"] == upstream_id:
                return normalize_upstream_protocol(upstream.get("protocol"))
        return "openai"

    def _get_manual_upstream_locked(self, upstreams: List[Dict[str, Any]], protocol: str) -> Optional[Dict[str, Any]]:
        manual_id = str(self._get_protocol_routing_locked(protocol).get("manual_active_upstream_id") or "")
        for upstream in upstreams:
            if upstream["id"] == manual_id:
                return upstream
        return upstreams[0] if upstreams else None

    def _partition_upstreams_locked(self, upstreams: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return partition_upstreams_locked(self, upstreams)

    def _latency_sort_key_locked(self, upstream_id: str, index: int) -> tuple[float, int]:
        return latency_sort_key_locked(self, upstream_id, index)

    def _apply_routing_mode_locked(self, upstreams: List[Dict[str, Any]], protocol: str, *, advance_cursor: bool) -> List[Dict[str, Any]]:
        return apply_routing_mode_locked(self, upstreams, protocol, advance_cursor=advance_cursor)

    def get_request_plan(self, *, protocol: str = "openai", for_models: bool = False, advance_round_robin: bool = False) -> Dict[str, Any]:
        with self.lock:
            return build_request_plan(self, protocol=protocol, for_models=for_models, advance_round_robin=advance_round_robin)

    def _upstream_name_locked(self, upstream_id: str) -> str:
        return upstream_name_locked(self, upstream_id)

    def _protocol_upstream_counts_locked(self, protocol: str) -> Dict[str, int]:
        return protocol_upstream_counts_locked(self, protocol)

    def _runtime_urls_locked(self, runtime_host: str) -> Dict[str, Any]:
        return runtime_urls(self.config, runtime_host)

    def _local_api_key_statuses_locked(self) -> List[Dict[str, Any]]:
        return local_api_key_statuses_locked(self)

    def _routing_status_locked(self) -> tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        return routing_status_locked(self)

    def get_status(
        self,
        runtime_host: str,
        runtime_port: int,
        *,
        service_state: str = "running",
        service_error: str = "",
        service_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self.lock:
            return build_status_payload(
                self,
                runtime_host,
                web_ui_port_from_config(self.config),
                service_state=service_state,
                service_error=service_error,
                service_details=service_details,
            )

    def get_usage_series(self, range_key: str) -> Dict[str, Any]:
        with self.lock:
            return build_usage_series(self, range_key)

    def get_upstream(self, upstream_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            for upstream in self.config["upstreams"]:
                if upstream["id"] == upstream_id:
                    return self._clone(upstream)
        return None

    def reactivate_upstream(self, upstream_id: str) -> Dict[str, Any]:
        with self.lock:
            upstream = self._find_upstream_locked(upstream_id)
            if not upstream:
                return {"ok": False, "message": "upstream_not_found"}
            stat = self._ensure_upstream_stat_locked(upstream_id)
            stat["subscription_manual_enable_required"] = False
            stat["subscription_manual_enable_reason"] = ""
            stat["cooldown_until"] = 0.0
            for subscription in upstream.get("subscriptions") or []:
                runtime_state = self._ensure_subscription_state_locked(upstream_id, subscription["id"])
                runtime_state["exhausted"] = False
                runtime_state["exhausted_cycle_key"] = ""
                runtime_state["exhausted_at"] = ""
                runtime_state["consecutive_failures"] = 0
                runtime_state["consecutive_failure_days"] = 0
                runtime_state["last_failure_day"] = ""
            self._save_runtime_state_locked()
            return {"ok": True, "message": "reactivated", "upstream_id": upstream_id}

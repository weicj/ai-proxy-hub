from __future__ import annotations

import secrets
import time
from datetime import date, datetime, time as datetime_time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .utils import safe_int


SUBSCRIPTION_KINDS = ("unlimited", "periodic", "quota")
DEFAULT_SUBSCRIPTION_KIND = "unlimited"
DEFAULT_QUOTA_FAILURE_DAYS = 2
DEFAULT_REFRESH_RESET_TIME = "00:00"


def current_local_datetime() -> datetime:
    return datetime.fromtimestamp(time.time()).astimezone().replace(tzinfo=None)


def iso_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def subscription_default_failure_mode(kind: str) -> str:
    normalized_kind = normalize_subscription_kind(kind)
    return "consecutive_days" if normalized_kind == "quota" else "consecutive_failures"


def subscription_default_failure_threshold(kind: str) -> int:
    normalized_kind = normalize_subscription_kind(kind)
    return DEFAULT_QUOTA_FAILURE_DAYS if normalized_kind == "quota" else 1


def default_subscription_runtime() -> Dict[str, Any]:
    return {
        "exhausted": False,
        "exhausted_at": "",
        "exhausted_cycle_key": "",
        "last_failure_at": "",
        "last_success_at": "",
        "last_error": "",
        "last_reset_at": "",
        "last_cycle_marker": "",
        "consecutive_failures": 0,
        "last_failure_day": "",
        "consecutive_failure_days": 0,
    }


def merged_subscription_runtime(current: Dict[str, Any] | None) -> Dict[str, Any]:
    base = default_subscription_runtime()
    base.update(current or {})
    return base


def normalize_subscription_kind(value: Any) -> str:
    kind = str(value or DEFAULT_SUBSCRIPTION_KIND).strip().lower()
    if kind == "refresh":
        kind = "periodic"
    if kind not in SUBSCRIPTION_KINDS:
        return DEFAULT_SUBSCRIPTION_KIND
    return kind


def normalize_subscription_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if ":" in raw:
        hour_raw, minute_raw = raw.split(":", 1)
    else:
        hour_raw, minute_raw = raw, "0"
    hour = safe_int(hour_raw, -1)
    minute = safe_int(minute_raw, -1)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"


def normalize_subscription_times(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    else:
        raw_items = []
    normalized: List[str] = []
    for item in raw_items:
        parsed = normalize_subscription_time(item)
        if parsed and parsed not in normalized:
            normalized.append(parsed)
    normalized.sort()
    return normalized


def normalize_refresh_time(value: Any) -> str:
    return normalize_subscription_time(value)


def normalize_refresh_times(value: Any) -> List[str]:
    return normalize_subscription_times(value)


def normalize_expiry_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for candidate in (raw, raw[:10]):
        try:
            parsed_date = date.fromisoformat(candidate)
            return parsed_date.isoformat()
        except ValueError:
            continue
    return ""


def default_subscription(name: Optional[str] = None, *, kind: str = DEFAULT_SUBSCRIPTION_KIND) -> Dict[str, Any]:
    normalized_kind = normalize_subscription_kind(kind)
    return {
        "id": secrets.token_hex(6),
        "name": name or "Subscription 1",
        "kind": normalized_kind,
        "enabled": True,
        "permanent": True,
        "expires_at": "",
        "reset_times": [DEFAULT_REFRESH_RESET_TIME] if normalized_kind == "periodic" else [],
        "failure_mode": subscription_default_failure_mode(normalized_kind),
        "failure_threshold": subscription_default_failure_threshold(normalized_kind),
        "notes": "",
    }


def normalize_subscription(item: Any, index: int) -> Dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    kind = normalize_subscription_kind(item.get("kind") or item.get("type"))
    permanent = bool(item.get("permanent", True))
    expires_at = "" if permanent else normalize_expiry_date(item.get("expires_at"))
    reset_times = normalize_subscription_times(item.get("reset_times") or item.get("refresh_times"))
    default_failure_mode = subscription_default_failure_mode(kind)
    raw_failure_mode = str(item.get("failure_mode") or "").strip().lower()
    failure_mode = raw_failure_mode if raw_failure_mode in {"consecutive_failures", "consecutive_days"} else default_failure_mode
    if kind == "periodic" and not reset_times:
        reset_times = [DEFAULT_REFRESH_RESET_TIME]
    return {
        "id": str(item.get("id") or secrets.token_hex(6)),
        "name": str(item.get("name") or f"Subscription {index + 1}").strip() or f"Subscription {index + 1}",
        "kind": kind,
        "enabled": bool(item.get("enabled", True)),
        "permanent": permanent,
        "expires_at": expires_at,
        "reset_times": reset_times if kind == "periodic" else [],
        "failure_mode": failure_mode,
        "failure_threshold": max(
            1,
            safe_int(
                item.get("failure_threshold")
                if item.get("failure_threshold") is not None
                else item.get("failure_threshold_days"),
                subscription_default_failure_threshold(kind),
            ),
        ),
        "notes": str(item.get("notes") or "").strip(),
    }


def normalize_subscriptions(value: Any) -> List[Dict[str, Any]]:
    raw_items = value if isinstance(value, list) and value else [default_subscription()]
    normalized = [normalize_subscription(item, index) for index, item in enumerate(raw_items)]
    return normalized or [default_subscription()]


def normalize_upstream_subscriptions(value: Any, upstream_name: str = "") -> List[Dict[str, Any]]:
    normalized = normalize_subscriptions(value)
    if value:
        return normalized
    prefix = str(upstream_name or "Upstream").strip() or "Upstream"
    default_item = default_subscription(name=f"{prefix} Subscription 1")
    return [normalize_subscription(default_item, 0)]


def subscription_expiry_datetime(subscription: Dict[str, Any]) -> Optional[datetime]:
    if subscription.get("permanent", True):
        return None
    expiry = normalize_expiry_date(subscription.get("expires_at"))
    if not expiry:
        return None
    parsed = date.fromisoformat(expiry)
    if normalize_subscription_kind(subscription.get("kind")) == "periodic":
        reset_times = normalize_subscription_times(subscription.get("reset_times") or subscription.get("refresh_times"))
        parsed_times = [parse_reset_time(item) for item in reset_times] or [parse_reset_time(DEFAULT_REFRESH_RESET_TIME)]
        return datetime.combine(parsed, max(parsed_times))
    return datetime.combine(parsed + timedelta(days=1), datetime_time.min) - timedelta(seconds=1)


def subscription_is_expired(subscription: Dict[str, Any], now_dt: Optional[datetime] = None) -> bool:
    expires_at = subscription_expiry_datetime(subscription)
    if expires_at is None:
        return False
    return (now_dt or current_local_datetime()) > expires_at


def parse_reset_time(value: str) -> datetime_time:
    hour, minute = value.split(":", 1)
    return datetime_time(hour=safe_int(hour, 0), minute=safe_int(minute, 0))


def refresh_reset_candidates(now_dt: datetime, reset_times: List[str]) -> Tuple[Optional[datetime], datetime]:
    parsed_times = [parse_reset_time(item) for item in reset_times] or [parse_reset_time(DEFAULT_REFRESH_RESET_TIME)]
    today = now_dt.date()
    candidates = sorted(
        datetime.combine(day, item)
        for day in (today - timedelta(days=1), today, today + timedelta(days=1))
        for item in parsed_times
    )
    latest_reset = max((candidate for candidate in candidates if candidate <= now_dt), default=None)
    next_reset = min(
        (candidate for candidate in candidates if candidate > now_dt),
        default=datetime.combine(today + timedelta(days=1), min(parsed_times)),
    )
    return latest_reset, next_reset


def refresh_subscription_snapshot(
    subscription: Dict[str, Any],
    runtime: Dict[str, Any],
    *,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now_dt or current_local_datetime()
    latest_reset, next_reset = refresh_reset_candidates(now, subscription.get("reset_times") or [])
    latest_reset_text = iso_datetime(latest_reset) if latest_reset else ""
    next_reset_text = iso_datetime(next_reset)
    cycle_marker = latest_reset_text
    if cycle_marker and runtime.get("last_cycle_marker") != cycle_marker:
        runtime["last_cycle_marker"] = cycle_marker
        runtime["last_reset_at"] = cycle_marker
        runtime["consecutive_failures"] = 0
        runtime["consecutive_failure_days"] = 0
        runtime["last_failure_day"] = ""
        if not bool(runtime.get("exhausted")):
            runtime["exhausted_at"] = ""
            runtime["last_error"] = ""
            runtime["exhausted_cycle_key"] = ""
    active_now = bool(latest_reset_text) and not bool(runtime.get("exhausted"))
    return {
        "active_now": active_now,
        "latest_reset_at": latest_reset_text,
        "next_reset_at": next_reset_text,
        "state": "ready" if active_now else "pending_refresh",
        "cycle_key": latest_reset_text,
    }


def choose_active_subscription(active_views: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not active_views:
        return None

    def priority(item: Dict[str, Any]) -> Tuple[int, int, str]:
        kind = str(item.get("kind") or DEFAULT_SUBSCRIPTION_KIND)
        latest_reset_at = str(item.get("latest_reset_at") or "")
        latest_reset_rank = int(datetime.fromisoformat(latest_reset_at).timestamp()) if latest_reset_at else 0
        kind_rank = 0 if kind == "periodic" else 1 if kind == "unlimited" else 2
        return (kind_rank, -latest_reset_rank, str(item.get("name") or ""))

    return sorted(active_views, key=priority)[0]


def ensure_upstream_subscription_runtime(stat: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    current_states = stat.get("subscription_states") if isinstance(stat.get("subscription_states"), dict) else {}
    legacy_states = stat.get("subscription_stats") if isinstance(stat.get("subscription_stats"), dict) else {}
    subscriptions = normalize_subscriptions(upstream.get("subscriptions"))
    runtime = {
        subscription["id"]: merged_subscription_runtime(current_states.get(subscription["id"]) or legacy_states.get(subscription["id"]))
        for subscription in subscriptions
    }
    stat["subscription_states"] = runtime
    if isinstance(stat.get("subscription_stats"), dict):
        stat["subscription_stats"] = runtime
    return runtime


def reset_upstream_subscription_hold(stat: Dict[str, Any]) -> None:
    stat["subscription_manual_hold"] = False
    stat["subscription_manual_hold_reason"] = ""
    stat["subscription_manual_hold_at"] = ""


def set_upstream_subscription_hold(stat: Dict[str, Any], reason: str, *, now_dt: Optional[datetime] = None) -> None:
    stat["subscription_manual_hold"] = True
    stat["subscription_manual_hold_reason"] = str(reason or "manual")
    stat["subscription_manual_hold_at"] = iso_datetime(now_dt or current_local_datetime())


def build_subscription_view(
    subscription: Dict[str, Any],
    runtime: Dict[str, Any],
    *,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now_dt or current_local_datetime()
    expired = subscription_is_expired(subscription, now)
    next_reset_at = ""
    latest_reset_at = ""
    configured_enabled = bool(subscription.get("enabled", True))
    effective_enabled = configured_enabled and not expired
    valid = effective_enabled
    available = False
    cycle_key = ""
    if expired:
        state = "expired"
    elif not configured_enabled:
        state = "disabled"
    elif subscription["kind"] == "periodic":
        refresh_snapshot = refresh_subscription_snapshot(subscription, runtime, now_dt=now)
        next_reset_at = refresh_snapshot["next_reset_at"]
        latest_reset_at = refresh_snapshot["latest_reset_at"]
        cycle_key = refresh_snapshot["cycle_key"]
        exhausted_cycle_key = str(runtime.get("exhausted_cycle_key") or "")
        if bool(runtime.get("exhausted")):
            if cycle_key and exhausted_cycle_key and exhausted_cycle_key == cycle_key:
                state = "exhausted"
            elif cycle_key and exhausted_cycle_key and exhausted_cycle_key != cycle_key:
                state = "awaiting_probe"
            elif refresh_snapshot["state"] == "pending_refresh":
                state = "pending_refresh"
            else:
                state = "awaiting_probe"
        else:
            state = refresh_snapshot["state"]
            available = refresh_snapshot["state"] == "ready"
    elif subscription["kind"] == "quota" and runtime.get("exhausted"):
        state = "exhausted"
    else:
        state = "ready"
        available = valid
    if subscription["kind"] == "quota" and state == "ready":
        available = True
    if subscription["kind"] == "unlimited" and state == "ready":
        available = True
    return {
        "id": subscription["id"],
        "name": subscription["name"],
        "kind": subscription["kind"],
        "enabled": configured_enabled,
        "effective_enabled": effective_enabled,
        "permanent": bool(subscription.get("permanent", True)),
        "expires_at": str(subscription.get("expires_at") or ""),
        "reset_times": list(subscription.get("reset_times") or []),
        "failure_mode": str(subscription.get("failure_mode") or subscription_default_failure_mode(subscription["kind"])),
        "failure_threshold": int(subscription.get("failure_threshold") or subscription_default_failure_threshold(subscription["kind"])),
        "notes": str(subscription.get("notes") or ""),
        "expired": expired,
        "state": state,
        "valid": valid,
        "available": available,
        "active_now": available,
        "exhausted": bool(runtime.get("exhausted")),
        "next_reset_at": next_reset_at,
        "latest_reset_at": latest_reset_at,
        "cycle_key": cycle_key,
        "last_failure_at": str(runtime.get("last_failure_at") or ""),
        "last_success_at": str(runtime.get("last_success_at") or ""),
        "last_error": str(runtime.get("last_error") or ""),
        "consecutive_failures": int(runtime.get("consecutive_failures") or 0),
        "consecutive_failure_days": int(runtime.get("consecutive_failure_days") or 0),
    }


def upstream_subscription_state(
    upstream: Dict[str, Any],
    stat: Dict[str, Any],
    *,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now_dt or current_local_datetime()
    subscriptions = normalize_subscriptions(upstream.get("subscriptions"))
    runtime_map = ensure_upstream_subscription_runtime(stat, upstream)
    views = [build_subscription_view(subscription, runtime_map[subscription["id"]], now_dt=now) for subscription in subscriptions]
    active_views = [view for view in views if view["available"]]
    pending_views = [view for view in views if view["state"] in {"pending_refresh", "awaiting_probe"}]
    valid_views = [view for view in views if view["valid"]]

    manual_hold = bool(stat.get("subscription_manual_hold"))
    manual_reason = str(stat.get("subscription_manual_hold_reason") or "")

    if not valid_views:
        if not manual_hold or manual_reason != "expired":
            set_upstream_subscription_hold(stat, "expired", now_dt=now)
            manual_hold = True
            manual_reason = "expired"
    elif not active_views and not pending_views:
        if not manual_hold:
            set_upstream_subscription_hold(stat, "quota_exhausted", now_dt=now)
            manual_hold = True
            manual_reason = "quota_exhausted"

    chosen = choose_active_subscription(active_views)
    next_reset_at = min(
        (
            view["next_reset_at"]
            for view in views
            if view["state"] in {"exhausted", "pending_refresh", "awaiting_probe"} and view.get("next_reset_at")
        ),
        default="",
    )

    if manual_hold:
        state = "frozen"
        reason = manual_reason or "manual"
    elif chosen:
        state = "ready"
        reason = ""
    elif pending_views:
        state = "pending_refresh"
        reason = "pending_refresh"
    else:
        state = "frozen"
        reason = "unavailable"

    return {
        "state": state,
        "reason": reason,
        "available": state == "ready",
        "resume_required": state == "frozen" and manual_hold,
        "next_reset_at": next_reset_at,
        "subscription_id": str(chosen.get("id") or "") if chosen else "",
        "subscription_name": str(chosen.get("name") or "") if chosen else "",
        "subscription_kind": str(chosen.get("kind") or "") if chosen else "",
        "valid_count": len(valid_views),
        "active_count": len(active_views),
        "pending_count": len(pending_views),
        "total_count": len(views),
        "subscriptions": views,
    }


def record_subscription_success(
    upstream: Dict[str, Any],
    stat: Dict[str, Any],
    subscription_id: str,
    *,
    now_dt: Optional[datetime] = None,
) -> None:
    if not subscription_id:
        return
    now = now_dt or current_local_datetime()
    runtime_map = ensure_upstream_subscription_runtime(stat, upstream)
    runtime = runtime_map.get(subscription_id)
    if runtime is None:
        return
    runtime["last_success_at"] = iso_datetime(now)
    runtime["last_error"] = ""
    runtime["consecutive_failures"] = 0
    runtime["consecutive_failure_days"] = 0
    runtime["last_failure_day"] = ""
    runtime["exhausted"] = False
    runtime["exhausted_at"] = ""
    runtime["exhausted_cycle_key"] = ""


def record_subscription_failure(
    upstream: Dict[str, Any],
    stat: Dict[str, Any],
    subscription_id: str,
    *,
    error: str = "",
    exhaustion_signal: bool = False,
    now_dt: Optional[datetime] = None,
) -> None:
    if not subscription_id:
        return
    now = now_dt or current_local_datetime()
    subscriptions = normalize_subscriptions(upstream.get("subscriptions"))
    subscription = next((item for item in subscriptions if item["id"] == subscription_id), None)
    if subscription is None:
        return
    runtime_map = ensure_upstream_subscription_runtime(stat, upstream)
    runtime = runtime_map.get(subscription_id)
    if runtime is None:
        return
    runtime["last_failure_at"] = iso_datetime(now)
    runtime["last_error"] = str(error or "")
    if not exhaustion_signal:
        return
    runtime["consecutive_failures"] = int(runtime.get("consecutive_failures") or 0) + 1
    if subscription["kind"] == "periodic":
        runtime["exhausted"] = True
        runtime["exhausted_at"] = runtime["last_failure_at"]
        runtime["exhausted_cycle_key"] = str(runtime.get("last_cycle_marker") or "")
        return
    if subscription["kind"] != "quota":
        return
    failure_day = now.date().isoformat()
    previous_day = str(runtime.get("last_failure_day") or "")
    current_count = int(runtime.get("consecutive_failure_days") or 0)
    if previous_day != failure_day:
        expected_previous = (now.date() - timedelta(days=1)).isoformat()
        runtime["consecutive_failure_days"] = current_count + 1 if previous_day == expected_previous else 1
        runtime["last_failure_day"] = failure_day
    failure_mode = str(subscription.get("failure_mode") or subscription_default_failure_mode(subscription["kind"]))
    threshold = max(1, int(subscription.get("failure_threshold") or subscription_default_failure_threshold(subscription["kind"])))
    should_exhaust = (
        int(runtime.get("consecutive_failures") or 0) >= threshold
        if failure_mode == "consecutive_failures"
        else int(runtime.get("consecutive_failure_days") or 0) >= threshold
    )
    if should_exhaust:
        runtime["exhausted"] = True
        runtime["exhausted_at"] = runtime["last_failure_at"]


def default_subscription_runtime_state() -> Dict[str, Any]:
    return default_subscription_runtime()


def describe_subscription(subscription: Dict[str, Any], runtime_state: Dict[str, Any], *, now_ts: Optional[float] = None) -> Dict[str, Any]:
    now_dt = datetime.fromtimestamp(now_ts).astimezone().replace(tzinfo=None) if now_ts is not None else None
    return build_subscription_view(subscription, runtime_state, now_dt=now_dt)


__all__ = [
    "DEFAULT_QUOTA_FAILURE_DAYS",
    "DEFAULT_REFRESH_RESET_TIME",
    "SUBSCRIPTION_KINDS",
    "build_subscription_view",
    "choose_active_subscription",
    "current_local_datetime",
    "default_subscription_runtime_state",
    "default_subscription",
    "default_subscription_runtime",
    "describe_subscription",
    "ensure_upstream_subscription_runtime",
    "iso_datetime",
    "merged_subscription_runtime",
    "normalize_expiry_date",
    "normalize_subscription",
    "normalize_subscription_kind",
    "normalize_refresh_time",
    "normalize_refresh_times",
    "normalize_subscription_time",
    "normalize_subscription_times",
    "normalize_subscriptions",
    "normalize_upstream_subscriptions",
    "record_subscription_failure",
    "record_subscription_success",
    "refresh_subscription_snapshot",
    "reset_upstream_subscription_hold",
    "set_upstream_subscription_hold",
    "subscription_default_failure_mode",
    "subscription_default_failure_threshold",
    "subscription_expiry_datetime",
    "subscription_is_expired",
    "upstream_subscription_state",
]

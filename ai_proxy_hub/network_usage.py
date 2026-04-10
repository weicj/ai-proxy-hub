from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .constants import USAGE_RANGE_CONFIGS


def normalize_usage_range(value: Any) -> str:
    range_key = str(value or "hour").strip().lower()
    if range_key not in USAGE_RANGE_CONFIGS:
        return "hour"
    return range_key


def resolve_usage_window(range_key: str, now_ts: Optional[float] = None) -> Dict[str, Any]:
    normalized_range = normalize_usage_range(range_key)
    config = USAGE_RANGE_CONFIGS[normalized_range]
    now_dt = datetime.fromtimestamp(now_ts or time.time(), tz=timezone.utc).astimezone()
    bucket_count = int(config["bucket_count"])

    if normalized_range == "minute":
        bucket_delta = timedelta(minutes=1)
        current_bucket_start = now_dt.replace(second=0, microsecond=0)
    elif normalized_range == "hour":
        bucket_delta = timedelta(hours=1)
        current_bucket_start = now_dt.replace(minute=0, second=0, microsecond=0)
    elif normalized_range == "day":
        bucket_delta = timedelta(days=1)
        current_bucket_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        bucket_delta = timedelta(weeks=1)
        current_bucket_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_dt.weekday())

    current_bucket_end = current_bucket_start + bucket_delta
    start_dt = current_bucket_end - (bucket_delta * bucket_count)

    return {
        "range": normalized_range,
        "start": start_dt.timestamp(),
        "end": current_bucket_end.timestamp(),
        "bucket_count": bucket_count,
        "bucket_seconds": int(bucket_delta.total_seconds()),
    }


__all__ = ["normalize_usage_range", "resolve_usage_window"]

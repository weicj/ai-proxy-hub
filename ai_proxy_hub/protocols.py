from __future__ import annotations

from typing import Any

from .constants import UPSTREAM_PROTOCOLS


def normalize_upstream_protocol(value: Any) -> str:
    protocol = str(value or "openai").strip().lower()
    if protocol == "claude":
        protocol = "anthropic"
    if protocol not in UPSTREAM_PROTOCOLS:
        return "openai"
    return protocol


__all__ = ["normalize_upstream_protocol"]

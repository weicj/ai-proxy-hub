from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

from .constants import UPSTREAM_PROTOCOL_ORDER
from .protocols import normalize_upstream_protocol
from .utils import now_iso


def generate_local_api_key() -> str:
    return "sk-local-" + secrets.token_hex(12)


def default_local_api_key_name(index: int) -> str:
    return f"Local Key {index + 1}"


def normalize_local_key_protocols(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    elif value is None or value == "":
        raw_items = []
    else:
        raw_items = [value]
    aliases = {
        "openai": "openai",
        "codex": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "gemini": "gemini",
    }
    normalized: List[str] = []
    for item in raw_items:
        mapped = aliases.get(str(item or "").strip().lower())
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return normalized or list(UPSTREAM_PROTOCOL_ORDER)


def normalize_local_api_key_entry(item: Any, index: int) -> Dict[str, Any]:
    item = item if isinstance(item, dict) else {}
    default_name = default_local_api_key_name(index)
    key_value = str(item.get("key") or item.get("value") or item.get("api_key") or "").strip() or generate_local_api_key()
    created_at = str(item.get("created_at") or "").strip() or now_iso()
    return {
        "id": str(item.get("id") or secrets.token_hex(6)),
        "name": str(item.get("name") or default_name).strip() or default_name,
        "key": key_value,
        "enabled": bool(item.get("enabled", True)),
        "created_at": created_at,
        "allowed_protocols": normalize_local_key_protocols(item.get("allowed_protocols") or item.get("protocols")),
    }


def normalize_local_api_keys(value: Any, legacy_value: Any = "") -> List[Dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    normalized = [normalize_local_api_key_entry(item, index) for index, item in enumerate(raw_items)]
    if not normalized:
        legacy_key = str(legacy_value or "").strip() or generate_local_api_key()
        normalized = [
            {
                "id": secrets.token_hex(6),
                "name": default_local_api_key_name(0),
                "key": legacy_key,
                "enabled": True,
                "created_at": now_iso(),
                "allowed_protocols": list(UPSTREAM_PROTOCOL_ORDER),
            }
        ]

    unique_items: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for item in normalized:
        key_value = str(item.get("key") or "").strip()
        if not key_value or key_value in seen_keys:
            continue
        seen_keys.add(key_value)
        unique_items.append(normalize_local_api_key_entry(item, len(unique_items)))

    if not unique_items:
        unique_items.append(
            {
                "id": secrets.token_hex(6),
                "name": default_local_api_key_name(0),
                "key": generate_local_api_key(),
                "enabled": True,
                "created_at": now_iso(),
                "allowed_protocols": list(UPSTREAM_PROTOCOL_ORDER),
            }
        )

    if not any(bool(item.get("enabled", True)) for item in unique_items):
        unique_items[0]["enabled"] = True
    return unique_items


def primary_local_api_key_entry(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    enabled = next((item for item in entries if item.get("enabled", True)), None)
    return enabled or entries[0]


def local_key_allows_protocol(entry: Dict[str, Any], protocol: str) -> bool:
    allowed = entry.get("allowed_protocols") or entry.get("protocols")
    return normalize_upstream_protocol(protocol) in normalize_local_key_protocols(allowed)


def set_primary_local_api_key(config: Dict[str, Any], key_value: str, *, name: Optional[str] = None) -> None:
    entries = normalize_local_api_keys(config.get("local_api_keys"), key_value)
    primary = primary_local_api_key_entry(entries)
    primary["key"] = str(key_value or "").strip() or generate_local_api_key()
    if name:
        primary["name"] = str(name).strip() or primary["name"]
    config["local_api_keys"] = entries
    config["local_api_key"] = primary["key"]


__all__ = [
    "default_local_api_key_name",
    "generate_local_api_key",
    "local_key_allows_protocol",
    "normalize_local_api_key_entry",
    "normalize_local_api_keys",
    "normalize_local_key_protocols",
    "primary_local_api_key_entry",
    "set_primary_local_api_key",
]

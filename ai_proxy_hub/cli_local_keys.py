from __future__ import annotations

import secrets
from typing import Dict, List, Optional

from .constants import UPSTREAM_PROTOCOL_ORDER
from .local_keys import default_local_api_key_name


def build_local_key_entry(language: str, next_index: int, key: str, created_at: str) -> Dict[str, object]:
    name_prefix = "本地 Key" if language == "zh" else "Local Key"
    return {
        "id": secrets.token_hex(6),
        "name": f"{name_prefix} {next_index + 1}" if language == "zh" else default_local_api_key_name(next_index),
        "key": key,
        "enabled": False,
        "created_at": created_at,
        "allowed_protocols": list(UPSTREAM_PROTOCOL_ORDER),
    }


def allowed_protocol_input_value(current: List[str]) -> str:
    return ",".join(
        {
            "openai": "1",
            "anthropic": "2",
            "gemini": "3",
        }.get(protocol, protocol)
        for protocol in current
    )


def parse_allowed_protocols_input(raw: str) -> Optional[List[str]]:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value in {"a", "all"}:
        return list(UPSTREAM_PROTOCOL_ORDER)
    aliases = {
        "1": "openai",
        "openai": "openai",
        "codex": "openai",
        "2": "anthropic",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "3": "gemini",
        "gemini": "gemini",
    }
    values: List[str] = []
    for token in value.replace(",", " ").split():
        mapped = aliases.get(token)
        if mapped and mapped not in values:
            values.append(mapped)
    return values


__all__ = [
    "allowed_protocol_input_value",
    "build_local_key_entry",
    "parse_allowed_protocols_input",
]

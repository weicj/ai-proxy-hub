from __future__ import annotations

import json
import ssl
import threading
import time
from http.client import HTTPConnection, HTTPSConnection
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

from .constants import EXPECTED_CLIENT_DISCONNECT_EXCEPTIONS, IGNORED_SOCKET_ERRNOS
from .protocols import normalize_upstream_protocol


def build_error_payload(message: str, *, code: str = "proxy_error", details: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": {
            "message": message,
            "type": "router_error",
            "code": code,
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


def is_retryable_response(status: int, body: bytes, retryable_statuses: List[int]) -> bool:
    if status in retryable_statuses:
        return True

    lowered = body.decode("utf-8", errors="ignore").lower()
    retry_markers = [
        "insufficient_quota",
        "quota",
        "rate_limit",
        "rate limit",
        "billing",
        "余额",
        "额度",
        "exhausted",
        "temporarily unavailable",
        "overloaded",
        "invalid_api_key",
        "unauthorized",
    ]
    if any(marker in lowered for marker in retry_markers):
        return True
    if status == 404 and "model" in lowered and ("not found" in lowered or "does not exist" in lowered):
        return True
    return False


def is_subscription_exhaustion_signal(status: Optional[int], error: str) -> bool:
    lowered = str(error or "").lower()
    strong_markers = [
        "insufficient_quota",
        "quota exceeded",
        "quota_exceeded",
        "余额不足",
        "额度耗尽",
        "额度已用完",
        "billing",
        "credit balance",
        "payment required",
        "exhausted",
    ]
    if any(marker in lowered for marker in strong_markers):
        return True
    if status == 402:
        return True
    return False


def split_bearer_token(header_value: Optional[str]) -> str:
    if not header_value:
        return ""
    if header_value.lower().startswith("bearer "):
        return header_value[7:].strip()
    return ""


def extract_client_token(headers) -> str:
    return (
        split_bearer_token(headers.get("Authorization"))
        or str(headers.get("api-key") or "").strip()
        or str(headers.get("x-api-key") or "").strip()
        or str(headers.get("x-goog-api-key") or "").strip()
    )


def join_upstream_url(base_url: str, local_path: str, query: str) -> str:
    parsed = urlsplit(base_url)
    relative_path = local_path or "/"
    if relative_path and not relative_path.startswith("/"):
        relative_path = "/" + relative_path
    base_path = parsed.path.rstrip("/")
    for prefix in ("/v1beta", "/v1alpha", "/v1"):
        if base_path.endswith(prefix) and relative_path.startswith(prefix):
            relative_path = relative_path[len(prefix):] or "/"
            break
    target_path = f"{base_path}{relative_path}" or "/"
    return urlunsplit((parsed.scheme, parsed.netloc, target_path, query, ""))


def is_expected_client_disconnect(exc: BaseException) -> bool:
    if isinstance(exc, EXPECTED_CLIENT_DISCONNECT_EXCEPTIONS):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in IGNORED_SOCKET_ERRNOS:
        return True
    return False


def decode_request_payload(body: bytes, content_type: str) -> Optional[Dict[str, Any]]:
    if not body or "json" not in str(content_type or "").lower():
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


_connection_pool: Dict[str, List[tuple[HTTPConnection, float]]] = {}
_connection_pool_lock = threading.Lock()
_connection_pool_max_size = 10
_connection_pool_max_age = 300


def open_http_connection(parsed_target, timeout: int) -> HTTPConnection:
    pool_key = f"{parsed_target.scheme}://{parsed_target.netloc}"
    current_time = time.time()

    with _connection_pool_lock:
        if pool_key in _connection_pool:
            _connection_pool[pool_key] = [
                (conn, timestamp)
                for conn, timestamp in _connection_pool[pool_key]
                if current_time - timestamp < _connection_pool_max_age
            ]
            while _connection_pool[pool_key]:
                conn, _ = _connection_pool[pool_key].pop(0)
                try:
                    conn.sock  # type: ignore[attr-defined]
                    return conn
                except (AttributeError, OSError):
                    continue

    if parsed_target.scheme == "https":
        return HTTPSConnection(parsed_target.netloc, timeout=timeout, context=ssl.create_default_context())
    return HTTPConnection(parsed_target.netloc, timeout=timeout)


def return_http_connection(parsed_target, conn: HTTPConnection) -> None:
    pool_key = f"{parsed_target.scheme}://{parsed_target.netloc}"
    current_time = time.time()

    with _connection_pool_lock:
        if pool_key not in _connection_pool:
            _connection_pool[pool_key] = []

        if len(_connection_pool[pool_key]) < _connection_pool_max_size:
            _connection_pool[pool_key].append((conn, current_time))
        else:
            try:
                conn.close()
            except Exception:
                pass


def upstream_probe_path(protocol: str) -> str:
    if protocol == "anthropic":
        return "/v1/models"
    if protocol == "gemini":
        return "/v1beta/models"
    return "/v1/models"


def build_protocol_auth_headers(protocol: str, api_key: str) -> Dict[str, str]:
    if protocol == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    if protocol == "gemini":
        return {
            "x-goog-api-key": api_key,
        }
    return {
        "Authorization": f"Bearer {api_key}",
    }


def extract_models_count(protocol: str, parsed_body: Any) -> Optional[int]:
    if not isinstance(parsed_body, dict):
        return None
    if protocol == "gemini" and isinstance(parsed_body.get("models"), list):
        return len(parsed_body["models"])
    if isinstance(parsed_body.get("data"), list):
        return len(parsed_body["data"])
    return None


def extract_model_ids(protocol: str, parsed_body: Any) -> List[str]:
    if not isinstance(parsed_body, dict):
        return []
    if protocol == "gemini":
        items = parsed_body.get("models") if isinstance(parsed_body.get("models"), list) else []
        id_key = "name"
    else:
        items = parsed_body.get("data") if isinstance(parsed_body.get("data"), list) else []
        id_key = "id"
    model_ids: List[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get(id_key) or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        model_ids.append(model_id)
    return model_ids


def perform_upstream_probe_request(upstream: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    protocol = normalize_upstream_protocol(upstream.get("protocol"))
    effective_protocol = upstream.get("upstream_protocol", "openai") if protocol == "local_llm" else protocol
    target = join_upstream_url(upstream["base_url"], upstream_probe_path(effective_protocol), "")
    parsed = urlsplit(target)
    connection = open_http_connection(parsed, timeout)
    start = time.perf_counter()
    try:
        path_with_query = parsed.path or "/"
        if parsed.query:
            path_with_query = f"{path_with_query}?{parsed.query}"
        headers = {
            "Accept": "application/json",
            **build_protocol_auth_headers(effective_protocol, upstream["api_key"]),
            **upstream.get("extra_headers", {}),
        }
        connection.request("GET", path_with_query, headers=headers)
        response = connection.getresponse()
        body = response.read()
        content_type = response.getheader("Content-Type", "")
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}: {body.decode('utf-8', errors='ignore')[:200]}")
        models_count = None
        model_ids: List[str] = []
        if "json" in content_type:
            try:
                parsed_body = json.loads(body.decode("utf-8"))
                model_ids = extract_model_ids(effective_protocol, parsed_body)
                models_count = len(model_ids) if model_ids else extract_models_count(effective_protocol, parsed_body)
            except json.JSONDecodeError:
                models_count = None
        return {
            "status": response.status,
            "content_type": content_type,
            "models_count": models_count,
            "models": model_ids,
            "protocol": protocol,
            "target": target,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }
    finally:
        connection.close()


__all__ = [
    "build_error_payload",
    "build_protocol_auth_headers",
    "decode_request_payload",
    "extract_client_token",
    "extract_model_ids",
    "extract_models_count",
    "is_expected_client_disconnect",
    "is_retryable_response",
    "join_upstream_url",
    "open_http_connection",
    "perform_upstream_probe_request",
    "return_http_connection",
    "split_bearer_token",
    "upstream_probe_path",
]

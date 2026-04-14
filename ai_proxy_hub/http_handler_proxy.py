from __future__ import annotations

import json
import socket
import ssl
import time
from http.client import HTTPConnection, HTTPException
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from .constants import ANTHROPIC_MODEL_AWARE_PATHS, HOP_BY_HOP_HEADERS, MODEL_AWARE_PATHS
from .network import (
    build_error_payload,
    build_protocol_auth_headers,
    decode_request_payload,
    extract_client_token,
    is_retryable_response,
    join_upstream_url,
    open_http_connection,
    perform_upstream_probe_request,
    return_http_connection,
    upstream_probe_path,
)
from .utils import safe_int


class RouterRequestHandlerProxyMixin:
    def requested_model_for_request(
        self,
        protocol: str,
        request_path: str,
        request_payload: Optional[Dict[str, Any]],
    ) -> str:
        if not isinstance(request_payload, dict):
            return ""
        requested_model = str(request_payload.get("model") or "").strip()
        if requested_model:
            return requested_model
        model_aware_paths = ANTHROPIC_MODEL_AWARE_PATHS if protocol == "anthropic" else MODEL_AWARE_PATHS
        if request_path not in model_aware_paths:
            return ""
        model_settings = self.store.get_default_model_settings(protocol)
        if model_settings["mode"] == "global":
            return str(model_settings["global_default_model"] or "").strip()
        return ""

    def recover_periodic_upstreams(self, protocol: str) -> None:
        candidates = self.store.get_periodic_probe_candidates(protocol=protocol)
        if not candidates:
            return
        timeout = self.store.get_timeout()
        for candidate in candidates:
            upstream = candidate["upstream"]
            upstream_id = str(upstream.get("id") or "")
            subscription_id = str(candidate.get("subscription_id") or "")
            if not upstream_id or not subscription_id:
                continue
            try:
                result = perform_upstream_probe_request(upstream, timeout)
                self.store.record_periodic_probe_success(
                    upstream_id,
                    subscription_id,
                    status=result.get("status"),
                    latency_ms=result.get("latency_ms"),
                    models_count=result.get("models_count"),
                    models=result.get("models"),
                )
            except Exception as exc:  # pragma: no cover
                self.store.record_periodic_probe_failure(
                    upstream_id,
                    subscription_id,
                    error=str(exc),
                )

    def handle_proxy(self, protocol: str = "openai") -> None:
        local_key_entry = None
        local_key_id = ""
        configured_local_keys = self.store.get_local_api_keys()
        if configured_local_keys:
            client_token = extract_client_token(self.headers)
            local_key_entry = self.store.match_local_api_key(client_token, protocol)
            if not local_key_entry:
                self.send_json(401, build_error_payload("本地代理 key 不正确，或当前 key 无权访问该类型。", code="invalid_local_api_key"))
                return
            local_key_id = str(local_key_entry["id"])
        local_key_recorded = False

        def record_local_key_once(success: bool, *, upstream_id: str = "", error: str = "") -> None:
            nonlocal local_key_recorded
            if local_key_recorded or not local_key_id:
                return
            self.store.record_local_key_result(local_key_id, success=success, upstream_id=upstream_id, error=error)
            local_key_recorded = True

        body_length = safe_int(self.headers.get("Content-Length"), 0)
        request_body = self.rfile.read(body_length) if body_length > 0 else b""
        parsed_request = urlsplit(self.path)
        local_request_path = self.strip_local_protocol_prefix(parsed_request.path, protocol)
        request_payload = decode_request_payload(request_body, self.headers.get("Content-Type", ""))
        requested_model = self.requested_model_for_request(protocol, local_request_path, request_payload)
        self.recover_periodic_upstreams(protocol)

        if self.command == "GET" and local_request_path == upstream_probe_path(protocol):
            models_result = self.try_aggregate_models(protocol, parsed_request.query, local_key_id=local_key_id)
            if models_result["payload"] is not None:
                record_local_key_once(True)
                self.send_json(200, models_result["payload"])
                return
            if models_result["failures"]:
                record_local_key_once(False, error="all_upstreams_failed")
                self.send_json(
                    503,
                    build_error_payload(
                        "所有上游都不可用，已自动尝试切换但仍失败。",
                        code="all_upstreams_failed",
                        details=models_result["failures"],
                    ),
                )
                return

        routing_plan = self.store.get_request_plan(
            protocol=protocol,
            for_models=False,
            advance_round_robin=True,
            requested_model=requested_model,
        )
        upstreams = routing_plan["upstreams"]
        if not upstreams:
            record_local_key_once(False, error="no_upstreams")
            self.send_json(503, build_error_payload(self.no_upstreams_message(protocol), code="no_upstreams"))
            return

        failures: List[Dict[str, Any]] = []
        retryable_statuses = self.store.get_retryable_statuses()
        can_failover = bool(routing_plan["can_failover"])

        for index, upstream in enumerate(upstreams):
            target = join_upstream_url(upstream["base_url"], local_request_path, parsed_request.query)
            parsed_target = urlsplit(target)
            connection = self.open_connection(parsed_target)
            started_at = time.perf_counter()
            try:
                outgoing_body = self.build_outgoing_body(local_request_path, request_body, request_payload, upstream, protocol)
                outgoing_headers = self.build_outgoing_headers(upstream, len(outgoing_body), protocol)
                path_with_query = parsed_target.path or "/"
                if parsed_target.query:
                    path_with_query = f"{path_with_query}?{parsed_target.query}"
                connection.request(self.command, path_with_query, body=outgoing_body or None, headers=outgoing_headers)
                response = connection.getresponse()
                content_type = response.getheader("Content-Type", "")
                is_stream = "text/event-stream" in content_type.lower()

                if response.status >= 400:
                    error_body = response.read()
                    error_text = error_body.decode("utf-8", errors="ignore")[:300]
                    retryable = is_retryable_response(response.status, error_body, retryable_statuses)
                    if retryable and can_failover and index < len(upstreams) - 1:
                        self.store.record_failure(
                            upstream["id"],
                            status=response.status,
                            error=error_text,
                            cooldown=True,
                            local_key_id=local_key_id,
                        )
                        failures.append(
                            {
                                "upstream": upstream["name"],
                                "status": response.status,
                                "message": error_text,
                            }
                        )
                        connection.close()
                        continue
                    if response.status == 413:
                        diagnostic_error = (
                            f"upstream={upstream['name']} path={local_request_path} "
                            f"request_bytes={len(outgoing_body)} model={requested_model or '-'} "
                            f"message={error_text}"
                        )
                        record_local_key_once(
                            False,
                            upstream_id=upstream["id"],
                            error=diagnostic_error,
                        )
                        self.store.record_failure(
                            upstream["id"],
                            status=response.status,
                            error=diagnostic_error,
                            cooldown=False,
                            local_key_id=local_key_id,
                        )
                        self.send_json(
                            413,
                            build_error_payload(
                                (
                                    f"上游 {upstream['name']} 拒绝了过大的请求体。"
                                    f" path={local_request_path}, request_bytes={len(outgoing_body)}, "
                                    f"model={requested_model or '-'}。请缩短会话上下文或新开会话。"
                                ),
                                code="upstream_payload_too_large",
                                details=[
                                    {
                                        "upstream": upstream["name"],
                                        "status": response.status,
                                        "path": local_request_path,
                                        "request_bytes": len(outgoing_body),
                                        "model": requested_model or "",
                                        "message": error_text,
                                    }
                                ],
                            ),
                        )
                        connection.close()
                        return
                    record_local_key_once(
                        False,
                        upstream_id=upstream["id"],
                        error=error_text,
                    )
                    self.store.record_failure(
                        upstream["id"],
                        status=response.status,
                        error=error_text,
                        cooldown=retryable and bool(routing_plan["auto_routing_enabled"]),
                        local_key_id=local_key_id,
                    )
                    self.send_proxied_response(response.status, response.getheaders(), error_body, is_stream=False)
                    connection.close()
                    return

                if is_stream:
                    self.send_response(response.status)
                    for header, value in response.getheaders():
                        if header.lower() in HOP_BY_HOP_HEADERS or header.lower() == "content-length":
                            continue
                        self.send_header(header, value)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        while True:
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        record_local_key_once(True, upstream_id=upstream["id"])
                        self.store.record_success(
                            upstream["id"],
                            response.status,
                            (time.perf_counter() - started_at) * 1000,
                            local_key_id=local_key_id,
                        )
                        return
                    finally:
                        self.close_connection = True
                        connection.close()
                success_body = response.read()
                record_local_key_once(True, upstream_id=upstream["id"])
                self.store.record_success(
                    upstream["id"],
                    response.status,
                    (time.perf_counter() - started_at) * 1000,
                    local_key_id=local_key_id,
                )
                self.send_proxied_response(response.status, response.getheaders(), success_body, is_stream=False)
                return_http_connection(parsed_target, connection)
                return
            except (OSError, HTTPException, socket.timeout, ssl.SSLError) as exc:
                self.store.record_failure(
                    upstream["id"],
                    status=None,
                    error=str(exc),
                    cooldown=True,
                    local_key_id=local_key_id,
                )
                failures.append({"upstream": upstream["name"], "status": None, "message": str(exc)})
                if not can_failover or index == len(upstreams) - 1:
                    record_local_key_once(False, upstream_id=upstream["id"], error=str(exc))
                    self.send_json(
                        503,
                        build_error_payload(
                            f"当前上游不可用: {exc}" if not can_failover else "所有上游都不可用，已自动尝试切换但仍失败。",
                            code="all_upstreams_failed" if can_failover else "active_upstream_failed",
                            details=failures,
                        ),
                    )
                    connection.close()
                    return
                connection.close()

        record_local_key_once(False, error="all_upstreams_failed")
        self.send_json(
            503,
            build_error_payload(
                "所有上游都不可用，已自动尝试切换但仍失败。",
                code="all_upstreams_failed",
                details=failures,
            ),
        )

    def try_aggregate_models(self, protocol: str, query: str, *, local_key_id: str = "") -> Dict[str, Any]:
        routing_plan = self.store.get_request_plan(protocol=protocol, for_models=True, advance_round_robin=False)
        upstreams = routing_plan["upstreams"]
        if not upstreams:
            return {"payload": None, "failures": []}
        merged: Dict[str, Dict[str, Any]] = {}
        successes = 0
        failures: List[Dict[str, Any]] = []
        for upstream in upstreams:
            effective_protocol = upstream.get("upstream_protocol", "openai") if protocol == "local_llm" else protocol
            target = join_upstream_url(upstream["base_url"], upstream_probe_path(effective_protocol), query)
            parsed = urlsplit(target)
            connection = self.open_connection(parsed)
            started_at = time.perf_counter()
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
                if response.status >= 400:
                    message = body.decode("utf-8", errors="ignore")[:300]
                    self.store.record_failure(
                        upstream["id"],
                        status=response.status,
                        error=message,
                        cooldown=is_retryable_response(response.status, body, self.store.get_retryable_statuses()),
                        local_key_id=local_key_id,
                    )
                    failures.append({"upstream": upstream["name"], "status": response.status, "message": message})
                    connection.close()
                    continue
                payload = json.loads(body.decode("utf-8"))
                if isinstance(payload, dict):
                    self.merge_models_payload(effective_protocol, merged, payload)
                    successes += 1
                    self.store.record_success(
                        upstream["id"],
                        response.status,
                        (time.perf_counter() - started_at) * 1000,
                        local_key_id=local_key_id,
                    )
                return_http_connection(parsed, connection)
            except (json.JSONDecodeError, OSError, HTTPException, socket.timeout, ssl.SSLError) as exc:
                self.store.record_failure(
                    upstream["id"],
                    status=None,
                    error=str(exc),
                    cooldown=True,
                    local_key_id=local_key_id,
                )
                failures.append({"upstream": upstream["name"], "status": None, "message": str(exc)})
                connection.close()
                continue
        if successes == 0:
            return {"payload": None, "failures": failures}
        effective_protocol_for_response = "openai" if protocol == "local_llm" else protocol
        payload = self.empty_models_payload(effective_protocol_for_response)
        if effective_protocol_for_response == "gemini":
            payload["models"] = list(merged.values())
        else:
            payload["data"] = list(merged.values())
        return {"payload": payload, "failures": failures}

    def build_outgoing_headers(self, upstream: Dict[str, Any], content_length: int, protocol: str) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        for key, value in self.headers.items():
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered in {"host", "authorization", "content-length", "api-key", "x-api-key", "x-goog-api-key"}:
                continue
            headers[key] = value
        effective_protocol = upstream.get("upstream_protocol", "openai") if protocol == "local_llm" else protocol
        auth_headers = build_protocol_auth_headers(effective_protocol, upstream["api_key"])
        existing_lower = {key.lower() for key in headers}
        extra_header_keys = {str(key).lower() for key in (upstream.get("extra_headers") or {}).keys()}
        if effective_protocol == "anthropic" and ("anthropic-version" in existing_lower or "anthropic-version" in extra_header_keys):
            auth_headers.pop("anthropic-version", None)
        headers.update(auth_headers)
        if content_length > 0:
            headers["Content-Length"] = str(content_length)
        headers.update(upstream.get("extra_headers", {}))
        return headers

    def build_outgoing_body(
        self,
        request_path: str,
        request_body: bytes,
        request_payload: Optional[Dict[str, Any]],
        upstream: Dict[str, Any],
        protocol: str,
    ) -> bytes:
        effective_protocol = upstream.get("upstream_protocol", "openai") if protocol == "local_llm" else protocol
        model_aware_paths = ANTHROPIC_MODEL_AWARE_PATHS if effective_protocol == "anthropic" else MODEL_AWARE_PATHS
        if request_payload is None or request_path not in model_aware_paths or "model" in request_payload:
            return request_body

        model_settings = self.store.get_default_model_settings(protocol)
        default_model = ""
        if model_settings["mode"] == "global":
            default_model = model_settings["global_default_model"]
        else:
            default_model = str(upstream.get("default_model") or "").strip()

        if not default_model:
            return request_body

        patched_payload = json.loads(json.dumps(request_payload))
        patched_payload["model"] = default_model
        return json.dumps(patched_payload, ensure_ascii=False).encode("utf-8")

    def open_connection(self, parsed_target) -> HTTPConnection:
        timeout = self.store.get_timeout()
        return open_http_connection(parsed_target, timeout)

    def send_proxied_response(self, status: int, headers: List[tuple[str, str]], body: bytes, *, is_stream: bool) -> None:
        self.send_response(status)
        for header, value in headers:
            lowered = header.lower()
            if lowered in HOP_BY_HOP_HEADERS:
                continue
            if lowered == "content-length":
                continue
            self.send_header(header, value)
        if not is_stream:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

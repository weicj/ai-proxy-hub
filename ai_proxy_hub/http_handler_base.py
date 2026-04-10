from __future__ import annotations

import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qsl, urlsplit

from .constants import (
    DEFAULT_SHARED_API_PREFIXES,
    LEGACY_SHARED_API_PREFIXES,
    NATIVE_API_PREFIXES,
    UPSTREAM_PROTOCOL_ORDER,
)
from .network import build_error_payload, protocol_display_name
from .utils import now_iso, safe_int


class RouterRequestHandlerBaseMixin:
    MAX_BODY_SIZE = 100 * 1024 * 1024

    def do_GET(self) -> None:
        self.route_request()

    def do_POST(self) -> None:
        self.route_request()

    def do_PUT(self) -> None:
        self.route_request()

    def do_PATCH(self) -> None:
        self.route_request()

    def do_DELETE(self) -> None:
        self.route_request()

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/api/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, api-key, x-api-key, x-goog-api-key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
            self.send_security_headers()
            self.end_headers()
            return
        self.send_error(405)

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "quiet_logging", False):  # type: ignore[attr-defined]
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            rendered = format % args if args else format
        except Exception:
            rendered = " ".join([str(format), *[str(arg) for arg in args]])
        safe_message = str(rendered).replace("\n", "\\n").replace("\r", "\\r")
        print(f"[{timestamp}] {self.address_string()} {safe_message}")

    def local_protocol_from_path(self, path: str) -> Optional[str]:
        exposed = set(getattr(self.server, "exposed_protocols", UPSTREAM_PROTOCOL_ORDER))  # type: ignore[attr-defined]
        prefix_map = dict(getattr(self.server, "protocol_prefixes", DEFAULT_SHARED_API_PREFIXES))  # type: ignore[attr-defined]
        for protocol in UPSTREAM_PROTOCOL_ORDER:
            if protocol not in exposed:
                continue
            candidates = [prefix_map.get(protocol, DEFAULT_SHARED_API_PREFIXES[protocol]), *LEGACY_SHARED_API_PREFIXES.get(protocol, ())]
            if NATIVE_API_PREFIXES[protocol] not in candidates:
                candidates.append(NATIVE_API_PREFIXES[protocol])
            for prefix in candidates:
                if path == prefix or path.startswith(prefix + "/"):
                    return protocol
        return None

    def strip_local_protocol_prefix(self, path: str, protocol: str) -> str:
        prefix_map = dict(getattr(self.server, "protocol_prefixes", DEFAULT_SHARED_API_PREFIXES))  # type: ignore[attr-defined]
        candidates = [prefix_map.get(protocol, DEFAULT_SHARED_API_PREFIXES[protocol]), *LEGACY_SHARED_API_PREFIXES.get(protocol, ())]
        for prefix in candidates:
            if prefix == NATIVE_API_PREFIXES[protocol]:
                continue
            if path == prefix:
                return "/"
            if path.startswith(prefix + "/"):
                stripped = path[len(prefix) :]
                return stripped or "/"
        return path

    def no_upstreams_message(self, protocol: str) -> str:
        return f"当前没有可用的 {protocol_display_name(protocol)} 上游，请先在控制台填写 base_url 和 API key。"

    def empty_models_payload(self, protocol: str) -> Dict[str, Any]:
        if protocol == "gemini":
            return {"models": []}
        if protocol == "anthropic":
            return {"data": [], "has_more": False}
        return {"object": "list", "data": []}

    def merge_models_payload(self, protocol: str, merged: Dict[str, Dict[str, Any]], payload: Dict[str, Any]) -> None:
        items: List[Any]
        if protocol == "gemini":
            items = payload.get("models") if isinstance(payload.get("models"), list) else []
            id_key = "name"
        else:
            items = payload.get("data") if isinstance(payload.get("data"), list) else []
            id_key = "id"
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get(id_key) or "").strip()
            if model_id and model_id not in merged:
                merged[model_id] = item

    def dispatch_allowed_methods(self, handlers: Dict[str, Callable[[], None]]) -> bool:
        handler = handlers.get(self.command)
        if handler is None:
            self.send_error(405)
            return True
        handler()
        return True

    def runtime_service_snapshot(self) -> Optional[Dict[str, Any]]:
        service_controller = getattr(self.server, "service_controller", None)  # type: ignore[attr-defined]
        if service_controller is None:
            return None
        return service_controller.status_snapshot()

    def runtime_status_payload(self, service_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        runtime_host, runtime_port = self.server.server_address[:2]
        snapshot = service_snapshot if service_snapshot is not None else self.runtime_service_snapshot()
        service_controller = getattr(self.server, "service_controller", None)  # type: ignore[attr-defined]
        runtime_payload = service_controller.runtime_info() if service_controller is not None else None
        if isinstance(runtime_payload, dict):
            runtime_host = runtime_payload.get("host") or runtime_host
            runtime_port = int(runtime_payload.get("port") or runtime_port)
        if snapshot is None:
            payload = self.store.get_status(runtime_host, runtime_port)
        else:
            payload = self.store.get_status(
                runtime_host,
                runtime_port,
                service_state=str(snapshot.get("state") or "running"),
                service_error=str(snapshot.get("error") or ""),
                service_details=snapshot,
            )
        if isinstance(runtime_payload, dict):
            payload["runtime"] = runtime_payload
        return payload

    def handle_dashboard_request(self, path: str) -> bool:
        dashboard_enabled = bool(getattr(self.server, "dashboard_enabled", True))  # type: ignore[attr-defined]
        if path == "/health":
            self.send_json(200, {"status": "ok", "time": now_iso()})
            return True
        if not dashboard_enabled:
            return False
        if path == "/" or path == "/index.html":
            self.serve_dashboard()
            return True
        if self.command == "GET" and self.serve_static_asset(path):
            return True
        if path == "/api/config":
            return self.dispatch_allowed_methods({"GET": lambda: self.send_json(200, self.store.get_config()), "POST": self.handle_save_config})
        if path == "/api/config/export":
            return self.dispatch_allowed_methods({"GET": lambda: self.send_json_file("ai-proxy-hub-config.json", self.store.get_config())})
        if path == "/api/config/import":
            return self.dispatch_allowed_methods({"POST": self.handle_import_config})
        if path == "/api/status":
            return self.dispatch_allowed_methods({"GET": lambda: self.send_json(200, self.runtime_status_payload())})
        if path == "/api/usage":
            return self.dispatch_allowed_methods(
                {
                    "GET": lambda: self.send_json(
                        200,
                        self.store.get_usage_series(dict(parse_qsl(urlsplit(self.path).query)).get("range", "hour")),
                    )
                }
            )
        if path == "/api/test":
            return self.dispatch_allowed_methods({"POST": self.handle_test_upstream})
        if path == "/api/upstream/control":
            return self.dispatch_allowed_methods({"POST": self.handle_upstream_control})
        if path == "/api/client/control":
            return self.dispatch_allowed_methods({"POST": self.handle_client_control})
        if path == "/api/service/control":
            return self.dispatch_allowed_methods({"POST": self.handle_service_control})
        return False

    def route_request(self) -> None:
        path = urlsplit(self.path).path
        if self.handle_dashboard_request(path):
            return
        protocol = self.local_protocol_from_path(path)
        if protocol:
            self.handle_proxy(protocol)
            return
        self.send_json(404, build_error_payload("未找到对应页面。", code="not_found"))

    def read_json_body(self) -> Dict[str, Any]:
        content_length = safe_int(self.headers.get("Content-Length"), 0)
        if content_length > self.MAX_BODY_SIZE:
            self.send_error(413, "Request body too large")
            return {}
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw_body:
            return {}
        try:
            return json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.send_error(400, f"Invalid JSON: {exc}")
            return {}

    def send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_json_file(self, filename: str, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def serve_dashboard(self) -> None:
        index_path = self.server.static_dir / "index.html"  # type: ignore[attr-defined]
        if not index_path.exists():
            self.send_json(500, build_error_payload("控制台页面不存在。", code="dashboard_missing"))
            return
        body = index_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def serve_static_asset(self, path: str) -> bool:
        if not path or path == "/" or path.startswith("/api/") or path == "/health":
            return False
        relative_path = path.lstrip("/")
        if not relative_path or ".." in Path(relative_path).parts:
            return False
        asset_path = (self.server.static_dir / relative_path).resolve()  # type: ignore[attr-defined]
        static_root = Path(self.server.static_dir).resolve()  # type: ignore[attr-defined]
        try:
            asset_path.relative_to(static_root)
        except ValueError:
            return False
        if not asset_path.is_file():
            return False
        body = asset_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(asset_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)
        return True

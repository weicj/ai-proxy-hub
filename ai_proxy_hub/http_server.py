from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterable, Optional

from .config_logic import normalize_shared_api_prefixes
from .constants import DEFAULT_SHARED_API_PREFIXES, UPSTREAM_PROTOCOL_ORDER
from .http_handler_base import RouterRequestHandlerBaseMixin
from .http_handler_control import RouterRequestHandlerControlMixin
from .http_handler_proxy import RouterRequestHandlerProxyMixin
from .network import is_expected_client_disconnect

if TYPE_CHECKING:
    from .service_controller import ServiceController
    from .store import ConfigStore


class RouterHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        store: ConfigStore,
        static_dir: Path,
        quiet_logging: bool = False,
        protocol_prefixes: Optional[Dict[str, str]] = None,
        exposed_protocols: Optional[Iterable[str]] = None,
        dashboard_enabled: bool = True,
        service_controller: Optional["ServiceController"] = None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.store = store
        self.static_dir = static_dir
        self.quiet_logging = quiet_logging
        self.protocol_prefixes = dict(protocol_prefixes or DEFAULT_SHARED_API_PREFIXES)
        self.exposed_protocols = tuple(exposed_protocols or UPSTREAM_PROTOCOL_ORDER)
        self.dashboard_enabled = dashboard_enabled
        self.service_controller = service_controller

    def handle_error(self, request, client_address) -> None:  # type: ignore[override]
        exc = sys.exc_info()[1]
        if exc is not None and is_expected_client_disconnect(exc):
            return
        if getattr(self, "quiet_logging", False):
            return
        super().handle_error(request, client_address)


class RouterRequestHandler(
    RouterRequestHandlerBaseMixin,
    RouterRequestHandlerControlMixin,
    RouterRequestHandlerProxyMixin,
    BaseHTTPRequestHandler,
):
    server_version = "AIProxyHub/0.3"
    protocol_version = "HTTP/1.1"

    @property
    def store(self) -> ConfigStore:
        return self.server.store  # type: ignore[attr-defined]


def create_server(
    config_path: Path,
    static_dir: Path,
    host_override: Optional[str],
    port_override: Optional[int],
    store_override: Optional["ConfigStore"] = None,
    quiet_logging: bool = False,
    protocol_prefixes: Optional[Dict[str, str]] = None,
    exposed_protocols: Optional[Iterable[str]] = None,
    dashboard_enabled: bool = True,
    service_controller: Optional["ServiceController"] = None,
) -> RouterHTTPServer:
    from .store import ConfigStore

    store = store_override or ConfigStore(config_path)
    config = store.get_config()
    host = host_override or config["listen_host"]
    port = port_override if port_override is not None else int(config["listen_port"])
    return RouterHTTPServer(
        (host, port),
        RouterRequestHandler,
        store,
        static_dir,
        quiet_logging=quiet_logging,
        protocol_prefixes=protocol_prefixes or normalize_shared_api_prefixes(config.get("shared_api_prefixes")),
        exposed_protocols=exposed_protocols or UPSTREAM_PROTOCOL_ORDER,
        dashboard_enabled=dashboard_enabled,
        service_controller=service_controller,
    )


__all__ = ["RouterHTTPServer", "RouterRequestHandler", "create_server"]

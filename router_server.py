#!/usr/bin/env python3
from __future__ import annotations

import sys


if __name__ == "__main__":
    from start import main

    main()
else:
    from ai_proxy_hub import legacy_impl as _legacy
    from ai_proxy_hub.cli_app import InteractiveConsoleApp
    from ai_proxy_hub.entrypoints import main, parse_args, print_runtime_paths, resolve_config_path, serve_foreground
    from ai_proxy_hub.http_server import RouterHTTPServer, RouterRequestHandler, create_server
    from ai_proxy_hub.service_controller import ServiceController
    from ai_proxy_hub.store import ConfigStore

    _legacy.ConfigStore = ConfigStore
    _legacy.ServiceController = ServiceController
    _legacy.InteractiveConsoleApp = InteractiveConsoleApp
    _legacy.RouterHTTPServer = RouterHTTPServer
    _legacy.RouterRequestHandler = RouterRequestHandler
    _legacy.create_server = create_server
    _legacy.main = main
    _legacy.parse_args = parse_args
    _legacy.print_runtime_paths = print_runtime_paths
    _legacy.resolve_config_path = resolve_config_path
    _legacy.serve_foreground = serve_foreground
    sys.modules[__name__] = _legacy

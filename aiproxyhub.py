#!/usr/bin/env python3
from __future__ import annotations

from ai_proxy_hub.entrypoints import main, parse_args, print_runtime_paths, resolve_config_path, serve_foreground

__all__ = [
    "main",
    "parse_args",
    "print_runtime_paths",
    "resolve_config_path",
    "serve_foreground",
]


if __name__ == "__main__":
    main()

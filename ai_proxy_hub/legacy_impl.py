#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from .client_switch import *  # noqa: F401,F403
from .config import *  # noqa: F401,F403
from .constants import *  # noqa: F401,F403
from .console_i18n import CONSOLE_I18N
from .http_server import RouterHTTPServer, RouterRequestHandler, create_server
from .network import *  # noqa: F401,F403
from .store import ConfigStore
from .service_controller import ServiceController
from .cli_app import InteractiveConsoleApp


def parse_args() -> argparse.Namespace:
    from .entrypoints import parse_args as _parse_args

    return _parse_args()


def resolve_config_path(config_arg: Optional[str], base_dir: Path) -> Path:
    from .entrypoints import resolve_config_path as _resolve_config_path

    return _resolve_config_path(config_arg, base_dir)


def print_runtime_paths(config_path: Path, static_dir: Path) -> None:
    from .entrypoints import print_runtime_paths as _print_runtime_paths

    _print_runtime_paths(config_path, static_dir)


def serve_foreground(config_path: Path, static_dir: Path, host: Optional[str], port: Optional[int]) -> None:
    from .entrypoints import serve_foreground as _serve_foreground

    _serve_foreground(config_path, static_dir, host, port)


def main() -> None:
    from .entrypoints import main as _main

    _main()


__all__ = [name for name in globals() if not name.startswith("_")]


if __name__ == "__main__":
    main()

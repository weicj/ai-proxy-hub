from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Optional

from .cli import InteractiveConsoleApp
from .config import (
    app_config_dir,
    claude_cli_settings_path,
    codex_cli_auth_path,
    codex_cli_config_path,
    default_user_config_path,
    first_env_value,
    gemini_cli_auth_path,
    gemini_cli_settings_path,
    legacy_config_locations,
    platform_family,
    preferred_app_config_dir,
    resolve_static_dir,
    seed_config_path,
)
from .constants import (
    APP_NAME,
    APP_SLUG,
    APP_VERSION,
    CONFIG_PATH_ENV_VAR,
    LEGACY_CONFIG_PATH_ENV_VARS,
    LEGACY_STATIC_DIR_ENV_VARS,
    STATIC_DIR_ENV_VAR,
)
from .network_runtime import display_runtime_host
from .runtime import ConfigStore
from .service import ServiceController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME} local proxy and control console")
    parser.add_argument("--config", help="配置文件路径；默认使用当前用户目录下的配置文件")
    parser.add_argument("--serve", action="store_true", help="直接启动 HTTP 服务，不进入交互式 CLI 控制台")
    parser.add_argument("--host", help="覆盖监听地址")
    parser.add_argument("--port", type=int, help="覆盖监听端口")
    parser.add_argument("--print-paths", action="store_true", help="打印当前平台下的配置和资源路径后退出")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    return parser.parse_args()


def resolve_config_path(config_arg: Optional[str], base_dir: Path) -> Path:
    env_config = first_env_value(CONFIG_PATH_ENV_VAR, *LEGACY_CONFIG_PATH_ENV_VARS)
    if config_arg:
        config_path = (base_dir / config_arg).resolve() if not os.path.isabs(config_arg) else Path(config_arg).resolve()
    elif env_config:
        config_path = Path(env_config).expanduser().resolve()
    else:
        config_path = default_user_config_path().resolve()
    for legacy_path in legacy_config_locations(base_dir):
        if legacy_path != config_path and legacy_path.exists():
            seed_config_path(config_path, legacy_path)
            break
    else:
        seed_config_path(config_path, None)
    return config_path


def print_runtime_paths(config_path: Path, static_dir: Path) -> None:
    payload = {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "platform": platform_family(),
        "config_path": str(config_path),
        "preferred_app_config_dir": str(preferred_app_config_dir()),
        "platform_default_app_config_dir": str(app_config_dir()),
        "static_dir": str(static_dir),
        "codex_config_path": str(codex_cli_config_path()),
        "codex_auth_path": str(codex_cli_auth_path()),
        "claude_settings_path": str(claude_cli_settings_path()),
        "gemini_settings_path": str(gemini_cli_settings_path()),
        "gemini_auth_path": str(gemini_cli_auth_path()),
        "config_override_env": CONFIG_PATH_ENV_VAR,
        "static_override_env": STATIC_DIR_ENV_VAR,
        "legacy_config_override_envs": list(LEGACY_CONFIG_PATH_ENV_VARS),
        "legacy_static_override_envs": list(LEGACY_STATIC_DIR_ENV_VARS),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _mask_secret(value: str) -> str:
    text = str(value or "")
    if len(text) <= 18:
        return text or "-"
    return f"{text[:12]}...{text[-4:]}"


def foreground_runtime_lines(config_path: Path, runtime: dict, config: dict) -> list[str]:
    lines = [
        "AI Proxy Hub 已启动",
        f"配置文件: {config_path}",
        f"Web 控制台: {runtime['dashboard_url']}",
    ]
    host = display_runtime_host(str(runtime.get("listen_host") or runtime.get("host") or "127.0.0.1"))
    endpoint_mode = str(runtime.get("endpoint_mode") or "shared")
    if endpoint_mode == "shared":
        prefixes = runtime.get("shared_api_prefixes") if isinstance(runtime.get("shared_api_prefixes"), dict) else {}
        lines.append(
            "API: "
            f"shared {host}:{runtime.get('listen_port')} | "
            f"Codex {prefixes.get('openai', '/openai')} | "
            f"Claude {prefixes.get('anthropic', '/claude')} | "
            f"Gemini {prefixes.get('gemini', '/gemini')}"
        )
    else:
        ports = runtime.get("split_api_ports") if isinstance(runtime.get("split_api_ports"), dict) else {}
        lines.append(
            "API: "
            f"split | Codex {host}:{ports.get('openai', '-')}"
            f" | Claude {host}:{ports.get('anthropic', '-')}"
            f" | Gemini {host}:{ports.get('gemini', '-')}"
        )
    key_count = len(config.get("local_api_keys") or [])
    lines.append(
        f"本地 Keys: {key_count} | 主 Key {_mask_secret(str(config.get('local_api_key') or ''))}"
    )
    return lines


def serve_foreground(config_path: Path, static_dir: Path, host: Optional[str], port: Optional[int]) -> None:
    store = ConfigStore(config_path)
    config = store.get_config()
    if host:
        config["listen_host"] = host
    if port is not None:
        config["listen_port"] = int(port)
    if host or port is not None:
        config = store.save_config(config)

    controller = ServiceController(config_path, static_dir, store)
    dashboard_result = controller.ensure_dashboard_running()
    if not dashboard_result.get("ok"):
        raise OSError(str(dashboard_result.get("message") or "dashboard_start_failed"))
    start_result = controller.start()
    if not start_result.get("ok") and start_result.get("message") != "already_running":
        controller.shutdown()
        raise OSError(str(start_result.get("message") or "service_start_failed"))

    runtime = controller.runtime_info()
    for line in foreground_runtime_lines(config_path, runtime, config):
        print(line)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        controller.shutdown()


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent.parent
    config_path = resolve_config_path(args.config, base_dir)
    static_dir = resolve_static_dir(base_dir)
    if args.print_paths:
        print_runtime_paths(config_path, static_dir)
        return
    if args.serve:
        serve_foreground(config_path, static_dir, args.host, args.port)
        return
    app = InteractiveConsoleApp(config_path, static_dir)
    app.run()


__all__ = [
    "main",
    "parse_args",
    "foreground_runtime_lines",
    "print_runtime_paths",
    "resolve_config_path",
    "serve_foreground",
]

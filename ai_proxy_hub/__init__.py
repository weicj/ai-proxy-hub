from __future__ import annotations

from importlib import import_module

from . import constants as _constants
from .constants import *  # noqa: F401,F403


_LAZY_EXPORTS = {
    "cli": ("InteractiveConsoleApp",),
    "client_switch": (
        "collect_client_binding_statuses",
        "detect_active_codex_provider",
        "get_claude_cli_binding_status",
        "get_codex_cli_binding_status",
        "get_gemini_cli_binding_status",
        "get_local_llm_cli_binding_status",
        "read_toml_string_value",
        "restore_all_clients_from_backup",
        "restore_claude_cli_from_backup",
        "restore_client_from_backup",
        "restore_codex_cli_from_backup",
        "restore_gemini_cli_from_backup",
        "switch_all_clients_to_local_hub",
        "switch_claude_cli_to_local_hub",
        "switch_client_to_local_hub",
        "switch_codex_cli_to_local_hub",
        "switch_gemini_cli_to_local_hub",
        "upsert_toml_key",
    ),
    "config": (
        "app_config_dir",
        "app_config_dir_candidates",
        "claude_cli_settings_path",
        "codex_cli_auth_path",
        "codex_cli_config_path",
        "default_user_config_path",
        "first_env_value",
        "gemini_cli_auth_path",
        "gemini_cli_settings_path",
        "legacy_config_locations",
        "local_key_allows_protocol",
        "normalize_config",
        "normalize_local_api_keys",
        "platform_family",
        "preferred_app_config_dir",
        "resolve_static_dir",
        "seed_config_path",
        "write_json",
    ),
    "console_i18n": ("CONSOLE_I18N",),
    "entrypoints": (
        "foreground_runtime_lines",
        "main",
        "parse_args",
        "print_runtime_paths",
        "resolve_config_path",
        "serve_foreground",
    ),
    "http_server": ("RouterHTTPServer", "RouterRequestHandler", "create_server"),
    "network_runtime": ("client_display_name", "display_runtime_host"),
    "project_meta": ("project_metadata_payload",),
    "protocols": ("normalize_upstream_protocol",),
    "service_controller": ("ServiceController",),
    "store": ("ConfigStore",),
}

_LAZY_MODULES = {"http_server", "legacy_impl"}

__version__ = APP_VERSION


def __getattr__(name: str):
    if name in _LAZY_MODULES:
        module = import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    for module_name, export_names in _LAZY_EXPORTS.items():
        if name in export_names:
            module = import_module(f".{module_name}", __name__)
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


__all__ = [
    *_constants.__all__,
    "CONSOLE_I18N",
    "ConfigStore",
    "InteractiveConsoleApp",
    "RouterHTTPServer",
    "RouterRequestHandler",
    "ServiceController",
    "app_config_dir",
    "app_config_dir_candidates",
    "claude_cli_settings_path",
    "client_display_name",
    "codex_cli_auth_path",
    "codex_cli_config_path",
    "collect_client_binding_statuses",
    "create_server",
    "default_user_config_path",
    "detect_active_codex_provider",
    "display_runtime_host",
    "first_env_value",
    "foreground_runtime_lines",
    "gemini_cli_auth_path",
    "gemini_cli_settings_path",
    "get_claude_cli_binding_status",
    "get_codex_cli_binding_status",
    "get_gemini_cli_binding_status",
    "get_local_llm_cli_binding_status",
    "http_server",
    "legacy_config_locations",
    "legacy_impl",
    "local_key_allows_protocol",
    "main",
    "normalize_config",
    "normalize_local_api_keys",
    "normalize_upstream_protocol",
    "parse_args",
    "platform_family",
    "preferred_app_config_dir",
    "print_runtime_paths",
    "project_metadata_payload",
    "read_toml_string_value",
    "resolve_config_path",
    "resolve_static_dir",
    "restore_all_clients_from_backup",
    "restore_claude_cli_from_backup",
    "restore_client_from_backup",
    "restore_codex_cli_from_backup",
    "restore_gemini_cli_from_backup",
    "seed_config_path",
    "serve_foreground",
    "switch_all_clients_to_local_hub",
    "switch_claude_cli_to_local_hub",
    "switch_client_to_local_hub",
    "switch_codex_cli_to_local_hub",
    "switch_gemini_cli_to_local_hub",
    "upsert_toml_key",
    "write_json",
]

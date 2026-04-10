from __future__ import annotations

import json
import os
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cli_display import (
    activation_label as compute_activation_label,
    current_language_label as compute_current_language_label,
    format_client_status_line as compute_client_status_line,
    format_protocol_list as compute_protocol_list,
    format_usage_label as compute_usage_label,
    masked_secret as compute_masked_secret,
    probe_label as compute_probe_label,
    protocol_client_status_label as compute_protocol_client_status_label,
    protocol_console_label as compute_protocol_console_label,
    protocol_is_active as compute_protocol_is_active,
    protocol_label as compute_protocol_label,
    protocol_runtime_url as compute_protocol_runtime_url,
    protocol_service_status_label as compute_protocol_service_status_label,
    routing_strategy_label as compute_routing_strategy_label,
    runtime_mode_label as compute_runtime_mode_label,
    theme_label as compute_theme_label,
    usage_scope_label as compute_usage_scope_label,
)
from .cli_key_manager import CliLocalKeyController
from .cli_local_keys import allowed_protocol_input_value, parse_allowed_protocols_input
from .cli_runtime import CliRuntimeController
from .cli_settings import CliSettingsController
from .cli_upstreams import CliUpstreamController
from .cli_usage import CliUsageController
from .cli_workspace import CliWorkspaceController
from .config_logic import (
    normalize_config,
    normalize_cli_theme_mode,
    normalize_endpoint_mode,
    normalize_shared_api_prefixes,
    normalize_split_api_ports,
    normalize_ui_language,
)
from .console_i18n import CONSOLE_I18N
from .constants import DEFAULT_LISTEN_PORT, UPSTREAM_PROTOCOL_ORDER
from .local_keys import normalize_local_key_protocols
from .network import client_display_name, perform_upstream_probe_request
from .protocols import normalize_upstream_protocol
from .service_controller import ServiceController
from .store import ConfigStore


class InteractiveConsoleApp:
    COLOR_CODES = ["\033[38;5;75m", "\033[38;5;114m", "\033[38;5;221m", "\033[38;5;204m", "\033[38;5;141m", "\033[38;5;80m"]
    COLOR_RESET = "\033[0m"

    def __init__(self, config_path: Path, static_dir: Path) -> None:
        self.config_path = config_path
        self.static_dir = static_dir
        self.store = ConfigStore(config_path)
        self.service = ServiceController(config_path, static_dir, self.store)
        self.usage_range = "hour"
        self.usage_local_key = "all"
        self.runtime_controller = CliRuntimeController(self)
        self.settings_controller = CliSettingsController(self)
        self.upstream_controller = CliUpstreamController(self)
        self.workspace_controller = CliWorkspaceController(self)
        self.local_key_controller = CliLocalKeyController(self)
        self.usage_controller = CliUsageController(self)
        self.refresh_switched_clients = self.runtime_controller.refresh_switched_clients
        self.run_with_port_recovery = self.runtime_controller.run_with_port_recovery
        self.start_service_with_recovery = self.runtime_controller.start_service_with_recovery
        self.start_forwarding_with_recovery = self.runtime_controller.start_forwarding_with_recovery
        self.start_protocol_with_recovery = self.runtime_controller.start_protocol_with_recovery
        self.ensure_dashboard_with_recovery = self.runtime_controller.ensure_dashboard_with_recovery
        self.print_client_action_results = self.runtime_controller.print_client_action_results
        self.client_action_result_lines = self.runtime_controller.client_action_result_lines
        self.enable_client_for_protocol = self.runtime_controller.enable_client_for_protocol
        self.restore_client_for_protocol = self.runtime_controller.restore_client_for_protocol
        self.menu_network_ports = self.settings_controller.menu_network_ports
        self.menu_port_layout = self.settings_controller.menu_port_layout
        self.menu_protocol_default_models = self.settings_controller.menu_protocol_default_models
        self.menu_routing_controls = self.settings_controller.menu_routing_controls
        self.menu_protocol_routing = self.settings_controller.menu_protocol_routing
        self.menu_config_transfer = self.settings_controller.menu_config_transfer
        self.menu_settings = self.settings_controller.menu_settings
        self.menu_runtime_settings = self.settings_controller.menu_runtime_settings
        self.menu_runtime_auth = self.settings_controller.menu_runtime_auth
        self.menu_appearance = self.settings_controller.menu_appearance
        self.menu_language = self.settings_controller.menu_language
        self.menu_theme = self.settings_controller.menu_theme
        self.menu_theme_accents = self.settings_controller.menu_theme_accents
        self.menu_dashboard_usage = self.settings_controller.menu_dashboard_usage
        self.prompt_upstream = self.upstream_controller.prompt_upstream
        self.test_upstream = self.upstream_controller.test_upstream
        self.delete_upstream = self.upstream_controller.delete_upstream
        self.add_upstream = self.upstream_controller.add_upstream
        self.edit_upstream = self.upstream_controller.edit_upstream
        self.test_all_upstreams = self.upstream_controller.test_all_upstreams
        self.reorder_protocol_upstreams = self.upstream_controller.reorder_protocol_upstreams
        self.menu_upstream_detail = self.upstream_controller.menu_upstream_detail
        self.menu_protocol_upstreams = self.upstream_controller.menu_protocol_upstreams
        self.menu_local_api_keys = self.local_key_controller.menu_local_api_keys
        self.menu_local_api_key_editor = self.local_key_controller.menu_local_api_key_editor
        self.menu_global_runtime = self.workspace_controller.menu_global_runtime
        self.menu_protocol_workspace_selector = self.workspace_controller.menu_protocol_workspace_selector
        self.menu_protocol_workspace = self.workspace_controller.menu_protocol_workspace
        self.menu_protocol_runtime = self.workspace_controller.menu_protocol_runtime
        self.render_usage_chart = self.usage_controller.render_usage_chart
        self.menu_usage_scope = self.usage_controller.menu_usage_scope
        self.menu_usage = self.usage_controller.menu_usage

        # Try to use modern CLI
        self.modern_cli = None
        try:
            from cli_modern import ModernCLI
            if ModernCLI.is_available():
                self.modern_cli = ModernCLI(self)
        except ImportError:
            pass
        self._header_notices: List[Dict[str, str]] = []

    def language(self) -> str:
        choice = str(self.store.get_config().get("ui_language") or "auto")
        if choice == "zh" or choice == "en":
            return choice
        return "zh" if str(os.environ.get("LANG") or "").lower().startswith("zh") else "en"

    def tr(self, key: str, **vars: Any) -> str:
        table = CONSOLE_I18N.get(self.language(), CONSOLE_I18N["en"])
        text = table.get(key, key)
        for name, value in vars.items():
            text = text.replace(f"{{{name}}}", str(value))
        return text

    def pause(self) -> None:
        if self.modern_cli:
            self.modern_cli.pause()
        else:
            input(f"{self.tr('press_enter')}: ")

    def print_menu_lines(self, lines: List[str]) -> None:
        if self.modern_cli:
            self.modern_cli.print_menu(lines)
        else:
            for line in lines:
                self.print_info(line)

    def supports_single_key_choice(self) -> bool:
        stdin = getattr(sys, "stdin", None)
        stdout = getattr(sys, "stdout", None)
        if stdin is None or stdout is None:
            return False
        stdin_isatty = getattr(stdin, "isatty", None)
        stdout_isatty = getattr(stdout, "isatty", None)
        if not callable(stdin_isatty) or not callable(stdout_isatty):
            return False
        return bool(stdin_isatty() and stdout_isatty())

    def read_single_key(self, default: str = "0") -> str:
        if not self.supports_single_key_choice():
            return input().strip() or default

        if os.name == "nt":
            import msvcrt

            while True:
                char = msvcrt.getwch()
                if char in {"\x00", "\xe0"}:
                    msvcrt.getwch()
                    continue
                if char in {"\r", "\n"}:
                    return default
                if char == "\x03":
                    raise KeyboardInterrupt
                if char == "\x04":
                    raise EOFError
                if char in {"\x08", "\x7f"}:
                    continue
                return char

        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                char = sys.stdin.read(1)
                if not char:
                    return default
                if char in {"\r", "\n"}:
                    return default
                if char == "\x03":
                    raise KeyboardInterrupt
                if char == "\x04":
                    raise EOFError
                if char == "\x1b":
                    while True:
                        ready, _, _ = select.select([fd], [], [], 0)
                        if not ready:
                            break
                        os.read(fd, 1)
                    continue
                if char in {"\x08", "\x7f"}:
                    continue
                return char
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def supports_ansi(self) -> bool:
        if not sys.stdout.isatty():
            return False
        if os.name != "nt":
            return True
        return bool(
            os.environ.get("WT_SESSION")
            or os.environ.get("ANSICON")
            or os.environ.get("TERM_PROGRAM")
            or os.environ.get("ConEmuANSI") == "ON"
        )

    def clear_screen(self) -> None:
        if self.modern_cli:
            self.modern_cli.clear()
        elif self.supports_ansi():
            self.print_info("\033[2J\033[H", end="")

    def prompt(self, label: str, current: Any) -> str:
        if self.modern_cli:
            return self.modern_cli.prompt(label, current)
        return input(f"{label} [{current}]: ").strip()

    def prompt_yes_no(self, question: str, default: bool = True) -> bool:
        if self.modern_cli:
            return self.modern_cli.confirm(question, default)
        answer = input(f"{question} ").strip().lower()
        if not answer:
            return default
        return answer in {"y", "yes", "1", "true"}

    def print_success(self, message: str) -> None:
        """Print success message."""
        if self.modern_cli:
            self.modern_cli.success(message)
        else:
            print(f"✓ {message}")

    def print_error(self, message: str) -> None:
        """Print error message."""
        if self.modern_cli:
            self.modern_cli.error(message)
        else:
            print(f"✗ {message}")

    def print_info(self, message: str) -> None:
        """Print info message."""
        if self.modern_cli:
            self.modern_cli.info(message)
        else:
            print(message)

    def queue_notice(self, message: str, kind: str = "info") -> None:
        self._header_notices.append({"kind": str(kind or "info"), "message": str(message or "")})

    def queue_notices(self, messages: List[str], kind: str = "info") -> None:
        for message in messages:
            self.queue_notice(message, kind=kind)

    def consume_notices(self) -> List[Dict[str, str]]:
        notices = list(self._header_notices)
        self._header_notices.clear()
        return notices

    def print_spacer(self) -> None:
        """Print a blank spacer line."""
        if self.modern_cli:
            self.modern_cli.blank_line()
        else:
            print()

    def prompt_choice(self, label: Optional[str] = None) -> str:
        """Prompt for menu choice."""
        if self.modern_cli:
            return self.modern_cli.prompt_choice(label)
        label = label or self.tr('prompt')
        if self.supports_single_key_choice():
            print(f"{label}: ", end="", flush=True)
            choice = self.read_single_key(default="0")
            print(choice)
            return choice.strip()
        return input(f"{label}: ").strip()

    def terminal_width(self) -> int:
        if self.modern_cli and getattr(self.modern_cli, "console", None) is not None:
            try:
                return max(40, int(self.modern_cli.console.size.width))
            except Exception:
                pass
        return max(40, shutil.get_terminal_size(fallback=(80, 24)).columns)

    def get_runtime_snapshot(self) -> Dict[str, Any]:
        attached_status = self.service.attached_status_payload()
        if attached_status is not None:
            return attached_status
        runtime = self.service.runtime_info()
        service_snapshot = self.service.status_snapshot()
        snapshot = self.store.get_status(
            runtime["host"],
            runtime["port"],
            service_state=str(service_snapshot.get("state") or "stopped"),
            service_error=str(service_snapshot.get("error") or self.service.last_error),
            service_details=service_snapshot,
        )
        snapshot["runtime"] = runtime
        return snapshot

    def protocol_console_label(self, protocol: str) -> str:
        return compute_protocol_console_label(self.language(), self.tr, protocol)

    def format_client_status_line(self, client_name: str, info: Dict[str, Any]) -> str:
        return compute_client_status_line(self.language(), client_name, info)

    def service_status_short_label(self, service_state: str) -> str:
        return self.tr(f"service_{service_state}").replace("服务状态: ", "").replace("Service: ", "")

    def routing_strategy_from_snapshot(self, snapshot: Dict[str, Any], protocol: str) -> str:
        routing = (((snapshot.get("routing") or {}).get("protocols")) or {}).get(protocol, {})
        if routing:
            if not bool(routing.get("auto_routing_enabled", True)):
                return self.routing_strategy_label("manual")
            mode = str(routing.get("routing_mode") or "priority")
            if mode == "manual_lock":
                return self.routing_strategy_label("manual")
            return self.routing_strategy_label(mode)
        return self.routing_strategy_label(routing_strategy_from_config(self.store.get_config(), protocol))

    def runtime_source_summary(self, snapshot: Dict[str, Any]) -> Dict[str, str]:
        service = snapshot.get("service") or {}
        if str(service.get("owner") or "local") != "external":
            return {"label": self.tr("config_path"), "value": str(self.config_path)}
        runtime = snapshot.get("runtime") or {}
        origin = self.service.external_origin or {}
        host = str(origin.get("host") or runtime.get("host") or "127.0.0.1")
        if host in {"0.0.0.0", "::", ""}:
            host = "127.0.0.1"
        port = origin.get("port") or runtime.get("web_ui_port") or runtime.get("port") or ""
        attached_url = f"http://{host}:{port}/" if port else str(runtime.get("dashboard_url") or "")
        return {
            "label": self.tr("runtime_source"),
            "value": self.tr("runtime_source_external", url=attached_url, path=self.config_path),
        }

    def _runtime_apply_enabled(self, snapshot: Dict[str, Any]) -> bool:
        service = snapshot.get("service") or {}
        if str(service.get("owner") or "local") == "external":
            return False
        if str(service.get("state") or "") in {"running", "partial"}:
            return True
        active_protocols = [
            normalize_upstream_protocol(protocol)
            for protocol in (service.get("active_protocols") or [])
            if normalize_upstream_protocol(protocol) in UPSTREAM_PROTOCOL_ORDER
        ]
        return bool(active_protocols)

    def _normalized_runtime_reference_config(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        config = normalize_config(self.store.get_config())
        runtime = snapshot.get("runtime") or {}
        config["listen_host"] = str(runtime.get("listen_host") or runtime.get("host") or config.get("listen_host") or "127.0.0.1")
        config["listen_port"] = int(runtime.get("listen_port") or config.get("listen_port") or DEFAULT_LISTEN_PORT)
        config["endpoint_mode"] = normalize_endpoint_mode(runtime.get("endpoint_mode") or config.get("endpoint_mode"))
        config["shared_api_prefixes"] = normalize_shared_api_prefixes(runtime.get("shared_api_prefixes") or config.get("shared_api_prefixes"))
        config["split_api_ports"] = normalize_split_api_ports(runtime.get("split_api_ports") or config.get("split_api_ports"), config["listen_port"])
        config["web_ui_port"] = int(runtime.get("web_ui_port") or runtime.get("port") or config.get("web_ui_port") or 0)
        return normalize_config(config)

    def _global_runtime_slice(self, config: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_config(config)
        endpoint_mode = normalize_endpoint_mode(normalized.get("endpoint_mode"))
        payload: Dict[str, Any] = {
            "endpoint_mode": endpoint_mode,
            "listen_host": str(normalized.get("listen_host") or "127.0.0.1"),
            "web_ui_port": int(normalized.get("web_ui_port") or 0),
        }
        if endpoint_mode == "shared":
            payload["listen_port"] = int(normalized.get("listen_port") or DEFAULT_LISTEN_PORT)
            payload["shared_api_prefixes"] = normalize_shared_api_prefixes(normalized.get("shared_api_prefixes"))
        else:
            payload["split_api_ports"] = normalize_split_api_ports(
                normalized.get("split_api_ports"),
                int(normalized.get("listen_port") or DEFAULT_LISTEN_PORT),
            )
        return payload

    def _protocol_runtime_slice(self, config: Dict[str, Any], protocol: str) -> Dict[str, Any]:
        normalized = normalize_config(config)
        endpoint_mode = normalize_endpoint_mode(normalized.get("endpoint_mode"))
        normalized_protocol = normalize_upstream_protocol(protocol)
        if endpoint_mode == "shared":
            prefixes = normalize_shared_api_prefixes(normalized.get("shared_api_prefixes"))
            return {
                "endpoint_mode": "shared",
                "listen_host": str(normalized.get("listen_host") or "127.0.0.1"),
                "listen_port": int(normalized.get("listen_port") or DEFAULT_LISTEN_PORT),
                "path": str(prefixes.get(normalized_protocol) or ""),
            }
        split_ports = normalize_split_api_ports(
            normalized.get("split_api_ports"),
            int(normalized.get("listen_port") or DEFAULT_LISTEN_PORT),
        )
        return {
            "endpoint_mode": "split",
            "listen_host": str(normalized.get("listen_host") or "127.0.0.1"),
            "listen_port": int(split_ports.get(normalized_protocol) or DEFAULT_LISTEN_PORT),
        }

    def runtime_apply_status(self, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current_snapshot = snapshot or self.get_runtime_snapshot()
        service = current_snapshot.get("service") or {}
        default_status = {
            "enabled": False,
            "settings": False,
            "global_runtime": False,
            "protocol_workspace": False,
            "protocols": {protocol: False for protocol in UPSTREAM_PROTOCOL_ORDER},
            "labels": [],
            "count": 0,
            "owner": str(service.get("owner") or "local"),
            "service_state": str(service.get("state") or "stopped"),
        }
        if not self._runtime_apply_enabled(current_snapshot):
            return default_status

        saved_config = normalize_config(self.store.get_config())
        runtime_config = self._normalized_runtime_reference_config(current_snapshot)
        global_pending = self._global_runtime_slice(saved_config) != self._global_runtime_slice(runtime_config)
        protocol_pending = {
            protocol: self._protocol_runtime_slice(saved_config, protocol) != self._protocol_runtime_slice(runtime_config, protocol)
            for protocol in UPSTREAM_PROTOCOL_ORDER
        }
        protocol_labels = [
            self.protocol_console_label(protocol)
            for protocol, pending in protocol_pending.items()
            if pending
        ]
        labels = list(protocol_labels)
        if global_pending:
            labels.insert(0, "全局运行与端口" if self.language() == "zh" else "Global runtime & ports")
        return {
            "enabled": global_pending or any(protocol_pending.values()),
            "settings": global_pending or any(protocol_pending.values()),
            "global_runtime": global_pending or any(protocol_pending.values()),
            "protocol_workspace": any(protocol_pending.values()),
            "protocols": protocol_pending,
            "labels": labels,
            "count": len(protocol_labels),
            "owner": str(service.get("owner") or "local"),
            "service_state": str(service.get("state") or "stopped"),
        }

    def runtime_apply_summary(self, snapshot: Optional[Dict[str, Any]] = None) -> str:
        status = self.runtime_apply_status(snapshot)
        if not status.get("enabled"):
            return ""
        labels = status.get("labels") or []
        if not labels:
            return self.tr("apply_pending_label")
        return f"{self.tr('apply_pending_label')}: {', '.join(str(label) for label in labels)}"

    def pending_badge(self, pending: bool, count: int = 0) -> str:
        if not pending:
            return ""
        short = self.tr("apply_pending_short")
        if count > 1:
            return f" [{count} {short}]" if self.language() == "en" else f" [{count}{short}]"
        return f" [{short}]"

    def runtime_previous_config(self, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current_snapshot = snapshot or self.get_runtime_snapshot()
        return self._normalized_runtime_reference_config(current_snapshot)

    def apply_saved_runtime_changes(self) -> Dict[str, Any]:
        snapshot = self.get_runtime_snapshot()
        status = self.runtime_apply_status(snapshot)
        if status["owner"] == "external":
            result = {"ok": False, "message": "external_runtime"}
            self.queue_notice(self.tr("apply_external_unavailable"), kind="warning")
            return result
        if not self._runtime_apply_enabled(snapshot):
            result = {"ok": False, "message": "service_not_running"}
            self.queue_notice(self.tr("apply_not_running"), kind="warning")
            return result
        if not status["enabled"]:
            result = {"ok": True, "apply_required": False, "message": "no_runtime_changes"}
            self.queue_notice(self.tr("apply_not_needed"), kind="info")
            return result
        previous_config = self.runtime_previous_config(snapshot)
        result = self.runtime_controller.apply_runtime_changes_with_recovery(previous_config)
        if result.get("ok"):
            self.queue_notice(self.tr("apply_ok"), kind="success")
        else:
            self.queue_notice(self.tr("start_fail", message=result.get("message") or "runtime_apply_failed"), kind="error")
        return result

    def print_header(self) -> None:
        if self.modern_cli:
            self.modern_cli.print_header()
            return

        self.clear_screen()
        snapshot = self.get_runtime_snapshot()
        runtime = self.service.runtime_info()
        hub_dashboard_url = runtime["dashboard_url"]
        service_info = snapshot.get("service", {})
        service_state = str(service_info.get("state") or self.service.status_state())
        service_error = str(service_info.get("error") or self.service.last_error or "")
        active_protocols = [
            protocol
            for protocol in (service_info.get("active_protocols") or [])
            if normalize_upstream_protocol(protocol) in UPSTREAM_PROTOCOL_ORDER
        ]
        if service_state == "running":
            service_label = f"🟢 {self.tr('service_running')}"
        elif service_state == "partial":
            service_label = f"🟡 {self.tr('service_partial')}"
        elif service_state == "external":
            service_label = f"🟡 {self.tr('service_external')}"
        elif service_state == "error":
            service_label = f"🔴 {self.tr('service_error')}"
        else:
            service_label = f"⚪ {self.tr('service_stopped')}"
        divider = "=" * min(max(self.terminal_width() - 2, 36), 96)
        source = self.runtime_source_summary(snapshot)
        print()
        self.print_info(divider)
        self.print_info(self.tr("title"))
        self.print_info(f"{source['label']}: {source['value']}")
        self.print_info(service_label)
        if active_protocols:
            services_text = ", ".join(self.protocol_console_label(protocol) for protocol in active_protocols)
            self.print_info(f"   {self.tr('service_active_protocols', services=services_text)}")
        if service_state == "error" and service_error:
            self.print_info(f"   {service_error}")
        elif self.service.last_warning:
            self.print_info(f"   {self.service.last_warning}")
        clients = snapshot.get("clients", {})
        for client_id in ("codex", "claude", "gemini"):
            info = clients[client_id]
            self.print_info(self.format_client_status_line(client_display_name(client_id), info))
            if info["state"] == "error" and info.get("message"):
                self.print_info(f"   {info['message']}")
        hub_label = "Hub 地址" if self.language() == "zh" else "Hub URL"
        self.print_info(f"{hub_label}: {hub_dashboard_url}")
        pending_summary = self.runtime_apply_summary(snapshot)
        if pending_summary:
            self.print_info(f"⚠ {pending_summary}")
        routing_protocols = (((snapshot.get("routing") or {}).get("protocols")) or {})
        routing_summary = " | ".join(
            f"{self.protocol_console_label(protocol)}={self.routing_strategy_from_snapshot(snapshot, protocol)}"
            for protocol in UPSTREAM_PROTOCOL_ORDER
        )
        count_summary = " | ".join(
            f"{self.protocol_console_label(protocol)}={routing_protocols.get(protocol, {}).get('upstream_count', 0)}"
            for protocol in UPSTREAM_PROTOCOL_ORDER
        )
        self.print_info(f"{self.tr('routing_strategy')}: {routing_summary}")
        self.print_info(f"{self.tr('upstream_count')}: {count_summary}")
        self.print_info(divider)
        for notice in self.consume_notices():
            prefix = {
                "success": "✓",
                "error": "✗",
                "warning": "⚠",
            }.get(str(notice.get("kind") or "info"), "•")
            self.print_info(f"{prefix} {notice.get('message') or ''}")

    def ensure_initial_language_choice(self) -> None:
        config = self.store.get_config()
        if config.get("ui_language_initialized"):
            return
        print()
        divider = "=" * min(max(self.terminal_width() - 2, 36), 96)
        self.print_info(divider)
        self.print_info(self.tr("first_language_title"))
        self.print_info(self.tr("first_language_subtitle"))
        self.print_info(divider)
        choice = self.prompt_choice().strip().lower()
        if choice == "1":
            config["ui_language"] = "en"
        elif choice == "2":
            config["ui_language"] = "zh"
        config["ui_language_initialized"] = True
        self.save_config(config)

    def routing_strategy_label(self, strategy: str) -> str:
        return compute_routing_strategy_label(self.tr, strategy)

    def open_web_console(self) -> None:
        result = self.ensure_dashboard_with_recovery()
        if not result.get("ok"):
            message = self.tr("already_running") if result.get("message") == "already_running" else result.get("message")
            self.print_info(self.tr("start_fail", message=message))
            self.pause()
            return
        url = self.service.runtime_info()["dashboard_url"]
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        self.print_info(self.tr("open_browser_ok" if opened else "open_browser_fail", url=url))

    def save_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        before_status = self.runtime_apply_status()
        saved = self.store.save_config(config)
        after_status = self.runtime_apply_status()
        if after_status["enabled"] and not before_status["enabled"]:
            self.queue_notice(self.tr("apply_pending_notice"), kind="warning")
        return saved


    def activation_label(self, upstream_id: str, enabled: bool, snapshot: Dict[str, Any], protocol: str) -> str:
        return compute_activation_label(self.tr, upstream_id, enabled, snapshot, protocol)

    def probe_label(self, stats: Dict[str, Any]) -> str:
        return compute_probe_label(self.tr, stats)

    def protocol_label(self, protocol: str) -> str:
        return compute_protocol_label(self.language(), protocol)

    def test_upstream(self, index: int) -> None:
        config = self.store.get_config()
        upstream = config["upstreams"][index]
        try:
            result = perform_upstream_probe_request(upstream, self.store.get_timeout())
            self.store.record_probe_result(upstream["id"], status=result["status"], latency_ms=result["latency_ms"], models_count=result["models_count"])
            self.print_info(self.tr("test_ok", status=result["status"], latency=result["latency_ms"], models=result.get("models_count")))
        except Exception as exc:
            self.store.record_probe_result(upstream["id"], status=None, error=str(exc))
            self.print_info(self.tr("test_fail", message=str(exc)))
        self.pause()

    def delete_upstream(self, index: int) -> None:
        config = self.store.get_config()
        if not self.prompt_yes_no(self.tr("delete_confirm"), default=False):
            return
        config["upstreams"].pop(index)
        self.save_config(config)
        self.print_info(self.tr("deleted"))
        self.pause()

    def colorize(self, text: str, index: int) -> str:
        if not self.supports_ansi():
            return text
        return f"{self.COLOR_CODES[index % len(self.COLOR_CODES)]}{text}{self.COLOR_RESET}"

    def format_usage_label(self, start_ts_ms: int) -> str:
        return compute_usage_label(self.usage_range, start_ts_ms)

    def theme_label(self, mode: str) -> str:
        return compute_theme_label(self.language(), mode)

    def cli_theme_mode(self) -> str:
        config = self.store.get_config()
        return normalize_cli_theme_mode(config.get("cli_theme_mode") or config.get("theme_mode"))

    def current_cli_theme_label(self) -> str:
        return self.theme_label(self.cli_theme_mode())

    def current_language_label(self) -> str:
        value = normalize_ui_language(self.store.get_config().get("ui_language"))
        return compute_current_language_label(self.language(), value)

    def usage_scope_label(self) -> str:
        return compute_usage_scope_label(self.language(), str(getattr(self, "usage_protocol", "all") or "all"))

    def usage_local_key_label(self) -> str:
        selected = str(getattr(self, "usage_local_key", "all") or "all")
        if selected == "all":
            return "全部本地Key" if self.language() == "zh" else "All Local Keys"
        if selected == "":
            return "直连 / 未鉴权" if self.language() == "zh" else "Direct / No Local Key"
        config = self.store.get_config()
        for item in config.get("local_api_keys") or []:
            if str(item.get("id") or "") == selected:
                return str(item.get("name") or selected)
        return selected

    def protocol_runtime_url(self, runtime: Dict[str, Any], protocol: str) -> str:
        return compute_protocol_runtime_url(runtime, protocol)

    def protocol_is_active(self, snapshot: Dict[str, Any], protocol: str) -> bool:
        return compute_protocol_is_active(snapshot, protocol)

    def protocol_service_status_label(self, snapshot: Dict[str, Any], protocol: str) -> str:
        return compute_protocol_service_status_label(self.language(), snapshot, protocol)

    def protocol_client_status_label(self, snapshot: Dict[str, Any], protocol: str) -> str:
        return compute_protocol_client_status_label(self.language(), snapshot, protocol)

    def runtime_mode_label(self, snapshot: Dict[str, Any]) -> str:
        return compute_runtime_mode_label(self.language(), snapshot)

    def masked_secret(self, value: str) -> str:
        return compute_masked_secret(value)

    def protocol_upstream_indices(self, config: Dict[str, Any], protocol: str) -> List[int]:
        return [
            index
            for index, upstream in enumerate(config.get("upstreams") or [])
            if normalize_upstream_protocol(upstream.get("protocol")) == protocol
        ]

    def prompt_local_index(self, count: int) -> Optional[int]:
        if count <= 9 and self.supports_single_key_choice():
            value = self.prompt_choice(self.tr("choose_index")).strip()
        else:
            value = input(f"{self.tr('choose_index')}: ").strip()
        if not value.isdigit():
            self.print_info(self.tr("invalid"))
            self.pause()
            return None
        index = int(value)
        if not 1 <= index <= count:
            self.print_info(self.tr("invalid"))
            self.pause()
            return None
        return index - 1

    def format_protocol_list(self, protocols: List[str]) -> str:
        return compute_protocol_list(protocols)

    def prompt_allowed_protocols(self, current: List[str]) -> Optional[List[str]]:
        self.print_info("1 Codex | 2 Claude | 3 Gemini | a All")
        prompt_text = "允许类型" if self.language() == "zh" else "Allowed protocols"
        current_value = allowed_protocol_input_value(normalize_local_key_protocols(current))
        raw = input(f"{prompt_text} [{current_value or 'a'}]: ").strip().lower()
        parsed = parse_allowed_protocols_input(raw)
        if parsed is None:
            return None
        if not parsed:
            self.print_info(self.tr("invalid"))
            self.pause()
            return None
        return parsed

    def run(self) -> None:
        self.ensure_initial_language_choice()
        dashboard_result = self.ensure_dashboard_with_recovery()
        if not dashboard_result.get("ok"):
            self.print_info(self.tr("start_fail", message=dashboard_result.get("message") or "dashboard_start_failed"))
            self.pause()
        elif dashboard_result.get("attached_to_external"):
            # 成功接管外部运行的实例
            msg = "✓ 已连接到后台运行的服务实例" if self.language() == "zh" else "✓ Attached to background service instance"
            self.print_info(msg)
            self.pause()
        while True:
            self.print_header()
            pending_status = self.runtime_apply_status()
            self.print_menu_lines(
                [
                    "1. ★ " + ("打开 Web 控制台" if self.language() == "zh" else "Open Web dashboard"),
                    "2. " + ("运行与设置" if self.language() == "zh" else "Runtime & settings") + self.pending_badge(bool(pending_status["settings"])),
                    "3. " + ("协议工作区" if self.language() == "zh" else "Protocol workspace") + self.pending_badge(bool(pending_status["protocol_workspace"]), int(pending_status["count"])),
                    "4. " + ("本地 API Keys" if self.language() == "zh" else "Local API keys"),
                    "5. " + ("用量统计" if self.language() == "zh" else "Usage stats"),
                    "6. " + ("语言 / CLI 主题" if self.language() == "zh" else "Language / CLI theme"),
                    "0. " + ("退出" if self.language() == "zh" else "Exit"),
                ]
            )
            choice = self.prompt_choice().lower()
            if choice == "1":
                self.open_web_console()
            elif choice == "2":
                self.menu_runtime_settings()
            elif choice == "3":
                self.menu_protocol_workspace_selector()
            elif choice == "4":
                self.menu_local_api_keys()
            elif choice == "5":
                self.menu_usage()
            elif choice == "6":
                self.menu_appearance()
            elif choice == "0":
                self.service.shutdown()
                self.print_info(self.tr("bye"))
                return
            else:
                self.print_info(self.tr("invalid"))
                self.pause()

from __future__ import annotations

from typing import TYPE_CHECKING

from .config_logic import default_model_settings_from_config
from .constants import UPSTREAM_PROTOCOL_ORDER
from .network import protocol_client_id
from .protocols import normalize_upstream_protocol

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliWorkspaceController:
    def __init__(self, app: "InteractiveConsoleApp") -> None:
        self.app = app

    def menu_global_runtime(self) -> None:
        while True:
            self.app.print_header()
            snapshot = self.app.get_runtime_snapshot()
            apply_status = self.app.runtime_apply_status(snapshot)
            service = snapshot.get("service") or {}
            active_protocols = [
                self.app.protocol_console_label(protocol)
                for protocol in (service.get("active_protocols") or [])
                if normalize_upstream_protocol(protocol) in UPSTREAM_PROTOCOL_ORDER
            ]
            self.app.print_spacer()
            self.app.print_info("--- " + ("全局运行" if self.app.language() == "zh" else "Global runtime") + " ---")
            self.app.print_info(f"{'当前模式' if self.app.language() == 'zh' else 'Current mode'}: {self.app.runtime_mode_label(snapshot)}")
            self.app.print_info(
                f"{self.app.tr('service_active_protocols', services=', '.join(active_protocols) if active_protocols else self.app.tr('service_none'))}"
            )
            pending_summary = self.app.runtime_apply_summary(snapshot)
            if pending_summary:
                self.app.print_info(f"⚠ {pending_summary}")
            self.app.print_menu_lines(
                [
                    "1. " + ("启动代理模式" if self.app.language() == "zh" else "Start proxy mode"),
                    "2. " + ("启动转发模式" if self.app.language() == "zh" else "Start forwarding mode"),
                    "3. " + ("停止全部服务" if self.app.language() == "zh" else "Stop all services"),
                    "4. " + self.app.tr("apply_now") + self.app.pending_badge(bool(apply_status["enabled"])),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                result = self.app.start_service_with_recovery()
                if not result.get("ok"):
                    message = self.app.tr("already_running") if result.get("message") == "already_running" else result.get("message")
                    self.app.queue_notice(self.app.tr("start_fail", message=message), kind="error")
                else:
                    self.app.queue_notice("代理模式已启动。" if self.app.language() == "zh" else "Proxy mode started.", kind="success")
                    self.app.queue_notices(self.app.client_action_result_lines(result.get("switch_results") or {}, "switch"))
                continue
            if choice == "2":
                result = self.app.start_forwarding_with_recovery()
                if not result.get("ok"):
                    message = self.app.tr("already_running") if result.get("message") == "already_running" else result.get("message")
                    self.app.queue_notice(self.app.tr("start_fail", message=message), kind="error")
                else:
                    self.app.queue_notice("转发模式已启动。" if self.app.language() == "zh" else "Forwarding mode started.", kind="success")
                    self.app.queue_notices(self.app.client_action_result_lines(result.get("restore_results") or {}, "restore"))
                continue
            if choice == "3":
                stopped = self.app.service.stop()
                if not stopped:
                    self.app.queue_notice(self.app.tr("not_running"), kind="warning")
                else:
                    self.app.queue_notice(self.app.tr("stop_ok"), kind="success")
                    self.app.queue_notices(self.app.client_action_result_lines(self.app.service.last_restore_results, "restore"))
                continue
            if choice == "4":
                self.app.apply_saved_runtime_changes()
                continue
            self.app.queue_notice(self.app.tr("invalid"), kind="warning")

    def menu_protocol_workspace_selector(self) -> None:
        while True:
            self.app.print_header()
            apply_status = self.app.runtime_apply_status()
            self.app.print_spacer()
            self.app.print_info("--- " + ("协议工作区" if self.app.language() == "zh" else "Protocol workspace") + " ---")
            self.app.print_menu_lines(
                [
                    "1. Codex / OpenAI" + self.app.pending_badge(bool(apply_status["protocols"].get("openai"))),
                    "2. Claude / Anthropic" + self.app.pending_badge(bool(apply_status["protocols"].get("anthropic"))),
                    "3. Gemini" + self.app.pending_badge(bool(apply_status["protocols"].get("gemini"))),
                    "4. Local LLM" + self.app.pending_badge(bool(apply_status["protocols"].get("local_llm"))),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            mapping = {"1": "openai", "2": "anthropic", "3": "gemini", "4": "local_llm"}
            if choice == "0":
                return
            if choice in mapping:
                self.app.menu_protocol_workspace(mapping[choice])
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_protocol_workspace(self, protocol: str) -> None:
        while True:
            self.app.print_header()
            snapshot = self.app.get_runtime_snapshot()
            apply_status = self.app.runtime_apply_status(snapshot)
            runtime = snapshot.get("runtime") or {}
            routing = (((snapshot.get("routing") or {}).get("protocols")) or {}).get(protocol, {})
            model_settings = default_model_settings_from_config(self.app.store.get_config(), protocol)
            self.app.print_spacer()
            self.app.print_info(f"--- {self.app.protocol_console_label(protocol)} ---")
            self.app.print_info(f"{'本地入口' if self.app.language() == 'zh' else 'Local endpoint'}: {self.app.protocol_runtime_url(runtime, protocol)}")
            self.app.print_info(f"{'代理状态' if self.app.language() == 'zh' else 'Proxy service'}: {self.app.protocol_service_status_label(snapshot, protocol)}")
            self.app.print_info(f"{'本机使用' if self.app.language() == 'zh' else 'This machine'}: {self.app.protocol_client_status_label(snapshot, protocol)}")
            self.app.print_info(
                f"{'缺省模型来源' if self.app.language() == 'zh' else 'Fallback model source'}: "
                f"{self.app.tr('default_model_mode_global') if model_settings['mode'] == 'global' else self.app.tr('default_model_mode_upstream')}"
            )
            self.app.print_info(
                f"{'协议默认模型' if self.app.language() == 'zh' else 'Protocol default model'}: "
                f"{model_settings['global_default_model'] or '-'}"
            )
            self.app.print_info(
                f"{self.app.tr('routing_strategy')}: {self.app.routing_strategy_from_snapshot(snapshot, protocol)}"
            )
            self.app.print_info(f"{self.app.tr('manualActiveUpstream')}: {routing.get('manual_active_upstream_name') or '-'}")
            self.app.print_info(
                f"{'最近命中' if self.app.language() == 'zh' else 'Recent hit'}: "
                f"{routing.get('last_used_upstream_name') or '-'}"
            )
            if apply_status["protocols"].get(protocol):
                self.app.print_info(f"⚠ {self.app.tr('apply_runtime_network_hint')}")
            self.app.print_menu_lines(
                [
                    "1. " + ("运行控制" if self.app.language() == "zh" else "Runtime controls"),
                    "2. " + ("默认模型" if self.app.language() == "zh" else "Default model"),
                    "3. " + self.app.tr("routing_controls"),
                    "4. " + ("上游 API" if self.app.language() == "zh" else "Upstreams"),
                    "5. " + ("测试连接" if self.app.language() == "zh" else "Test all upstreams"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.app.menu_protocol_runtime(protocol)
            elif choice == "2":
                self.app.menu_protocol_default_models(protocol)
            elif choice == "3":
                self.app.menu_protocol_routing(protocol)
            elif choice == "4":
                self.app.menu_protocol_upstreams(protocol)
            elif choice == "5":
                self.app.test_all_upstreams(protocol)
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_protocol_runtime(self, protocol: str) -> None:
        while True:
            self.app.print_header()
            snapshot = self.app.get_runtime_snapshot()
            apply_status = self.app.runtime_apply_status(snapshot)
            runtime = snapshot.get("runtime") or {}
            self.app.print_spacer()
            self.app.print_info(f"--- {self.app.protocol_console_label(protocol)} / {('运行控制' if self.app.language() == 'zh' else 'Runtime controls')} ---")
            self.app.print_info(f"{'本地入口' if self.app.language() == 'zh' else 'Local endpoint'}: {self.app.protocol_runtime_url(runtime, protocol)}")
            self.app.print_info(f"{'代理状态' if self.app.language() == 'zh' else 'Proxy service'}: {self.app.protocol_service_status_label(snapshot, protocol)}")
            self.app.print_info(f"{'本机使用' if self.app.language() == 'zh' else 'This machine'}: {self.app.protocol_client_status_label(snapshot, protocol)}")
            if apply_status["protocols"].get(protocol):
                self.app.print_info(f"⚠ {self.app.tr('apply_runtime_network_hint')}")
            self.app.print_menu_lines(
                [
                    "1. " + ("启动代理" if self.app.language() == "zh" else "Start proxy"),
                    "2. " + ("停止代理" if self.app.language() == "zh" else "Stop proxy"),
                    "3. " + ("本机启用" if self.app.language() == "zh" else "Enable on this machine"),
                    "4. " + ("恢复本机" if self.app.language() == "zh" else "Restore local client"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                result = self.app.start_protocol_with_recovery(protocol)
                if result.get("ok"):
                    self.app.queue_notice("代理已启动。" if self.app.language() == "zh" else "Proxy started.", kind="success")
                else:
                    message = self.app.tr("already_running") if result.get("message") == "already_running" else result.get("message")
                    self.app.queue_notice(self.app.tr("start_fail", message=message), kind="error")
                continue
            if choice == "2":
                result = self.app.service.stop_protocol(protocol)
                if result.get("ok"):
                    self.app.queue_notice(self.app.tr("stop_ok"), kind="success")
                    restore_result = result.get("restore_result") or {}
                    self.app.queue_notices(self.app.client_action_result_lines({protocol_client_id(protocol): restore_result}, "restore"))
                else:
                    message = self.app.tr("not_running") if result.get("message") == "not_running" else result.get("message")
                    self.app.queue_notice(self.app.tr("start_fail", message=message), kind="error")
                continue
            if choice == "3":
                result = self.app.enable_client_for_protocol(protocol)
                if result.get("ok"):
                    self.app.queue_notice("本机已接入 Hub。" if self.app.language() == "zh" else "This machine now uses the Hub.", kind="success")
                else:
                    self.app.queue_notice(self.app.tr("start_fail", message=result.get("message") or "client_switch_failed"), kind="error")
                continue
            if choice == "4":
                result = self.app.restore_client_for_protocol(protocol)
                if result.get("ok") and result.get("restored", True):
                    self.app.queue_notice("本机配置已恢复。" if self.app.language() == "zh" else "Local client restored.", kind="success")
                elif result.get("ok"):
                    self.app.queue_notice("当前无需恢复。" if self.app.language() == "zh" else "Nothing to restore.", kind="warning")
                else:
                    self.app.queue_notice(self.app.tr("start_fail", message=result.get("message") or "client_restore_failed"), kind="error")
                continue
            self.app.queue_notice(self.app.tr("invalid"), kind="warning")


__all__ = ["CliWorkspaceController"]

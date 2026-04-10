from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict

from .client_switch import switch_client_to_local_hub
from .network import client_display_name, process_label, protocol_client_id
from .service_controller import restore_client_from_backup
from .utils import safe_int

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


def runtime_base_urls(runtime: Dict[str, Any]) -> Dict[str, str]:
    return {
        "codex": str(runtime.get("openai_base_url") or ""),
        "claude": str(runtime.get("claude_base_url") or ""),
        "gemini": str(runtime.get("gemini_base_url") or ""),
    }


class CliRuntimeController:
    def __init__(self, app: "InteractiveConsoleApp") -> None:
        self.app = app

    def client_action_result_lines(self, results: Dict[str, Dict[str, Any]], action: str) -> list[str]:
        lines: list[str] = []
        for client_id in ("codex", "claude", "gemini"):
            result = results.get(client_id) or {}
            if action == "switch":
                if result.get("ok"):
                    text = "已接入 Hub" if self.app.language() == "zh" else "connected to Hub"
                else:
                    text = (
                        f"接入失败: {result.get('message') or 'unknown'}"
                        if self.app.language() == "zh"
                        else f"connect failed: {result.get('message') or 'unknown'}"
                    )
            else:
                if result.get("ok") and result.get("restored", True):
                    text = "已恢复本机" if self.app.language() == "zh" else "restored"
                elif result.get("ok"):
                    text = "无需恢复" if self.app.language() == "zh" else "nothing to restore"
                else:
                    text = (
                        f"恢复失败: {result.get('message') or 'unknown'}"
                        if self.app.language() == "zh"
                        else f"restore failed: {result.get('message') or 'unknown'}"
                    )
            lines.append(f"{client_display_name(client_id)}: {text}")
        return lines

    def refresh_switched_clients(self) -> None:
        snapshot = self.app.get_runtime_snapshot()
        runtime = snapshot.get("runtime") or {}
        for client_id in ("codex", "claude", "gemini"):
            client_info = ((snapshot.get("clients") or {}).get(client_id) or {})
            if client_info.get("state") != "switched":
                continue
            result = switch_client_to_local_hub(client_id, runtime_base_urls(runtime), self.app.store.get_local_api_key())
            self.app.service.last_switch_results[client_id] = result

    def run_with_port_recovery(self, action: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
        result = action()
        if result.get("ok"):
            return result
        if result.get("error_code") != "port_in_use":
            return result
        port = safe_int(result.get("port"), 0)
        host = str(result.get("host", "127.0.0.1"))

        if port and self.app.service._is_ai_proxy_hub_running(host, port):
            attach_result = self.app.service.attach_external_instance(host, port)
            msg = (
                "检测到后台运行的 AI Proxy Hub 实例，已接管控制"
                if self.app.language() == "zh"
                else "Detected running AI Proxy Hub instance, attached successfully"
            )
            self.app.print_info(f"✓ {msg}")
            runtime = attach_result if attach_result.get("ok") else self.app.service.runtime_info()
            return {
                "ok": True,
                "attached_to_external": True,
                "message": "attached_to_running_instance",
                **runtime,
            }

        owner = process_label(result.get("port_owner")) or self.app.tr("port_owner_unknown")
        if not port or not self.app.prompt_yes_no(self.app.tr("port_in_use_prompt", port=port, owner=owner), default=False):
            return result
        termination = self.app.service.terminate_port_owner(port)
        if not termination.get("ok"):
            self.app.print_info(self.app.tr("port_release_fail", message=termination.get("message") or "unknown"))
            return result
        self.app.print_info(self.app.tr("port_release_ok"))
        return action()

    def start_service_with_recovery(self) -> Dict[str, Any]:
        return self.run_with_port_recovery(self.app.service.start_proxy_mode)

    def start_forwarding_with_recovery(self) -> Dict[str, Any]:
        return self.run_with_port_recovery(self.app.service.start_forwarding_mode)

    def start_protocol_with_recovery(self, protocol: str) -> Dict[str, Any]:
        return self.run_with_port_recovery(lambda: self.app.service.start_protocol(protocol))

    def ensure_dashboard_with_recovery(self) -> Dict[str, Any]:
        return self.run_with_port_recovery(self.app.service.ensure_dashboard_running)

    def apply_runtime_changes_with_recovery(self, previous_config: Dict[str, Any]) -> Dict[str, Any]:
        return self.run_with_port_recovery(lambda: self.app.service.apply_runtime_changes(previous_config))

    def print_client_action_results(self, results: Dict[str, Dict[str, Any]], action: str) -> None:
        for line in self.client_action_result_lines(results, action):
            self.app.print_info(line)

    def enable_client_for_protocol(self, protocol: str) -> Dict[str, Any]:
        snapshot = self.app.get_runtime_snapshot()
        if not self.app.protocol_is_active(snapshot, protocol):
            start_result = self.start_protocol_with_recovery(protocol)
            if not start_result.get("ok") and start_result.get("message") != "already_running":
                return start_result
        runtime = self.app.service.runtime_info()
        client_id = protocol_client_id(protocol)
        result = switch_client_to_local_hub(client_id, runtime_base_urls(runtime), self.app.store.get_local_api_key())
        self.app.service.last_switch_results[client_id] = result
        return result

    def restore_client_for_protocol(self, protocol: str) -> Dict[str, Any]:
        client_id = protocol_client_id(protocol)
        result = restore_client_from_backup(client_id)
        self.app.service.last_restore_results[client_id] = result
        return result


__all__ = ["CliRuntimeController", "runtime_base_urls"]

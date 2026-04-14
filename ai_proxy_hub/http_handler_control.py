from __future__ import annotations

import json
from typing import Any, Dict

from .client_switch import restore_client_from_backup, switch_client_to_local_hub
from .config_logic import normalize_upstream
from .network import build_error_payload, perform_upstream_probe_request
from .protocols import normalize_upstream_protocol


class RouterRequestHandlerControlMixin:
    def handle_save_config(self) -> None:
        try:
            payload = self.read_json_body()
            apply_runtime_changes = False
            config_payload = payload
            if isinstance(payload, dict) and isinstance(payload.get("config"), dict):
                config_payload = payload["config"]
                apply_runtime_changes = bool(payload.get("apply_runtime_changes"))
            elif isinstance(payload, dict):
                apply_runtime_changes = bool(payload.get("apply_runtime_changes"))
                if "apply_runtime_changes" in payload:
                    config_payload = dict(payload)
                    config_payload.pop("apply_runtime_changes", None)
            previous_config = self.store.get_config()
            config = self.store.save_config(config_payload)
        except json.JSONDecodeError:
            self.send_json(400, build_error_payload("配置 JSON 不合法。", code="invalid_json"))
            return
        response = {"ok": True, "config": config, "message_key": "config_saved", "restart_required_for_network_changes": True}
        service_controller = getattr(self.server, "service_controller", None)  # type: ignore[attr-defined]
        if apply_runtime_changes and service_controller is not None:
            apply_result = service_controller.schedule_runtime_apply(previous_config)
            response["runtime_apply_requested"] = True
            response["runtime_apply_scheduled"] = bool(apply_result.get("ok") and apply_result.get("apply_required"))
            if not apply_result.get("ok"):
                response["runtime_apply_error"] = str(apply_result.get("message") or "runtime_apply_failed")
                response["runtime_apply_error_code"] = str(apply_result.get("error_code") or "")
                if apply_result.get("port") is not None:
                    response["runtime_apply_port"] = int(apply_result["port"])
                if isinstance(apply_result.get("port_owner"), dict):
                    response["runtime_apply_port_owner"] = apply_result["port_owner"]
        self.send_json(200, response)

    def handle_import_config(self) -> None:
        try:
            payload = self.read_json_body()
            config_payload = payload.get("config") if isinstance(payload.get("config"), dict) else payload
            if not isinstance(config_payload, dict):
                self.send_json(400, build_error_payload("导入配置 JSON 不合法。", code="invalid_import_config"))
                return
            config = self.store.save_config(config_payload)
        except json.JSONDecodeError:
            self.send_json(400, build_error_payload("导入配置 JSON 不合法。", code="invalid_import_config"))
            return
        self.send_json(200, {"ok": True, "config": config, "message_key": "config_imported", "restart_required_for_network_changes": True})

    def handle_test_upstream(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError:
            self.send_json(400, build_error_payload("测试参数 JSON 不合法。", code="invalid_json"))
            return
        upstream = None
        upstream_id = str(payload.get("id") or "").strip()
        if isinstance(payload.get("upstream"), dict):
            upstream = normalize_upstream(payload["upstream"], 0)
            if upstream_id and not upstream.get("id"):
                upstream["id"] = upstream_id
            upstream_id = upstream["id"]
        elif upstream_id:
            upstream = self.store.get_upstream(upstream_id)

        if not upstream:
            self.send_json(404, build_error_payload("没有找到对应上游。", code="upstream_not_found"))
            return
        try:
            result = self.perform_upstream_probe(upstream)
            self.store.record_probe_result(
                upstream_id,
                status=result["status"],
                latency_ms=result.get("latency_ms"),
                models_count=result.get("models_count"),
                models=result.get("models"),
            )
            self.send_json(200, {"ok": True, "result": result})
        except Exception as exc:  # pragma: no cover
            self.store.record_probe_result(upstream["id"], status=None, error=str(exc))
            self.send_json(502, build_error_payload(f"测试失败: {exc}", code="probe_failed"))

    def perform_upstream_probe(self, upstream: Dict[str, Any]) -> Dict[str, Any]:
        return perform_upstream_probe_request(upstream, self.store.get_timeout())

    def handle_upstream_control(self) -> None:
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError:
            self.send_json(400, build_error_payload("上游控制参数 JSON 不合法。", code="invalid_json"))
            return
        action = str(payload.get("action") or "").strip().lower()
        upstream_id = str(payload.get("id") or "").strip()
        if not upstream_id:
            self.send_json(400, build_error_payload("缺少上游 ID。", code="missing_upstream_id"))
            return
        if action != "reactivate":
            self.send_json(400, build_error_payload("不支持的上游控制操作。", code="invalid_upstream_action"))
            return
        result = self.store.reactivate_upstream(upstream_id)
        if not result.get("ok"):
            self.send_json(404, build_error_payload("没有找到对应上游。", code="upstream_not_found"))
            return
        self.send_json(
            200,
            {
                "ok": True,
                "action": action,
                "result": result,
                "status": self.runtime_status_payload(),
            },
        )

    def handle_client_control(self) -> None:
        try:
            payload = self.read_json_body()
            client_id = str(payload.get("client") or "").strip().lower()
            action = str(payload.get("action") or "").strip().lower()
            if client_id not in {"codex", "claude", "gemini"}:
                self.send_json(400, build_error_payload("不支持的客户端类型。", code="invalid_client"))
                return
            if action not in {"switch", "restore"}:
                self.send_json(400, build_error_payload("不支持的客户端操作。", code="invalid_client_action"))
                return
            runtime_status = self.runtime_status_payload()
            runtime = runtime_status.get("runtime", {})
            runtime_base_urls = {
                "codex": str(runtime.get("openai_base_url") or ""),
                "claude": str(runtime.get("claude_base_url") or ""),
                "gemini": str(runtime.get("gemini_base_url") or ""),
            }
            result = (
                switch_client_to_local_hub(client_id, runtime_base_urls, self.store.get_local_api_key())
                if action == "switch"
                else restore_client_from_backup(client_id)
            )
            if not result.get("ok"):
                self.send_json(500, build_error_payload(str(result.get("message") or "client_action_failed"), code="client_action_failed"))
                return
            refreshed_status = self.runtime_status_payload()
            status = (refreshed_status.get("clients") or {}).get(client_id, {})
            self.send_json(200, {"ok": True, "client": client_id, "action": action, "result": result, "status": status})
        except (json.JSONDecodeError, OSError, PermissionError) as exc:
            self.send_json(500, build_error_payload(f"客户端操作失败: {exc}", code="client_action_failed"))

    def handle_service_control(self) -> None:
        service_controller = getattr(self.server, "service_controller", None)  # type: ignore[attr-defined]
        if service_controller is None:
            self.send_json(501, build_error_payload("当前服务实例不支持运行时服务控制。", code="service_control_unsupported"))
            return
        try:
            payload = self.read_json_body()
        except json.JSONDecodeError:
            self.send_json(400, build_error_payload("服务控制参数 JSON 不合法。", code="invalid_json"))
            return
        action = str(payload.get("action") or "").strip().lower()
        protocol = normalize_upstream_protocol(str(payload.get("protocol") or "").strip().lower() or "openai")
        if action == "start_forwarding":
            result = service_controller.start_forwarding_mode()
        elif action in {"start_proxy", "start_all"}:
            result = service_controller.start_proxy_mode()
        elif action == "stop_all":
            stopped = service_controller.stop()
            result = {"ok": stopped, "message": "stopped" if stopped else "not_running"}
        elif action == "start_protocol":
            result = service_controller.start_protocol(protocol)
        elif action == "stop_protocol":
            result = service_controller.stop_protocol(protocol)
        else:
            self.send_json(400, build_error_payload("不支持的服务控制操作。", code="invalid_service_action"))
            return
        service_snapshot = service_controller.status_snapshot()
        status_payload = self.runtime_status_payload(service_snapshot)
        response_status = 200 if result.get("ok") else 400
        payload = {
            "ok": bool(result.get("ok")),
            "action": action,
            "protocol": protocol,
            "result": result,
            "status": status_payload,
        }
        if not result.get("ok"):
            payload["message"] = str(result.get("message") or "service_control_failed")
        self.send_json(response_status, payload)

from __future__ import annotations

import copy
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import legacy_impl as _legacy
from .constants import UPSTREAM_PROTOCOL_ORDER
from .http_server import RouterHTTPServer, create_server
from .network import find_listening_process
from .network import client_display_name
from .protocols import normalize_upstream_protocol
from .service_controller_helpers import (
    api_spec_names,
    build_server_specs,
    build_server_specs_map,
    controller_runtime_settings,
    dashboard_spec_name,
    endpoint_reachable,
    fetch_hub_status,
    is_ai_proxy_hub_running,
    ordered_protocols,
    runtime_base_urls,
    runtime_info_payload,
    snapshot_payload,
)
from .service_controller_ops import (
    ensure_api_running,
    restore_client_for_protocol,
    shutdown_all,
    start_forwarding_mode,
    start_protocol as start_protocol_op,
    start_proxy_mode,
    start_spec_names,
    stop_all,
    stop_protocol as stop_protocol_op,
    terminate_port_owner_for_controller,
)
from .store import ConfigStore


def restore_all_clients_from_backup(*args, **kwargs):
    return _legacy.restore_all_clients_from_backup(*args, **kwargs)


def restore_client_from_backup(*args, **kwargs):
    return _legacy.restore_client_from_backup(*args, **kwargs)


def switch_all_clients_to_local_hub(*args, **kwargs):
    return _legacy.switch_all_clients_to_local_hub(*args, **kwargs)


class ServiceController:
    def __init__(self, config_path: Path, static_dir: Path, store: ConfigStore) -> None:
        self.config_path = config_path
        self.static_dir = static_dir
        self.store = store
        self.servers: Dict[str, RouterHTTPServer] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.last_error = ""
        self.last_warning = ""
        self.last_switch_results: Dict[str, Dict[str, Any]] = {}
        self.last_restore_results: Dict[str, Dict[str, Any]] = {}
        self.shared_exposed_protocols: tuple[str, ...] = tuple(UPSTREAM_PROTOCOL_ORDER)
        self.runtime_apply_lock = threading.Lock()
        self.external_runtime: Optional[Dict[str, Any]] = None
        self.external_service_snapshot: Optional[Dict[str, Any]] = None
        self.external_status_payload: Optional[Dict[str, Any]] = None
        self.external_origin: Optional[Dict[str, Any]] = None

    def restore_all_clients_from_backup(self, *args, **kwargs):
        return restore_all_clients_from_backup(*args, **kwargs)

    def restore_client_from_backup(self, *args, **kwargs):
        return restore_client_from_backup(*args, **kwargs)

    def _runtime_settings(self) -> Dict[str, Any]:
        return controller_runtime_settings(self.store.get_config())

    def _warning_message_for_results(self, results: Dict[str, Dict[str, Any]]) -> str:
        warnings = [f"{client_display_name(name)}: {result.get('message')}" for name, result in results.items() if not result.get("ok")]
        return " | ".join(warnings)

    def _store_client_results(self, results: Dict[str, Dict[str, Any]], *, use_local_hub: bool) -> Dict[str, Dict[str, Any]]:
        if use_local_hub:
            self.last_switch_results = results
        else:
            self.last_restore_results = results
        self.last_warning = self._warning_message_for_results(results)
        return results

    def _clear_external_attachment(self) -> None:
        self.external_runtime = None
        self.external_service_snapshot = None
        self.external_status_payload = None
        self.external_origin = None

    def _set_external_attachment(self, payload: Dict[str, Any], host: str, port: int) -> Dict[str, Any]:
        external_payload = copy.deepcopy(payload)
        runtime = copy.deepcopy(payload.get("runtime") or {})
        service = copy.deepcopy(payload.get("service") or {})
        runtime.setdefault("host", "127.0.0.1" if str(host) in {"0.0.0.0", "::", ""} else str(host))
        runtime.setdefault("port", int(runtime.get("web_ui_port") or port))
        runtime.setdefault("web_ui_port", int(runtime.get("port") or port))
        runtime_port = int(runtime.get("web_ui_port") or runtime.get("port") or port)
        active_server_names = list(service.get("active_server_names") or [])
        active_protocols = [
            normalize_upstream_protocol(protocol)
            for protocol in (service.get("active_protocols") or [])
            if normalize_upstream_protocol(protocol) in UPSTREAM_PROTOCOL_ORDER
        ]
        if not active_server_names or not active_protocols:
            derived_server_names: List[str] = []
            derived_protocols: List[str] = []
            for spec in runtime.get("listen_targets") or []:
                if not isinstance(spec, dict):
                    continue
                spec_name = str(spec.get("name") or "")
                spec_port = int(spec.get("port") or 0)
                spec_protocols = [
                    normalize_upstream_protocol(protocol)
                    for protocol in (spec.get("exposed_protocols") or [])
                    if normalize_upstream_protocol(protocol) in UPSTREAM_PROTOCOL_ORDER
                ]
                if spec_protocols and spec_port == runtime_port:
                    if spec_name and spec_name not in derived_server_names:
                        derived_server_names.append(spec_name)
                    for protocol in spec_protocols:
                        if protocol not in derived_protocols:
                            derived_protocols.append(protocol)
            if not active_server_names:
                active_server_names = derived_server_names
            if not active_protocols:
                active_protocols = derived_protocols
        if not active_protocols:
            endpoint_mode = str(runtime.get("endpoint_mode") or "")
            split_ports = runtime.get("split_api_ports") if isinstance(runtime.get("split_api_ports"), dict) else {}
            if endpoint_mode == "shared":
                active_protocols = list(UPSTREAM_PROTOCOL_ORDER)
                if not active_server_names:
                    active_server_names = ["shared"]
            elif endpoint_mode == "split":
                for protocol in UPSTREAM_PROTOCOL_ORDER:
                    if int(split_ports.get(protocol) or 0) != runtime_port:
                        continue
                    if protocol not in active_protocols:
                        active_protocols.append(protocol)
                    if protocol not in active_server_names:
                        active_server_names.append(protocol)
        service["active_server_names"] = active_server_names
        service["active_protocols"] = active_protocols
        service["all_protocols_started"] = len(active_protocols) == len(UPSTREAM_PROTOCOL_ORDER)
        service["partially_started"] = 0 < len(active_protocols) < len(UPSTREAM_PROTOCOL_ORDER)
        service["state"] = "external"
        service["owner"] = "external"
        service["dashboard_running"] = bool(service.get("dashboard_running", True))
        external_payload["runtime"] = runtime
        external_payload["service"] = service
        self.external_runtime = runtime
        self.external_service_snapshot = service
        self.external_status_payload = external_payload
        self.external_origin = {"host": host, "port": int(port)}
        self.last_error = ""
        return {
            "ok": True,
            "attached_to_external": True,
            "message": "attached_to_running_instance",
            **copy.deepcopy(runtime),
        }

    def _fetch_external_attachment_payload(
        self,
        host: str,
        port: int,
        *,
        timeout_sec: float = 2.5,
        interval_sec: float = 0.1,
    ) -> Optional[Dict[str, Any]]:
        deadline = time.monotonic() + timeout_sec
        while True:
            payload = fetch_hub_status(host, port)
            if payload is not None:
                return payload
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(interval_sec, remaining))

    def attach_external_instance(self, host: str, port: int) -> Dict[str, Any]:
        payload = self._fetch_external_attachment_payload(host, port)
        if payload is None:
            return {"ok": False, "message": "external_status_unavailable"}
        return self._set_external_attachment(payload, host, port)

    def _refresh_external_attachment(self) -> Optional[Dict[str, Any]]:
        if not self.external_origin:
            return None
        payload = fetch_hub_status(str(self.external_origin.get("host") or ""), int(self.external_origin.get("port") or 0))
        if payload is None:
            self._clear_external_attachment()
            return None
        self._set_external_attachment(payload, str(self.external_origin.get("host") or ""), int(self.external_origin.get("port") or 0))
        return copy.deepcopy(self.external_service_snapshot)

    def _detach_servers(self, names: Iterable[str]) -> tuple[Dict[str, RouterHTTPServer], Dict[str, threading.Thread]]:
        names_set = set(names)
        servers = {name: self.servers.pop(name) for name in list(self.servers) if name in names_set}
        threads = {name: self.threads.pop(name) for name in list(self.threads) if name in names_set}
        return servers, threads

    def _shutdown_servers(self, servers: Dict[str, RouterHTTPServer], threads: Dict[str, threading.Thread]) -> None:
        for server in servers.values():
            server.shutdown()
        for server in servers.values():
            server.server_close()
        for thread in threads.values():
            thread.join(timeout=2)

    def _spawn_server_thread(self, name: str, server: RouterHTTPServer) -> threading.Thread:
        thread = threading.Thread(target=server.serve_forever, daemon=True, name=f"ai-proxy-hub-{name}")
        thread.start()
        return thread

    def _snapshot_payload(
        self,
        *,
        state: str,
        error: str,
        owner: str,
        active_server_names: List[str],
        active_protocols: List[str],
        dashboard_running: bool,
    ) -> Dict[str, Any]:
        return snapshot_payload(
            state=state,
            error=error,
            owner=owner,
            active_server_names=active_server_names,
            active_protocols=active_protocols,
            dashboard_running=dashboard_running,
        )

    def is_running(self) -> bool:
        specs = self._build_server_specs_map()
        return any(name in self.servers for name in self._api_spec_names(specs))

    def _ordered_protocols(self, protocols: Iterable[str]) -> tuple[str, ...]:
        return ordered_protocols(protocols)

    def _set_shared_protocols(self, protocols: Iterable[str]) -> tuple[str, ...]:
        ordered = self._ordered_protocols(protocols)
        self.shared_exposed_protocols = ordered
        shared_server = self.servers.get("shared")
        if shared_server is not None:
            shared_server.exposed_protocols = ordered
        return ordered

    def _reset_shared_protocols(self) -> tuple[str, ...]:
        return self._set_shared_protocols(UPSTREAM_PROTOCOL_ORDER)

    def _active_protocols_for_server_name(self, name: str, spec: Dict[str, Any]) -> tuple[str, ...]:
        server = self.servers.get(name)
        if server is not None:
            return self._ordered_protocols(getattr(server, "exposed_protocols", spec.get("exposed_protocols") or ()))
        return self._ordered_protocols(spec.get("exposed_protocols") or ())

    def _build_server_specs(self) -> List[Dict[str, Any]]:
        return build_server_specs(self.store.get_config(), self.shared_exposed_protocols)

    def _build_server_specs_map(self) -> Dict[str, Dict[str, Any]]:
        return build_server_specs_map(self.store.get_config(), self.shared_exposed_protocols)

    def _dashboard_spec_name(self, specs: Dict[str, Dict[str, Any]]) -> str:
        return dashboard_spec_name(specs)

    def _api_spec_names(self, specs: Dict[str, Dict[str, Any]]) -> List[str]:
        return api_spec_names(specs)

    def _reachable_spec_names(self, specs: Dict[str, Dict[str, Any]]) -> List[str]:
        reachable: List[str] = []
        for name, spec in specs.items():
            if self._is_endpoint_reachable(str(spec["host"]), int(spec["port"])):
                reachable.append(name)
        return reachable

    def _protocols_for_spec_names(self, spec_names: Iterable[str], specs: Dict[str, Dict[str, Any]]) -> List[str]:
        active: List[str] = []
        for name in spec_names:
            spec = specs.get(name) or {}
            for protocol in self._active_protocols_for_server_name(name, spec):
                normalized = normalize_upstream_protocol(protocol)
                if normalized in UPSTREAM_PROTOCOL_ORDER and normalized not in active:
                    active.append(normalized)
        return active

    def _create_server_from_spec(self, spec: Dict[str, Any]) -> RouterHTTPServer:
        return create_server(
            self.config_path,
            self.static_dir,
            spec["host"],
            spec["port"],
            store_override=self.store,
            quiet_logging=True,
            protocol_prefixes=spec["protocol_prefixes"],
            exposed_protocols=spec["exposed_protocols"],
            dashboard_enabled=bool(spec["dashboard_enabled"]),
            service_controller=self,
        )

    def _start_spec_names(self, spec_names: Iterable[str], specs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        return start_spec_names(self, spec_names, specs)

    def ensure_dashboard_running(self) -> Dict[str, Any]:
        specs = self._build_server_specs_map()
        dashboard_name = self._dashboard_spec_name(specs)
        if not dashboard_name:
            return {"ok": False, "message": "dashboard_not_configured"}
        if dashboard_name in self.servers:
            runtime = self.runtime_info()
            return {"ok": True, "started_server_names": [], **runtime}

        # 检查是否有外部 AI Proxy Hub 实例正在运行
        dashboard_spec = specs.get(dashboard_name)
        if dashboard_spec:
            host = dashboard_spec["host"]
            port = dashboard_spec["port"]
            if self._is_ai_proxy_hub_running(host, port):
                attach_result = self.attach_external_instance(str(host), int(port))
                if attach_result.get("ok"):
                    return {
                        **attach_result,
                        "started_server_names": [],
                    }

        result = self._start_spec_names([dashboard_name], specs)
        if result.get("ok"):
            runtime = self.runtime_info()
            result.update(runtime)
        return result

    def status_snapshot(self) -> Dict[str, Any]:
        specs = self._build_server_specs_map()
        reachable_names = self._reachable_spec_names(specs)
        running_names = [name for name in specs if name in self.servers]
        dashboard_name = self._dashboard_spec_name(specs)
        api_spec_names = self._api_spec_names(specs)
        running_api_names = [name for name in api_spec_names if name in self.servers]
        reachable_api_names = [name for name in api_spec_names if name in reachable_names]
        active_protocols = self._protocols_for_spec_names(running_api_names, specs)
        dashboard_running = bool(dashboard_name and dashboard_name in running_names)
        if running_api_names:
            self._clear_external_attachment()
            unreachable_local = [name for name in running_api_names if name not in reachable_names]
            if unreachable_local:
                error = f"health probe failed: {', '.join(unreachable_local)}"
                self.last_error = error
                return self._snapshot_payload(
                    state="error",
                    error=error,
                    owner="local",
                    active_server_names=running_api_names,
                    active_protocols=active_protocols,
                    dashboard_running=dashboard_running,
                )
            state = "running" if len(active_protocols) == len(UPSTREAM_PROTOCOL_ORDER) else "partial" if active_protocols else "stopped"
            return self._snapshot_payload(
                state=state,
                error="",
                owner="local",
                active_server_names=running_api_names,
                active_protocols=active_protocols,
                dashboard_running=dashboard_running,
            )
        external_snapshot = self._refresh_external_attachment()
        if external_snapshot is not None:
            return external_snapshot
        if reachable_api_names:
            reachable_protocols = self._protocols_for_spec_names(reachable_api_names, specs)
            return self._snapshot_payload(
                state="external",
                error="",
                owner="external",
                active_server_names=reachable_api_names,
                active_protocols=reachable_protocols,
                dashboard_running=dashboard_running or bool(dashboard_name and dashboard_name in reachable_names),
            )
        return self._snapshot_payload(
            state="error" if self.last_error else "stopped",
            error=self.last_error,
            owner="local",
            active_server_names=[],
            active_protocols=[],
            dashboard_running=dashboard_running or bool(dashboard_name and dashboard_name in reachable_names),
        )

    def _is_endpoint_reachable(self, host: str, port: int) -> bool:
        return endpoint_reachable(host, port)

    def _is_ai_proxy_hub_running(self, host: str, port: int) -> bool:
        return is_ai_proxy_hub_running(host, port)

    def status_state(self) -> str:
        return str(self.status_snapshot().get("state") or "stopped")

    def runtime_info(self) -> Dict[str, Any]:
        if not self.servers and self.external_runtime is not None:
            return copy.deepcopy(self.external_runtime)
        return runtime_info_payload(self.store.get_config(), self.shared_exposed_protocols, self.servers)

    def attached_status_payload(self) -> Optional[Dict[str, Any]]:
        if not self.servers and self.external_status_payload is not None:
            return copy.deepcopy(self.external_status_payload)
        return None

    def _config_apply_plan(self, previous_config: Dict[str, Any]) -> Dict[str, Any]:
        old_specs = build_server_specs_map(previous_config, self.shared_exposed_protocols)
        running_names = [name for name in self.servers if name in old_specs]
        old_dashboard_name = self._dashboard_spec_name(old_specs)
        had_dashboard = bool(old_dashboard_name and old_dashboard_name in running_names)
        old_api_names = [name for name in running_names if name in self._api_spec_names(old_specs)]
        active_protocols = self._protocols_for_spec_names(old_api_names, old_specs)

        target_names_set = set()
        new_specs = self._build_server_specs_map()
        dashboard_name = self._dashboard_spec_name(new_specs)
        if had_dashboard and dashboard_name:
            target_names_set.add(dashboard_name)
        if active_protocols:
            if "shared" in new_specs:
                target_names_set.add("shared")
            else:
                for protocol in active_protocols:
                    if protocol in new_specs:
                        target_names_set.add(protocol)

        desired_shared_protocols: tuple[str, ...] | None = None
        if "shared" in target_names_set:
            desired_shared_protocols = tuple(active_protocols) if active_protocols else ()

        target_names = [name for name in new_specs if name in target_names_set]
        return {
            "target_names": target_names,
            "active_protocols": active_protocols,
            "desired_shared_protocols": desired_shared_protocols,
        }

    def preview_runtime_apply(self, previous_config: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._config_apply_plan(previous_config)
        target_names = list(plan["target_names"])
        if not target_names:
            return {"ok": True, "apply_required": False, **plan}

        current_ports = {int(server.server_address[1]) for server in self.servers.values()}
        desired_shared_protocols = plan.get("desired_shared_protocols")
        specs = build_server_specs_map(
            self.store.get_config(),
            desired_shared_protocols if desired_shared_protocols is not None else self.shared_exposed_protocols,
        )
        for name in target_names:
            spec = specs.get(name)
            if not spec:
                continue
            port = int(spec["port"])
            if port in current_ports:
                continue
            port_owner = find_listening_process(port)
            if port_owner:
                return {
                    "ok": False,
                    "apply_required": True,
                    "error_code": "port_in_use",
                    "message": f"port {port} already in use",
                    "port": port,
                    "host": str(spec["host"]),
                    "port_owner": port_owner,
                    **plan,
                }
        return {"ok": True, "apply_required": True, **plan}

    def apply_runtime_changes(self, previous_config: Dict[str, Any]) -> Dict[str, Any]:
        preview = self.preview_runtime_apply(previous_config)
        if not preview.get("ok") or not preview.get("apply_required"):
            return preview
        with self.runtime_apply_lock:
            result = self._apply_runtime_plan(preview)
        return {
            **preview,
            **result,
            "apply_required": True,
        }

    def _apply_runtime_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        target_names = list(plan.get("target_names") or [])
        if not target_names:
            return {"ok": True, "started_server_names": [], "stopped_server_names": []}

        desired_shared_protocols = plan.get("desired_shared_protocols")
        if desired_shared_protocols is not None:
            self._set_shared_protocols(desired_shared_protocols)
        specs = self._build_server_specs_map()
        target_set = set(target_names)
        names_to_stop: List[str] = []

        for name, server in list(self.servers.items()):
            spec = specs.get(name)
            if name not in target_set or spec is None:
                names_to_stop.append(name)
                continue
            server_host, server_port = server.server_address[0], int(server.server_address[1])
            if str(server_host) != str(spec["host"]) or server_port != int(spec["port"]):
                names_to_stop.append(name)
                continue
            server.protocol_prefixes = dict(spec["protocol_prefixes"])
            server.exposed_protocols = tuple(spec["exposed_protocols"])
            server.dashboard_enabled = bool(spec["dashboard_enabled"])

        stopped_server_names = list(names_to_stop)
        if names_to_stop:
            servers, threads = self._detach_servers(names_to_stop)
            self._shutdown_servers(servers, threads)

        missing_names = [name for name in target_names if name in specs and name not in self.servers]
        if missing_names:
            start_result = self._start_spec_names(missing_names, specs)
            if not start_result.get("ok"):
                return start_result

        self.last_error = ""
        return {
            "ok": True,
            "started_server_names": missing_names,
            "stopped_server_names": stopped_server_names,
            "target_names": target_names,
        }

    def schedule_runtime_apply(self, previous_config: Dict[str, Any], *, delay_sec: float = 0.25) -> Dict[str, Any]:
        preview = self.preview_runtime_apply(previous_config)
        if not preview.get("ok") or not preview.get("apply_required"):
            return preview

        def worker() -> None:
            time.sleep(delay_sec)
            with self.runtime_apply_lock:
                self._apply_runtime_plan(preview)

        thread = threading.Thread(target=worker, daemon=True, name="ai-proxy-hub-runtime-apply")
        thread.start()
        return preview

    def _runtime_base_urls(self, runtime: Dict[str, Any]) -> Dict[str, str]:
        return runtime_base_urls(runtime)

    def _set_client_usage_mode(self, use_local_hub: bool, runtime: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        if use_local_hub:
            runtime = runtime or self.runtime_info()
            results = switch_all_clients_to_local_hub(
                self._runtime_base_urls(runtime),
                self.store.get_local_api_key(),
            )
        else:
            results = restore_all_clients_from_backup()
        return self._store_client_results(results, use_local_hub=use_local_hub)

    def _ensure_api_running(self) -> Dict[str, Any]:
        return ensure_api_running(self)

    def start(self) -> Dict[str, Any]:
        return self.start_proxy_mode()

    def start_proxy_mode(self) -> Dict[str, Any]:
        return start_proxy_mode(self)

    def start_forwarding_mode(self) -> Dict[str, Any]:
        return start_forwarding_mode(self)

    def start_protocol(self, protocol: str) -> Dict[str, Any]:
        return start_protocol_op(self, protocol)

    def terminate_port_owner(self, port: int) -> Dict[str, Any]:
        return terminate_port_owner_for_controller(self, port)

    def _restore_client_for_protocol(self, protocol: str) -> Dict[str, Any]:
        return restore_client_for_protocol(self, protocol)

    def stop(self) -> bool:
        return stop_all(self)

    def shutdown(self) -> None:
        shutdown_all(self)

    def stop_protocol(self, protocol: str) -> Dict[str, Any]:
        return stop_protocol_op(self, protocol)

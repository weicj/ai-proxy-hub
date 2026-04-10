from __future__ import annotations

from typing import Any, Dict, Iterable

from .constants import UPSTREAM_PROTOCOL_ORDER
from .network import find_listening_process, is_address_in_use_error, protocol_client_id, terminate_listening_processes, terminate_process
from .protocols import normalize_upstream_protocol


def start_spec_names(controller: Any, spec_names: Iterable[str], specs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    names = [name for name in spec_names if name in specs and name not in controller.servers]
    if not names:
        return {"ok": True, "started_server_names": []}
    created_servers: Dict[str, Any] = {}
    try:
        for name in names:
            created_servers[name] = controller._create_server_from_spec(specs[name])
    except OSError as exc:
        for server in created_servers.values():
            try:
                server.server_close()
            except OSError:
                pass
        controller.last_error = str(exc)
        result: Dict[str, Any] = {
            "ok": False,
            "message": str(exc),
        }
        if is_address_in_use_error(exc):
            result["error_code"] = "port_in_use"
            failed_spec = next((specs[name] for name in names if name not in created_servers), None)
            if failed_spec:
                result["port"] = int(failed_spec["port"])
                result["host"] = str(failed_spec["host"])
                result["port_owner"] = find_listening_process(int(failed_spec["port"]))
                attach_external = getattr(controller, "attach_external_instance", None)
                if callable(attach_external):
                    attach_result = attach_external(str(failed_spec["host"]), int(failed_spec["port"]))
                    if attach_result.get("ok"):
                        attach_result.setdefault("started_server_names", [])
                        return attach_result
        return result
    controller.servers.update(created_servers)
    for name, server in created_servers.items():
        thread = controller._spawn_server_thread(name, server)
        controller.threads[name] = thread
    controller.last_error = ""
    return {"ok": True, "started_server_names": names}


def ensure_api_running(controller: Any) -> Dict[str, Any]:
    specs = controller._build_server_specs_map()
    if not specs:
        return {"ok": False, "message": "no_specs"}
    dashboard_result = controller.ensure_dashboard_running()
    if not dashboard_result.get("ok"):
        return dashboard_result
    api_spec_names = controller._api_spec_names(specs)
    missing_names = [name for name in api_spec_names if name not in controller.servers]
    if missing_names:
        start_result = controller._start_spec_names(missing_names, specs)
        if not start_result.get("ok"):
            return start_result
        if start_result.get("attached_to_external"):
            runtime = controller.runtime_info()
            return {
                **start_result,
                **runtime,
            }
    runtime = controller.runtime_info()
    return {"ok": True, "started_server_names": missing_names, **runtime}


def start_proxy_mode(controller: Any) -> Dict[str, Any]:
    controller._reset_shared_protocols()
    start_result = controller._ensure_api_running()
    if not start_result.get("ok"):
        return start_result
    switch_results = controller._set_client_usage_mode(True, start_result)
    return {
        "ok": True,
        "switch_results": switch_results,
        "switch_result": switch_results.get("codex", {}),
        **start_result,
    }


def start_forwarding_mode(controller: Any) -> Dict[str, Any]:
    controller._reset_shared_protocols()
    start_result = controller._ensure_api_running()
    if not start_result.get("ok"):
        return start_result
    restore_results = controller._set_client_usage_mode(False)
    return {
        "ok": True,
        "restore_results": restore_results,
        **start_result,
    }


def start_protocol(controller: Any, protocol: str) -> Dict[str, Any]:
    protocol = normalize_upstream_protocol(protocol)
    specs = controller._build_server_specs_map()
    if "shared" in specs:
        if protocol not in UPSTREAM_PROTOCOL_ORDER:
            return {"ok": False, "message": "invalid_protocol"}
        dashboard_result = controller.ensure_dashboard_running()
        if not dashboard_result.get("ok"):
            return dashboard_result
        current = controller._ordered_protocols(getattr(controller.servers.get("shared"), "exposed_protocols", controller.shared_exposed_protocols))
        if protocol in current:
            return {"ok": False, "message": "already_running"}
        ordered = controller._set_shared_protocols((*current, protocol))
        if "shared" not in controller.servers:
            start_result = controller._start_spec_names(["shared"], controller._build_server_specs_map())
            if not start_result.get("ok"):
                return start_result
        controller.last_error = ""
        return {"ok": True, "protocol": protocol, "active_protocols": list(ordered)}
    if protocol not in UPSTREAM_PROTOCOL_ORDER or protocol not in specs:
        return {"ok": False, "message": "invalid_protocol"}
    dashboard_result = controller.ensure_dashboard_running()
    if not dashboard_result.get("ok"):
        return dashboard_result
    names_to_start = [protocol] if protocol not in controller.servers else []
    if not names_to_start:
        return {"ok": False, "message": "already_running"}
    start_result = controller._start_spec_names(names_to_start, specs)
    if not start_result.get("ok"):
        return start_result
    if start_result.get("attached_to_external"):
        return {
            **start_result,
            "protocol": protocol,
        }
    return {"ok": True, "started_server_names": names_to_start, "protocol": protocol}


def terminate_port_owner_for_controller(_: Any, port: int) -> Dict[str, Any]:
    process_info = find_listening_process(port)
    if process_info and process_info.get("pid"):
        result = terminate_process(int(process_info["pid"]))
        result["process_info"] = process_info
        if result.get("ok"):
            return result
    fallback = terminate_listening_processes(port)
    if process_info:
        fallback["process_info"] = process_info
    return fallback


def restore_client_for_protocol(controller: Any, protocol: str) -> Dict[str, Any]:
    client_id = protocol_client_id(protocol)
    restore_result = controller.restore_client_from_backup(client_id)
    controller.last_restore_results[client_id] = restore_result
    if not restore_result.get("ok"):
        controller.last_warning = controller._warning_message_for_results({client_id: restore_result})
        return {
            "ok": False,
            "message": str(restore_result.get("message") or "restore_failed"),
            "client": client_id,
            "restore_result": restore_result,
        }
    return {
        "ok": True,
        "client": client_id,
        "restore_result": restore_result,
    }


def stop_all(controller: Any) -> bool:
    specs = controller._build_server_specs_map()
    api_spec_names = set(controller._api_spec_names(specs))
    shared_server = controller.servers.get("shared")
    preserve_shared_dashboard = controller._dashboard_spec_name(specs) == "shared" and shared_server is not None
    if preserve_shared_dashboard:
        shared_protocols = tuple(
            controller._ordered_protocols(getattr(shared_server, "exposed_protocols", controller.shared_exposed_protocols))
        )
        servers_to_stop, threads_to_stop = controller._detach_servers(api_spec_names - {"shared"})
        if servers_to_stop:
            controller._shutdown_servers(servers_to_stop, threads_to_stop)
        changed = bool(shared_protocols) or bool(servers_to_stop)
        if not changed:
            return False
        controller._set_shared_protocols(())
        controller.last_error = ""
        controller._store_client_results(controller.restore_all_clients_from_backup(), use_local_hub=False)
        return True
    servers_to_stop, threads_to_stop = controller._detach_servers(api_spec_names)
    if not servers_to_stop:
        return False
    controller._shutdown_servers(servers_to_stop, threads_to_stop)
    controller._reset_shared_protocols()
    controller.last_error = ""
    controller._store_client_results(controller.restore_all_clients_from_backup(), use_local_hub=False)
    return True


def shutdown_all(controller: Any) -> None:
    had_api_servers = controller.is_running()
    servers, threads = controller._detach_servers(tuple(controller.servers))
    for server in servers.values():
        try:
            server.shutdown()
        except Exception:
            pass
    for server in servers.values():
        try:
            server.server_close()
        except Exception:
            pass
    for thread in threads.values():
        try:
            thread.join(timeout=2)
        except Exception:
            pass
    controller._reset_shared_protocols()
    if had_api_servers:
        controller._store_client_results(controller.restore_all_clients_from_backup(), use_local_hub=False)


def stop_protocol(controller: Any, protocol: str) -> Dict[str, Any]:
    protocol = normalize_upstream_protocol(protocol)
    specs = controller._build_server_specs_map()
    if "shared" in specs:
        shared_server = controller.servers.get("shared")
        if shared_server is None:
            return {"ok": False, "message": "not_running"}
        current = controller._ordered_protocols(getattr(shared_server, "exposed_protocols", controller.shared_exposed_protocols))
        if protocol not in current:
            return {"ok": False, "message": "not_running"}
        restore_state = controller._restore_client_for_protocol(protocol)
        if not restore_state.get("ok"):
            return restore_state
        remaining = tuple(item for item in current if item != protocol)
        if remaining:
            ordered = controller._set_shared_protocols(remaining)
            controller.last_error = ""
            return {
                "ok": True,
                "protocol": protocol,
                "active_protocols": list(ordered),
                "restore_result": restore_state.get("restore_result"),
            }
        controller._set_shared_protocols(())
        controller.last_error = ""
        return {
            "ok": True,
            "protocol": protocol,
            "active_protocols": [],
            "restore_result": restore_state.get("restore_result"),
        }
    server = controller.servers.pop(protocol, None)
    thread = controller.threads.pop(protocol, None)
    if server is None:
        return {"ok": False, "message": "not_running"}
    restore_state = controller._restore_client_for_protocol(protocol)
    if not restore_state.get("ok"):
        controller.servers[protocol] = server
        if thread is not None:
            controller.threads[protocol] = thread
        return restore_state
    server.shutdown()
    server.server_close()
    if thread is not None:
        thread.join(timeout=2)
    controller.last_error = ""
    return {
        "ok": True,
        "stopped_server_names": [protocol],
        "protocol": protocol,
        "restore_result": restore_state.get("restore_result"),
    }

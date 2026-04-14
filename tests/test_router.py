import importlib.util
import io
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from datetime import datetime
from http.client import HTTPConnection
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

BUILD_RELEASE_SPEC = importlib.util.spec_from_file_location(
    "build_release_module", PROJECT_ROOT / "scripts" / "build_release.py"
)
assert BUILD_RELEASE_SPEC and BUILD_RELEASE_SPEC.loader
build_release_module = importlib.util.module_from_spec(BUILD_RELEASE_SPEC)
BUILD_RELEASE_SPEC.loader.exec_module(build_release_module)

SYNC_RELEASE_SPEC = importlib.util.spec_from_file_location(
    "sync_release_snapshot_module", PROJECT_ROOT / "scripts" / "sync_release_snapshot.py"
)
assert SYNC_RELEASE_SPEC and SYNC_RELEASE_SPEC.loader
sync_release_snapshot_module = importlib.util.module_from_spec(SYNC_RELEASE_SPEC)
SYNC_RELEASE_SPEC.loader.exec_module(sync_release_snapshot_module)

SYNC_HOMEBREW_TAP_SPEC = importlib.util.spec_from_file_location(
    "sync_homebrew_tap_module", PROJECT_ROOT / "scripts" / "sync_homebrew_tap.py"
)
assert SYNC_HOMEBREW_TAP_SPEC and SYNC_HOMEBREW_TAP_SPEC.loader
sync_homebrew_tap_module = importlib.util.module_from_spec(SYNC_HOMEBREW_TAP_SPEC)
SYNC_HOMEBREW_TAP_SPEC.loader.exec_module(sync_homebrew_tap_module)

import router_server as router_server_module  # noqa: E402
from router_server import (  # noqa: E402
    APP_NAME,
    APP_SLUG,
    ConfigStore,
    InteractiveConsoleApp,
    RouterRequestHandler,
    ServiceController,
    app_config_dir,
    app_config_dir_candidates,
    collect_client_binding_statuses,
    first_env_value,
    legacy_config_locations,
    local_key_allows_protocol,
    normalize_local_api_keys,
    preferred_app_config_dir,
    create_server,
    extract_model_ids,
    get_claude_cli_binding_status,
    get_codex_cli_binding_status,
    get_gemini_cli_binding_status,
    normalize_config,
    resolve_usage_window,
    resolve_static_dir,
    restore_claude_cli_from_backup,
    restore_client_from_backup,
    restore_codex_cli_from_backup,
    restore_gemini_cli_from_backup,
    switch_claude_cli_to_local_hub,
    switch_client_to_local_hub,
    switch_codex_cli_to_local_hub,
    switch_gemini_cli_to_local_hub,
    write_json,
)
from ai_proxy_hub import http_server as http_server_module  # noqa: E402
from ai_proxy_hub import legacy_impl as legacy_impl_module  # noqa: E402
from ai_proxy_hub.cli_local_keys import build_local_key_entry, parse_allowed_protocols_input  # noqa: E402
from ai_proxy_hub.cli_usage import prepare_usage_chart_data  # noqa: E402
from ai_proxy_hub.entrypoints import foreground_runtime_lines as entrypoint_foreground_runtime_lines  # noqa: E402
from ai_proxy_hub.entrypoints import parse_args as entrypoint_parse_args  # noqa: E402
from ai_proxy_hub.entrypoints import print_runtime_paths as entrypoint_print_runtime_paths  # noqa: E402
from ai_proxy_hub.entrypoints import write_runtime_line as entrypoint_write_runtime_line  # noqa: E402


def make_upstream_server(routes, call_log):
    class UpstreamHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.handle_any()

        def do_POST(self):
            self.handle_any()

        def handle_any(self):
            path = self.path.split("?", 1)[0]
            content_length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(content_length) if content_length else b""
            call_log.append(
                {
                    "method": self.command,
                    "path": path,
                    "body": body.decode("utf-8", errors="ignore"),
                    "headers": {key.lower(): value for key, value in self.headers.items()},
                }
            )
            route = routes[(self.command, path)]
            payload = route["body"]
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(route["status"])
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    wait_for_tcp_server("127.0.0.1", server.server_address[1])
    return server, thread


def make_request(url, *, method="GET", data=None, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def encode_request_body(payload):
    return json.dumps(payload).encode("utf-8")


def local_datetime(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second)


def reserve_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return handle.getsockname()[1]


def wait_for_tcp_server(host: str, port: int, *, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for TCP server {host}:{port}")


class RouterServerTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.upstream_one_log = []
        self.upstream_two_log = []
        self.upstream_one_routes = {
            ("POST", "/v1/chat/completions"): {
                "status": 429,
                "body": {"error": {"message": "insufficient_quota", "code": "insufficient_quota"}},
            },
            ("GET", "/v1/models"): {"status": 200, "body": {"object": "list", "data": [{"id": "gpt-a"}]}},
        }
        self.upstream_two_routes = {
            ("POST", "/v1/chat/completions"): {
                "status": 200,
                "body": {
                    "id": "chatcmpl-ok",
                    "object": "chat.completion",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第二个上游"}}],
                },
            },
            ("GET", "/v1/models"): {"status": 200, "body": {"object": "list", "data": [{"id": "gpt-b"}]}},
        }

        self.upstream_one, self.upstream_one_thread = make_upstream_server(
            self.upstream_one_routes,
            self.upstream_one_log,
        )
        self.upstream_two, self.upstream_two_thread = make_upstream_server(
            self.upstream_two_routes,
            self.upstream_two_log,
        )

        config_path = Path(self.tempdir.name) / "api-config.json"
        self.config_path = config_path
        config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 0,
                "local_api_key": "sk-local-test",
                "request_timeout_sec": 5,
                "cooldown_seconds": 30,
                "upstreams": [
                    {
                        "name": "上游一",
                        "base_url": f"http://127.0.0.1:{self.upstream_one.server_address[1]}/v1",
                        "api_key": "sk-upstream-one",
                    },
                    {
                        "name": "上游二",
                        "base_url": f"http://127.0.0.1:{self.upstream_two.server_address[1]}/v1",
                        "api_key": "sk-upstream-two",
                    },
                ],
            }
        )
        write_json(config_path, config)
        self.proxy = create_server(config_path, PROJECT_ROOT / "web", "127.0.0.1", 0)
        self.proxy_thread = threading.Thread(target=self.proxy.serve_forever, daemon=True)
        self.proxy_thread.start()
        wait_for_tcp_server("127.0.0.1", self.proxy.server_address[1])
        self.proxy_base = f"http://127.0.0.1:{self.proxy.server_address[1]}"

    def tearDown(self):
        for server in (self.proxy, self.upstream_one, self.upstream_two):
            server.shutdown()
            server.server_close()
        for thread in (self.proxy_thread, self.upstream_one_thread, self.upstream_two_thread):
            thread.join(timeout=2)
        self.tempdir.cleanup()

    def managed_dashboard_base(self, controller):
        config_path = Path(self.tempdir.name) / "managed-api-config.json"
        config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 8787,
                "web_ui_port": 0,
                "endpoint_mode": "shared",
                "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
            }
        )
        write_json(config_path, config)
        server = create_server(
            config_path,
            PROJECT_ROOT / "web",
            "127.0.0.1",
            0,
            service_controller=controller,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_service_controller_attaches_to_running_external_instance_on_port_conflict(self):
        port = reserve_tcp_port()
        external_config_path = Path(self.tempdir.name) / "external-instance.json"
        external_config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": port,
                "web_ui_port": port,
                "endpoint_mode": "shared",
                "shared_api_prefixes": {
                    "openai": "/external-openai",
                    "anthropic": "/external-claude",
                    "gemini": "/external-gemini",
                    "local_llm": "/external-local",
                },
                "upstreams": [
                    {
                        "name": "External Upstream",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-demo",
                    }
                ],
            }
        )
        write_json(external_config_path, external_config)
        external_server = create_server(external_config_path, PROJECT_ROOT / "web", "127.0.0.1", port)
        external_thread = threading.Thread(target=external_server.serve_forever, daemon=True)
        external_thread.start()
        wait_for_tcp_server("127.0.0.1", port)
        self.addCleanup(external_server.shutdown)
        self.addCleanup(external_server.server_close)
        self.addCleanup(external_thread.join, 1)

        local_config_path = Path(self.tempdir.name) / "local-instance.json"
        local_config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": port,
                "web_ui_port": port,
                "endpoint_mode": "shared",
                "shared_api_prefixes": {
                    "openai": "/local-openai",
                    "anthropic": "/local-claude",
                    "gemini": "/local-gemini",
                    "local_llm": "/local-local",
                },
                "upstreams": [
                    {
                        "name": "Local Upstream",
                        "base_url": "https://example.org/v1",
                        "api_key": "sk-local",
                    }
                ],
            }
        )
        write_json(local_config_path, local_config)
        controller = ServiceController(local_config_path, PROJECT_ROOT / "web", ConfigStore(local_config_path))

        with mock.patch(
            "ai_proxy_hub.service_controller.switch_all_clients_to_local_hub",
            return_value={"codex": {"ok": True}, "claude": {"ok": True}, "gemini": {"ok": True}},
        ):
            result = controller.start_proxy_mode()

        self.assertTrue(result["ok"])
        self.assertTrue(result.get("attached_to_external"))
        runtime = controller.runtime_info()
        self.assertEqual(runtime["port"], port)
        self.assertTrue(str(runtime["openai_base_url"]).endswith("/external-openai"))
        snapshot = controller.status_snapshot()
        self.assertEqual(snapshot["state"], "external")
        self.assertIn("openai", snapshot["active_protocols"])

    def test_failover_switches_to_second_upstream_after_429(self):
        status, payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "你好"}],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["choices"][0]["message"]["content"], "来自第二个上游")
        self.assertEqual(len(self.upstream_one_log), 1)
        self.assertEqual(len(self.upstream_two_log), 1)

    def test_manual_lock_uses_selected_upstream_without_failover(self):
        config = self.proxy.store.get_config()
        config["auto_routing_enabled"] = False
        config["manual_active_upstream_id"] = config["upstreams"][0]["id"]
        self.proxy.store.save_config(config)

        request = urllib.request.Request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            data=encode_request_body({"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "你好"}]}),
            headers={
                "Authorization": "Bearer sk-local-test",
                "Content-Type": "application/json",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        body = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 429)
        self.assertEqual(body["error"]["code"], "insufficient_quota")
        self.assertEqual(len(self.upstream_one_log), 1)
        self.assertEqual(len(self.upstream_two_log), 0)

    def test_payload_too_large_returns_proxy_diagnostic(self):
        self.upstream_one_routes[("POST", "/v1/responses")] = {
            "status": 413,
            "body": {"error": {"message": "payload too large", "code": "payload_too_large"}},
        }
        config = self.proxy.store.get_config()
        config["auto_routing_enabled"] = False
        config["manual_active_upstream_id"] = config["upstreams"][0]["id"]
        self.proxy.store.save_config(config)

        payload = {"model": "gpt-5.4", "input": "hello"}
        raw_body = encode_request_body(payload)
        request = urllib.request.Request(
            f"{self.proxy_base}/v1/responses",
            method="POST",
            data=raw_body,
            headers={
                "Authorization": "Bearer sk-local-test",
                "Content-Type": "application/json",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        body = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 413)
        self.assertEqual(body["error"]["code"], "upstream_payload_too_large")
        self.assertIn("request_bytes=", body["error"]["message"])
        self.assertIn(str(len(raw_body)), body["error"]["message"])
        self.assertEqual(body["error"]["details"][0]["path"], "/v1/responses")
        self.assertEqual(body["error"]["details"][0]["request_bytes"], len(raw_body))
        self.assertEqual(len(self.upstream_one_log), 1)

    def test_models_endpoint_aggregates_multiple_upstreams(self):
        status, payload = make_request(f"{self.proxy_base}/v1/models", token="sk-local-test")
        self.assertEqual(status, 200)
        self.assertEqual({item["id"] for item in payload["data"]}, {"gpt-a", "gpt-b"})

    def test_openai_alias_path_routes_through_openai_prefix(self):
        status, payload = make_request(
            f"{self.proxy_base}/openai/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["choices"][0]["message"]["content"], "来自第二个上游")

    def test_anthropic_proxy_routes_with_protocol_specific_headers(self):
        self.upstream_one_routes[("POST", "/v1/messages")] = {
            "status": 429,
            "body": {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
        }
        self.upstream_two_routes[("POST", "/v1/messages")] = {
            "status": 200,
            "body": {
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "来自 Claude 上游"}],
            },
        }
        config = self.proxy.store.get_config()
        for index, upstream in enumerate(config["upstreams"]):
            upstream["protocol"] = "anthropic"
            upstream["base_url"] = f"http://127.0.0.1:{self.upstream_one.server_address[1]}" if index == 0 else f"http://127.0.0.1:{self.upstream_two.server_address[1]}"
        self.proxy.store.save_config(config)

        request = urllib.request.Request(
            f"{self.proxy_base}/anthropic/v1/messages",
            method="POST",
            data=encode_request_body({"model": "claude-sonnet", "max_tokens": 16, "messages": [{"role": "user", "content": "hello"}]}),
            headers={
                "x-api-key": "sk-local-test",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["content"][0]["text"], "来自 Claude 上游")
        self.assertEqual(self.upstream_two_log[0]["headers"]["x-api-key"], "sk-upstream-two")
        self.assertEqual(self.upstream_two_log[0]["path"], "/v1/messages")

    def test_gemini_proxy_routes_with_protocol_specific_headers(self):
        self.upstream_one_routes[("POST", "/v1beta/models/gemini-2.5-flash:generateContent")] = {
            "status": 200,
            "body": {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "来自 Gemini 上游"}],
                        }
                    }
                ]
            },
        }
        config = self.proxy.store.get_config()
        config["upstreams"][0]["protocol"] = "gemini"
        config["upstreams"][0]["base_url"] = f"http://127.0.0.1:{self.upstream_one.server_address[1]}"
        config["upstreams"][1]["enabled"] = False
        self.proxy.store.save_config(config)

        request = urllib.request.Request(
            f"{self.proxy_base}/gemini/v1beta/models/gemini-2.5-flash:generateContent",
            method="POST",
            data=encode_request_body({"contents": [{"role": "user", "parts": [{"text": "hello"}]}]}),
            headers={
                "x-goog-api-key": "sk-local-test",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["candidates"][0]["content"]["parts"][0]["text"], "来自 Gemini 上游")
        self.assertEqual(self.upstream_one_log[-1]["headers"]["x-goog-api-key"], "sk-upstream-one")
        self.assertEqual(self.upstream_one_log[-1]["path"], "/v1beta/models/gemini-2.5-flash:generateContent")

    def test_usage_series_counts_requests_by_upstream(self):
        self.upstream_one_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-one",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第一个上游"}}],
            },
        }
        self.upstream_two_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-two",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第二个上游"}}],
            },
        }
        config = self.proxy.store.get_config()
        config["routing_mode"] = "round_robin"
        self.proxy.store.save_config(config)
        primary_local_key_id = self.proxy.store.get_config()["local_api_keys"][0]["id"]

        make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "1"}]},
        )
        make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "2"}]},
        )

        usage = self.proxy.store.get_usage_series("hour")
        self.assertEqual(usage["metric"], "requests")
        upstream_totals = {}
        local_key_totals = {}
        pair_totals = {}
        for bucket in usage["buckets"]:
            for upstream_id, count in bucket["by_upstream"].items():
                upstream_totals[upstream_id] = upstream_totals.get(upstream_id, 0) + count
            for local_key_id, count in bucket["by_local_key"].items():
                local_key_totals[local_key_id] = local_key_totals.get(local_key_id, 0) + count
            for pair in bucket["pairs"]:
                pair_key = (pair["local_key_id"], pair["upstream_id"])
                pair_totals[pair_key] = pair_totals.get(pair_key, 0) + int(pair["count"])
        self.assertEqual(sum(bucket["total"] for bucket in usage["buckets"]), 2)
        self.assertEqual(sorted(upstream_totals.values()), [1, 1])
        self.assertEqual(local_key_totals[primary_local_key_id], 2)
        self.assertEqual(sorted(pair_totals.values()), [1, 1])

    def test_usage_ranges_use_expected_bucket_precision(self):
        expectations = {
            "minute": {"bucket_seconds": 60, "bucket_count": 60},
            "hour": {"bucket_seconds": 3600, "bucket_count": 24},
            "day": {"bucket_seconds": 86400, "bucket_count": 30},
            "week": {"bucket_seconds": 604800, "bucket_count": 12},
        }
        for range_key, expected in expectations.items():
            window = resolve_usage_window(range_key, now_ts=1_744_000_000)
            usage = self.proxy.store.get_usage_series(range_key)
            self.assertEqual(window["bucket_seconds"], expected["bucket_seconds"])
            self.assertEqual(window["bucket_count"], expected["bucket_count"])
            self.assertEqual(usage["bucket_seconds"], expected["bucket_seconds"])
            self.assertEqual(usage["bucket_count"], expected["bucket_count"])
            self.assertEqual(len(usage["buckets"]), expected["bucket_count"])

    def test_usage_and_stats_persist_after_store_restart(self):
        status, _payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "persist"}]},
        )
        self.assertEqual(status, 200)

        restarted = create_server(self.config_path, PROJECT_ROOT / "web", "127.0.0.1", 0)
        try:
            usage = restarted.store.get_usage_series("hour")
            self.assertEqual(sum(bucket["total"] for bucket in usage["buckets"]), 2)
            primary_local_key_id = restarted.store.get_config()["local_api_keys"][0]["id"]
            local_key_totals = {}
            for bucket in usage["buckets"]:
                for local_key_id, count in bucket["by_local_key"].items():
                    local_key_totals[local_key_id] = local_key_totals.get(local_key_id, 0) + count
            self.assertEqual(local_key_totals[primary_local_key_id], 2)

            upstream_stats = restarted.store.get_status("127.0.0.1", 0, service_state="stopped")["upstreams"]
            self.assertEqual(sum(int(item["stats"]["request_count"]) for item in upstream_stats), 2)

            local_keys = restarted.store.get_status("127.0.0.1", 0, service_state="stopped")["local_api_keys"]
            self.assertEqual(local_keys[0]["stats"]["request_count"], 1)
            self.assertEqual(local_keys[0]["stats"]["success_count"], 1)
        finally:
            restarted.server_close()

    def test_usage_series_tracks_secondary_local_key_dimension(self):
        config = self.proxy.store.get_config()
        primary_local_key_id = config["local_api_keys"][0]["id"]
        config["local_api_keys"].append(
            {
                "id": "secondary-key",
                "name": "Secondary Key",
                "key": "sk-local-secondary",
                "enabled": True,
                "created_at": "2026-04-05T00:00:00+00:00",
            }
        )
        self.proxy.store.save_config(config)

        for token in ("sk-local-test", "sk-local-secondary"):
            status, _payload = make_request(
                f"{self.proxy_base}/v1/chat/completions",
                method="POST",
                token=token,
                data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": token}]},
            )
            self.assertEqual(status, 200)

        usage = self.proxy.store.get_usage_series("hour")
        self.assertIn({"id": "secondary-key", "name": "Secondary Key"}, usage["local_keys"])
        local_key_totals = {}
        pair_totals = {}
        for bucket in usage["buckets"]:
            for local_key_id, count in bucket["by_local_key"].items():
                local_key_totals[local_key_id] = local_key_totals.get(local_key_id, 0) + count
            for pair in bucket["pairs"]:
                pair_key = (pair["local_key_id"], pair["upstream_id"])
                pair_totals[pair_key] = pair_totals.get(pair_key, 0) + int(pair["count"])
        self.assertEqual(local_key_totals[primary_local_key_id], 2)
        self.assertEqual(local_key_totals["secondary-key"], 1)
        self.assertEqual(sum(pair_totals.values()), 3)

    def test_status_exposes_runtime_client_endpoints(self):
        status, payload = make_request(f"{self.proxy_base}/api/status")
        self.assertEqual(status, 200)
        self.assertIn("clients", payload)
        self.assertIn("claude", payload["clients"])
        self.assertIn("gemini", payload["clients"])
        self.assertTrue(payload["runtime"]["openai_base_url"].endswith("/openai"))
        self.assertTrue(payload["runtime"]["claude_base_url"].endswith("/claude"))
        self.assertTrue(payload["runtime"]["gemini_base_url"].endswith("/gemini"))

    def test_dashboard_serves_split_javascript_assets(self):
        with urllib.request.urlopen(f"{self.proxy_base}/app-01-i18n.js", timeout=5) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
        self.assertEqual(response.status, 200)
        self.assertIn("javascript", content_type)
        self.assertIn("const I18N", body)

    def test_secondary_local_api_key_is_accepted_and_tracked(self):
        config = self.proxy.store.get_config()
        config["local_api_keys"].append(
            {
                "id": "secondary-key",
                "name": "Secondary Key",
                "key": "sk-local-secondary",
                "enabled": True,
                "created_at": "2026-04-05T00:00:00+00:00",
            }
        )
        self.proxy.store.save_config(config)

        status, _payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-secondary",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hello"}]},
        )
        self.assertEqual(status, 200)

        status, payload = make_request(f"{self.proxy_base}/api/status")
        self.assertEqual(status, 200)
        local_key = next(item for item in payload["local_api_keys"] if item["id"] == "secondary-key")
        self.assertEqual(local_key["stats"]["request_count"], 1)
        self.assertEqual(local_key["stats"]["success_count"], 1)

    def test_local_api_key_can_be_limited_to_specific_protocols(self):
        self.upstream_one_routes[("POST", "/v1/messages")] = {
            "status": 200,
            "body": {
                "id": "msg_ok",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "anthropic only"}],
            },
        }
        config = self.proxy.store.get_config()
        config["local_api_keys"][0]["allowed_protocols"] = ["anthropic"]
        config["upstreams"][0]["protocol"] = "anthropic"
        config["upstreams"][0]["base_url"] = f"http://127.0.0.1:{self.upstream_one.server_address[1]}"
        config["upstreams"][1]["enabled"] = False
        self.proxy.store.save_config(config)

        openai_request = urllib.request.Request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            data=encode_request_body({"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "blocked"}]}),
            headers={
                "Authorization": "Bearer sk-local-test",
                "Content-Type": "application/json",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as blocked:
            urllib.request.urlopen(openai_request, timeout=5)
        self.assertEqual(blocked.exception.code, 401)

        request = urllib.request.Request(
            f"{self.proxy_base}/anthropic/v1/messages",
            method="POST",
            data=encode_request_body({"model": "claude-sonnet", "max_tokens": 16, "messages": [{"role": "user", "content": "allowed"}]}),
            headers={
                "x-api-key": "sk-local-test",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["content"][0]["text"], "anthropic only")

    def test_client_control_endpoint_switches_single_client(self):
        with mock.patch("router_server.switch_codex_cli_to_local_hub", return_value={"ok": True, "provider": "openai"}):
            with mock.patch(
                "router_server.collect_client_binding_statuses",
                return_value={
                    "codex": {"state": "switched", "base_url": "http://127.0.0.1:8787/openai"},
                    "claude": {"state": "not_switched"},
                    "gemini": {"state": "not_switched"},
                },
            ):
                status, payload = make_request(
                    f"{self.proxy_base}/api/client/control",
                    method="POST",
                    data={"client": "codex", "action": "switch"},
                )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["client"], "codex")
        self.assertEqual(payload["action"], "switch")
        self.assertEqual(payload["status"]["state"], "switched")

    def test_codex_binding_status_treats_legacy_local_endpoint_as_not_switched(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "config.toml"
            auth_path = tempdir_path / "auth.json"
            config_path.write_text(
                '\n'.join(
                    [
                        'model_provider = "my_codex"',
                        '',
                        '[model_providers.my_codex]',
                        'name = "my_codex"',
                        'base_url = "http://127.0.0.1:8820/v1"',
                        'wire_api = "responses"',
                        'requires_openai_auth = true',
                        '',
                    ]
                ),
                encoding="utf-8",
            )
            auth_path.write_text(
                json.dumps({"OPENAI_API_KEY": "sk-local-test", "auth_mode": "apikey"}, ensure_ascii=False),
                encoding="utf-8",
            )

            status = get_codex_cli_binding_status(
                "http://127.0.0.1:8820/openai",
                "sk-local-test",
                config_path=config_path,
                auth_path=auth_path,
                service_state="running",
            )

        self.assertEqual(status["state"], "not_switched")
        self.assertEqual(status["base_url"], "http://127.0.0.1:8820/v1")

    def test_service_control_endpoint_starts_forwarding_mode(self):
        controller = mock.Mock()
        controller.start_forwarding_mode.return_value = {"ok": True, "message": "started_forwarding"}
        controller.status_snapshot.return_value = {
            "state": "running",
            "error": "",
            "owner": "local",
            "active_server_names": ["shared"],
            "active_protocols": ["openai"],
            "all_protocols_started": False,
            "partially_started": True,
            "dashboard_running": True,
        }
        base = self.managed_dashboard_base(controller)

        status, payload = make_request(
            f"{base}/api/service/control",
            method="POST",
            data={"action": "start_forwarding"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        controller.start_forwarding_mode.assert_called_once_with()

    def test_service_control_endpoint_starts_proxy_mode(self):
        controller = mock.Mock()
        controller.start_proxy_mode.return_value = {"ok": True, "message": "started_proxy"}
        controller.status_snapshot.return_value = {
            "state": "running",
            "error": "",
            "owner": "local",
            "active_server_names": ["shared"],
            "active_protocols": ["openai", "anthropic", "gemini"],
            "all_protocols_started": True,
            "partially_started": False,
            "dashboard_running": True,
        }
        base = self.managed_dashboard_base(controller)

        status, payload = make_request(
            f"{base}/api/service/control",
            method="POST",
            data={"action": "start_proxy"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        controller.start_proxy_mode.assert_called_once_with()

    def test_config_export_and_import_endpoints(self):
        export_request = urllib.request.Request(f"{self.proxy_base}/api/config/export", headers={"Authorization": "Bearer sk-local-test"})
        with urllib.request.urlopen(export_request, timeout=5) as response:
            exported = json.loads(response.read().decode("utf-8"))
        self.assertIn("upstreams", exported)

        import_payload = {
            **exported,
            "global_default_model": "gpt-imported",
            "endpoint_mode": "shared",
            "shared_api_prefixes": {"openai": "/openai", "anthropic": "/claude", "gemini": "/gemini"},
        }
        status, payload = make_request(
            f"{self.proxy_base}/api/config/import",
            method="POST",
            data={"config": import_payload},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["config"]["global_default_model"], "gpt-imported")

        current = self.proxy.store.get_config()
        self.assertEqual(current["global_default_model"], "gpt-imported")

    def test_round_robin_rotates_between_upstreams(self):
        self.upstream_one_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-one",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第一个上游"}}],
            },
        }
        self.upstream_two_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-two",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第二个上游"}}],
            },
        }
        config = self.proxy.store.get_config()
        config["auto_routing_enabled"] = True
        config["routing_mode"] = "round_robin"
        self.proxy.store.save_config(config)

        first_status, first_payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "第一次"}]},
        )
        second_status, second_payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "第二次"}]},
        )

        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual(first_payload["choices"][0]["message"]["content"], "来自第一个上游")
        self.assertEqual(second_payload["choices"][0]["message"]["content"], "来自第二个上游")
        self.assertEqual(len(self.upstream_one_log), 1)
        self.assertEqual(len(self.upstream_two_log), 1)

    def test_global_default_model_is_injected_when_request_model_is_missing(self):
        self.upstream_one_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-one",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "global default"}}],
            },
        }
        config = self.proxy.store.get_config()
        config["default_model_mode"] = "global"
        config["global_default_model"] = "gpt-5.4"
        config["auto_routing_enabled"] = False
        config["manual_active_upstream_id"] = config["upstreams"][0]["id"]
        self.proxy.store.save_config(config)

        status, _payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"messages": [{"role": "user", "content": "没有显式模型"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.upstream_one_log[0]["body"])["model"], "gpt-5.4")

    def test_upstream_default_model_is_injected_when_request_model_is_missing(self):
        self.upstream_one_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-one",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "upstream default"}}],
            },
        }
        config = self.proxy.store.get_config()
        config["default_model_mode"] = "upstream"
        config["upstreams"][0]["default_model"] = "gpt-5.3-codex"
        config["auto_routing_enabled"] = False
        config["manual_active_upstream_id"] = config["upstreams"][0]["id"]
        self.proxy.store.save_config(config)

        status, _payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"messages": [{"role": "user", "content": "没有显式模型"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.upstream_one_log[0]["body"])["model"], "gpt-5.3-codex")

    def test_protocol_specific_default_model_is_used_for_anthropic_requests(self):
        self.upstream_one_routes[("POST", "/v1/messages")] = {
            "status": 200,
            "body": {
                "id": "msg-one",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "anthropic default"}],
            },
        }
        config = self.proxy.store.get_config()
        config["upstreams"][0]["protocol"] = "anthropic"
        config["upstreams"][0]["base_url"] = f"http://127.0.0.1:{self.upstream_one.server_address[1]}"
        config["upstreams"][1]["enabled"] = False
        config["default_model_mode_by_protocol"]["anthropic"] = "global"
        config["global_default_models_by_protocol"]["anthropic"] = "claude-opus-4-1"
        config["routing_by_protocol"]["anthropic"]["auto_routing_enabled"] = False
        config["routing_by_protocol"]["anthropic"]["manual_active_upstream_id"] = config["upstreams"][0]["id"]
        self.proxy.store.save_config(config)

        status, _payload = make_request(
            f"{self.proxy_base}/anthropic/v1/messages",
            method="POST",
            token="sk-local-test",
            data={"max_tokens": 32, "messages": [{"role": "user", "content": "hello"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.upstream_one_log[0]["body"])["model"], "claude-opus-4-1")

    def test_auto_routing_skips_upstream_that_does_not_advertise_requested_model(self):
        self.upstream_one_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-one",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第一个上游"}}],
            },
        }
        self.upstream_two_routes[("POST", "/v1/chat/completions")] = {
            "status": 503,
            "body": {
                "error": {
                    "message": "No available channel for model gpt-5.4",
                    "type": "new_api_error",
                    "code": "model_not_found",
                }
            },
        }
        self.proxy.store.record_probe_result(
            self.proxy.store.get_config()["upstreams"][0]["id"],
            status=200,
            models_count=1,
            models=["gpt-5.4"],
        )
        self.proxy.store.record_probe_result(
            self.proxy.store.get_config()["upstreams"][1]["id"],
            status=200,
            models_count=1,
            models=["claude-sonnet-4-6"],
        )

        status, payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-5.4", "messages": [{"role": "user", "content": "hello"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["choices"][0]["message"]["content"], "来自第一个上游")
        self.assertEqual(len(self.upstream_one_log), 1)
        self.assertEqual(len(self.upstream_two_log), 0)

    def test_latency_mode_prefers_lower_latency_upstream(self):
        self.upstream_one_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-one",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第一个上游"}}],
            },
        }
        self.upstream_two_routes[("POST", "/v1/chat/completions")] = {
            "status": 200,
            "body": {
                "id": "chatcmpl-two",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "来自第二个上游"}}],
            },
        }
        config = self.proxy.store.get_config()
        config["auto_routing_enabled"] = True
        config["routing_mode"] = "latency"
        saved = self.proxy.store.save_config(config)
        upstream_one_id = saved["upstreams"][0]["id"]
        upstream_two_id = saved["upstreams"][1]["id"]
        self.proxy.store.record_success(upstream_one_id, 200, latency_ms=220)
        self.proxy.store.record_success(upstream_two_id, 200, latency_ms=40)

        status, payload = make_request(
            f"{self.proxy_base}/v1/chat/completions",
            method="POST",
            token="sk-local-test",
            data={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "测速"}]},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["choices"][0]["message"]["content"], "来自第二个上游")
        self.assertEqual(len(self.upstream_one_log), 0)
        self.assertEqual(len(self.upstream_two_log), 1)

    def test_non_stream_proxy_response_has_single_content_length_header(self):
        connection = HTTPConnection("127.0.0.1", self.proxy.server_address[1], timeout=5)
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=json.dumps({"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "你好"}]}),
            headers={
                "Authorization": "Bearer sk-local-test",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        content_length_headers = [value for key, value in response.getheaders() if key.lower() == "content-length"]
        connection.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(len(content_length_headers), 1)
        self.assertEqual(body["choices"][0]["message"]["content"], "来自第二个上游")

    def test_local_api_key_is_required(self):
        request = urllib.request.Request(f"{self.proxy_base}/v1/models", headers={"Authorization": "Bearer wrong-key"})
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        body = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 401)
        self.assertEqual(body["error"]["code"], "invalid_local_api_key")

    def test_models_all_fail_returns_503_without_double_probing(self):
        self.upstream_one_routes[("GET", "/v1/models")] = {
            "status": 503,
            "body": {"error": {"message": "upstream one unavailable"}},
        }
        self.upstream_two_routes[("GET", "/v1/models")] = {
            "status": 503,
            "body": {"error": {"message": "upstream two unavailable"}},
        }
        request = urllib.request.Request(f"{self.proxy_base}/v1/models", headers={"Authorization": "Bearer sk-local-test"})
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request, timeout=5)
        body = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 503)
        self.assertEqual(body["error"]["code"], "all_upstreams_failed")
        self.assertEqual(len(self.upstream_one_log), 1)
        self.assertEqual(len(self.upstream_two_log), 1)

    def test_upstream_probe_returns_detected_model_ids(self):
        upstream_id = self.proxy.store.get_config()["upstreams"][0]["id"]
        status, payload = make_request(
            f"{self.proxy_base}/api/test",
            method="POST",
            data={"id": upstream_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["models"], ["gpt-a"])
        self.assertEqual(payload["result"]["models_count"], 1)

    def test_legacy_config_is_migrated_to_upstreams(self):
        config = normalize_config({"url": "https://demo.example/v1", "token": "sk-demo", "model": "gpt-4.1-mini"})
        self.assertEqual(config["upstreams"][0]["base_url"], "https://demo.example/v1")
        self.assertEqual(config["upstreams"][0]["api_key"], "sk-demo")
        self.assertEqual(config["upstreams"][0]["default_model"], "gpt-4.1-mini")
        self.assertEqual(config["upstreams"][0]["protocol"], "openai")
        self.assertTrue(config["auto_routing_enabled"])
        self.assertEqual(config["routing_mode"], "priority")
        self.assertEqual(config["default_model_mode"], "upstream")
        self.assertEqual(config["ui_language"], "auto")


class ProbeParsingTest(unittest.TestCase):
    def test_extract_model_ids_handles_openai_anthropic_and_gemini_shapes(self):
        self.assertEqual(extract_model_ids("openai", {"data": [{"id": "gpt-5.4"}, {"id": "gpt-5.4"}]}), ["gpt-5.4"])
        self.assertEqual(extract_model_ids("anthropic", {"data": [{"id": "claude-sonnet-4-5"}]}), ["claude-sonnet-4-5"])
        self.assertEqual(extract_model_ids("gemini", {"models": [{"name": "models/gemini-2.5-pro"}]}), ["models/gemini-2.5-pro"])


class CodexSwitchTest(unittest.TestCase):
    def test_switch_and_restore_codex_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "config.toml"
            auth_path = tempdir_path / "auth.json"
            backup_path = tempdir_path / "backup.json"

            config_path.write_text(
                '\n'.join(
                    [
                        'model_provider = "my_codex"',
                        '',
                        '[model_providers.my_codex]',
                        'name = "my_codex"',
                        'base_url = "https://old.example/v1"',
                        'wire_api = "responses"',
                        'requires_openai_auth = true',
                        '',
                    ]
                ),
                encoding="utf-8",
            )
            auth_path.write_text(json.dumps({"OPENAI_API_KEY": "sk-old", "auth_mode": "apikey"}), encoding="utf-8")

            switch_result = switch_codex_cli_to_local_hub(
                "http://127.0.0.1:8820/v1",
                "sk-local-test",
                config_path=config_path,
                auth_path=auth_path,
                backup_path=backup_path,
            )
            self.assertTrue(switch_result["ok"])
            self.assertIn('base_url = "http://127.0.0.1:8820/v1"', config_path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(auth_path.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "sk-local-test")
            self.assertTrue(backup_path.exists())

            restore_result = restore_codex_cli_from_backup(backup_path=backup_path)
            self.assertTrue(restore_result["ok"])
            self.assertFalse(backup_path.exists())
            self.assertIn('base_url = "https://old.example/v1"', config_path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(auth_path.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "sk-old")

    def test_codex_binding_status_marks_external_when_other_instance_is_running(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "config.toml"
            auth_path = tempdir_path / "auth.json"
            config_path.write_text(
                '\n'.join(
                    [
                        'model_provider = "my_codex"',
                        '',
                        '[model_providers.my_codex]',
                        'name = "my_codex"',
                        'base_url = "http://127.0.0.1:8820/v1"',
                        'wire_api = "responses"',
                        'requires_openai_auth = true',
                        '',
                    ]
                ),
                encoding="utf-8",
            )
            auth_path.write_text(json.dumps({"OPENAI_API_KEY": "sk-local-test", "auth_mode": "apikey"}), encoding="utf-8")

            status = get_codex_cli_binding_status(
                "http://127.0.0.1:8820/v1",
                "sk-local-test",
                config_path=config_path,
                auth_path=auth_path,
                service_state="external",
            )
            self.assertEqual(status["state"], "external")
            self.assertEqual(status["dashboard_url"], "http://127.0.0.1:8820/")

    def test_codex_binding_status_missing_files_is_not_switched(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            status = get_codex_cli_binding_status(
                "http://127.0.0.1:8820/v1",
                "sk-local-test",
                config_path=tempdir_path / "missing-config.toml",
                auth_path=tempdir_path / "missing-auth.json",
            )
            self.assertEqual(status["state"], "not_switched")
            self.assertEqual(status["base_url"], "")


class ClientSwitchTest(unittest.TestCase):
    def test_switch_and_restore_claude_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            settings_path = tempdir_path / "settings.json"
            backup_path = tempdir_path / "claude-backup.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "https://old-claude.example",
                            "ANTHROPIC_AUTH_TOKEN": "sk-old",
                        }
                    }
                ),
                encoding="utf-8",
            )

            switch_result = switch_claude_cli_to_local_hub(
                "http://127.0.0.1:8820/anthropic",
                "sk-local-test",
                settings_path=settings_path,
                backup_path=backup_path,
            )
            self.assertTrue(switch_result["ok"])
            switched = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(switched["env"]["ANTHROPIC_BASE_URL"], "http://127.0.0.1:8820/anthropic")
            self.assertEqual(switched["env"]["ANTHROPIC_AUTH_TOKEN"], "sk-local-test")
            self.assertEqual(switched["env"]["ANTHROPIC_API_KEY"], "sk-local-test")

            status = get_claude_cli_binding_status(
                "http://127.0.0.1:8820/anthropic",
                "sk-local-test",
                settings_path=settings_path,
                service_state="running",
            )
            self.assertEqual(status["state"], "switched")

            restore_result = restore_claude_cli_from_backup(backup_path=backup_path)
            self.assertTrue(restore_result["ok"])
            restored = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(restored["env"]["ANTHROPIC_BASE_URL"], "https://old-claude.example")
            self.assertEqual(restored["env"]["ANTHROPIC_AUTH_TOKEN"], "sk-old")

    def test_switch_and_restore_gemini_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            auth_path = tempdir_path / "auth.json"
            backup_path = tempdir_path / "gemini-backup.json"
            auth_path.write_text(
                json.dumps(
                    {
                        "GOOGLE_GEMINI_BASE_URL": "https://old-gemini.example",
                        "GEMINI_API_KEY": "sk-old",
                        "GEMINI_MODEL": "gemini-2.5-pro",
                    }
                ),
                encoding="utf-8",
            )

            switch_result = switch_gemini_cli_to_local_hub(
                "http://127.0.0.1:8820/gemini",
                "sk-local-test",
                auth_path=auth_path,
                backup_path=backup_path,
            )
            self.assertTrue(switch_result["ok"])
            switched = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(switched["GOOGLE_GEMINI_BASE_URL"], "http://127.0.0.1:8820/gemini")
            self.assertEqual(switched["GEMINI_API_KEY"], "sk-local-test")

            status = get_gemini_cli_binding_status(
                "http://127.0.0.1:8820/gemini",
                "sk-local-test",
                auth_path=auth_path,
                service_state="running",
            )
            self.assertEqual(status["state"], "switched")

            restore_result = restore_gemini_cli_from_backup(backup_path=backup_path)
            self.assertTrue(restore_result["ok"])
            restored = json.loads(auth_path.read_text(encoding="utf-8"))
            self.assertEqual(restored["GOOGLE_GEMINI_BASE_URL"], "https://old-gemini.example")
            self.assertEqual(restored["GEMINI_API_KEY"], "sk-old")

    def test_generic_client_switch_and_restore_dispatch(self):
        runtime_base_urls = {
            "codex": "http://127.0.0.1:8820/openai",
            "claude": "http://127.0.0.1:8820/claude",
            "gemini": "http://127.0.0.1:8820/gemini",
        }

        with mock.patch("router_server.switch_claude_cli_to_local_hub", return_value={"ok": True, "provider": "anthropic"}) as switch_claude:
            switch_result = switch_client_to_local_hub("claude", runtime_base_urls, "sk-local-test")

        self.assertTrue(switch_result["ok"])
        switch_claude.assert_called_once_with(runtime_base_urls["claude"], "sk-local-test")

        with mock.patch("router_server.restore_gemini_cli_from_backup", return_value={"ok": True, "restored": True}) as restore_gemini:
            restore_result = restore_client_from_backup("gemini")

        self.assertTrue(restore_result["ok"])
        restore_gemini.assert_called_once_with()

    def test_collect_client_binding_statuses_tracks_partial_service_per_protocol(self):
        runtime_base_urls = {
            "codex": "http://127.0.0.1:8820/openai",
            "claude": "http://127.0.0.1:8820/claude",
            "gemini": "http://127.0.0.1:8820/gemini",
        }
        service_details = {
            "state": "partial",
            "owner": "local",
            "active_protocols": ["openai", "gemini"],
            "partially_started": True,
        }
        with mock.patch("router_server.get_codex_cli_binding_status", return_value={"state": "switched"}) as codex_status:
            with mock.patch("router_server.get_claude_cli_binding_status", return_value={"state": "error"}) as claude_status:
                with mock.patch("router_server.get_gemini_cli_binding_status", return_value={"state": "switched"}) as gemini_status:
                    collect_client_binding_statuses(
                        runtime_base_urls,
                        "sk-local-test",
                        service_state="partial",
                        service_details=service_details,
                    )
        codex_status.assert_called_once_with(runtime_base_urls["codex"], "sk-local-test", service_state="running")
        claude_status.assert_called_once_with(runtime_base_urls["claude"], "sk-local-test", service_state="stopped")
        gemini_status.assert_called_once_with(runtime_base_urls["gemini"], "sk-local-test", service_state="running")

    def test_collect_client_binding_statuses_includes_local_llm_only_when_present(self):
        runtime_base_urls = {
            "codex": "http://127.0.0.1:8820/openai",
            "claude": "http://127.0.0.1:8820/claude",
            "gemini": "http://127.0.0.1:8820/gemini",
            "local_llm": "http://127.0.0.1:8820/local",
        }
        service_details = {
            "state": "partial",
            "owner": "local",
            "active_protocols": ["openai", "local_llm"],
            "partially_started": True,
        }
        with mock.patch("router_server.get_codex_cli_binding_status", return_value={"state": "switched"}):
            with mock.patch("router_server.get_claude_cli_binding_status", return_value={"state": "error"}):
                with mock.patch("router_server.get_gemini_cli_binding_status", return_value={"state": "switched"}):
                    with mock.patch("router_server.get_local_llm_cli_binding_status", return_value={"state": "switched"}) as local_llm_status:
                        statuses = collect_client_binding_statuses(
                            runtime_base_urls,
                            "sk-local-test",
                            service_state="partial",
                            service_details=service_details,
                        )
        self.assertIn("local_llm", statuses)
        local_llm_status.assert_called_once_with(runtime_base_urls["local_llm"], "sk-local-test", service_state="running")


class HandlerLoggingTest(unittest.TestCase):
    def test_log_message_handles_mixed_format_args(self):
        class DummyServer:
            quiet_logging = False

        class DummyHandler:
            server = DummyServer()

            def address_string(self):
                return "127.0.0.1"

        with mock.patch("builtins.print") as print_mock:
            RouterRequestHandler.log_message(DummyHandler(), "code %d, message %s", 400, "bad\nrequest")

        self.assertTrue(print_mock.called)
        output = print_mock.call_args[0][0]
        self.assertIn("code 400, message bad\\nrequest", output)


class CompatibilityLayerTest(unittest.TestCase):
    def test_router_server_module_reexports_runtime_symbols_from_modular_impl(self):
        self.assertIs(router_server_module, legacy_impl_module)
        self.assertIs(router_server_module.RouterHTTPServer, http_server_module.RouterHTTPServer)
        self.assertIs(router_server_module.RouterRequestHandler, http_server_module.RouterRequestHandler)
        self.assertIs(router_server_module.create_server, http_server_module.create_server)
        self.assertIs(router_server_module.parse_args, entrypoint_parse_args)


class PlatformSupportTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tempdir.name) / "api-config.json"
        self.base_config = {
            "listen_host": "127.0.0.1",
            "listen_port": 8787,
            "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def make_console_app(self, **overrides):
        config = normalize_config({**self.base_config, **overrides})
        write_json(self.config_path, config)
        app = InteractiveConsoleApp(self.config_path, PROJECT_ROOT / "web")
        app.modern_cli = None
        return app

    def test_shared_mode_assigns_dedicated_web_ui_port(self):
        config = normalize_config({"listen_port": 8787, "endpoint_mode": "shared"})
        self.assertEqual(config["web_ui_port"], config["listen_port"])
        self.assertEqual(config["web_ui_port"], 8787)

    def test_console_app_language_prefers_saved_setting(self):
        with mock.patch.dict("os.environ", {"LANG": "zh_CN.UTF-8"}, clear=False):
            app = self.make_console_app(ui_language="en")
            self.assertEqual(app.language(), "en")

    def test_console_app_language_follows_system_when_auto(self):
        with mock.patch.dict("os.environ", {"LANG": "zh_CN.UTF-8"}, clear=False):
            self.assertEqual(self.make_console_app(ui_language="auto").language(), "zh")
        with mock.patch.dict("os.environ", {"LANG": "en_US.UTF-8"}, clear=False):
            self.assertEqual(self.make_console_app(ui_language="auto").language(), "en")

    def test_console_app_routing_strategy_label_uses_active_language(self):
        self.assertEqual(
            self.make_console_app(ui_language="en").routing_strategy_label("priority"),
            "Auto / Priority order",
        )
        self.assertEqual(
            self.make_console_app(ui_language="zh").routing_strategy_label("priority"),
            "自动 / 顺序优先",
        )

    def test_console_app_formats_client_status_line(self):
        app = self.make_console_app(ui_language="en")
        self.assertEqual(
            app.format_client_status_line(
                "Codex",
                {"state": "switched", "base_url": "http://127.0.0.1:8787/openai"},
            ),
            "🟢 Codex: switched to Hub @ http://127.0.0.1:8787/openai",
        )
        self.assertEqual(
            app.format_client_status_line(
                "Claude Code",
                {"state": "external", "base_url": "http://127.0.0.1:8787/claude"},
            ),
            "🟡 Claude Code: switched to another running Hub @ http://127.0.0.1:8787/claude",
        )
        zh_app = self.make_console_app(ui_language="zh")
        self.assertEqual(
            zh_app.format_client_status_line("Gemini CLI", {"state": "not_switched"}),
            "⚪ Gemini CLI: 未切换",
        )

    def test_console_app_theme_and_language_labels_follow_language(self):
        zh_app = self.make_console_app(ui_language="zh", theme_mode="teal")
        self.assertEqual(zh_app.theme_label("teal"), "青绿")
        self.assertEqual(zh_app.current_language_label(), "中文")

        en_app = self.make_console_app(ui_language="en", theme_mode="teal")
        self.assertEqual(en_app.theme_label("teal"), "Teal")
        self.assertEqual(en_app.current_language_label(), "English")

    def test_console_app_cli_theme_mode_is_independent_from_web_theme(self):
        app = self.make_console_app(ui_language="en", theme_mode="dark", cli_theme_mode="rose")
        self.assertEqual(app.cli_theme_mode(), "rose")
        self.assertEqual(app.current_cli_theme_label(), "Rose")

    def test_console_app_protocol_status_labels(self):
        app = self.make_console_app(ui_language="en")
        snapshot = {
            "service": {"state": "partial", "owner": "local", "active_protocols": ["openai"]},
            "clients": {"codex": {"state": "switched"}, "claude": {"state": "not_switched"}},
        }
        self.assertEqual(app.protocol_service_status_label(snapshot, "openai"), "🟢 Running")
        self.assertEqual(app.protocol_service_status_label(snapshot, "anthropic"), "⚪ Stopped")
        self.assertEqual(app.protocol_client_status_label(snapshot, "openai"), "🟢 Enabled here")
        self.assertEqual(app.protocol_client_status_label(snapshot, "anthropic"), "⚪ Not enabled")

    def test_console_app_runtime_mode_label_distinguishes_forwarding_proxy_and_external(self):
        app = self.make_console_app(ui_language="en")
        forwarding = {
            "service": {"state": "running", "active_protocols": ["openai"]},
            "clients": {"codex": {"state": "not_switched"}},
        }
        proxy = {
            "service": {"state": "running", "active_protocols": ["openai", "anthropic"]},
            "clients": {"codex": {"state": "switched"}, "claude": {"state": "external"}},
        }
        external = {
            "service": {"state": "external", "active_protocols": []},
            "clients": {},
        }
        self.assertEqual(app.runtime_mode_label(forwarding), "Forwarding mode")
        self.assertEqual(app.runtime_mode_label(proxy), "Proxy mode")
        self.assertEqual(app.runtime_mode_label(external), "External instance")

    def test_console_app_format_protocol_list_normalizes_aliases(self):
        app = self.make_console_app(ui_language="en")
        self.assertEqual(app.format_protocol_list(["claude", "gemini"]), "Claude, Gemini")
        self.assertEqual(app.format_protocol_list(["openai"]), "Codex")

    def test_console_app_protocol_upstream_indices_filters_by_protocol(self):
        app = self.make_console_app(
            ui_language="en",
            upstreams=[
                {"name": "OpenAI A", "base_url": "https://a.example/v1", "api_key": "sk-a", "protocol": "openai"},
                {"name": "Claude A", "base_url": "https://c.example", "api_key": "sk-c", "protocol": "anthropic"},
                {"name": "OpenAI B", "base_url": "https://b.example/v1", "api_key": "sk-b", "protocol": "openai"},
            ],
        )
        indices = app.protocol_upstream_indices(app.store.get_config(), "openai")
        self.assertEqual(indices, [0, 2])

    def test_cli_local_keys_parse_allowed_protocols_input_supports_aliases(self):
        self.assertEqual(parse_allowed_protocols_input("1 3"), ["openai", "gemini"])
        self.assertEqual(parse_allowed_protocols_input("claude,gemini"), ["anthropic", "gemini"])
        self.assertEqual(parse_allowed_protocols_input("all"), ["openai", "anthropic", "gemini", "local_llm"])
        self.assertEqual(parse_allowed_protocols_input(""), None)
        self.assertEqual(parse_allowed_protocols_input("unknown"), [])

    def test_cli_local_keys_build_local_key_entry_starts_disabled(self):
        entry = build_local_key_entry("en", 1, "sk-local-demo", "2026-04-07T00:00:00+00:00")
        self.assertEqual(entry["name"], "Local Key 2")
        self.assertEqual(entry["key"], "sk-local-demo")
        self.assertFalse(entry["enabled"])
        self.assertEqual(entry["allowed_protocols"], ["openai", "anthropic", "gemini", "local_llm"])

    def test_console_app_print_client_action_results_formats_messages(self):
        app = self.make_console_app(ui_language="en")
        with mock.patch.object(app, "print_info") as print_info:
            app.print_client_action_results(
                {
                    "codex": {"ok": True},
                    "claude": {"ok": False, "message": "boom"},
                    "gemini": {"ok": True, "restored": False},
                },
                "restore",
            )
        self.assertEqual(
            [call.args[0] for call in print_info.call_args_list],
            [
                "Codex: restored",
                "Claude Code: restore failed: boom",
                "Gemini CLI: nothing to restore",
            ],
        )

    def test_console_app_runtime_apply_status_detects_pending_network_changes(self):
        app = self.make_console_app(
            ui_language="en",
            listen_port=9000,
            endpoint_mode="shared",
            shared_api_prefixes={"openai": "/openai-next"},
        )
        snapshot = {
            "service": {"state": "running", "owner": "local", "active_protocols": ["openai"]},
            "runtime": {
                "host": "127.0.0.1",
                "port": 8787,
                "listen_host": "127.0.0.1",
                "listen_port": 8787,
                "web_ui_port": 8787,
                "endpoint_mode": "shared",
                "shared_api_prefixes": {
                    "openai": "/openai",
                    "anthropic": "/claude",
                    "gemini": "/gemini",
                    "local_llm": "/local",
                },
                "split_api_ports": {
                    "openai": 8787,
                    "anthropic": 8788,
                    "gemini": 8789,
                    "local_llm": 8790,
                },
            },
        }
        with mock.patch.object(app, "get_runtime_snapshot", return_value=snapshot):
            status = app.runtime_apply_status()
            summary = app.runtime_apply_summary()

        self.assertTrue(status["enabled"])
        self.assertTrue(status["settings"])
        self.assertTrue(status["global_runtime"])
        self.assertTrue(status["protocol_workspace"])
        self.assertTrue(status["protocols"]["openai"])
        self.assertIn("Global runtime & ports", summary)
        self.assertIn("Codex", summary)

    def test_cli_usage_prepare_usage_chart_data_filters_by_protocol_scope(self):
        usage = {
            "upstreams": [
                {"id": "oa-1", "name": "OpenAI 1"},
                {"id": "cl-1", "name": "Claude 1"},
            ],
            "buckets": [
                {"start_ts": 1000, "end_ts": 2000, "by_upstream": {"oa-1": 2, "cl-1": 5}},
                {"start_ts": 2000, "end_ts": 3000, "by_upstream": {"cl-1": 1}},
            ],
        }
        config = {
            "upstreams": [
                {"id": "oa-1", "protocol": "openai"},
                {"id": "cl-1", "protocol": "anthropic"},
            ]
        }
        legend, buckets, max_total = prepare_usage_chart_data(usage, config, "openai", language="en")
        self.assertEqual([item["id"] for item in legend], ["oa-1"])
        self.assertEqual([bucket["total"] for bucket in buckets], [2, 0])
        self.assertEqual(buckets[0]["by_group"], {"oa-1": 2})
        self.assertEqual(max_total, 2)

    def test_cli_usage_prepare_usage_chart_data_filters_by_local_key(self):
        usage = {
            "upstreams": [
                {"id": "oa-1", "name": "OpenAI 1"},
                {"id": "cl-1", "name": "Claude 1"},
            ],
            "local_keys": [
                {"id": "key-a", "name": "Key A"},
                {"id": "key-b", "name": "Key B"},
            ],
            "buckets": [
                {
                    "start_ts": 1000,
                    "end_ts": 2000,
                    "pairs": [
                        {"upstream_id": "oa-1", "local_key_id": "key-a", "count": 2},
                        {"upstream_id": "cl-1", "local_key_id": "key-b", "count": 3},
                    ],
                },
                {
                    "start_ts": 2000,
                    "end_ts": 3000,
                    "pairs": [
                        {"upstream_id": "oa-1", "local_key_id": "", "count": 1},
                    ],
                },
            ],
        }
        config = {
            "upstreams": [
                {"id": "oa-1", "protocol": "openai"},
                {"id": "cl-1", "protocol": "anthropic"},
            ],
            "local_api_keys": [
                {"id": "key-a", "name": "Key A", "allowed_protocols": ["openai"]},
                {"id": "key-b", "name": "Key B", "allowed_protocols": ["anthropic"]},
            ],
        }
        legend, buckets, max_total = prepare_usage_chart_data(usage, config, "all", "key-a", language="en")
        self.assertEqual([item["id"] for item in legend], ["oa-1"])
        self.assertEqual(buckets[0]["by_group"], {"oa-1": 2})
        self.assertEqual(buckets[1]["by_group"], {})
        self.assertEqual(max_total, 2)

    def test_console_app_menu_protocol_workspace_selector_routes_choice(self):
        app = self.make_console_app(ui_language="en")
        with mock.patch.object(app, "print_header"):
            with mock.patch.object(app, "print_info"):
                with mock.patch.object(app, "print_menu_lines"):
                    with mock.patch.object(app, "pause"):
                        with mock.patch.object(app, "menu_protocol_workspace") as workspace_menu:
                            with mock.patch.object(app, "prompt_choice", side_effect=["2", "0"]):
                                app.menu_protocol_workspace_selector()
        workspace_menu.assert_called_once_with("anthropic")

    def test_console_app_menu_protocol_workspace_routes_default_model_choice(self):
        app = self.make_console_app(ui_language="en")
        snapshot = app.get_runtime_snapshot()
        with mock.patch.object(app, "get_runtime_snapshot", return_value=snapshot):
            with mock.patch.object(app, "print_header"):
                with mock.patch.object(app, "print_info"):
                    with mock.patch.object(app, "print_menu_lines"):
                        with mock.patch.object(app, "pause"):
                            with mock.patch.object(app, "menu_protocol_default_models") as menu_default_models:
                                with mock.patch.object(app, "prompt_choice", side_effect=["2", "0"]):
                                    app.menu_protocol_workspace("openai")
        menu_default_models.assert_called_once_with("openai")

    def test_console_app_menu_protocol_upstreams_direct_number_opens_detail(self):
        app = self.make_console_app(ui_language="en")
        snapshot = app.get_runtime_snapshot()
        with mock.patch.object(app, "get_runtime_snapshot", return_value=snapshot):
            with mock.patch.object(app, "print_header"):
                with mock.patch.object(app, "print_info"):
                    with mock.patch.object(app, "print_menu_lines"):
                        with mock.patch.object(app, "pause"):
                            with mock.patch.object(app.upstream_controller, "menu_upstream_detail") as detail_menu:
                                with mock.patch.object(app, "prompt_choice", side_effect=["1", "0"]):
                                    app.menu_protocol_upstreams("openai")
        detail_menu.assert_called_once()
        self.assertEqual(detail_menu.call_args.args[0], "openai")

    def test_console_app_menu_upstream_detail_routes_subscription_menu(self):
        app = self.make_console_app(ui_language="en")
        snapshot = app.get_runtime_snapshot()
        with mock.patch.object(app, "get_runtime_snapshot", return_value=snapshot):
            with mock.patch.object(app, "print_header"):
                with mock.patch.object(app, "print_info"):
                    with mock.patch.object(app, "print_menu_lines"):
                        with mock.patch.object(app, "pause"):
                            with mock.patch.object(app.upstream_controller, "menu_upstream_subscriptions") as subscription_menu:
                                with mock.patch.object(app, "prompt_choice", side_effect=["6", "0"]):
                                    app.menu_upstream_detail("openai", 0)
        subscription_menu.assert_called_once_with(0)

    def test_console_app_menu_local_keys_direct_number_opens_editor(self):
        app = self.make_console_app(ui_language="en", local_api_key="sk-local-test")
        snapshot = app.get_runtime_snapshot()
        with mock.patch.object(app, "get_runtime_snapshot", return_value=snapshot):
            with mock.patch.object(app, "print_header"):
                with mock.patch.object(app, "print_info"):
                    with mock.patch.object(app, "print_menu_lines"):
                        with mock.patch.object(app, "pause"):
                            with mock.patch.object(app.local_key_controller, "menu_local_api_key_editor") as editor_menu:
                                with mock.patch.object(app, "prompt_choice", side_effect=["1", "0"]):
                                    app.menu_local_api_keys()
        editor_menu.assert_called_once_with(0)

    def test_console_app_menu_local_key_detail_can_set_primary(self):
        app = self.make_console_app(
            ui_language="en",
            local_api_keys=[
                {"name": "Primary", "key": "sk-local-primary", "enabled": True},
                {"name": "Backup", "key": "sk-local-backup", "enabled": False},
            ],
        )
        target_id = app.store.get_config()["local_api_keys"][1]["id"]
        with mock.patch.object(app, "print_header"):
            with mock.patch.object(app, "print_info"):
                with mock.patch.object(app, "print_menu_lines"):
                    with mock.patch.object(app, "pause"):
                        with mock.patch.object(app, "refresh_switched_clients"):
                            with mock.patch.object(app, "prompt_choice", side_effect=["3", "0"]):
                                app.menu_local_api_key_editor(1)
        updated = app.store.get_config()["local_api_keys"]
        self.assertEqual(updated[0]["id"], target_id)
        self.assertTrue(updated[0]["enabled"])

    def test_console_app_menu_local_key_detail_can_toggle_enabled(self):
        app = self.make_console_app(
            ui_language="en",
            local_api_keys=[
                {"name": "Primary", "key": "sk-local-primary", "enabled": True},
                {"name": "Backup", "key": "sk-local-backup", "enabled": False},
            ],
        )
        target_id = app.store.get_config()["local_api_keys"][1]["id"]
        with mock.patch.object(app, "print_header"):
            with mock.patch.object(app, "print_info"):
                with mock.patch.object(app, "print_menu_lines"):
                    with mock.patch.object(app, "pause"):
                        with mock.patch.object(app, "refresh_switched_clients"):
                            with mock.patch.object(app, "prompt_choice", side_effect=["4", "0"]):
                                app.menu_local_api_key_editor(1)
        updated = next(item for item in app.store.get_config()["local_api_keys"] if item["id"] == target_id)
        self.assertTrue(updated["enabled"])

    def test_console_app_menu_local_key_detail_can_delete(self):
        app = self.make_console_app(
            ui_language="en",
            local_api_keys=[
                {"name": "Primary", "key": "sk-local-primary", "enabled": True},
                {"name": "Backup", "key": "sk-local-backup", "enabled": False},
            ],
        )
        with mock.patch.object(app, "print_header"):
            with mock.patch.object(app, "print_info"):
                with mock.patch.object(app, "print_menu_lines"):
                    with mock.patch.object(app, "pause"):
                        with mock.patch.object(app, "refresh_switched_clients"):
                            with mock.patch.object(app, "prompt_yes_no", return_value=True):
                                with mock.patch.object(app, "prompt_choice", side_effect=["6"]):
                                    app.menu_local_api_key_editor(1)
        updated = app.store.get_config()["local_api_keys"]
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["name"], "Primary")

    def test_console_app_menu_settings_routes_choice(self):
        app = self.make_console_app(ui_language="en")
        with mock.patch.object(app, "print_header"):
            with mock.patch.object(app, "print_info"):
                with mock.patch.object(app, "print_menu_lines"):
                    with mock.patch.object(app, "pause"):
                        with mock.patch.object(app, "menu_config_transfer") as menu_config_transfer:
                            with mock.patch.object(app, "prompt_choice", side_effect=["4", "0"]):
                                app.menu_settings()
        menu_config_transfer.assert_called_once_with()

    def test_foreground_runtime_lines_compact_shared_mode_output(self):
        lines = entrypoint_foreground_runtime_lines(
            Path("/tmp/api-config.json"),
            {
                "dashboard_url": "http://127.0.0.1:8820/",
                "listen_host": "127.0.0.1",
                "listen_port": 8787,
                "endpoint_mode": "shared",
                "shared_api_prefixes": {
                    "openai": "/openai",
                    "anthropic": "/claude",
                    "gemini": "/gemini",
                },
            },
            {
                "local_api_key": "sk-local-1234567890abcdef",
                "local_api_keys": [{"id": "primary"}],
            },
        )
        self.assertIn("AI Proxy Hub 已启动", lines[0])
        self.assertIn("Web 控制台: http://127.0.0.1:8820/", lines[2])
        self.assertIn("API: shared 127.0.0.1:8787 | Codex /openai | Claude /claude | Gemini /gemini", lines[3])
        self.assertIn("本地 Keys: 1 | 主 Key sk-local-123...cdef", lines[4])

    def test_write_runtime_line_falls_back_to_stdout_buffer_on_unicode_encode_error(self):
        class BrokenStdout:
            def __init__(self):
                self.buffer = io.BytesIO()
                self.flush_count = 0

            def write(self, _value):
                raise UnicodeEncodeError("cp1252", "已", 0, 1, "character maps to <undefined>")

            def flush(self):
                self.flush_count += 1

        stdout = BrokenStdout()
        with mock.patch.object(sys, "stdout", stdout):
            entrypoint_write_runtime_line("AI Proxy Hub 已启动")
        self.assertIn("AI Proxy Hub 已启动", stdout.buffer.getvalue().decode("utf-8"))
        self.assertEqual(stdout.flush_count, 1)

    def test_print_runtime_paths_includes_project_metadata(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            entrypoint_print_runtime_paths(self.config_path, PROJECT_ROOT / "web")
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["project"]["version"], payload["version"])
        self.assertEqual(payload["project"]["license"]["name"], "Apache-2.0")
        self.assertEqual(payload["project"]["author"], "weicj")
        self.assertTrue(payload["project"]["source"]["configured"])
        self.assertEqual(payload["project"]["source"]["url"], "https://github.com/weicj/ai-proxy-hub")
        self.assertEqual(payload["project"]["updates"]["url"], "https://github.com/weicj/ai-proxy-hub/releases")
        self.assertEqual(payload["project"]["updates"]["channel"], "manual")

    def test_app_config_dir_linux_prefers_xdg(self):
        path = app_config_dir(home=Path("/home/demo"), env={"XDG_CONFIG_HOME": "/tmp/xdg"}, family="linux")
        self.assertEqual(path, Path("/tmp/xdg") / APP_SLUG)

    def test_status_payload_includes_project_metadata(self):
        app = self.make_console_app(ui_language="en")
        status = app.store.get_status("127.0.0.1", 8787, service_state="stopped")
        self.assertEqual(status["app"]["name"], APP_NAME)
        self.assertEqual(status["app"]["author"], "weicj")
        self.assertEqual(status["app"]["license"]["name"], "Apache-2.0")
        self.assertTrue(status["app"]["source"]["configured"])
        self.assertEqual(status["app"]["source"]["url"], "https://github.com/weicj/ai-proxy-hub")
        self.assertEqual(status["app"]["updates"]["url"], "https://github.com/weicj/ai-proxy-hub/releases")
        self.assertEqual(status["app"]["updates"]["channel"], "manual")

    def test_app_config_dir_macos_uses_application_support(self):
        path = app_config_dir(home=Path("/Users/demo"), env={}, family="macos")
        self.assertEqual(path, Path("/Users/demo/Library/Application Support") / APP_NAME)

    def test_app_config_dir_windows_uses_appdata(self):
        path = app_config_dir(home=Path("C:/Users/demo"), env={"APPDATA": "C:/Users/demo/AppData/Roaming"}, family="windows")
        self.assertEqual(path, Path("C:/Users/demo/AppData/Roaming") / APP_NAME)

    def test_resolve_static_dir_falls_back_to_shared_prefix(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            base_dir = tempdir_path / "repo"
            share_dir = tempdir_path / "prefix" / "share" / APP_SLUG / "web"
            share_dir.mkdir(parents=True)
            (share_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            with mock.patch("router_server.sys.prefix", str(tempdir_path / "prefix")):
                with mock.patch("router_server.sys.base_prefix", str(tempdir_path / "base")):
                    resolved = resolve_static_dir(base_dir)
            self.assertEqual(resolved, share_dir.resolve())

    def test_pyproject_data_files_include_all_split_web_assets(self):
        pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for asset in [
            "web/index.html",
            "web/app-theme.css",
            "web/app.css",
            "web/app-effects.css",
            "web/app-01-i18n.js",
            "web/app-02-foundation.js",
            "web/app-02-model.js",
            "web/app-02-core.js",
            "web/app-03-ui.js",
            "web/app-03-runtime.js",
            "web/app-03-upstream-render.js",
            "web/app-03-upstream-editor.js",
            "web/app-03-upstreams.js",
            "web/app-04-usage.js",
            "web/app-05-bootstrap.js",
        ]:
            self.assertIn(f'"{asset}"', pyproject_text)

    def test_manifest_includes_web_css_assets(self):
        manifest_text = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("recursive-include web *.html *.js *.css", manifest_text)
        self.assertIn("include LICENSE", manifest_text)
        self.assertIn("include NOTICE", manifest_text)

    def test_pyproject_declares_apache_license_metadata(self):
        pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('requires = ["setuptools>=68", "wheel>=0.42"]', pyproject_text)
        self.assertIn('license = {file = "LICENSE"}', pyproject_text)
        self.assertIn('"License :: OSI Approved :: Apache Software License"', pyproject_text)
        self.assertIn('license-files = ["LICENSE", "NOTICE"]', pyproject_text)

    def test_release_staging_includes_runtime_package_and_split_web_assets(self):
        with tempfile.TemporaryDirectory() as tempdir:
            staging_root = build_release_module.stage_release_tree(PROJECT_ROOT, "0.0.0-test", Path(tempdir))
            self.assertTrue((staging_root / "LICENSE").exists())
            self.assertTrue((staging_root / "start.py").exists())
            self.assertTrue((staging_root / "router_server.py").exists())
            self.assertTrue((staging_root / "ai_proxy_hub" / "__main__.py").exists())
            self.assertTrue((staging_root / "cli_modern.py").exists())
            self.assertTrue((staging_root / "ai_proxy_hub" / "__init__.py").exists())
            self.assertTrue((staging_root / "ai_proxy_hub" / "entrypoints.py").exists())
            self.assertTrue((staging_root / "web" / "index.html").exists())
            self.assertTrue((staging_root / "web" / "app-05-bootstrap.js").exists())
            self.assertFalse((staging_root / "config_8830.json").exists())

    def test_sync_release_snapshot_copies_source_tree_without_runtime_noise(self):
        with tempfile.TemporaryDirectory() as source_tempdir, tempfile.TemporaryDirectory() as release_tempdir:
            source_root = Path(source_tempdir)
            release_root = Path(release_tempdir)
            for relative, content in {
                ".gitignore": "*.pyc\n",
                "README.md": "# demo\n",
                "pyproject.toml": "[project]\nname='demo'\n",
                "start.py": "print('start')\n",
                "router_server.py": "print('ok')\n",
                "cli_modern.py": "print('cli')\n",
                ".github/workflows/ci.yml": "name: ci\n",
                "ai_proxy_hub/__init__.py": "__all__ = []\n",
                "docs/PROJECT_STRUCTURE.md": "# docs\n",
                "examples/api-config.example.json": "{}\n",
                "scripts/build_release.py": "APP_SLUG = 'demo'\n",
                "tests/test_demo.py": "def test_ok():\n    assert True\n",
                "web/index.html": "<html></html>\n",
                "config_8830.json": "{}\n",
                "tmp/debug.log": "noise\n",
                "dist/output.txt": "artifact\n",
            }.items():
                target = source_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            snapshot_dir = sync_release_snapshot_module.sync_release_snapshot(source_root, release_root, "v0.0.0")

            self.assertTrue((snapshot_dir / ".github" / "workflows" / "ci.yml").exists())
            self.assertTrue((snapshot_dir / "ai_proxy_hub" / "__init__.py").exists())
            self.assertTrue((snapshot_dir / "start.py").exists())
            self.assertTrue((snapshot_dir / "scripts" / "build_release.py").exists())
            self.assertTrue((snapshot_dir / "tests" / "test_demo.py").exists())
            self.assertTrue((snapshot_dir / "web" / "index.html").exists())
            self.assertTrue((snapshot_dir / "SYNC_MANIFEST.json").exists())
            self.assertFalse((snapshot_dir / "config_8830.json").exists())
            self.assertFalse((snapshot_dir / "tmp").exists())
            self.assertFalse((snapshot_dir / "dist").exists())

    def test_sync_homebrew_tap_writes_formula_and_readme(self):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            formula_path = temp_path / "ai-proxy-hub.rb"
            formula_path.write_text("class AiProxyHub < Formula\nend\n", encoding="utf-8")

            target_formula = sync_homebrew_tap_module.sync_homebrew_tap(
                formula_path,
                temp_path / "homebrew-tap",
                "weicj/homebrew-tap",
                version="0.3.1",
            )

            self.assertEqual(target_formula.name, "ai-proxy-hub.rb")
            self.assertTrue(target_formula.exists())
            self.assertIn("class AiProxyHub < Formula", target_formula.read_text(encoding="utf-8"))
            tap_readme = (temp_path / "homebrew-tap" / "README.md").read_text(encoding="utf-8")
            self.assertIn("brew tap weicj/homebrew-tap", tap_readme)
            self.assertIn("brew install weicj/tap/ai-proxy-hub", tap_readme)
            self.assertTrue((temp_path / "homebrew-tap" / ".gitignore").exists())

    def test_index_html_references_extracted_stylesheet(self):
        index_text = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="/app-theme.css" />', index_text)
        self.assertIn('<link rel="stylesheet" href="/app.css" />', index_text)
        self.assertIn('<link rel="stylesheet" href="/app-effects.css" />', index_text)

    def test_write_json_tolerates_platforms_without_chown(self):
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "demo.json"
            with mock.patch("router_server.os.chown", side_effect=NotImplementedError, create=True):
                write_json(target, {"ok": True})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["ok"], True)

    def test_preferred_app_config_dir_falls_back_when_default_dir_is_not_writable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            home = Path(tempdir)
            default_dir = home / "Library" / "Application Support" / APP_NAME
            default_dir.mkdir(parents=True)
            with mock.patch("router_server.os.getuid", return_value=999999, create=True):
                preferred = preferred_app_config_dir(home=home, env={}, family="macos")
            self.assertEqual(preferred, home / ".config" / APP_SLUG)

    def test_app_config_dir_candidates_include_expected_fallbacks_without_duplicates(self):
        home = Path("/Users/demo")
        candidates = app_config_dir_candidates(home=home, env={}, family="macos")
        self.assertEqual(
            candidates,
            [
                home / "Library" / "Application Support" / APP_NAME,
                home / ".config" / APP_SLUG,
                home / f".{APP_SLUG}",
            ],
        )

    def test_legacy_config_locations_include_legacy_slugs_without_duplicates(self):
        base_dir = Path("/repo")
        home = Path("/Users/demo")
        paths = legacy_config_locations(base_dir, home=home, env={"APPDATA": "C:/Users/demo/AppData/Roaming"})
        self.assertEqual(paths[0], (base_dir / "api-config.json").resolve())
        self.assertEqual(len(paths), len({str(path) for path in paths}))
        self.assertIn(home / ".config" / "ai-api-local-hub" / "api-config.json", paths)
        self.assertIn(home / ".openai-upstream-hub" / "api-config.json", paths)
        self.assertIn(home / "Library" / "Application Support" / "AI API Local Hub" / "api-config.json", paths)

    def test_first_env_value_returns_first_non_empty_match(self):
        value = first_env_value("A", "B", "C", env={"A": " ", "B": "", "C": "demo"})
        self.assertEqual(value, "demo")

    def test_normalize_local_api_keys_deduplicates_and_ensures_one_enabled_entry(self):
        entries = normalize_local_api_keys(
            [
                {"name": "One", "key": "sk-local-1", "enabled": False},
                {"name": "Duplicate", "key": "sk-local-1", "enabled": True},
                {"name": "Two", "key": "sk-local-2", "enabled": False, "allowed_protocols": ["claude"]},
            ]
        )
        self.assertEqual([item["key"] for item in entries], ["sk-local-1", "sk-local-2"])
        self.assertTrue(entries[0]["enabled"])
        self.assertEqual(entries[1]["allowed_protocols"], ["anthropic"])

    def test_local_key_allows_protocol_supports_protocol_aliases(self):
        entry = {"allowed_protocols": ["claude", "gemini"]}
        self.assertTrue(local_key_allows_protocol(entry, "anthropic"))
        self.assertTrue(local_key_allows_protocol(entry, "claude"))
        self.assertFalse(local_key_allows_protocol(entry, "openai"))

    def test_write_json_can_overwrite_existing_file_when_parent_dir_is_read_only(self):
        with tempfile.TemporaryDirectory() as tempdir:
            parent = Path(tempdir) / "locked"
            parent.mkdir()
            target = parent / "demo.json"
            write_json(target, {"value": 1})
            parent.chmod(0o555)
            try:
                write_json(target, {"value": 2})
            finally:
                parent.chmod(0o755)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["value"], 2)

    def test_service_controller_stop_keeps_dashboard_alive(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "shared",
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            shared_server = mock.Mock()
            shared_thread = mock.Mock()
            shared_server.exposed_protocols = ("openai", "anthropic", "gemini")
            controller.servers = {"shared": shared_server}
            controller.threads = {"shared": shared_thread}

            with mock.patch(
                "router_server.restore_all_clients_from_backup",
                return_value={"codex": {"ok": True}, "claude": {"ok": True}, "gemini": {"ok": True}},
            ):
                stopped = controller.stop()

            self.assertTrue(stopped)
            self.assertIn("shared", controller.servers)
            self.assertEqual(tuple(shared_server.exposed_protocols), ())
            shared_server.shutdown.assert_not_called()
            shared_server.server_close.assert_not_called()
            shared_thread.join.assert_not_called()
            with mock.patch.object(controller, "_reachable_spec_names", return_value=["shared"]):
                snapshot = controller.status_snapshot()
            self.assertEqual(snapshot["state"], "stopped")
            self.assertTrue(snapshot["dashboard_running"])

    def test_service_controller_shutdown_with_only_dashboard_does_not_restore_clients(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "split",
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            dashboard_server = mock.Mock()
            dashboard_thread = mock.Mock()
            controller.servers = {"dashboard": dashboard_server}
            controller.threads = {"dashboard": dashboard_thread}

            with mock.patch("router_server.restore_all_clients_from_backup") as restore_all:
                controller.shutdown()

            restore_all.assert_not_called()
            dashboard_server.shutdown.assert_called_once()
            dashboard_server.server_close.assert_called_once()
            dashboard_thread.join.assert_called_once_with(timeout=2)
            self.assertEqual(controller.servers, {})
            self.assertEqual(controller.threads, {})

    def test_service_controller_can_toggle_shared_mode_protocols(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "shared",
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            dashboard_server = mock.Mock()
            shared_server = mock.Mock()
            dashboard_thread = mock.Mock()
            shared_thread = mock.Mock()
            dashboard_server.server_address = ("127.0.0.1", 8797)
            shared_server.server_address = ("127.0.0.1", 8787)
            shared_server.exposed_protocols = ("openai", "anthropic", "gemini")
            controller.servers = {"dashboard": dashboard_server, "shared": shared_server}
            controller.threads = {"dashboard": dashboard_thread, "shared": shared_thread}

            with mock.patch("router_server.restore_client_from_backup", return_value={"ok": True, "restored": True}) as restore_client:
                stop_result = controller.stop_protocol("anthropic")

            self.assertTrue(stop_result["ok"])
            restore_client.assert_called_once_with("claude")
            self.assertEqual(tuple(shared_server.exposed_protocols), ("openai", "gemini"))
            shared_server.shutdown.assert_not_called()
            with mock.patch.object(controller, "_reachable_spec_names", return_value=["dashboard", "shared"]):
                snapshot = controller.status_snapshot()
            self.assertEqual(snapshot["state"], "partial")
            self.assertEqual(snapshot["active_protocols"], ["openai", "gemini"])

            start_result = controller.start_protocol("anthropic")

            self.assertTrue(start_result["ok"])
            self.assertEqual(tuple(shared_server.exposed_protocols), ("openai", "anthropic", "gemini"))

    def test_service_controller_shared_mode_can_stop_last_protocol(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "shared",
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            dashboard_server = mock.Mock()
            shared_server = mock.Mock()
            dashboard_thread = mock.Mock()
            shared_thread = mock.Mock()
            dashboard_server.server_address = ("127.0.0.1", 8797)
            shared_server.server_address = ("127.0.0.1", 8787)
            shared_server.exposed_protocols = ("openai",)
            controller.servers = {"dashboard": dashboard_server, "shared": shared_server}
            controller.threads = {"dashboard": dashboard_thread, "shared": shared_thread}

            with mock.patch("router_server.restore_client_from_backup", return_value={"ok": True, "restored": True}) as restore_client:
                result = controller.stop_protocol("openai")

            self.assertTrue(result["ok"])
            restore_client.assert_called_once_with("codex")
            self.assertIn("shared", controller.servers)
            self.assertEqual(tuple(shared_server.exposed_protocols), ())
            shared_server.shutdown.assert_not_called()
            shared_server.server_close.assert_not_called()
            shared_thread.join.assert_not_called()

    def test_service_controller_can_rebind_dashboard_port_after_config_save(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            previous_config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "split",
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, previous_config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            dashboard_server = mock.Mock()
            dashboard_thread = mock.Mock()
            dashboard_server.server_address = ("127.0.0.1", 8797)
            controller.servers = {"dashboard": dashboard_server}
            controller.threads = {"dashboard": dashboard_thread}

            next_config = store.get_config()
            next_config["web_ui_port"] = 8807
            store.save_config(next_config)

            plan = controller.preview_runtime_apply(previous_config)
            self.assertTrue(plan["ok"])
            self.assertTrue(plan["apply_required"])
            self.assertEqual(plan["target_names"], ["dashboard"])

            with mock.patch.object(controller, "_start_spec_names", return_value={"ok": True, "started_server_names": ["dashboard"]}) as start_names:
                result = controller._apply_runtime_plan(plan)

            self.assertTrue(result["ok"])
            dashboard_server.shutdown.assert_called_once()
            dashboard_server.server_close.assert_called_once()
            dashboard_thread.join.assert_called_once_with(timeout=2)
            start_names.assert_called_once()
            self.assertEqual(start_names.call_args.args[0], ["dashboard"])

    def test_service_controller_preview_runtime_apply_detects_port_conflict(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            previous_config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "split",
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, previous_config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            dashboard_server = mock.Mock()
            dashboard_server.server_address = ("127.0.0.1", 8797)
            controller.servers = {"dashboard": dashboard_server}

            next_config = store.get_config()
            next_config["web_ui_port"] = 8807
            store.save_config(next_config)

            with mock.patch("ai_proxy_hub.service_controller.find_listening_process", return_value={"pid": 1234, "command": "python3"}):
                result = controller.preview_runtime_apply(previous_config)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "port_in_use")
            self.assertEqual(result["port"], 8807)

    def test_service_controller_runtime_info_prefers_bound_server_layout(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            config_path = tempdir_path / "api-config.json"
            config = normalize_config(
                {
                    "listen_host": "127.0.0.1",
                    "listen_port": 8787,
                    "web_ui_port": 8797,
                    "endpoint_mode": "split",
                    "split_api_ports": {
                        "openai": 8787,
                        "anthropic": 8788,
                        "gemini": 8789,
                        "local_llm": 8790,
                    },
                    "upstreams": [{"name": "Upstream", "base_url": "https://example.com/v1", "api_key": "sk-demo"}],
                }
            )
            write_json(config_path, config)
            store = ConfigStore(config_path)
            controller = ServiceController(config_path, PROJECT_ROOT / "web", store)
            dashboard_server = mock.Mock()
            dashboard_server.server_address = ("127.0.0.1", 8807)
            dashboard_server.protocol_prefixes = {}
            dashboard_server.exposed_protocols = ()
            dashboard_server.dashboard_enabled = True
            openai_server = mock.Mock()
            openai_server.server_address = ("127.0.0.1", 8891)
            openai_server.protocol_prefixes = {"openai": "/v1"}
            openai_server.exposed_protocols = ("openai",)
            openai_server.dashboard_enabled = False
            controller.servers = {"dashboard": dashboard_server, "openai": openai_server}

            runtime = controller.runtime_info()

            self.assertEqual(runtime["endpoint_mode"], "split")
            self.assertEqual(runtime["web_ui_port"], 8807)
            self.assertEqual(runtime["split_api_ports"]["openai"], 8891)
            self.assertEqual(runtime["openai_base_url"], "http://127.0.0.1:8891/v1")
            self.assertEqual(runtime["dashboard_url"], "http://127.0.0.1:8807/")


class SubscriptionRulesTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tempdir.name) / "api-config.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def create_store(self, subscriptions, *, cooldown_seconds=0):
        config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 0,
                "web_ui_port": 0,
                "local_api_key": "sk-local-test",
                "request_timeout_sec": 5,
                "cooldown_seconds": cooldown_seconds,
                "upstreams": [
                    {
                        "id": "upstream-subscriptions",
                        "name": "订阅上游",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-upstream",
                        "subscriptions": subscriptions,
                    }
                ],
            }
        )
        write_json(self.config_path, config)
        return ConfigStore(self.config_path)

    def summary_at(self, store, when):
        with store.lock:
            upstream = store._find_upstream_locked("upstream-subscriptions")
            self.assertIsNotNone(upstream)
            return store._upstream_subscription_summary_locked(upstream, now_ts=when.timestamp())

    def test_legacy_upstream_config_gets_default_subscription(self):
        config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 8787,
                "upstreams": [
                    {
                        "name": "Legacy Upstream",
                        "base_url": "https://example.com/v1",
                        "api_key": "sk-legacy",
                    }
                ],
            }
        )
        subscriptions = config["upstreams"][0]["subscriptions"]
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["kind"], "unlimited")
        self.assertTrue(subscriptions[0]["permanent"])
        self.assertTrue(subscriptions[0]["enabled"])

    def test_expired_subscription_is_effectively_disabled_while_preserving_expired_state(self):
        store = self.create_store(
            [
                {
                    "id": "sub-expired",
                    "name": "Expired Subscription",
                    "kind": "periodic",
                    "enabled": True,
                    "permanent": False,
                    "expires_at": "2026-04-09",
                    "reset_times": ["09:30"],
                },
            ]
        )
        expired_now = local_datetime(2026, 4, 9, 13, 0, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=expired_now))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=expired_now))
            summary = self.summary_at(store, expired_now)
        self.assertEqual(summary["state"], "expired")
        self.assertEqual(summary["subscriptions"][0]["state"], "expired")
        self.assertTrue(summary["subscriptions"][0]["enabled"])
        self.assertFalse(summary["subscriptions"][0]["effective_enabled"])

    def test_periodic_subscription_requires_probe_after_later_reset_window(self):
        store = self.create_store(
            [
                {
                    "id": "sub-periodic",
                    "name": "Split Reset",
                    "kind": "periodic",
                    "reset_times": ["09:00", "21:00"],
                    "failure_mode": "consecutive_failures",
                    "failure_threshold": 1,
                },
            ]
        )

        exhausted_at = local_datetime(2026, 4, 8, 10, 30, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=exhausted_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=exhausted_at))
            store.record_failure("upstream-subscriptions", status=429, error="insufficient_quota", cooldown=True)

        waiting_summary = self.summary_at(store, local_datetime(2026, 4, 8, 15, 0, 0))
        self.assertEqual(waiting_summary["state"], "temporary_exhausted")
        self.assertFalse(waiting_summary["available"])
        self.assertEqual(waiting_summary["next_reset_at"], "2026-04-08T21:00:00")

        recovered_summary = self.summary_at(store, local_datetime(2026, 4, 8, 21, 30, 0))
        self.assertEqual(recovered_summary["state"], "temporary_exhausted")
        self.assertFalse(recovered_summary["available"])
        self.assertEqual(recovered_summary["current_subscription_id"], "")

        store.record_periodic_probe_success("upstream-subscriptions", "sub-periodic", status=200, latency_ms=188.0, models_count=5)
        probed_summary = self.summary_at(store, local_datetime(2026, 4, 8, 21, 30, 0))
        self.assertEqual(probed_summary["state"], "ready")
        self.assertTrue(probed_summary["available"])
        self.assertEqual(probed_summary["current_subscription_id"], "sub-periodic")
        self.assertEqual(probed_summary["current_subscription_name"], "Split Reset")

    def test_periodic_subscription_network_timeout_does_not_enter_waiting_reset(self):
        store = self.create_store(
            [
                {
                    "id": "sub-periodic",
                    "name": "Split Reset",
                    "kind": "periodic",
                    "reset_times": ["09:00", "21:00"],
                    "failure_mode": "consecutive_failures",
                    "failure_threshold": 1,
                },
            ],
            cooldown_seconds=30,
        )

        failed_at = local_datetime(2026, 4, 8, 10, 30, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=failed_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=failed_at))
            store.record_failure("upstream-subscriptions", status=None, error="timed out", cooldown=True)

        summary = self.summary_at(store, local_datetime(2026, 4, 8, 15, 0, 0))
        self.assertEqual(summary["state"], "ready")
        self.assertTrue(summary["available"])
        self.assertEqual(summary["next_reset_at"], "")
        self.assertEqual(summary["subscriptions"][0]["state"], "ready")
        self.assertFalse(summary["subscriptions"][0]["exhausted"])

    def test_success_clears_temporary_exhausted_periodic_subscription(self):
        store = self.create_store(
            [
                {
                    "id": "sub-periodic",
                    "name": "Split Reset",
                    "kind": "periodic",
                    "reset_times": ["09:00", "21:00"],
                    "failure_mode": "consecutive_failures",
                    "failure_threshold": 1,
                },
            ]
        )

        exhausted_at = local_datetime(2026, 4, 8, 10, 30, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=exhausted_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=exhausted_at))
            store.record_failure("upstream-subscriptions", status=429, error="insufficient_quota", cooldown=True)

        waiting_summary = self.summary_at(store, local_datetime(2026, 4, 8, 15, 0, 0))
        self.assertEqual(waiting_summary["state"], "temporary_exhausted")
        self.assertFalse(waiting_summary["available"])

        success_at = local_datetime(2026, 4, 8, 15, 5, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=success_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=success_at))
            store.record_success("upstream-subscriptions", 200, 188.0)

        recovered_summary = self.summary_at(store, success_at)
        self.assertEqual(recovered_summary["state"], "ready")
        self.assertTrue(recovered_summary["available"])
        self.assertEqual(recovered_summary["current_subscription_id"], "sub-periodic")
        self.assertEqual(recovered_summary["subscriptions"][0]["state"], "ready")

    def test_periodic_subscription_stays_active_before_first_reset_of_day(self):
        store = self.create_store(
            [
                {
                    "id": "sub-periodic",
                    "name": "Day Split Reset",
                    "kind": "periodic",
                    "reset_times": ["09:00", "21:00"],
                    "failure_mode": "consecutive_failures",
                    "failure_threshold": 1,
                }
            ]
        )

        early_summary = self.summary_at(store, local_datetime(2026, 4, 8, 8, 0, 0))
        self.assertEqual(early_summary["state"], "ready")
        self.assertTrue(early_summary["available"])
        self.assertEqual(early_summary["current_subscription_id"], "sub-periodic")

        midday_summary = self.summary_at(store, local_datetime(2026, 4, 8, 12, 0, 0))
        self.assertEqual(midday_summary["state"], "ready")
        self.assertTrue(midday_summary["available"])

    def test_periodic_subscription_expires_at_refresh_time_instead_of_waiting_next_day(self):
        store = self.create_store(
            [
                {
                    "id": "sub-periodic-expiring",
                    "name": "Morning Reset Window",
                    "kind": "periodic",
                    "permanent": False,
                    "expires_at": "2026-04-09",
                    "reset_times": ["09:30"],
                    "failure_mode": "consecutive_failures",
                    "failure_threshold": 1,
                }
            ]
        )

        before_expiry = self.summary_at(store, local_datetime(2026, 4, 9, 9, 29, 0))
        self.assertEqual(before_expiry["state"], "ready")
        self.assertTrue(before_expiry["available"])
        self.assertEqual(before_expiry["current_subscription_id"], "sub-periodic-expiring")

        with ExitStack() as stack:
            failed_at = local_datetime(2026, 4, 9, 9, 0, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=failed_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=failed_at))
            store.record_failure("upstream-subscriptions", status=429, error="insufficient_quota", cooldown=True)

        after_expiry = self.summary_at(store, local_datetime(2026, 4, 9, 9, 31, 0))
        self.assertEqual(after_expiry["state"], "expired")
        self.assertTrue(after_expiry["manual_enable_required"])
        self.assertFalse(after_expiry["available"])
        self.assertEqual(after_expiry["current_subscription_id"], "")
        self.assertEqual(after_expiry["next_reset_at"], "")

        with ExitStack() as stack:
            after_expiry_time = local_datetime(2026, 4, 9, 9, 31, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=after_expiry_time))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=after_expiry_time))
            plan = store.get_request_plan(protocol="openai", for_models=False, advance_round_robin=False)
        self.assertEqual(plan["upstreams"], [])

    def test_priority_routing_returns_to_primary_upstream_after_periodic_probe_success(self):
        config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 0,
                "web_ui_port": 0,
                "local_api_key": "sk-local-test",
                "request_timeout_sec": 5,
                "cooldown_seconds": 0,
                "upstreams": [
                    {
                        "id": "primary-periodic",
                        "name": "Primary Periodic",
                        "base_url": "https://primary.example/v1",
                        "api_key": "sk-primary",
                        "subscriptions": [
                            {
                                "id": "sub-primary",
                                "name": "Day Split Reset",
                                "kind": "periodic",
                                "reset_times": ["09:00", "21:00"],
                                "failure_mode": "consecutive_failures",
                                "failure_threshold": 1,
                            }
                        ],
                    },
                    {
                        "id": "fallback-unlimited",
                        "name": "Fallback Unlimited",
                        "base_url": "https://fallback.example/v1",
                        "api_key": "sk-fallback",
                        "subscriptions": [
                            {
                                "id": "sub-fallback",
                                "name": "Fallback Unlimited",
                                "kind": "unlimited",
                            }
                        ],
                    },
                ],
            }
        )
        write_json(self.config_path, config)
        store = ConfigStore(self.config_path)

        with ExitStack() as stack:
            exhausted_at = local_datetime(2026, 4, 8, 10, 30, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=exhausted_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=exhausted_at))
            store.record_failure("primary-periodic", status=429, error="insufficient_quota", cooldown=True)

        with ExitStack() as stack:
            waiting_at = local_datetime(2026, 4, 8, 15, 0, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=waiting_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=waiting_at))
            waiting_plan = store.get_request_plan(protocol="openai", for_models=False, advance_round_robin=False)
        self.assertEqual([item["id"] for item in waiting_plan["upstreams"]], ["fallback-unlimited"])

        with ExitStack() as stack:
            recovered_at = local_datetime(2026, 4, 8, 21, 30, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=recovered_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=recovered_at))
            recovered_plan_before_probe = store.get_request_plan(protocol="openai", for_models=False, advance_round_robin=False)
        self.assertEqual([item["id"] for item in recovered_plan_before_probe["upstreams"]], ["fallback-unlimited"])

        store.record_periodic_probe_success("primary-periodic", "sub-primary", status=200, latency_ms=120.0, models_count=4)

        with ExitStack() as stack:
            recovered_at = local_datetime(2026, 4, 8, 21, 30, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=recovered_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=recovered_at))
            recovered_plan = store.get_request_plan(protocol="openai", for_models=False, advance_round_robin=False)
        self.assertEqual([item["id"] for item in recovered_plan["upstreams"]], ["primary-periodic", "fallback-unlimited"])

    def test_manual_routing_ignores_periodic_auto_recovery_and_keeps_selected_upstream(self):
        config = normalize_config(
            {
                "listen_host": "127.0.0.1",
                "listen_port": 0,
                "web_ui_port": 0,
                "local_api_key": "sk-local-test",
                "request_timeout_sec": 5,
                "cooldown_seconds": 0,
                "auto_routing_enabled": False,
                "manual_active_upstream_id": "primary-periodic",
                "upstreams": [
                    {
                        "id": "primary-periodic",
                        "name": "Primary Periodic",
                        "base_url": "https://primary.example/v1",
                        "api_key": "sk-primary",
                        "subscriptions": [
                            {
                                "id": "sub-primary",
                                "name": "Day Split Reset",
                                "kind": "periodic",
                                "reset_times": ["09:00", "21:00"],
                                "failure_mode": "consecutive_failures",
                                "failure_threshold": 1,
                            }
                        ],
                    },
                    {
                        "id": "fallback-unlimited",
                        "name": "Fallback Unlimited",
                        "base_url": "https://fallback.example/v1",
                        "api_key": "sk-fallback",
                        "subscriptions": [
                            {
                                "id": "sub-fallback",
                                "name": "Fallback Unlimited",
                                "kind": "unlimited",
                            }
                        ],
                    },
                ],
            }
        )
        write_json(self.config_path, config)
        store = ConfigStore(self.config_path)

        with ExitStack() as stack:
            exhausted_at = local_datetime(2026, 4, 8, 10, 30, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=exhausted_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=exhausted_at))
            store.record_failure("primary-periodic", status=429, error="insufficient_quota", cooldown=True)

        with ExitStack() as stack:
            waiting_at = local_datetime(2026, 4, 8, 21, 30, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=waiting_at))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=waiting_at))
            waiting_plan = store.get_request_plan(protocol="openai", for_models=False, advance_round_robin=False)
            probe_candidates = store.get_periodic_probe_candidates(protocol="openai")

        self.assertEqual([item["id"] for item in waiting_plan["upstreams"]], ["primary-periodic"])
        self.assertEqual(probe_candidates, [])

    def test_quota_subscription_exhaustion_requires_manual_reactivation(self):
        store = self.create_store(
            [
                {
                    "id": "sub-quota",
                    "name": "Emergency Quota",
                    "kind": "quota",
                    "failure_mode": "consecutive_days",
                    "failure_threshold": 2,
                }
            ]
        )

        day_one = local_datetime(2026, 4, 8, 11, 0, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=day_one))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=day_one))
            store.record_failure("upstream-subscriptions", status=429, error="insufficient_quota", cooldown=True)

        first_day_summary = self.summary_at(store, local_datetime(2026, 4, 8, 12, 0, 0))
        self.assertEqual(first_day_summary["state"], "ready")
        self.assertTrue(first_day_summary["available"])

        day_two = local_datetime(2026, 4, 9, 11, 0, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=day_two))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=day_two))
            store.record_failure("upstream-subscriptions", status=429, error="insufficient_quota", cooldown=True)

        exhausted_summary = self.summary_at(store, local_datetime(2026, 4, 9, 12, 0, 0))
        self.assertEqual(exhausted_summary["state"], "quota_exhausted")
        self.assertFalse(exhausted_summary["available"])

        with ExitStack() as stack:
            at_noon = local_datetime(2026, 4, 9, 12, 0, 0)
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=at_noon))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=at_noon))
            plan = store.get_request_plan(protocol="openai", for_models=False, advance_round_robin=False)
        self.assertEqual(plan["upstreams"], [])

        reactivate_result = store.reactivate_upstream("upstream-subscriptions")
        self.assertTrue(reactivate_result["ok"])

        reactivated_summary = self.summary_at(store, local_datetime(2026, 4, 9, 12, 30, 0))
        self.assertEqual(reactivated_summary["state"], "ready")
        self.assertTrue(reactivated_summary["available"])
        self.assertEqual(reactivated_summary["current_subscription_id"], "sub-quota")

    def test_expired_subscription_stays_manual_locked_until_reactivated(self):
        store = self.create_store(
            [
                {
                    "id": "sub-expiring",
                    "name": "Monthly Pass",
                    "kind": "unlimited",
                    "permanent": False,
                    "expires_at": "2026-04-08",
                }
            ]
        )

        expired_summary = self.summary_at(store, local_datetime(2026, 4, 9, 9, 0, 0))
        self.assertEqual(expired_summary["state"], "expired")
        self.assertTrue(expired_summary["manual_enable_required"])
        self.assertFalse(expired_summary["available"])

        config = store.get_config()
        config["upstreams"][0]["subscriptions"][0]["expires_at"] = "2026-04-30"
        config["upstreams"][0]["subscriptions"][0]["permanent"] = False
        store.save_config(config)

        renewed_summary = self.summary_at(store, local_datetime(2026, 4, 10, 9, 0, 0))
        self.assertEqual(renewed_summary["state"], "manual_lock")
        self.assertTrue(renewed_summary["manual_enable_required"])
        self.assertFalse(renewed_summary["available"])
        self.assertEqual(renewed_summary["current_subscription_id"], "sub-expiring")

        reactivate_result = store.reactivate_upstream("upstream-subscriptions")
        self.assertTrue(reactivate_result["ok"])

        active_summary = self.summary_at(store, local_datetime(2026, 4, 10, 9, 5, 0))
        self.assertEqual(active_summary["state"], "ready")
        self.assertTrue(active_summary["available"])

    def test_upstream_control_endpoint_reactivates_frozen_subscription_state(self):
        store = self.create_store(
            [
                {
                    "id": "sub-api",
                    "name": "Quota Reset",
                    "kind": "quota",
                    "failure_mode": "consecutive_failures",
                    "failure_threshold": 1,
                }
            ]
        )
        failure_time = local_datetime(2026, 4, 8, 14, 0, 0)
        with ExitStack() as stack:
            stack.enter_context(mock.patch("ai_proxy_hub.store.current_local_datetime", return_value=failure_time))
            stack.enter_context(mock.patch("ai_proxy_hub.subscriptions.current_local_datetime", return_value=failure_time))
            store.record_failure("upstream-subscriptions", status=429, error="insufficient_quota", cooldown=True)

        proxy = create_server(self.config_path, PROJECT_ROOT / "web", "127.0.0.1", 0)
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        self.addCleanup(proxy.shutdown)
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy_thread.join, 1)

        status, payload = make_request(
            f"http://127.0.0.1:{proxy.server_address[1]}/api/upstream/control",
            method="POST",
            data={"id": "upstream-subscriptions", "action": "reactivate"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"]["message"], "reactivated")
        self.assertTrue(payload["status"]["upstreams"][0]["subscription_available"])
        self.assertEqual(payload["status"]["upstreams"][0]["current_subscription_id"], "sub-api")


if __name__ == "__main__":
    unittest.main()

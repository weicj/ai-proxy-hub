import sys
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import cli_modern  # noqa: E402


class _DummyStatus:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConsole:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append(("clear", None))

    def print(self, value="", **kwargs):
        if kwargs:
            self.calls.append(("print", value, kwargs))
        else:
            self.calls.append(("print", value))

    def status(self, value, spinner="dots"):
        self.calls.append(("status", value, spinner))
        return _DummyStatus()


class FakeService:
    def runtime_info(self):
        return {"dashboard_url": "http://127.0.0.1:8820/"}


class FakeStore:
    def get_config(self):
        return {}


class FakeApp:
    config_path = Path("/tmp/api-config.json")

    def __init__(self):
        self.service = FakeService()
        self.store = FakeStore()

    def get_runtime_snapshot(self):
        return {
            "service": {"state": "stopped"},
            "clients": {
                "codex": {"state": "not_switched"},
                "claude": {"state": "not_switched"},
                "gemini": {"state": "not_switched"},
            },
            "routing": {
                "protocols": {
                    "openai": {"upstream_count": 1},
                    "anthropic": {"upstream_count": 2},
                    "gemini": {"upstream_count": 3},
                    "local_llm": {"upstream_count": 4},
                }
            },
        }

    def language(self):
        return "en"

    def tr(self, key, **vars):
        text = str(key)
        for name, value in vars.items():
            text = text.replace(f"{{{name}}}", str(value))
        return text

    def routing_strategy_label(self, strategy):
        return strategy

    def protocol_console_label(self, protocol):
        return protocol

    def cli_theme_mode(self):
        return "auto"

    def supports_single_key_choice(self):
        return False

    def read_single_key(self, default="0"):
        return default


@unittest.skipUnless(cli_modern.RICH_AVAILABLE, "rich is required for ModernCLI tests")
class ModernCLITest(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.cli = cli_modern.ModernCLI(self.app)
        self.console = FakeConsole()
        self.cli.console = self.console

    def test_page_info_is_rendered_after_menu_panel(self):
        self.cli.print_header()
        header_call_count = len(self.console.calls)

        self.cli.info("Local API: sk-local-demo")
        self.assertEqual(len(self.console.calls), header_call_count)

        self.cli.print_menu(["1. Start", "0. Exit"])
        new_calls = self.console.calls[header_call_count:]
        self.assertEqual(len(new_calls), 1)
        self.assertEqual(new_calls[0][0], "print")
        self.assertEqual(type(new_calls[0][1]).__name__, "Panel")

    def test_buffered_spacer_is_rendered_after_menu_panel(self):
        self.cli.print_header()
        header_call_count = len(self.console.calls)

        self.cli.blank_line()
        self.cli.info("Local API: sk-local-demo")
        self.assertEqual(len(self.console.calls), header_call_count)

        self.cli.print_menu(["1. Start", "0. Exit"])
        new_calls = self.console.calls[header_call_count:]
        self.assertEqual(len(new_calls), 1)
        self.assertEqual(type(new_calls[0][1]).__name__, "Panel")

    def test_prompt_flushes_buffered_page_info_without_menu(self):
        self.cli.print_header()
        header_call_count = len(self.console.calls)

        self.cli.info("Local API: sk-local-demo")
        with mock.patch.object(self.app, "supports_single_key_choice", return_value=False):
            with mock.patch.object(cli_modern.Prompt, "ask", return_value="0"):
                result = self.cli.prompt_choice()

        self.assertEqual(result, "0")
        new_calls = self.console.calls[header_call_count:]
        self.assertEqual(new_calls, [("print", "[cyan]ℹ[/cyan] Local API: sk-local-demo")])

    def test_prompt_choice_uses_single_key_mode_when_supported(self):
        with mock.patch.object(self.app, "supports_single_key_choice", return_value=True):
            with mock.patch.object(self.app, "read_single_key", return_value="3") as read_single_key:
                result = self.cli.prompt_choice()

        self.assertEqual(result, "3")
        read_single_key.assert_called_once_with(default="0")
        self.assertEqual(self.console.calls[-2], ("print", "[bold cyan]prompt[/bold cyan] ", {"end": ""}))
        self.assertEqual(self.console.calls[-1], ("print", "[bold cyan]3[/bold cyan]"))

    def test_menu_prompt_is_shown_before_buffered_info(self):
        self.cli.print_header()
        header_call_count = len(self.console.calls)
        self.cli.info("Local API: sk-local-demo")
        self.cli.print_menu(["1. Start", "0. Exit"])

        with mock.patch.object(self.app, "supports_single_key_choice", return_value=True):
            with mock.patch.object(self.app, "read_single_key", return_value="1"):
                result = self.cli.prompt_choice()

        self.assertEqual(result, "1")
        new_calls = self.console.calls[header_call_count:]
        self.assertEqual(type(new_calls[0][1]).__name__, "Panel")
        self.assertEqual(new_calls[1], ("print", "[bold cyan]prompt[/bold cyan] ", {"end": ""}))
        self.assertEqual(new_calls[2], ("print", "[bold cyan]1[/bold cyan]"))
        self.assertEqual(new_calls[3], ("print", "[cyan]ℹ[/cyan] Local API: sk-local-demo"))

    def test_priority_menu_item_renders_single_panel_with_highlighted_primary_item(self):
        self.cli.print_menu(["1. ★ Open Web dashboard", "2. Global runtime", "0. Exit"])

        self.assertEqual(type(self.console.calls[0][1]).__name__, "Panel")
        self.assertEqual(len(self.console.calls), 1)


if __name__ == "__main__":
    unittest.main()

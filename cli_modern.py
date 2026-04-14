#!/usr/bin/env python3
"""Modern CLI interface with Rich library styling - Claude Code inspired."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ai_proxy_hub.cli import InteractiveConsoleApp

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


CLI_THEME_PALETTES = {
    "auto": {
        "brand_border": "bright_cyan",
        "brand_title": "bold white",
        "brand_subtitle": "dim",
        "brand_meta": "grey70",
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "status_label": "cyan",
        "status_value": "white",
        "status_title": "bold cyan",
        "status_border": "cyan",
        "menu_title": "bold yellow",
        "menu_border": "yellow",
        "menu_badge": "bold black on cyan",
        "menu_primary_badge": "bold black on yellow",
        "menu_text": "white",
        "menu_primary_text": "bold yellow",
        "prompt": "bold cyan",
    },
    "dark": {
        "brand_border": "bright_cyan",
        "brand_title": "bold white",
        "brand_subtitle": "grey70",
        "brand_meta": "grey58",
        "info": "bright_cyan",
        "success": "bright_green",
        "warning": "bright_yellow",
        "error": "bright_red",
        "status_label": "bright_cyan",
        "status_value": "white",
        "status_title": "bold bright_cyan",
        "status_border": "bright_cyan",
        "menu_title": "bold bright_yellow",
        "menu_border": "bright_yellow",
        "menu_badge": "bold black on bright_cyan",
        "menu_primary_badge": "bold black on bright_yellow",
        "menu_text": "white",
        "menu_primary_text": "bold bright_yellow",
        "prompt": "bold bright_cyan",
    },
    "light": {
        "brand_border": "blue",
        "brand_title": "bold black",
        "brand_subtitle": "grey50",
        "brand_meta": "grey42",
        "info": "blue",
        "success": "green",
        "warning": "dark_orange",
        "error": "red",
        "status_label": "blue",
        "status_value": "black",
        "status_title": "bold blue",
        "status_border": "blue",
        "menu_title": "bold blue",
        "menu_border": "blue",
        "menu_badge": "bold white on blue",
        "menu_primary_badge": "bold white on dark_orange",
        "menu_text": "black",
        "menu_primary_text": "bold dark_orange",
        "prompt": "bold blue",
    },
    "blue": {
        "brand_border": "bright_blue",
        "brand_title": "bold white",
        "brand_subtitle": "bright_black",
        "brand_meta": "grey70",
        "info": "bright_blue",
        "success": "green",
        "warning": "bright_yellow",
        "error": "bright_red",
        "status_label": "bright_blue",
        "status_value": "white",
        "status_title": "bold bright_blue",
        "status_border": "bright_blue",
        "menu_title": "bold bright_blue",
        "menu_border": "bright_blue",
        "menu_badge": "bold white on blue",
        "menu_primary_badge": "bold white on bright_blue",
        "menu_text": "white",
        "menu_primary_text": "bold bright_blue",
        "prompt": "bold bright_blue",
    },
    "green": {
        "brand_border": "green",
        "brand_title": "bold white",
        "brand_subtitle": "grey70",
        "brand_meta": "grey70",
        "info": "green",
        "success": "bright_green",
        "warning": "yellow",
        "error": "red",
        "status_label": "green",
        "status_value": "white",
        "status_title": "bold green",
        "status_border": "green",
        "menu_title": "bold green",
        "menu_border": "green",
        "menu_badge": "bold black on green",
        "menu_primary_badge": "bold black on bright_green",
        "menu_text": "white",
        "menu_primary_text": "bold bright_green",
        "prompt": "bold green",
    },
    "amber": {
        "brand_border": "dark_orange",
        "brand_title": "bold white",
        "brand_subtitle": "grey70",
        "brand_meta": "grey70",
        "info": "dark_orange",
        "success": "green",
        "warning": "bright_yellow",
        "error": "red",
        "status_label": "dark_orange",
        "status_value": "white",
        "status_title": "bold dark_orange",
        "status_border": "dark_orange",
        "menu_title": "bold dark_orange",
        "menu_border": "dark_orange",
        "menu_badge": "bold black on dark_orange",
        "menu_primary_badge": "bold black on yellow",
        "menu_text": "white",
        "menu_primary_text": "bold yellow",
        "prompt": "bold dark_orange",
    },
    "rose": {
        "brand_border": "magenta",
        "brand_title": "bold white",
        "brand_subtitle": "grey70",
        "brand_meta": "grey70",
        "info": "magenta",
        "success": "green",
        "warning": "yellow",
        "error": "bright_red",
        "status_label": "magenta",
        "status_value": "white",
        "status_title": "bold magenta",
        "status_border": "magenta",
        "menu_title": "bold magenta",
        "menu_border": "magenta",
        "menu_badge": "bold white on magenta",
        "menu_primary_badge": "bold white on bright_magenta",
        "menu_text": "white",
        "menu_primary_text": "bold bright_magenta",
        "prompt": "bold magenta",
    },
    "teal": {
        "brand_border": "bright_cyan",
        "brand_title": "bold white",
        "brand_subtitle": "grey70",
        "brand_meta": "grey70",
        "info": "bright_cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "status_label": "bright_cyan",
        "status_value": "white",
        "status_title": "bold bright_cyan",
        "status_border": "bright_cyan",
        "menu_title": "bold bright_cyan",
        "menu_border": "bright_cyan",
        "menu_badge": "bold black on bright_cyan",
        "menu_primary_badge": "bold black on cyan",
        "menu_text": "white",
        "menu_primary_text": "bold bright_cyan",
        "prompt": "bold bright_cyan",
    },
}


class ModernCLI:
    """Modern CLI wrapper with Rich styling."""

    def __init__(self, app: 'InteractiveConsoleApp'):
        self.app = app
        self.console = Console() if RICH_AVAILABLE else None
        self._defer_page_info = False
        self._page_menu_rendered = False
        self._buffered_info: List[Optional[str]] = []
        self._menu_prompt_pending = False

    @staticmethod
    def is_available() -> bool:
        """Check if Rich is available."""
        return RICH_AVAILABLE

    def clear(self) -> None:
        """Clear screen."""
        if self.console:
            self.console.clear()
        else:
            self.app.clear_screen()

    def _reset_page_flow(self) -> None:
        self._defer_page_info = False
        self._page_menu_rendered = False
        self._buffered_info = []
        self._menu_prompt_pending = False

    def _start_page_info_buffering(self) -> None:
        self._defer_page_info = True
        self._page_menu_rendered = False
        self._buffered_info = []

    def _print_info_now(self, message: str) -> None:
        if self.console:
            palette = self._palette()
            self.console.print(f"[{palette['info']}]ℹ[/{palette['info']}] {message}")

    def _theme_mode(self) -> str:
        getter = getattr(self.app, "cli_theme_mode", None)
        if callable(getter):
            try:
                return str(getter() or "auto")
            except Exception:
                return "auto"
        return "auto"

    def _palette(self) -> Dict[str, str]:
        return CLI_THEME_PALETTES.get(self._theme_mode(), CLI_THEME_PALETTES["auto"])

    def _terminal_width(self) -> int:
        if not self.console:
            return self.app.terminal_width()
        try:
            return max(40, int(self.console.size.width))
        except Exception:
            return 80

    def _build_brand_panel(self) -> Panel:
        palette = self._palette()
        width = self._terminal_width()
        center = width >= 72
        justify = "center" if center else "left"
        title = Text("AI Proxy Hub", style=palette["brand_title"], justify=justify)
        subtitle = Text(
            "Codex · Claude · Gemini local control hub"
            if self.app.language() == "en"
            else "Codex · Claude · Gemini 本地控制中心",
            style=palette["brand_subtitle"],
            justify=justify,
        )
        lines = [title, subtitle]
        meta_lines_getter = getattr(self.app, "project_meta_lines", None)
        if callable(meta_lines_getter):
            for item in meta_lines_getter():
                lines.append(Text(str(item), style=palette["brand_meta"], justify=justify))
        return Panel(
            Group(*lines),
            border_style=palette["brand_border"],
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _build_status_rows(self, snapshot: Dict[str, Any], runtime: Dict[str, Any]) -> List[tuple[str, str]]:
        service_info = snapshot.get("service", {})
        service_state = str(service_info.get("state") or self.app.service.status_state())
        service_label_getter = getattr(self.app, "service_status_short_label", None)
        service_label = service_label_getter(service_state) if callable(service_label_getter) else service_state
        status_icons = {
            "running": "🟢",
            "partial": "🟡",
            "external": "🟡",
            "error": "🔴",
            "stopped": "⚪",
        }
        icon = status_icons.get(service_state, "⚪")
        rows: List[tuple[str, str]] = []
        rows.append(
            (
                "服务" if self.app.language() == "zh" else "Service",
                f"{icon} {service_label}",
            )
        )
        runtime_source_getter = getattr(self.app, "runtime_source_summary", None)
        if callable(runtime_source_getter):
            source = runtime_source_getter(snapshot)
        else:
            source = {
                "label": self.app.tr("config_path"),
                "value": str(getattr(self.app, "config_path", "-")),
            }
        rows.append((str(source["label"]), str(source["value"])))
        rows.append((self.app.tr("dashboard_url"), str(runtime.get("dashboard_url") or "-")))
        runtime_apply_status = {"enabled": False, "labels": []}
        runtime_apply_getter = getattr(self.app, "runtime_apply_status", None)
        if callable(runtime_apply_getter):
            try:
                runtime_apply_status = runtime_apply_getter(snapshot)
            except Exception:
                runtime_apply_status = {"enabled": False, "labels": []}
        if runtime_apply_status.get("enabled"):
            labels = runtime_apply_status.get("labels") or []
            rows.append(
                (
                    self.app.tr("apply_pending_label"),
                    ", ".join(str(label) for label in labels) if labels else self.app.tr("apply_pending_short"),
                )
            )

        active_protocols = [
            self._routing_protocol_label(protocol)
            for protocol in (service_info.get("active_protocols") or [])
            if protocol in {"openai", "anthropic", "gemini", "local_llm"}
        ]
        if active_protocols:
            rows.append(
                (
                    "已启动" if self.app.language() == "zh" else "Active",
                    ", ".join(active_protocols),
                )
            )

        clients = snapshot.get("clients", {})
        for client_id in ("codex", "claude", "gemini"):
            info = clients.get(client_id, {})
            client_name = self._get_client_name(client_id)
            status = self._format_client_status(info)
            rows.append((client_name, status))

        routing_protocols = snapshot.get("routing", {}).get("protocols", {})
        routing_from_snapshot = getattr(self.app, "routing_strategy_from_snapshot", None)
        for protocol in ("openai", "anthropic", "gemini", "local_llm"):
            proto_info = routing_protocols.get(protocol, {})
            count = proto_info.get("upstream_count", 0)
            if callable(routing_from_snapshot):
                strategy = routing_from_snapshot(snapshot, protocol)
            else:
                strategy = self.app.routing_strategy_label(str(proto_info.get("routing_mode") or "priority"))
            count_label = (
                f"{count} 个上游"
                if self.app.language() == "zh"
                else f"{count} upstreams"
            )
            rows.append((self._routing_protocol_label(protocol), f"{count_label} · {strategy}"))
        return rows

    def _build_status_panel(self, rows: List[tuple[str, str]]) -> Panel:
        palette = self._palette()
        width = self._terminal_width()
        if width < 76:
            content = Text()
            for index, (label, value) in enumerate(rows):
                if index:
                    content.append("\n\n")
                content.append(f"{label}\n", style=palette["status_title"])
                content.append(str(value), style=palette["status_value"])
        else:
            key_width = min(16, max(10, width // 6))
            table = Table.grid(expand=True, padding=(0, 1))
            table.add_column(style=palette["status_label"], width=key_width, no_wrap=True)
            table.add_column(style=palette["status_value"], ratio=1, overflow="fold")
            for label, value in rows:
                table.add_row(label, str(value))
            content = table
        return Panel(
            content,
            title=(
                f"[{palette['status_title']}]系统状态[/{palette['status_title']}]"
                if self.app.language() == "zh"
                else f"[{palette['status_title']}]System Status[/{palette['status_title']}]"
            ),
            border_style=palette["status_border"],
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _build_menu_text(
        self,
        items: List[tuple[str, str]],
        *,
        badge_style: str,
        text_style: str,
        hint: Optional[str] = None,
    ) -> Text:
        body = Text()
        for index, (num, desc) in enumerate(items):
            if index:
                body.append("\n")
            body.append(f" {num} ", style=badge_style)
            body.append(" ")
            body.append(desc, style=text_style)
        if hint:
            body.append("\n")
            body.append(hint, style="dim")
        return body

    def _flush_buffered_info(self) -> None:
        if not self.console:
            return
        if not self._buffered_info:
            self._defer_page_info = False
            return
        buffered = list(self._buffered_info)
        self._buffered_info.clear()
        self._defer_page_info = False
        for message in buffered:
            if message is None:
                self.console.print()
            else:
                self._print_info_now(message)

    def print_header(self) -> None:
        """Print modern header with status."""
        if not self.console:
            self.app.print_header()
            return

        self._reset_page_flow()
        self.clear()

        self.console.print(self._build_brand_panel())
        self.console.print()

        snapshot = self.app.get_runtime_snapshot()
        runtime = self.app.service.runtime_info()
        self.console.print(self._build_status_panel(self._build_status_rows(snapshot, runtime)))
        self.console.print()
        consume_notices = getattr(self.app, "consume_notices", None)
        notices = consume_notices() if callable(consume_notices) else []
        palette = self._palette()
        for notice in notices:
            kind = str(notice.get("kind") or "info")
            message = str(notice.get("message") or "")
            if kind == "success":
                self.console.print(f"[{palette['success']}]✓[/{palette['success']}] {message}")
            elif kind == "error":
                self.console.print(f"[{palette['error']}]✗[/{palette['error']}] {message}")
            elif kind == "warning":
                self.console.print(f"[{palette['warning']}]⚠[/{palette['warning']}] {message}")
            else:
                self.console.print(f"[{palette['info']}]ℹ[/{palette['info']}] {message}")
        self._start_page_info_buffering()

    def _get_client_name(self, client_id: str) -> str:
        """Get display name for client."""
        from ai_proxy_hub import client_display_name
        return client_display_name(client_id)

    def _routing_protocol_label(self, protocol: str) -> str:
        if protocol == "openai":
            return "Codex"
        if protocol == "anthropic":
            return "Claude"
        if protocol == "gemini":
            return "Gemini"
        return "Local LLM" if self.app.language() == "en" else "本地 LLM"

    def _format_client_status(self, info: Dict[str, Any]) -> str:
        """Format client status with color."""
        state = info.get("state", "unknown")

        if state == "switched":
            return "🟢 已接入 Hub" if self.app.language() == "zh" else "🟢 Connected to Hub"
        if state == "external":
            return "🟡 外部 Hub" if self.app.language() == "zh" else "🟡 External Hub"
        if state == "not_switched":
            return "⚪ 未接入" if self.app.language() == "zh" else "⚪ Not configured"
        return "🔴 异常" if self.app.language() == "zh" else "🔴 Error"

    def print_menu(self, options: List[str]) -> None:
        """Print menu options."""
        if not self.console:
            self.app.print_menu_lines(options)
            return

        palette = self._palette()
        items: List[tuple[str, str, bool]] = []
        for option in options:
            if ". " not in option:
                continue
            num, desc = option.split(". ", 1)
            is_priority = desc.startswith("★")
            clean_desc = desc[1:].strip() if is_priority else desc
            items.append((num, clean_desc, is_priority))

        body = Text()
        for index, (num, desc, is_priority) in enumerate(items):
            if index:
                body.append("\n")
            body.append(
                f" {num} ",
                style=palette["menu_primary_badge"] if is_priority else palette["menu_badge"],
            )
            body.append(" ")
            body.append(
                desc,
                style=palette["menu_primary_text"] if is_priority else palette["menu_text"],
            )

        panel = Panel(
            body,
            title=(
                f"[{palette['menu_title']}]菜单[/{palette['menu_title']}]"
                if self.app.language() == "zh"
                else f"[{palette['menu_title']}]Menu[/{palette['menu_title']}]"
            ),
            border_style=palette["menu_border"],
            box=box.ROUNDED,
            padding=(0, 1),
        )

        self.console.print(panel)
        self._page_menu_rendered = True
        self._menu_prompt_pending = True

    def prompt(self, label: str, default: Any = None) -> str:
        """Prompt for input."""
        if not self.console:
            return self.app.prompt(label, default)

        self._flush_buffered_info()
        palette = self._palette()
        prompt_text = f"[{palette['prompt']}]{label}[/{palette['prompt']}]"
        if default:
            return Prompt.ask(prompt_text, default=str(default))
        return Prompt.ask(prompt_text)

    def prompt_choice(self, label: str = None) -> str:
        """Prompt for menu choice."""
        if not self.console:
            if label:
                return input(f"{label}: ").strip()
            return input(f"{self.app.tr('prompt')}: ").strip()

        if label is None:
            label = self.app.tr('prompt')
        if not self._menu_prompt_pending:
            self._flush_buffered_info()

        if self.app.supports_single_key_choice():
            if self._menu_prompt_pending:
                self._menu_prompt_pending = False
            palette = self._palette()
            self.console.print(f"[{palette['prompt']}]{label}[/{palette['prompt']}] ", end="")
            choice = self.app.read_single_key(default="0").strip()
            self.console.print(f"[{palette['prompt']}]{choice}[/{palette['prompt']}]")
            self._flush_buffered_info()
            return choice

        self._menu_prompt_pending = False
        palette = self._palette()
        result = Prompt.ask(f"[{palette['prompt']}]{label}[/{palette['prompt']}]", default="0")
        self._flush_buffered_info()
        return result

    def confirm(self, question: str, default: bool = True) -> bool:
        """Prompt for confirmation."""
        if not self.console:
            return self.app.prompt_yes_no(question, default)

        self._flush_buffered_info()
        palette = self._palette()
        return Confirm.ask(f"[{palette['warning']}]{question}[/{palette['warning']}]", default=default)

    def success(self, message: str) -> None:
        """Show success message."""
        if not self.console:
            print(f"✓ {message}")
            return

        self._flush_buffered_info()
        palette = self._palette()
        self.console.print(f"[{palette['success']}]✓[/{palette['success']}] {message}")

    def error(self, message: str) -> None:
        """Show error message."""
        if not self.console:
            print(f"✗ {message}")
            return

        self._flush_buffered_info()
        palette = self._palette()
        self.console.print(f"[{palette['error']}]✗[/{palette['error']}] {message}")

    def warning(self, message: str) -> None:
        """Show warning message."""
        if not self.console:
            print(f"⚠ {message}")
            return

        self._flush_buffered_info()
        palette = self._palette()
        self.console.print(f"[{palette['warning']}]⚠[/{palette['warning']}] {message}")

    def info(self, message: str) -> None:
        """Show info message."""
        if not self.console:
            print(message)
            return

        if self._defer_page_info and not self._page_menu_rendered:
            self._buffered_info.append(message)
            return
        self._print_info_now(message)

    def blank_line(self) -> None:
        """Print or defer a spacer line."""
        if not self.console:
            print()
            return

        if self._defer_page_info and not self._page_menu_rendered:
            self._buffered_info.append(None)
            return
        self.console.print()

    def pause(self) -> None:
        """Pause for user input."""
        if not self.console:
            self.app.pause()
            return

        self._flush_buffered_info()
        self.console.print()
        Prompt.ask(f"[dim]{self.app.tr('press_enter')}[/dim]", default="")

    def print_table(self, title: str, headers: List[str], rows: List[List[str]],
                   styles: Optional[List[str]] = None) -> None:
        """Print a formatted table."""
        if not self.console:
            # Fallback to simple print
            print(f"\n{title}")
            print("-" * 60)
            for row in rows:
                print(" | ".join(str(cell) for cell in row))
            return

        self._flush_buffered_info()
        table = Table(
            title=f"[{self._palette()['status_title']}]{title}[/{self._palette()['status_title']}]",
            box=box.ROUNDED,
            border_style=self._palette()["status_border"],
            show_lines=self._terminal_width() >= 88,
            expand=True,
        )

        # Add columns
        for i, header in enumerate(headers):
            style = styles[i] if styles and i < len(styles) else "white"
            table.add_column(header, style=style)

        # Add rows
        for row in rows:
            table.add_row(*[str(cell) for cell in row])

        self.console.print(table)

    def print_section(self, title: str, content: str) -> None:
        """Print a section with panel."""
        if not self.console:
            print(f"\n{title}")
            print(content)
            return

        self._flush_buffered_info()
        panel = Panel(
            content,
            title=f"[{self._palette()['status_title']}]{title}[/{self._palette()['status_title']}]",
            border_style=self._palette()["status_border"],
            box=box.ROUNDED
        )
        self.console.print(panel)

    def spinner(self, message: str):
        """Context manager for spinner."""
        if not self.console:
            print(message)
            return self._dummy_context()

        self._flush_buffered_info()
        return self.console.status(
            f"[{self._palette()['info']}]{message}[/{self._palette()['info']}]",
            spinner="dots",
        )

    def _dummy_context(self):
        """Dummy context manager for fallback."""
        class DummyContext:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return DummyContext()

    def print(self, message: str, style: str = "") -> None:
        """Print message with optional style."""
        if not self.console:
            print(message)
            return

        self._flush_buffered_info()
        if style:
            self.console.print(f"[{style}]{message}[/{style}]")
        else:
            self.console.print(message)

    def input(self, prompt: str) -> str:
        """Get user input."""
        if not self.console:
            return input(prompt).strip()

        self._flush_buffered_info()
        palette = self._palette()
        return Prompt.ask(f"[{palette['prompt']}]{prompt}[/{palette['prompt']}]").strip()

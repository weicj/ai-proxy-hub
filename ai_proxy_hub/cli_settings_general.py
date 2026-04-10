from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .file_io import write_json

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliSettingsGeneralMixin:
    app: "InteractiveConsoleApp"

    def menu_config_transfer(self) -> None:
        while True:
            self.app.print_header()
            self.app.print_spacer()
            self.app.print_info("--- " + ("配置导入 / 导出" if self.app.language() == "zh" else "Import / export config") + " ---")
            self.app.print_menu_lines(
                [
                    "1. " + ("导出到文件" if self.app.language() == "zh" else "Export to file"),
                    "2. " + ("从文件导入" if self.app.language() == "zh" else "Import from file"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                default_path = str((self.app.config_path.parent / "ai-proxy-hub-export.json").expanduser())
                target = input(f"{('导出路径' if self.app.language() == 'zh' else 'Export path')} [{default_path}]: ").strip() or default_path
                try:
                    write_json(Path(target).expanduser(), self.app.store.get_config())
                    self.app.print_info("配置已导出。" if self.app.language() == "zh" else "Config exported.")
                except (OSError, PermissionError) as exc:
                    self.app.print_info(self.app.tr("start_fail", message=str(exc)))
                self.app.pause()
                continue
            if choice == "2":
                source = input(f"{('导入文件路径' if self.app.language() == 'zh' else 'Import file path')}: ").strip()
                if not source:
                    self.app.print_info(self.app.tr("invalid"))
                    self.app.pause()
                    continue
                try:
                    payload = json.loads(Path(source).expanduser().read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        raise json.JSONDecodeError("invalid", "", 0)
                    self.app.save_config(payload.get("config") if isinstance(payload.get("config"), dict) else payload)
                    self.app.print_info("配置已导入。" if self.app.language() == "zh" else "Config imported.")
                except (OSError, PermissionError, json.JSONDecodeError) as exc:
                    self.app.print_info(self.app.tr("start_fail", message=str(exc)))
                self.app.pause()
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_runtime_settings(self) -> None:
        while True:
            self.app.print_header()
            apply_status = self.app.runtime_apply_status()
            self.app.print_spacer()
            self.app.print_info("--- " + ("运行与设置" if self.app.language() == "zh" else "Runtime & settings") + " ---")
            pending_summary = self.app.runtime_apply_summary()
            if pending_summary:
                self.app.print_info(f"⚠ {pending_summary}")
            self.app.print_menu_lines(
                [
                    "1. " + ("全局运行" if self.app.language() == "zh" else "Global runtime") + self.app.pending_badge(bool(apply_status["global_runtime"])),
                    "2. " + ("网络与端口" if self.app.language() == "zh" else "Network & ports") + self.app.pending_badge(bool(apply_status["settings"])),
                    "3. " + ("超时与冷却" if self.app.language() == "zh" else "Timeout & cooldown"),
                    "4. " + ("导入 / 导出配置" if self.app.language() == "zh" else "Import / export config"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.app.menu_global_runtime()
            elif choice == "2":
                self.app.menu_network_ports()
            elif choice == "3":
                self.app.menu_runtime_auth()
            elif choice == "4":
                self.app.menu_config_transfer()
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_settings(self) -> None:
        self.menu_runtime_settings()

    def menu_dashboard_usage(self) -> None:
        while True:
            self.app.print_header()
            runtime = self.app.service.runtime_info()
            self.app.print_spacer()
            self.app.print_info("--- " + ("Web 与用量" if self.app.language() == "zh" else "Web & usage") + " ---")
            self.app.print_info(f"{self.app.tr('dashboard_url')}: {runtime.get('dashboard_url')}")
            self.app.print_menu_lines(
                [
                    "1. " + ("打开 Web 控制台" if self.app.language() == "zh" else "Open Web dashboard"),
                    "2. " + ("用量统计" if self.app.language() == "zh" else "Usage stats"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.app.open_web_console()
            elif choice == "2":
                self.app.menu_usage()
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliSettingsAppearanceMixin:
    app: "InteractiveConsoleApp"

    def menu_appearance(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            self.app.print_spacer()
            self.app.print_info("--- " + ("语言与 CLI 主题" if self.app.language() == "zh" else "Language & CLI theme") + " ---")
            self.app.print_menu_lines(
                [
                    f"1. Language [{self.app.current_language_label()}]",
                    f"2. {('CLI 主题' if self.app.language() == 'zh' else 'CLI theme')} [{self.app.theme_label(config.get('cli_theme_mode') or config.get('theme_mode') or 'auto')}]",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.app.menu_language()
            elif choice == "2":
                self.app.menu_theme()
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_language(self) -> None:
        while True:
            self.app.print_header()
            self.app.print_spacer()
            self.app.print_info(f"--- {self.app.tr('language_title')} ---")
            self.app.print_menu_lines(
                [
                    "1. " + ("跟随系统" if self.app.language() == "zh" else "Follow system"),
                    "2. 中文",
                    "3. English",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice()
            if choice == "0":
                return
            mapping = {"1": "auto", "2": "zh", "3": "en"}
            if choice in mapping:
                config = self.app.store.get_config()
                config["ui_language"] = mapping[choice]
                self.app.save_config(config)
                self.app.print_info(self.app.tr("language_saved"))
                self.app.pause()
                return
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_theme(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            self.app.print_spacer()
            self.app.print_info("--- " + ("CLI 主题" if self.app.language() == "zh" else "CLI theme") + " ---")
            self.app.print_menu_lines(
                [
                    f"1. {self.app.theme_label('auto')}",
                    f"2. {self.app.theme_label('dark')}",
                    f"3. {self.app.theme_label('light')}",
                    "4. " + ("更多主题" if self.app.language() == "zh" else "More themes"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            mapping = {"1": "auto", "2": "dark", "3": "light"}
            if choice in mapping:
                config["cli_theme_mode"] = mapping[choice]
                self.app.save_config(config)
                self.app.print_info(self.app.tr("saved"))
                self.app.pause()
                return
            if choice == "4":
                self.app.menu_theme_accents()
                return
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_theme_accents(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            self.app.print_spacer()
            self.app.print_info("--- " + ("更多 CLI 主题" if self.app.language() == "zh" else "More CLI themes") + " ---")
            self.app.print_menu_lines(
                [
                    f"1. {self.app.theme_label('blue')}",
                    f"2. {self.app.theme_label('green')}",
                    f"3. {self.app.theme_label('amber')}",
                    f"4. {self.app.theme_label('rose')}",
                    f"5. {self.app.theme_label('teal')}",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            mapping = {"1": "blue", "2": "green", "3": "amber", "4": "rose", "5": "teal"}
            if choice == "0":
                return
            if choice in mapping:
                config["cli_theme_mode"] = mapping[choice]
                self.app.save_config(config)
                self.app.print_info(self.app.tr("saved"))
                self.app.pause()
                return
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

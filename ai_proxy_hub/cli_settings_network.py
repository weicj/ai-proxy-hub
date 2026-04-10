from __future__ import annotations

from typing import TYPE_CHECKING

from .config_logic import (
    apply_routing_strategy_to_config,
    default_model_settings_from_config,
    normalize_api_prefix,
    normalize_default_model_mode_map,
    normalize_endpoint_mode,
    normalize_global_default_models_map,
    normalize_shared_api_prefixes,
    normalize_split_api_ports,
    protocol_routing_settings_from_config,
    routing_strategy_from_config,
    set_manual_active_upstream,
)
from .constants import DEFAULT_LISTEN_PORT
from .protocols import normalize_upstream_protocol
from .utils import safe_int

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliSettingsNetworkMixin:
    app: "InteractiveConsoleApp"

    def menu_network_ports(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            apply_status = self.app.runtime_apply_status()
            endpoint_mode = normalize_endpoint_mode(config.get("endpoint_mode"))
            allow_lan = str(config.get("listen_host") or "").strip() not in {"127.0.0.1", "localhost", "::1", ""}
            self.app.print_spacer()
            self.app.print_info("--- " + ("网络与端口" if self.app.language() == "zh" else "Network & ports") + " ---")
            pending_summary = self.app.runtime_apply_summary()
            if pending_summary:
                self.app.print_info(f"⚠ {pending_summary}")
            self.app.print_menu_lines(
                [
                    f"1. {self.app.tr('listenHost')} [{config['listen_host']}]",
                    f"2. {('局域网访问' if self.app.language() == 'zh' else 'LAN access')} [{'ON' if allow_lan else 'OFF'}]",
                    f"3. {('端口模式' if self.app.language() == 'zh' else 'Endpoint mode')} "
                    f"[{'共享端口' if endpoint_mode == 'shared' and self.app.language() == 'zh' else '独立端口' if endpoint_mode == 'split' and self.app.language() == 'zh' else 'Shared port' if endpoint_mode == 'shared' else 'Split ports'}]",
                    "4. " + ("编辑端口 / 前缀" if self.app.language() == "zh" else "Edit ports / prefixes"),
                    "5. " + self.app.tr("apply_now") + self.app.pending_badge(bool(apply_status["enabled"])),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                value = self.app.prompt(self.app.tr("listenHost"), config["listen_host"])
                if value:
                    config["listen_host"] = value
                    self.app.save_config(config)
            elif choice == "2":
                config["listen_host"] = "0.0.0.0" if not allow_lan else "127.0.0.1"
                self.app.save_config(config)
            elif choice == "3":
                self.app.print_menu_lines(
                    [
                        "1. " + ("共享端口" if self.app.language() == "zh" else "Shared port"),
                        "2. " + ("独立端口" if self.app.language() == "zh" else "Split ports"),
                        "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                    ]
                )
                value = self.app.prompt_choice()
                if value == "1":
                    config["endpoint_mode"] = "shared"
                    self.app.save_config(config)
                elif value == "2":
                    config["endpoint_mode"] = "split"
                    self.app.save_config(config)
            elif choice == "4":
                self.app.menu_port_layout()
            elif choice == "5":
                self.app.apply_saved_runtime_changes()
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_port_layout(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            endpoint_mode = normalize_endpoint_mode(config.get("endpoint_mode"))
            self.app.print_spacer()
            self.app.print_info("--- " + ("端口与前缀" if self.app.language() == "zh" else "Ports & prefixes") + " ---")
            if endpoint_mode == "shared":
                prefixes = normalize_shared_api_prefixes(config.get("shared_api_prefixes"))
                self.app.print_menu_lines(
                    [
                        f"1. {self.app.tr('listenPort')} [{config['listen_port']}]",
                        f"2. Codex / OpenAI [{prefixes['openai']}]",
                        f"3. Claude [{prefixes['anthropic']}]",
                        f"4. Gemini [{prefixes['gemini']}]",
                        "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                    ]
                )
                choice = self.app.prompt_choice().lower()
                if choice == "0":
                    return
                if choice == "1":
                    value = self.app.prompt(self.app.tr("listenPort"), config["listen_port"])
                    if value.isdigit():
                        config["listen_port"] = int(value)
                        self.app.save_config(config)
                elif choice in {"2", "3", "4"}:
                    protocol = {"2": "openai", "3": "anthropic", "4": "gemini"}[choice]
                    current = prefixes[protocol]
                    value = self.app.prompt(self.app.protocol_console_label(protocol), current)
                    if value:
                        config.setdefault("shared_api_prefixes", {})
                        config["shared_api_prefixes"][protocol] = normalize_api_prefix(value, current)
                        self.app.save_config(config)
                else:
                    self.app.print_info(self.app.tr("invalid"))
                    self.app.pause()
                continue

            split_ports = normalize_split_api_ports(
                config.get("split_api_ports"),
                safe_int(config.get("listen_port"), DEFAULT_LISTEN_PORT),
            )
            self.app.print_menu_lines(
                [
                    f"1. {('Web UI 端口' if self.app.language() == 'zh' else 'Web UI port')} [{config.get('web_ui_port')}]",
                    f"2. Codex / OpenAI [{split_ports['openai']}]",
                    f"3. Claude [{split_ports['anthropic']}]",
                    f"4. Gemini [{split_ports['gemini']}]",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                value = self.app.prompt("Web UI", config.get("web_ui_port"))
                if value.isdigit():
                    config["web_ui_port"] = int(value)
                    self.app.save_config(config)
            elif choice in {"2", "3", "4"}:
                protocol = {"2": "openai", "3": "anthropic", "4": "gemini"}[choice]
                value = self.app.prompt(self.app.protocol_console_label(protocol), split_ports[protocol])
                if value.isdigit():
                    config.setdefault("split_api_ports", {})
                    config["split_api_ports"][protocol] = int(value)
                    self.app.save_config(config)
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_protocol_default_models(self, protocol: str) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            settings = default_model_settings_from_config(config, protocol)
            self.app.print_spacer()
            self.app.print_info(
                f"--- {self.app.protocol_console_label(protocol)} / "
                f"{('默认模型' if self.app.language() == 'zh' else 'Default model')} ---"
            )
            self.app.print_menu_lines(
                [
                    f"1. {('缺省模型来源' if self.app.language() == 'zh' else 'Fallback model source')} "
                    f"[{self.app.tr('default_model_mode_global') if settings['mode'] == 'global' else self.app.tr('default_model_mode_upstream')}]",
                    f"2. {('协议默认模型' if self.app.language() == 'zh' else 'Protocol default model')} "
                    f"[{settings['global_default_model'] or '-'}]",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.app.print_menu_lines(
                    [
                        "1. " + self.app.tr("default_model_mode_global"),
                        "2. " + self.app.tr("default_model_mode_upstream"),
                        "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                    ]
                )
                value = self.app.prompt_choice()
                if value == "1":
                    config["default_model_mode_by_protocol"] = normalize_default_model_mode_map(
                        config.get("default_model_mode_by_protocol"),
                        legacy_mode=config.get("default_model_mode"),
                    )
                    config["default_model_mode_by_protocol"][protocol] = "global"
                    if protocol == "openai":
                        config["default_model_mode"] = "global"
                    self.app.save_config(config)
                elif value == "2":
                    config["default_model_mode_by_protocol"] = normalize_default_model_mode_map(
                        config.get("default_model_mode_by_protocol"),
                        legacy_mode=config.get("default_model_mode"),
                    )
                    config["default_model_mode_by_protocol"][protocol] = "upstream"
                    if protocol == "openai":
                        config["default_model_mode"] = "upstream"
                    self.app.save_config(config)
            elif choice == "2":
                prompt_label = (
                    f"{self.app.protocol_console_label(protocol)} 默认模型"
                    if self.app.language() == "zh"
                    else f"{self.app.protocol_console_label(protocol)} default model"
                )
                value = self.app.prompt(prompt_label, settings["global_default_model"])
                config["global_default_models_by_protocol"] = normalize_global_default_models_map(
                    config.get("global_default_models_by_protocol"),
                    legacy_model=config.get("global_default_model"),
                )
                config["global_default_models_by_protocol"][protocol] = value
                if protocol == "openai":
                    config["global_default_model"] = value
                self.app.save_config(config)
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_default_models(self) -> None:
        self.menu_protocol_default_models("openai")

    def menu_routing_controls(self) -> None:
        while True:
            self.app.print_header()
            self.app.print_spacer()
            self.app.print_info(f"--- {self.app.tr('routing_controls')} ---")
            self.app.print_menu_lines(
                [
                    "1. " + self.app.tr("routing_codex"),
                    "2. " + self.app.tr("routing_claude"),
                    "3. " + self.app.tr("routing_gemini"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            mapping = {"1": "openai", "2": "anthropic", "3": "gemini"}
            if choice in mapping:
                self.menu_protocol_routing(mapping[choice])
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_protocol_routing(self, protocol: str) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            settings = protocol_routing_settings_from_config(config, protocol)
            upstreams = [item for item in config["upstreams"] if normalize_upstream_protocol(item.get("protocol")) == protocol]
            manual_name = next((item["name"] for item in upstreams if item["id"] == settings["manual_active_upstream_id"]), "-")
            self.app.print_spacer()
            self.app.print_info(f"--- {self.app.protocol_console_label(protocol)} ---")
            self.app.print_info(f"{self.app.tr('routing_strategy')}: {self.app.routing_strategy_label(routing_strategy_from_config(config, protocol))}")
            self.app.print_info(f"{self.app.tr('manualActiveUpstream')}: {manual_name}")
            self.app.print_menu_lines(
                [
                    "1. " + self.app.tr("routing_strategy"),
                    "2. " + self.app.tr("manualActiveUpstream"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.app.print_menu_lines(
                    [
                        "1. " + self.app.tr("routing_manual"),
                        "2. " + self.app.tr("routing_priority"),
                        "3. " + self.app.tr("routing_round_robin"),
                        "4. " + self.app.tr("routing_latency"),
                        "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                    ]
                )
                value = self.app.prompt_choice()
                mapping = {"1": "manual", "2": "priority", "3": "round_robin", "4": "latency"}
                if value in mapping:
                    apply_routing_strategy_to_config(config, mapping[value], protocol)
                    self.app.save_config(config)
            elif choice == "2":
                if not upstreams:
                    self.app.print_info(self.app.tr("no_upstreams"))
                    self.app.pause()
                    continue
                for index, upstream in enumerate(upstreams, start=1):
                    self.app.print_info(f"{index}. {upstream['name']}")
                value = input(f"{self.app.tr('choose_index')}: ").strip()
                if value.isdigit() and 1 <= int(value) <= len(upstreams):
                    set_manual_active_upstream(config, protocol, upstreams[int(value) - 1]["id"])
                    self.app.save_config(config)
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

    def menu_runtime_auth(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            self.app.print_spacer()
            self.app.print_info("--- " + ("超时与冷却" if self.app.language() == "zh" else "Timeout & cooldown") + " ---")
            self.app.print_menu_lines(
                [
                    f"1. {self.app.tr('timeoutSeconds')} [{config['request_timeout_sec']}]",
                    f"2. {self.app.tr('cooldownSeconds')} [{config['cooldown_seconds']}]",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                value = self.app.prompt(self.app.tr("timeoutSeconds"), config["request_timeout_sec"])
                if value.isdigit():
                    config["request_timeout_sec"] = int(value)
                    self.app.save_config(config)
            elif choice == "2":
                value = self.app.prompt(self.app.tr("cooldownSeconds"), config["cooldown_seconds"])
                if value.isdigit():
                    config["cooldown_seconds"] = int(value)
                    self.app.save_config(config)
            else:
                self.app.print_info(self.app.tr("invalid"))
                self.app.pause()

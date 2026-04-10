from __future__ import annotations

from typing import TYPE_CHECKING

from .cli_local_keys import build_local_key_entry
from .local_keys import generate_local_api_key, normalize_local_key_protocols
from .utils import now_iso

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliLocalKeyController:
    def __init__(self, app: "InteractiveConsoleApp") -> None:
        self.app = app

    def _local_key_status_map(self, snapshot: dict) -> dict:
        return {item["id"]: item for item in snapshot.get("local_api_keys") or []}

    def _find_local_key_index(self, config: dict, key_id: str) -> int:
        for index, entry in enumerate(config.get("local_api_keys") or []):
            if str(entry.get("id") or "") == key_id:
                return index
        return -1

    def _last_upstream_name(self, snapshot: dict, upstream_id: str) -> str:
        for upstream in snapshot.get("upstreams") or []:
            if str(upstream.get("id") or "") == str(upstream_id or ""):
                return str(upstream.get("name") or "")
        return ""

    def _save_and_refresh_clients(self, config: dict) -> None:
        self.app.save_config(config)
        self.app.refresh_switched_clients()

    def _set_primary_local_key(self, key_id: str) -> None:
        config = self.app.store.get_config()
        key_index = self._find_local_key_index(config, key_id)
        if key_index < 0:
            return
        entry = config["local_api_keys"].pop(key_index)
        entry["enabled"] = True
        config["local_api_keys"].insert(0, entry)
        self._save_and_refresh_clients(config)
        self.app.print_info(self.app.tr("saved"))
        self.app.pause()

    def _toggle_local_key_enabled(self, key_id: str) -> None:
        config = self.app.store.get_config()
        key_index = self._find_local_key_index(config, key_id)
        if key_index < 0:
            return
        entry = config["local_api_keys"][key_index]
        enabled_count = sum(1 for item in config["local_api_keys"] if item.get("enabled", True))
        if entry.get("enabled", True) and enabled_count <= 1:
            self.app.print_info("至少要保留一个启用的 Key。" if self.app.language() == "zh" else "At least one key must stay enabled.")
            self.app.pause()
            return
        entry["enabled"] = not bool(entry.get("enabled", True))
        self._save_and_refresh_clients(config)
        self.app.print_info(self.app.tr("saved"))
        self.app.pause()

    def _delete_local_key(self, key_id: str) -> bool:
        config = self.app.store.get_config()
        key_index = self._find_local_key_index(config, key_id)
        if key_index < 0:
            return True
        if len(config["local_api_keys"]) <= 1:
            self.app.print_info("至少要保留一个 Key。" if self.app.language() == "zh" else "At least one key is required.")
            self.app.pause()
            return False
        if not self.app.prompt_yes_no(("确定删除这个 Key？" if self.app.language() == "zh" else "Delete this key?"), default=False):
            return False
        config["local_api_keys"].pop(key_index)
        self._save_and_refresh_clients(config)
        self.app.print_info(self.app.tr("deleted"))
        self.app.pause()
        return True

    def menu_local_api_keys(self) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            snapshot = self.app.get_runtime_snapshot()
            stats_by_id = self._local_key_status_map(snapshot)
            self.app.print_spacer()
            self.app.print_info("--- " + ("本地 API Keys" if self.app.language() == "zh" else "Local API keys") + " ---")
            if config.get("local_api_keys"):
                self.app.print_info(
                    "输入 Key 编号可直接查看详情。"
                    if self.app.language() == "zh"
                    else "Press a key number to open its detail view."
                )
            for index, entry in enumerate(config.get("local_api_keys") or [], start=1):
                status_entry = stats_by_id.get(entry["id"], {})
                stats = status_entry.get("stats") or {}
                primary = bool(status_entry.get("is_primary"))
                enabled = bool(entry.get("enabled", True))
                labels = []
                labels.append("ON" if enabled else "OFF")
                if primary:
                    labels.append("主 Key" if self.app.language() == "zh" else "Primary")
                self.app.print_info(
                    f"{index}. {entry['name']} [{' / '.join(labels)}] | {self.app.format_protocol_list(entry.get('allowed_protocols') or [])} | "
                    f"{stats.get('success_count', 0)}/{stats.get('request_count', 0)} | {self.app.masked_secret(str(entry.get('key') or ''))}"
                )
            self.app.print_menu_lines(
                [
                    "A. " + ("新增 Key" if self.app.language() == "zh" else "Add key"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice.isdigit():
                local_index = int(choice) - 1
                if 0 <= local_index < len(config.get("local_api_keys") or []):
                    self.menu_local_api_key_editor(local_index)
                    continue
            if choice == "a":
                next_index = len(config.get("local_api_keys") or [])
                entry = build_local_key_entry(self.app.language(), next_index, generate_local_api_key(), now_iso())
                config.setdefault("local_api_keys", []).append(entry)
                self.app.save_config(config)
                self.app.print_info(self.app.tr("saved"))
                self.app.pause()
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_local_api_key_editor(self, index: int) -> None:
        config = self.app.store.get_config()
        if not 0 <= index < len(config.get("local_api_keys") or []):
            return
        key_id = str(config["local_api_keys"][index].get("id") or "")
        while True:
            config = self.app.store.get_config()
            key_index = self._find_local_key_index(config, key_id)
            if key_index < 0:
                return
            entry = config["local_api_keys"][key_index]
            snapshot = self.app.get_runtime_snapshot()
            status_entry = self._local_key_status_map(snapshot).get(key_id, {})
            stats = status_entry.get("stats") or {}
            primary = bool(status_entry.get("is_primary"))
            last_upstream_name = self._last_upstream_name(snapshot, str(stats.get("last_upstream_id") or ""))

            self.app.print_header()
            self.app.print_spacer()
            self.app.print_info(f"--- {entry['name']} ---")
            status_labels = ["ON" if entry.get("enabled", True) else "OFF"]
            if primary:
                status_labels.append("主 Key" if self.app.language() == "zh" else "Primary")
            self.app.print_info(f"{'状态' if self.app.language() == 'zh' else 'Status'}: {' | '.join(status_labels)}")
            self.app.print_info(f"Key: {self.app.masked_secret(str(entry.get('key') or ''))}")
            self.app.print_info(
                f"{('允许类型' if self.app.language() == 'zh' else 'Allowed protocols')}: "
                f"{self.app.format_protocol_list(entry.get('allowed_protocols') or [])}"
            )
            self.app.print_info(
                f"{'请求统计' if self.app.language() == 'zh' else 'Requests'}: "
                f"{stats.get('success_count', 0)}/{stats.get('request_count', 0)}"
            )
            self.app.print_info(
                f"{'创建时间' if self.app.language() == 'zh' else 'Created'}: "
                f"{entry.get('created_at') or '-'}"
            )
            self.app.print_info(
                f"{'最近使用' if self.app.language() == 'zh' else 'Last used'}: "
                f"{stats.get('last_used_at') or '-'}"
            )
            self.app.print_info(
                f"{'最近成功' if self.app.language() == 'zh' else 'Last success'}: "
                f"{stats.get('last_success_at') or '-'}"
            )
            self.app.print_info(
                f"{'最近上游' if self.app.language() == 'zh' else 'Last upstream'}: "
                f"{last_upstream_name or '-'}"
            )
            if stats.get("last_error"):
                self.app.print_info(
                    f"{'最近错误' if self.app.language() == 'zh' else 'Last error'}: "
                    f"{stats.get('last_error') or '-'}"
                )
            self.app.print_menu_lines(
                [
                    "1. " + ("重命名" if self.app.language() == "zh" else "Rename"),
                    "2. " + ("允许类型" if self.app.language() == "zh" else "Allowed protocols"),
                    "3. " + ("设为主 Key" if self.app.language() == "zh" else "Set primary"),
                    "4. " + ("启用 / 关闭" if self.app.language() == "zh" else "Enable / Disable"),
                    "5. " + ("重新生成 Key" if self.app.language() == "zh" else "Regenerate key"),
                    "6. " + ("删除" if self.app.language() == "zh" else "Delete"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                value = self.app.prompt(self.app.tr("name"), entry["name"])
                if value:
                    entry["name"] = value
                    self.app.save_config(config)
                    self.app.print_info(self.app.tr("saved"))
                    self.app.pause()
                continue
            if choice == "2":
                protocols = self.app.prompt_allowed_protocols(normalize_local_key_protocols(entry.get("allowed_protocols") or []))
                if protocols is not None:
                    entry["allowed_protocols"] = protocols
                    self.app.save_config(config)
                    self.app.print_info(self.app.tr("saved"))
                    self.app.pause()
                continue
            if choice == "3":
                self._set_primary_local_key(key_id)
                continue
            if choice == "4":
                self._toggle_local_key_enabled(key_id)
                continue
            if choice == "5":
                entry["key"] = generate_local_api_key()
                self._save_and_refresh_clients(config)
                self.app.print_info(self.app.tr("saved"))
                self.app.pause()
                continue
            if choice == "6":
                if self._delete_local_key(key_id):
                    return
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()


__all__ = ["CliLocalKeyController"]

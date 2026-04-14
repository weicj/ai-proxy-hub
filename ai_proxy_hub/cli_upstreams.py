from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from .config_logic import default_upstream, normalize_extra_headers, normalize_upstream
from .network import client_display_name, perform_upstream_probe_request, protocol_client_id
from .protocols import normalize_upstream_protocol
from .subscriptions import current_local_datetime, default_subscription, normalize_subscription

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


class CliUpstreamController:
    def __init__(self, app: "InteractiveConsoleApp") -> None:
        self.app = app

    def _subscription_kind_label(self, kind: str) -> str:
        return {
            "unlimited": "无限制" if self.app.language() == "zh" else "Unlimited",
            "periodic": "定期刷新" if self.app.language() == "zh" else "Periodic",
            "quota": "定额消耗" if self.app.language() == "zh" else "Quota",
        }.get(str(kind or ""), str(kind or "-"))

    def _subscription_state_label(self, state: str) -> str:
        return {
            "ready": "可用" if self.app.language() == "zh" else "Ready",
            "awaiting_probe": "待探测" if self.app.language() == "zh" else "Awaiting probe",
            "pending_refresh": "等待刷新" if self.app.language() == "zh" else "Pending refresh",
            "exhausted": "已耗尽" if self.app.language() == "zh" else "Exhausted",
            "expired": "已过期" if self.app.language() == "zh" else "Expired",
            "disabled": "已禁用" if self.app.language() == "zh" else "Disabled",
            "manual_lock": "需手动恢复" if self.app.language() == "zh" else "Manual reactivate",
            "temporary_exhausted": "临时冻结" if self.app.language() == "zh" else "Temporarily exhausted",
            "quota_exhausted": "额度耗尽" if self.app.language() == "zh" else "Quota exhausted",
        }.get(str(state or ""), str(state or "-"))

    def _relative_time_label(self, iso_text: str) -> str:
        target = str(iso_text or "").strip()
        if not target:
            return "-"
        try:
            target_dt = datetime.fromisoformat(target)
        except ValueError:
            return target
        delta = target_dt - current_local_datetime()
        seconds = int(delta.total_seconds())
        if seconds <= 0:
            return "已到达" if self.app.language() == "zh" else "Reached"
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        if self.app.language() == "zh":
            parts = []
            if days:
                parts.append(f"{days}天")
            if hours:
                parts.append(f"{hours}小时")
            if minutes or not parts:
                parts.append(f"{minutes}分钟")
            return "还差 " + "".join(parts)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes or not parts:
            parts.append(f"{minutes}m")
        return "in " + " ".join(parts)

    def _subscription_label(self, subscription: Dict[str, Any]) -> str:
        name = str(subscription.get("name") or "-")
        kind = self._subscription_kind_label(str(subscription.get("kind") or ""))
        state = self._subscription_state_label(str(subscription.get("state") or ""))
        status = "ON" if subscription.get("enabled", True) else "OFF"
        parts = [status, kind, state]
        if subscription.get("next_reset_at"):
            parts.append(self._relative_time_label(str(subscription.get("next_reset_at") or "")))
        elif subscription.get("expires_at"):
            parts.append(str(subscription.get("expires_at") or ""))
        return f"{name} | {' | '.join(parts)}"

    def prompt_subscription(self, subscription: Dict[str, Any], title: str) -> Optional[Dict[str, Any]]:
        self.app.print_header()
        self.app.print_spacer()
        self.app.print_info(f"--- {title} ---")
        draft = json.loads(json.dumps(subscription))

        name = self.app.prompt(self.app.tr("name"), draft.get("name") or "")
        if name:
            draft["name"] = name

        kind_prompt = "订阅类型" if self.app.language() == "zh" else "Subscription kind"
        self.app.print_info(
            "1 无限 | 2 定期刷新 | 3 定额消耗"
            if self.app.language() == "zh"
            else "1 Unlimited | 2 Periodic | 3 Quota"
        )
        current_kind = str(draft.get("kind") or "unlimited")
        kind_value = self.app.prompt(kind_prompt, current_kind)
        if kind_value in {"1", "unlimited"}:
            draft["kind"] = "unlimited"
        elif kind_value in {"2", "periodic", "refresh"}:
            draft["kind"] = "periodic"
        elif kind_value in {"3", "quota"}:
            draft["kind"] = "quota"

        enabled = self.app.prompt(self.app.tr("enabled"), "y" if draft.get("enabled", True) else "n")
        if enabled.lower() in {"y", "yes", "1", "true"}:
            draft["enabled"] = True
        elif enabled.lower() in {"n", "no", "0", "false"}:
            draft["enabled"] = False

        permanent_prompt = "永久有效" if self.app.language() == "zh" else "Permanent"
        permanent = self.app.prompt(permanent_prompt, "y" if draft.get("permanent", True) else "n")
        if permanent.lower() in {"y", "yes", "1", "true"}:
            draft["permanent"] = True
            draft["expires_at"] = ""
        elif permanent.lower() in {"n", "no", "0", "false"}:
            draft["permanent"] = False
            expiry_label = "到期日期 YYYY-MM-DD" if self.app.language() == "zh" else "Expiry date YYYY-MM-DD"
            draft["expires_at"] = self.app.prompt(expiry_label, draft.get("expires_at") or "")

        if draft.get("kind") == "periodic":
            reset_label = "刷新时间 HH:MM, 逗号分隔" if self.app.language() == "zh" else "Reset times HH:MM, comma separated"
            current_reset_times = ", ".join(draft.get("reset_times") or [])
            reset_times = self.app.prompt(reset_label, current_reset_times or "09:00")
            if reset_times:
                draft["reset_times"] = [item.strip() for item in str(reset_times).split(",")]
        else:
            draft["reset_times"] = []

        if draft.get("kind") in {"periodic", "quota"}:
            self.app.print_info(
                "1 连续失败次数 | 2 连续失败天数"
                if self.app.language() == "zh"
                else "1 Consecutive failures | 2 Consecutive days"
            )
            failure_mode_label = "冻结规则" if self.app.language() == "zh" else "Freeze rule"
            current_failure_mode = str(draft.get("failure_mode") or "consecutive_failures")
            failure_mode = self.app.prompt(failure_mode_label, current_failure_mode)
            if failure_mode in {"1", "consecutive_failures"}:
                draft["failure_mode"] = "consecutive_failures"
            elif failure_mode in {"2", "consecutive_days"}:
                draft["failure_mode"] = "consecutive_days"
            threshold_label = "阈值" if self.app.language() == "zh" else "Threshold"
            threshold = self.app.prompt(threshold_label, draft.get("failure_threshold") or 1)
            if str(threshold).strip().isdigit():
                draft["failure_threshold"] = int(str(threshold).strip())

        notes = self.app.prompt(self.app.tr("notes"), draft.get("notes") or "")
        if notes:
            draft["notes"] = notes

        if not self.app.prompt_yes_no(self.app.tr("save_confirm"), default=True):
            self.app.print_info(self.app.tr("cancelled"))
            self.app.pause()
            return None
        return normalize_subscription(draft, 0)

    def test_upstream(self, index: int) -> None:
        config = self.app.store.get_config()
        upstream = config["upstreams"][index]
        try:
            result = perform_upstream_probe_request(upstream, self.app.store.get_timeout())
            self.app.store.record_probe_result(
                upstream["id"],
                status=result["status"],
                latency_ms=result["latency_ms"],
                models_count=result["models_count"],
                models=result.get("models"),
            )
            self.app.print_info(
                self.app.tr(
                    "test_ok",
                    status=result["status"],
                    latency=result["latency_ms"],
                    models=result.get("models_count"),
                )
            )
        except Exception as exc:
            self.app.store.record_probe_result(upstream["id"], status=None, error=str(exc))
            self.app.print_info(self.app.tr("test_fail", message=str(exc)))
        self.app.pause()

    def delete_upstream(self, index: int) -> None:
        config = self.app.store.get_config()
        if not self.app.prompt_yes_no(self.app.tr("delete_confirm"), default=False):
            return
        config["upstreams"].pop(index)
        self.app.save_config(config)
        self.app.print_info(self.app.tr("deleted"))
        self.app.pause()

    def prompt_upstream(
        self,
        upstream: Dict[str, Any],
        title_key: str,
        locked_protocol: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        self.app.print_header()
        self.app.print_spacer()
        self.app.print_info(f"--- {self.app.tr(title_key)} ---")
        draft = json.loads(json.dumps(upstream))
        if locked_protocol:
            draft["protocol"] = normalize_upstream_protocol(locked_protocol)
        name = self.app.prompt(self.app.tr("name"), draft["name"])
        if name:
            draft["name"] = name
        protocol_prompt = "协议类型" if self.app.language() == "zh" else "Protocol"
        if locked_protocol:
            self.app.print_info(f"{protocol_prompt}: {self.app.protocol_console_label(draft['protocol'])}")
        else:
            self.app.print_info("1 Codex / OpenAI | 2 Claude / Anthropic | 3 Gemini | 4 Local LLM")
            protocol_value = self.app.prompt(
                protocol_prompt,
                self.app.protocol_label(normalize_upstream_protocol(draft.get("protocol"))),
            )
            if protocol_value in {"1", "openai", "OpenAI", "codex"}:
                draft["protocol"] = "openai"
            elif protocol_value in {"2", "anthropic", "claude", "Claude", "Claude/Anthropic"}:
                draft["protocol"] = "anthropic"
            elif protocol_value in {"3", "gemini", "Gemini"}:
                draft["protocol"] = "gemini"
            elif protocol_value in {"4", "local_llm", "local", "Local LLM", "本地LLM"}:
                draft["protocol"] = "local_llm"

        if draft["protocol"] == "local_llm" and not locked_protocol:
            upstream_protocol_prompt = "上游协议类型" if self.app.language() == "zh" else "Upstream Protocol"
            self.app.print_info("1 OpenAI Compatible | 2 Anthropic | 3 Gemini")
            current_upstream_protocol = draft.get("upstream_protocol", "openai")
            upstream_protocol_value = self.app.prompt(
                upstream_protocol_prompt,
                self.app.protocol_label(normalize_upstream_protocol(current_upstream_protocol)),
            )
            if upstream_protocol_value in {"1", "openai", "OpenAI", "openai-compatible"}:
                draft["upstream_protocol"] = "openai"
            elif upstream_protocol_value in {"2", "anthropic", "claude", "Claude", "Anthropic"}:
                draft["upstream_protocol"] = "anthropic"
            elif upstream_protocol_value in {"3", "gemini", "Gemini"}:
                draft["upstream_protocol"] = "gemini"
            else:
                draft["upstream_protocol"] = (
                    current_upstream_protocol
                    if current_upstream_protocol in {"openai", "anthropic", "gemini"}
                    else "openai"
                )

        base_url = self.app.prompt(self.app.tr("base_url"), draft["base_url"])
        if base_url:
            draft["base_url"] = base_url
        api_key = self.app.prompt(self.app.tr("api_key"), draft["api_key"])
        if api_key:
            draft["api_key"] = api_key
        enabled = self.app.prompt(self.app.tr("enabled"), "y" if draft["enabled"] else "n")
        if enabled.lower() in {"y", "yes", "1", "true"}:
            draft["enabled"] = True
        elif enabled.lower() in {"n", "no", "0", "false"}:
            draft["enabled"] = False
        default_model = self.app.prompt(self.app.tr("default_model"), draft["default_model"])
        if default_model:
            draft["default_model"] = default_model
        notes = self.app.prompt(self.app.tr("notes"), draft["notes"])
        if notes:
            draft["notes"] = notes
        headers_input = self.app.prompt(
            self.app.tr("extra_headers"),
            json.dumps(draft["extra_headers"], ensure_ascii=False),
        )
        if headers_input:
            try:
                parsed = json.loads(headers_input)
                if isinstance(parsed, dict):
                    draft["extra_headers"] = normalize_extra_headers(parsed)
            except json.JSONDecodeError:
                pass
        if not self.app.prompt_yes_no(self.app.tr("save_confirm"), default=True):
            self.app.print_info(self.app.tr("cancelled"))
            self.app.pause()
            return None
        return draft

    def add_upstream(self, protocol: Optional[str] = None) -> None:
        config = self.app.store.get_config()
        locked_protocol = normalize_upstream_protocol(protocol) if protocol else None
        base_name = (
            client_display_name(protocol_client_id(locked_protocol))
            if locked_protocol
            else ("Upstream" if self.app.language() == "en" else "上游")
        )
        count = len(self.app.protocol_upstream_indices(config, locked_protocol)) if locked_protocol else len(config["upstreams"])
        upstream = default_upstream(f"{base_name} {count + 1}")
        if locked_protocol:
            upstream["protocol"] = locked_protocol
        draft = self.prompt_upstream(upstream, "add_upstream", locked_protocol=locked_protocol)
        if draft is None:
            return
        config["upstreams"].append(normalize_upstream(draft, len(config["upstreams"])))
        self.app.save_config(config)
        self.app.print_info(self.app.tr("saved"))
        self.app.pause()

    def edit_upstream(self, index: int, protocol: Optional[str] = None) -> None:
        config = self.app.store.get_config()
        locked_protocol = normalize_upstream_protocol(protocol) if protocol else None
        draft = self.prompt_upstream(config["upstreams"][index], "edit_upstream", locked_protocol=locked_protocol)
        if draft is None:
            return
        config["upstreams"][index] = normalize_upstream({**config["upstreams"][index], **draft}, index)
        self.app.save_config(config)
        self.app.print_info(self.app.tr("saved"))
        self.app.pause()

    def test_all_upstreams(self, protocol: Optional[str] = None) -> None:
        config = self.app.store.get_config()
        targets = [
            upstream
            for upstream in config["upstreams"]
            if protocol is None or normalize_upstream_protocol(upstream.get("protocol")) == normalize_upstream_protocol(protocol)
        ]
        if not targets:
            self.app.print_info(self.app.tr("no_upstreams"))
            self.app.pause()
            return
        self.app.print_info(self.app.tr("testing_all"))
        for index, upstream in enumerate(targets, start=1):
            self.app.print_info(self.app.tr("testing_item", index=index, total=len(targets), name=upstream["name"]))
            try:
                result = perform_upstream_probe_request(upstream, self.app.store.get_timeout())
                self.app.store.record_probe_result(
                    upstream["id"],
                    status=result["status"],
                    latency_ms=result["latency_ms"],
                    models_count=result["models_count"],
                    models=result.get("models"),
                )
            except Exception as exc:
                self.app.store.record_probe_result(upstream["id"], status=None, error=str(exc))
        self.app.pause()

    def reorder_protocol_upstreams(self, protocol: str) -> None:
        config = self.app.store.get_config()
        indices = self.app.protocol_upstream_indices(config, protocol)
        if len(indices) < 2:
            self.app.print_info("至少需要两个上游。" if self.app.language() == "zh" else "At least two upstreams are required.")
            self.app.pause()
            return
        local_index = self.app.prompt_local_index(len(indices))
        if local_index is None:
            return
        self.app.print_menu_lines(
            [
                "1. " + ("上移" if self.app.language() == "zh" else "Move up"),
                "2. " + ("下移" if self.app.language() == "zh" else "Move down"),
                "0. " + ("返回" if self.app.language() == "zh" else "Back"),
            ]
        )
        direction = self.app.prompt_choice(
            "移动方向" if self.app.language() == "zh" else "Move direction"
        ).strip().lower()
        if direction == "0":
            return
        direction = "u" if direction == "1" else "d" if direction == "2" else direction
        swap_index = local_index - 1 if direction == "u" else local_index + 1 if direction == "d" else -1
        if swap_index < 0 or swap_index >= len(indices):
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()
            return
        subset = [config["upstreams"][index] for index in indices]
        subset[local_index], subset[swap_index] = subset[swap_index], subset[local_index]
        for position, global_index in enumerate(indices):
            config["upstreams"][global_index] = subset[position]
        self.app.save_config(config)

    def toggle_upstream_enabled(self, index: int) -> None:
        config = self.app.store.get_config()
        upstream = config["upstreams"][index]
        upstream["enabled"] = not bool(upstream.get("enabled", True))
        self.app.save_config(config)
        self.app.print_info(self.app.tr("saved"))
        self.app.pause()

    def reactivate_upstream(self, upstream_id: str) -> None:
        result = self.app.store.reactivate_upstream(upstream_id)
        if result.get("ok"):
            message = "上游订阅状态已恢复。" if self.app.language() == "zh" else "Upstream subscription state reactivated."
            self.app.print_info(message)
        else:
            message = "没有找到对应上游。" if self.app.language() == "zh" else "Upstream not found."
            self.app.print_info(message)
        self.app.pause()

    def menu_upstream_subscriptions(self, upstream_index: int) -> None:
        while True:
            config = self.app.store.get_config()
            if upstream_index >= len(config.get("upstreams") or []):
                return
            upstream = config["upstreams"][upstream_index]
            snapshot = self.app.get_runtime_snapshot()
            upstream_status = next((item for item in snapshot["upstreams"] if item["id"] == upstream["id"]), {})
            subscriptions = upstream_status.get("subscriptions") or upstream.get("subscriptions") or []

            self.app.print_header()
            self.app.print_spacer()
            self.app.print_info(
                f"--- {upstream['name']} / "
                f"{('订阅管理' if self.app.language() == 'zh' else 'Subscriptions')} ---"
            )
            if subscriptions:
                self.app.print_info(
                    "输入订阅编号可直接编辑。"
                    if self.app.language() == "zh"
                    else "Press a subscription number to edit it."
                )
            for index, item in enumerate(subscriptions, start=1):
                self.app.print_info(f"{index}. {self._subscription_label(item)}")
            self.app.print_menu_lines(
                [
                    "A. " + ("新增订阅" if self.app.language() == "zh" else "Add subscription"),
                    "X. " + ("启用 / 关闭" if self.app.language() == "zh" else "Toggle enabled"),
                    "D. " + ("删除订阅" if self.app.language() == "zh" else "Delete subscription"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice.isdigit():
                sub_index = int(choice) - 1
                if 0 <= sub_index < len(upstream.get("subscriptions") or []):
                    draft = self.prompt_subscription(
                        upstream["subscriptions"][sub_index],
                        "编辑订阅" if self.app.language() == "zh" else "Edit subscription",
                    )
                    if draft is None:
                        continue
                    config["upstreams"][upstream_index]["subscriptions"][sub_index] = draft
                    self.app.save_config(config)
                    self.app.print_info(self.app.tr("saved"))
                    self.app.pause()
                    continue
            if choice == "a":
                next_number = len(upstream.get("subscriptions") or []) + 1
                draft = self.prompt_subscription(
                    default_subscription(name=f"{upstream['name']} Subscription {next_number}"),
                    "新增订阅" if self.app.language() == "zh" else "Add subscription",
                )
                if draft is None:
                    continue
                config["upstreams"][upstream_index].setdefault("subscriptions", []).append(draft)
                self.app.save_config(config)
                self.app.print_info(self.app.tr("saved"))
                self.app.pause()
                continue
            if choice in {"x", "d"}:
                if not subscriptions:
                    self.app.print_info(self.app.tr("invalid"))
                    self.app.pause()
                    continue
                sub_index = self.app.prompt_local_index(len(subscriptions))
                if sub_index is None:
                    continue
                if choice == "x":
                    target = config["upstreams"][upstream_index]["subscriptions"][sub_index]
                    target["enabled"] = not bool(target.get("enabled", True))
                    self.app.save_config(config)
                    self.app.print_info(self.app.tr("saved"))
                    self.app.pause()
                    continue
                if len(config["upstreams"][upstream_index].get("subscriptions") or []) <= 1:
                    self.app.print_info(
                        "至少保留一个订阅。"
                        if self.app.language() == "zh"
                        else "At least one subscription is required."
                    )
                    self.app.pause()
                    continue
                if not self.app.prompt_yes_no(
                    "确定删除这个订阅？" if self.app.language() == "zh" else "Delete this subscription?",
                    default=False,
                ):
                    continue
                config["upstreams"][upstream_index]["subscriptions"].pop(sub_index)
                self.app.save_config(config)
                self.app.print_info(self.app.tr("deleted"))
                self.app.pause()
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_upstream_detail(self, protocol: str, index: int) -> None:
        while True:
            config = self.app.store.get_config()
            if index >= len(config["upstreams"]):
                return
            upstream = config["upstreams"][index]
            if normalize_upstream_protocol(upstream.get("protocol")) != normalize_upstream_protocol(protocol):
                return

            snapshot = self.app.get_runtime_snapshot()
            upstream_status = next((item for item in snapshot["upstreams"] if item["id"] == upstream["id"]), {})
            stats = upstream_status.get("stats") or {}
            self.app.print_header()
            self.app.print_spacer()
            self.app.print_info(
                f"--- {self.app.protocol_console_label(protocol)} / {upstream['name']} ---"
            )
            self.app.print_info(
                f"{self.app.tr('summary_activation')}: "
                f"{self.app.activation_label(upstream['id'], upstream['enabled'], snapshot, protocol)}"
            )
            self.app.print_info(f"{self.app.tr('summary_probe')}: {self.app.probe_label(stats)}")
            self.app.print_info(
                f"{self.app.tr('summary_requests')}: "
                f"{self.app.tr('summary_requests_value', success=stats.get('success_count', 0), total=stats.get('request_count', 0))}"
            )
            self.app.print_info(f"{self.app.tr('base_url')}: {upstream['base_url'] or '-'}")
            self.app.print_info(f"{self.app.tr('api_key')}: {self.app.masked_secret(upstream.get('api_key') or '')}")
            self.app.print_info(f"{self.app.tr('default_model')}: {upstream.get('default_model') or '-'}")
            self.app.print_info(
                f"{self.app.tr('enabled')}: "
                f"{'ON' if upstream.get('enabled', True) else 'OFF'}"
            )
            self.app.print_info(f"{self.app.tr('notes')}: {upstream.get('notes') or '-'}")
            self.app.print_spacer()
            self.app.print_info(
                f"{'当前订阅' if self.app.language() == 'zh' else 'Current subscription'}: "
                f"{upstream_status.get('current_subscription_name') or '-'}"
            )
            self.app.print_info(
                f"{'订阅状态' if self.app.language() == 'zh' else 'Subscription state'}: "
                f"{self._subscription_state_label(str(upstream_status.get('subscription_state') or ''))}"
            )
            if upstream_status.get("subscription_next_reset_at"):
                self.app.print_info(
                    f"{'下次重置' if self.app.language() == 'zh' else 'Next reset'}: "
                    f"{self._relative_time_label(str(upstream_status.get('subscription_next_reset_at') or ''))}"
                )
            subscriptions = upstream_status.get("subscriptions") or []
            if subscriptions:
                self.app.print_info("订阅列表:" if self.app.language() == "zh" else "Subscriptions:")
                for item in subscriptions:
                    state_label = self._subscription_state_label(str(item.get("state") or ""))
                    kind_label = self._subscription_kind_label(str(item.get("kind") or ""))
                    suffix_parts = [kind_label, state_label]
                    if item.get("next_reset_at"):
                        suffix_parts.append(self._relative_time_label(str(item.get("next_reset_at") or "")))
                    elif item.get("expires_at"):
                        suffix_parts.append(str(item.get("expires_at") or ""))
                    self.app.print_info(f"  - {item.get('name') or '-'} | {' | '.join(suffix_parts)}")
            self.app.print_menu_lines(
                [
                    "1. " + ("测试连接" if self.app.language() == "zh" else "Test"),
                    "2. " + ("修改" if self.app.language() == "zh" else "Edit"),
                    "3. " + ("禁用 / 启用" if self.app.language() == "zh" else "Disable / Enable"),
                    "4. " + ("删除" if self.app.language() == "zh" else "Delete"),
                    "5. " + ("恢复订阅状态" if self.app.language() == "zh" else "Reactivate subscriptions"),
                    "6. " + ("管理订阅" if self.app.language() == "zh" else "Manage subscriptions"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice == "1":
                self.test_upstream(index)
                continue
            if choice == "2":
                self.edit_upstream(index, protocol)
                continue
            if choice == "3":
                self.toggle_upstream_enabled(index)
                continue
            if choice == "4":
                self.delete_upstream(index)
                return
            if choice == "5":
                self.reactivate_upstream(upstream["id"])
                continue
            if choice == "6":
                self.menu_upstream_subscriptions(index)
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_protocol_upstreams(self, protocol: str) -> None:
        while True:
            self.app.print_header()
            config = self.app.store.get_config()
            snapshot = self.app.get_runtime_snapshot()
            status_map = {item["id"]: item["stats"] for item in snapshot["upstreams"]}
            indices = self.app.protocol_upstream_indices(config, protocol)
            self.app.print_spacer()
            self.app.print_info(f"--- {self.app.protocol_console_label(protocol)} / {self.app.tr('upstream_title')} ---")
            if not indices:
                self.app.print_info(self.app.tr("no_upstreams"))
            else:
                self.app.print_info(
                    "输入上游编号可直接查看详情。"
                    if self.app.language() == "zh"
                    else "Press an upstream number to open its detail view."
                )
            for local_index, global_index in enumerate(indices, start=1):
                upstream = config["upstreams"][global_index]
                stats = status_map.get(upstream["id"], {})
                self.app.print_info(
                    f"{local_index}. {upstream['name']} | {self.app.tr('summary_activation')}: "
                    f"{self.app.activation_label(upstream['id'], upstream['enabled'], snapshot, protocol)} | "
                    f"{self.app.tr('summary_probe')}: {self.app.probe_label(stats)} | "
                    f"{self.app.tr('summary_requests')}: "
                    f"{self.app.tr('summary_requests_value', success=stats.get('success_count', 0), total=stats.get('request_count', 0))}"
                )
                self.app.print_info(f"   {upstream['base_url'] or '-'}")
            self.app.print_menu_lines(
                [
                    "A. " + ("新增上游" if self.app.language() == "zh" else "Add upstream"),
                    "T. " + ("测试全部" if self.app.language() == "zh" else "Test all"),
                    "R. " + ("调整顺序" if self.app.language() == "zh" else "Reorder upstreams"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice().lower()
            if choice == "0":
                return
            if choice.isdigit():
                local_index = int(choice) - 1
                if 0 <= local_index < len(indices):
                    self.menu_upstream_detail(protocol, indices[local_index])
                    continue
            if choice == "a":
                self.add_upstream(protocol)
                continue
            if choice == "t":
                self.test_all_upstreams(protocol)
                continue
            if choice == "r":
                self.reorder_protocol_upstreams(protocol)
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()


__all__ = ["CliUpstreamController"]

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from .local_keys import normalize_local_key_protocols
from .protocols import normalize_upstream_protocol

if TYPE_CHECKING:
    from .cli_app import InteractiveConsoleApp


def direct_local_key_label(language: str) -> str:
    return "直连 / 未鉴权" if language == "zh" else "Direct / No Local Key"


def usage_pairs_for_scope(bucket: Dict[str, Any], allowed_upstream_ids: set[str]) -> List[Dict[str, Any]]:
    raw_pairs = bucket.get("pairs")
    if not isinstance(raw_pairs, list):
        raw_pairs = [
            {
                "upstream_id": upstream_id,
                "local_key_id": "",
                "count": count,
            }
            for upstream_id, count in (bucket.get("by_upstream") or {}).items()
        ]
    pairs: List[Dict[str, Any]] = []
    for pair in raw_pairs:
        upstream_id = str(pair.get("upstream_id") or "")
        if upstream_id not in allowed_upstream_ids:
            continue
        count = int(pair.get("count") or 0)
        if count <= 0:
            continue
        pairs.append(
            {
                "upstream_id": upstream_id,
                "local_key_id": str(pair.get("local_key_id") or ""),
                "count": count,
            }
        )
    return pairs


def prepare_usage_chart_data(
    usage: Dict[str, Any],
    config: Dict[str, Any],
    scope: str,
    local_key_filter: str = "all",
    *,
    language: str = "zh",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    upstream_protocols = {
        upstream["id"]: normalize_upstream_protocol(upstream.get("protocol"))
        for upstream in config.get("upstreams") or []
    }
    allowed_upstream_ids = {
        upstream_id
        for upstream_id, protocol in upstream_protocols.items()
        if scope == "all" or protocol == scope
    }
    buckets: List[Dict[str, Any]] = []
    active_upstream_ids: set[str] = set()
    for bucket in usage["buckets"]:
        pairs = usage_pairs_for_scope(bucket, allowed_upstream_ids)
        by_upstream: Dict[str, int] = {}
        for pair in pairs:
            if local_key_filter != "all" and pair["local_key_id"] != local_key_filter:
                continue
            upstream_id = pair["upstream_id"]
            by_upstream[upstream_id] = by_upstream.get(upstream_id, 0) + pair["count"]
        active_upstream_ids.update(by_upstream.keys())
        buckets.append(
            {
                "start_ts": bucket["start_ts"],
                "end_ts": bucket["end_ts"],
                "total": sum(by_upstream.values()),
                "by_group": by_upstream,
            }
        )

    filtered_upstreams = [
        upstream
        for upstream in (usage.get("upstreams") or [])
        if str(upstream.get("id") or "") in allowed_upstream_ids
    ]
    if active_upstream_ids:
        filtered_upstreams = [upstream for upstream in filtered_upstreams if str(upstream.get("id") or "") in active_upstream_ids]
    legend_items = [
        {
            "id": str(upstream.get("id") or ""),
            "name": str(upstream.get("name") or upstream.get("id") or ""),
        }
        for upstream in filtered_upstreams
        if str(upstream.get("id") or "")
    ]

    max_total = max((bucket["total"] for bucket in buckets), default=0)
    return legend_items, buckets, max_total


class CliUsageController:
    def __init__(self, app: "InteractiveConsoleApp") -> None:
        self.app = app

    def available_local_key_options(self, usage: Dict[str, Any], config: Dict[str, Any], scope: str) -> List[Dict[str, str]]:
        configured = [
            item
            for item in (config.get("local_api_keys") or [])
            if scope == "all" or scope in normalize_local_key_protocols(item.get("allowed_protocols") or item.get("protocols"))
        ]
        options = [
            {"id": "all", "name": "全部本地Key" if self.app.language() == "zh" else "All Local Keys"}
        ]
        seen = {"all"}
        active_local_key_ids = {
            str(pair.get("local_key_id") or "")
            for bucket in (usage.get("buckets") or [])
            for pair in (bucket.get("pairs") or [])
            if str(pair.get("upstream_id") or "") in {
                upstream["id"]
                for upstream in config.get("upstreams") or []
                if scope == "all" or normalize_upstream_protocol(upstream.get("protocol")) == scope
            }
        }
        for item in configured:
            key_id = str(item.get("id") or "")
            if not key_id or key_id in seen or (active_local_key_ids and key_id not in active_local_key_ids):
                continue
            options.append({"id": key_id, "name": str(item.get("name") or key_id)})
            seen.add(key_id)
        for item in usage.get("local_keys") or []:
            key_id = str(item.get("id") or "")
            if not key_id or key_id in seen or key_id not in active_local_key_ids:
                continue
            options.append({"id": key_id, "name": str(item.get("name") or key_id)})
            seen.add(key_id)
        if "" in active_local_key_ids:
            options.append({"id": "", "name": direct_local_key_label(self.app.language())})
        return options

    def ensure_usage_local_key(self, usage: Dict[str, Any], config: Dict[str, Any], scope: str) -> str:
        selected = str(getattr(self.app, "usage_local_key", "all") or "all")
        option_ids = {item["id"] for item in self.available_local_key_options(usage, config, scope)}
        if selected in option_ids:
            return selected
        self.app.usage_local_key = "all"
        return "all"

    def render_usage_chart(self) -> None:
        usage = self.app.store.get_usage_series(self.app.usage_range)
        scope = str(getattr(self.app, "usage_protocol", "all") or "all")
        config = self.app.store.get_config()
        selected_local_key = self.ensure_usage_local_key(usage, config, scope)
        legend_items, buckets, max_total = prepare_usage_chart_data(
            usage,
            config,
            scope,
            selected_local_key,
            language=self.app.language(),
        )
        self.app.print_spacer()
        self.app.print_info(f"--- {self.app.tr('usage_title')} ---")
        self.app.print_info(
            f"{self.app.tr('usage_metric_label')} | "
            f"{('范围' if self.app.language() == 'zh' else 'Scope')}: {self.app.usage_scope_label()} | "
            f"{('本地Key' if self.app.language() == 'zh' else 'Local Key')}: {self.app.usage_local_key_label()}"
        )
        if max_total == 0:
            self.app.print_info(self.app.tr("usage_empty"))
            return
        self.app.print_info(f"{self.app.tr('legend')}:")
        for index, item in enumerate(legend_items):
            marker = self.app.colorize("██", index)
            self.app.print_info(f"  {marker} {item['name']}")
        self.app.print_spacer()
        max_width = 28
        available_width = self.app.terminal_width()
        label_width = 6 if str(self.app.usage_range) in {"minute", "hour"} else 5
        max_width = max(8, min(40, available_width - label_width - 10))
        for bucket in buckets:
            total = bucket["total"]
            label = self.app.format_usage_label(bucket["start_ts"])
            if total == 0:
                bar = ""
            else:
                segments: List[str] = []
                for index, item in enumerate(legend_items):
                    count = bucket["by_group"].get(item["id"], 0)
                    if count <= 0:
                        continue
                    width = max(1, int(round((count / max(max_total, 1)) * max_width)))
                    segments.append(self.app.colorize("█" * width, index))
                bar = "".join(segments)
            self.app.print_info(f"{label:>{label_width}} | {bar} {total}")

    def menu_usage_range(self) -> None:
        while True:
            self.app.print_header()
            self.render_usage_chart()
            self.app.print_menu_lines(
                [
                    "1. " + ("分钟" if self.app.language() == "zh" else "Minute"),
                    "2. " + ("小时" if self.app.language() == "zh" else "Hour"),
                    "3. " + ("日" if self.app.language() == "zh" else "Day"),
                    "4. " + ("周" if self.app.language() == "zh" else "Week"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice()
            if choice == "0":
                return
            mapping = {"1": "minute", "2": "hour", "3": "day", "4": "week"}
            if choice in mapping:
                self.app.usage_range = mapping[choice]
                return
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_usage_scope(self) -> None:
        while True:
            self.app.print_header()
            self.render_usage_chart()
            self.app.print_menu_lines(
                [
                    "1. " + ("全部" if self.app.language() == "zh" else "All"),
                    "2. Codex / OpenAI",
                    "3. Claude / Anthropic",
                    "4. Gemini",
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice()
            mapping = {"1": "all", "2": "openai", "3": "anthropic", "4": "gemini"}
            if choice == "0":
                return
            if choice in mapping:
                self.app.usage_protocol = mapping[choice]
                return
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_usage_local_key(self) -> None:
        while True:
            self.app.print_header()
            self.render_usage_chart()
            usage = self.app.store.get_usage_series(self.app.usage_range)
            config = self.app.store.get_config()
            scope = str(getattr(self.app, "usage_protocol", "all") or "all")
            options = self.available_local_key_options(usage, config, scope)
            lines = [
                f"{index + 1}. {item['name']}"
                for index, item in enumerate(options)
            ]
            lines.append("0. " + ("返回" if self.app.language() == "zh" else "Back"))
            self.app.print_menu_lines(lines)
            choice = self.app.prompt_choice()
            if choice == "0":
                return
            try:
                index = int(choice) - 1
            except ValueError:
                index = -1
            if 0 <= index < len(options):
                self.app.usage_local_key = options[index]["id"]
                return
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()

    def menu_usage(self) -> None:
        while True:
            self.app.print_header()
            self.render_usage_chart()
            range_label = {
                "minute": "分钟" if self.app.language() == "zh" else "Minute",
                "hour": "小时" if self.app.language() == "zh" else "Hour",
                "day": "日" if self.app.language() == "zh" else "Day",
                "week": "周" if self.app.language() == "zh" else "Week",
            }.get(str(self.app.usage_range), str(self.app.usage_range))
            self.app.print_menu_lines(
                [
                    "1. " + (f"时间范围 ({range_label})" if self.app.language() == "zh" else f"Time Range ({range_label})"),
                    "2. " + (f"协议范围 ({self.app.usage_scope_label()})" if self.app.language() == "zh" else f"Protocol Scope ({self.app.usage_scope_label()})"),
                    "3. " + (f"本地Key ({self.app.usage_local_key_label()})" if self.app.language() == "zh" else f"Local Key ({self.app.usage_local_key_label()})"),
                    "0. " + ("返回" if self.app.language() == "zh" else "Back"),
                ]
            )
            choice = self.app.prompt_choice()
            if choice == "0":
                return
            if choice == "1":
                self.menu_usage_range()
                continue
            if choice == "2":
                self.menu_usage_scope()
                continue
            if choice == "3":
                self.menu_usage_local_key()
                continue
            self.app.print_info(self.app.tr("invalid"))
            self.app.pause()


__all__ = ["CliUsageController", "prepare_usage_chart_data"]

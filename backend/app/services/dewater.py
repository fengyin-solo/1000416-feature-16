"""脱水运行业务规则：状态流转、字段校验、异常筛选与按设备统计都收在这里。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "dewater"
REQUIRED_FIELDS = ["记录编号", "脱水机编号", "进泥量"]
DATA_FIELDS = [
    "记录编号",
    "脱水机编号",
    "运行时间",
    "进泥量",
    "出泥含水率",
    "絮凝剂用量",
    "运行时长",
    "操作人员",
]
STATUS_ORDER = ["待开机", "运行中", "已停机", "故障停机"]
ACTION_RULES = {"确认开机": "运行中", "确认停机": "已停机", "登记故障": "故障停机"}
NEGATIVE_ACTIONS = []

MACHINE_FIELD = "脱水机编号"
TIME_FIELD = "运行时间"
FEED_FIELD = "进泥量"
MOISTURE_FIELD = "出泥含水率"
DURATION_FIELD = "运行时长"

# 口径与页面筛选项保持一致；默认值集中在这里，后续接入配置时只需改这一处。
MIN_FEED = 10.0
MAX_FEED = 80.0
MOISTURE_LIMIT = 80.0
FEED_ABNORMAL = "进泥量异常"
MOISTURE_ABNORMAL = "出泥含水率偏高"
ABNORMAL_ALIASES = {
    "abnormal": "abnormal",
    "all": "abnormal",
    "异常": "abnormal",
    "feed": "feed",
    "feed_abnormal": "feed",
    "sludge": "feed",
    FEED_ABNORMAL: "feed",
    "进泥量": "feed",
    "moisture": "moisture",
    "moisture_high": "moisture",
    MOISTURE_ABNORMAL: "moisture",
    "出泥含水率": "moisture",
}
ACTION_TO_EVENT_TYPE = {
    "待开机": "待开机",
    "确认开机": "开机",
    "确认停机": "停机",
    "登记故障": "故障",
}
STATUS_TO_EVENT_TYPE = {
    "待开机": "待开机",
    "运行中": "开机",
    "已停机": "停机",
    "故障停机": "故障",
}
UNKNOWN_MACHINE = "未填写脱水机编号"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", _text(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _time_key(value: Any) -> tuple[int, datetime | None]:
    text = _text(value)
    if not text:
        return (1, datetime.max)
    try:
        return (0, datetime.fromisoformat(text.replace("/", "-")))
    except ValueError:
        return (1, datetime.max)


def _parse_time(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("/", "-"))
    except ValueError:
        return None


def _moisture_value(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    # 同时兼容“82%”和“0.82”两种录入口径。
    return number * 100 if number <= 1 else number


def abnormal_reasons(row: dict[str, Any]) -> list[str]:
    """按脱水记录列表的同一口径判断异常，空值和非数字不纳入过程异常。"""
    reasons: list[str] = []
    feed = _number(row.get(FEED_FIELD))
    if feed is not None and (feed < MIN_FEED or feed > MAX_FEED):
        reasons.append(FEED_ABNORMAL)

    moisture = _moisture_value(row.get(MOISTURE_FIELD))
    if moisture is not None and moisture > MOISTURE_LIMIT:
        reasons.append(MOISTURE_ABNORMAL)
    return reasons


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    """返回给接口的数据不携带内部事件，同时补齐列表用于展示和筛选的异常类型。"""
    item = {key: value for key, value in row.items() if not key.startswith("_")}
    item["异常类型"] = "、".join(abnormal_reasons(row)) or "正常"
    return item


class DewaterService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        machine: str | None = None,
        abnormal: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(store.rows(MODULE))

        keyword_text = _text(keyword)
        if keyword_text:
            rows = [row for row in rows if keyword_text in _text(row.get("记录编号"))]

        status_text = _text(status)
        if status_text:
            rows = [row for row in rows if _text(row.get("status")) == status_text]

        machine_text = _text(machine)
        if machine_text:
            rows = [row for row in rows if machine_text in _text(row.get(MACHINE_FIELD))]

        if _text(start_time):
            rows = [row for row in rows if self._in_time_range(row.get(TIME_FIELD), _text(start_time), None)]
        if _text(end_time):
            rows = [row for row in rows if self._in_time_range(row.get(TIME_FIELD), None, _text(end_time))]

        abnormal_key = ABNORMAL_ALIASES.get(_text(abnormal), "")
        if abnormal_key:
            filtered: list[dict[str, Any]] = []
            for row in rows:
                reasons = abnormal_reasons(row)
                if abnormal_key == "abnormal" and reasons:
                    filtered.append(row)
                elif abnormal_key == "feed" and FEED_ABNORMAL in reasons:
                    filtered.append(row)
                elif abnormal_key == "moisture" and MOISTURE_ABNORMAL in reasons:
                    filtered.append(row)
            rows = filtered

        # 异常记录和设备时序都按运行时间升序；时间为空的记录不臆造时间，统一排在最后。
        return sorted(rows, key=lambda row: _time_key(row.get(TIME_FIELD)))

    @staticmethod
    def _in_time_range(value: Any, start_text: str | None, end_text: str | None) -> bool:
        current = _parse_time(value)
        if current is None:
            return False
        if start_text:
            start = _parse_time(start_text)
            if start is not None and current < start:
                return False
        if end_text:
            end = _parse_time(end_text)
            if end is not None and current > end:
                return False
        return True

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        machine: str | None = None,
        abnormal: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(
            keyword=keyword,
            status=status,
            machine=machine,
            abnormal=abnormal,
            start_time=start_time,
            end_time=end_time,
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return [public_row(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return public_row(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in DATA_FIELDS:
            if field in values:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return public_row(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"脱水记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于脱水运行可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        action_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        events = entry.setdefault("_events", [])
        if isinstance(events, list):
            events.append({"action": action, "time": action_time})
        entry[TIME_FIELD] = action_time

        # 状态、pending、abnormal 的原有计算方式不动，重复开机/停机只在时序里提示，不拦截动作。
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return public_row(entry), f"脱水记录已{action}"

    def machine_statistics(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        machine: str | None = None,
        abnormal: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page_size: int = 20,
    ) -> dict[str, Any]:
        rows = self._filter_rows(
            keyword=keyword,
            status=status,
            machine=machine,
            abnormal=abnormal,
            start_time=start_time,
            end_time=end_time,
        )
        groups_map: dict[str, list[dict[str, Any]]] = {}
        for index, row in enumerate(rows):
            machine_name = _text(row.get(MACHINE_FIELD)) or UNKNOWN_MACHINE
            groups_map.setdefault(machine_name, []).append(row)

        groups: list[dict[str, Any]] = []
        notes: list[str] = []
        total_faults = 0
        total_feed_abnormal = 0
        total_moisture_abnormal = 0
        total_empty_time = 0
        total_runtime_hours = 0.0

        for machine_name in sorted(groups_map):
            machine_rows = groups_map[machine_name]
            events = self._build_events(machine_rows, rows, page_size)
            warnings = sorted({event["note"] for event in events if event.get("note")})
            for warning in warnings:
                notes.append(f"{machine_name}：{warning}")

            reasons = [reason for row in machine_rows for reason in abnormal_reasons(row)]
            empty_time_count = sum(1 for row in machine_rows if not _text(row.get(TIME_FIELD)))
            fault_count = sum(1 for row in machine_rows if row.get("status") == "故障停机")
            duration = sum(value for value in (_number(row.get(DURATION_FIELD)) for row in machine_rows) if value is not None)
            last_fault_time = self._last_fault_time(machine_rows, events)

            total_faults += fault_count
            total_feed_abnormal += sum(1 for row in machine_rows if FEED_ABNORMAL in abnormal_reasons(row))
            total_moisture_abnormal += sum(1 for row in machine_rows if MOISTURE_ABNORMAL in abnormal_reasons(row))
            total_empty_time += empty_time_count
            total_runtime_hours += duration

            groups.append({
                "脱水机编号": machine_name,
                "记录数": len(machine_rows),
                "运行中": sum(1 for row in machine_rows if row.get("status") == "运行中"),
                "已停机": sum(1 for row in machine_rows if row.get("status") == "已停机"),
                "故障停机": fault_count,
                "进泥量异常": sum(1 for reason in reasons if reason == FEED_ABNORMAL),
                "出泥含水率偏高": sum(1 for reason in reasons if reason == MOISTURE_ABNORMAL),
                "时间为空记录": empty_time_count,
                "运行时长合计": round(duration, 2),
                "最近故障时间": last_fault_time or "",
                "warnings": warnings,
                "events": events,
            })

        if total_empty_time:
            notes.append(f"有 {total_empty_time} 条记录运行时间为空，已排在时序末尾，无法参与开始/结束时间范围筛选。")
        if not rows:
            notes.append("当前筛选条件下暂无脱水记录，请调整筛选条件后重试。")

        actual_machine_count = len({name for name in groups_map if name != UNKNOWN_MACHINE})
        fault_rate = round(total_faults / len(rows) * 100, 1) if rows else 0.0
        return {
            "summary": {
                "脱水机数": actual_machine_count,
                "记录数": len(rows),
                "故障停机": total_faults,
                "故障率": fault_rate,
                "进泥量异常": total_feed_abnormal,
                "出泥含水率偏高": total_moisture_abnormal,
                "时间为空记录": total_empty_time,
                "运行时长合计": round(total_runtime_hours, 2),
            },
            "groups": groups,
            "notes": notes,
            "thresholds": {
                "进泥量下限": MIN_FEED,
                "进泥量上限": MAX_FEED,
                "出泥含水率上限": MOISTURE_LIMIT,
            },
        }

    def _build_events(
        self,
        machine_rows: list[dict[str, Any]],
        filtered_rows: list[dict[str, Any]],
        page_size: int,
    ) -> list[dict[str, Any]]:
        page_by_id = {
            int(row["id"]): index // page_size + 1
            for index, row in enumerate(filtered_rows)
            if "id" in row
        }
        events: list[dict[str, Any]] = []
        for row in machine_rows:
            stored_events = row.get("_events")
            if isinstance(stored_events, list) and stored_events:
                source_events = stored_events
            else:
                event_type = STATUS_TO_EVENT_TYPE.get(_text(row.get("status")))
                source_events = [{"action": next(
                    (action for action, label in ACTION_TO_EVENT_TYPE.items() if label == event_type), ""
                ), "time": row.get(TIME_FIELD, "")}] if event_type else []

            for event in source_events:
                action = _text(event.get("action"))
                event_type = ACTION_TO_EVENT_TYPE.get(action)
                if not event_type:
                    continue
                event_time = _text(event.get("time"))
                reasons = abnormal_reasons(row)
                events.append({
                    "id": row.get("id"),
                    "记录编号": row.get("记录编号", ""),
                    "脱水机编号": row.get(MACHINE_FIELD, "") or UNKNOWN_MACHINE,
                    "动作": action,
                    "事件类型": event_type,
                    "运行时间": event_time or "时间为空",
                    "状态": row.get("status", ""),
                    "异常类型": "、".join(reasons),
                    "page": page_by_id.get(int(row.get("id", 0)), 1),
                    "note": "",
                })

        events.sort(key=lambda event: (
            _time_key(event["运行时间"] if event["运行时间"] != "时间为空" else ""),
            int(event.get("id") or 0),
        ))
        normal_counts = {"开机": 0, "停机": 0}
        previous_normal_type = ""
        for event in events:
            event_type = event["事件类型"]
            if event_type == "故障":
                previous_normal_type = ""
            elif event_type in {"开机", "停机"}:
                normal_counts[event_type] += 1
                if normal_counts[event_type] > 1:
                    event["note"] = f"同一脱水机第{normal_counts[event_type]}次{event_type}"
                if event_type == previous_normal_type:
                    suffix = "开机，请核对是否重复登记" if event_type == "开机" else "停机，请核对是否重复登记"
                    event["note"] = f"同一脱水机连续重复{suffix}"
                previous_normal_type = event_type
        return events

    @staticmethod
    def _last_fault_time(machine_rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> str | None:
        fault_times = [
            event["运行时间"]
            for event in events
            if event["事件类型"] == "故障" and event["运行时间"] != "时间为空"
        ]
        if fault_times:
            return max(fault_times, key=lambda value: _time_key(value))
        row_fault_times = [
            _text(row.get(TIME_FIELD))
            for row in machine_rows
            if row.get("status") == "故障停机" and _text(row.get(TIME_FIELD))
        ]
        return max(row_fault_times, key=lambda value: _time_key(value), default=None)

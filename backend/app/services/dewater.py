"""脱水运行业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "dewater"
REQUIRED_FIELDS = ["记录编号", "脱水机编号", "进泥量"]
STATUS_ORDER = ["待开机", "运行中", "已停机", "故障停机"]
ACTION_RULES = {"确认开机": "运行中", "确认停机": "已停机", "登记故障": "故障停机"}
NEGATIVE_ACTIONS = []

TIME_FIELD = "登记时间"
INFLOW_LIMIT = 120.0  # 进泥量（m³/h）超过该上限视为进泥量异常
MOISTURE_LIMIT = 80.0  # 出泥含水率（%）超过该上限视为偏高
START_STATUSES = {"运行中"}
STOP_STATUSES = {"已停机", "故障停机"}


def _to_float(value: Any) -> float | None:
    """把字段值转成浮点数；空值或非数值返回 None，由调用方决定如何解释。"""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _time_text(row: dict[str, Any]) -> str:
    return str(row.get(TIME_FIELD) or "").strip()


def anomaly_reasons(row: dict[str, Any]) -> list[str]:
    """判断一条脱水记录的异常原因：进泥量异常、出泥含水率偏高。"""
    reasons: list[str] = []
    inflow = _to_float(row.get("进泥量"))
    if inflow is None or inflow <= 0 or inflow > INFLOW_LIMIT:
        reasons.append("进泥量异常")
    moisture = _to_float(row.get("出泥含水率"))
    if moisture is not None and moisture > MOISTURE_LIMIT:
        reasons.append("出泥含水率偏高")
    return reasons


def _split_by_time(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按登记时间升序排列；时间为空的记录无法排序，单独拿出来由调用方说明。"""
    timed = sorted((row for row in rows if _time_text(row)), key=_time_text)
    untimed = [row for row in rows if not _time_text(row)]
    return timed, untimed


def _repeat_notes(machine: str, timed_rows: list[dict[str, Any]]) -> list[str]:
    """同一脱水机的时序里连续出现同类开停机记录时给出说明；待开机不计入开停机时序。"""
    notes: list[str] = []
    previous: tuple[str, str] | None = None
    for row in timed_rows:
        status = str(row.get("status") or "")
        if status in START_STATUSES:
            kind = "开机"
        elif status in STOP_STATUSES:
            kind = "停机"
        else:
            continue
        code = str(row.get("记录编号") or row.get("id"))
        if previous is not None and previous[0] == kind:
            notes.append(f"脱水机 {machine} 存在重复{kind}记录：{previous[1]}、{code}，请核对开停机登记")
        previous = (kind, code)
    return notes


class DewaterService:
    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        machine: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """列表、统计、异常定位共用的筛选口径，保证三处查出来的数据一致。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if machine:
            rows = [row for row in rows if machine in str(row.get("脱水机编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        machine: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered_rows(keyword=keyword, machine=machine, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"脱水记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于脱水运行可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"脱水记录已{action}"

    def machine_stats(
        self,
        *,
        keyword: str | None = None,
        machine: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """按脱水机编号汇总运行时序与故障停机；筛选口径与脱水记录列表一致。"""
        rows = self._filtered_rows(keyword=keyword, machine=machine, status=status)
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            name = str(row.get("脱水机编号") or "").strip() or "未编号"
            groups.setdefault(name, []).append(row)
        machines: list[dict[str, Any]] = []
        notes: list[str] = []
        for name in sorted(groups):
            group = groups[name]
            timed, untimed = _split_by_time(group)
            hours = [value for value in (_to_float(row.get("运行时长")) for row in group) if value is not None]
            latest = timed[-1] if timed else None
            machines.append({
                "脱水机编号": name,
                "记录数": len(group),
                "开机次数": sum(1 for row in group if row.get("status") in START_STATUSES),
                "停机次数": sum(1 for row in group if row.get("status") in STOP_STATUSES),
                "故障停机次数": sum(1 for row in group if row.get("status") == "故障停机"),
                "累计运行时长": round(sum(hours), 1),
                "异常记录数": sum(1 for row in group if anomaly_reasons(row)),
                "当前状态": str(latest.get("status")) if latest else "暂无",
                "最近登记时间": _time_text(latest) if latest else "",
            })
            notes.extend(_repeat_notes(name, timed))
            if untimed:
                notes.append(f"脱水机 {name} 有 {len(untimed)} 条记录{TIME_FIELD}为空，时序统计时已排在末尾")
        moistures = [value for value in (_to_float(row.get("出泥含水率")) for row in rows) if value is not None]
        summary = {
            "运行机组": len(machines),
            "累计运行时长": round(sum(item["累计运行时长"] for item in machines), 1),
            "故障停机次数": sum(item["故障停机次数"] for item in machines),
            "异常记录数": sum(item["异常记录数"] for item in machines),
            "出泥含水率均值": round(sum(moistures) / len(moistures), 1) if moistures else None,
        }
        return {"machines": machines, "summary": summary, "notes": notes}

    def list_anomalies(
        self,
        *,
        keyword: str | None = None,
        machine: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """把进泥量异常、出泥含水率偏高的记录挑出来，按登记时间升序排列；时间为空的排在末尾。"""
        rows = self._filtered_rows(keyword=keyword, machine=machine, status=status)
        hits: list[dict[str, Any]] = []
        for row in rows:
            reasons = anomaly_reasons(row)
            if reasons:
                hits.append({**row, "异常原因": reasons})
        timed, untimed = _split_by_time(hits)
        notes: list[str] = []
        if untimed:
            notes.append(f"有 {len(untimed)} 条异常记录{TIME_FIELD}为空，已排在时序末尾")
        return {"items": timed + untimed, "total": len(hits), "notes": notes}

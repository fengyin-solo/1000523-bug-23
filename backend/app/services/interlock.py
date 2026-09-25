"""联锁设备业务规则：归属校验、状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "interlock"
REQUIRED_FIELDS = ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "责任人"]
STATUS_ORDER = ["待检修", "运用正常", "降级使用", "已停用"]
ACTION_RULES = {"确认检修": "运用正常", "降级登记": "降级使用", "停用设备": "已停用"}
NEGATIVE_ACTIONS = ["停用设备"]
# 降级登记与停用设备会把责任人移交给当前操作人；确认检修维持原样，不动责任人
HANDOVER_ACTIONS = ["降级登记", "停用设备"]
# 软件版本变更时这三个字段必须一起提交、一起落库，避免控制范围与责任人对不上
VERSION_FIELDS = ["软件版本", "控制范围", "责任人"]

# 账号名录：每个账号归属一个车站，只有本站账号与责任人本人能改动设备，其余账号只读
OPERATORS = [
    {"name": "王建国", "station": "望江站"},
    {"name": "李秀兰", "station": "望江站"},
    {"name": "张志强", "station": "云溪站"},
    {"name": "陈晓梅", "station": "松湖站"},
    {"name": "值班管理员", "station": "调度中心"},
]


class InterlockService:
    def list_operators(self) -> list[dict[str, str]]:
        return [dict(item) for item in OPERATORS]

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any], operator: str | None) -> tuple[dict[str, Any] | None, str]:
        account = self._find_operator(operator)
        if account is None:
            return None, self._unknown_operator_message(operator)
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        station = str(values["所属车站"]).strip()
        if station != account["station"]:
            return None, f"账号「{account['name']}」属于「{account['station']}」，只能登记本站的联锁设备，不能登记到「{station}」"
        owner_error = self._owner_check(values["责任人"], station)
        if owner_error:
            return None, owner_error
        conflict = self._scope_conflict(values["控制范围"])
        if conflict is not None:
            return None, self._scope_conflict_message(conflict)
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values[field]).strip() for field in REQUIRED_FIELDS})
        if str(values.get("上次检修日") or "").strip():
            entry["上次检修日"] = str(values["上次检修日"]).strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        self._sync_status(entry)
        rows.append(entry)
        return entry, "联锁设备已登记"

    def run_action(self, entry_id: int, action: str, operator: str | None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"联锁设备 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于联锁设备可执行范围"
        denied = self._permission_error(entry, operator)
        if denied:
            return None, denied
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action in HANDOVER_ACTIONS:
            # 降级、停用之后设备由操作人兜底，责任人跟着记录走
            entry["责任人"] = str(operator).strip()
        self._sync_status(entry)
        return entry, f"联锁设备已{action}"

    def change_version(self, entry_id: int, values: dict[str, Any], operator: str | None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"联锁设备 {entry_id} 不存在或已归档"
        denied = self._permission_error(entry, operator)
        if denied:
            return None, denied
        missing = [field for field in VERSION_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"版本变更需要同时提交：{'、'.join(VERSION_FIELDS)}，本次缺少：{'、'.join(missing)}"
        owner_error = self._owner_check(values["责任人"], str(entry.get("所属车站", "")).strip())
        if owner_error:
            return None, owner_error
        conflict = self._scope_conflict(values["控制范围"], exclude_id=entry_id)
        if conflict is not None:
            return None, self._scope_conflict_message(conflict)
        for field in VERSION_FIELDS:
            entry[field] = str(values[field]).strip()
        return entry, "软件版本已变更，控制范围与责任人已同步更新"

    def _find_operator(self, operator: str | None) -> dict[str, str] | None:
        name = str(operator or "").strip()
        for account in OPERATORS:
            if account["name"] == name:
                return account
        return None

    def _unknown_operator_message(self, operator: str | None) -> str:
        name = str(operator or "").strip()
        if not name:
            return "未提供操作账号，联锁设备只有所属车站与责任人能改动"
        return f"账号「{name}」不在联锁设备账号名录里，只能查看不能改动"

    def _permission_error(self, entry: dict[str, Any], operator: str | None) -> str:
        account = self._find_operator(operator)
        if account is None:
            return self._unknown_operator_message(operator)
        station = str(entry.get("所属车站", "")).strip()
        owner = str(entry.get("责任人", "")).strip()
        if account["station"] == station or account["name"] == owner:
            return ""
        return (
            f"账号「{account['name']}」属于「{account['station']}」，无权改动「{station}」的"
            f"联锁设备 {entry.get('设备编号', '')}；如需变更请联系该站责任人 {owner or '未登记'}"
        )

    def _owner_check(self, owner: Any, station: str) -> str:
        name = str(owner or "").strip()
        account = self._find_operator(name)
        if account is None:
            return f"责任人「{name}」不在联锁设备账号名录里，请填写名录内的值班账号"
        if account["station"] != station:
            return f"责任人「{name}」属于「{account['station']}」，与所属车站「{station}」对不上"
        return ""

    def _scope_conflict(self, scope: Any, exclude_id: int | None = None) -> dict[str, Any] | None:
        target = str(scope or "").strip()
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("控制范围", "")).strip() == target:
                return row
        return None

    def _scope_conflict_message(self, conflict: dict[str, Any]) -> str:
        return (
            f"控制范围「{conflict.get('控制范围', '')}」已被「{conflict.get('所属车站', '')}」的"
            f"设备 {conflict.get('设备编号', '')} 认领，一段范围只能由一个车站认领"
        )

    def _sync_status(self, entry: dict[str, Any]) -> None:
        # 设备状态始终跟着流转状态走，保证列表、详情与责任人列看到的是同一份
        entry["设备状态"] = entry.get("status", "")

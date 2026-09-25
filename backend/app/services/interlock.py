"""联锁设备业务规则：状态流转、字段校验、归属约束与筛选口径都收在这里。

归属约束（与产品口径一致）：
- 每条联锁设备固定归属一个「所属车站」和一名「责任人」；
- 只有所属车站、责任人同时匹配的账号才能改动设备（含状态动作与版本变更），
  其他账号列表与详情只读，越权提交带原因拒绝；
- 同一段「控制范围」全局只能由一个车站（一台设备）认领，重复认领直接拒绝；
- 软件版本变更时，控制范围、责任人与所属车站必须随版本一起提交、一起落库，
  杜绝版本更新后归属字段错位。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "interlock"
REQUIRED_FIELDS = ["设备编号", "联锁类型", "控制范围", "所属车站", "责任人"]
OWNER_FIELDS = ["所属车站", "责任人"]
STATUS_ORDER = ["待检修", "运用正常", "降级使用", "已停用"]
ACTION_RULES = {"确认检修": "运用正常", "降级登记": "降级使用", "停用设备": "已停用"}
NEGATIVE_ACTIONS = ["降级登记", "停用设备"]
# 版本变更必须随版本号一起核对/更新的归属字段，少一个都不受理。
VERSION_FIELDS = ["软件版本", "控制范围", "所属车站", "责任人"]
# 越权拒绝时统一带上的原因前缀，前端直接展示给值班人员。
FORBIDDEN_REASON = "越权提交已拒绝"


class InterlockService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        station: str | None = None,
        owner: str | None = None,
        scope: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if station:
            rows = [row for row in rows if station in str(row.get("所属车站", ""))]
        if owner:
            rows = [row for row in rows if owner in str(row.get("责任人", ""))]
        if scope:
            rows = [row for row in rows if scope in str(row.get("控制范围", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(
        self,
        values: dict[str, Any],
        *,
        station: str = "",
        operator: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """登记设备：归属车站默认取当前账号，控制范围不允许与既有设备重复。"""
        values = {**values}
        # 登记时归属以当前登录车站账号为准，防止替别的车站先占一段范围。
        if station:
            values["所属车站"] = station
        if operator and not str(values.get("责任人") or "").strip():
            values["责任人"] = operator
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        scope_owner, scope_message = self._find_scope_owner(str(values["控制范围"]).strip())
        if scope_owner:
            return None, scope_message
        entry: dict[str, Any] = {"id": self._next_id()}
        entry.update({field: str(values.get(field) or "").strip() for field in
                      ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "上次检修日", "责任人"]})
        if not entry["软件版本"]:
            entry["软件版本"] = "未登记"
        if not entry["上次检修日"]:
            entry["上次检修日"] = datetime.now().strftime("%Y-%m-%d")
        entry["status"] = STATUS_ORDER[0]
        entry["设备状态"] = entry["status"]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["操作履历"] = [
            self._log_entry("登记设备", entry["status"], station or entry["所属车站"],
                            entry["责任人"], "设备入库登记"),
        ]
        store.rows(MODULE).append(entry)
        return entry, ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        station: str = "",
        operator: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"联锁设备 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于联锁设备可执行范围"
        allowed, reason = self._check_ownership(entry, station, operator)
        if not allowed:
            return None, reason
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["设备状态"] = target
        # 已停用后不再挂待办；降级使用仍是在运设备，需要持续盯控。
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "确认检修":
            entry["上次检修日"] = datetime.now().strftime("%Y-%m-%d")
        # 履历按操作发生时的账号留痕：降级、停用之后再看记录，责任人就是实际操作人，
        # 不会因为设备后续改派而把旧账算到新责任人头上。
        entry.setdefault("操作履历", []).append(
            self._log_entry(action, target, station, operator,
                            "检修确认后恢复运用" if action == "确认检修" else "")
        )
        return entry, f"联锁设备已{action}"

    def change_version(
        self,
        entry_id: int,
        values: dict[str, Any],
        *,
        station: str = "",
        operator: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        """软件版本变更：版本号、控制范围、责任人与所属车站同批校验、同批更新。

        归属字段即便与现值相同也必须随版本号一起回传，缺项即视为变更单不完整，
        从入口上杜绝「只换版本、归属错站」的情况。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"联锁设备 {entry_id} 不存在或已归档"
        allowed, reason = self._check_ownership(entry, station, operator)
        if not allowed:
            return None, reason
        missing = [field for field in VERSION_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"版本变更单缺少必填字段：{'、'.join(missing)}（版本变更需与控制范围、责任人、所属车站一起更新）"
        new_version = str(values["软件版本"]).strip()
        if new_version == str(entry.get("软件版本") or "").strip():
            return None, "软件版本与当前版本一致，无需发起版本变更"
        new_scope = str(values["控制范围"]).strip()
        scope_owner, scope_message = self._find_scope_owner(new_scope, exclude_id=entry_id)
        if scope_owner:
            return None, scope_message
        old_version = entry.get("软件版本")
        old_station = entry.get("所属车站")
        old_owner = entry.get("责任人")
        old_scope = entry.get("控制范围")
        # 归属与版本一次性落库，中间没有只改一半的窗口。
        entry["软件版本"] = new_version
        entry["控制范围"] = new_scope
        entry["所属车站"] = str(values["所属车站"]).strip()
        entry["责任人"] = str(values["责任人"]).strip()
        changes = [f"软件版本 {old_version} → {new_version}"]
        if old_scope != entry["控制范围"]:
            changes.append(f"控制范围 {old_scope} → {entry['控制范围']}")
        if old_station != entry["所属车站"] or old_owner != entry["责任人"]:
            changes.append(f"归属 {old_station}/{old_owner} → {entry['所属车站']}/{entry['责任人']}")
        entry.setdefault("操作履历", []).append(
            self._log_entry("版本变更", entry["status"], station, operator, "；".join(changes))
        )
        return entry, f"联锁设备软件版本已更新至 {new_version}，控制范围与责任人已同步更新"

    def owner_summary(self) -> list[dict[str, Any]]:
        """责任人视角汇总：按所属车站 + 责任人聚合，与列表、详情共用同一份底层数据。"""
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for row in store.rows(MODULE):
            key = (str(row.get("所属车站") or "未分配车站"), str(row.get("责任人") or "未指派责任人"))
            group = groups.setdefault(key, {
                "所属车站": key[0],
                "责任人": key[1],
                "设备总数": 0,
                "运用正常": 0,
                "降级使用": 0,
                "已停用": 0,
                "待检修": 0,
                "设备编号": [],
                "控制范围": [],
            })
            group["设备总数"] += 1
            status = str(row.get("status") or "")
            if status in STATUS_ORDER:
                group[status] += 1
            group["设备编号"].append(row.get("设备编号"))
            group["控制范围"].append(row.get("控制范围"))
        return sorted(groups.values(), key=lambda item: (item["所属车站"], item["责任人"]))

    # ---- 内部规则 -------------------------------------------------

    def _next_id(self) -> int:
        return max((int(row.get("id", 0)) for row in store.rows(MODULE)), default=0) + 1

    def _check_ownership(
        self,
        entry: dict[str, Any],
        station: str,
        operator: str,
    ) -> tuple[bool, str]:
        """归属校验：所属车站与责任人必须同时匹配，只读账号带原因被拒。"""
        entry_station = str(entry.get("所属车站") or "").strip()
        entry_owner = str(entry.get("责任人") or "").strip()
        if station and entry_station != station:
            return False, (
                f"{FORBIDDEN_REASON}：设备 {entry.get('设备编号')} 归属{entry_station}，"
                f"当前账号属于{station}，非所属车站账号仅可只读查看"
            )
        if operator and entry_owner != operator:
            return False, (
                f"{FORBIDDEN_REASON}：设备 {entry.get('设备编号')} 的责任人是{entry_owner}，"
                f"当前账号为{operator}，非责任人仅可只读查看"
            )
        return True, ""

    def _find_scope_owner(
        self,
        scope: str,
        *,
        exclude_id: int | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        """控制范围唯一性校验：同一段范围只能被一个车站的一台设备认领。"""
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("控制范围") or "").strip() == scope:
                return row, (
                    f"控制范围「{scope}」已被{row.get('所属车站')}的设备 "
                    f"{row.get('设备编号')}（责任人：{row.get('责任人')}）认领，"
                    f"同一段范围只能由一个车站认领，请勿重复登记"
                )
        return None, ""

    def _log_entry(
        self,
        action: str,
        target_status: str,
        station: str,
        operator: str,
        note: str,
    ) -> dict[str, Any]:
        return {
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "动作": action,
            "目标状态": target_status,
            "操作人": operator or "未识别账号",
            "操作车站": station or "未识别车站",
            "说明": note,
        }

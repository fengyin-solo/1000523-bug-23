"""联锁设备接口：维护联锁设备，覆盖确认检修、降级登记、停用设备与软件版本变更。

写接口（状态动作、版本变更、登记）都要求带当前车站账号（values.station / values.operator，
也兼容请求头 X-Station / X-Operator），服务层按「所属车站 + 责任人」做归属校验，
越权提交会以可读原因拒绝；列表、详情、责任人汇总对任何账号只读开放。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.interlock import InterlockService

router = APIRouter(prefix="/api/interlock", tags=["联锁设备"])

service = InterlockService()

LIST_FIELDS = ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "上次检修日", "责任人", "设备状态"]
STATUSES = ["待检修", "运用正常", "降级使用", "已停用"]

# 平台内可切换的车站值班账号：账号=责任人，所属车站决定其可改动的设备范围。
STATION_ACCOUNTS = [
    {"station": "南京站", "operator": "王建国"},
    {"station": "南京站", "operator": "李志强"},
    {"station": "苏州站", "operator": "陈海峰"},
    {"station": "苏州站", "operator": "赵敏"},
]


def _account(payload: EntryPayload, x_station: str | None, x_operator: str | None) -> tuple[str, str]:
    """从请求体或请求头解析当前值班账号；两处都没有时按未登录处理（只读）。"""
    station = str(payload.values.get("station") or x_station or "").strip()
    operator = str(payload.values.get("operator") or x_operator or "").strip()
    return station, operator


@router.get("/accounts")
def list_accounts() -> dict[str, Any]:
    """给前端账号切换器提供车站值班账号清单。"""
    return {"items": STATION_ACCOUNTS}


@router.get("/owners")
def list_owners() -> dict[str, Any]:
    """责任人视角汇总：列表、详情与本页同一份底层数据，字段对不上时一处即可定位。"""
    return {"items": service.owner_summary()}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="待检修、运用正常、降级使用、已停用"),
    station: str | None = Query(default=None, description="按所属车站筛选"),
    owner: str | None = Query(default=None, description="按责任人筛选"),
    scope: str | None = Query(default=None, description="按控制范围检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号、状态、车站、责任人与控制范围过滤联锁设备列表；没有数据时返回空页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, station=station, owner=owner, scope=scope,
        page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出联锁设备清单：返回当前全量数据（只读，任何车站账号均可导出）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "interlock", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条联锁设备明细（含操作履历）；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"联锁设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(
    payload: EntryPayload,
    x_station: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """登记一条联锁设备，缺字段或控制范围被别的车站认领时说明原因而不是静默丢弃。"""
    station, operator = _account(payload, x_station, x_operator)
    if not station:
        return ActionResult(ok=False, message="未识别当前车站账号，请先切换到所属车站账号后再登记设备")
    values = payload.values.get("values") if isinstance(payload.values.get("values"), dict) else payload.values
    entry, message = service.create_entry(values, station=station, operator=operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="联锁设备已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_station: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """对单条联锁设备执行确认检修、降级登记、停用设备；越权与非法动作都拦下并说明原因。"""
    station, operator = _account(payload, x_station, x_operator)
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, station=station, operator=operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/version", response_model=ActionResult)
def change_version(
    entry_id: int,
    payload: EntryPayload,
    x_station: str | None = Header(default=None),
    x_operator: str | None = Header(default=None),
) -> ActionResult:
    """软件版本变更：版本号必须与控制范围、责任人、所属车站一起提交、一起更新。"""
    station, operator = _account(payload, x_station, x_operator)
    values = payload.values.get("values") if isinstance(payload.values.get("values"), dict) else payload.values
    entry, message = service.change_version(entry_id, values, station=station, operator=operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

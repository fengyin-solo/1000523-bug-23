"""联锁设备接口：维护联锁设备，覆盖确认检修、降级登记、停用设备与软件版本变更。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.interlock import InterlockService

router = APIRouter(prefix="/api/interlock", tags=["联锁设备"])

service = InterlockService()

LIST_FIELDS = ["设备编号", "联锁类型", "控制范围", "软件版本", "所属车站", "上次检修日", "责任人", "设备状态"]
STATUSES = ["待检修", "运用正常", "降级使用", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="待检修、运用正常、降级使用、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号与状态过滤联锁设备列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/operators")
def list_operators() -> dict[str, Any]:
    """联锁设备账号名录：前端切换值班账号用，改动设备前会先按这里校验车站归属。"""
    return {"items": service.list_operators()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出联锁设备清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "interlock", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条联锁设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"联锁设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条联锁设备：只能登记本站的设备，控制范围全网唯一；缺字段或越权时说明原因。"""
    entry, message = service.create_entry(payload.values, payload.operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条联锁设备执行确认检修、降级登记、停用设备；越权或不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/version", response_model=ActionResult)
def change_version(entry_id: int, payload: EntryPayload) -> ActionResult:
    """软件版本变更：控制范围与责任人必须一起提交、一起更新，范围重复认领会被拦下。"""
    entry, message = service.change_version(entry_id, payload.values, payload.operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)

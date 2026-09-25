"""不依赖第三方包的 ASGI 冒烟测试：直接构造 HTTP 调用走完整路由栈。

FastAPI/Pydantic 若已安装则路由行为与真实服务一致；
运行：PYTHONPATH=. python3 scripts/check_interlock_http.py
"""
from __future__ import annotations

import asyncio
import json
import sys

from app.main import app
from app.seed import SEED_ROWS


def _send(scope, receive, sent):
    async def send(message):
        sent.append(message)
    return send


async def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    payload = json.dumps(body).encode() if body is not None else b""
    raw_path, _, query = path.partition("?")
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": raw_path,
        "raw_path": raw_path.encode(),
        "query_string": query.encode(),
        "headers": [(b"content-type", b"application/json")] if body is not None else [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def receive():
        if not getattr(receive, "_done", False):
            receive._done = True
            return {"type": "http.request", "body": payload}
        return {"type": "http.disconnect"}

    sent: list[dict] = []
    await app(scope, receive, _send(scope, receive, sent))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    chunks = [m["body"] for m in sent if m["type"] == "http.response.body"]
    data = json.loads(b"".join(chunks) or b"{}")
    return status, data


async def main() -> int:
    # 重建干净数据
    from app.store import store
    store._tables = {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}

    status, data = await call("GET", "/api/interlock")
    assert status == 200 and data["total"] == 4, data

    status, data = await call("GET", "/api/interlock/accounts")
    assert status == 200 and len(data["items"]) == 4

    status, data = await call("GET", "/api/interlock/owners")
    assert status == 200 and {g["责任人"] for g in data["items"]} >= {"王建国", "李志强", "陈海峰", "赵敏"}

    status, data = await call("GET", "/api/interlock/1")
    assert status == 200 and data["所属车站"] == "南京站" and len(data["操作履历"]) == 1

    status, data = await call("GET", "/api/interlock/999")
    assert status == 404

    # 越权：跨站账号
    status, data = await call("POST", "/api/interlock/1/actions",
                              {"values": {"action": "确认检修", "station": "调度中心", "operator": "值班管理员"}})
    assert status == 200 and data["ok"] is False and "越权提交已拒绝" in data["message"], data

    # 越权：同站非责任人
    status, data = await call("POST", "/api/interlock/1/actions",
                              {"values": {"action": "确认检修", "station": "南京站", "operator": "李志强"}})
    assert data["ok"] is False and "非责任人" in data["message"]

    # 归属人确认检修照旧
    status, data = await call("POST", "/api/interlock/1/actions",
                              {"values": {"action": "确认检修", "station": "南京站", "operator": "王建国"}})
    assert data["ok"] is True and data["entry"]["status"] == "运用正常", data

    # 未登录账号登记被拒
    status, data = await call("POST", "/api/interlock", {"values": {"values": {}}})
    assert data["ok"] is False and "未识别当前车站账号" in data["message"]

    # 登记：范围唯一
    status, data = await call("POST", "/api/interlock", {"values": {
        "values": {"设备编号": "INTE-0009", "联锁类型": "计算机联锁", "控制范围": "动车所出库线"},
        "station": "南京站", "operator": "王建国",
    }})
    assert data["ok"] is False and "只能由一个车站认领" in data["message"]

    status, data = await call("POST", "/api/interlock", {"values": {
        "values": {"设备编号": "INTE-0009", "联锁类型": "计算机联锁", "控制范围": "车辆段联络线"},
        "station": "南京站", "operator": "王建国",
    }})
    assert data["ok"] is True and data["entry"]["所属车站"] == "南京站", data

    # 版本变更：缺字段 / 撞范围 / 成功 / 越权
    status, data = await call("POST", "/api/interlock/1/version", {"values": {
        "软件版本": "V9.0.0", "station": "南京站", "operator": "王建国",
    }})
    assert data["ok"] is False and "版本变更单缺少必填字段" in data["message"]

    status, data = await call("POST", "/api/interlock/1/version", {"values": {
        "软件版本": "V9.0.0", "控制范围": "2号站台进站信号机",
        "所属车站": "南京站", "责任人": "王建国",
        "station": "南京站", "operator": "王建国",
    }})
    assert data["ok"] is False and "已被苏州站" in data["message"], data

    status, data = await call("POST", "/api/interlock/1/version", {"values": {
        "软件版本": "V3.0.0", "控制范围": "1号道岔至4号道岔",
        "所属车站": "南京站", "责任人": "王建国",
        "station": "南京站", "operator": "王建国",
    }})
    assert data["ok"] is True
    assert data["entry"]["软件版本"] == "V3.0.0" and data["entry"]["控制范围"] == "1号道岔至4号道岔"

    status, data = await call("POST", "/api/interlock/1/version", {"values": {
        "软件版本": "V3.1.0", "控制范围": "1号道岔至4号道岔",
        "所属车站": "南京站", "责任人": "王建国",
        "station": "苏州站", "operator": "陈海峰",
    }})
    assert data["ok"] is False and "越权" in data["message"]

    # 筛选：status / station / scope
    status, data = await call("GET", "/api/interlock?status=%E5%B7%B2%E5%81%9C%E7%94%A8")
    assert all(row["status"] == "已停用" for row in data["items"]) and data["total"] >= 1

    # 导出仍对只读账号开放
    status, data = await call("GET", "/api/interlock/export")
    assert status == 200 and data["total"] == 5

    print("ALL HTTP SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

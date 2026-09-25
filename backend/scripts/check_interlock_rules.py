"""联锁归属规则的端到端校验：直接驱动服务层，不依赖 FastAPI / 网络。

运行：python3 scripts/check_interlock_rules.py
"""
from __future__ import annotations

import sys

from app.services.interlock import InterlockService
from app.store import store

# 每个用例都从种子数据重建仓库，避免用例间串状态。
def reset() -> None:
    from app import seed
    store._tables = {name: [dict(row) for row in rows] for name, rows in seed.SEED_ROWS.items()}


def main() -> int:
    svc = InterlockService()

    # 1. 初始列表 4 台、字段一致
    reset()
    rows, total = svc.list_entries(page=1, size=200)
    assert total == 4, total
    assert all(row["设备状态"] == row["status"] for row in rows), "列表状态列与真实状态必须一致"

    # 2. 跨站账号不能改设备，拒绝原因可读
    entry, message = svc.run_action(1, "确认检修", station="调度中心", operator="值班管理员")
    assert entry is None and "越权" in message, message
    assert "非所属车站" in message, message

    # 3. 同站但非责任人同样拒绝
    entry, message = svc.run_action(1, "确认检修", station="南京站", operator="李志强")
    assert entry is None and "责任人" in message, message

    # 4. 责任人执行确认检修照旧：状态、检修日、履历操作人
    entry, message = svc.run_action(1, "确认检修", station="南京站", operator="王建国")
    assert entry is not None and entry["status"] == "运用正常", message
    assert entry["设备状态"] == "运用正常"
    assert entry["上次检修日"]
    assert entry["操作履历"][-1]["操作人"] == "王建国"
    assert entry["操作履历"][-1]["动作"] == "确认检修"

    # 5. 降级使用：履历记录实际操作人，abnormal 置位
    entry, _ = svc.run_action(2, "降级登记", station="南京站", operator="李志强")
    assert entry["status"] == "降级使用" and entry["abnormal"] is True
    assert entry["操作履历"][-1]["操作人"] == "李志强"

    # 6. 停用：pending 取消、履历留痕
    entry, _ = svc.run_action(2, "停用设备", station="南京站", operator="李志强")
    assert entry["status"] == "已停用" and entry["pending"] is False
    assert entry["操作履历"][-1]["操作人"] == "李志强"
    assert entry["操作履历"][-2]["动作"] == "降级登记", "老履历不被覆盖"

    # 7. 版本变更缺归属字段：拒绝并说明
    entry, message = svc.change_version(
        1, {"软件版本": "V3.0.0"}, station="南京站", operator="王建国",
    )
    assert entry is None and "缺少必填字段" in message, message

    # 8. 版本未变化：拒绝
    entry_same, message_same = svc.change_version(
        1, {"软件版本": store.find("interlock", 1)["软件版本"],
            "控制范围": "1号道岔至3号道岔", "所属车站": "南京站", "责任人": "王建国"},
        station="南京站", operator="王建国",
    )
    assert entry_same is None and "无需发起版本变更" in message_same, message_same

    # 9. 控制范围撞别的车站：唯一性拒绝
    entry, message = svc.change_version(
        1, {"软件版本": "V3.0.0", "控制范围": "动车所出库线",
            "所属车站": "南京站", "责任人": "王建国"},
        station="南京站", operator="王建国",
    )
    assert entry is None and "只能由一个车站认领" in message, message

    # 10. 版本变更成功：版本、范围、车站、责任人原子更新
    entry, message = svc.change_version(
        1, {"软件版本": "V3.0.0", "控制范围": "1号道岔至4号道岔",
            "所属车站": "南京站", "责任人": "王建国"},
        station="南京站", operator="王建国",
    )
    assert entry is not None, message
    assert entry["软件版本"] == "V3.0.0"
    assert entry["控制范围"] == "1号道岔至4号道岔"
    assert entry["所属车站"] == "南京站" and entry["责任人"] == "王建国"
    log = entry["操作履历"][-1]
    assert log["动作"] == "版本变更" and "V2.1.0" in log["说明"] and "V3.0.0" in log["说明"]

    # 11. 版本变更同样受归属约束
    entry, message = svc.change_version(
        1, {"软件版本": "V3.1.0", "控制范围": "1号道岔至4号道岔",
            "所属车站": "南京站", "责任人": "王建国"},
        station="苏州站", operator="陈海峰",
    )
    assert entry is None and "越权" in message

    # 12. 改派归属（同设备换责任人/车站，范围不与他人重复）后旧责任人失权、新责任人有权
    entry, message = svc.change_version(
        1, {"软件版本": "V3.0.1", "控制范围": "1号道岔至4号道岔",
            "所属车站": "苏州站", "责任人": "陈海峰"},
        station="南京站", operator="王建国",
    )
    assert entry is not None, message
    entry, _ = svc.run_action(1, "降级登记", station="南京站", operator="王建国")
    assert entry is None, "改派后旧责任人必须失去改动权"
    entry, _ = svc.run_action(1, "确认检修", station="苏州站", operator="陈海峰")
    assert entry is not None and entry["status"] == "运用正常"

    # 13. 登记：车站固定为当前账号、范围重复拒绝、唯一范围放行
    entry, message = svc.create_entry(
        {"设备编号": "INTE-0009", "联锁类型": "计算机联锁", "控制范围": "动车所出库线"},
        station="南京站", operator="王建国",
    )
    assert entry is None and "只能由一个车站认领" in message
    entry, message = svc.create_entry(
        {"设备编号": "INTE-0009", "联锁类型": "计算机联锁",
         "控制范围": "车辆段联络线", "责任人": "王建国"},
        station="南京站", operator="王建国",
    )
    assert entry is not None, message
    assert entry["所属车站"] == "南京站" and entry["责任人"] == "王建国"
    assert entry["status"] == "待检修" and entry["设备状态"] == "待检修"

    # 14. 登记缺必填字段
    entry, message = svc.create_entry({"设备编号": "X"}, station="南京站", operator="王建国")
    assert entry is None and "缺少必填字段" in message

    # 15. 未登录车站账号不允许登记（路由层规则，这里模拟 service 也给不到归属）
    entry, message = svc.create_entry(
        {"设备编号": "INTE-0010", "联锁类型": "计算机联锁",
         "控制范围": "北咽喉", "所属车站": "", "责任人": ""},
        station="", operator="",
    )
    assert entry is None and "所属车站" in message

    # 16. 筛选口径
    _, total_sz = svc.list_entries(station="苏州站")
    suzhou_rows, _ = svc.list_entries(station="苏州站", size=200)
    assert {row["所属车站"] for row in suzhou_rows} == {"苏州站"}
    stopped, total_stop = svc.list_entries(status="已停用", size=200)
    assert all(row["status"] == "已停用" for row in stopped)
    scoped, _ = svc.list_entries(scope="动车所", size=200)
    assert all("动车所" in row["控制范围"] for row in scoped) and scoped

    # 17. 责任人汇总：与列表同源、计数正确
    groups = svc.owner_summary()
    g = next(g for g in groups if g["所属车站"] == "苏州站" and g["责任人"] == "赵敏")
    assert g["设备总数"] == 1 and g["已停用"] == 1, g
    assert "动车所出库线" in g["控制范围"]
    assert sum(g["设备总数"] for g in groups) == 5, groups  # 4 种子 + 1 新登记

    # 18. 详情读取：履历完整、状态字段对得上
    detail = svc.get_entry(3)
    assert detail["设备状态"] == detail["status"] == "降级使用"
    assert [log["动作"] for log in detail["操作履历"]][-1] == "降级登记"

    # 19. 非法动作 / 不存在设备
    assert svc.run_action(999, "确认检修")[0] is None
    assert svc.run_action(3, "任意操作", station="苏州站", operator="陈海峰")[0] is None

    print("ALL INTERLOCK RULE CHECKS PASSED (19 groups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

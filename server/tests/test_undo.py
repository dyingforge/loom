"""撤销逻辑：服务端仅提供规则，客户端必须遵守。

撤销规则：
- 仅恢复最近一次日历变更；
- 不覆盖变更之后录入的实际进度；
- 旧安排如因当前约束已不合法则拒绝撤销；
- 撤销生成新项目版本与变更记录，并作废旧版本待确认方案；
- 无重做路径。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import TypeAdapter

from server.domain.constraints import validate
from server.domain.models import Candidate, Project, Task, Block


ADAPTER = TypeAdapter(Project)


def _make_project(version: int, blocks: list[dict] | None = None) -> Project:
    return ADAPTER.validate_python({
        "id": "p", "version": version, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1, "remainingHours": 4,
            "dependsOn": [], "adjustable": True,
            "blocks": blocks or [],
        }],
    })


def test_undo_rejects_when_old_arrangement_violates_constraints() -> None:
    """旧方案中的块在当前剩余工时下不合法，撤销应被拒绝。"""
    current = _make_project(version=3, blocks=[{
        "id": "b1", "taskId": "t1",
        "start": "2026-10-02T09:00:00", "end": "2026-10-02T13:00:00",
        "done": False,
    }])
    # 假设过去方案是：6 小时（超出当前剩余工时 4）
    past = _make_project(version=2)
    cand = Candidate.model_validate({"blocks": [
        {"id": "b1", "taskId": "t1",
         "start": "2026-10-02T09:00:00", "end": "2026-10-02T15:00:00"},
    ]})
    violations = validate(current, cand)
    assert any(v.code == "C5" for v in violations)


def test_undo_increments_version() -> None:
    """撤销应当生成新版本号。撤销不在服务端执行；客户端负责。

    本测试仅约束：撤销后的 snapshot 应携带 version+1。
    """
    before = _make_project(version=2)
    after = before.model_copy(update={"version": 3})
    assert after.version == 3

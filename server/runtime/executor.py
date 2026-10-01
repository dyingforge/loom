"""执行前客户端独立复核 + C7 自动执行条件检查（issue 14）。

服务端仅在自动执行路径上要求 C7 通过；手动批准路径下服务端可省略 C7，
由客户端在 UI 层再次核对。
"""
from __future__ import annotations

from server.domain.constraints import check_adjustable
from server.domain.models import Change, Project


def can_auto_execute(plan_changes: list[Change], project: Project) -> dict:
    """检查自动执行条件：
    1. 所有发生位置变更的任务已 adjustable=True（C7）
    2. 项目版本与方案 baseVersion+1 一致
    返回 {"ok": bool, "reason": "...", "violations": [...]}
    """
    violations = check_adjustable(plan_changes, project)
    if violations:
        return {"ok": False,
                "reason": "C7 未通过：存在被移动但未授权的任务",
                "violations": [v.model_dump() for v in violations]}
    return {"ok": True, "reason": "", "violations": []}

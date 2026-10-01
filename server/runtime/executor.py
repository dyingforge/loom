from __future__ import annotations

from datetime import datetime

from server.domain.constraints import check_adjustable, validate
from server.domain.models import Candidate, Plan, Project
from server.runtime.plans import apply_plan


def can_auto_execute(plan: Plan, project: Project, now: datetime) -> dict:
    if not project.autoAdjust:
        return {"ok": False, "reason": "项目自动调整尚未授权"}
    if plan.baseVersion != project.version:
        return {"ok": False, "reason": "项目版本已经变化"}
    if plan.risks or plan.exceptions:
        return {"ok": False, "reason": "方案存在风险或例外，需要明确批准"}
    target = apply_plan(project, plan)
    candidate = Candidate(blocks=[block.model_dump() for task in target.tasks for block in task.blocks])
    violations = validate(project, candidate, now) + check_adjustable(plan.changes, project)
    return {"ok": not violations, "reason": "；".join(item.detail for item in violations)}

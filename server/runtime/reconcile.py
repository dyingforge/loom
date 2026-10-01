from __future__ import annotations

from datetime import datetime

from server.domain.models import Candidate, Plan, Project, Receipt
from server.domain.constraints import validate
from server.runtime.plans import apply_plan


def comparable(project: Project):
    data = project.model_dump(mode="json")
    for task in data["tasks"]:
        task["blocks"] = sorted(task["blocks"], key=lambda block: block["id"])
    return data


def verify(plan: dict, version_before: int, version_after: int,
           readback: Project, before: Project) -> Receipt:
    approved = Plan.model_validate(plan)
    reason = ""
    if approved.baseVersion != version_before or before.version != version_before:
        reason = "批准版本与执行前项目版本不一致"
    elif version_after != version_before + 1 or readback.version != version_after:
        reason = "保存后的版本必须增加一次且与回读版本一致"
    elif comparable(apply_plan(before, approved)) != comparable(readback):
        reason = "完整回读项目与批准方案不一致"
    return Receipt(planId=approved.planId, versionBefore=version_before,
                   versionAfter=version_after, readbackSnapshot=readback,
                   status="not_verified" if reason else "verified", reason=reason)


def verify_calendar(before: Project, draft: Project, plan: Plan,
                    readback: Project, now: datetime) -> Receipt:
    reasons = []
    if before.id != draft.id or before.version != draft.version or plan.baseVersion != before.version:
        reasons.append("候选计划与当前日历的编号或版本不一致")
    if readback.version != before.version + 1:
        reasons.append("保存后的日历版本必须增加一次")
    if (before.fixedEvents != draft.fixedEvents or before.workHours != draft.workHours
            or before.restDays != draft.restDays):
        reasons.append("候选计划修改了已经保存的工作时间或固定日程")
    new_tasks = {task.id: task for task in readback.tasks}
    new_blocks = {block.id: block for task in readback.tasks for block in task.blocks}
    for task in before.tasks:
        replacement = new_tasks.get(task.id)
        if task.done and (replacement is None or not replacement.done
                          or replacement.remainingHours != task.remainingHours):
            reasons.append("已经完成的任务记录发生变化：" + task.id)
        for block in task.blocks:
            if (block.done or block.start < now) and new_blocks.get(block.id) != block:
                reasons.append("已经开始或完成的日历安排发生变化：" + block.id)
    if not reasons and comparable(apply_plan(draft, plan)) != comparable(readback):
        reasons.append("完整回读任务与获准候选计划不一致")
    candidate = Candidate(blocks=[block.model_dump() for task in readback.tasks for block in task.blocks])
    reasons.extend(item.detail for item in validate(draft, candidate, now))
    return Receipt(planId=plan.planId, versionBefore=before.version,
                   versionAfter=readback.version, readbackSnapshot=readback,
                   status="not_verified" if reasons else "verified", reason="；".join(reasons))

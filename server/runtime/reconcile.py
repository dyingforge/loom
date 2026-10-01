from __future__ import annotations

from server.domain.models import Plan, Project, Receipt
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

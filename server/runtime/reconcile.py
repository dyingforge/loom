"""执行后核验：对比批准方案、版本与回读快照。

服务端核验失败时返回 not_verified；客户端不显示「已核验」。
"""
from __future__ import annotations

from server.domain.models import Project, Receipt


def verify(plan: dict, version_before: int, version_after: int,
           readback: Project) -> Receipt:
    """对比：版本一致 + 方案变更块的 after 集合 ⊆ 回读 Project 现有块。"""
    if plan.get("baseVersion") != version_before:
        return Receipt(
            planId=plan["planId"], versionBefore=version_before,
            versionAfter=version_after, readbackSnapshot=readback,
            status="not_verified",
            reason="baseVersion 与 versionBefore 不一致",
        )
    expected: dict[str, dict] = {}
    for ch in plan.get("changes") or []:
        if ch.get("after"):
            expected[ch["blockId"]] = {
                "start": ch["after"]["start"],
                "end": ch["after"]["end"],
                "done": ch["after"].get("done", False),
                "taskId": ch["after"]["taskId"],
            }
    actual: dict[str, dict] = {}
    for t in readback.tasks:
        for b in t.blocks:
            actual[b.id] = {
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),
                "done": b.done,
                "taskId": b.taskId,
            }
    missing = [bid for bid in expected if bid not in actual]
    mismatched = [
        bid for bid in expected if bid in actual and (
            actual[bid]["start"] != expected[bid]["start"]
            or actual[bid]["end"] != expected[bid]["end"]
        )
    ]
    if missing or mismatched:
        return Receipt(
            planId=plan["planId"], versionBefore=version_before,
            versionAfter=version_after, readbackSnapshot=readback,
            status="not_verified",
            reason=f"回读不一致: missing={missing}, mismatched={mismatched}",
        )
    return Receipt(
        planId=plan["planId"], versionBefore=version_before,
        versionAfter=version_after, readbackSnapshot=readback,
        status="verified", reason="",
    )

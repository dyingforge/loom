"""硬约束校验（C1–C7），无 IO。

按 `constraints.md` 实现。`validate(project, candidate)` 返回 Violation 列表，
空列表表示通过。`check_adjustable(plan, project)` 用于 C7 自动路径。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .models import Block, Candidate, CandidateBlock, Project, Violation


def _hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def _within_workhours(block_start: datetime, block_end: datetime,
                      work_start_h: int, work_start_m: int,
                      work_end_h: int, work_end_m: int) -> bool:
    s = (block_start.hour, block_start.minute, block_start.second)
    e = (block_end.hour, block_end.minute, block_end.second)
    if (block_start.hour, block_start.minute) < (work_start_h, work_start_m):
        return False
    if (block_end.hour, block_end.minute) > (work_end_h, work_end_m):
        return False
    # 块必须在同一日历日内
    if block_start.date() != block_end.date():
        return False
    if s > e:  # 实际不可能，但显式拒绝
        return False
    return True


def _touches_rest_day(start: datetime, end: datetime, rest_days: set[int]) -> bool:
    d = start.date()
    last = end.date()
    while d <= last:
        if d.weekday() in rest_days:
            return True
        d += timedelta(days=1)
    return False


def _overlap(a_start: datetime, a_end: datetime,
             b_start: datetime, b_end: datetime) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def validate(project: Project, candidate: Candidate) -> list[Violation]:
    """逐条核对 C1–C6；C7 在自动路径单独检查。"""
    violations: list[Violation] = []

    tasks_by_id = {t.id: t for t in project.tasks}
    work = project.workHours
    ws_h, ws_m = (int(x) for x in work.start.split(":"))
    we_h, we_m = (int(x) for x in work.end.split(":"))
    rest_days = set(project.restDays)
    fixed = project.fixedEvents

    parsed: list[CandidateBlock] = []
    for b in candidate.blocks:
        tid = b.taskId
        # C1 边界检查：done 任务不能再排
        task = tasks_by_id.get(tid)
        if task and task.done:
            violations.append(Violation(
                code="C1", blockId=tid,
                detail="已完成任务不再排程",
            ))
            continue
        # C3 工作时段 + 休息日
        if not _within_workhours(b.start, b.end, ws_h, ws_m, we_h, we_m):
            violations.append(Violation(
                code="C3", blockId=tid,
                detail=f"块未完整落在工作时段 {work.start}-{work.end} 内",
            ))
            continue
        if _touches_rest_day(b.start, b.end, rest_days):
            violations.append(Violation(
                code="C3", blockId=tid,
                detail=f"块落在休息日 {b.start.date().isoformat()} "
                       f"– {b.end.date().isoformat()}",
            ))
            continue
        # C2 固定日程
        conflict = None
        for fe in fixed:
            if _overlap(b.start, b.end, fe.start, fe.end):
                conflict = fe
                break
        if conflict is not None:
            violations.append(Violation(
                code="C2", blockId=tid,
                detail=f"与固定日程 {conflict.id} 冲突",
            ))
            continue
        parsed.append(b)

    # C6 重叠（端点重合视为重叠）
    ordered = sorted(parsed, key=lambda x: (x.start, x.end))
    for i in range(1, len(ordered)):
        prev = ordered[i - 1]
        cur = ordered[i]
        if cur.start < prev.end:
            violations.append(Violation(
                code="C6", blockId=cur.taskId,
                detail=f"与任务 {prev.taskId} 的块时间重叠",
            ))

    # C5 工时总量
    by_task: dict[str, float] = {}
    for b in parsed:
        by_task[b.taskId] = by_task.get(b.taskId, 0.0) + _hours(b.start, b.end)
    for tid, total in by_task.items():
        task = tasks_by_id.get(tid)
        if task is None:
            violations.append(Violation(
                code="C0", blockId=tid,
                detail="候选引用了不存在的任务",
            ))
            continue
        rem = float(task.remainingHours)
        # 浮点容差 1e-6
        if abs(total - rem) > 1e-6:
            violations.append(Violation(
                code="C5", blockId=tid,
                detail=f"块总时长 {total:.3f} ≠ 剩余工时 {rem}",
            ))

    # C1 已完成块不动：候选不能动现有已完成的块；通过比对 project.tasks[*].blocks
    for task in project.tasks:
        for existing in task.blocks:
            if not existing.done:
                continue
            # 若候选中包含同 id 的块且时间不同，违规
            for b in parsed:
                if b.id is not None and b.id == existing.id:
                    if b.start != existing.start or b.end != existing.end:
                        violations.append(Violation(
                            code="C1", blockId=task.id,
                            detail=f"已完成块 {existing.id} 被移动",
                        ))

    # C4 依赖顺序
    task_latest_end: dict[str, datetime] = {}
    task_earliest_start: dict[str, datetime] = {}
    for b in parsed:
        if b.taskId not in task_latest_end or b.end > task_latest_end[b.taskId]:
            task_latest_end[b.taskId] = b.end
        if b.taskId not in task_earliest_start or b.start < task_earliest_start[b.taskId]:
            task_earliest_start[b.taskId] = b.start
    for tid, end in task_latest_end.items():
        task = tasks_by_id.get(tid)
        if task is None:
            continue
        for dep in task.dependsOn:
            dep_task = tasks_by_id.get(dep)
            if dep_task is None:
                violations.append(Violation(
                    code="C4", blockId=tid,
                    detail=f"依赖任务 {dep} 不存在",
                ))
                continue
            if dep_task.done:
                continue  # 已完成无需排程
            dep_end = task_latest_end.get(dep)
            if dep_end is None:
                # 前驱未排程：若前驱剩余工时为 0 也算 OK；否则违规
                if dep_task.remainingHours > 0:
                    violations.append(Violation(
                        code="C4", blockId=tid,
                        detail=f"依赖任务 {dep} 尚未排程",
                    ))
                continue
            earliest_start = task_earliest_start.get(tid, end)
            if earliest_start < dep_end:
                violations.append(Violation(
                    code="C4", blockId=tid,
                    detail=f"早于依赖任务 {dep} 的完成时间",
                ))

    return violations


def check_adjustable(plan_changes: Iterable, project: Project) -> list[Violation]:
    """C7 自动路径：所有发生位置变更的任务均需 adjustable=True。"""
    out: list[Violation] = []
    tasks_by_id = {t.id: t for t in project.tasks}
    for ch in plan_changes:
        # ch.blockId 形式：task_id 或 task_id:block_id
        tid = ch.blockId.split(":", 1)[0]
        task = tasks_by_id.get(tid)
        if task is None:
            continue
        if ch.before is not None and ch.after is not None:
            if (ch.before.start != ch.after.start or ch.before.end != ch.after.end):
                if not task.adjustable:
                    out.append(Violation(
                        code="C7", blockId=tid,
                        detail="被移动任务未标记可调整",
                    ))
    return out

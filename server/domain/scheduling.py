"""调度域函数：可用时段、方案差异。无 IO。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import Block, Candidate, CandidateBlock, Plan, Project


def _workdays(start: datetime, end: datetime, rest_days: set[int]) -> list[tuple[datetime, datetime]]:
    """返回 [start, end] 内每天的工作时段。"""
    out: list[tuple[datetime, datetime]] = []
    d = start.date()
    last = end.date()
    while d <= last:
        if d.weekday() not in rest_days:
            ws = datetime.combine(d, datetime.min.time()).replace(
                hour=start.hour if d == start.date() else 0)
            # 使用 project.workHours 由调用方传入；这里只生成日期边界
            out.append((datetime.combine(d, datetime.min.time()),
                        datetime.combine(d, datetime.max.time())))
        d += timedelta(days=1)
    return out


def free_slots(project: Project, range_start: datetime,
               range_end: datetime) -> list[tuple[datetime, datetime]]:
    """返回范围内扣除固定日程、已完成块、休息日后的空闲时段。

    实现说明：先按工作时段切分每天为 [work.start, work.end] 的区间，然后
    减去所有已锁定的占用（固定日程与已完成块），剩下的合并连续区间即为
    空闲时段。返回值为按起始时间排序的不重叠区间。
    """
    if range_end <= range_start:
        return []
    ws_h, ws_m = (int(x) for x in project.workHours.start.split(":"))
    we_h, we_m = (int(x) for x in project.workHours.end.split(":"))
    rest_days = set(project.restDays)

    # 1. 生成每天的工作时段（含跨日裁剪）
    daily: list[tuple[datetime, datetime]] = []
    d = range_start.date()
    last = range_end.date()
    while d <= last:
        if d.weekday() not in rest_days:
            day_start = datetime.combine(d, datetime.min.time()).replace(hour=ws_h, minute=ws_m)
            day_end = datetime.combine(d, datetime.min.time()).replace(hour=we_h, minute=we_m)
            day_start = max(day_start, range_start)
            day_end = min(day_end, range_end)
            if day_end > day_start:
                daily.append((day_start, day_end))
        d += timedelta(days=1)

    # 2. 锁定占用：固定日程 + 已完成块
    locked: list[tuple[datetime, datetime]] = []
    for fe in project.fixedEvents:
        locked.append((fe.start, fe.end))
    for t in project.tasks:
        for b in t.blocks:
            if b.done:
                locked.append((b.start, b.end))

    # 3. 逐天求差集（线性扫描，量级小）
    free: list[tuple[datetime, datetime]] = []
    for seg_start, seg_end in daily:
        # 该天内的占用裁剪到 [seg_start, seg_end]
        day_locked: list[tuple[datetime, datetime]] = []
        for ls, le in locked:
            cs = max(ls, seg_start)
            ce = min(le, seg_end)
            if ce > cs:
                day_locked.append((cs, ce))
        day_locked.sort()
        cur = seg_start
        for ls, le in day_locked:
            if ls > cur:
                free.append((cur, ls))
            cur = max(cur, le)
        if cur < seg_end:
            free.append((cur, seg_end))
    free.sort()
    return free


def diff(project: Project, candidate: Candidate) -> Plan:
    """对比 project 现有块与 candidate，生成 Plan（包含 changes）。"""
    existing: dict[str, Block] = {}
    for t in project.tasks:
        for b in t.blocks:
            existing[b.id] = b

    candidate_blocks: dict[str, Block] = {}
    for i, cb in enumerate(candidate.blocks):
        bid = cb.id or f"{cb.taskId}-{i}"
        candidate_blocks[bid] = Block(
            id=bid, taskId=cb.taskId,
            start=cb.start, end=cb.end, done=False,
        )

    changes = []
    # 删除：存在于 existing 但不在 candidate_blocks
    for bid, b in existing.items():
        if bid not in candidate_blocks:
            changes.append({"blockId": bid, "before": b, "after": None})
    # 新增/修改
    for bid, nb in candidate_blocks.items():
        if bid not in existing:
            changes.append({"blockId": bid, "before": None, "after": nb})
        else:
            ob = existing[bid]
            if ob.start != nb.start or ob.end != nb.end:
                changes.append({"blockId": bid, "before": ob, "after": nb})

    return Plan(
        planId=f"plan-{project.version + 1}",
        baseVersion=project.version,
        changes=changes,  # type: ignore[arg-type]
        risks=[],
        exceptions=[],
        rationale="",
    )

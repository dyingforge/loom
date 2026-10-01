"""客户端领域：独立实现的 C1–C7 校验器（与服务器同源但代码独立维护）。

通过同一份 `vectors/` 验证。运行：`python3 -m pytest client/tests/`。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def _within_workhours(block_start: datetime, block_end: datetime,
                      ws_h: int, ws_m: int, we_h: int, we_m: int) -> bool:
    if (block_start.hour, block_start.minute) < (ws_h, ws_m):
        return False
    if (block_end.hour, block_end.minute) > (we_h, we_m):
        return False
    if block_start.date() != block_end.date():
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


def _overlap(a_s: datetime, a_e: datetime, b_s: datetime, b_e: datetime) -> bool:
    return max(a_s, b_s) < min(a_e, b_e)


def validate(project: dict, candidate: dict) -> list[dict]:
    """客户端独立校验；返回 [{code, blockId, detail}]。"""
    violations: list[dict] = []
    tasks_by_id = {t["id"]: t for t in project["tasks"]}
    work = project["workHours"]
    ws_h, ws_m = (int(x) for x in work["start"].split(":"))
    we_h, we_m = (int(x) for x in work["end"].split(":"))
    rest_days = set(project.get("restDays") or [])
    fixed = project.get("fixedEvents") or []

    parsed: list[dict] = []
    for b in candidate.get("blocks") or []:
        tid = b["taskId"]
        task = tasks_by_id.get(tid)
        if task and task.get("done"):
            violations.append({"code": "C1", "blockId": tid,
                               "detail": "已完成任务不再排程"})
            continue
        s = datetime.fromisoformat(b["start"])
        e = datetime.fromisoformat(b["end"])
        if not _within_workhours(s, e, ws_h, ws_m, we_h, we_m):
            violations.append({"code": "C3", "blockId": tid,
                               "detail": f"块未完整落在工作时段 {work['start']}-{work['end']} 内"})
            continue
        if _touches_rest_day(s, e, rest_days):
            violations.append({"code": "C3", "blockId": tid,
                               "detail": f"块落在休息日 {s.date().isoformat()} – {e.date().isoformat()}"})
            continue
        conflict = None
        for fe in fixed:
            fs = datetime.fromisoformat(fe["start"])
            fe_ = datetime.fromisoformat(fe["end"])
            if _overlap(s, e, fs, fe_):
                conflict = fe
                break
        if conflict is not None:
            violations.append({"code": "C2", "blockId": tid,
                               "detail": f"与固定日程 {conflict['id']} 冲突"})
            continue
        parsed.append(b)

    # C6 重叠（端点重合视为重叠）
    ordered = sorted(parsed, key=lambda x: (x["start"], x["end"]))
    for i in range(1, len(ordered)):
        prev = ordered[i - 1]
        cur = ordered[i]
        cur_s = datetime.fromisoformat(cur["start"])
        prev_e = datetime.fromisoformat(prev["end"])
        if cur_s < prev_e:
            violations.append({"code": "C6", "blockId": cur["taskId"],
                               "detail": f"与任务 {prev['taskId']} 的块时间重叠"})

    # C5 工时总量
    by_task: dict[str, float] = {}
    for b in parsed:
        tid = b["taskId"]
        s = datetime.fromisoformat(b["start"])
        e = datetime.fromisoformat(b["end"])
        by_task[tid] = by_task.get(tid, 0.0) + _hours(s, e)
    for tid, total in by_task.items():
        task = tasks_by_id.get(tid)
        if task is None:
            violations.append({"code": "C0", "blockId": tid,
                               "detail": "候选引用了不存在的任务"})
            continue
        rem = float(task["remainingHours"])
        if abs(total - rem) > 1e-6:
            violations.append({"code": "C5", "blockId": tid,
                               "detail": f"块总时长 {total:.3f} ≠ 剩余工时 {rem}"})

    # C1 移动已完成块
    for task in project["tasks"]:
        for existing in task.get("blocks") or []:
            if not existing.get("done"):
                continue
            eid = existing["id"]
            for b in parsed:
                if b.get("id") == eid:
                    if (b["start"] != existing["start"]
                            or b["end"] != existing["end"]):
                        violations.append({"code": "C1", "blockId": task["id"],
                                           "detail": f"已完成块 {eid} 被移动"})

    # C4 依赖顺序
    task_latest_end: dict[str, datetime] = {}
    task_earliest_start: dict[str, datetime] = {}
    for b in parsed:
        tid = b["taskId"]
        e = datetime.fromisoformat(b["end"])
        s = datetime.fromisoformat(b["start"])
        if tid not in task_latest_end or e > task_latest_end[tid]:
            task_latest_end[tid] = e
        if tid not in task_earliest_start or s < task_earliest_start[tid]:
            task_earliest_start[tid] = s
    for tid in task_latest_end:
        task = tasks_by_id.get(tid)
        if task is None:
            continue
        for dep in task.get("dependsOn") or []:
            dep_task = tasks_by_id.get(dep)
            if dep_task is None:
                violations.append({"code": "C4", "blockId": tid,
                                   "detail": f"依赖任务 {dep} 不存在"})
                continue
            if dep_task.get("done"):
                continue
            dep_end = task_latest_end.get(dep)
            if dep_end is None:
                if dep_task["remainingHours"] > 0:
                    violations.append({"code": "C4", "blockId": tid,
                                       "detail": f"依赖任务 {dep} 尚未排程"})
                continue
            earliest_start = task_earliest_start.get(tid, task_latest_end[tid])
            if earliest_start < dep_end:
                violations.append({"code": "C4", "blockId": tid,
                                   "detail": f"早于依赖任务 {dep} 的完成时间"})

    return violations


def analyze(project: dict) -> dict:
    """结构检查：依赖环、缺失引用。"""
    cycles: list[list[str]] = []
    graph: dict[str, list[str]] = {t["id"]: list(t.get("dependsOn") or [])
                                   for t in project["tasks"]}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    path: list[str] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for nb in graph.get(node, []):
            if nb not in color:
                continue
            if color[nb] == GRAY:
                idx = path.index(nb)
                cycles.append(path[idx:] + [nb])
            elif color[nb] == WHITE:
                dfs(nb)
        path.pop()
        color[node] = BLACK

    for n in list(graph):
        if color[n] == WHITE:
            dfs(n)

    ids = {t["id"] for t in project["tasks"]}
    missing = [t["id"] for t in project["tasks"]
               if any(d not in ids for d in t.get("dependsOn") or [])]

    return {"cycles": cycles, "missingRefs": missing}

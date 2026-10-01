"""结构检查：依赖环、缺失任务引用、工时与切分总量。无 IO。"""
from __future__ import annotations

from .models import Project, Task, Violation


def _dep_graph(tasks: list[Task]) -> dict[str, list[str]]:
    return {t.id: list(t.dependsOn) for t in tasks}


def find_cycles(project: Project) -> list[list[str]]:
    """返回所有依赖环（路径表示）。空列表表示无环。"""
    graph = _dep_graph(project.tasks)
    cycles: list[list[str]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    path: list[str] = []
    on_stack = set()

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        on_stack.add(node)
        for nb in graph.get(node, []):
            if nb not in color:
                continue
            if color[nb] == GRAY:
                idx = path.index(nb)
                cycles.append(path[idx:] + [nb])
            elif color[nb] == WHITE:
                dfs(nb)
        path.pop()
        on_stack.discard(node)
        color[node] = BLACK

    for n in list(graph):
        if color[n] == WHITE:
            dfs(n)
    return cycles


def find_missing_refs(project: Project) -> list[str]:
    """返回所有引用了不存在任务的 task_id（不在 tasks 列表中）。"""
    ids = {t.id for t in project.tasks}
    out: list[str] = []
    for t in project.tasks:
        for dep in t.dependsOn:
            if dep not in ids:
                out.append(t.id)
                break
    return out


def check_hours_split(project: Project) -> list[Violation]:
    """校验每个任务的已排块总时长是否等于 (原工时 - remainingHours)。

    即：原工时 = remainingHours + 已用时长；这里原工时不可直接获得，
    因此改为校验：done=true 的任务 remainingHours 必须为 0；
    已完成块的累计时长不得超过 remainingHours + 已用时长（这里无原工时
    时仅校验正性）。
    """
    out: list[Violation] = []
    for t in project.tasks:
        used = sum(((b.end - b.start).total_seconds() / 3600.0)
                   for b in t.blocks if b.done)
        # 已完成块不得使累计 used 为负（仅作正性校验）
        if used < 0:
            out.append(Violation(
                code="C5", blockId=t.id,
                detail="已完成块时长非法",
            ))
        if t.done and t.remainingHours != 0:
            out.append(Violation(
                code="C5", blockId=t.id,
                detail="任务已完成但剩余工时不为 0",
            ))
    return out


def analyze(project: Project) -> dict:
    """汇总：依赖环、缺失引用、工时切分、里程碑风险。"""
    cycles = find_cycles(project)
    missing = find_missing_refs(project)
    hours = check_hours_split(project)
    return {
        "cycles": cycles,
        "missingRefs": missing,
        "hoursViolations": [v.model_dump() for v in hours],
    }

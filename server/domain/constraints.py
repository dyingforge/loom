from __future__ import annotations

from datetime import datetime, time
from typing import Iterable

from .models import Candidate, Project, Violation
from .structure import analyze


def validate(project: Project, candidate: Candidate,
             now: datetime | None = None) -> list[Violation]:
    violations = []

    def reject(code, identifier, detail):
        violations.append(Violation(code=code, blockId=identifier, detail=detail))

    tasks = {task.id: task for task in project.tasks}
    existing = {block.id: block for task in project.tasks for block in task.blocks}
    if len(tasks) != len(project.tasks):
        reject("C0", "project", "任务编号重复")
    if len(existing) != sum(len(task.blocks) for task in project.tasks):
        reject("C0", "project", "已有时间块编号重复")
    structure = analyze(project)
    if structure["cycles"] or structure["missingRefs"] or structure["hoursViolations"]:
        reject("C4", "project", "项目依赖或完成状态非法：" + str(structure))
    ids = set()
    start_time = time.fromisoformat(project.workHours.start)
    end_time = time.fromisoformat(project.workHours.end)
    hours = {identifier: 0.0 for identifier in tasks}
    future = []
    for block in candidate.blocks:
        identifier = block.id or block.taskId
        if block.id:
            if block.id in ids:
                reject("C0", identifier, "候选时间块编号重复")
            ids.add(block.id)
        task = tasks.get(block.taskId)
        if task is None:
            reject("C0", identifier, "引用了不存在的任务")
            continue
        old = existing.get(block.id)
        locked = old is not None and (old.done or (now is not None and old.start < now))
        if locked:
            if (block.taskId, block.start, block.end, block.done) != (
                    old.taskId, old.start, old.end, old.done):
                reject("C1", identifier, "已经开始或完成的时间块必须完整保留")
            continue
        if block.done or task.done or (now is not None and block.start < now):
            reject("C1", identifier, "新增时间块必须属于未完成任务且从当前时间以后开始")
        if old is not None and old.taskId != block.taskId:
            reject("C0", identifier, "已有时间块不能更换所属任务")
        if (block.start.date() != block.end.date()
                or block.start.time() < start_time or block.end.time() > end_time
                or block.start.weekday() in project.restDays):
            reject("C3", identifier, "时间块必须完整位于工作日的工作时段")
        for event in project.fixedEvents:
            if max(block.start, event.start) < min(block.end, event.end):
                reject("C2", identifier, "与固定日程 " + event.id + " 冲突")
        hours[block.taskId] += (block.end - block.start).total_seconds() / 3600
        future.append(block)
    for identifier, old in existing.items():
        if (old.done or (now is not None and old.start < now)) and identifier not in ids:
            reject("C1", identifier, "候选遗漏已经开始或完成的时间块")
    ordered = sorted(candidate.blocks, key=lambda block: (block.start, block.end))
    for index, block in enumerate(ordered):
        for previous in ordered[:index]:
            if block.start < previous.end:
                reject("C6", block.id or block.taskId, "时间块与 " + (previous.id or previous.taskId) + " 重叠")
    for identifier, task in tasks.items():
        expected = 0 if task.done else task.remainingHours
        if abs(hours[identifier] - expected) > 1e-6:
            reject("C5", identifier, f"未来未完成块总工时 {hours[identifier]:.3f} 与剩余工时 {expected} 不一致")
        blocks = [block for block in future if block.taskId == identifier]
        for dependency in task.dependsOn:
            predecessor = tasks.get(dependency)
            if predecessor is None or predecessor.done or predecessor.remainingHours == 0 or not blocks:
                continue
            before = [block.end for block in future if block.taskId == dependency]
            if not before or min(block.start for block in blocks) < max(before):
                reject("C4", identifier, "必须在依赖任务 " + dependency + " 完成后开始")
    return violations


def check_adjustable(plan_changes: Iterable, project: Project) -> list[Violation]:
    tasks = {task.id: task for task in project.tasks}
    violations = []
    for change in plan_changes:
        owners = {block.taskId for block in (change.before, change.after) if block is not None}
        for identifier in owners:
            if identifier not in tasks or not tasks[identifier].adjustable:
                violations.append(Violation(code="C7", blockId=identifier,
                                            detail="变更涉及未授权自动调整的任务"))
    return violations

from datetime import datetime

from .models import Candidate, Project
from .scheduling import free_slots


def capacity(project: Project, now: datetime) -> dict:
    required = sum(task.remainingHours for task in project.tasks if not task.done)
    available = None
    if project.deadline is not None:
        slots = free_slots(project, now, project.deadline, now)
        available = sum((end - start).total_seconds() / 3600 for start, end in slots)
    return {"remainingHours": required, "availableHours": available,
            "gapHours": max(0, required - available) if available is not None else None}


def schedule_risks(project: Project, candidate: Candidate) -> list[str]:
    risks = []
    limits = [("项目截止时间", project.deadline, {task.id for task in project.tasks})]
    for milestone in project.milestones:
        ids = set(milestone.taskIds) if milestone.taskIds else {task.id for task in project.tasks}
        missing = ids - {task.id for task in project.tasks}
        if missing:
            raise ValueError("里程碑引用不存在的任务：" + "、".join(sorted(missing)))
        limits.append(("里程碑「" + milestone.title + "」", milestone.due, ids))
    for label, due, ids in limits:
        late = {block.taskId for block in candidate.blocks
                if not block.done and block.taskId in ids and due is not None and block.end > due}
        if late:
            risks.append(label + "之后仍有任务：" + "、".join(sorted(late)))
    return risks

from __future__ import annotations

from server.domain.models import Plan, Project


def apply_plan(project: Project, plan: Plan) -> Project:
    if project.version != plan.baseVersion:
        raise ValueError("方案版本已经过期")
    result = project.model_copy(deep=True)
    blocks = {block.id: block for task in result.tasks for block in task.blocks}
    tasks = {task.id: task for task in result.tasks}
    seen = set()
    for change in plan.changes:
        if change.blockId in seen:
            raise ValueError("方案变更编号重复")
        seen.add(change.blockId)
        old = blocks.get(change.blockId)
        if old != change.before:
            raise ValueError("方案中的原始时间块与项目不一致")
        if change.before is None and change.after is None:
            raise ValueError("变更必须包含时间块")
        if change.after is None:
            del blocks[change.blockId]
        else:
            if change.after.id != change.blockId or change.after.taskId not in tasks:
                raise ValueError("变更时间块编号或任务归属非法")
            blocks[change.blockId] = change.after.model_copy(deep=True)
    for task in result.tasks:
        task.blocks = sorted((block for block in blocks.values() if block.taskId == task.id),
                             key=lambda block: (block.start, block.id))
    result.version += 1
    return result

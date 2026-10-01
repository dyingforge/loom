from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from server.domain.scheduling import free_slots
from server.domain.structure import analyze
from server.domain.constraints import validate
from server.domain.models import Candidate, Project, Task


# ---------- 参数 schema（JSON Schema 风格） ----------
ANALYZE_SCHEMA: dict[str, Any] = {
    "name": "analyze",
    "description": "检查项目结构：依赖环、缺失任务引用、剩余工时切分是否一致。"
                "返回结构化诊断。",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}

QUERY_FREE_SLOTS_SCHEMA: dict[str, Any] = {
    "name": "query_free_slots",
    "description": "返回指定时间范围内扣除固定日程、已完成块、休息日后的空闲时段，"
                "格式 [(start_iso, end_iso), ...]，按起始时间排序。",
    "parameters": {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "ISO 8601 起始"},
            "end": {"type": "string", "description": "ISO 8601 结束（exclusive）"},
        },
        "required": ["start", "end"],
        "additionalProperties": False,
    },
}

PROPOSE_TASKS_SCHEMA: dict[str, Any] = {
    "name": "propose_tasks",
    "description": "从 goal/deadline 出发，提出任务清单（标题、剩余工时、依赖、优先级）。"
                "返回 [{id,title,priority,remainingHours,dependsOn}]。",
    "parameters": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "minLength": 1, "maxLength": 80},
                        "title": {"type": "string", "minLength": 1, "maxLength": 200},
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                        "remainingHours": {"type": "number", "exclusiveMinimum": 0, "maximum": 720},
                        "dependsOn": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "title", "priority", "remainingHours", "dependsOn"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["tasks"],
        "additionalProperties": False,
    },
}


VALIDATE_SCHEDULE_SCHEMA: dict[str, Any] = {
    "name": "validate_schedule",
    "description": "校验完整候选排程是否违反 C1–C6；返回 [{code, blockId, detail}]，"
                "空列表表示通过。只判断，不代排。",
    "parameters": Candidate.model_json_schema(),
}


SCHEMAS: list[dict[str, Any]] = [
    ANALYZE_SCHEMA,
    QUERY_FREE_SLOTS_SCHEMA,
    VALIDATE_SCHEDULE_SCHEMA,
    PROPOSE_TASKS_SCHEMA,
]

REBUILD_TASKS_SCHEMA = deepcopy(PROPOSE_TASKS_SCHEMA)
REBUILD_TASKS_SCHEMA["name"] = "rebuild_tasks"
REBUILD_TASKS_SCHEMA["description"] = (
    "根据目标、截止日期和用户建议提交完整任务清单，然后继续安排日历。"
    "可以新增、修改或删除尚未开始的任务。已有任务沿用 id；必须保留已完成或已有开始时间块的任务，"
    "已完成任务剩余工时保持为零。返回完整任务清单，随后查询空闲时间并提交完整日历。"
)
REBUILD_TASKS_SCHEMA["parameters"]["properties"]["tasks"]["items"]["properties"]["remainingHours"] = {
    "type": "number", "minimum": 0, "maximum": 720,
}


def rebuild_tasks(project: Project, args: dict, now) -> Project:
    previous = {task.id: task for task in project.tasks}
    tasks = []
    seen = set()
    for value in args["tasks"]:
        task = Task.model_validate(value)
        if task.id in seen:
            raise ValueError("任务编号重复：" + task.id)
        seen.add(task.id)
        old = previous.get(task.id)
        if old is not None:
            task.blocks = [block.model_copy(deep=True) for block in old.blocks]
            task.adjustable = old.adjustable
            task.done = old.done
            if old.done and task.remainingHours != old.remainingHours:
                raise ValueError("已经完成的任务不能修改剩余工时：" + task.id)
        if not task.done and task.remainingHours <= 0:
            raise ValueError("尚未完成的任务需要正数工时：" + task.id)
        tasks.append(task)
    for old in project.tasks:
        if (old.done or any(block.done or block.start < now for block in old.blocks)) and old.id not in seen:
            raise ValueError("必须保留已经开始或完成的任务：" + old.id)
    target = project.model_copy(update={"tasks": tasks}, deep=True)
    analysis = analyze(target)
    if analysis["cycles"] or analysis["missingRefs"]:
        raise ValueError("任务依赖存在循环或缺少引用：" + str(analysis))
    return target


# ---------- 工具实现 ----------
def analyze_tool(project: Project, args: dict) -> dict:
    if args != {}:
        raise ValueError("analyze 不接受参数")
    return analyze(project)


def query_free_slots_tool(project: Project, args: dict) -> dict:
    if not isinstance(args, dict) or "start" not in args or "end" not in args:
        raise ValueError("query_free_slots 需要 start 和 end")
    start = datetime.fromisoformat(args["start"])
    end = datetime.fromisoformat(args["end"])
    if end <= start:
        raise ValueError("end 必须晚于 start")
    slots = free_slots(project, start, end)
    return {
        "slots": [[s.isoformat(), e.isoformat()] for s, e in slots],
    }


def validate_schedule_tool(project: Project, args: dict) -> dict:
    if not isinstance(args, dict) or "blocks" not in args:
        raise ValueError("validate_schedule 需要 blocks")
    cand = Candidate.model_validate(args)
    return {"violations": [v.model_dump() for v in validate(project, cand)]}


DISPATCH: dict[str, Any] = {
    "analyze": analyze_tool,
    "query_free_slots": query_free_slots_tool,
    "validate_schedule": validate_schedule_tool,
}


def propose_tasks_tool(project: Project, args: dict) -> dict:
    if not isinstance(args, dict) or "tasks" not in args:
        raise ValueError("propose_tasks 需要 tasks 数组")
    proposed = args["tasks"]
    if not isinstance(proposed, list):
        raise ValueError("propose_tasks.tasks 必须是数组")
    # 基本健全性：检查 ID 唯一、依赖引用存在
    seen: set[str] = {task.id for task in project.tasks}
    for t in proposed:
        if not isinstance(t, dict):
            raise ValueError("propose_tasks.tasks 项必须是对象")
        tid = t.get("id")
        if not isinstance(tid, str) or not tid:
            raise ValueError("任务 id 必填且为字符串")
        if tid in seen:
            raise ValueError(f"重复任务 id: {tid}")
        seen.add(tid)
    for t in proposed:
        for dep in t.get("dependsOn") or []:
            if dep not in seen:
                raise ValueError(f"任务 {t['id']} 依赖 {dep} 不存在")
        if t.get("remainingHours", 0) <= 0:
            raise ValueError(f"任务 {t['id']} 剩余工时必须为正")
    tasks = [Task.model_validate(item) for item in proposed]
    combined = project.model_copy(update={"tasks": project.tasks + tasks}, deep=True)
    analysis = analyze(combined)
    if analysis["cycles"] or analysis["missingRefs"]:
        return {"error": "建议依赖形成循环或引用不存在：" + str(analysis)}
    return {"proposed": [task.model_dump(mode="json") for task in tasks]}


DISPATCH["propose_tasks"] = propose_tasks_tool


def dispatch(project: Project, name: str, args: dict) -> dict:
    fn = DISPATCH.get(name)
    if fn is None:
        raise ValueError(f"unknown tool: {name}")
    return fn(project, args)

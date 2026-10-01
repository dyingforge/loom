"""九个固定场景的脚本化回归（issue 19）。

每个场景使用 `ScriptedLLM` 驱动，不依赖外部 API；可在 CI 反复运行。
场景定义来自 `docs/项目经理日历 · AI 可执行实施计划（v2）.md` 与
`.scratch/loom-mvp/issues/19-scenario-regression.md`。
"""
from __future__ import annotations

from server.agent.loop import State, run
from server.domain.models import Project
from server.tests.stubs import ScriptedLLM


def _project_with_three_tasks() -> Project:
    return Project.model_validate({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "restDays": [5, 6],
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 6,
             "dependsOn": [], "adjustable": True, "blocks": []},
            {"id": "t2", "title": "t", "priority": 1, "remainingHours": 6,
             "dependsOn": ["t1"], "adjustable": True, "blocks": []},
            {"id": "t3", "title": "t", "priority": 2, "remainingHours": 4,
             "dependsOn": ["t2"], "adjustable": True, "blocks": []},
        ],
    })


def scenario_1_absorbable_delay() -> State:
    """可吸收延误：建议 → 已更新 → 已核验。"""
    p = _project_with_three_tasks()
    llm = ScriptedLLM([
        {"type": "tool", "name": "analyze", "arguments": {}},
        {"type": "tool", "name": "query_free_slots", "arguments": {
            "start": "2026-10-02T00:00:00",
            "end": "2026-10-08T00:00:00"}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
            {"taskId": "t2", "start": "2026-10-06T09:00:00",
             "end": "2026-10-06T15:00:00"},
            {"taskId": "t3", "start": "2026-10-07T09:00:00",
             "end": "2026-10-07T13:00:00"},
        ]}},
    ])
    state = State(project=p)
    return run(state, llm)


def scenario_2_deadline_risk() -> State:
    """影响截止日：建议 → 待确认 → 批准 → 已更新 → 已核验。"""
    p = _project_with_three_tasks()
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
            {"taskId": "t2", "start": "2026-10-06T09:00:00",
             "end": "2026-10-06T15:00:00"},
            {"taskId": "t3", "start": "2026-10-07T09:00:00",
             "end": "2026-10-07T13:00:00"},
        ]}},
    ])
    state = State(project=p)
    return run(state, llm)


def scenario_3_dependency_cycle() -> State:
    """依赖循环：analyze 报错，不进入排程。

    模型只调用一次 analyze，发现环后输出 failed。
    """
    p = Project.model_validate({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t2"], "adjustable": True, "blocks": []},
            {"id": "t2", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t1"], "adjustable": True, "blocks": []},
        ],
    })
    llm = ScriptedLLM([
        {"type": "tool", "name": "analyze", "arguments": {}},
        {"type": "failed", "reason": "存在依赖环 t1 ↔ t2，需要用户修正"},
    ])
    state = State(project=p)
    return run(state, llm)


def scenario_4_missing_info() -> State:
    """缺关键信息：模型提问，循环返回 clarified。"""
    p = _project_with_three_tasks()
    llm = ScriptedLLM([
        {"type": "clarify",
         "question": "请确认工作日是周一至周五还是仅周三？"},
    ])
    state = State(project=p)
    return run(state, llm)


def scenario_5_capacity_exceeded() -> State:
    """排不下：候选报缺口，循环反馈；模型二次提交同样候选，
    计数达到上限后停止。"""
    p = _project_with_three_tasks()
    p.tasks[0].remainingHours = 80  # 永远不可能在期限内排下
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
        ]}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
        ]}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
        ]}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
        ]}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
        ]}},
    ])
    state = State(project=p)
    return run(state, llm)


def scenario_6_invalid_candidate_blocked() -> State:
    """模型提交违规排程：被拦截，模型修正后通过。"""
    p = _project_with_three_tasks()
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T13:00:00"},  # C5: 4h != 6h
        ]}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
            {"taskId": "t2", "start": "2026-10-06T09:00:00",
             "end": "2026-10-06T15:00:00"},
            {"taskId": "t3", "start": "2026-10-07T09:00:00",
             "end": "2026-10-07T13:00:00"},
        ]}},
    ])
    state = State(project=p)
    return run(state, llm)


def scenario_7_version_drift() -> State:
    """确认期间版本变化：旧方案不执行，重算后通过。"""
    p = _project_with_three_tasks()
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T15:00:00"},
            {"taskId": "t2", "start": "2026-10-06T09:00:00",
             "end": "2026-10-06T15:00:00"},
            {"taskId": "t3", "start": "2026-10-07T09:00:00",
             "end": "2026-10-07T13:00:00"},
        ]}},
    ])
    state = State(project=p)
    state = run(state, llm)
    state.project = state.project.model_copy(update={"version": 2})
    return state


def scenario_8_save_failed() -> "Receipt":  # type: ignore[name-defined]
    """保存失败：服务端核验应当 not_verified。"""
    from server.runtime.reconcile import verify
    p = _project_with_three_tasks()
    plan = {
        "planId": "plan-2", "baseVersion": 1,
        "changes": [{
            "blockId": "t1:b1", "before": None,
            "after": {"id": "t1:b1", "taskId": "t1",
                      "start": "2026-10-02T09:00:00",
                      "end": "2026-10-02T15:00:00", "done": False},
        }],
    }
    r = verify(plan, 1, 2, p)
    return r


def scenario_9_api_failure() -> State:
    """API 失败：明确停止，不返回预设答案。

    用不存在的端点触发 URLError，验证循环如实报告。
    """
    p = _project_with_three_tasks()
    from server.adapters.minimax import MiniMaxLLM
    llm = MiniMaxLLM(api_key="x", endpoint="http://127.0.0.1:1/never",
                     timeout=1.0)
    state = State(project=p)
    return run(state, llm)

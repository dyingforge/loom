"""Agent 循环与工具的测试。

使用脚本化替身（仅在本 tests/ 目录出现）模拟 LLM。覆盖：
- 工具单元测试
- 非法参数被拒
- step 状态分支：正常提交、违规后修正、追问、各上限停止、序列化往返
"""
from __future__ import annotations

import pytest

from server.agent.loop import State, step, run
from server.agent.tools import (
    SCHEMAS, analyze_tool, dispatch, query_free_slots_tool,
    validate_schedule_tool,
)
from server.domain.models import Candidate, Project
from server.tests.stubs import ScriptedLLM


def _project() -> Project:
    return Project.model_validate({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "restDays": [5, 6],
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 4,
             "done": False, "dependsOn": [], "adjustable": True, "blocks": []},
        ],
    })


def test_analyze_tool_no_args_accepted() -> None:
    p = _project()
    out = analyze_tool(p, {})
    assert "cycles" in out


def test_query_free_slots_tool_needs_range() -> None:
    p = _project()
    with pytest.raises(ValueError):
        query_free_slots_tool(p, {})


def test_query_free_slots_returns_free_intervals() -> None:
    p = _project()
    out = query_free_slots_tool(p, {
        "start": "2026-10-02T00:00:00",
        "end": "2026-10-03T00:00:00",
    })
    assert len(out["slots"]) >= 1


def test_validate_schedule_tool_passes_when_valid() -> None:
    p = _project()
    out = validate_schedule_tool(p, {
        "blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T13:00:00"}
        ]
    })
    assert out["violations"] == []


def test_validate_schedule_tool_detects_c5() -> None:
    p = _project()
    out = validate_schedule_tool(p, {
        "blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T11:00:00"}
        ]
    })
    codes = [v["code"] for v in out["violations"]]
    assert "C5" in codes


def test_dispatch_unknown_tool_raises() -> None:
    p = _project()
    with pytest.raises(ValueError):
        dispatch(p, "nope", {})


def test_state_serializable_roundtrip() -> None:
    s = State(project=_project(), messages=[{"role": "user", "content": "hi"}])
    blob = s.to_dict()
    s2 = State.from_dict(blob)
    assert s2.project == s.project
    assert s2.messages == s.messages


def test_step_submits_and_generates_plan() -> None:
    p = _project()
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T13:00:00"},
        ]}},
    ])
    s = State(project=p)
    s = step(s, llm)
    assert s.status == "submitted"
    assert s.plan is not None
    assert len(s.plan.changes) == 1


def test_step_rejects_invalid_candidate_then_submits_valid() -> None:
    p = _project()
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T11:00:00"},  # C5
        ]}},
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T13:00:00"},
        ]}},
    ])
    s = State(project=p)
    s = step(s, llm)
    assert s.status == "running"
    s = step(s, llm)
    assert s.status == "submitted"


def test_step_clarify() -> None:
    p = _project()
    llm = ScriptedLLM([
        {"type": "clarify", "question": "工作日是哪几天？"},
    ])
    s = State(project=p)
    s = step(s, llm)
    assert s.status == "clarified"
    assert "工作日" in (s.clarification or "")


def test_step_invalid_tool_args_stops_after_streak() -> None:
    p = _project()
    llm = ScriptedLLM([
        {"type": "tool", "name": "nope", "arguments": {}},
        {"type": "tool", "name": "nope", "arguments": {}},
    ])
    s = State(project=p)
    step(s, llm)
    s = step(s, llm)
    assert s.status == "stopped"
    assert "无效参数" in s.failure_reason


def test_step_max_calls_per_round() -> None:
    p = _project()
    llm = ScriptedLLM([{"type": "tool", "name": "analyze", "arguments": {}}] * 20)
    s = State(project=p)
    run(s, llm, max_steps=20)
    assert s.status == "stopped"
    assert s.llm_calls == 10


def test_step_max_validations_per_candidate() -> None:
    p = _project()
    bad = {"blocks": [{"taskId": "t1", "start": "2026-10-02T09:00:00",
                       "end": "2026-10-02T11:00:00"}]}
    llm = ScriptedLLM([{"type": "submit", "candidate": bad}] * 6)
    s = State(project=p)
    for _ in range(6):
        step(s, llm)
    assert s.status == "stopped"
    assert "超过上限" in s.failure_reason


def test_step_passes_final_validation_even_if_model_claimed() -> None:
    """循环最终校验不被模型已声明的“通过”替代。"""
    p = _project()
    llm = ScriptedLLM([
        {"type": "submit", "candidate": {"blocks": [
            {"taskId": "t1", "start": "2026-10-02T09:00:00",
             "end": "2026-10-02T11:00:00"},  # C5 违规
        ]}},
    ])
    s = State(project=p)
    s = step(s, llm)
    assert s.status == "running"
    # 循环把违规反馈回消息；模型后续可改
    last = s.messages[-1]
    assert "C5" in last["content"]

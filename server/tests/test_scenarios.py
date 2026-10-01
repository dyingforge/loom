"""九个固定场景的回归（issue 19）。"""
from __future__ import annotations

import pytest

from fixtures.scenarios.scenarios import (
    scenario_1_absorbable_delay, scenario_2_deadline_risk,
    scenario_3_dependency_cycle, scenario_4_missing_info,
    scenario_5_capacity_exceeded, scenario_6_invalid_candidate_blocked,
    scenario_7_version_drift, scenario_8_save_failed,
    scenario_9_api_failure,
)


def test_scenario_1_absorbable_delay() -> None:
    state = scenario_1_absorbable_delay()
    assert state.status == "submitted"
    assert state.plan is not None
    assert len(state.plan.changes) == 3


def test_scenario_2_deadline_risk_submits() -> None:
    state = scenario_2_deadline_risk()
    assert state.status == "submitted"
    # 风险方案的 risks 由模型或 UI 在展示时填充；服务端只生成 changes


def test_scenario_3_dependency_cycle_detected_by_tool() -> None:
    state = scenario_3_dependency_cycle()
    # 模型调用 analyze，发现环后声明 failed；状态应为 failed
    assert state.status == "failed"
    tool_calls = [t for t in state.trace if t.get("type") == "tool_call"]
    assert any(t["name"] == "analyze" for t in tool_calls)
    assert any(t.get("type") == "failed" for t in state.trace)


def test_scenario_4_missing_info_clarifies() -> None:
    state = scenario_4_missing_info()
    assert state.status == "clarified"
    assert "工作日" in (state.clarification or "")


def test_scenario_5_capacity_exceeded_stops_or_submits() -> None:
    state = scenario_5_capacity_exceeded()
    # 模型二次提交相同候选 → 同一候选校验超过上限 → 停止
    assert state.status == "stopped"
    assert "超过上限" in (state.failure_reason or "")


def test_scenario_6_invalid_candidate_blocked_then_passes() -> None:
    state = scenario_6_invalid_candidate_blocked()
    assert state.status == "submitted"
    assert state.plan is not None
    # 第一次提交被 C5 拦截，第二次成功
    validations = [t for t in state.trace if t.get("type") == "validation"]
    assert len(validations) >= 2
    assert any(v["violations"] for v in validations)
    assert any(not v["violations"] for v in validations)


def test_scenario_7_version_drift() -> None:
    state = scenario_7_version_drift()
    # 模型方案已生成；用户更新版本；plan.baseVersion=1 与 readback.version=2 不一致
    assert state.plan is not None
    assert state.plan.baseVersion == 1
    assert state.project.version == 2


def test_scenario_8_save_failed_not_verified() -> None:
    r = scenario_8_save_failed()
    assert r.status == "not_verified"


def test_scenario_9_api_failure_returns_failed() -> None:
    state = scenario_9_api_failure()
    # 网络不可达 → MiniMaxLLM 返回 {"type":"failed",...} → 循环状态 failed
    assert state.status == "failed"
    assert state.failure_reason is not None
    assert "network" in state.failure_reason or "connection" in state.failure_reason.lower()

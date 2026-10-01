from datetime import datetime

import pytest
from pydantic import ValidationError

from server.agent.loop import State, execute
from server.agent.tools import rebuild_tasks
from server.domain.models import AgentRequest, Block, Candidate, FixedEvent
from server.domain.scheduling import diff
from server.runtime.plans import apply_plan
from server.runtime.reconcile import verify_calendar
from server.tests.test_preliminary_constraints import NOW, blocks, project


def task(identifier, title, hours, dependencies=()):
    return {"id": identifier, "title": title, "remainingHours": hours,
            "priority": 1, "dependsOn": list(dependencies)}


def test_goal_compose_requires_decomposition():
    value = project()
    state = State(project=value, now=NOW, trigger="compose")
    arguments = {"candidate": {"blocks": blocks()}, "rationale": "按依赖完成",
                 "risks": [], "exceptions": []}
    assert "error" in execute(state, "submit_plan", arguments)
    execute(state, "rebuild_tasks", {"tasks": [task("a", "设计", 2), task("b", "开发", 1, ["a"])]})
    assert execute(state, "submit_plan", arguments)["accepted"]
    assert state.status == "submitted"
    assert State.from_dict(state.to_dict()).tasks_rebuilt


def test_rebuild_adds_and_removes_future_tasks_without_mutating_formal():
    formal = apply_plan(project(), diff(project(), Candidate(blocks=blocks())))
    revised = rebuild_tasks(formal, {"tasks": [task("a", "完成设计", 3), task("c", "讲解说明", 0.5, ["a"])]}, NOW)
    assert [item.id for item in formal.tasks] == ["a", "b"]
    assert [item.id for item in revised.tasks] == ["a", "c"]
    assert revised.tasks[0].blocks == formal.tasks[0].blocks
    assert revised.tasks[0].remainingHours == 3
    assert revised.version == formal.version


def test_rebuild_preserves_started_and_completed_records():
    formal = project()
    formal.tasks[0].blocks = [Block(id="past", taskId="a", start=NOW.replace(month=9, day=30, hour=9),
                                  end=NOW.replace(month=9, day=30, hour=10), done=True)]
    with pytest.raises(ValueError, match="保留"):
        rebuild_tasks(formal, {"tasks": [task("b", "开发", 1)]}, NOW)
    revised = rebuild_tasks(formal, {"tasks": [task("a", "设计", 2), task("b", "开发", 1)]}, NOW)
    assert revised.tasks[0].blocks == formal.tasks[0].blocks
    formal.tasks[0].done = True
    formal.tasks[0].remainingHours = 0
    with pytest.raises(ValueError, match="工时"):
        rebuild_tasks(formal, {"tasks": [task("a", "设计", 2), task("b", "开发", 1)]}, NOW)
    revised = rebuild_tasks(formal, {"tasks": [task("a", "设计", 0), task("b", "开发", 1)]}, NOW)
    assert revised.tasks[0].done
    assert revised.tasks[0].blocks == formal.tasks[0].blocks


def test_rebuild_rejects_duplicate_missing_reference_and_cycle():
    for values in ([task("a", "设计", 1), task("a", "开发", 1)],
                   [task("a", "设计", 1, ["missing"])],
                   [task("a", "设计", 1, ["b"]), task("b", "开发", 1, ["a"])]):
        with pytest.raises(ValueError):
            rebuild_tasks(project(), {"tasks": values}, NOW)


def prepared():
    formal = project()
    draft = rebuild_tasks(formal, {"tasks": [task("a", "设计", 2), task("b", "开发", 1, ["a"])]}, NOW)
    plan = diff(draft, Candidate(blocks=blocks()))
    return formal, draft, plan, apply_plan(draft, plan)


def test_complete_calendar_readback_is_verified():
    formal, draft, plan, readback = prepared()
    assert verify_calendar(formal, draft, plan, readback, NOW).status == "verified"
    assert formal.version == 1
    assert not formal.tasks[0].blocks


def test_readback_tampering_and_versions_are_rejected():
    for field in ("hours", "version", "goal", "missing_block"):
        formal, draft, plan, readback = prepared()
        if field == "hours":
            readback.tasks[0].remainingHours += 1
        elif field == "version":
            readback.version += 1
        elif field == "goal":
            readback.goal = "其他目标"
        else:
            readback.tasks[0].blocks = []
        assert verify_calendar(formal, draft, plan, readback, NOW).status == "not_verified"


def test_work_constraints_and_history_cannot_change_in_draft():
    formal, draft, plan, readback = prepared()
    draft.restDays = []
    assert verify_calendar(formal, draft, plan, readback, NOW).status == "not_verified"
    formal, draft, plan, readback = prepared()
    old = Block(id="past", taskId="a", start=NOW.replace(month=9, day=30, hour=9),
                end=NOW.replace(month=9, day=30, hour=10), done=True)
    formal.tasks[0].blocks = [old]
    assert verify_calendar(formal, draft, plan, readback, NOW).status == "not_verified"


def test_verification_checks_calendar_constraints():
    formal, draft, plan, readback = prepared()
    meeting = FixedEvent(id="meeting", start=NOW.replace(hour=10), end=NOW.replace(hour=11))
    formal.fixedEvents = [meeting]
    draft.fixedEvents = [meeting]
    readback.fixedEvents = [meeting]
    assert verify_calendar(formal, draft, plan, readback, NOW).status == "not_verified"


def test_goal_deadline_and_advice_validation():
    request = {"snapshot": project().model_dump(mode="json"), "trigger": "compose", "now": NOW}
    assert AgentRequest.model_validate(request).trigger == "compose"
    for invalid in ("2027-02-29T18:00:00", "2026-13-01T18:00:00", "2026-10-00T18:00:00"):
        request["snapshot"]["deadline"] = invalid
        with pytest.raises(ValidationError):
            AgentRequest.model_validate(request)
    request["snapshot"]["deadline"] = "2028-02-29T18:00:00"
    assert AgentRequest.model_validate(request).snapshot.deadline == datetime(2028, 2, 29, 18)
    request["trigger"] = "revise"
    with pytest.raises(ValidationError, match="修改建议"):
        AgentRequest.model_validate(request)
    request["instruction"] = "提前设计任务"
    assert AgentRequest.model_validate(request).instruction == "提前设计任务"

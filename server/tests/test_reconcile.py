"""执行后核验测试。"""
from __future__ import annotations

from pydantic import TypeAdapter

from server.runtime.reconcile import verify
from server.domain.models import Project


ADAPTER = TypeAdapter(Project)


def _project(version: int, blocks: list[dict]) -> Project:
    return ADAPTER.validate_python({
        "id": "p", "version": version, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1, "remainingHours": 4,
            "dependsOn": [], "adjustable": True, "blocks": blocks,
        }],
    })


def test_verify_ok_when_readback_matches_plan() -> None:
    plan = {
        "planId": "plan-2", "baseVersion": 1,
        "changes": [{
            "blockId": "t1:b1",
            "before": None,
            "after": {"id": "t1:b1", "taskId": "t1",
                      "start": "2026-10-02T09:00:00",
                      "end": "2026-10-02T13:00:00",
                      "done": False},
        }],
    }
    readback = _project(2, [{
        "id": "t1:b1", "taskId": "t1",
        "start": "2026-10-02T09:00:00", "end": "2026-10-02T13:00:00",
        "done": False,
    }])
    r = verify(plan, version_before=1, version_after=2, readback=readback)
    assert r.status == "verified"
    assert r.reason == ""


def test_verify_not_verified_on_baseversion_mismatch() -> None:
    plan = {"planId": "p", "baseVersion": 1, "changes": []}
    r = verify(plan, version_before=2, version_after=3,
               readback=_project(3, []))
    assert r.status == "not_verified"
    assert "baseVersion" in r.reason


def test_verify_not_verified_on_missing_block() -> None:
    plan = {
        "planId": "p", "baseVersion": 1,
        "changes": [{
            "blockId": "t1:b1", "before": None,
            "after": {"id": "t1:b1", "taskId": "t1",
                      "start": "2026-10-02T09:00:00",
                      "end": "2026-10-02T13:00:00", "done": False},
        }],
    }
    readback = _project(2, [])
    r = verify(plan, version_before=1, version_after=2, readback=readback)
    assert r.status == "not_verified"


def test_verify_not_verified_on_mismatched_time() -> None:
    plan = {
        "planId": "p", "baseVersion": 1,
        "changes": [{
            "blockId": "t1:b1", "before": None,
            "after": {"id": "t1:b1", "taskId": "t1",
                      "start": "2026-10-02T09:00:00",
                      "end": "2026-10-02T13:00:00", "done": False},
        }],
    }
    readback = _project(2, [{
        "id": "t1:b1", "taskId": "t1",
        "start": "2026-10-02T10:00:00", "end": "2026-10-02T13:00:00",
        "done": False,
    }])
    r = verify(plan, version_before=1, version_after=2, readback=readback)
    assert r.status == "not_verified"

"""自动执行条件检查（issue 14）。"""
from __future__ import annotations

from pydantic import TypeAdapter

from server.runtime.executor import can_auto_execute
from server.domain.models import Change, Project


ADAPTER = TypeAdapter(Project)


def test_can_auto_execute_when_all_adjusted() -> None:
    p = ADAPTER.validate_python({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
            "dependsOn": [], "adjustable": True, "blocks": [],
        }],
    })
    ch = Change.model_validate({
        "blockId": "t1:b1",
        "before": {"id": "b1", "taskId": "t1",
                   "start": "2026-10-02T09:00:00",
                   "end": "2026-10-02T11:00:00", "done": False},
        "after": {"id": "b1", "taskId": "t1",
                  "start": "2026-10-02T13:00:00",
                  "end": "2026-10-02T15:00:00", "done": False},
    })
    r = can_auto_execute([ch], p)
    assert r["ok"]


def test_cannot_auto_execute_when_not_adjusted() -> None:
    p = ADAPTER.validate_python({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
            "dependsOn": [], "adjustable": False, "blocks": [],
        }],
    })
    ch = Change.model_validate({
        "blockId": "t1:b1",
        "before": {"id": "b1", "taskId": "t1",
                   "start": "2026-10-02T09:00:00",
                   "end": "2026-10-02T11:00:00", "done": False},
        "after": {"id": "b1", "taskId": "t1",
                  "start": "2026-10-02T13:00:00",
                  "end": "2026-10-02T15:00:00", "done": False},
    })
    r = can_auto_execute([ch], p)
    assert not r["ok"]
    assert r["violations"][0]["code"] == "C7"

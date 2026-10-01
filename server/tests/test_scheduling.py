"""domain.scheduling 测试。"""
from __future__ import annotations

from datetime import datetime

from pydantic import TypeAdapter

from server.domain.scheduling import diff, free_slots
from server.domain.models import Candidate, Project


ADAPTER = TypeAdapter(Project)


def test_free_slots_empty_day_when_all_locked() -> None:
    p = ADAPTER.validate_python({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "fixedEvents": [{
            "id": "f1", "title": "全天会议",
            "start": "2026-10-02T09:00", "end": "2026-10-02T18:00"}],
        "tasks": [],
    })
    slots = free_slots(
        p,
        datetime.fromisoformat("2026-10-02T00:00"),
        datetime.fromisoformat("2026-10-03T00:00"),
    )
    assert slots == []


def test_free_slots_subtracts_fixed_and_done() -> None:
    p = ADAPTER.validate_python({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "fixedEvents": [{
            "id": "f1", "title": "会议",
            "start": "2026-10-02T13:00", "end": "2026-10-02T14:00"}],
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1, "remainingHours": 1,
            "dependsOn": [], "adjustable": True,
            "blocks": [{
                "id": "b1", "taskId": "t1",
                "start": "2026-10-02T15:00", "end": "2026-10-02T16:00",
                "done": True,
            }],
        }],
    })
    slots = free_slots(
        p,
        datetime.fromisoformat("2026-10-02T00:00"),
        datetime.fromisoformat("2026-10-03T00:00"),
    )
    expected = [
        (datetime.fromisoformat("2026-10-02T09:00"),
         datetime.fromisoformat("2026-10-02T13:00")),
        (datetime.fromisoformat("2026-10-02T14:00"),
         datetime.fromisoformat("2026-10-02T15:00")),
        (datetime.fromisoformat("2026-10-02T16:00"),
         datetime.fromisoformat("2026-10-02T18:00")),
    ]
    assert slots == expected


def test_free_slots_excludes_rest_days() -> None:
    p = ADAPTER.validate_python({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "restDays": [5, 6],
        "tasks": [],
    })
    slots = free_slots(
        p,
        datetime.fromisoformat("2026-10-02T00:00"),
        datetime.fromisoformat("2026-10-05T00:00"),
    )
    expected = [
        (datetime.fromisoformat("2026-10-02T09:00"),
         datetime.fromisoformat("2026-10-02T18:00")),
    ]
    assert slots == expected


def test_diff_add_remove_modify() -> None:
    p = ADAPTER.validate_python({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1, "remainingHours": 2,
            "dependsOn": [], "adjustable": True,
            "blocks": [{
                "id": "b1", "taskId": "t1",
                "start": "2026-10-02T09:00", "end": "2026-10-02T11:00",
                "done": False,
            }],
        }],
    })
    cand = Candidate.model_validate({"blocks": [
        {"id": "b1", "taskId": "t1",
         "start": "2026-10-02T13:00", "end": "2026-10-02T15:00"},
        {"taskId": "t1",
         "start": "2026-10-05T09:00", "end": "2026-10-05T11:00"},
    ]})
    plan = diff(p, cand)
    change_pairs = [(c.blockId, c.before, c.after) for c in plan.changes]
    # b1 被修改
    assert ("b1", plan.changes[0].before, plan.changes[0].after) in change_pairs
    b1_change = next(c for c in plan.changes if c.blockId == "b1")
    assert b1_change.before is not None
    assert b1_change.after is not None
    assert b1_change.before.start != b1_change.after.start
    # 新增块（before=None, after=Block）
    new_change = next(c for c in plan.changes
                      if c.before is None and c.after is not None)
    assert new_change.after.taskId == "t1"

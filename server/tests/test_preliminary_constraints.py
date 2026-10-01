from datetime import datetime

from server.domain.constraints import check_adjustable, validate
from server.domain.models import Block, Candidate, Project
from server.domain.scheduling import diff

NOW = datetime(2026, 10, 1, 8)


def project():
    return Project.model_validate({"id": "acceptance", "version": 1, "goal": "完成作品",
        "deadline": "2026-10-08T18:00:00", "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{"id": "a", "title": "设计", "priority": 1, "remainingHours": 2},
                  {"id": "b", "title": "开发", "priority": 2, "remainingHours": 1, "dependsOn": ["a"]}]})


def blocks():
    return [{"id": "a-1", "taskId": "a", "start": "2026-10-01T09:00:00", "end": "2026-10-01T11:00:00"},
            {"id": "b-1", "taskId": "b", "start": "2026-10-01T11:00:00", "end": "2026-10-01T12:00:00"}]


def codes(value, raw):
    return {item.code for item in validate(value, Candidate.model_validate({"blocks": raw}), NOW)}


def test_complete_schedule():
    assert codes(project(), blocks()) == set()


def test_missing_task_and_duplicate_ids():
    assert "C5" in codes(project(), blocks()[:1])
    raw = blocks()
    raw[1]["id"] = raw[0]["id"]
    assert "C0" in codes(project(), raw)


def test_dependency_overlap_and_fixed_event():
    raw = blocks()
    raw[1].update(start="2026-10-01T10:00:00", end="2026-10-01T11:00:00")
    assert {"C4", "C6"} <= codes(project(), raw)
    value = project()
    from server.domain.models import FixedEvent
    value.fixedEvents = [FixedEvent(id="meeting", start=NOW.replace(hour=10), end=NOW.replace(hour=11))]
    assert "C2" in codes(value, blocks())


def test_completed_and_started_blocks_are_preserved():
    value = project()
    old = Block(id="history", taskId="a", start=NOW.replace(day=30, month=9, hour=9),
                end=NOW.replace(day=30, month=9, hour=10), done=True)
    value.tasks[0].blocks = [old]
    assert "C1" in codes(value, blocks())
    assert codes(value, blocks() + [old.model_dump(mode="json")]) == set()
    old.done = False
    assert "C1" in codes(value, blocks())
    assert codes(value, blocks() + [old.model_dump(mode="json")]) == set()


def test_rest_days_and_work_hours():
    raw = blocks()
    raw[0].update(start="2026-10-03T09:00:00", end="2026-10-03T11:00:00")
    assert "C3" in codes(project(), raw)
    raw = blocks()
    raw[1].update(start="2026-10-01T18:00:00", end="2026-10-01T19:00:00")
    assert "C3" in codes(project(), raw)


def test_automatic_additions_and_deletions_require_task_permission():
    value = project()
    plan = diff(value, Candidate.model_validate({"blocks": blocks()}))
    assert len(check_adjustable(plan.changes, value)) == 2
    for task in value.tasks:
        task.adjustable = True
    assert check_adjustable(plan.changes, value) == []

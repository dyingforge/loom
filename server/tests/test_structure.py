"""domain.structure 测试。"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from server.domain.structure import (
    analyze, find_cycles, find_missing_refs, check_hours_split,
)
from server.domain.models import Project


ADAPTER = TypeAdapter(Project)


def _project(d: dict) -> Project:
    return ADAPTER.validate_python(d)


def test_find_cycles_no_cycle() -> None:
    p = _project({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": [], "adjustable": True, "blocks": []},
            {"id": "t2", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t1"], "adjustable": True, "blocks": []},
        ],
    })
    assert find_cycles(p) == []


def test_find_cycles_simple() -> None:
    p = _project({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t2"], "adjustable": True, "blocks": []},
            {"id": "t2", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t1"], "adjustable": True, "blocks": []},
        ],
    })
    cycles = find_cycles(p)
    assert len(cycles) >= 1
    # 至少一个环包含 t1 和 t2
    flat = {n for c in cycles for n in c}
    assert "t1" in flat and "t2" in flat


def test_find_missing_refs() -> None:
    p = _project({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["ghost"], "adjustable": True, "blocks": []},
            {"id": "t2", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t1"], "adjustable": True, "blocks": []},
        ],
    })
    assert find_missing_refs(p) == ["t1"]


def test_check_hours_split_done_must_have_zero() -> None:
    p = _project({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 3,
             "done": True, "dependsOn": [], "adjustable": True, "blocks": []},
        ],
    })
    out = check_hours_split(p)
    assert any(v.code == "C5" for v in out)


def test_analyze_returns_cycles_missing_hours() -> None:
    p = _project({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [
            {"id": "t1", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t2"], "adjustable": True, "blocks": []},
            {"id": "t2", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["t1"], "adjustable": True, "blocks": []},
            {"id": "t3", "title": "t", "priority": 1, "remainingHours": 1,
             "dependsOn": ["ghost"], "adjustable": True, "blocks": []},
        ],
    })
    a = analyze(p)
    assert len(a["cycles"]) >= 1
    assert "t3" in a["missingRefs"]

"""propose_tasks 工具测试（issue 11）。"""
from __future__ import annotations

import pytest

from server.agent.tools import dispatch, propose_tasks_tool
from server.domain.models import Project


@pytest.fixture
def empty_project() -> Project:
    return Project.model_validate({
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [],
    })


def test_propose_basic(empty_project: Project) -> None:
    out = propose_tasks_tool(empty_project, {"tasks": [
        {"id": "t1", "title": "t", "priority": 1,
         "remainingHours": 4, "dependsOn": []},
    ]})
    assert "proposed" in out


def test_propose_rejects_missing_id(empty_project: Project) -> None:
    with pytest.raises(ValueError):
        propose_tasks_tool(empty_project, {"tasks": [
            {"title": "t", "remainingHours": 4}
        ]})


def test_propose_rejects_duplicate_id(empty_project: Project) -> None:
    with pytest.raises(ValueError):
        propose_tasks_tool(empty_project, {"tasks": [
            {"id": "t1", "title": "t", "remainingHours": 4},
            {"id": "t1", "title": "t2", "remainingHours": 2},
        ]})


def test_propose_rejects_missing_dependency(empty_project: Project) -> None:
    with pytest.raises(ValueError):
        propose_tasks_tool(empty_project, {"tasks": [
            {"id": "t1", "title": "t", "remainingHours": 4,
             "dependsOn": ["ghost"]},
        ]})


def test_propose_rejects_nonpositive_hours(empty_project: Project) -> None:
    with pytest.raises(ValueError):
        propose_tasks_tool(empty_project, {"tasks": [
            {"id": "t1", "title": "t", "remainingHours": 0},
        ]})


def test_propose_via_dispatch(empty_project: Project) -> None:
    out = dispatch(empty_project, "propose_tasks", {"tasks": [
        {"id": "t1", "title": "t", "remainingHours": 4, "priority": 2, "dependsOn": []},
    ]})
    assert "proposed" in out

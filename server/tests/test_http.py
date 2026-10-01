"""HTTP 路由测试：使用 FastAPI TestClient。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.adapters.http import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_advance_returns_plan(client: TestClient) -> None:
    r = client.post("/v1/agent/advance", json={
        "snapshot": {
            "id": "probe", "version": 1, "goal": "g",
            "workHours": {"start": "09:00", "end": "18:00"},
            "restDays": [5, 6],
            "tasks": [
                {"id": "t1", "title": "t", "priority": 1,
                 "remainingHours": 6, "dependsOn": [],
                 "adjustable": True, "blocks": []},
                {"id": "t2", "title": "t", "priority": 1,
                 "remainingHours": 6, "dependsOn": ["t1"],
                 "adjustable": True, "blocks": []},
                {"id": "t3", "title": "t", "priority": 2,
                 "remainingHours": 4, "dependsOn": ["t2"],
                 "adjustable": True, "blocks": []},
            ],
        },
        "trigger": "new",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "plan"
    assert body["payload"]["baseVersion"] == 1
    assert len(body["payload"]["changes"]) == 3
    assert len(body["trace"]) >= 3


def test_verify_returns_verified_when_readback_matches(client: TestClient) -> None:
    plan = {
        "planId": "plan-2", "baseVersion": 1,
        "changes": [{
            "blockId": "t1:b1", "before": None,
            "after": {"id": "t1:b1", "taskId": "t1",
                      "start": "2026-10-02T09:00:00",
                      "end": "2026-10-02T15:00:00", "done": False},
        }],
    }
    r = client.post("/v1/agent/verify", json={
        "plan": plan, "versionBefore": 1, "versionAfter": 2,
        "readbackSnapshot": {
            "id": "p", "version": 2, "goal": "g",
            "workHours": {"start": "09:00", "end": "18:00"},
            "tasks": [{
                "id": "t1", "title": "t", "priority": 1,
                "remainingHours": 0, "dependsOn": [],
                "adjustable": True,
                "blocks": [{
                    "id": "t1:b1", "taskId": "t1",
                    "start": "2026-10-02T09:00:00",
                    "end": "2026-10-02T15:00:00", "done": True,
                }],
            }],
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "verified"


def test_verify_not_verified_on_missing_block(client: TestClient) -> None:
    plan = {
        "planId": "plan-2", "baseVersion": 1,
        "changes": [{
            "blockId": "t1:b1", "before": None,
            "after": {"id": "t1:b1", "taskId": "t1",
                      "start": "2026-10-02T09:00:00",
                      "end": "2026-10-02T15:00:00", "done": False},
        }],
    }
    r = client.post("/v1/agent/verify", json={
        "plan": plan, "versionBefore": 1, "versionAfter": 2,
        "readbackSnapshot": {
            "id": "p", "version": 2, "goal": "g",
            "workHours": {"start": "09:00", "end": "18:00"},
            "tasks": [],
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_verified"

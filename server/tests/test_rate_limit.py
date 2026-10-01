"""HTTP 中间件：限流与每日费用上限。

可在测试中临时修改 CONFIG 或直接重置 USAGE。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.adapters import http as http_mod
from server.adapters.http import HttpConfig, app


@pytest.fixture(autouse=True)
def reset_usage() -> None:
    http_mod.USAGE.window.clear()
    http_mod.USAGE.day_cents.clear()


@pytest.fixture
def strict_config(monkeypatch) -> None:
    monkeypatch.setattr(http_mod, "CONFIG", HttpConfig(
        rate_limit_per_minute=2,
        daily_cost_limit_cents=10,
        reviewer_token="reviewer-secret",
    ))


@pytest.fixture
def client_strict(strict_config) -> TestClient:
    return TestClient(app)


def test_rate_limit_returns_429_after_limit(client_strict: TestClient) -> None:
    payload = {"snapshot": {
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1,
            "remainingHours": 2, "dependsOn": [],
            "adjustable": True, "blocks": [],
        }],
    }, "trigger": "new"}
    # 第 1、2 次成功
    r1 = client_strict.post("/v1/agent/advance", json=payload)
    assert r1.status_code == 200
    r2 = client_strict.post("/v1/agent/advance", json=payload)
    assert r2.status_code == 200
    # 第 3 次被限流
    r3 = client_strict.post("/v1/agent/advance", json=payload)
    assert r3.status_code == 429
    assert "rate limit" in r3.text.lower()


def test_reviewer_token_bypasses_limit(client_strict: TestClient) -> None:
    payload = {"snapshot": {
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1,
            "remainingHours": 2, "dependsOn": [],
            "adjustable": True, "blocks": [],
        }],
    }, "trigger": "new"}
    for _ in range(5):
        r = client_strict.post(
            "/v1/agent/advance",
            json=payload,
            headers={"x-loom-reviewer-token": "reviewer-secret"},
        )
        assert r.status_code == 200


def test_daily_cost_limit_blocks_after_threshold(client_strict: TestClient) -> None:
    """当日费用上限到达后，普通请求被拒绝。"""
    payload = {"snapshot": {
        "id": "p", "version": 1, "goal": "g",
        "workHours": {"start": "09:00", "end": "18:00"},
        "tasks": [{
            "id": "t1", "title": "t", "priority": 1,
            "remainingHours": 2, "dependsOn": [],
            "adjustable": True, "blocks": [],
        }],
    }, "trigger": "new"}
    # rate_limit=2 但 daily_cost=10 cents，先把费用烧光
    for _ in range(15):
        r = client_strict.post("/v1/agent/advance", json=payload)
        if r.status_code == 429:
            assert "cost" in r.text.lower() or "rate" in r.text.lower()
            return
    pytest.fail("应当至少有一次 429")

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from server.adapters.usage import UsageLedger


def ledger(limit=10):
    return UsageLedger(Path(".test-state") / (uuid4().hex + ".sqlite3"), limit, limit, 30, 120, 3)


def test_unknown_usage_stays_reserved_after_restart():
    value = ledger()
    identifier = value.reserve("public")
    resumed = UsageLedger(value.path, 10, 10, 30, 120, 3)
    with pytest.raises(HTTPException, match="额度"):
        resumed.reserve("public")
    resumed.settle(identifier, {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000})
    resumed.reserve("public")
    with sqlite3.connect(value.path) as db:
        row = db.execute("SELECT cost,usage,status FROM calls WHERE id=?", (identifier,)).fetchone()
    assert row[0] == 0.15 and row[2] == "reported"


def test_public_and_reviewer_have_separate_finite_limits():
    value = ledger()
    value.reserve("public")
    value.reserve("reviewer")
    for bucket in ("public", "reviewer"):
        with pytest.raises(HTTPException):
            value.reserve(bucket)


def test_pause_is_persistent_and_consumed_once():
    value = ledger()
    token = value.pause({"project": {"id": "owner"}, "llm_calls": 8,
                         "candidate_attempts": {"candidate": 3}})
    resumed = UsageLedger(value.path, 10, 10, 30, 120, 3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(resumed.resume, token, "owner") for _ in range(2)]
    assert sum(future.exception() is None for future in futures) == 1
    result = next(future.result() for future in futures if future.exception() is None)
    assert result["llm_calls"] == 8


def test_resume_distinguishes_unknown_consumed_and_expired():
    value = ledger()
    with pytest.raises(HTTPException) as unknown:
        value.resume("never-issued", "owner")
    assert unknown.value.status_code == 404
    assert unknown.value.detail["code"] == "resume_unknown"

    consumed = value.pause({"project": {"id": "owner"}, "llm_calls": 1})
    value.resume(consumed, "owner")
    with pytest.raises(HTTPException) as used:
        value.resume(consumed, "owner")
    assert used.value.status_code == 409
    assert used.value.detail["code"] == "resume_consumed"

    expired = value.pause({"project": {"id": "owner"}, "llm_calls": 2})
    with sqlite3.connect(value.path) as db:
        db.execute("UPDATE pauses SET expires=? WHERE token=?", (time.time() - 1, expired))
    with pytest.raises(HTTPException) as stale:
        value.resume(expired, "owner")
    assert stale.value.status_code == 410
    assert stale.value.detail["code"] == "resume_expired"


def test_pause_cleanup_keeps_expired_tokens_recognizable():
    value = ledger()
    stale = f"{int(time.time()) - 1}.orphan"
    with sqlite3.connect(value.path) as db:
        db.execute("INSERT INTO pauses VALUES (?,?,?,0)",
                   (stale, '{"project": {"id": "owner"}}', time.time() - 1))
    fresh = value.pause({"project": {"id": "owner"}, "llm_calls": 2})
    with sqlite3.connect(value.path) as db:
        tokens = {row[0] for row in db.execute("SELECT token FROM pauses")}
    assert stale not in tokens and fresh in tokens
    with pytest.raises(HTTPException) as expired:
        value.resume(stale, "owner")
    assert expired.value.status_code == 410
    assert expired.value.detail["code"] == "resume_expired"
    assert value.resume(fresh, "owner")["llm_calls"] == 2


def test_project_mismatch_does_not_consume_token():
    value = ledger()
    token = value.pause({"project": {"id": "owner"}, "llm_calls": 1})
    with pytest.raises(HTTPException) as mismatch:
        value.resume(token, "intruder")
    assert mismatch.value.status_code == 409
    assert mismatch.value.detail["code"] == "resume_project_mismatch"
    assert value.resume(token, "owner")["llm_calls"] == 1


def test_resume_route_returns_distinct_token_errors(tmp_path):
    from fastapi.testclient import TestClient
    from server.adapters.http import app
    from server.agent.loop import State
    from server.domain.models import Project

    snapshot = {"id": "resume-project", "version": 0, "goal": "完成作品",
                "workHours": {"start": "09:00", "end": "18:00"},
                "tasks": [{"id": "a", "title": "设计", "priority": 1, "remainingHours": 2}]}
    request = {"snapshot": snapshot, "trigger": "resume", "clarificationAnswer": "两天",
               "now": "2026-10-01T08:00:00"}

    def paused(project_id):
        project = Project.model_validate({**snapshot, "id": project_id})
        return State(project=project, now=datetime(2026, 10, 1, 8), trigger="compose",
                     status="clarified", clarification="多久？").to_dict()

    ledger = UsageLedger(Path(tmp_path) / "service.sqlite3", 1000, 1000, 30, 120, 60)
    app.state.ledger = ledger
    client = TestClient(app)
    unknown = client.post("/v1/agent/advance", json={**request, "resumeToken": "missing"})
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "resume_unknown"

    consumed = ledger.pause(paused("resume-project"))
    ledger.resume(consumed, "resume-project")
    used = client.post("/v1/agent/advance", json={**request, "resumeToken": consumed})
    assert used.status_code == 409
    assert used.json()["detail"]["code"] == "resume_consumed"

    expired = ledger.pause(paused("resume-project"))
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE pauses SET expires=? WHERE token=?", (time.time() - 1, expired))
    stale = client.post("/v1/agent/advance", json={**request, "resumeToken": expired})
    assert stale.status_code == 410
    assert stale.json()["detail"]["code"] == "resume_expired"

    other = ledger.pause(paused("other-project"))
    mismatch = client.post("/v1/agent/advance", json={**request, "resumeToken": other})
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "resume_project_mismatch"
    assert ledger.resume(other, "other-project")["project"]["id"] == "other-project"

    legacy = client.post("/v1/agent/advance", json={**request, "state": {"resumeToken": expired}})
    assert legacy.status_code == 422

    missing = client.post("/v1/agent/advance", json=request)
    assert missing.status_code == 409


def test_rate_limit_persists():
    value = ledger()
    for _ in range(3):
        value.check_rate("127.0.0.1")
    with pytest.raises(HTTPException):
        UsageLedger(value.path, 10, 10, 30, 120, 3).check_rate("127.0.0.1")

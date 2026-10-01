import sqlite3
from concurrent.futures import ThreadPoolExecutor
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
    token = value.pause({"llm_calls": 8, "candidate_attempts": {"candidate": 3}})
    resumed = UsageLedger(value.path, 10, 10, 30, 120, 3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(resumed.resume, token) for _ in range(2)]
    assert sum(future.exception() is None for future in futures) == 1
    result = next(future.result() for future in futures if future.exception() is None)
    assert result["llm_calls"] == 8


def test_rate_limit_persists():
    value = ledger()
    for _ in range(3):
        value.check_rate("127.0.0.1")
    with pytest.raises(HTTPException):
        UsageLedger(value.path, 10, 10, 30, 120, 3).check_rate("127.0.0.1")

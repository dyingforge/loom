"""客户端 A/B 快照测试。"""
from __future__ import annotations

import json
import pathlib

import pytest

from client.store import (
    SLOT_A, SLOT_B, write, load, snapshot_to_project,
    corrupt_demo, _read_slot,
)


@pytest.fixture
def jail(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


def _latest_slot(jail: pathlib.Path) -> str:
    a = _read_slot(jail, SLOT_A)
    b = _read_slot(jail, SLOT_B)
    if a is None and b is None:
        return SLOT_A
    if a is None:
        return SLOT_B
    if b is None:
        return SLOT_A
    return SLOT_A if a["sequence"] >= b["sequence"] else SLOT_B


def test_write_then_load_roundtrip(jail: pathlib.Path) -> None:
    snap1 = {"id": "p", "version": 1, "goal": "g1",
             "workHours": {"start": "09:00", "end": "18:00"},
             "tasks": []}
    write(jail, snap1, sequence=1)
    loaded = load(jail)
    assert loaded is not None
    assert loaded["sequence"] == 1
    assert snapshot_to_project(loaded) == snap1


def test_subsequent_writes_have_higher_sequence(jail: pathlib.Path) -> None:
    for i in range(1, 5):
        snap = {"id": "p", "version": i, "goal": f"g{i}",
                "workHours": {"start": "09:00", "end": "18:00"},
                "tasks": []}
        write(jail, snap, sequence=i)
        assert load(jail)["sequence"] == i


def test_load_returns_latest_when_both_valid(jail: pathlib.Path) -> None:
    for i in (1, 2, 3, 4):
        write(jail, {"id": "p", "version": i, "goal": f"v{i}",
                     "workHours": {"start": "09:00", "end": "18:00"},
                     "tasks": []}, sequence=i)
    loaded = load(jail)
    assert loaded["sequence"] == 4
    assert snapshot_to_project(loaded)["version"] == 4


def test_corrupted_slot_falls_back(jail: pathlib.Path) -> None:
    write(jail, {"id": "p", "version": 1, "goal": "v1",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=1)
    write(jail, {"id": "p", "version": 2, "goal": "v2",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=2)
    latest = _latest_slot(jail)
    corrupt_demo(jail, latest)
    loaded = load(jail)
    assert loaded is not None
    assert loaded["sequence"] == 1
    assert snapshot_to_project(loaded)["version"] == 1


def test_load_returns_none_when_no_snapshot(jail: pathlib.Path) -> None:
    assert load(jail) is None


def test_partial_write_invalidates_only_corrupt_slot(jail: pathlib.Path) -> None:
    write(jail, {"id": "p", "version": 1, "goal": "v1",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=1)
    # 模拟 partial write：直接覆盖另一槽位为无效 JSON
    other = SLOT_B if _latest_slot(jail) == SLOT_A else SLOT_A
    (jail / other).write_text("{not-json", encoding="utf-8")
    loaded = load(jail)
    assert loaded is not None
    assert loaded["sequence"] == 1
    assert snapshot_to_project(loaded)["goal"] == "v1"


def test_tampered_checksum_does_not_load_but_valid_slot_does(jail: pathlib.Path) -> None:
    write(jail, {"id": "p", "version": 1, "goal": "v1",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=1)
    write(jail, {"id": "p", "version": 2, "goal": "v2",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=2)
    latest = _latest_slot(jail)
    body = json.loads((jail / latest).read_text(encoding="utf-8"))
    body["snapshot"]["goal"] = "tampered"
    (jail / latest).write_text(json.dumps(body), encoding="utf-8")
    loaded = load(jail)
    assert loaded is not None
    assert loaded["sequence"] == 1
    assert snapshot_to_project(loaded)["goal"] == "v1"


def test_write_keeps_version_monotonic(jail: pathlib.Path) -> None:
    """每次写入后版本号严格递增或保持不变（外部负责递增；存储只保留序列号）。"""
    write(jail, {"id": "p", "version": 1, "goal": "v1",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=1)
    write(jail, {"id": "p", "version": 2, "goal": "v2",
                 "workHours": {"start": "09:00", "end": "18:00"},
                 "tasks": []}, sequence=2)
    loaded = load(jail)
    assert loaded["sequence"] == 2

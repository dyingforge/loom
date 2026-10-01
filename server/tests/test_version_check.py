"""版本失配检测测试（issue 16）。"""
from __future__ import annotations

from server.runtime.version_check import check_version


def test_version_matches_after_one_increment() -> None:
    r = check_version(plan_base_version=1, current_version=2,
                      recalculation_count=0)
    assert r.ok
    assert not r.needs_recalculation


def test_version_mismatch_triggers_recalculation() -> None:
    r = check_version(plan_base_version=1, current_version=3,
                      recalculation_count=0)
    assert not r.ok
    assert r.needs_recalculation


def test_repeated_mismatch_stops_after_max() -> None:
    r = check_version(plan_base_version=1, current_version=5,
                      recalculation_count=1)
    assert not r.ok
    assert not r.needs_recalculation
    assert "重新发起" in r.reason


def test_recalculation_zero_keeps_open_until_max() -> None:
    r = check_version(plan_base_version=1, current_version=10,
                      recalculation_count=0)
    assert r.needs_recalculation

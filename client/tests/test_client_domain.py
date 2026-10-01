"""客户端领域独立实现，覆盖 vectors 中的 C1–C7 全部用例。"""
from __future__ import annotations

import json
import pathlib

import pytest

from client.domain import validate, analyze


VECTORS = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def _load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


def _codes(violations: list[dict]) -> list[str]:
    seen = []
    for v in violations:
        if v["code"] not in seen:
            seen.append(v["code"])
    return seen


@pytest.mark.parametrize("vector_file", [
    "c1_done_blocks.json",
    "c2_fixed_events.json",
    "c3_workhours_restdays.json",
    "c4_dependencies.json",
    "c5_total_hours.json",
    "c6_overlap.json",
])
def test_positive_cases_pass(vector_file: str) -> None:
    data = _load(vector_file)
    for case in data.get("positive", []):
        violations = validate(case["project"], case["candidate"])
        assert violations == [], (
            f"{vector_file} positive '{case['name']}' expected pass, "
            f"got {[(v['code'], v['blockId'], v['detail']) for v in violations]}"
        )


@pytest.mark.parametrize("vector_file", [
    "c1_done_blocks.json",
    "c2_fixed_events.json",
    "c3_workhours_restdays.json",
    "c4_dependencies.json",
    "c5_total_hours.json",
    "c6_overlap.json",
])
def test_negative_cases_have_expected_codes(vector_file: str) -> None:
    data = _load(vector_file)
    for case in data.get("negative", []):
        violations = validate(case["project"], case["candidate"])
        codes = _codes(violations)
        for code in case["expected_codes"]:
            assert code in codes


def test_combined_scenarios() -> None:
    data = _load("combined.json")
    for case in data["scenarios"]:
        violations = validate(case["project"], case["candidate"])
        codes = _codes(violations)
        if case["expected_codes"] == []:
            assert violations == []
        else:
            for code in case["expected_codes"]:
                assert code in codes


def test_analyze_finds_cycle_and_missing() -> None:
    project = {
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
    }
    a = analyze(project)
    assert len(a["cycles"]) >= 1
    assert "t3" in a["missingRefs"]

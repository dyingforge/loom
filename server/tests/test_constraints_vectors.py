"""加载 `vectors/` 下所有 C1–C7 验证向量，验证 server 端校验器与期望一致。

这是双实现单向量保证：客户端与服务器共用同一组向量。
"""
from __future__ import annotations

import json
import pathlib
from typing import Iterable

import pytest
from pydantic import TypeAdapter

from server.domain.constraints import check_adjustable, validate
from server.domain.models import Block, Candidate, Change, Project


VECTORS = pathlib.Path(__file__).resolve().parents[2] / "vectors"
PROJECT_ADAPTER = TypeAdapter(Project)


def _load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


def _normalize_violation_codes(violations: Iterable) -> list[str]:
    seen = []
    for v in violations:
        if v.code not in seen:
            seen.append(v.code)
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
        project = PROJECT_ADAPTER.validate_python(case["project"])
        cand = Candidate.model_validate(case["candidate"])
        violations = validate(project, cand)
        assert violations == [], (
            f"{vector_file} positive '{case['name']}' expected pass, "
            f"got {[(v.code, v.blockId, v.detail) for v in violations]}"
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
        project = PROJECT_ADAPTER.validate_python(case["project"])
        cand = Candidate.model_validate(case["candidate"])
        violations = validate(project, cand)
        codes = _normalize_violation_codes(violations)
        expected = case["expected_codes"]
        for code in expected:
            assert code in codes, (
                f"{vector_file} negative '{case['name']}' "
                f"期望违规 {code}，实际 {codes}"
            )


def test_c7_adjustable_positive_and_negative() -> None:
    data = _load("c7_adjustable.json")
    for case in data.get("positive", []):
        project = PROJECT_ADAPTER.validate_python(case["project"])
        changes = [Change.model_validate(c) for c in case["plan_changes"]]
        assert check_adjustable(changes, project) == []
    for case in data.get("negative", []):
        project = PROJECT_ADAPTER.validate_python(case["project"])
        changes = [Change.model_validate(c) for c in case["plan_changes"]]
        codes = _normalize_violation_codes(check_adjustable(changes, project))
        for code in case["expected_codes"]:
            assert code in codes


def test_combined_scenarios() -> None:
    data = _load("combined.json")
    for case in data["scenarios"]:
        project = PROJECT_ADAPTER.validate_python(case["project"])
        cand = Candidate.model_validate(case["candidate"])
        violations = validate(project, cand)
        codes = _normalize_violation_codes(violations)
        expected = case["expected_codes"]
        if expected == []:
            assert violations == [], (
                f"combined '{case['name']}' 应当通过，实际 {codes}"
            )
        else:
            for code in expected:
                assert code in codes, (
                    f"combined '{case['name']}' 期望 {code}，实际 {codes}"
                )

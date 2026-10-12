import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "vectors"
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter
from server.domain.capacity import capacity
from server.domain.constraints import check_adjustable, validate
from server.domain.models import Candidate, Change, Project
from datetime import datetime

PROJECT_ADAPTER = TypeAdapter(Project)


def unique(violations):
    seen = []
    for v in violations:
        if v.code not in seen:
            seen.append(v.code)
    return seen


def normalize_candidate(candidate):
    blocks = []
    for block in candidate["blocks"]:
        item = dict(block)
        if "id" not in item:
            item["id"] = None
        if "done" not in item:
            item["done"] = False
        blocks.append(item)
    return {"blocks": blocks}


def normalize_project(project):
    item = dict(project)
    tasks = []
    for task in item["tasks"]:
        t = dict(task)
        blocks = []
        for block in t["blocks"]:
            b = dict(block)
            if "done" not in b:
                b["done"] = False
            blocks.append(b)
        t["blocks"] = blocks
        tasks.append(t)
    item["tasks"] = tasks
    return item


def normalize_changes(changes):
    out = []
    for change in changes:
        c = dict(change)
        if "before" not in c:
            c["before"] = None
        if "after" not in c:
            c["after"] = None
        out.append(c)
    return out


def add_capacity_case(cases):
    synthetic = {
        "id": "cap", "version": 0, "goal": "g",
        "deadline": "2026-10-09T18:00:00",
        "milestones": [],
        "fixedEvents": [{"id": "f1", "title": "会议",
                          "start": "2026-10-05T09:00:00", "end": "2026-10-05T11:00:00"}],
        "workHours": {"start": "09:00", "end": "18:00"}, "restDays": [5, 6],
        "preferences": "", "autoAdjust": False,
        "tasks": [
            {"id": "t1", "title": "a", "priority": 1, "remainingHours": 3, "done": False,
             "dependsOn": [], "adjustable": True,
             "blocks": [{"id": "b1", "taskId": "t1", "start": "2026-10-02T09:00:00",
                         "end": "2026-10-02T12:00:00", "done": True}]},
            {"id": "t2", "title": "b", "priority": 1, "remainingHours": 5, "done": False,
             "dependsOn": [], "adjustable": True, "blocks": []},
        ],
    }
    project = PROJECT_ADAPTER.validate_python(synthetic)
    expected = capacity(project, datetime(2026, 10, 2, 9, 0, 0))
    cases.append({"kind": "capacity", "file": "synthetic", "name": "capacity",
                  "expected_capacity": expected,
                  "project": normalize_project(synthetic),
                  "now": "2026-10-02T09:00:00"})


def build_cases():
    cases = []
    for filename in ["c1_done_blocks.json", "c2_fixed_events.json",
                     "c3_workhours_restdays.json", "c4_dependencies.json",
                     "c5_total_hours.json", "c6_overlap.json"]:
        data = json.loads((VECTORS / filename).read_text(encoding="utf-8"))
        for case in data.get("positive", []):
            project = PROJECT_ADAPTER.validate_python(case["project"])
            cand = Candidate.model_validate(case["candidate"])
            violations = validate(project, cand)
            expected = unique(violations)
            assert expected == [], (filename, case["name"], expected)
            cases.append({"kind": "validate", "file": filename,
                          "name": "positive: " + case["name"],
                          "expected": expected,
                          "project": normalize_project(case["project"]),
                          "candidate": normalize_candidate(case["candidate"])})
        for case in data.get("negative", []):
            project = PROJECT_ADAPTER.validate_python(case["project"])
            cand = Candidate.model_validate(case["candidate"])
            cases.append({"kind": "validate", "file": filename,
                          "name": "negative: " + case["name"],
                          "expected": case["expected_codes"],
                          "project": normalize_project(case["project"]),
                          "candidate": normalize_candidate(case["candidate"])})
    data = json.loads((VECTORS / "c7_adjustable.json").read_text(encoding="utf-8"))
    for case in data.get("positive", []):
        project = PROJECT_ADAPTER.validate_python(case["project"])
        changes = [Change.model_validate(c) for c in case["plan_changes"]]
        assert check_adjustable(changes, project) == []
        cases.append({"kind": "adjustable", "file": "c7_adjustable.json",
                      "name": "positive: " + case["name"], "expected": [],
                      "project": normalize_project(case["project"]),
                      "plan_changes": normalize_changes(case["plan_changes"])})
    for case in data.get("negative", []):
        project = PROJECT_ADAPTER.validate_python(case["project"])
        cases.append({"kind": "adjustable", "file": "c7_adjustable.json",
                      "name": "negative: " + case["name"],
                      "expected": case["expected_codes"],
                      "project": normalize_project(case["project"]),
                      "plan_changes": normalize_changes(case["plan_changes"])})
    data = json.loads((VECTORS / "combined.json").read_text(encoding="utf-8"))
    for case in data["scenarios"]:
        project = PROJECT_ADAPTER.validate_python(case["project"])
        cand = Candidate.model_validate(case["candidate"])
        cases.append({"kind": "validate", "file": "combined.json",
                      "name": case["name"], "expected": case["expected_codes"],
                      "project": normalize_project(case["project"]),
                      "candidate": normalize_candidate(case["candidate"])})
    add_capacity_case(cases)
    return cases


def compare(expected, computed):
    if expected == []:
        return computed == []
    for code in expected:
        if code not in computed:
            return False
    return True


def main():
    host = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host"
    if not host.is_file():
        raise SystemExit("找不到 card-host，请先运行 scripts/build_native.py")
    cases = build_cases()
    print(f"向量用例总数：{len(cases)}")
    app_data = ROOT / ".scratch/issue2-vectors"
    jail = app_data / "loom.pm-calendar"
    if jail.exists():
        import shutil
        shutil.rmtree(jail)
    jail.mkdir(parents=True)
    (jail / "vector-check-input.json").write_text(
        json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")
    port = 8156
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit("端口被占用")
    env = dict(os.environ, TMPDIR=str(ROOT / ".scratch/native-temp"),
               MAKEPAD_REMOTE=str(port), MAKEPAD_HIDE_WINDOWS="1")
    command = [str(host), "--bundle", str(ROOT / "bundle"),
               "--app-data", str(app_data), "--allow-unsigned", "--stamp",
               "--size", "1440x1000"]
    log = (app_data / "card-host.log").open("w")
    process = subprocess.Popen(command, cwd=host.resolve().parents[2], env=env,
                               stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
    output_file = jail / "vector-check-output.json"
    until = time.monotonic() + 60
    output = None
    while time.monotonic() < until:
        if process.poll() is not None:
            break
        if output_file.is_file():
            try:
                output = json.loads(output_file.read_text(encoding="utf-8"))
            except ValueError:
                output = None
            if output is not None:
                break
        time.sleep(0.2)
    if output is None:
        print("未生成输出文件，详情见 " + str(log.name))
        process.terminate()
        raise SystemExit(1)
    computed_map = {c["file"] + "|" + c["name"]: c for c in output["cases"]}
    failed = 0
    rows = []
    for case in cases:
        key = case["file"] + "|" + case["name"]
        computed = computed_map.get(key)
        if case["kind"] == "capacity":
            if computed is None:
                failed += 1
                rows.append([case["file"], case["name"], case["expected_capacity"], "MISSING", "FAIL"])
                continue
            got = computed.get("capacity")
            exp = case["expected_capacity"]
            ok = (abs(got["remainingHours"] - exp["remainingHours"]) < 0.001
                  and abs(got["availableHours"] - exp["availableHours"]) < 0.001
                  and abs(got["gapHours"] - exp["gapHours"]) < 0.001)
            if not ok:
                failed += 1
            rows.append([case["file"], case["name"], exp, got, "PASS" if ok else "FAIL"])
            continue
        codes = computed.get("codes") if computed else None
        if codes is None:
            failed += 1
            rows.append([case["file"], case["name"], case["expected"], "MISSING", "FAIL"])
            continue
        ok = compare(case["expected"], codes)
        if not ok:
            failed += 1
        rows.append([case["file"], case["name"], case["expected"], codes,
                     "PASS" if ok else "FAIL"])
    import httpx
    try:
        httpx.get(f"http://127.0.0.1:{port}/quit", timeout=5)
    except Exception:
        pass
    process.wait(timeout=30)
    for row in rows:
        print(f"{row[4]:5} {row[0]:22} {row[1]:40} 期望={row[2]} 实际={row[3]}")
    print(f"通过 {len(rows) - failed} / {len(rows)}")
    if failed:
        raise SystemExit(1)
    print("全部向量与 Python 参考输出一致")


if __name__ == "__main__":
    main()

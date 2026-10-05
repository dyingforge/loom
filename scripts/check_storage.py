import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE_FILES = ("state-a.json", "state-b.json")
BUSINESS_FIELDS = ("schema", "project", "draftProject", "plan", "receipt", "pendingVerification",
                   "calendar", "capacity", "formalCapacity", "activeJob", "lastRequest", "phase", "error",
                   "savedAt", "confirmedRationale", "confirmedRisks", "questionId", "question", "resumeToken",
                   "workingProject", "utcOffset", "timezone", "month", "selectedDay", "showingFormal")
DRAFT_FIELDS = ("projectId", "questionId", "revision", "goal", "deadline", "answer")

sys.path.insert(0, str(ROOT / "scripts"))
from check_client_state import Remote, free_port


def complete_record(record):
    if not isinstance(record, dict):
        return False
    for field in ("schema", "sequence", "businessVersion", "business", "draft"):
        if field not in record:
            return False
    if record["schema"] != 1 or record["sequence"] < 1 or record["businessVersion"] < 0:
        return False
    business = record["business"]
    if not isinstance(business, dict):
        return False
    for field in BUSINESS_FIELDS:
        if field not in business:
            return False
    saved_project = business["project"]
    if not isinstance(saved_project, dict) or "id" not in saved_project:
        return False
    draft = record["draft"]
    if not isinstance(draft, dict):
        return False
    for field in DRAFT_FIELDS:
        if field not in draft:
            return False
    if draft["projectId"] != saved_project["id"] or draft["questionId"] == "":
        return False
    return True


class StorageCheck:
    def __init__(self, host):
        self.host = host.resolve()
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.run_dir = ROOT / ".scratch" / "storage-check" / f"{stamp}-{uuid4().hex[:6]}"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "tmp").mkdir()
        self.app_data = self.run_dir / "app-data"
        self.bundle = self.run_dir / "bundle"
        self.remote_port = free_port()
        self.process = None
        self.remote = None
        self.results = {}

    def prepare_bundle(self):
        # 复制真实应用包并加盖官方摘要，不改写 main.splash，也不改主机清单。
        shutil.copytree(ROOT / "bundle", self.bundle)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.app_id = manifest["id"]
        subprocess.run([str(self.host.parent / "hub"), "stamp", str(self.bundle)], check=True)

    def jail(self):
        return self.app_data / self.app_id

    def path_of(self, name):
        return self.jail() / name

    def raw_text(self, name):
        path = self.path_of(name)
        return path.read_text() if path.exists() else None

    def stable_text(self, name):
        path = self.path_of(name)
        if not path.exists():
            return None
        first = path.read_text()
        time.sleep(0.05)
        second = path.read_text()
        return second if first == second else None

    def read_valid(self, name):
        text = self.stable_text(name)
        assert text is not None, f"{name} 不存在或正在写入"
        record = json.loads(text)
        assert complete_record(record), f"{name} 不是完整记录"
        return record

    def read_valid_optional(self, name):
        text = self.stable_text(name)
        if text is None or text == "":
            return None
        record = json.loads(text)
        assert complete_record(record), f"{name} 不是完整记录"
        return record

    def latest_valid(self):
        candidates = []
        for name in STATE_FILES:
            record = self.read_valid_optional(name)
            if record is not None:
                candidates.append((name, record))
        assert candidates, "没有有效记录"
        return max(candidates, key=lambda item: item[1]["sequence"])

    def wait_for(self, describe, probe, timeout=30):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            value = probe()
            if value:
                return value
            time.sleep(0.2)
        raise AssertionError(f"等待超时：{describe}")

    def wait_for_value(self, identifier, expected, timeout=30):
        return self.wait_for(f"{identifier}={expected}",
                             lambda: self.remote.value(identifier) == expected, timeout)

    def status_text(self):
        for value in self.remote.snapshot():
            if value.get("i") == "status_label":
                return value.get("t", "")
        return None

    def start_client(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_client
        run_client.check_native_build(self.host)
        device_dir = self.jail()
        device_dir.mkdir(parents=True, exist_ok=True)
        local = datetime.now().astimezone()
        timezone_name = Path("/etc/localtime").resolve().as_posix().split("zoneinfo/")[-1]
        (device_dir / "device.json").write_text(json.dumps(
            {"utcOffset": local.utcoffset().total_seconds() / 3600, "timezone": timezone_name}))
        env = dict(os.environ, TMPDIR=str(self.run_dir / "tmp"),
                   MAKEPAD_REMOTE=str(self.remote_port), MAKEPAD_HIDE_WINDOWS="1")
        log = (self.run_dir / "card-host.log").open("a")
        self.process = subprocess.Popen(
            [str(self.host), "--bundle", str(self.bundle), "--app-data", str(self.app_data),
             "--allow-unsigned", "--stamp", "--size", "1440x1000"],
            cwd=str(self.host.parents[2]), env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT)
        until = time.monotonic() + 90
        while time.monotonic() < until:
            if self.process.poll() is not None:
                raise SystemExit((self.run_dir / "card-host.log").read_text())
            with socket.socket() as probe:
                ready = probe.connect_ex(("127.0.0.1", self.remote_port)) == 0
            if ready:
                response = httpx.get(f"http://127.0.0.1:{self.remote_port}/snap", timeout=10)
                if response.status_code == 200 and any(item["i"] == "timezone_label" for item in response.json()["s"]):
                    self.remote = Remote(self.remote_port)
                    return
            time.sleep(0.3)
        raise AssertionError("客户端启动超时")

    def stop_client(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            Remote(self.remote_port).quit()
            until = time.monotonic() + 20
            while self.process.poll() is None and time.monotonic() < until:
                time.sleep(0.2)
            if self.process.poll() is None:
                self.process.terminate()
                until = time.monotonic() + 20
                while self.process.poll() is None and time.monotonic() < until:
                    time.sleep(0.2)
                if self.process.poll() is None:
                    self.process.kill()
                    self.process.wait()
        self.process = None
        self.remote = None

    def stop(self):
        self.stop_client()

    def type_into(self, identifier, text):
        # 等待界面与同步写入完成后再读取文件。
        self.remote.focus(identifier)
        self.remote.retype(text)
        self.remote.ensure_value(identifier, text)
        assert self.remote.value(identifier) == text, self.remote.value(identifier)

    def run(self):
        self.prepare_bundle()
        self.start_client()

        # 首次启动初始化，写入一条完整记录。
        name, initial = self.wait_for("首次初始化记录", lambda: self.first_record(), 30)
        assert initial["sequence"] == 1, initial
        assert initial["businessVersion"] == 1, initial
        self.results["初始化"] = {"文件": name, "sequence": initial["sequence"],
                                "businessVersion": initial["businessVersion"]}

        deadline = (datetime.now().astimezone() + timedelta(days=30)).date().isoformat()
        goals = ["产品功能演示准备", "准备产品功能演示", "准备产品功能演示和讲解"]
        revisions = []
        for goal in goals:
            self.type_into("goal_input", goal)
            name, record = self.wait_for("连续中文草稿", lambda: self.draft_record("initial", goal), 30)
            revisions.append(record["draft"]["revision"])
        self.type_into("deadline_input", deadline)
        name, record = self.wait_for("截止日期草稿",
                                     lambda: self.draft_record("initial", goals[-1], deadline), 30)
        revisions.append(record["draft"]["revision"])
        assert revisions == sorted(set(revisions)) and len(revisions) == len(set(revisions)), revisions
        status = self.wait_for("初始状态提示", self.status_text, 30)
        assert "失败" not in status, status
        self.results["连续中文输入"] = {"目标": goals[-1], "截止日期": deadline,
                                     "草稿修订号": revisions, "界面状态": status}

        # 界面与文件一致，记录完整。
        latest_name, latest = self.latest_valid()
        assert latest["draft"]["goal"] == goals[-1], latest["draft"]
        assert latest["draft"]["deadline"] == deadline, latest["draft"]
        self.results["回读一致"] = {"最新文件": latest_name, "sequence": latest["sequence"],
                                 "businessVersion": latest["businessVersion"],
                                 "草稿修订号": latest["draft"]["revision"],
                                 "草稿目标": latest["draft"]["goal"], "草稿截止日期": latest["draft"]["deadline"]}

        sizes = {name: self.path_of(name).stat().st_size for name in STATE_FILES if self.path_of(name).exists()}
        assert all(size < 1024 * 1024 for size in sizes.values()), sizes
        assert sum(sizes.values()) < 4 * 1024 * 1024, sizes
        self.results["文件大小"] = sizes

        # 关闭并重启，恢复草稿且不再写入新序号。
        self.stop_client()
        self.start_client()
        self.wait_for_value("goal_input", goals[-1])
        self.wait_for_value("deadline_input", deadline)
        restarted_name, restarted = self.latest_valid()
        assert restarted["sequence"] == latest["sequence"], (restarted["sequence"], latest["sequence"])
        assert restarted["draft"]["goal"] == goals[-1], restarted["draft"]
        self.results["关闭重启"] = {"界面目标": self.remote.value("goal_input"),
                                 "草稿目标": restarted["draft"]["goal"],
                                 "界面截止日期": self.remote.value("deadline_input"),
                                 "草稿截止日期": restarted["draft"]["deadline"],
                                 "sequence": restarted["sequence"],
                                 "businessVersion": restarted["businessVersion"]}

        # 部分写入：截断最新文件，重启应恢复另一份完整记录并提示中断保存。
        newest = latest_name
        older = [name for name in STATE_FILES if name != newest][0]
        older_record = self.read_valid(older)
        raw = self.path_of(newest).read_text()
        truncated = raw[: len(raw) // 2]
        self.path_of(newest).write_text(truncated)
        self.stop_client()
        self.start_client()
        recovered = self.read_valid(older)
        assert recovered["sequence"] == older_record["sequence"], recovered["sequence"]
        self.wait_for_value("goal_input", older_record["draft"]["goal"])
        assert self.path_of(newest).read_text() == truncated, "恢复启动改写了损坏文件"
        status = self.wait_for("中断保存提示", self.status_text, 30)
        assert "中断" in status, status
        self.results["部分写入恢复"] = {"损坏文件": newest, "恢复文件": older, "恢复序号": recovered["sequence"],
                                     "恢复草稿目标": older_record["draft"]["goal"],
                                     "界面目标": self.remote.value("goal_input"), "界面提示": status}

        # 全部无效：两份文件都截断，重启应停止初始化并保留文件。
        self.stop_client()
        truncated_all = {}
        for name in STATE_FILES:
            raw = self.path_of(name).read_text()
            truncated_all[name] = raw[: max(1, len(raw) // 3)]
            self.path_of(name).write_text(truncated_all[name])
        self.start_client()
        status = self.wait_for("全部无效提示", self.status_text, 30)
        assert self.remote.value("goal_input") == "", self.remote.value("goal_input")
        for name in STATE_FILES:
            assert self.path_of(name).read_text() == truncated_all[name], f"{name} 被改写"
        assert sorted(path.name for path in self.jail().iterdir() if path.name.startswith("state-")) == ["state-a.json", "state-b.json"]
        self.results["全部无效停止"] = {"文件": sorted(truncated_all), "界面目标": self.remote.value("goal_input"),
                                     "界面提示": status}
        assert "无效" in status, status

        (self.run_dir / "results.json").write_text(json.dumps(self.results, ensure_ascii=False, indent=2))
        print(json.dumps(self.results, ensure_ascii=False, indent=2))
        print(f"文件存储检查通过，证据目录 {self.run_dir}")

    def first_record(self):
        for name in STATE_FILES:
            record = self.read_valid_optional(name)
            if record is not None and record["sequence"] == 1:
                return name, record
        return None

    def draft_record(self, question_id, goal, deadline=None):
        latest = self.latest_valid()
        name, record = latest
        if record["draft"]["questionId"] != question_id:
            return None
        if record["draft"]["goal"] != goal:
            return None
        if deadline is not None and record["draft"]["deadline"] != deadline:
            return None
        return name, record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=Path,
                        default=ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host")
    args = parser.parse_args()
    check = StorageCheck(args.host)
    try:
        check.run()
    finally:
        check.stop()

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host"
HUB = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/hub"
STATE_FILES = ("state-a.json", "state-b.json")
COMPOSE_GOAL = ("我要准备一场产品功能演示，内容包括新增记录、列表和本地保存，每项约半小时。"
                "演示日期还没定，可能是本周五或下周一，请先确认日期再安排。")


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Remote:
    def __init__(self, port):
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)

    def snapshot(self):
        return self.client.get("/snap").raise_for_status().json()["s"]

    def find(self, identifier):
        for _ in range(50):
            for value in self.snapshot():
                if value.get("i") == identifier:
                    return value
            time.sleep(0.2)
        raise AssertionError(f"没有找到控件 {identifier}")

    def value(self, identifier):
        return self.find(identifier)["val"]

    def quit(self):
        self.client.get("/quit").raise_for_status()

    def click_value(self, value, wait=1):
        x, y, width, height = value["r"]
        self.client.get("/click", params={"x": x + width / 2, "y": y + height / 2, "wait": wait}).raise_for_status()

    def click(self, text):
        for _ in range(50):
            for value in self.snapshot():
                if value.get("t") == text and value["ty"] != "Splash":
                    self.click_value(value)
                    return
            time.sleep(0.2)
        raise AssertionError(f"没有找到按钮 {text}")

    def focus(self, identifier):
        self.click_value(self.find(identifier))

    def retype(self, text):
        self.client.get("/k", params={"k": "down", "c": "KeyA", "cmd": 1}).raise_for_status()
        self.client.get("/t", params={"t": text, "wait": 0}).raise_for_status()

    def replace(self, identifier, text):
        self.focus(identifier)
        self.retype(text)

    def ensure_value(self, identifier, text):
        for _ in range(5):
            if self.value(identifier) == text:
                return
            self.replace(identifier, text)
        assert self.value(identifier) == text


class ClientStateCheck:
    def __init__(self):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.run_dir = ROOT / ".scratch" / "client-state-check" / f"{stamp}-{uuid4().hex[:6]}"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "tmp").mkdir()
        self.app_data = self.run_dir / "app-data"
        self.bundle = self.run_dir / "bundle"
        self.remote_port = free_port()
        self.client_process = None
        self.remote = None
        self.results = {}

    def build_native(self):
        subprocess.run([sys.executable, str(ROOT / "scripts/build_native.py")], check=True)

    def prepare_bundle(self):
        # 复制真实应用包并加盖官方摘要，不改写 main.splash，也不改主机清单。
        shutil.copytree(ROOT / "bundle", self.bundle)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.app_id = manifest["id"]
        subprocess.run([str(HUB), "stamp", str(self.bundle)], check=True)

    def start_client(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_client
        run_client.check_native_build(HOST.resolve())
        self.app_data.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMPDIR=str(self.run_dir / "tmp"),
                   MAKEPAD_REMOTE=str(self.remote_port), MAKEPAD_HIDE_WINDOWS="1")
        log = (self.run_dir / "card-host.log").open("a")
        self.client_process = subprocess.Popen(
            [str(HOST.resolve()), "--bundle", str(self.bundle), "--app-data", str(self.app_data),
             "--allow-unsigned", "--stamp", "--size", "1440x1000"],
            cwd=str(HOST.resolve().parents[2]), env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT)
        until = time.monotonic() + 90
        while time.monotonic() < until:
            if self.client_process.poll() is not None:
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
        if self.client_process is None:
            return
        if self.client_process.poll() is None:
            Remote(self.remote_port).quit()
            until = time.monotonic() + 20
            while self.client_process.poll() is None and time.monotonic() < until:
                time.sleep(0.2)
            if self.client_process.poll() is None:
                self.client_process.terminate()
                until = time.monotonic() + 20
                while self.client_process.poll() is None and time.monotonic() < until:
                    time.sleep(0.2)
                if self.client_process.poll() is None:
                    self.client_process.kill()
                    self.client_process.wait()
        self.client_process = None
        self.remote = None

    def stop(self):
        self.stop_client()

    def state_records(self):
        records = []
        for name in STATE_FILES:
            path = self.app_data / self.app_id / name
            if path.exists():
                records.append(json.loads(path.read_text()))
        return records

    def latest_record(self):
        records = self.state_records()
        if not records:
            return None
        return max(records, key=lambda record: record["sequence"])

    def read_business(self):
        record = self.latest_record()
        if record is None:
            return None, None
        return record["businessVersion"], record["business"]

    def read_draft(self, question_id):
        record = self.latest_record()
        if record is None:
            return None
        draft = record["draft"]
        if draft["questionId"] != question_id:
            return None
        return draft

    def wait_draft(self, question_id, expect, timeout=60):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            draft = self.read_draft(question_id)
            if draft is not None and all(draft[key] == value for key, value in expect.items()):
                return draft
            time.sleep(0.2)
        raise AssertionError(f"草稿没有到 {expect}: {self.read_draft(question_id)}")

    def wait_until(self, describe, probe, timeout):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            value = probe()
            if value:
                return value
            time.sleep(0.3)
        raise AssertionError(f"等待超时：{describe}")

    def run(self):
        self.prepare_bundle()
        self.start_client()

        deadline = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=30)).date().isoformat()
        goals = ["产品功能演示准备", "准备产品功能演示", "准备产品功能演示和讲解", COMPOSE_GOAL]
        self.remote.focus("goal_input")
        for goal in goals:
            self.remote.retype(goal)
        self.remote.ensure_value("goal_input", goals[-1])
        self.remote.focus("deadline_input")
        self.remote.retype(deadline)
        self.remote.ensure_value("deadline_input", deadline)
        draft = self.wait_draft("initial", {"goal": goals[-1], "deadline": deadline})
        version, record = self.read_business()
        assert version >= 1 and record["questionId"] == "initial", (version, record.get("questionId"))
        self.results["输入草稿"] = {"中文目标": goals[-1], "截止日期": deadline, "草稿修订号": draft["revision"]}
        self.results["业务版本"] = {"version": version, "questionId": record["questionId"]}

        self.stop_client()
        self.start_client()
        assert self.remote.value("goal_input") == goals[-1], self.remote.value("goal_input")
        assert self.remote.value("deadline_input") == deadline, self.remote.value("deadline_input")
        restored = self.read_draft("initial")
        assert restored["goal"] == goals[-1] and restored["deadline"] == deadline, restored
        self.results["重启恢复"] = {"界面目标": self.remote.value("goal_input"), "草稿目标": restored["goal"],
                                 "界面截止日期": self.remote.value("deadline_input"),
                                 "草稿截止日期": restored["deadline"], "草稿修订号": restored["revision"]}

        self.remote.click("生成计划")
        business = self.wait_until("真实模型追问", self.clarify_business, 180)
        question_id = business["questionId"]
        question = business["question"]
        assert question_id not in ("", "initial") and question, "模型没有返回有效追问"
        self.results["真实追问"] = {"questionId": question_id, "question": question}

        answers = ["安排在本周五上午 10 点。", "安排在本周五上午 10 点，方便大家参加。"]
        self.remote.focus("advice_input")
        for answer in answers:
            self.remote.retype(answer)
        self.remote.ensure_value("advice_input", answers[-1])
        answer_draft = self.wait_draft(question_id, {"answer": answers[-1]})
        assert self.remote.value("advice_input") == answers[-1], self.remote.value("advice_input")
        self.results["回答草稿"] = {"中文回答": answers[-1], "草稿修订号": answer_draft["revision"],
                                 "问题标识": question_id}

        self.stop_client()
        self.start_client()
        assert self.remote.value("advice_input") == answers[-1], self.remote.value("advice_input")
        restored_answer = self.read_draft(question_id)
        assert restored_answer["answer"] == answers[-1], restored_answer
        self.results["回答重启恢复"] = {"界面回答": self.remote.value("advice_input"),
                                     "草稿回答": restored_answer["answer"],
                                     "草稿修订号": restored_answer["revision"]}

        before = self.read_draft(question_id)["revision"]
        self.remote.click("提交回答并继续")
        after = self.wait_until("回答草稿先于恢复请求保存", lambda: self.revision_after(question_id, before), 60)
        resumed = self.wait_until("真实恢复请求已发送", lambda: self.resume_sent(question_id), 240)
        self.results["回答提交"] = {"中文回答": answers[-1], "提交前修订号": before, "提交后修订号": after,
                                 "恢复后状态": resumed, "问题标识": question_id}

        (self.run_dir / "results.json").write_text(json.dumps(self.results, ensure_ascii=False, indent=2))
        print(json.dumps(self.results, ensure_ascii=False, indent=2))
        print("真实客户端状态检查通过")

    def clarify_business(self):
        version, record = self.read_business()
        if record is not None and record.get("phase") == "clarify" and record.get("questionId") not in ("", "initial"):
            return record
        return None

    def revision_after(self, question_id, before):
        draft = self.read_draft(question_id)
        if draft is not None and draft["revision"] > before:
            return draft["revision"]
        return None

    def resume_sent(self, question_id):
        version, record = self.read_business()
        if record is None:
            return None
        phase = record.get("phase")
        assert phase != "failed", phase
        if phase == "candidate":
            return "candidate"
        if phase == "clarify" and record.get("questionId") != question_id:
            return "clarify"
        return None


if __name__ == "__main__":
    check = ClientStateCheck()
    try:
        check.run()
    finally:
        check.stop()

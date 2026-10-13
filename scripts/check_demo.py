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

GOAL = "完成阅读记录应用的演示准备：检查新增记录和列表、本地保存、编写讲解说明，每项约半小时至一小时。"
REVISE = "请新增一个独立任务「演示设备检查」，工时 0.5 小时，安排在所有其他任务之前，原有任务标题与工时保持。"
ANSWER = "安排在上午 09:00 开始。"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def next_workday_epoch():
    """与客户端 next_workday 一致：明天起第一个非周末日的东八区当地午夜 epoch。"""
    day = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=1)).date()
    while day.weekday() >= 5:
        day += timedelta(days=1)
    epoch_day = datetime(1970, 1, 1, tzinfo=timezone(timedelta(hours=8))).date()
    return (day.toordinal() - epoch_day.toordinal()) * 86400 - 8 * 3600


class Remote:
    def __init__(self, port):
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)

    def snapshot(self):
        return self.client.get("/snap").raise_for_status().json()["s"]

    def scroll(self, amount):
        self.client.get("/m", params={"k": "scroll", "x": 1000, "y": 700, "dy": amount, "wait": 1}).raise_for_status()

    def scroll_to_top(self):
        for _ in range(10):
            self.scroll(-800)

    def click_day(self, epoch):
        """按 calendar_grid 几何位置点击东八区日期对应的日历格。"""
        from datetime import datetime as dt
        day = dt.fromtimestamp(epoch + 8 * 3600, tz=timezone(timedelta(hours=8)))
        month_start = dt(day.year, day.month, 1, tzinfo=timezone(timedelta(hours=8)))
        lead = month_start.weekday()
        index = (day.toordinal() - month_start.toordinal()) + lead
        row, column = divmod(index, 7)
        grid = self.find(identifier="calendar_grid")
        gx, gy, _, _ = grid["r"]
        self.client.get("/click", params={"x": gx + column * 144 + 72, "y": gy + row * 120 + 60, "wait": 1}).raise_for_status()

    def find(self, identifier=None, text=None):
        for attempt in range(20):
            values = [value for value in self.snapshot()
                      if value["ty"] != "Splash"
                      and (identifier is None or value.get("i") == identifier)
                      and (text is None or value.get("t") == text)
                      and 0 <= value["r"][1] < 970]
            if values:
                assert len(values) == 1, values
                return values[0]
            self.scroll(220 if attempt < 10 else -220)
        raise AssertionError((identifier, text))

    def value(self, identifier):
        return self.find(identifier=identifier)["val"]

    def click_value(self, value, wait=1):
        x, y, width, height = value["r"]
        self.client.get("/click", params={"x": x + width / 2, "y": y + height / 2, "wait": wait}).raise_for_status()

    def click(self, text):
        self.click_value(self.find(text=text))

    def click_first(self, text):
        """点击同文本控件中最靠上的一个（用于当天安排的逐块操作）。"""
        values = []
        for attempt in range(20):
            values = [value for value in self.snapshot()
                      if value["ty"] != "Splash" and value.get("t") == text
                      and 0 <= value["r"][1] < 970]
            if values:
                break
            self.scroll(220 if attempt < 10 else -220)
        assert values, text
        top = min(values, key=lambda value: value["r"][1])
        self.click_value(top)

    def focus(self, identifier):
        self.click_value(self.find(identifier=identifier))

    def retype(self, text):
        self.client.get("/k", params={"k": "down", "c": "KeyA", "cmd": 1}).raise_for_status()
        self.client.get("/t", params={"t": text, "wait": 0}).raise_for_status()

    def fill(self, identifier, text):
        self.focus(identifier)
        self.retype(text)
        assert self.value(identifier) == text, (self.value(identifier), text)

    def quit(self):
        self.client.get("/quit").raise_for_status()


class DemoCheck:
    def __init__(self):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.run_dir = ROOT / ".scratch" / "demo-check" / f"{stamp}-{uuid4().hex[:6]}"
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "tmp").mkdir()
        self.app_data = self.run_dir / "app-data"
        self.bundle = self.run_dir / "bundle"
        self.remote_port = free_port()
        self.window_size = "1440x1000"
        self.client_process = None
        self.remote = None
        self.results = {}

    def prepare_bundle(self):
        shutil.copytree(ROOT / "bundle", self.bundle)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.app_id = manifest["id"]
        subprocess.run([str(HUB), "stamp", str(self.bundle)], check=True)

    def start_client(self):
        self.app_data.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, TMPDIR=str(self.run_dir / "tmp"),
                   MAKEPAD_REMOTE=str(self.remote_port), MAKEPAD_HIDE_WINDOWS="1")
        log = (self.run_dir / "card-host.log").open("a")
        self.client_process = subprocess.Popen(
            [str(HOST.resolve()), "--bundle", str(self.bundle), "--app-data", str(self.app_data),
             "--allow-unsigned", "--stamp", "--size", self.window_size],
            cwd=str(HOST.resolve().parents[2]), env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT)
        until = time.monotonic() + 90
        while time.monotonic() < until:
            if self.client_process.poll() is not None:
                raise SystemExit((self.run_dir / "card-host.log").read_text())
            try:
                if any(item.get("i") == "timezone_label" for item in httpx.get(
                        f"http://127.0.0.1:{self.remote_port}/snap", timeout=10).json()["s"]):
                    self.remote = Remote(self.remote_port)
                    return
            except Exception:
                pass
            time.sleep(0.3)
        raise AssertionError("客户端启动超时")

    def stop_client(self):
        if self.client_process is None:
            return
        if self.client_process.poll() is None:
            try:
                Remote(self.remote_port).quit()
            except Exception:
                pass
            until = time.monotonic() + 20
            while self.client_process.poll() is None and time.monotonic() < until:
                time.sleep(0.2)
            if self.client_process.poll() is None:
                self.client_process.terminate()
                self.client_process.wait()
        self.client_process = None
        self.remote = None

    def latest_record(self):
        records = []
        for name in STATE_FILES:
            path = self.app_data / self.app_id / name
            if path.exists():
                records.append(json.loads(path.read_text()))
        return max(records, key=lambda record: record["sequence"]) if records else None

    def business(self):
        return self.latest_record()["business"]

    def wait_phase(self, phases, timeout=60):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            phase = self.business().get("phase")
            if phase in phases:
                return self.business()
            time.sleep(0.2)
        raise AssertionError(f"等待阶段超时：{phases}，当前 {self.business().get('phase')}")

    def run(self):
        self.prepare_bundle()
        self.start_client()

        assert self.business()["project"]["tasks"] == []

        deadline = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=7)).date().isoformat()
        self.remote.fill("goal_input", GOAL)
        self.remote.fill("deadline_input", deadline)

        self.remote.click("生成计划")
        state = self.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        assert state["demoMode"] is True, state.get("demoMode")
        assert [task["id"] for task in state["draftProject"]["tasks"]] == ["demo-1", "demo-2", "demo-3", "demo-4"]
        assert state["plan"]["changes"]
        assert state["plan"]["rationale"], "候选计划缺少安排理由"
        assert state["calendar"], "候选日历为空"
        self.remote.find(text="演示数据")
        self.results["生成"] = {"任务数": 4, "候选变更数": len(state["plan"]["changes"]), "徽标": "演示数据"}

        self.remote.click("确认计划")
        state = self.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["receipt"]["status"] == "verified", state["receipt"]
        assert state["receipt"]["readbackSnapshot"] == state["project"]
        assert state["project"]["version"] == 1
        assert state["plan"] is None
        self.results["确认"] = {"回执": "verified", "版本": 1, "正式任务数": len(state["project"]["tasks"])}

        self.remote.fill("advice_input", REVISE)
        self.remote.click("根据建议修改")
        state = self.wait_phase(["clarify", "failed"])
        assert state["phase"] == "clarify", state
        assert state["question"], "追问为空"
        assert state["workingProject"] is not None
        self.results["修改"] = {"问题": state["question"]}

        self.remote.fill("advice_input", ANSWER)
        self.remote.click("提交回答并继续")
        state = self.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        task_ids = [task["id"] for task in state["draftProject"]["tasks"]]
        assert task_ids == ["demo-0", "demo-1", "demo-2", "demo-3", "demo-4"], task_ids
        assert any(task["title"] == "演示设备检查" for task in state["draftProject"]["tasks"])
        self.results["追问"] = {"回答后任务数": 5, "新增任务": "演示设备检查"}

        self.remote.click("确认修改后的计划")
        state = self.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["receipt"]["status"] == "verified", state["receipt"]
        assert state["project"]["version"] == 2
        assert len(state["project"]["tasks"]) == 5
        self.results["确认修改"] = {"回执": "verified", "版本": 2, "正式任务数": 5}

        # 执行闭环：标记完成 → 重新安排剩余工作 → 确认重排
        self.remote.scroll_to_top()
        self.remote.click_day(next_workday_epoch())
        self.remote.click_first("标记完成")
        state = self.wait_phase(["confirmed"])
        assert state["project"]["version"] == 3, state["project"]["version"]
        demo_zero = [task for task in state["project"]["tasks"] if task["id"] == "demo-0"][0]
        assert demo_zero["done"] is True, demo_zero
        assert demo_zero["remainingHours"] == 0, demo_zero
        self.results["完成标记"] = {"版本": 3, "已完成任务": "demo-0"}

        self.remote.click("重新安排剩余工作")
        state = self.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        assert len(state["draftProject"]["tasks"]) == 5
        demo_zero = [task for task in state["draftProject"]["tasks"] if task["id"] == "demo-0"][0]
        assert demo_zero["done"] is True, demo_zero
        self.results["重排"] = {"任务数": 5, "已完成任务": "demo-0"}

        self.remote.click("确认修改后的计划")
        state = self.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["receipt"]["status"] == "verified", state["receipt"]
        assert state["project"]["version"] == 4, state["project"]["version"]
        demo_zero = [task for task in state["project"]["tasks"] if task["id"] == "demo-0"][0]
        assert demo_zero["done"] is True, demo_zero
        self.results["确认重排"] = {"回执": "verified", "版本": 4}

        self.stop_client()
        self.start_client()
        state = self.business()
        assert state["demoMode"] is True, state.get("demoMode")
        assert state["phase"] == "confirmed"
        assert state["receipt"]["status"] == "verified"
        assert state["project"]["version"] == 4
        assert len(state["project"]["tasks"]) == 5
        demo_zero = [task for task in state["project"]["tasks"] if task["id"] == "demo-0"][0]
        assert demo_zero["done"] is True, demo_zero
        self.remote.find(text="演示数据")
        self.results["重启恢复"] = {"demoMode": True, "正式任务数": 5, "已完成任务": "demo-0", "徽标": "演示数据"}

        (self.run_dir / "results.json").write_text(json.dumps(self.results, ensure_ascii=False, indent=2))
        print(json.dumps(self.results, ensure_ascii=False, indent=2))
        print("演示模式闭环检查通过（生成→确认→核验→保存→月历→修改→追问→标记完成→重排→重启恢复）")

    def stop(self):
        self.stop_client()


if __name__ == "__main__":
    check = DemoCheck()
    try:
        check.run()
    finally:
        check.stop()

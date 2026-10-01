import argparse
import calendar
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx


class DemoCheck:
    def __init__(self, remote: str, state: Path, output: Path):
        self.client = httpx.Client(base_url=remote, timeout=20)
        self.state = state
        self.output = output
        self.records = []

    def snapshot(self):
        response = self.client.get("/snap")
        response.raise_for_status()
        return response.json()["s"]

    def scroll(self, amount):
        self.client.get("/m", params={"k": "scroll", "x": 1000, "y": 700,
                                     "dy": amount, "wait": 1}).raise_for_status()

    def top(self):
        self.scroll(-4000)

    def find(self, identifier=None, text=None):
        for attempt in range(17):
            values = [value for value in self.snapshot()
                      if value["ty"] != "Splash"
                      and (identifier is None or value["i"] == identifier)
                      and (text is None or value.get("t") == text)
                      and 0 <= value["r"][1] < 970]
            if values:
                assert len(values) == 1, values
                return values[0]
            self.scroll(220 if attempt < 8 else -220)
        raise AssertionError((identifier, text))

    def click_value(self, value):
        x, y, width, height = value["r"]
        self.client.get("/click", params={"x": x + width / 2, "y": y + height / 2, "wait": 1}).raise_for_status()

    def click(self, text):
        self.click_value(self.find(text=text))

    def fill(self, identifier, text):
        value = self.find(identifier=identifier)
        self.click_value(value)
        self.client.get("/k", params={"k": "down", "c": "KeyA", "cmd": 1}).raise_for_status()
        self.client.get("/t", params={"t": text, "wait": 1}).raise_for_status()
        assert self.find(identifier=identifier)["val"] == text

    def saved(self):
        records = [json.loads(path.read_text()) for path in self.state.rglob("calendar-*.json")]
        assert records
        record = max(records, key=lambda value: value["sequence"])
        assert record["payload"] == record["mirror"]
        return json.loads(record["payload"])

    def wait(self):
        until = time.monotonic() + 650
        while time.monotonic() < until:
            state = self.saved()
            if state["phase"] not in ("generating", "revising", "verifying"):
                print(state["phase"], state["error"], flush=True)
                assert state["phase"] in ("candidate", "confirmed"), state
                return state
            time.sleep(1)
        raise AssertionError("演示流程超过等待时间")

    def record(self, step):
        state = self.saved()
        self.records.append({"step": step, "sequence": state["sequence"], "phase": state["phase"],
                             "project": state["project"], "draftProject": state["draftProject"],
                             "plan": state["plan"], "receipt": state["receipt"],
                             "modelCalls": state["agent"]["llm_calls"] if state["agent"] else 0,
                             "usage": state["agent"]["usage"] if state["agent"] else None})
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(self.records, ensure_ascii=False, indent=2))

    def approve(self):
        before = self.saved()
        assert before["plan"] is not None
        assert before["plan"]["baseVersion"] == before["project"]["version"]
        self.click("确认修改后的计划" if before["project"]["tasks"] else "确认计划")
        state = self.wait()
        assert state["receipt"]["status"] == "verified"
        assert state["project"]["version"] == before["project"]["version"] + 1
        assert state["plan"] is None
        assert state["receipt"]["readbackSnapshot"] == state["project"]

    def check_month(self, year, month):
        self.top()
        current = datetime.utcfromtimestamp(self.saved()["month"])
        distance = (year - current.year) * 12 + month - current.month
        for _ in range(abs(distance)):
            self.click("下个月" if distance > 0 else "上个月")
        assert self.find(identifier="month_label")["t"] == f"{year}年 {month}月"
        values = self.snapshot()
        dates_by_cell = {}
        for _ in range(2):
            snapshot = self.snapshot()
            grid = next(value for value in snapshot if value["i"] == "calendar_grid")
            for value in snapshot:
                if value["i"] == "date_number":
                    row = int((value["r"][1] - grid["r"][1]) // 120)
                    column = int((value["r"][0] - grid["r"][0]) // 144)
                    dates_by_cell[row * 7 + column] = value
            self.scroll(500)
        self.top()
        dates = [dates_by_cell[index] for index in sorted(dates_by_cell)]
        expected = [day for week in calendar.Calendar().monthdatescalendar(year, month) for day in week]
        assert [value["t"] for value in dates] == [f"{day.day:02}" for day in expected], (dates, expected)
        columns = sorted({round(value["r"][0], 1) for value in dates})
        assert len(columns) == 7
        assert all(abs(columns[index + 1] - columns[index] - 144) < 1 for index in range(6))
        assert any(value["i"] == "plan_summary" and value["r"][0] == 1072 for value in values)
        return {"year": year, "month": month, "rows": len(dates) // 7, "days": len(expected)}

    def check_dates(self):
        results = [self.check_month(year, month) for year, month in
                   [(2026, 11), (2026, 12), (2027, 1), (2027, 2), (2028, 2)]]
        self.click("今天")
        self.records.append({"step": "真实月历日期与七列布局", "months": results})
        self.fill("goal_input", "完成阅读记录应用的演示准备：检查新增记录和列表、本地保存、编写讲解说明，每项约半小时至一小时。")
        for invalid in ("2027-02-29", "2026-13-01", "2026-10-00"):
            self.fill("deadline_input", invalid)
            self.click("生成计划")
            assert "有效的截止日期" in self.find(identifier="status_label")["t"]
            assert self.saved()["activeJob"] is None
        self.fill("deadline_input", (datetime.now().astimezone() + timedelta(days=7)).date().isoformat())

    def run(self):
        assert self.saved()["project"]["tasks"] == []
        self.check_dates()
        self.click("生成计划")
        state = self.wait()
        assert state["project"]["tasks"] == []
        assert state["draftProject"]["tasks"]
        assert state["plan"]["changes"]
        assert state["agent"]["llm_calls"] > 0
        self.check_daily_details()
        self.record("真实模型拆分目标并生成候选月历")
        self.approve()
        self.record("确认计划并核验本地保存结果")
        self.revise()

    def revise(self):
        original = self.saved()["project"]
        self.fill("advice_input", "请新增一个独立任务“演示设备检查”，工时0.5小时，安排在所有其他任务之前，原有任务标题与工时保持。")
        self.click("根据建议修改")
        state = self.wait()
        assert state["project"] == original
        assert any(task["title"] == "演示设备检查" for task in state["draftProject"]["tasks"])
        assert len(state["draftProject"]["tasks"]) == len(original["tasks"]) + 1
        self.top()
        self.click("查看已确认计划")
        assert self.saved()["showingFormal"]
        self.click("查看候选计划")
        assert not self.saved()["showingFormal"]
        self.record("文字建议重构任务并保留正式计划")
        self.check_logs()
        print("候选与正式计划等待重新启动恢复验证", flush=True)

    def check_logs(self):
        log = self.client.get("/log", params={"n": 300}).json()
        assert not any("[E]" in line for line in log["l"]), log

    def check_daily_details(self):
        state = self.saved()
        changes = [item["after"] for item in state["plan"]["changes"] if item["after"]]
        first_day = min(item["start"] for item in changes).split("T")[0]
        day = datetime.fromisoformat(first_day).day
        self.top()
        snapshot = self.snapshot()
        grid = next(item for item in snapshot if item["i"] == "calendar_grid")
        first = datetime.fromisoformat(first_day).replace(day=1)
        cell = first.weekday() + day - 1
        matches = [item for item in snapshot if item["i"] == "date_number"
                   and int((item["r"][1] - grid["r"][1]) // 120) * 7
                   + int((item["r"][0] - grid["r"][0]) // 144) == cell]
        assert len(matches) == 1
        self.click_value(matches[0])
        self.scroll(500)
        visible = [item.get("t", "") for item in self.snapshot() if item["ty"] == "Label"]
        on_day = [item for item in changes if item["start"].split("T")[0] == first_day]
        assert any(text.startswith(f"{len(on_day)} 项安排") for text in visible), visible
        tasks = {item["id"]: item for item in state["draftProject"]["tasks"]}
        assert all(tasks[item["taskId"]]["title"] in visible for item in on_day)
        if len(on_day) > 2:
            assert f"还有 {len(on_day) - 2} 项安排" in visible
        self.top()

    def confirmation_failure(self):
        self.records = json.loads(self.output.read_text())
        before = self.saved()
        previous = self.records[-1]
        assert before["project"] == previous["project"]
        assert before["draftProject"] == previous["draftProject"]
        assert before["plan"] == previous["plan"]
        assert "恢复候选计划" in self.find(identifier="status_label")["t"]
        self.record("重新启动后恢复候选与正式日历")
        self.click("确认修改后的计划" if before["project"]["tasks"] else "确认计划")
        until = time.monotonic() + 60
        while self.saved()["phase"] == "verifying" and time.monotonic() < until:
            time.sleep(1)
        state = self.saved()
        assert state["phase"] == "confirm_failed", state
        assert state["project"] == before["project"]
        assert state["plan"] == before["plan"]
        assert state["pendingVerification"]["target"]["tasks"]
        self.find(text="重新确认计划")
        self.record("实际服务连接中断时保留正式日历与候选计划")
        self.check_logs()

    def retry_confirm(self):
        self.records = json.loads(self.output.read_text())
        state = self.saved()
        assert state["pendingVerification"] is not None
        assert "重新确认核验" in self.find(identifier="status_label")["t"]
        self.click("重新确认计划")
        assert self.wait()["receipt"]["status"] == "verified"
        self.record("重新启动后恢复待核验候选并成功确认")
        self.check_logs()

    def restored_candidate(self):
        self.records = json.loads(self.output.read_text())
        state = self.saved()
        last = self.records[-1]
        assert state["project"] == last["project"]
        assert state["draftProject"] == last["draftProject"]
        assert state["plan"] == last["plan"]
        self.record("重新启动后恢复候选与正式日历")
        self.approve()
        self.record("确认修改后的计划并核验")
        self.check_logs()

    def restored(self):
        self.records = json.loads(self.output.read_text())
        state = self.saved()
        assert state["project"] == self.records[-1]["project"]
        assert state["receipt"]["status"] == "verified"
        assert "恢复本地日历" in self.find(identifier="status_label")["t"]
        self.record("重新启动后恢复正式日历与核验回执")
        self.check_logs()
        print("真实客户端与真实模型主流程验证通过", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", default="http://127.0.0.1:8144")
    parser.add_argument("--state", type=Path, default=Path(".scratch/calendar-demo"))
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/calendar-demo.json"))
    parser.add_argument("--phase", choices=["run", "restore-candidate", "restore", "verify-failure", "retry-confirm"], default="run")
    args = parser.parse_args()
    check = DemoCheck(args.remote, args.state, args.output)
    if args.phase == "run":
        check.run()
    elif args.phase == "restore-candidate":
        check.restored_candidate()
    elif args.phase == "verify-failure":
        check.confirmation_failure()
    elif args.phase == "retry-confirm":
        check.retry_confirm()
    else:
        check.restored()

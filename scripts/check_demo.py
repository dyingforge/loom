import argparse
import json
import time
from pathlib import Path

import httpx


class DemoCheck:
    def __init__(self, remote: str, state: Path, output: Path):
        self.client = httpx.Client(base_url=remote, timeout=15)
        self.state = state
        self.output = output
        self.records = []

    def snapshot(self):
        response = self.client.get("/snap")
        response.raise_for_status()
        return response.json()["s"]

    def find(self, identifier=None, text=None):
        for attempt in range(17):
            values = [value for value in self.snapshot()
                      if (identifier is None or value["i"] == identifier)
                      and (text is None or value.get("t") == text)]
            if values:
                assert len(values) == 1, values
                return values[0]
            self.client.get("/m", params={"k": "scroll", "x": 340, "y": 500,
                                           "dy": 280 if attempt < 8 else -280, "wait": 1}).raise_for_status()
        raise AssertionError((identifier, text))

    def click(self, text):
        value = self.find(text=text)
        x, y, width, height = value["r"]
        self.client.get("/click", params={"x": x + width / 2, "y": y + height / 2, "wait": 1}).raise_for_status()

    def fill(self, identifier, text):
        value = self.find(identifier=identifier)
        x, y, width, height = value["r"]
        self.client.get("/click", params={"x": x + width / 2, "y": y + height / 2, "wait": 1}).raise_for_status()
        self.client.get("/k", params={"k": "down", "c": "KeyA", "cmd": 1}).raise_for_status()
        self.client.get("/t", params={"t": text, "wait": 1}).raise_for_status()
        assert self.find(identifier=identifier)["val"] == text

    def saved(self):
        records = [json.loads(path.read_text()) for path in self.state.rglob("snap-*.json")]
        assert records
        record = max(records, key=lambda value: value["sequence"])
        assert record["payload"] == record["mirror"]
        return json.loads(record["payload"])

    def wait(self):
        until = time.monotonic() + 650
        while time.monotonic() < until:
            status = self.find(identifier="status_label")["t"]
            if "正在请求" not in status and "正在核验" not in status:
                print(status, flush=True)
                return status
            time.sleep(1)
        raise AssertionError("演示流程超过等待时间")

    def record(self, step):
        state = self.saved()
        self.records.append({"step": step, "sequence": state["sequence"],
                             "project": state["project"], "receipt": state["receipt"],
                             "modelCalls": state["agent"]["llm_calls"] if state["agent"] else 0,
                             "usage": state["agent"]["usage"] if state["agent"] else None})
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(self.records, ensure_ascii=False, indent=2))

    def approve(self):
        before = self.saved()
        assert before["plan"] is not None
        assert before["plan"]["baseVersion"] == before["project"]["version"]
        self.click("批准当前方案")
        assert "已保存并核验" in self.wait()
        state = self.saved()
        assert state["receipt"]["status"] == "verified"
        assert state["project"]["version"] == before["project"]["version"] + 1
        assert state["plan"] is None

    def run(self):
        self.fill("goal_input", "完成阅读记录应用的初赛演示准备，包括检查新增记录与列表、本地保存验证和讲解说明。")
        self.fill("preferences_input", "请提出上述三个准备事项的任务建议，每项估算0.5至1小时，按工作需要给出依赖。")
        self.click("保存项目")
        assert self.saved()["project"]["tasks"] == []
        self.click("方案")
        self.click("根据目标生成任务建议")
        assert "任务建议已生成" in self.wait()
        state = self.saved()
        assert len(state["proposals"]) == 3
        identifier = state["proposals"][0]["id"]
        title = state["proposals"][0]["title"] + "（初赛准备）"
        self.click("修改建议 " + identifier)
        self.fill("proposal_edit_title", title)
        self.click("保存建议修改")
        assert self.saved()["proposals"][0]["title"] == title
        self.click("确认全部任务建议")
        assert len(self.saved()["project"]["tasks"]) == 3
        self.record("确认真实模型的任务建议")
        self.click("方案")
        self.click("生成排程方案")
        assert "方案已生成" in self.wait()
        self.approve()
        self.record("批准排程并核验实际保存结果")
        self.click("项目")
        self.fill("preferences_input", "任务已经确认，剩余工时由用户更新，以当前快照为准；遵守依赖并尽早完成。")
        self.click("保存项目")
        self.click("任务")
        self.click("编辑 " + identifier)
        previous = self.saved()["project"]["tasks"][0]["remainingHours"]
        self.fill("edit_task_hours", str(previous + 0.5))
        self.click("保存任务与进度")
        assert self.saved()["project"]["tasks"][0]["remainingHours"] == previous + 0.5
        self.click("方案")
        self.click("根据当前进度重新规划")
        assert "方案已生成" in self.wait()
        self.approve()
        self.record("更新剩余工时后重新规划并核验")
        self.click("过程")
        assert any("次模型调用" in value.get("t", "") for value in self.snapshot())
        log = self.client.get("/log", params={"n": 200}).json()
        assert not any("[E]" in line for line in log["l"]), log
        print("主流程通过真实客户端和真实模型验证", flush=True)

    def restored(self):
        state = self.saved()
        records = json.loads(self.output.read_text())
        assert state["project"] == records[-1]["project"]
        assert state["receipt"]["status"] == "verified"
        assert "已恢复本地项目" in self.find(identifier="status_label")["t"]
        self.records = records
        self.record("重新启动后恢复相同项目与核验回执")
        print("重新启动恢复通过", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", default="http://127.0.0.1:8144")
    parser.add_argument("--state", type=Path, default=Path(".scratch/demo-state"))
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/demo.json"))
    parser.add_argument("--phase", choices=["run", "restore"], default="run")
    args = parser.parse_args()
    check = DemoCheck(args.remote, args.state, args.output)
    if args.phase == "run":
        check.run()
    else:
        check.restored()

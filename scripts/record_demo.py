import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_demo import ANSWER, GOAL, REVISE, DemoCheck, next_workday_epoch


class DemoRecorder:
    def __init__(self):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.run_dir = ROOT / ".scratch" / "demo-video" / f"{stamp}-{uuid.uuid4().hex[:6]}"
        self.frames_dir = self.run_dir / "frames"
        self.frames_dir.mkdir(parents=True)
        self.check = DemoCheck()
        self.timeline = []
        self.counter = 0

    def grab(self, caption, hold):
        self.counter += 1
        name = f"f{self.counter:04d}.png"
        response = httpx.get(f"http://127.0.0.1:{self.check.remote_port}/g?raw=1", timeout=60)
        response.raise_for_status()
        (self.frames_dir / name).write_bytes(response.content)
        self.timeline.append({"file": name, "duration": hold, "caption": caption})

    def scene(self, caption, holds):
        for hold in holds:
            self.grab(caption, hold)

    def run(self):
        check = self.check
        check.prepare_bundle()
        check.start_client()
        remote = check.remote

        assert check.business()["project"]["tasks"] == []
        deadline = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=7)).date().isoformat()
        self.scene("Loom 目标日历 — 填写目标与截止日期", [4])

        remote.fill("goal_input", GOAL)
        remote.fill("deadline_input", deadline)
        self.scene("目标与截止日期已填写 · 点击生成计划", [3])

        remote.click("生成计划")
        self.grab("生成计划：宿主模型拆分任务并排程", 2)
        state = check.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        assert state["plan"]["rationale"], "候选计划缺少安排理由"
        self.scene("候选安排 · 理由与风险提示 · 本地核验 C1–C7", [5])

        remote.click("确认计划")
        state = check.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["receipt"]["status"] == "verified", state["receipt"]
        self.scene("确认计划 · 本地核验通过 · 双快照保存", [5])

        remote.fill("advice_input", REVISE)
        self.scene("文字建议：新增「演示设备检查」任务", [3])
        remote.click("根据建议修改")
        state = check.wait_phase(["clarify", "failed"])
        assert state["phase"] == "clarify", state
        assert state["question"], "追问为空"
        self.scene("模型追问：希望安排在上午 09:00 还是下午 14:00？", [4])

        remote.fill("advice_input", ANSWER)
        remote.click("提交回答并继续")
        state = check.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        assert len(state["draftProject"]["tasks"]) == 5, state["draftProject"]["tasks"]
        self.scene("回答后生成新候选 · 5 项任务", [4])

        remote.click("确认修改后的计划")
        state = check.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["project"]["version"] == 2, state["project"]["version"]
        self.scene("确认修改后的计划 · 版本 1 → 2", [3])

        remote.scroll_to_top()
        remote.click_day(next_workday_epoch())
        self.scene("当天安排 · 标记完成", [3])
        remote.click_first("标记完成")
        state = check.wait_phase(["confirmed"])
        assert state["project"]["version"] == 3, state["project"]["version"]
        self.scene("已标记完成 · 剩余工时扣减 · 容量重算", [3])

        remote.click("重新安排剩余工作")
        state = check.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        self.scene("剩余工作一键重排 · 已完成工作保留", [4])

        remote.click("确认修改后的计划")
        state = check.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["project"]["version"] == 4, state["project"]["version"]
        self.scene("确认重排 · 版本 → 4", [3])

        check.stop_client()
        check.start_client()
        state = check.business()
        assert state["phase"] == "confirmed" and state["project"]["version"] == 4, state
        self.scene("重启应用 · 从双快照恢复", [5])
        self.scene("零服务化 · 规划由宿主模型完成 · 数据只保存在本机", [5])

        (self.run_dir / "timeline.json").write_text(
            json.dumps(self.timeline, ensure_ascii=False, indent=2))
        print(json.dumps({"运行目录": str(self.run_dir), "帧数": len(self.timeline)}, ensure_ascii=False))


if __name__ == "__main__":
    recorder = DemoRecorder()
    try:
        recorder.run()
    finally:
        recorder.check.stop_client()

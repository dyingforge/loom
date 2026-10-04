import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "loom-calendar"
PORT = 8155
STATE = ROOT / ".scratch" / "client-state-check"
HOST = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host"
OUTPUT = STATE / "results.json"
CLARIFY_QUESTION = "这次追问由检查脚本写入真实宿主业务记录，用来驱动真实客户端的回答草稿。"


def manifest_id():
    return json.loads((ROOT / "bundle/manifest.json").read_text())["id"]


def database_path():
    return STATE / manifest_id() / "state.sqlite3"


def connect(readonly):
    if readonly:
        return sqlite3.connect(f"file:{database_path()}?mode=ro", uri=True, timeout=10)
    return sqlite3.connect(str(database_path()), timeout=10)


class Remote:
    def __init__(self):
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", timeout=30)

    def snapshot(self):
        response = self.client.get("/snap")
        response.raise_for_status()
        return response.json()["s"]

    def find(self, identifier):
        for _ in range(50):
            for value in self.snapshot():
                if value.get("i") == identifier:
                    return value
            time.sleep(0.2)
        raise AssertionError(f"没有找到控件 {identifier}")

    def value(self, identifier):
        return self.find(identifier)["val"]

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

    def quit(self):
        try:
            self.client.get("/quit", timeout=5)
        except httpx.HTTPError:
            pass


def start_client():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_client.py"), "--host", str(HOST),
         "--state", str(STATE), "--port", str(PORT), "--hidden"],
        check=True,
    )
    return Remote()


def stop_client(remote):
    remote.quit()
    until = time.monotonic() + 30
    while time.monotonic() < until:
        with httpx.Client(timeout=2) as probe:
            try:
                probe.get(f"http://127.0.0.1:{PORT}/snap")
            except httpx.HTTPError:
                time.sleep(0.5)
                return
        time.sleep(0.5)
    raise AssertionError("客户端没有在超时内关闭")


def read_business():
    connection = connect(True)
    try:
        row = connection.execute(
            "SELECT version, business FROM business WHERE project_id = ?", (PROJECT_ID,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None, None
    return row[0], json.loads(row[1])


def read_draft(question_id):
    connection = connect(True)
    try:
        row = connection.execute(
            "SELECT revision, goal, deadline, answer FROM draft WHERE project_id = ? AND question_id = ?",
            (PROJECT_ID, question_id),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else {"revision": row[0], "goal": row[1], "deadline": row[2], "answer": row[3]}


def wait_for_draft(question_id, expect):
    until = time.monotonic() + 30
    while time.monotonic() < until:
        draft = read_draft(question_id)
        if draft is not None and all(draft[key] == value for key, value in expect.items()):
            return draft
        time.sleep(0.2)
    raise AssertionError(f"草稿没有稳定到 {expect}: {read_draft(question_id)}")


def seed_clarify():
    version, record = read_business()
    assert version is not None, "启动后应存在业务记录"
    record["questionId"] = "check-answer-question"
    record["resumeToken"] = "check-answer-question"
    record["question"] = CLARIFY_QUESTION
    record["phase"] = "clarify"
    record["workingProject"] = record["project"]
    if not record["project"].get("goal"):
        record["project"]["goal"] = "完成检查用目标"
    connection = connect(False)
    try:
        connection.execute(
            "UPDATE business SET business = ? WHERE project_id = ?",
            (json.dumps(record, ensure_ascii=False), PROJECT_ID),
        )
        connection.execute(
            "DELETE FROM draft WHERE project_id = ? AND question_id = ?",
            (PROJECT_ID, "check-answer-question"),
        )
        connection.commit()
    finally:
        connection.close()


def check():
    results = {}
    STATE.mkdir(parents=True, exist_ok=True)

    goals = ["完成季度评审", "完成季度评审并整理记录", "完成季度评审、整理记录和发布说明",
             "把季度评审安排进日历", "把季度评审安排进日历并预留检查时间"]
    deadlines = ["2027-01-05", "2027-01-06", "2027-01-07", "2027-01-08", "2027-01-09"]

    remote = start_client()
    try:
        remote.focus("goal_input")
        for goal in goals:
            remote.retype(goal)
        remote.ensure_value("goal_input", goals[-1])
        remote.focus("deadline_input")
        for due in deadlines:
            remote.retype(due)
        remote.ensure_value("deadline_input", deadlines[-1])
        draft = wait_for_draft("initial", {"goal": goals[-1], "deadline": deadlines[-1]})
        assert remote.value("goal_input") == goals[-1], remote.value("goal_input")
        assert remote.value("deadline_input") == deadlines[-1], remote.value("deadline_input")
        version, record = read_business()
        assert version >= 1, version
        assert record["questionId"] == "initial", record["questionId"]
        results["输入草稿"] = {"中文目标": goals[-1], "截止日期": deadlines[-1],
                             "草稿修订号": draft["revision"], "业务版本": version}
        results["业务版本"] = {"version": version, "questionId": record["questionId"]}
    finally:
        stop_client(remote)

    remote = start_client()
    try:
        assert remote.value("goal_input") == goals[-1], remote.value("goal_input")
        assert remote.value("deadline_input") == deadlines[-1], remote.value("deadline_input")
        restored = read_draft("initial")
        assert restored["goal"] == goals[-1] and restored["deadline"] == deadlines[-1], restored
        results["重启恢复"] = {"界面目标": remote.value("goal_input"), "草稿目标": restored["goal"],
                             "界面截止日期": remote.value("deadline_input"), "草稿截止日期": restored["deadline"],
                             "草稿修订号": restored["revision"]}
    finally:
        stop_client(remote)

    seed_clarify()
    answers = ["需要先评审", "需要先评审再整理记录", "需要先评审、整理记录和发布说明",
               "需要在周五前完成评审", "需要在周五前完成评审并预留检查时间"]
    remote = start_client()
    try:
        remote.focus("advice_input")
        for answer in answers:
            remote.retype(answer)
        remote.ensure_value("advice_input", answers[-1])
        draft = wait_for_draft("check-answer-question", {"answer": answers[-1]})
        assert remote.value("advice_input") == answers[-1], remote.value("advice_input")
        results["回答草稿"] = {"中文回答": answers[-1], "草稿修订号": draft["revision"],
                             "问题标识": "check-answer-question"}
    finally:
        stop_client(remote)

    remote = start_client()
    try:
        assert remote.value("advice_input") == answers[-1], remote.value("advice_input")
        restored = read_draft("check-answer-question")
        assert restored["answer"] == answers[-1], restored
        results["回答重启恢复"] = {"界面回答": remote.value("advice_input"), "草稿回答": restored["answer"],
                                 "草稿修订号": restored["revision"]}
        remote.click("提交回答并继续")
        until = time.monotonic() + 30
        after_click = restored
        while time.monotonic() < until:
            after_click = read_draft("check-answer-question")
            if after_click["revision"] > restored["revision"]:
                break
            time.sleep(0.2)
        assert after_click["revision"] > restored["revision"], (restored, after_click)
        assert after_click["answer"] == answers[-1], after_click
        results["回答提交"] = {"中文回答": answers[-1], "提交前修订号": restored["revision"],
                             "提交后修订号": after_click["revision"], "问题标识": "check-answer-question"}
    finally:
        stop_client(remote)

    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("真实客户端状态检查通过")


if __name__ == "__main__":
    check()

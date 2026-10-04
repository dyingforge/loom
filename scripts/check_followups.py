import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ARTIFACTS = ROOT / ".scratch" / "followups-real"
RUN_DIR = ARTIFACTS / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid4().hex[:6])
RUN_DIR.mkdir(parents=True)
(RUN_DIR / "tmp").mkdir()
DB_PATH = RUN_DIR / "service.sqlite3"
LOG_PATH = RUN_DIR / "service.log"
EVIDENCE_PATH = RUN_DIR / "evidence.json"

# 展示字段：服务端只允许把这些回给客户端。
DISPLAY_KEYS = {"type", "draftProject", "payload", "proposed_tasks", "resumeToken", "calendar", "capacity"}
# 服务端内部字段：完整会话、trace、工具结果、执行计数等不得出现在响应里。
INTERNAL_KEYS = {"messages", "trace", "tool_calls", "llm_calls", "tool_results", "state",
                 "usage", "candidate_attempts", "invalid_streak", "tasks_rebuilt",
                 "clarification", "failure_reason", "lastRequest", "activeJob", "agent"}


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_service(port):
    env = dict(os.environ, PORT=str(port), LOOM_USAGE_DB=str(DB_PATH),
               TMPDIR=str(RUN_DIR / "tmp"),
               LOOM_LLM_TIMEOUT=os.environ.get("LOOM_LLM_TIMEOUT", "120"))
    log = LOG_PATH.open("w")
    process = subprocess.Popen([sys.executable, str(ROOT / "scripts/run_dev_server.py")],
                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=300)
    until = time.monotonic() + 60
    while time.monotonic() < until:
        if process.poll() is not None:
            raise SystemExit(LOG_PATH.read_text())
        with socket.socket() as probe:
            ready = probe.connect_ex(("127.0.0.1", port)) == 0
        if ready:
            response = client.get("/healthz")
            if response.status_code == 200:
                return process, client
        time.sleep(0.3)
    raise AssertionError("服务启动超时")


def stop_service(process, client):
    client.close()
    if process.poll() is None:
        process.terminate()
        until = time.monotonic() + 20
        while process.poll() is None and time.monotonic() < until:
            time.sleep(0.2)
        if process.poll() is None:
            process.kill()
            process.wait()


def build_project(now):
    # 目标刻意留下未定日期，要求模型先确认；项目本身完全有效。
    first = (now + timedelta(days=1)).date().isoformat()
    second = (now + timedelta(days=3)).date().isoformat()
    return {
        "id": "followups-real",
        "version": 0,
        "goal": ("我要准备一场产品功能演示，内容包括新增记录、列表和本地保存，每项约半小时。"
                 f"演示日期还没定，可能是 {first} 或 {second}，请先确认日期再安排。"),
        "deadline": (now + timedelta(days=7)).replace(microsecond=0).isoformat(),
        "milestones": [],
        "tasks": [],
        "fixedEvents": [],
        "workHours": {"start": "09:00", "end": "18:00"},
        "restDays": [],
        "preferences": "",
        "autoAdjust": False,
    }


def submit(client, payload, events, label):
    response = client.post("/v1/agent/jobs", json=payload)
    events.append({"step": label + " 入队", "status": response.status_code})
    assert response.status_code == 202, response.text
    job_id = response.json()["jobId"]
    until = time.monotonic() + 300
    while time.monotonic() < until:
        poll = client.get("/v1/agent/jobs/" + job_id)
        assert poll.status_code == 200, poll.text
        data = poll.json()
        if data.get("status") == "complete":
            return data["result"]
        time.sleep(1)
    raise AssertionError(label + " 作业未在 300 秒内完成")


def internal_hits(value, where=""):
    hits = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = where + "/" + str(key)
            if key in INTERNAL_KEYS:
                hits.append(path)
            hits.extend(internal_hits(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(internal_hits(item, where + "[" + str(index) + "]"))
    return hits


def assert_clean(label, result, events):
    keys = set(result.keys())
    events.append({"step": label + " 响应字段", "keys": sorted(keys)})
    assert keys <= DISPLAY_KEYS, label + " 含未声明字段 " + str(sorted(keys - DISPLAY_KEYS))
    hits = internal_hits(result)
    assert not hits, label + " 泄露服务端内部字段 " + str(hits)


def main():
    assert os.environ.get("MINIMAX_API_KEY"), "缺少 MINIMAX_API_KEY，无法进行真实模型验收"
    now = datetime.now().replace(microsecond=0)
    snapshot = build_project(now)
    day = (now + timedelta(days=1)).date().isoformat()
    answer_one = (f"演示日期就定在 {day}。不过那天具体几点开始还没定，可能是上午或下午，"
                  "请先确认演示开始时间再安排准备任务。")
    answer_two = (f"演示在 {day} 下午 14:00 开始，请据此把准备工作安排在这之前的空闲时段。")
    events = [{"step": "配置", "runDir": str(RUN_DIR), "database": str(DB_PATH),
               "now": now.isoformat(), "deadline": snapshot["deadline"], "goal": snapshot["goal"]}]

    port = free_port()
    process, client = start_service(port)
    try:
        events.append({"step": "服务启动", "port": port, "health": client.get("/healthz").json()})

        # 第一轮：compose，真实模型应提出澄清问题。
        first = submit(client, {"snapshot": snapshot, "trigger": "compose", "now": now.isoformat()},
                       events, "compose")
        assert_clean("compose", first, events)
        assert first.get("type") == "clarify", "第一轮预期 clarify，实际 " + json.dumps(first, ensure_ascii=False)
        token_one = first["resumeToken"]
        question_one = first["payload"]["question"]
        assert token_one and question_one, first
        events.append({"step": "第一轮追问", "question": question_one, "resumeToken": token_one})

        # 第一轮 resume：提交真实回答与当前项目，应出现第二次真实追问。
        second = submit(client, {"snapshot": snapshot, "trigger": "resume",
                                 "clarificationAnswer": answer_one, "resumeToken": token_one,
                                 "now": now.isoformat()}, events, "resume 1")
        assert_clean("resume 1", second, events)
        assert second.get("type") == "clarify", "第二轮预期 clarify，实际 " + json.dumps(second, ensure_ascii=False)
        token_two = second["resumeToken"]
        question_two = second["payload"]["question"]
        assert token_two and token_two != token_one and question_two, second
        events.append({"step": "第二轮追问", "question": question_two, "resumeToken": token_two,
                       "sentResumeToken": token_one, "answer": answer_one})

        # 第二轮 resume：继续真实回答，记录最终计划或继续追问。
        final = submit(client, {"snapshot": snapshot, "trigger": "resume",
                                "clarificationAnswer": answer_two, "resumeToken": token_two,
                                "now": now.isoformat()}, events, "resume 2")
        assert_clean("resume 2", final, events)
        events.append({"step": "最终结果", "type": final.get("type"),
                       "payloadKeys": sorted(final.get("payload", {}).keys()),
                       "sentResumeToken": token_two, "answer": answer_two})

        # 同一恢复凭据不能重复消费。
        replay = client.post("/v1/agent/advance", json={
            "snapshot": snapshot, "trigger": "resume", "clarificationAnswer": answer_one,
            "resumeToken": token_one, "now": now.isoformat()})
        replay_body = replay.json()
        assert replay.status_code == 409, replay.text
        assert replay_body["detail"]["code"] == "resume_consumed", replay.text
        events.append({"step": "重复消费", "status": replay.status_code, "code": replay_body["detail"]["code"]})

        # 未知凭据返回 404。
        unknown = client.post("/v1/agent/advance", json={
            "snapshot": snapshot, "trigger": "resume", "clarificationAnswer": "无",
            "resumeToken": "9999999999.unknown", "now": now.isoformat()})
        unknown_body = unknown.json()
        assert unknown.status_code == 404, unknown.text
        assert unknown_body["detail"]["code"] == "resume_unknown", unknown.text
        events.append({"step": "未知凭据", "status": unknown.status_code, "code": unknown_body["detail"]["code"]})

        EVIDENCE_PATH.write_text(json.dumps(events, ensure_ascii=False, indent=2))
        print("真实模型两轮追问通过")
        print("第一轮问题：" + question_one)
        print("第二轮问题：" + question_two)
        print("最终结果类型：" + str(final.get("type")))
        print("证据：" + str(EVIDENCE_PATH))
    finally:
        stop_service(process, client)


if __name__ == "__main__":
    main()

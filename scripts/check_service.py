import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
ARTIFACTS = ROOT / ".scratch" / "service-check" / uuid4().hex
ARTIFACTS.mkdir(parents=True)

PROJECT = {"id": "service-acceptance", "version": 0, "goal": "完成服务检查",
           "workHours": {"start": "09:00", "end": "18:00"}, "tasks": [
               {"id": "a", "title": "准备演示", "priority": 1, "remainingHours": 1}]}
REQUEST = {"snapshot": PROJECT, "trigger": "new", "now": "2026-10-01T08:00:00"}


def start(name, settings):
    environment = dict(os.environ, PORT="8001", LOOM_USAGE_DB=str(ARTIFACTS / (name + ".sqlite3")),
                       TMPDIR=str(ROOT / ".scratch" / "native-temp"))
    environment.update(settings)
    log = (ARTIFACTS / (name + ".log")).open("w")
    process = subprocess.Popen([sys.executable, "scripts/run_dev_server.py"], cwd=ROOT,
                               env=environment, stdout=log, stderr=subprocess.STDOUT)
    client = httpx.Client(base_url="http://127.0.0.1:8001", timeout=90)
    for _ in range(100):
        if process.poll() is not None:
            return process, client
        # 使用端口探测等待真实服务启动。
        import socket
        with socket.socket() as probe:
            ready = probe.connect_ex(("127.0.0.1", 8001)) == 0
        if ready:
            return process, client
        time.sleep(0.1)
    raise RuntimeError("服务启动超过等待时间")


def finish(process, client):
    client.close()
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=90)


def main():
    results = []
    process, client = start("missing-key", {"MINIMAX_API_KEY": ""})
    assert process.poll() is not None
    results.append({"case": "missing-key", "exitCode": process.returncode})
    finish(process, client)
    for name, settings, expected in [
        ("timeout", {"LOOM_LLM_TIMEOUT": "0.001"}, 504),
        ("provider-error", {"MINIMAX_MODEL": "Loom-invalid-model-for-error-check"}, 502),
        ("budgets", {"LOOM_DAILY_COST_LIMIT_CENTS": "0.01", "LOOM_REVIEWER_DAILY_COST_LIMIT_CENTS": "0.01", "LOOM_REVIEWER_TOKEN": "acceptance-only"}, 429),
    ]:
        process, client = start(name, settings)
        response = client.post("/v1/agent/advance", json=REQUEST)
        assert response.status_code == expected, response.text
        results.append({"case": name, "status": response.status_code, "body": response.json()})
        if name == "budgets":
            reviewer = client.post("/v1/agent/advance", json=REQUEST,
                                   headers={"x-loom-reviewer-token": "acceptance-only"})
            assert reviewer.status_code == 429
            results.append({"case": "reviewer-budget", "status": reviewer.status_code, "body": reviewer.json()})
            invalid = client.post("/v1/agent/advance", json={"snapshot": PROJECT})
            assert invalid.status_code == 422
            results.append({"case": "invalid-request", "status": invalid.status_code})
            expired = dict(REQUEST, trigger="resume", clarificationAnswer="继续",
                           resumeToken=f"{int(time.time()) - 1}.expired")
            response = client.post("/v1/agent/advance", json=expired)
            assert response.status_code == 410
            results.append({"case": "expired-resume", "status": response.status_code, "body": response.json()})
        finish(process, client)
    output = ARTIFACTS / "results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(output)
    print("真实服务异常检查通过")


if __name__ == "__main__":
    main()

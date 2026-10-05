import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host"
HUB = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/hub"
CATALOG = ROOT / ".scratch/apphub-research/catalog.json"
SERVICE_PORT = 8010
SERVICE_STATE = ROOT / ".scratch/service"
TMP = ROOT / ".scratch/native-temp"

sys.path.insert(0, str(ROOT / "scripts"))
from check_client_state import Remote, free_port
from check_demo import DemoCheck


def environment():
    env = dict(os.environ, TMPDIR=str(TMP))
    return env


def run(name, args, log_dir):
    path = log_dir / f"{name}.log"
    with path.open("w") as log:
        result = subprocess.run([str(arg) for arg in args], cwd=ROOT, env=environment(),
                                stdout=log, stderr=subprocess.STDOUT)
    assert result.returncode == 0, f"{name} 失败，见 {path}"
    return str(path)


class Service:
    def __init__(self, log_dir):
        self.port = SERVICE_PORT
        self.pid_file = SERVICE_STATE / "server.pid"
        self.log = SERVICE_STATE / "server.log"
        self.log_dir = log_dir

    def health(self):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", self.port)) != 0:
                return False
        return httpx.get(f"http://127.0.0.1:{self.port}/healthz", timeout=5).status_code == 200

    def ensure(self):
        if not self.health():
            self.start()

    def start(self):
        SERVICE_STATE.mkdir(parents=True, exist_ok=True)
        env = environment()
        env["PORT"] = str(self.port)
        env["LOOM_USAGE_DB"] = str(SERVICE_STATE / "loom.sqlite3")
        env["LOOM_DAILY_COST_LIMIT_CENTS"] = "1000"
        env["LOOM_RATE_LIMIT"] = "60"
        log = self.log.open("a")
        process = subprocess.Popen([sys.executable, "scripts/run_dev_server.py"], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
        self.pid_file.write_text(str(process.pid))
        until = time.monotonic() + 60
        while time.monotonic() < until:
            if self.health():
                return
            time.sleep(0.3)
        raise AssertionError("服务启动超时")

    def stop(self):
        if not self.pid_file.exists():
            return
        pid = int(self.pid_file.read_text())
        subprocess.run(["kill", str(pid)], check=True)
        until = time.monotonic() + 30
        while time.monotonic() < until:
            if not self.health():
                return
            time.sleep(0.3)
        raise AssertionError("服务没有停止")


class ClientRunner:
    def __init__(self, data_dir, port):
        self.data_dir = data_dir
        self.port = port

    def start(self, log_dir, name):
        run(name, [sys.executable, "scripts/run_client.py", "--state", str(self.data_dir),
                   "--port", str(self.port), "--hidden"], log_dir)
        return Remote(self.port)

    def stop(self, remote):
        remote.quit()
        until = time.monotonic() + 20
        while time.monotonic() < until:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", self.port)) != 0:
                    return
            time.sleep(0.2)
        raise AssertionError("客户端没有退出")


def storage_step(run_dir):
    log = run("storage", [sys.executable, "scripts/check_storage.py", "--host", HOST], run_dir)
    return {"step": "真实文件存储", "log": str(log)}


def capture_screenshot(remote, path):
    response = remote.client.get("/g", params={"raw": 1}, timeout=30)
    response.raise_for_status()
    path.write_bytes(response.content)
    assert path.stat().st_size > 1000, f"截图内容过小：{path}"
    errors = [value for value in remote.snapshot()
              if value["ty"] != "Splash" and value.get("t") and "失败" in value["t"]]
    assert not errors, errors


def demo_step(run_dir, service):
    data = run_dir / "demo-data"
    port = free_port()
    output = run_dir / "demo.json"
    client = ClientRunner(data, port)
    remote = client.start(run_dir, "demo-run")
    try:
        DemoCheck(f"http://127.0.0.1:{port}", data, output).run()
        capture_screenshot(remote, run_dir / "screenshot.png")
    finally:
        client.stop(remote)

    remote = client.start(run_dir, "demo-failure")
    try:
        service.stop()
        try:
            DemoCheck(f"http://127.0.0.1:{port}", data, output).confirmation_failure()
        finally:
            service.start()
    finally:
        client.stop(remote)

    remote = client.start(run_dir, "demo-retry")
    try:
        DemoCheck(f"http://127.0.0.1:{port}", data, output).retry_confirm()
    finally:
        client.stop(remote)

    remote = client.start(run_dir, "demo-restored")
    try:
        DemoCheck(f"http://127.0.0.1:{port}", data, output).restored()
    finally:
        client.stop(remote)
    return {"step": "真实客户端状态与日历", "evidence": str(output)}


def state_step(run_dir):
    log = run("client-state", [sys.executable, "scripts/check_client_state.py"], run_dir)
    return {"step": "真实客户端草稿与追问", "log": str(log)}


def service_step(run_dir):
    log = run("service", [sys.executable, "scripts/check_service.py"], run_dir)
    return {"step": "真实服务错误与额度", "log": str(log)}


def hub_step(run_dir):
    assert CATALOG.is_file(), f"缺少官方目录：{CATALOG}"
    path = run_dir / "hub-check.log"
    with path.open("w") as log:
        result = subprocess.run([str(HUB), "check", str(ROOT / "bundle"), "--allow-unsigned",
                                 "--catalog", str(CATALOG)], cwd=ROOT, env=environment(),
                                stdout=log, stderr=subprocess.STDOUT, text=True)
    assert result.returncode == 0, f"hub check 失败，见 {path}"
    return {"step": "最终 hub check", "log": str(path)}


def main():
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = ROOT / ".scratch" / "release-check" / f"{stamp}-{uuid4().hex[:6]}"
    run_dir.mkdir(parents=True)
    TMP.mkdir(parents=True, exist_ok=True)
    results = []
    run("build-verify", [sys.executable, "scripts/build_native.py", "--verify"], run_dir)
    results.append({"step": "锁定来源验证", "log": str(run_dir / "build-verify.log")})
    results.append(storage_step(run_dir))
    service = Service(run_dir)
    service.ensure()
    results.append(demo_step(run_dir, service))
    results.append(state_step(run_dir))
    results.append(service_step(run_dir))
    results.append(hub_step(run_dir))
    service.ensure()
    output = run_dir / "results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(output)
    print("发布验收通过")


if __name__ == "__main__":
    main()

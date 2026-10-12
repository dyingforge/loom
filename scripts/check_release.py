import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host"
HUB = ROOT / ".scratch/native/OctoSense-App-Hub/target/release/hub"
TMP = ROOT / ".scratch/native-temp"


def environment():
    return dict(os.environ, TMPDIR=str(TMP))


def run(name, args, log_dir):
    path = log_dir / f"{name}.log"
    with path.open("w") as log:
        result = subprocess.run([str(arg) for arg in args], cwd=ROOT, env=environment(),
                                stdout=log, stderr=subprocess.STDOUT)
    assert result.returncode == 0, f"{name} 失败，见 {path}"
    return {"step": name, "log": str(path)}


def hub_check_step(log_dir):
    path = log_dir / "hub-check.log"
    with path.open("w") as log:
        result = subprocess.run([str(HUB), "check", str(ROOT / "bundle"), "--allow-unsigned"],
                                cwd=ROOT, env=environment(), stdout=log, stderr=subprocess.STDOUT)
    assert result.returncode == 0, f"hub check 失败，见 {path}"
    return {"step": "hub check", "log": str(path)}


def main():
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = ROOT / ".scratch" / "release-check" / f"{stamp}-{uuid4().hex[:6]}"
    run_dir.mkdir(parents=True)
    TMP.mkdir(parents=True, exist_ok=True)
    results = [
        run("build-verify", [sys.executable, "scripts/build_native.py", "--verify"], run_dir),
        run("storage", [sys.executable, "scripts/check_storage.py", "--host", str(HOST)], run_dir),
        run("demo", [sys.executable, "scripts/check_demo.py"], run_dir),
        run("client-state", [sys.executable, "scripts/check_client_state.py"], run_dir),
        run("vectors", [sys.executable, "scripts/check_vectors_client.py"], run_dir),
        hub_check_step(run_dir),
    ]
    output = run_dir / "results.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(output)
    print("发布验收通过（客户端自包含：存储、演示闭环、状态、向量核验、hub check）")


if __name__ == "__main__":
    main()

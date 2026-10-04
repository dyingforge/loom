import argparse
import hashlib
import json
import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def lock_sha256(lock_path: Path) -> str:
    return hashlib.sha256(lock_path.read_bytes()).hexdigest()


def check_native_build(host: Path) -> None:
    """Refuse a host that was not built from the locked native sources.

    ``scripts/build_native.py`` writes ``native-build.json`` next to the
    binaries. An old binary without it, or one whose stamp does not match the
    current lock, must not be mistaken for the fixed client.
    """
    lock_path = ROOT / "native" / "LOCK.json"
    stamp_path = host.parent / "native-build.json"
    build = "python3 scripts/build_native.py"
    if not host.is_file():
        raise SystemExit(f"找不到原生宿主 {host}，请先运行 {build}")
    if not lock_path.is_file() or not stamp_path.is_file():
        raise SystemExit(f"原生宿主没有按锁定来源构建的标记，请先运行 {build}")
    lock = json.loads(lock_path.read_text())
    stamp = json.loads(stamp_path.read_text())
    if stamp.get("lock_sha256") != lock_sha256(lock_path):
        raise SystemExit(f"native/LOCK.json 已变化，请重新运行 {build}")
    expected = {entry["name"]: entry["fix"] for entry in lock["repositories"]}
    if stamp.get("repositories") != expected:
        raise SystemExit(f"原生宿主构建来源与锁定记录不符，请重新运行 {build}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=Path, default=ROOT / ".scratch/native/OctoSense-App-Hub/target/release/card-host")
    parser.add_argument("--state", type=Path, default=ROOT / ".local-state/calendar")
    parser.add_argument("--port", type=int, default=8144)
    parser.add_argument("--size", default="1440x1000")
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()
    check_native_build(args.host.resolve())
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise SystemExit("客户端已经运行，请关闭当前窗口后重新启动")
    manifest = json.loads((ROOT / "bundle/manifest.json").read_text())
    state_directory = args.state.resolve()
    device_directory = state_directory / manifest["id"]
    device_directory.mkdir(parents=True, exist_ok=True)
    local = datetime.now().astimezone()
    timezone_name = Path("/etc/localtime").resolve().as_posix().split("zoneinfo/")[-1]
    (device_directory / "device.json").write_text(json.dumps({
        "utcOffset": local.utcoffset().total_seconds() / 3600, "timezone": timezone_name,
    }))
    temporary = ROOT / ".scratch/native-temp"
    temporary.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TMPDIR=str(temporary), MAKEPAD_REMOTE=str(args.port))
    if args.hidden:
        env["MAKEPAD_HIDE_WINDOWS"] = "1"
    command = [str(args.host.resolve()), "--bundle", str(ROOT / "bundle"),
               "--app-data", str(state_directory), "--allow-unsigned", "--stamp", "--size", args.size]
    log_path = state_directory / "card-host.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=args.host.resolve().parents[2], env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    until = time.monotonic() + 90
    while time.monotonic() < until:
        if process.poll() is not None:
            raise SystemExit(log_path.read_text())
        with socket.socket() as probe:
            ready = probe.connect_ex(("127.0.0.1", args.port)) == 0
        if ready:
            response = httpx.get(f"http://127.0.0.1:{args.port}/snap", timeout=10)
            response.raise_for_status()
            if any(item["i"] == "month_label" for item in response.json()["s"]):
                print(f"Loom 已打开，窗口 {args.size}，数据目录 {state_directory}")
                break
        time.sleep(0.2)
    else:
        process.terminate()
        raise SystemExit("客户端启动超时，详情见 " + str(log_path))

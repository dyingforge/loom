import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_demo import GOAL, DemoCheck


def main():
    check = DemoCheck()
    out_path = ROOT / "bundle" / "screenshots" / "01-main.png"
    try:
        check.prepare_bundle()
        check.start_client()
        remote = check.remote

        assert check.business()["project"]["tasks"] == []
        deadline = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=7)).date().isoformat()
        remote.fill("goal_input", GOAL)
        remote.fill("deadline_input", deadline)
        remote.click("生成计划")
        state = check.wait_phase(["candidate", "failed"])
        assert state["phase"] == "candidate", state
        remote.click("确认计划")
        state = check.wait_phase(["confirmed", "confirm_failed"])
        assert state["phase"] == "confirmed", state
        assert state["receipt"]["status"] == "verified", state["receipt"]

        # 回滚到顶部，让月历与计划摘要完整进入视口
        remote.scroll_to_top()
        response = httpx.get(f"http://127.0.0.1:{check.remote_port}/g?raw=1", timeout=60)
        response.raise_for_status()
        out_path.write_bytes(response.content)
        print(json.dumps({"截图": str(out_path), "字节数": len(response.content)}, ensure_ascii=False))
    finally:
        check.stop_client()


if __name__ == "__main__":
    main()

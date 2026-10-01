"""本地联调入口：独立进程，不进入 server/ 运行时包。

本脚本用脚本替身驱动开发模式 HTTP 服务，仅用于本地手动联调。
测试替身定义仅在这里 import；不进入 server.adapters.http 的运行时路径。
使用：
    PYTHONPATH=. MINIMAX_API_KEY=... python3 scripts/run_dev_server.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import uvicorn  # noqa: E402

# 用 monkey patch 替换 server.adapters.http.LLM 为脚本替身，
# 仅在本联调进程内生效，不影响其他进程。
import server.adapters.http as http_mod  # noqa: E402
from server.tests.stubs import ScriptedLLM  # noqa: E402


_DEV_RESPONSES = [
    {"type": "tool", "name": "analyze", "arguments": {}},
    {"type": "tool", "name": "query_free_slots", "arguments": {
        "start": "2026-10-02T00:00:00",
        "end": "2026-10-08T00:00:00",
    }},
    {"type": "submit", "candidate": {"blocks": [
        {"taskId": "t1", "start": "2026-10-02T09:00:00",
         "end": "2026-10-02T15:00:00"},
        {"taskId": "t2", "start": "2026-10-06T09:00:00",
         "end": "2026-10-06T15:00:00"},
        {"taskId": "t3", "start": "2026-10-07T09:00:00",
         "end": "2026-10-07T13:00:00"},
    ]}},
]


http_mod.LLM = ScriptedLLM(_DEV_RESPONSES)


if __name__ == "__main__":
    uvicorn.run(http_mod.app, host="127.0.0.1",
                port=int(os.environ.get("PORT", "8000")))

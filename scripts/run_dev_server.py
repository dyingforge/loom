"""本地联调入口：用脚本替身驱动开发模式 HTTP 服务。

仅用于 T4 联调；生产模式下 `LOOM_USE_REAL_MODEL=1` 切到真实模型。
按 .scratch/loom-mvp/issues/04-diagnostics-free-slots.md 要求，本入口不在
server/ 包内，不进入 bundle/，删除见 issue 08。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import uvicorn  # noqa: E402

from server.adapters.http import app  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))

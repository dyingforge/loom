"""脚本化 LLM 替身。仅用于 tests/，不得进入运行时包。"""
from __future__ import annotations

from typing import Any


class ScriptedLLM:
    """按调用顺序返回预定义的决策；可循环使用。"""

    def __init__(self, responses: list[dict] | None = None) -> None:
        self._responses = list(responses or [])
        self._idx = 0
        self.calls: int = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.calls += 1
        if not self._responses:
            return {"type": "failed", "reason": "no scripted response"}
        resp = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return resp

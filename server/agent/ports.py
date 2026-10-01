from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    """接收完整对话和工具定义，返回提供方 message 与真实 usage。"""

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        ...

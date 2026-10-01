"""Agent 端口接口：仅描述能力，不依赖具体提供方或 SDK。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    """模型适配器接口。

    实现方负责：
    - 维护内部对话状态；
    - 将工具调用历史与系统提示一并提交；
    - 解析模型最终输出为结构化响应。

    返回值是 dict，包含 type ∈ {"submit","clarify","tool","error"}，及对应字段。
    """

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        ...

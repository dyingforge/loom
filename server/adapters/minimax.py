from __future__ import annotations

import os

import httpx


class MiniMaxLLM:
    def __init__(self, api_key: str, model: str = "MiniMax-M2.7",
                 endpoint: str | None = None, timeout: float = 30.0):
        if not api_key:
            raise ValueError("MINIMAX_API_KEY 未配置")
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or os.environ.get(
            "MINIMAX_CHAT_URL", "https://api.minimax.chat/v1/chat/completions")
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        response = httpx.post(
            self.endpoint,
            headers={"Authorization": "Bearer " + self.api_key},
            json={"model": self.model, "messages": messages,
                  "tools": [{"type": "function", "function": tool} for tool in tools],
                  "tool_choice": "auto", "reasoning_split": True,
                  "max_tokens": 8192, "temperature": 1},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        provider = payload.get("base_resp", {})
        if provider.get("status_code", 0) != 0:
            raise ValueError("MiniMax 返回错误：" + str(provider))
        if payload.get("error"):
            raise ValueError("MiniMax 返回错误：" + str(payload["error"]))
        choice = payload["choices"][0]
        if choice["finish_reason"] == "length":
            raise ValueError("模型输出达到长度限制，无法完成本轮规划")
        return {"message": choice["message"], "usage": payload["usage"]}

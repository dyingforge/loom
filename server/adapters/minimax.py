"""MiniMax 适配器：实现 ports.LLM。

依赖：仅使用标准库 + urllib（避免引入额外 SDK）。运行时配置由调用方注入；
密钥永远不出现在源码或配置文件中。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class MiniMaxLLM:
    def __init__(self, api_key: str,
                 model: str = "MiniMax-M2.7",
                 endpoint: str | None = None,
                 timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or os.environ.get(
            "MINIMAX_CHAT_URL",
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
        )
        self.timeout = timeout

    def _call(self, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _extract_text(payload: dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        return (msg.get("content") or "").strip()

    @staticmethod
    def _parse_decision(text: str, tools: list[dict]) -> dict:
        """尝试从文本解析结构化决策；解析失败则返回 failed 决策。

        工具名集合来自 tools 参数；不接受未列入的工具名。
        """
        s = text.strip()
        if s.startswith("```"):
            lines = s.split("\n")
            s = "\n".join(lines[1:])
            if s.endswith("```"):
                s = s[:-3]
        a = s.find("{")
        b = s.rfind("}")
        if a < 0 or b <= a:
            return {"type": "submit", "candidate": {"blocks": []}}
        try:
            obj = json.loads(s[a:b + 1])
        except json.JSONDecodeError:
            return {"type": "submit", "candidate": {"blocks": []}}
        kind = obj.get("type")
        if kind == "clarify":
            return {"type": "clarify", "question": obj.get("question", "")}
        if kind == "tool":
            name = obj.get("name")
            allowed = {t["name"] for t in tools}
            if name not in allowed:
                return {"type": "failed",
                        "reason": f"unknown tool: {name}"}
            return {"type": "tool", "name": name,
                    "arguments": obj.get("arguments") or {}}
        if kind == "submit":
            return {"type": "submit",
                    "candidate": obj.get("candidate") or {"blocks": []}}
        return {"type": "failed", "reason": "无法识别模型输出结构"}

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            payload = self._call(messages, tools)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            return {"type": "failed", "reason": f"network: {e}"}
        text = self._extract_text(payload)
        return self._parse_decision(text, tools)

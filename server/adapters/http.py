"""HTTP 适配层：FastAPI 暴露路由 + 限流/额度中间件（同文件）。

约束：
- 不依赖 server.domain.models 之外的具体类型；
- agent.loop 不出现在这里；
- minimax 适配器不 import Web 框架。

按设计，本层是唯一的 Web 入口；agent 通过 LLM 协议被调用。
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from server.agent.loop import State, run
from server.domain.models import AgentRequest, Project
from server.runtime.reconcile import verify
from server.tests.stubs import ScriptedLLM  # 仅在未配置真实模型时使用


# ---------- 配置 ----------
class HttpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate_limit_per_minute: int = 60
    daily_cost_limit_cents: int = 1000
    reviewer_token: Optional[str] = None
    use_real_model: bool = False


CONFIG = HttpConfig(
    rate_limit_per_minute=int(os.environ.get("LOOM_RATE_LIMIT", "60")),
    daily_cost_limit_cents=int(os.environ.get("LOOM_DAILY_COST_LIMIT_CENTS", "1000")),
    reviewer_token=os.environ.get("LOOM_REVIEWER_TOKEN"),
    use_real_model=os.environ.get("LOOM_USE_REAL_MODEL", "0") == "1",
)


# ---------- 状态 ----------
class _Usage:
    def __init__(self) -> None:
        self.window: dict[str, deque] = defaultdict(deque)
        self.day_cents: dict[str, float] = defaultdict(float)

    def check(self, ip: str, is_reviewer: bool) -> None:
        if is_reviewer:
            return
        now = time.time()
        bucket = self.window[ip]
        cutoff = now - 60
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= CONFIG.rate_limit_per_minute:
            raise HTTPException(429, "rate limit exceeded")
        bucket.append(now)
        today = time.strftime("%Y-%m-%d")
        if self.day_cents[today] >= CONFIG.daily_cost_limit_cents:
            raise HTTPException(429, "daily cost limit reached")
        self.day_cents[today] += 1.0


USAGE = _Usage()


app = FastAPI(title="Loom Agent", version="0.1.0")


@app.middleware("http")
async def usage_middleware(request: Request, call_next):
    if request.url.path == "/healthz":
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    token = request.headers.get("x-loom-reviewer-token")
    is_reviewer = bool(CONFIG.reviewer_token and token == CONFIG.reviewer_token)
    try:
        USAGE.check(ip, is_reviewer)
    except HTTPException as e:
        return Response(status_code=e.status_code, content=str(e.detail))
    response = await call_next(request)
    return response


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/v1/agent/advance")
async def advance(request: AgentRequest) -> dict:
    llm = _make_llm()
    if request.state is not None:
        state = State.from_dict(request.state)
        state.project = request.snapshot
    else:
        state = State(project=request.snapshot)
    state = run(state, llm)
    if state.status == "submitted":
        return {
            "type": "plan",
            "payload": state.plan.model_dump(mode="json") if state.plan else {},
            "trace": state.trace,
            "state": state.to_dict(),
        }
    if state.status == "clarified":
        return {
            "type": "clarify",
            "payload": {"question": state.clarification or ""},
            "trace": state.trace,
            "state": state.to_dict(),
        }
    return {
        "type": "failed",
        "payload": {"reason": state.failure_reason or "unknown"},
        "trace": state.trace,
        "state": state.to_dict(),
    }


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: dict
    versionBefore: int
    versionAfter: int
    readbackSnapshot: dict


@app.post("/v1/agent/verify")
async def verify_route(request: VerifyRequest) -> dict:
    project = Project.model_validate(request.readbackSnapshot)
    receipt = verify(
        request.plan, request.versionBefore,
        request.versionAfter, project,
    )
    return receipt.model_dump(mode="json")


def _make_llm() -> Any:
    if CONFIG.use_real_model:
        from server.adapters.minimax import MiniMaxLLM
        return MiniMaxLLM(
            api_key=os.environ["MINIMAX_API_KEY"],
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
        )
    return ScriptedLLM(_dev_responses())


def _dev_responses() -> list:
    return [
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

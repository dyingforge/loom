"""HTTP 适配层：FastAPI 暴露路由 + 限流/额度中间件。

约束：
- 不依赖 server.domain.models 之外的具体类型；
- agent.loop 不出现在这里；
- minimax 适配器不 import Web 框架；
- 默认无 LLM：必须在启动时通过环境变量选择真实模型；缺凭据时启动失败。
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from server.agent.loop import State, run
from server.domain.models import AgentRequest, Project
from server.runtime.reconcile import verify


# ---------- 日志 ----------
LOG = logging.getLogger("loom")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


# ---------- 配置 ----------
class HttpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate_limit_per_minute: int = 60
    daily_cost_limit_cents: int = 1000
    reviewer_token: Optional[str] = None


def _build_config() -> HttpConfig:
    return HttpConfig(
        rate_limit_per_minute=int(os.environ.get("LOOM_RATE_LIMIT", "60")),
        daily_cost_limit_cents=int(
            os.environ.get("LOOM_DAILY_COST_LIMIT_CENTS", "1000")),
        reviewer_token=os.environ.get("LOOM_REVIEWER_TOKEN"),
    )


CONFIG = _build_config()


# ---------- 状态 ----------
class _Usage:
    def __init__(self) -> None:
        self.window: dict[str, deque] = defaultdict(deque)
        self.day_cents: dict[str, float] = defaultdict(float)
        self.request_ids: dict[str, str] = {}

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


def _build_llm() -> Any:
    """启动时构造真实 LLM；缺凭据立即失败。"""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MINIMAX_API_KEY missing；服务端不接受缺凭据启动（issue 08）。"
        )
    from server.adapters.minimax import MiniMaxLLM
    return MiniMaxLLM(
        api_key=api_key,
        model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
        timeout=float(os.environ.get("LOOM_LLM_TIMEOUT", "30")),
    )


LLM: Any = None  # 在每个路由懒构造，避免测试时启动即失败


def _get_llm() -> Any:
    global LLM
    if LLM is None:
        LLM = _build_llm()
    return LLM


@app.middleware("http")
async def usage_middleware(request: Request, call_next):
    rid = str(uuid.uuid4())
    request.state.request_id = rid
    if request.url.path == "/healthz":
        return await call_next(request)
    ip = request.client.host if request.client else "unknown"
    token = request.headers.get("x-loom-reviewer-token")
    is_reviewer = bool(CONFIG.reviewer_token and token == CONFIG.reviewer_token)
    try:
        USAGE.check(ip, is_reviewer)
    except HTTPException as e:
        LOG.warning("rid=%s ip=%s status=%s reason=%s",
                    rid, ip, e.status_code, e.detail)
        return Response(status_code=e.status_code, content=str(e.detail))
    try:
        t0 = time.time()
        response = await call_next(request)
    except Exception as e:
        LOG.exception("rid=%s ip=%s error=%s", rid, ip, e)
        return Response(status_code=500, content="internal error")
    elapsed_ms = int((time.time() - t0) * 1000)
    LOG.info("rid=%s ip=%s method=%s path=%s status=%s elapsed_ms=%s",
             rid, ip, request.method, request.url.path,
             response.status_code, elapsed_ms)
    return response


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/v1/agent/advance")
async def advance(request: AgentRequest) -> dict:
    if request.state is not None:
        state = State.from_dict(request.state)
        state.project = request.snapshot
    else:
        state = State(project=request.snapshot)
    state = run(state, _get_llm())
    # 从 trace 中提取 propose_tasks 的 proposed 结果，供 issue 11 客户端使用
    proposed_tasks = []
    for msg in state.messages:
        if msg.get("role") == "tool" and msg.get("name") == "propose_tasks":
            res = msg.get("result") or {}
            if isinstance(res, dict) and "proposed" in res:
                proposed_tasks = res["proposed"]
                break
    if state.status == "submitted":
        return {
            "type": "plan",
            "payload": state.plan.model_dump(mode="json") if state.plan else {},
            "trace": state.trace,
            "proposed_tasks": proposed_tasks,
            "state": state.to_dict(),
        }
    if state.status == "clarified":
        return {
            "type": "clarify",
            "payload": {"question": state.clarification or ""},
            "trace": state.trace,
            "proposed_tasks": proposed_tasks,
            "state": state.to_dict(),
        }
    return {
        "type": "failed",
        "payload": {"reason": state.failure_reason or "unknown"},
        "trace": state.trace,
        "proposed_tasks": proposed_tasks,
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

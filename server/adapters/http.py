from __future__ import annotations

import logging
import asyncio
import json
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict

from server.agent.loop import State, run
from server.domain.models import AgentRequest, Plan, Project
from server.domain.capacity import capacity
from server.runtime.reconcile import verify, verify_calendar
from server.adapters.minimax import MiniMaxLLM
from server.adapters.usage import MeteredLLM, UsageLedger


# ---------- 日志 ----------
LOG = logging.getLogger("loom")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.llm = MiniMaxLLM(api_key=os.environ.get("MINIMAX_API_KEY", ""),
                             model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
                             timeout=float(os.environ.get("LOOM_LLM_TIMEOUT", "60")))
    app.state.ledger = UsageLedger(
        Path(os.environ.get("LOOM_USAGE_DB", ".local-state/service.sqlite3")),
        float(os.environ.get("LOOM_DAILY_COST_LIMIT_CENTS", "1000")),
        float(os.environ.get("LOOM_REVIEWER_DAILY_COST_LIMIT_CENTS", "1000")),
        float(os.environ.get("LOOM_INPUT_CENTS_PER_MILLION", "37.5")),
        float(os.environ.get("LOOM_OUTPUT_CENTS_PER_MILLION", "120")),
        int(os.environ.get("LOOM_RATE_LIMIT", "60")))
    app.state.jobs = {}
    app.state.jobs_lock = Lock()
    app.state.pool = ThreadPoolExecutor(max_workers=4)
    yield
    app.state.pool.shutdown(wait=True)


app = FastAPI(title="Loom Agent", version="0.1.0", lifespan=lifespan)


@app.exception_handler(httpx.TimeoutException)
async def provider_timeout(request: Request, error):
    return JSONResponse(status_code=504, content={"detail": "模型调用超时，本轮已停止，请重新发起"})


@app.exception_handler(httpx.HTTPError)
async def provider_http_error(request: Request, error):
    LOG.error("提供方请求失败：%s", type(error).__name__)
    return JSONResponse(status_code=502, content={"detail": "模型提供方拒绝请求或网络连接失败，本轮已停止"})


@app.exception_handler(ValueError)
async def invalid_result(request: Request, error):
    return JSONResponse(status_code=502, content={"detail": str(error)})


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/privacy", response_class=PlainTextResponse)
async def privacy() -> str:
    return (Path(__file__).resolve().parents[2] / "docs/PRIVACY.md").read_text(encoding="utf-8")


@app.post("/v1/agent/jobs", status_code=202)
def start_job(request: AgentRequest, connection: Request) -> dict:
    jobs = connection.app.state.jobs
    with connection.app.state.jobs_lock:
        expired = [key for key, value in jobs.items() if value[0] < time.time() - 3600 and value[1].done()]
        for key in expired:
            del jobs[key]
        if sum(not value[1].done() for value in jobs.values()) >= 4:
            raise HTTPException(429, "服务正在处理四项规划，请稍后重新发起")
        identifier = uuid4().hex
        progress = {"stage": "正在拆分目标" if request.trigger == "compose" else "正在根据建议规划"}
        jobs[identifier] = (time.time(), connection.app.state.pool.submit(_advance, request, connection, progress), progress)
    return {"jobId": identifier}


@app.get("/v1/agent/jobs/{identifier}")
async def job_result(identifier: str, connection: Request) -> dict:
    job = connection.app.state.jobs.get(identifier)
    if job is None:
        raise HTTPException(410, "规划过程已过期或服务已经重启，请重新发起")
    future = job[1]
    until = time.monotonic() + 15
    while not future.done() and time.monotonic() < until:
        await asyncio.sleep(0.1)
    if not future.done():
        return {"status": "running", "stage": job[2]["stage"]}
    return {"status": "complete", "result": future.result()}


@app.post("/v1/agent/advance")
def advance(request: AgentRequest, connection: Request) -> dict:
    return _advance(request, connection, None)


def _advance(request: AgentRequest, connection: Request, progress: dict | None) -> dict:
    ledger = connection.app.state.ledger
    ledger.check_rate(connection.client.host if connection.client else "unknown")
    expected_token = os.environ.get("LOOM_REVIEWER_TOKEN", "")
    token = connection.headers.get("x-loom-reviewer-token", "")
    bucket = "reviewer" if expected_token and secrets.compare_digest(token, expected_token) else "public"
    if request.state is not None:
        if not request.state.get("resumeToken"):
            raise HTTPException(409, "暂停状态缺少恢复凭据，请重新发起规划")
        if request.trigger != "resume" or not request.clarificationAnswer:
            raise HTTPException(409, "恢复需要用户回答")
        state = State.from_dict(ledger.resume(request.state["resumeToken"]))
        if state.project.id != request.snapshot.id:
            raise HTTPException(409, "恢复请求属于不同项目")
        changed = state.project.model_dump() != request.snapshot.model_dump()
        if changed:
            state.trace.append({"type": "context_update", "fromVersion": state.project.version,
                                "toVersion": request.snapshot.version})
            state.messages.append({"role": "user", "content": "用户更新了项目，旧候选失效。完整当前项目：" +
                                   request.snapshot.model_dump_json()})
            state.plan = None
        state.project = request.snapshot
        if state.status != "clarified" or request.trigger != "resume" or not request.clarificationAnswer:
            raise HTTPException(409, "恢复需要有效暂停状态与用户回答")
        state.status = "running"
        state.now = request.now
        state.messages.append({"role": "user", "content": json.dumps({
            "answer": request.clarificationAnswer, "now": request.now.isoformat()}, ensure_ascii=False)})
    else:
        if request.trigger == "resume":
            raise HTTPException(409, "没有可恢复的暂停状态")
        state = State(project=request.snapshot, now=request.now, trigger=request.trigger,
                      instruction=request.instruction)
    def update_stage(stage):
        if progress is not None:
            progress["stage"] = stage

    state = run(state, MeteredLLM(connection.app.state.llm, ledger, bucket), progress=update_stage)
    response_state = state.to_dict()
    if state.status == "clarified":
        response_state["resumeToken"] = ledger.pause(response_state)
    proposed_tasks = state.proposed_tasks
    if state.status == "submitted":
        return {
            "type": "plan",
            "draftProject": state.project.model_dump(mode="json"),
            "payload": state.plan.model_dump(mode="json") if state.plan else {},
            "trace": state.trace,
            "proposed_tasks": proposed_tasks,
            "state": response_state,
            "calendar": calendar_metadata(state),
            "capacity": capacity(state.project, state.now),
        }
    if state.status == "proposed":
        return {"type": "tasks", "payload": {"tasks": proposed_tasks},
                "trace": state.trace, "state": response_state,
                "capacity": capacity(state.project, state.now)}
    if state.status == "clarified":
        return {
            "type": "clarify",
            "draftProject": state.project.model_dump(mode="json"),
            "payload": {"question": state.clarification or ""},
            "trace": state.trace,
            "proposed_tasks": proposed_tasks,
            "state": response_state,
            "capacity": capacity(state.project, state.now),
        }
    return {
        "type": "failed",
        "payload": {"reason": state.failure_reason or "unknown"},
        "trace": state.trace,
        "proposed_tasks": proposed_tasks,
        "state": response_state,
        "capacity": capacity(state.project, state.now),
    }


def calendar_metadata(state: State) -> dict:
    moments = {state.now.isoformat(): state.now}
    if state.project.deadline:
        moments[state.project.deadline.isoformat()] = state.project.deadline
    for task in state.project.tasks:
        for block in task.blocks:
            moments[block.start.isoformat()] = block.start
            moments[block.end.isoformat()] = block.end
    for event in state.project.fixedEvents:
        moments[event.start.isoformat()] = event.start
        moments[event.end.isoformat()] = event.end
    if state.plan:
        for change in state.plan.changes:
            for block in (change.before, change.after):
                if block:
                    moments[block.start.isoformat()] = block.start
                    moments[block.end.isoformat()] = block.end
    epoch = datetime(1970, 1, 1)
    return {text: (moment - epoch).total_seconds() for text, moment in moments.items()}


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: dict
    versionBefore: int
    versionAfter: int
    readbackSnapshot: dict
    beforeSnapshot: Project


@app.post("/v1/agent/verify")
async def verify_route(request: VerifyRequest) -> dict:
    project = Project.model_validate(request.readbackSnapshot)
    receipt = verify(
        request.plan, request.versionBefore,
        request.versionAfter, project, request.beforeSnapshot,
    )
    return receipt.model_dump(mode="json")


class CalendarVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beforeSnapshot: Project
    draftProject: Project
    plan: Plan
    readbackSnapshot: Project
    now: datetime


@app.post("/v1/calendar/verify")
async def calendar_verify_route(request: CalendarVerifyRequest) -> dict:
    if request.now.tzinfo is not None:
        raise ValueError("核验时间必须使用设备当地时间")
    return verify_calendar(request.beforeSnapshot, request.draftProject, request.plan,
                           request.readbackSnapshot, request.now).model_dump(mode="json")

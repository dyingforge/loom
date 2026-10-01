"""Agent 主循环：纯状态转移。

`step(state, llm) -> state'`。模型负责选工具或提交候选；循环负责校验参数、
执行工具、最终校验、生 Plan、计数与停止条件。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from server.agent.limits import (
    LLM_CALL_TIMEOUT_SECONDS,
    MAX_INVALID_PARAMS_STREAK,
    MAX_LLM_CALLS_PER_ROUND,
    MAX_VALIDATIONS_PER_CANDIDATE,
)
from server.agent.tools import SCHEMAS, dispatch
from server.domain.constraints import validate
from server.domain.models import (
    Candidate, Change, Plan, Project, Violation,
)
from server.domain.scheduling import diff


# ---------- 状态结构 ----------
@dataclass
class State:
    project: Project
    messages: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    invalid_streak: int = 0
    candidate_attempts: dict[str, int] = field(default_factory=dict)
    status: str = "running"  # running | submitted | clarified | stopped | failed
    plan: Plan | None = None
    clarification: str | None = None
    failure_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "project": self.project.model_dump(mode="json"),
            "messages": self.messages,
            "trace": self.trace,
            "llm_calls": self.llm_calls,
            "invalid_streak": self.invalid_streak,
            "candidate_attempts": self.candidate_attempts,
            "status": self.status,
            "plan": self.plan.model_dump(mode="json") if self.plan else None,
            "clarification": self.clarification,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        return cls(
            project=Project.model_validate(d["project"]),
            messages=list(d.get("messages") or []),
            trace=list(d.get("trace") or []),
            llm_calls=int(d.get("llm_calls", 0)),
            invalid_streak=int(d.get("invalid_streak", 0)),
            candidate_attempts=dict(d.get("candidate_attempts") or {}),
            status=d.get("status", "running"),
            plan=Plan.model_validate(d["plan"]) if d.get("plan") else None,
            clarification=d.get("clarification"),
            failure_reason=d.get("failure_reason"),
        )


# ---------- 工具消息辅助 ----------
def _tool_msg(name: str, args: dict, result: dict | None = None,
              error: str | None = None) -> dict:
    return {
        "role": "tool",
        "name": name,
        "arguments": args,
        "result": result,
        "error": error,
    }


def _assistant_msg(step: dict) -> dict:
    return {"role": "assistant", "step": step}


# ---------- 主循环 ----------
def _stop(state: State, reason: str) -> State:
    state.status = "stopped"
    state.failure_reason = reason
    state.trace.append({"type": "stop", "reason": reason})
    return state


def step(state: State, llm: Any) -> State:
    if state.status != "running":
        return state
    if state.llm_calls >= MAX_LLM_CALLS_PER_ROUND:
        return _stop(state, "达到每轮模型调用上限")

    state.llm_calls += 1
    decision = llm.chat(state.messages, SCHEMAS)
    state.messages.append(_assistant_msg(decision))

    kind = decision.get("type")
    trace_entry = {"type": "decision", "kind": kind}
    state.trace.append(trace_entry)

    if kind == "clarify":
        state.status = "clarified"
        state.clarification = decision.get("question") or ""
        state.trace.append({"type": "clarify", "question": state.clarification})
        return state

    if kind == "failed":
        state.status = "failed"
        state.failure_reason = decision.get("reason") or "模型声明失败"
        state.trace.append({"type": "failed", "reason": state.failure_reason})
        return state

    if kind == "tool":
        name = decision.get("name")
        args = decision.get("arguments", {})
        try:
            result = dispatch(state.project, name, args)
            state.invalid_streak = 0
            state.messages.append(_tool_msg(name, args, result=result))
            state.trace.append({"type": "tool_call", "name": name,
                                "args": args, "ok": True})
        except (ValueError, TypeError, KeyError) as e:
            state.invalid_streak += 1
            state.messages.append(_tool_msg(name, args, error=str(e)))
            state.trace.append({"type": "tool_call", "name": name,
                                "args": args, "ok": False,
                                "error": str(e)})
            if state.invalid_streak >= MAX_INVALID_PARAMS_STREAK:
                return _stop(state, "同类无效参数连续出现，停止")
        return state

    if kind == "submit":
        cand_raw = decision.get("candidate")
        sig = _candidate_signature(cand_raw)
        state.candidate_attempts[sig] = state.candidate_attempts.get(sig, 0) + 1
        attempts = state.candidate_attempts[sig]
        if attempts > MAX_VALIDATIONS_PER_CANDIDATE:
            return _stop(state, "同一候选校验超过上限")
        # 循环自己再次校验（不信任模型试校验）
        try:
            cand = Candidate.model_validate({"blocks": cand_raw.get("blocks") or []})
        except Exception as e:
            state.invalid_streak += 1
            state.messages.append({"role": "user",
                                   "content": f"候选格式非法: {e}"})
            if state.invalid_streak >= MAX_INVALID_PARAMS_STREAK:
                return _stop(state, "非法候选连续出现，停止")
            return state
        if len(cand.blocks) == 0:
            state.invalid_streak += 1
            state.messages.append({
                "role": "user",
                "content": "候选为空。请至少提交一个时间块。",
            })
            state.trace.append({"type": "empty_candidate"})
            if state.invalid_streak >= MAX_INVALID_PARAMS_STREAK:
                return _stop(state, "候选连续为空，停止")
            return state
        violations = validate(state.project, cand)
        state.trace.append({"type": "validation", "attempt": attempts,
                            "violations": [v.model_dump() for v in violations]})
        if violations:
            state.messages.append({
                "role": "user",
                "content": "校验器反馈违规: " +
                           str([v.model_dump() for v in violations]) +
                           "。请基于这些具体违规修正后再提交。",
            })
            return state
        # 通过：生成 Plan
        plan = diff(state.project, cand)
        state.plan = plan
        state.status = "submitted"
        state.trace.append({"type": "submit_ok", "planId": plan.planId,
                            "changes": len(plan.changes)})
        return state

    # 未知类型
    state.invalid_streak += 1
    state.trace.append({"type": "invalid_decision", "decision": decision})
    if state.invalid_streak >= MAX_INVALID_PARAMS_STREAK:
        return _stop(state, "模型输出结构无法识别")
    return state


def run(state: State, llm: Any, max_steps: int = 32) -> State:
    """连续 step 直至状态非 running。"""
    for _ in range(max_steps):
        if state.status != "running":
            break
        step(state, llm)
    return state


def _candidate_signature(cand_raw: dict | None) -> str:
    if not cand_raw or "blocks" not in cand_raw:
        return "empty"
    sig = []
    for b in cand_raw["blocks"]:
        sig.append((b.get("taskId"), b.get("start"), b.get("end"), b.get("id")))
    return repr(sorted(sig))

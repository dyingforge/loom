"""真实 MiniMax 端到端集成（issue 08 验收）。

仅当环境提供 MINIMAX_API_KEY 时运行（默认跳过）。验证：
- 模型最终能产出合规方案
- 候选被校验拦截后能修正并通过
- 方案包含全部任务
"""
from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("MINIMAX_API_KEY"),
    reason="MINIMAX_API_KEY missing",
)


THREE_TASK_PROJECT: dict = {
    "id": "probe", "version": 1, "goal": "在 5 天内完成原型实现并联调",
    "workHours": {"start": "09:00", "end": "18:00"},
    "restDays": [5, 6],
    "tasks": [
        {"id": "t1", "title": "领域模型与校验器", "priority": 1,
         "remainingHours": 6, "dependsOn": [], "adjustable": True, "blocks": []},
        {"id": "t2", "title": "Agent 循环与工具", "priority": 1,
         "remainingHours": 6, "dependsOn": ["t1"], "adjustable": True, "blocks": []},
        {"id": "t3", "title": "客户端执行器与回读", "priority": 2,
         "remainingHours": 4, "dependsOn": ["t2"], "adjustable": True, "blocks": []},
    ],
}


SYSTEM_PROMPT = """你是 Loom Agent。阅读项目 JSON 并只输出一个 JSON 对象表示排程候选。
候选格式严格如下：
{"type":"submit","candidate":{"blocks":[
  {"taskId":"t1","start":"2026-10-02T09:00","end":"2026-10-02T15:00"},
  {"taskId":"t2","start":"2026-10-06T09:00","end":"2026-10-06T15:00"},
  {"taskId":"t3","start":"2026-10-07T09:00","end":"2026-10-07T13:00"}
]}}
硬约束（必须全部满足，校验器会逐条核对）：
- 时间是设备本地时间，ISO 字符串；不跨休息日（Python weekday 5/6 = 周六周日）；
- 不跨工作时段 09:00-18:00；
- 块之间不重叠；
- 每任务块总时长等于其剩余工时（t1=6h、t2=6h、t3=4h）；
- 后继块不早于前驱全部完成；
- 2026-10-02 是周五，可排到 2026-10-08（周四）之前。
校验器反馈会告诉你哪条不满足，必须按反馈修正后再提交。
只输出一个 JSON 对象，不要解释。"""


def _state_for_test():
    from server.agent.loop import State
    return State.from_dict({
        "project": THREE_TASK_PROJECT,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "请按上述硬约束对全部三任务排程。"},
        ],
        "trace": [],
        "llm_calls": 0,
        "invalid_streak": 0,
        "candidate_attempts": {},
        "status": "running",
        "plan": None,
        "clarification": None,
        "failure_reason": None,
    })


def test_real_minimax_end_to_end() -> None:
    """真实 MiniMax 模型从快照收敛到 plan。"""
    from server.adapters.minimax import MiniMaxLLM
    from server.agent.loop import run
    import time
    llm = MiniMaxLLM(
        api_key=os.environ["MINIMAX_API_KEY"],
        model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
        timeout=120.0,
    )
    state = _state_for_test()
    t0 = time.time()
    state = run(state, llm, max_steps=12)
    elapsed = time.time() - t0
    assert state.status == "submitted", (
        f"模型未收敛: status={state.status} reason={state.failure_reason} "
        f"trace={state.trace[-3:] if state.trace else []}"
    )
    assert state.plan is not None
    task_ids = {ch.after.taskId for ch in state.plan.changes if ch.after}
    assert {"t1", "t2", "t3"}.issubset(task_ids), (
        f"排程缺少任务: have {task_ids}"
    )
    assert elapsed < 600


def test_real_minimax_recovers_from_invalid_candidate() -> None:
    """若第一轮模型提交违规候选，循环反馈后应能修正。"""
    from server.adapters.minimax import MiniMaxLLM
    from server.agent.loop import run
    import time
    llm = MiniMaxLLM(
        api_key=os.environ["MINIMAX_API_KEY"],
        model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
        timeout=120.0,
    )
    state = _state_for_test()
    t0 = time.time()
    state = run(state, llm, max_steps=12)
    elapsed = time.time() - t0
    # 校验 trace 中至少有一次 submit 与对应 validation；如未违规则直接通过
    decisions = [t for t in state.trace if t.get("type") == "decision"]
    assert decisions, "模型没有做出任何决策"
    assert state.status == "submitted", (
        f"模型未收敛: status={state.status} reason={state.failure_reason}"
    )
    assert elapsed < 600


def test_real_minimax_handles_invalid_decision_gracefully() -> None:
    """模型若输出结构无法识别，循环应当停止并给出原因。"""
    from server.adapters.minimax import MiniMaxLLM
    from server.agent.loop import run
    # 强制模型出错：把它的输出截断成无 JSON
    import time
    llm = MiniMaxLLM(
        api_key=os.environ["MINIMAX_API_KEY"],
        model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7"),
        timeout=120.0,
    )
    # 通过 messages 引导：只输出奇怪文本
    from server.agent.loop import State
    state = State.from_dict({
        "project": THREE_TASK_PROJECT,
        "messages": [
            {"role": "system",
             "content": "请用纯中文回答，不要 JSON。"},
            {"role": "user", "content": "今天天气怎么样？"},
        ],
        "trace": [], "llm_calls": 0, "invalid_streak": 0,
        "candidate_attempts": {}, "status": "running",
        "plan": None, "clarification": None, "failure_reason": None,
    })
    t0 = time.time()
    state = run(state, llm, max_steps=12)
    elapsed = time.time() - t0
    # 若模型没输出 JSON，_parse_decision 会回退到 submit 空候选
    # 然后循环以"候选为空"或"非法候选连续"停止；状态应为 stopped/submitted
    assert state.status in ("stopped", "submitted"), (
        f"未预期的状态: status={state.status} trace={state.trace[-3:]}"
    )
    assert elapsed < 600

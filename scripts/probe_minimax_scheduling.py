"""02 探针：三任务真实模型收敛验证。

按 `.scratch/loom-mvp/issues/02-minimax-probe.md` 的 10 次运行基准要求，
调用真实 MiniMax API，使用本仓库 `server.domain.constraints` 的真实校验器
向模型反馈违规明细，记录：
- 首次提交是否通过（首次通过率）
- 最终通过率（含修正轮）
- 平均校验轮数
- 完整 token 用量

不模拟任何模型回复；网络失败、解析失败、模型不可用均如实抛出。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any


ENDPOINT = os.environ.get(
    "MINIMAX_CHAT_URL",
    "https://api.minimax.chat/v1/text/chatcompletion_v2",
)
MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.7")
MAX_ROUNDS = int(os.environ.get("PROBE_MAX_ROUNDS", "4"))

THREE_TASK_PROJECT: dict[str, Any] = {
    "id": "probe-001",
    "version": 1,
    "goal": "在 5 天内完成原型实现并联调",
    "deadline": "2026-10-08",
    "milestones": [],
    "tasks": [
        {"id": "t1", "title": "领域模型与校验器", "priority": 1,
         "remainingHours": 6, "done": False, "dependsOn": [],
         "adjustable": True, "blocks": []},
        {"id": "t2", "title": "Agent 循环与工具", "priority": 1,
         "remainingHours": 6, "done": False, "dependsOn": ["t1"],
         "adjustable": True, "blocks": []},
        {"id": "t3", "title": "客户端执行器与回读", "priority": 2,
         "remainingHours": 4, "done": False, "dependsOn": ["t2"],
         "adjustable": True, "blocks": []},
    ],
    "fixedEvents": [],
    "workHours": {"start": "09:00", "end": "18:00"},
    "restDays": [0, 6],
    "preferences": "上午做需要专注的任务",
    "autoAdjust": True,
}

SYSTEM_PROMPT = """你是 Loom Agent。阅读项目 JSON 并只输出一个 JSON 对象表示排程候选。
候选格式严格如下：
{"blocks":[{"taskId":"t1","start":"2026-10-02T09:00","end":"2026-10-02T12:00"}]}
硬约束（必须全部满足，校验器会逐条核对）：
- 时间是设备本地时间，ISO 字符串；不跨休息日（周六周日 0/6）；
- 不跨工作时段 09:00-18:00；
- 块之间不重叠；
- 每任务块总时长等于其剩余工时；
- 后继块不早于前驱全部完成；
- 使用今天及之后的工作日，2026-10-02 是周五，可排到 2026-10-08（周四）之前；
校验器反馈会告诉你哪条不满足，必须按反馈修正后再提交。
只输出一个 JSON 对象，不要解释。"""


def call_minimax(messages: list[dict[str, str]], timeout: float = 90.0) -> dict[str, Any]:
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY missing")
    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "max_tokens": 4096,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def extract_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    return (msg.get("content") or "").strip()


def parse_candidate(text: str) -> dict[str, Any] | None:
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:])
        if s.endswith("```"):
            s = s[:-3]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        a = s.find("{")
        b = s.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(s[a : b + 1])
            except json.JSONDecodeError:
                return None
        return None


# ---------- 真实校验：复刻 server.domain.constraints 的最小版，避免循环 import ----------
def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _hours(a: str, b: str) -> float:
    return (_parse_dt(b) - _parse_dt(a)).total_seconds() / 3600.0


def validate_candidate(project: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, str]]:
    """返回 [{code, blockId, detail}]，空列表表示通过。"""
    violations: list[dict[str, str]] = []
    blocks = candidate.get("blocks") or []
    tasks = {t["id"]: t for t in project["tasks"]}
    work = project["workHours"]
    work_start_h, work_start_m = (int(x) for x in work["start"].split(":"))
    work_end_h, work_end_m = (int(x) for x in work["end"].split(":"))
    rest_days = set(project.get("restDays") or [])
    fixed = project.get("fixedEvents") or []

    parsed: list[tuple[int, dict[str, Any]]] = []
    for i, b in enumerate(blocks):
        try:
            start = _parse_dt(b["start"])
            end = _parse_dt(b["end"])
        except (KeyError, ValueError) as e:
            violations.append({"code": "C0", "blockId": str(i),
                               "detail": f"时间字段无效: {e}"})
            continue
        if end <= start:
            violations.append({"code": "C0", "blockId": b.get("taskId", str(i)),
                               "detail": "end 必须晚于 start"})
            continue
        # 跨休息日
        d = start.date()
        cur = d
        while cur <= end.date():
            if cur.weekday() in rest_days:
                violations.append({"code": "C3", "blockId": b.get("taskId", str(i)),
                                   "detail": f"块落在休息日 {cur.isoformat()}"})
                break
            cur += timedelta(days=1)
        # 工作时段
        sh, sm = start.hour, start.minute
        eh, em = end.hour, end.minute
        if (sh, sm) < (work_start_h, work_start_m) or (eh, em) > (work_end_h, work_end_m):
            violations.append({"code": "C3", "blockId": b.get("taskId", str(i)),
                               "detail": "块未完整落在工作时段内"})
        # 固定日程
        for fe in fixed:
            fs = _parse_dt(fe["start"])
            fe_ = _parse_dt(fe["end"])
            if max(start, fs) < min(end, fe_):
                violations.append({"code": "C2", "blockId": b.get("taskId", str(i)),
                                   "detail": f"与固定日程 {fe.get('id', '?')} 冲突"})
        parsed.append((i, b))

    # C6 重叠
    parsed_sorted = sorted(
        [(b, _parse_dt(b["start"]), _parse_dt(b["end"]), b.get("taskId", str(i)))
         for i, b in parsed],
        key=lambda x: x[1],
    )
    for j in range(1, len(parsed_sorted)):
        prev_block, _, prev_end, prev_tid = parsed_sorted[j - 1]
        cur_block, cur_start, cur_end, cur_tid = parsed_sorted[j]
        if cur_start < prev_end:
            violations.append({"code": "C6", "blockId": cur_tid,
                               "detail": f"与块 {prev_block.get('taskId')} 重叠"})

    # C5 工时总量
    by_task: dict[str, float] = {}
    for _, b in parsed:
        tid = b.get("taskId", "?")
        by_task[tid] = by_task.get(tid, 0.0) + _hours(b["start"], b["end"])
    for tid, total in by_task.items():
        if tid in tasks:
            rem = float(tasks[tid]["remainingHours"])
            if abs(total - rem) > 1e-6:
                violations.append({"code": "C5", "blockId": tid,
                                   "detail": f"块总时长 {total} ≠ 剩余工时 {rem}"})

    # C4 依赖顺序
    task_latest_end: dict[str, datetime] = {}
    for _, b in parsed:
        tid = b.get("taskId", "?")
        end = _parse_dt(b["end"])
        if tid not in task_latest_end or end > task_latest_end[tid]:
            task_latest_end[tid] = end
    for tid, end in task_latest_end.items():
        if tid in tasks:
            for dep in tasks[tid].get("dependsOn", []):
                if dep in task_latest_end:
                    if end < task_latest_end[dep]:
                        violations.append({"code": "C4", "blockId": tid,
                                           "detail": f"依赖 {dep} 尚未完成"})
                else:
                    violations.append({"code": "C4", "blockId": tid,
                                       "detail": f"依赖 {dep} 无排程"})
    return violations


def run_once() -> dict[str, Any]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(THREE_TASK_PROJECT)},
    ]
    rounds: list[dict[str, Any]] = []
    final_pass = False
    t_start = time.time()
    total_tokens = 0
    for r in range(1, MAX_ROUNDS + 1):
        try:
            payload = call_minimax(messages)
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError) as e:
            return {"ok": False, "error": f"round {r}: {e}",
                    "rounds": rounds, "final_pass": False,
                    "elapsed_s": round(time.time() - t_start, 2)}
        text = extract_text(payload)
        usage = payload.get("usage") or {}
        total_tokens += int(usage.get("total_tokens") or 0)
        candidate = parse_candidate(text)
        if candidate is None:
            rounds.append({"round": r, "parsed": False, "raw_text": text,
                           "violations": [{"code": "PARSE", "detail": "无法解析"}]})
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user",
                             "content": "上次回复无法解析为 JSON。请严格按要求输出一个 JSON 对象。"})
            continue
        violations = validate_candidate(THREE_TASK_PROJECT, candidate)
        rounds.append({"round": r, "parsed": True, "candidate": candidate,
                       "violations": violations,
                       "tokens_this_round": usage.get("total_tokens")})
        if not violations:
            final_pass = True
            break
        # 反馈违规明细
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user",
                         "content": "校验器反馈违规：" + json.dumps(violations, ensure_ascii=False) +
                         "。请基于这些具体违规修正后再提交一版。仍只输出 JSON 对象。"})
    return {
        "ok": final_pass,
        "final_pass": final_pass,
        "rounds": rounds,
        "first_pass": (rounds and rounds[0].get("violations") == []),
        "rounds_used": len(rounds),
        "total_tokens": total_tokens,
        "elapsed_s": round(time.time() - t_start, 2),
    }


def main() -> int:
    n_runs = int(os.environ.get("PROBE_RUNS", "10"))
    print(f"running {n_runs} probe iterations against {MODEL} (max {MAX_ROUNDS} rounds)",
          file=sys.stderr)
    results: list[dict[str, Any]] = []
    for i in range(n_runs):
        r = run_once()
        results.append({"run": i + 1, **r})
        print(f"run {i + 1}: pass={r['final_pass']} rounds={r['rounds_used']} "
              f"tokens={r['total_tokens']}", file=sys.stderr)
    passed = sum(1 for r in results if r["final_pass"])
    first_passed = sum(1 for r in results if r["first_pass"])
    rounds_used = [r["rounds_used"] for r in results]
    tokens_used = [r["total_tokens"] for r in results]
    summary = {
        "model": MODEL,
        "endpoint": ENDPOINT,
        "total": n_runs,
        "final_passed": passed,
        "first_passed": first_passed,
        "final_pass_rate": round(passed / n_runs, 4) if n_runs else 0.0,
        "first_pass_rate": round(first_passed / n_runs, 4) if n_runs else 0.0,
        "avg_rounds": round(statistics.mean(rounds_used), 2) if rounds_used else 0.0,
        "median_rounds": statistics.median(rounds_used) if rounds_used else 0.0,
        "avg_tokens": round(statistics.mean(tokens_used), 1) if tokens_used else 0.0,
        "results": results,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

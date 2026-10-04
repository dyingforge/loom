from __future__ import annotations

import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from uuid import uuid4

from fastapi import HTTPException


class UsageLedger:
    PAUSE_TTL_SECONDS = 86400

    def __init__(self, path: Path, public_limit: float, reviewer_limit: float,
                 input_rate: float, output_rate: float, rate_limit: int):
        self.path = path
        self.limits = {"public": public_limit, "reviewer": reviewer_limit}
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.rate_limit = rate_limit
        if min(public_limit, reviewer_limit, input_rate, output_rate, rate_limit) <= 0:
            raise ValueError("额度、价格和请求限制必须大于零")
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, day TEXT, bucket TEXT, reserved REAL, cost REAL, usage TEXT, status TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (ip TEXT, time REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS pauses (token TEXT PRIMARY KEY, state TEXT, expires REAL, consumed INTEGER)")
        self.slots = BoundedSemaphore(4)

    def check_rate(self, ip: str):
        now = time.time()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM requests WHERE time < ?", (now - 60,))
            count = db.execute("SELECT COUNT(*) FROM requests WHERE ip = ?", (ip,)).fetchone()[0]
            if count >= self.rate_limit:
                raise HTTPException(429, "每分钟请求次数达到上限，请稍后重新发起")
            db.execute("INSERT INTO requests VALUES (?, ?)", (ip, now))

    def reserve(self, bucket: str) -> str:
        day = datetime.now(timezone.utc).date().isoformat()
        # 为提供方完整上下文及最大输出预留额度，未知用量保留预留金额。
        amount = (204800 * self.input_rate + 8192 * self.output_rate) / 1_000_000
        identifier = uuid4().hex
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM calls WHERE day=? AND bucket=?", (day, bucket)).fetchone()[0]
            if used + amount > self.limits[bucket]:
                raise HTTPException(429, "当日模型额度不足以预留下一次调用，规划已停止")
            db.execute("INSERT INTO calls VALUES (?,?,?,?,NULL,NULL,'reserved')", (identifier, day, bucket, amount))
        return identifier

    def settle(self, identifier: str, usage: dict):
        prompt = usage["prompt_tokens"]
        completion = usage["completion_tokens"]
        if not isinstance(prompt, int) or not isinstance(completion, int) or min(prompt, completion) < 0:
            raise ValueError("提供方没有返回有效的用量计数")
        amount = (prompt * self.input_rate + completion * self.output_rate) / 1_000_000
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE calls SET cost=?,usage=?,status='reported' WHERE id=?", (amount, json.dumps(usage), identifier))

    def pause(self, state: dict) -> str:
        now = time.time()
        expires = now + self.PAUSE_TTL_SECONDS
        token = f"{expires:.0f}.{secrets.token_urlsafe(32)}"
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM pauses WHERE expires < ?", (now,))
            db.execute("INSERT INTO pauses VALUES (?,?,?,0)",
                       (token, json.dumps(state, ensure_ascii=False), expires))
        return token

    @staticmethod
    def _token_expiry(token: str) -> float | None:
        prefix, separator, _ = token.partition(".")
        if not separator:
            return None
        try:
            return float(prefix)
        except ValueError:
            return None

    def resume(self, token: str, project_id: str) -> dict:
        now = time.time()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,expires,consumed FROM pauses WHERE token=?", (token,)).fetchone()
            if row is None:
                expiry = self._token_expiry(token)
                if expiry is not None and expiry <= now:
                    raise HTTPException(410, detail={"code": "resume_expired", "message": "恢复凭据已过期，请重新发起规划"})
                raise HTTPException(404, detail={"code": "resume_unknown", "message": "恢复凭据不存在，请重新发起规划"})
            if row[2]:
                raise HTTPException(409, detail={"code": "resume_consumed", "message": "恢复凭据已使用，请重新发起规划"})
            if row[1] <= now:
                raise HTTPException(410, detail={"code": "resume_expired", "message": "恢复凭据已过期，请重新发起规划"})
            data = json.loads(row[0])
            if data["project"]["id"] != project_id:
                raise HTTPException(409, detail={"code": "resume_project_mismatch", "message": "恢复请求属于不同项目"})
            db.execute("UPDATE pauses SET consumed=1 WHERE token=?", (token,))
        return data


class MeteredLLM:
    def __init__(self, llm, ledger: UsageLedger, bucket: str):
        self.llm = llm
        self.ledger = ledger
        self.bucket = bucket

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        if len(json.dumps({"messages": messages, "tools": tools}).encode()) > 200000:
            raise ValueError("本轮上下文超过服务限制，请重新发起规划")
        with self.ledger.slots:
            identifier = self.ledger.reserve(self.bucket)
            response = self.llm.chat(messages, tools)
            self.ledger.settle(identifier, response["usage"])
            return response

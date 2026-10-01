"""领域模型（Pydantic）。

类型是 server 端的唯一来源。客户端按 `docs/PROTOCOL.md` 中的 JSON Schema
独立解析。IO、模型适配器、Web 框架均不依赖本模块。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ----- 时间与基础 -----
class WorkHours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM 工作日起始")
    end: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM 工作日结束")


# ----- 时间块 -----
class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    taskId: str
    start: datetime
    end: datetime
    done: bool = False

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v: datetime, info) -> datetime:
        start = info.data.get("start")
        if start is not None and v <= start:
            raise ValueError("block.end 必须晚于 block.start")
        return v


# ----- 任务 -----
class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    priority: int = Field(ge=1, le=5)
    remainingHours: float = Field(ge=0)
    done: bool = False
    dependsOn: list[str] = Field(default_factory=list)
    adjustable: bool = False
    blocks: list[Block] = Field(default_factory=list)


# ----- 固定日程 -----
class FixedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str = ""
    start: datetime
    end: datetime


# ----- 里程碑 -----
class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    due: datetime


# ----- 计划 -----
class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blockId: str
    before: Optional[Block] = None
    after: Optional[Block] = None


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planId: str
    baseVersion: int
    changes: list[Change]
    risks: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    rationale: str = ""


# ----- 候选 -----
class CandidateBlock(BaseModel):
    """候选中的时间块，仅需 taskId + 起止；id 可选。"""
    model_config = ConfigDict(extra="forbid")
    taskId: str
    start: datetime
    end: datetime
    id: Optional[str] = None


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[CandidateBlock]


# ----- 项目 -----
class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=0)
    goal: str
    deadline: Optional[datetime] = None
    milestones: list[Milestone] = Field(default_factory=list)
    tasks: list[Task]
    fixedEvents: list[FixedEvent] = Field(default_factory=list)
    workHours: WorkHours
    restDays: list[int] = Field(
        default_factory=lambda: [0, 6],
        description="Python weekday(): 0=周一, 6=周日",
    )
    preferences: str = ""
    autoAdjust: bool = True

    @field_validator("restDays")
    @classmethod
    def _rest_days_in_range(cls, v: list[int]) -> list[int]:
        for d in v:
            if d < 0 or d > 6:
                raise ValueError(f"restDay {d} 越界 [0,6]")
        return v


# ----- 回执 -----
class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planId: str
    versionBefore: int
    versionAfter: int
    readbackSnapshot: Project
    status: Literal["verified", "not_verified", "save_failed", "rejected"]
    reason: str = ""


# ----- Agent 请求 / 响应 -----
class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot: Project
    trigger: Literal["delay", "progress", "new", "resume", "propose"]
    clarificationAnswer: Optional[str] = None
    state: Optional[dict] = None  # 暂停恢复用


class Violation(BaseModel):
    code: str
    blockId: str
    detail: str


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["plan", "clarify", "failed"]
    payload: dict
    trace: list[dict] = Field(default_factory=list)

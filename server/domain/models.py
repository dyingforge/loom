from __future__ import annotations

from datetime import datetime, time
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ----- 时间与基础 -----
class WorkHours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM 工作日起始")
    end: str = Field(pattern=r"^\d{2}:\d{2}$", description="HH:MM 工作日结束")

    @model_validator(mode="after")
    def valid_interval(self):
        if time.fromisoformat(self.end) <= time.fromisoformat(self.start):
            raise ValueError("工作结束时间必须晚于开始时间")
        return self


# ----- 时间块 -----
class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    taskId: str
    start: datetime
    end: datetime
    done: bool = False

    @field_validator("start", "end")
    @classmethod
    def _local_time(cls, value):
        if value.tzinfo is not None:
            raise ValueError("时间必须使用项目所在地的无偏移日历时间")
        return value

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
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    priority: int = Field(ge=1, le=5)
    remainingHours: float = Field(ge=0, le=720, allow_inf_nan=False)
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

    @model_validator(mode="after")
    def valid_interval(self):
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("时间必须使用项目所在地的无偏移日历时间")
        if self.end <= self.start:
            raise ValueError("固定日程结束必须晚于开始")
        return self


# ----- 里程碑 -----
class Milestone(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    due: datetime
    taskIds: list[str] = Field(default_factory=list)

    @field_validator("due")
    @classmethod
    def local_due(cls, value):
        if value.tzinfo is not None:
            raise ValueError("里程碑必须使用项目所在地的无偏移日历时间")
        return value


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
    done: bool = False

    @model_validator(mode="after")
    def valid_interval(self):
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("时间必须使用项目所在地的无偏移日历时间")
        if self.end <= self.start:
            raise ValueError("结束时间必须晚于开始时间")
        return self


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
        default_factory=lambda: [5, 6],
        description="Python weekday(): 0=周一, 6=周日",
    )
    preferences: str = ""
    autoAdjust: bool = False

    @field_validator("deadline")
    @classmethod
    def _local_deadline(cls, value):
        if value is not None and value.tzinfo is not None:
            raise ValueError("截止时间必须使用项目所在地的无偏移日历时间")
        return value

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
    trigger: Literal["delay", "progress", "new", "resume", "propose", "compose", "revise"]
    instruction: str = Field(default="", max_length=4000)
    clarificationAnswer: Optional[str] = None
    resumeToken: Optional[str] = None  # 服务端恢复凭据
    now: datetime

    @model_validator(mode="after")
    def calendar_request(self):
        if self.trigger in ("compose", "revise"):
            if not self.snapshot.goal.strip() or self.snapshot.deadline is None:
                raise ValueError("请填写目标和截止日期")
            if self.snapshot.deadline <= self.now:
                raise ValueError("截止日期必须晚于当前时间")
        if self.trigger == "revise" and not self.instruction.strip():
            raise ValueError("请填写修改建议")
        return self

    @field_validator("now")
    @classmethod
    def local_now(cls, value):
        if value.tzinfo is not None:
            raise ValueError("now 必须使用项目所在地的无偏移日历时间")
        return value


class Violation(BaseModel):
    code: str
    blockId: str
    detail: str


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["plan", "tasks", "clarify", "failed"]
    payload: dict

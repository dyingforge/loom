"""版本失配检测：方案生成后用户修改项目，旧方案不应直接执行。

逻辑：
- 客户端执行前若 project.version != plan.baseVersion + 1，则版本失配；
- 服务端仅支持最多 1 次自动重算；第二次失配则停止并要求用户重新发起。
"""
from __future__ import annotations

from dataclasses import dataclass


MAX_AUTO_RECALCULATIONS = 1


@dataclass
class VersionCheckResult:
    ok: bool
    needs_recalculation: bool
    reason: str = ""


def check_version(plan_base_version: int, current_version: int,
                  recalculation_count: int) -> VersionCheckResult:
    expected_after = plan_base_version + 1
    if current_version == expected_after:
        return VersionCheckResult(ok=True, needs_recalculation=False)
    if recalculation_count >= MAX_AUTO_RECALCULATIONS:
        return VersionCheckResult(
            ok=False, needs_recalculation=False,
            reason="版本多次变化，已达最大重算次数；请用户重新发起",
        )
    return VersionCheckResult(
        ok=False, needs_recalculation=True,
        reason=f"版本失配：plan.baseVersion={plan_base_version}, "
               f"current={current_version}",
    )

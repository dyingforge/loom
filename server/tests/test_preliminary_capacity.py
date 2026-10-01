from datetime import datetime

from server.domain.capacity import capacity, schedule_risks
from server.domain.models import Candidate, Milestone
from server.domain.scheduling import diff
from server.runtime.executor import can_auto_execute
from server.tests.test_preliminary_constraints import NOW, blocks, project


def test_capacity_accounts_for_rest_days_and_locked_time():
    value = project()
    value.deadline = datetime(2026, 10, 1, 11)
    assert capacity(value, NOW) == {"remainingHours": 3, "availableHours": 2, "gapHours": 1}
    value.deadline = datetime(2026, 10, 4, 18)
    assert capacity(value, NOW)["availableHours"] == 18


def test_deadline_and_scoped_milestone_risks():
    value = project()
    value.deadline = datetime(2026, 10, 1, 11, 30)
    value.milestones = [Milestone(id="m", title="设计完成", due=NOW.replace(hour=10), taskIds=["a"])]
    risks = schedule_risks(value, Candidate.model_validate({"blocks": blocks()}))
    assert len(risks) == 2
    assert "b" in risks[0] and "a" in risks[1]


def test_automatic_execution_requires_every_permission_and_valid_schedule():
    value = project()
    candidate = Candidate.model_validate({"blocks": blocks()})
    plan = diff(value, candidate)
    assert not can_auto_execute(plan, value, NOW)["ok"]
    value.autoAdjust = True
    assert not can_auto_execute(plan, value, NOW)["ok"]
    for task in value.tasks:
        task.adjustable = True
    assert can_auto_execute(plan, value, NOW)["ok"]
    plan.risks = ["超期"]
    assert not can_auto_execute(plan, value, NOW)["ok"]
    plan.risks = []
    value.version += 1
    assert not can_auto_execute(plan, value, NOW)["ok"]

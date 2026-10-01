from server.domain.models import Candidate, Plan
from server.domain.scheduling import diff
from server.runtime.plans import apply_plan
from server.runtime.reconcile import verify
from server.tests.test_preliminary_constraints import blocks, project


def prepared():
    before = project()
    plan = diff(before, Candidate.model_validate({"blocks": blocks()}))
    after = apply_plan(before, plan)
    return before, plan, after


def receipt(before, plan, after, version=2):
    return verify(plan.model_dump(mode="json"), before.version, version, after, before)


def test_full_readback_matches():
    before, plan, after = prepared()
    assert receipt(before, plan, after).status == "verified"


def test_wrong_versions_and_completion_are_rejected():
    before, plan, after = prepared()
    assert receipt(before, plan, after, version=99).status == "not_verified"
    after.tasks[0].blocks[0].done = True
    assert receipt(before, plan, after).status == "not_verified"


def test_extra_block_missing_block_and_wrong_task_are_rejected():
    before, plan, after = prepared()
    after.tasks[1].blocks.append(after.tasks[0].blocks[0].model_copy(update={"id": "extra", "taskId": "b"}))
    assert receipt(before, plan, after).status == "not_verified"
    before, plan, after = prepared()
    after.tasks[0].blocks = []
    assert receipt(before, plan, after).status == "not_verified"
    before, plan, after = prepared()
    after.tasks[0].blocks[0].taskId = "b"
    assert receipt(before, plan, after).status == "not_verified"


def test_delete_and_unchanged_block():
    _, _, before = prepared()
    removed = before.tasks[0].blocks[0]
    plan = Plan(planId="deletion", baseVersion=before.version,
                changes=[{"blockId": removed.id, "before": removed, "after": None}])
    after = apply_plan(before, plan)
    assert after.tasks[1].blocks == before.tasks[1].blocks
    assert after.tasks[0].blocks == []
    assert receipt(before, plan, after, version=3).status == "verified"
    after.tasks[0].blocks = [removed]
    assert receipt(before, plan, after, version=3).status == "not_verified"


def test_project_details_are_part_of_receipt():
    before, plan, after = prepared()
    after.tasks[0].remainingHours += 1
    assert receipt(before, plan, after).status == "not_verified"

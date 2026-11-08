"""The task_plan tool behind Agent mode's checklist."""

from __future__ import annotations

from locus.server.approvals import tool_risk
from locus.tools.task_plan import MAX_STEPS, TaskPlanTool


def test_plan_is_cleaned_and_counted():
    result = TaskPlanTool().execute(
        steps=[
            {"title": " Find files ", "status": "done"},
            {"title": "Move them", "status": "in_progress"},
            {"title": "Report", "status": "nonsense"},
            {"title": "", "status": "done"},
            "not a step",
        ]
    )

    assert result.success
    assert result.content == "Plan shown to the user (1 of 3 steps done)."
    assert result.metadata["steps"] == [
        {"title": "Find files", "status": "done"},
        {"title": "Move them", "status": "in_progress"},
        {"title": "Report", "status": "pending"},
    ]


def test_plan_is_capped():
    steps = [{"title": f"Step {i}", "status": "pending"} for i in range(20)]
    assert len(TaskPlanTool().execute(steps=steps).metadata["steps"]) == MAX_STEPS


def test_empty_plans_fail():
    assert not TaskPlanTool().execute(steps=[]).success
    assert not TaskPlanTool().execute(steps=[{"title": " "}]).success
    assert not TaskPlanTool().execute().success


def test_planning_never_asks():
    tool = TaskPlanTool()
    assert tool_risk("task_plan", tool, {"steps": []}) == "read"
    assert tool_risk("task_plan") == "read"

"""Task plan tool — the agent's visible checklist for multi-step tasks.

The chat shows the latest ``task_plan`` call as a checklist (from its
``tool_call_start`` event), so the user can follow the task while it runs.
"""

from __future__ import annotations

from typing import Any

from locus.core.registry import ToolRegistry
from locus.core.types import ToolResult
from locus.tools._stubs import BaseTool, ToolSpec

STATUSES = ("pending", "in_progress", "done", "skipped")
MAX_STEPS = 12


@ToolRegistry.register("task_plan")
class TaskPlanTool(BaseTool):
    """Show or update the plan for the current task."""

    tool_id = "task_plan"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="task_plan",
            description=(
                "Show the user your plan for a task that takes more than one"
                " step. Call it before starting, with every step 'pending'"
                " except the first ('in_progress'), then again whenever a step"
                " finishes, sending the whole list each time. Keep steps short"
                " (a few words) and at most 12."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "status": {"type": "string", "enum": list(STATUSES)},
                            },
                            "required": ["title", "status"],
                        },
                    },
                },
                "required": ["steps"],
            },
            category="reasoning",
        )

    def risk_for(self, arguments: dict) -> str:
        return "read"

    def execute(self, **params: Any) -> ToolResult:
        steps = params.get("steps")
        if not isinstance(steps, list) or not steps:
            return ToolResult(
                tool_name="task_plan",
                content="Send at least one step, each with a title and status.",
                success=False,
            )
        clean = []
        for step in steps[:MAX_STEPS]:
            if not isinstance(step, dict) or not str(step.get("title", "")).strip():
                continue
            status = step.get("status")
            clean.append(
                {
                    "title": str(step["title"]).strip(),
                    "status": status if status in STATUSES else "pending",
                }
            )
        if not clean:
            return ToolResult(
                tool_name="task_plan",
                content="Each step needs a title.",
                success=False,
            )
        done = sum(s["status"] in ("done", "skipped") for s in clean)
        return ToolResult(
            tool_name="task_plan",
            content=f"Plan shown to the user ({done} of {len(clean)} steps done).",
            success=True,
            metadata={"steps": clean},
        )


__all__ = ["TaskPlanTool", "STATUSES"]

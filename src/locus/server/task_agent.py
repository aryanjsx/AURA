"""The tool-using agent behind the chat's Agent mode.

Agent mode always uses its own ``orchestrator``, built on first use with
:data:`ASSISTANT_TOOLS` and cached on ``app.state``, rather than the server's
configured agent: only this agent asks the user before tools that change
something (see ``server/approvals.py``).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("locus.server")

# Tools that change something (writing files, running commands) ask in the
# chat before each call; see ``server/approvals.py``. Network access waits.
ASSISTANT_TOOLS = (
    "task_plan",
    "think",
    "calculator",
    "file_read",
    "pdf_extract",
    "memory_manage",
    "git_status",
    "git_diff",
    "git_log",
    "file_write",
    "shell_exec",
    # Desktop control (locus.tools.desktop)
    "open_path",
    "app_control",
    "window_control",
    "system_control",
    "clipboard",
    "notify",
    "screenshot",
)

#: Agent mode tasks take more steps than chat; ``agent.max_turns`` can raise it.
MIN_MAX_TURNS = 25

ASSISTANT_AGENT_ID = "assistant"

_build_lock = threading.Lock()


def get_task_agent(state: Any) -> Optional[Any]:
    """Return the Agent mode agent for *state* (``app.state``), or ``None``."""
    cached = getattr(state, "task_agent", None)
    if cached is not None:
        return cached
    with _build_lock:
        cached = getattr(state, "task_agent", None)
        if cached is None:
            try:
                cached = _build_task_agent(state)
            except Exception:
                logger.warning("Agent mode could not start", exc_info=True)
                return None
            state.task_agent = cached
    return cached


def _assistant_tools(config: Any) -> list:
    import locus.tools  # noqa: F401  # trigger registration
    from locus.core.registry import ToolRegistry
    from locus.tools._paths import file_tool_kwargs
    from locus.tools._stubs import BaseTool

    tools = []
    for name in ASSISTANT_TOOLS:
        if not ToolRegistry.contains(name):
            continue
        tool_cls = ToolRegistry.get(name)
        if isinstance(tool_cls, BaseTool):
            tools.append(tool_cls)
            continue
        if not (isinstance(tool_cls, type) and issubclass(tool_cls, BaseTool)):
            continue
        kwargs = file_tool_kwargs(name, config)
        # An empty allow-list means "anywhere"; keep Agent mode in the home
        # folder unless the user configured something narrower or wider.
        if name in ("file_read", "file_write") and not kwargs.get("allowed_dirs"):
            kwargs["allowed_dirs"] = [str(Path.home())]
        if name == "file_write":
            # Same tool, but each change can be undone from the chat.
            from locus.tools.undo_journal import UndoableFileWriteTool

            tool_cls = UndoableFileWriteTool
        tools.append(tool_cls(**kwargs))
    return tools


def _build_task_agent(state: Any) -> Any:
    return _build_agent(
        state,
        tools=_assistant_tools(getattr(state, "config", None)),
        agent_id=ASSISTANT_AGENT_ID,
    )


DEVELOPER_AGENT_ID = "developer"

#: Developer agents kept per project folder (oldest dropped past this).
MAX_DEVELOPER_AGENTS = 8


def get_developer_agent(state: Any, project_dir: Optional[str]) -> Any:
    """The developer mode agent for *project_dir*.

    Raises ``ValueError`` (with a message for the user) if the folder can't
    be used.
    """
    from locus.server.developer import resolve_project_dir

    project = resolve_project_dir(project_dir)
    with _build_lock:
        agents = getattr(state, "developer_agents", None)
        if agents is None:
            agents = {}
            state.developer_agents = agents
        agent = agents.get(str(project))
        if agent is None:
            agent = _build_developer_agent(state, project)
            if len(agents) >= MAX_DEVELOPER_AGENTS:
                agents.pop(next(iter(agents)))
            agents[str(project)] = agent
        return agent


def _build_developer_agent(state: Any, project: Path) -> Any:
    from locus.server.developer import developer_prompt, developer_tools

    return _build_agent(
        state,
        tools=developer_tools(project, getattr(state, "config", None)),
        agent_id=DEVELOPER_AGENT_ID,
        system_prompt=developer_prompt(project),
    )


def _build_agent(
    state: Any,
    *,
    tools: list,
    agent_id: str,
    system_prompt: Optional[str] = None,
) -> Any:
    import inspect

    import locus.agents  # noqa: F401  # trigger registration
    from locus.core.registry import AgentRegistry
    from locus.security.runtime import agent_security_kwargs, wire_agent_security
    from locus.server.approvals import before_tool_call, confirm_after_approval

    config = getattr(state, "config", None)
    bus = getattr(state, "bus", None)
    capability_policy = getattr(state, "capability_policy", None)
    rate_limiter = getattr(state, "rate_limiter", None)

    agent_cls = AgentRegistry.get("orchestrator")
    kwargs: dict[str, Any] = {
        "bus": bus,
        "tools": tools,
        "agent_id": agent_id,
        "max_turns": MIN_MAX_TURNS,
        "before_tool_call": before_tool_call,
        # The hook asks the user first, so the executor may run tools marked
        # requires_confirmation (shell_exec) once they're approved.
        "interactive": True,
        "confirm_callback": confirm_after_approval,
        # Approvals are tracked per run on the agent's thread; parallel tool
        # threads wouldn't see the run's approval session.
        "parallel_tools": False,
    }
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if config is not None:
        kwargs["max_turns"] = max(config.agent.max_turns, MIN_MAX_TURNS)
    if (
        config is not None
        and not system_prompt
        and "prompt_builder" in inspect.signature(agent_cls.__init__).parameters
    ):
        from locus.prompt.builder import SystemPromptBuilder

        kwargs["prompt_builder"] = SystemPromptBuilder(
            agent_template=config.agent.default_system_prompt or "",
            memory_files_config=config.memory_files,
            system_prompt_config=config.system_prompt,
        )
    kwargs.update(
        agent_security_kwargs(
            agent_cls,
            capability_policy=capability_policy,
            rate_limiter=rate_limiter,
            agent_id=agent_id,
        )
    )

    agent = agent_cls(state.engine, state.model, **kwargs)
    wire_agent_security(
        agent,
        bus=bus,
        capability_policy=capability_policy,
        rate_limiter=rate_limiter,
        agent_id=agent_id,
    )
    return agent


def agent_event_ids(agent: Any) -> set[str]:
    """Ids that *agent*'s turn and tool events carry in their ``agent`` field."""
    ids = {
        getattr(agent, "agent_id", None),
        getattr(agent, "_runtime_agent_id", None),
        getattr(getattr(agent, "_executor", None), "_agent_id", None),
    }
    return {i for i in ids if isinstance(i, str) and i}

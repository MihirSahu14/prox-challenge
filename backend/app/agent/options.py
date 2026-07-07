"""Builds ClaudeAgentOptions for a chat turn.

Deliberate decisions (see CLAUDE.md):
- tools=[] disables ALL built-in tools (no filesystem/shell/web for this agent).
- strict_mcp_config=True ignores any MCP servers configured on the host machine.
- permission_mode="bypassPermissions" because the only tools are our own
  read-only, side-effect-free functions; the default mode would hang a headless
  server waiting for an interactive approval.
"""

from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server

from ..config import AGENT_MODEL, SYSTEM_PROMPT_PATH
from .tools.get_image import get_image
from .tools.get_video_moment import get_video_moment
from .tools.render_artifact import render_artifact
from .tools.search_knowledge import search_knowledge

_server = create_sdk_mcp_server(
    name="prox",
    version="1.0.0",
    tools=[search_knowledge, get_image, render_artifact, get_video_moment],
)

_system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_options(resume_session_id: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=AGENT_MODEL,
        system_prompt=_system_prompt,
        mcp_servers={"prox": _server},
        strict_mcp_config=True,
        tools=[],
        allowed_tools=[
            "mcp__prox__search_knowledge",
            "mcp__prox__get_image",
            "mcp__prox__render_artifact",
            "mcp__prox__get_video_moment",
        ],
        permission_mode="bypassPermissions",
        include_partial_messages=True,
        max_turns=12,
        resume=resume_session_id,
    )

"""Runs one agent turn and translates SDK messages into frontend content blocks.

Streaming translation rules:
- StreamEvent text deltas -> text_delta blocks (token-level streaming).
- AssistantMessage TextBlocks are NOT re-emitted (already streamed as deltas).
- ToolUseBlock render_artifact -> artifact block (the tool INPUT is the artifact).
- ToolUseBlock get_image -> image block pointing at the static /kb-images URL.
- ToolUseBlock search_knowledge -> tool_status block ("searching the manual").
- ResultMessage -> done block.

Multi-turn: the first turn's session_id is stored per conversation_id; later
turns pass it as options.resume so the SDK reloads history server-side.
"""

import re
import uuid
from collections.abc import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
    query,
)

from ..retrieval.index import get_index
from ..streaming.blocks import block
from .options import build_options

# conversation_id -> SDK session_id (in-memory; fine for a local single-user demo)
_sessions: dict[str, str] = {}

_REGISTER_RE = re.compile(r"^\s*\[\[register:(calm|warm|brisk|neutral)\]\]\s*")


def _tool_short_name(name: str) -> str:
    return name.rsplit("__", 1)[-1]


def _format_voice_block(voice_meta: dict) -> str:
    parts = [f"{k}={v}" for k, v in voice_meta.items()]
    return f"\n\n[VOICE_INPUT {' '.join(parts)}]"


class _RegisterParser:
    """Strips a leading [[register:x]] tag from the start of any text block in
    a voice turn and surfaces the first one as a voice_register block. Buffers
    at each text-block start until the tag either matches or is ruled out."""

    def __init__(self, enabled: bool):
        self.voice = enabled
        self.pending: str | None = "" if enabled else None
        self.register: str | None = None

    def on_text_block_start(self) -> None:
        if self.voice:
            self.pending = ""

    def feed(self, delta: str) -> tuple[str | None, str]:
        """Returns (new_register_or_None, text_to_emit)."""
        if self.pending is None:
            return None, delta
        self.pending += delta
        match = _REGISTER_RE.match(self.pending)
        if match:
            rest = self.pending[match.end():]
            self.pending = None
            register = match.group(1)
            if self.register is None:
                self.register = register
                return register, rest
            return None, rest  # later duplicate tags: strip silently
        # Give up buffering once it's clear no tag is coming.
        probe = self.pending.lstrip()[:11]
        if len(self.pending) > 48 or not "[[register:".startswith(probe):
            rest, self.pending = self.pending, None
            return None, rest
        return None, ""

    def flush(self) -> str:
        rest = self.pending or ""
        self.pending = None
        return rest


async def run_turn(
    conversation_id: str | None,
    message: str,
    voice_meta: dict | None = None,
) -> AsyncIterator[str]:
    conversation_id = conversation_id or str(uuid.uuid4())
    options = build_options(resume_session_id=_sessions.get(conversation_id))
    prompt = message + (_format_voice_block(voice_meta) if voice_meta else "")
    parser = _RegisterParser(enabled=voice_meta is not None)

    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, StreamEvent):
                event = msg.event
                etype = event.get("type")
                if (
                    etype == "content_block_start"
                    and event.get("content_block", {}).get("type") == "text"
                ):
                    leftover = parser.flush()
                    if leftover:
                        yield block("text_delta", text=leftover)
                    parser.on_text_block_start()
                elif (
                    etype == "content_block_delta"
                    and event.get("delta", {}).get("type") == "text_delta"
                ):
                    register, text = parser.feed(event["delta"]["text"])
                    if register:
                        yield block("voice_register", register=register)
                    if text:
                        yield block("text_delta", text=text)
                elif etype == "content_block_stop":
                    leftover = parser.flush()
                    if leftover:
                        yield block("text_delta", text=leftover)

            elif isinstance(msg, AssistantMessage):
                if msg.session_id and conversation_id not in _sessions:
                    _sessions[conversation_id] = msg.session_id
                    yield block("session", conversation_id=conversation_id,
                                session_id=msg.session_id)
                for content_block in msg.content:
                    if not isinstance(content_block, ToolUseBlock):
                        continue
                    name = _tool_short_name(content_block.name)
                    tool_input = content_block.input or {}
                    if name == "search_knowledge":
                        yield block("tool_status", tool=name, state="start",
                                    summary=f"Searching the manual: “{tool_input.get('query', '')}”")
                    elif name == "get_image":
                        figure_id = tool_input.get("figure_id", "")
                        figure = get_index().figures.get(figure_id)
                        if figure:
                            yield block(
                                "image",
                                figure_id=figure_id,
                                url=f"/kb-images/{figure_id}.png",
                                caption=figure.get("title", figure_id),
                                source=figure["source"],
                                page=figure["page"],
                            )
                    elif name == "get_video_moment":
                        frame_id = tool_input.get("frame_id", "")
                        moment = get_index().video_moments.get(frame_id)
                        if moment:
                            yield block(
                                "video_moment",
                                frame_id=frame_id,
                                url=f"/kb-images/video/{frame_id}.jpg",
                                caption=moment["caption"],
                                timestamp=moment["timestamp"],
                                t_seconds=moment["t_seconds"],
                                video_id=moment["video_id"],
                                youtube_url=moment["youtube_url"],
                            )
                    elif name == "render_artifact":
                        yield block(
                            "artifact",
                            id=content_block.id,
                            title=tool_input.get("title", "Artifact"),
                            artifact_type=tool_input.get("type", "html"),
                            code=tool_input.get("code", ""),
                        )

            elif isinstance(msg, ResultMessage):
                leftover = parser.flush()
                if leftover:
                    yield block("text_delta", text=leftover)
                if conversation_id not in _sessions and msg.session_id:
                    _sessions[conversation_id] = msg.session_id
                if msg.is_error:
                    yield block("error", message=msg.result or "Agent returned an error.")
                yield block("done", conversation_id=conversation_id)

    except Exception as exc:  # surface failures to the UI instead of a dropped stream
        yield block("error", message=f"{type(exc).__name__}: {exc}")
        yield block("done", conversation_id=conversation_id)

"""Typed content blocks streamed to the frontend as newline-delimited JSON.

Block types:
    session             {conversation_id, session_id}
    text_delta          {text}
    tool_status         {tool, state: "start"|"end", summary}
    image               {figure_id, url, caption, source, page}
    artifact            {id, title, artifact_type: "html"|"react", code}
    error               {message}
    done                {}
"""

import json
from typing import Any


def block(type_: str, **fields: Any) -> str:
    return json.dumps({"type": type_, **fields}, ensure_ascii=False) + "\n"

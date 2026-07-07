from claude_agent_sdk import tool

# The tool call's INPUT is the artifact: the streaming layer forwards the
# tool_use block's {title, type, code} straight to the frontend, which renders
# it in a sandboxed iframe. This handler only validates and acknowledges so the
# agent loop continues — it never executes the code.

MAX_CODE_CHARS = 60_000


@tool(
    "render_artifact",
    "Render an interactive artifact (diagram, calculator, configurator, flowchart) in the chat. "
    "type='html': self-contained HTML/CSS/JS for the page body (Tailwind classes available; "
    "inline SVG welcome). type='react': JSX defining `function App() {...}` using React 18 via "
    "globals (React.useState etc.), Tailwind classes, and Chart.js as global `Chart`; no imports. "
    "The artifact displays to the user immediately.",
    {"title": str, "type": str, "code": str},
)
async def render_artifact(args):
    kind = args.get("type", "")
    code = args.get("code", "")
    if kind not in ("html", "react"):
        return {
            "content": [{"type": "text", "text": "type must be 'html' or 'react'."}],
            "is_error": True,
        }
    if not code.strip():
        return {
            "content": [{"type": "text", "text": "code must not be empty."}],
            "is_error": True,
        }
    if len(code) > MAX_CODE_CHARS:
        return {
            "content": [{"type": "text", "text": f"code exceeds {MAX_CODE_CHARS} chars; simplify."}],
            "is_error": True,
        }
    return {
        "content": [{
            "type": "text",
            "text": f"Artifact '{args.get('title', 'untitled')}' rendered to the user.",
        }]
    }

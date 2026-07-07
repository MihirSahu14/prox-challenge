from claude_agent_sdk import tool

from ...retrieval.graph import get_graph
from ...retrieval.index import get_index


@tool(
    "search_knowledge",
    "Semantic search over the Vulcan OmniPro 220 knowledge base (owner's manual, quick start "
    "guide, selection chart). Returns relevant passages with their section and page numbers, "
    "plus any relevant manual figures (call get_image with a figure_id to show one to the user). "
    "Always call this before answering a technical question.",
    {"query": str, "top_k": int},
)
async def search_knowledge(args):
    index = get_index()
    top_k = min(int(args.get("top_k") or 6), 12)
    results = index.search(args["query"], top_k=top_k)

    lines = []
    for r in results:
        if r["type"] == "video_frame":
            lines.append(
                f"[VIDEO MOMENT at {r['timestamp']}: frame_id={r['frame_id']}] ({r['doc']})\n"
                f"{r['text']}\n"
                f"-> Call get_video_moment with frame_id=\"{r['frame_id']}\" to show the user "
                f"this screenshot + a player starting at {r['timestamp']}."
            )
            continue
        loc = f"{r['doc']} — {r['section']}, p.{r['page_start']}"
        if r["type"] == "image_caption":
            lines.append(
                f"[FIGURE available: figure_id={r['figure_id']}] ({loc})\n"
                f"{r['text']}\n"
                f"-> Call get_image with figure_id=\"{r['figure_id']}\" to show this image to the user."
            )
        else:
            lines.append(f"[{loc}]\n{r['text']}")

    text = "\n\n---\n\n".join(lines) if lines else "No results found."

    facts = get_graph().related_facts(args["query"])
    if facts:
        text += (
            "\n\n=== Related knowledge graph facts "
            "(symptom -> cause -> fix relationships) ===\n" + facts
        )
    return {"content": [{"type": "text", "text": text}]}

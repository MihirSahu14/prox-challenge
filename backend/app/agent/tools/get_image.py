import base64

from claude_agent_sdk import tool

from ...config import IMAGES_DIR
from ...retrieval.index import get_index


@tool(
    "get_image",
    "Retrieve a figure from the manual by figure_id (discovered via search_knowledge) and show "
    "it to the user. The image is displayed in the chat automatically and also returned to you "
    "so you can reference its details.",
    {"figure_id": str},
)
async def get_image(args):
    figure_id = args["figure_id"]
    figure = get_index().figures.get(figure_id)
    path = IMAGES_DIR / f"{figure_id}.png"
    if figure is None or not path.exists():
        known = ", ".join(sorted(get_index().figures))
        return {
            "content": [{
                "type": "text",
                "text": f"Unknown figure_id '{figure_id}'. Known figures: {known}",
            }],
            "is_error": True,
        }
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {
        "content": [
            {"type": "image", "data": data, "mimeType": "image/png"},
            {
                "type": "text",
                "text": f"Figure '{figure_id}' ({figure['source']} p.{figure['page']}) is now "
                        f"displayed to the user. Caption: {figure['caption']}",
            },
        ]
    }

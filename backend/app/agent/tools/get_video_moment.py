import base64

from claude_agent_sdk import tool

from ...config import IMAGES_DIR
from ...retrieval.index import get_index


@tool(
    "get_video_moment",
    "Show the user a moment from the official OmniPro 220 product video: the frame screenshot "
    "plus a player that starts at that timestamp. Use when a question relates to something the "
    "video demonstrates (frame_ids come from search_knowledge results with 'Video moment at').",
    {"frame_id": str},
)
async def get_video_moment(args):
    frame_id = args["frame_id"]
    moment = get_index().video_moments.get(frame_id)
    path = IMAGES_DIR / "video" / f"{frame_id}.jpg"
    if moment is None or not path.exists():
        known = ", ".join(sorted(get_index().video_moments)) or "(none ingested)"
        return {
            "content": [{
                "type": "text",
                "text": f"Unknown frame_id '{frame_id}'. Known video moments: {known}",
            }],
            "is_error": True,
        }
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {
        "content": [
            {"type": "image", "data": data, "mimeType": "image/jpeg"},
            {
                "type": "text",
                "text": f"Video moment at {moment['timestamp']} is now displayed to the user "
                        f"with a play-from-timestamp button. Caption: {moment['caption']}",
            },
        ]
    }

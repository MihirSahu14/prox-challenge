from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agent.turn import run_turn

router = APIRouter()


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    voice_meta: dict | None = None


@router.post("/api/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        run_turn(req.conversation_id, req.message, voice_meta=req.voice_meta),
        media_type="application/x-ndjson",
    )

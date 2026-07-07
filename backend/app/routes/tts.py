"""Optional premium TTS proxy (ElevenLabs).

Only active when ELEVENLABS_API_KEY is set in .env. The frontend asks
/api/voice-config which engine to use and falls back to browser
speechSynthesis when this is disabled or a request fails.
"""

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

router = APIRouter()

# Register -> ElevenLabs voice_settings. Stability down = more expressive;
# style up = more emotive delivery.
REGISTER_SETTINGS = {
    "calm": {"stability": 0.75, "similarity_boost": 0.75, "style": 0.15, "speed": 0.95},
    "warm": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.45, "speed": 1.0},
    "brisk": {"stability": 0.6, "similarity_boost": 0.75, "style": 0.3, "speed": 1.1},
    "neutral": {"stability": 0.6, "similarity_boost": 0.75, "style": 0.25, "speed": 1.0},
}


class TTSRequest(BaseModel):
    text: str
    register: str = "neutral"


@router.get("/api/voice-config")
async def voice_config():
    return {"tts": "elevenlabs" if ELEVENLABS_API_KEY else "browser"}


@router.post("/api/tts")
async def tts(req: TTSRequest):
    if not ELEVENLABS_API_KEY:
        raise HTTPException(404, "Premium TTS not configured")
    text = req.text[:4500]
    settings = REGISTER_SETTINGS.get(req.register, REGISTER_SETTINGS["neutral"])
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            json={
                "text": text,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": settings,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"TTS upstream error {resp.status_code}")
    return Response(content=resp.content, media_type="audio/mpeg")

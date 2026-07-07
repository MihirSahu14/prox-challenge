import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
load_dotenv(ROOT / ".env")

KB_DIR = ROOT / "backend" / "data" / "kb"
IMAGES_DIR = KB_DIR / "images"
SYSTEM_PROMPT_PATH = Path(__file__).parent / "agent" / "system_prompt.md"

AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5")
EMBED_MODEL = "all-MiniLM-L6-v2"

# Optional premium TTS. The app fully works without it (browser speechSynthesis
# fallback); with a key, voice replies use ElevenLabs and sound human.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel

# Optional access gate for hosted deployments (a hosted instance runs on the
# HOST'S API key). When set, credit-spending endpoints require a matching
# X-Access-Code header; the frontend prompts once and remembers it.
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")

# Built frontend, served by the backend in single-service hosting.
FRONTEND_DIST = ROOT / "frontend" / "dist"

from fastapi import APIRouter

router = APIRouter()

EXAMPLES = [
    "What's the duty cycle for MIG welding at 200A on 240V?",
    "I'm getting porosity in my flux-cored welds. What should I check?",
    "What polarity setup do I need for TIG welding? Which socket does the ground clamp go in?",
    "I'm a beginner welding 1/8\" mild steel outdoors — which process should I use?",
    "Walk me through loading a 2 lb wire spool for the first time.",
    "What wire speed should I use?",
    "Build me a settings calculator for MIG welding.",
]


@router.get("/api/examples")
async def examples():
    return {"examples": EXAMPLES}

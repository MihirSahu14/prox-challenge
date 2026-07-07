from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import IMAGES_DIR
from .routes.chat import router as chat_router
from .routes.examples import router as examples_router
from .routes.tts import router as tts_router

app = FastAPI(title="Vulcan OmniPro 220 Expert")


@app.on_event("startup")
async def warm_retrieval() -> None:
    # Load the embedding model + index at boot, not lazily inside the first
    # tool call — first load makes HuggingFace update-check requests that can
    # exhaust Windows socket buffers (WinError 10055) under a live request.
    from .retrieval.embed import embed_query
    from .retrieval.graph import get_graph
    from .retrieval.index import get_index

    get_index()
    get_graph()
    embed_query("warmup")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/kb-images", StaticFiles(directory=IMAGES_DIR), name="kb-images")

app.include_router(chat_router)
app.include_router(examples_router)
app.include_router(tts_router)


@app.get("/api/health")
async def health():
    return {"ok": True}

"""Lazy singleton around the local embedding model.

Two interchangeable backends producing MiniLM embeddings:
- sentence-transformers (torch) — default for local dev; also what built the
  committed embeddings.npy.
- fastembed (ONNX) — set EMBED_BACKEND=fastembed for memory-constrained
  hosting (Render free tier, 512MB): ~3x smaller footprint, no torch in the
  image. Same model weights exported to ONNX; cosine rankings are near-
  identical against the torch-built corpus (verified on the QA queries).
"""

import os

import numpy as np

from ..config import EMBED_MODEL

_model = None
_backend = os.environ.get("EMBED_BACKEND", "sentence-transformers")


def embed_query(text: str) -> np.ndarray:
    global _model
    if _backend == "fastembed":
        if _model is None:
            from fastembed import TextEmbedding

            _model = TextEmbedding(f"sentence-transformers/{EMBED_MODEL}")
        vec = np.asarray(next(iter(_model.embed([text]))), dtype="float32")
        return vec / np.linalg.norm(vec)
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model.encode([text], normalize_embeddings=True)[0]

"""Lazy singleton around the local sentence-transformers model."""

import numpy as np

from ..config import EMBED_MODEL

_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed_query(text: str) -> np.ndarray:
    return get_model().encode([text], normalize_embeddings=True)[0]

"""In-memory knowledge index: brute-force cosine search over the committed KB."""

import json
from pathlib import Path

import numpy as np

from ..config import KB_DIR
from .embed import embed_query

_index = None


class KnowledgeIndex:
    def __init__(self, kb_dir: Path):
        self.chunks = [
            json.loads(line)
            for line in (kb_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.embeddings = np.load(kb_dir / "embeddings.npy")
        figures_path = kb_dir / "figures.json"
        self.figures = {
            f["figure_id"]: f
            for f in (json.loads(figures_path.read_text(encoding="utf-8")) if figures_path.exists() else [])
        }
        video_path = kb_dir / "video_frames.json"
        self.video_moments = {
            m["frame_id"]: m
            for m in (json.loads(video_path.read_text(encoding="utf-8")) if video_path.exists() else [])
        }

    def search(self, query: str, top_k: int = 6, section_filter: str | None = None) -> list[dict]:
        q = embed_query(query)
        scores = self.embeddings @ q
        order = np.argsort(-scores)
        results = []
        for i in order:
            chunk = self.chunks[i]
            if section_filter and section_filter.lower() not in chunk["section"].lower():
                continue
            results.append({**chunk, "score": float(scores[i])})
            if len(results) >= top_k:
                break
        return results


def get_index() -> KnowledgeIndex:
    global _index
    if _index is None:
        _index = KnowledgeIndex(KB_DIR)
    return _index

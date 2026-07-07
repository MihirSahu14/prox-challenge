"""Keyword lookup + 1-hop expansion over the knowledge graph.

Complements embedding search: for cause/fix questions ("porosity in flux-cored
welds"), matched symptom nodes pull their causes and fixes as structured facts
even when those chunks wouldn't rank on cosine similarity alone.
"""

import json
import re
from pathlib import Path

from ..config import KB_DIR

_graph = None

STOPWORDS = {
    "the", "a", "an", "in", "on", "for", "of", "to", "my", "i", "is", "are",
    "with", "and", "or", "what", "which", "how", "do", "does", "should",
    "welding", "weld", "welds", "welder",  # too generic in this domain
}


class KnowledgeGraph:
    def __init__(self, kb_dir: Path):
        nodes_path = kb_dir / "graph_nodes.json"
        edges_path = kb_dir / "graph_edges.json"
        self.nodes: dict[str, dict] = {}
        self.out_edges: dict[str, list[dict]] = {}
        self.in_edges: dict[str, list[dict]] = {}
        if not nodes_path.exists():
            return
        for n in json.loads(nodes_path.read_text(encoding="utf-8")):
            self.nodes[n["id"]] = n
        for e in json.loads(edges_path.read_text(encoding="utf-8")):
            self.out_edges.setdefault(e["source"], []).append(e)
            self.in_edges.setdefault(e["target"], []).append(e)

    def _match_nodes(self, query: str, limit: int = 4) -> list[dict]:
        words = {w for w in re.findall(r"[a-z0-9]+", query.lower())} - STOPWORDS
        if not words:
            return []
        scored = []
        for node in self.nodes.values():
            node_words = set(re.findall(r"[a-z0-9]+", node["label"].lower()))
            node_words |= set(node["id"].split("-"))
            overlap = words & node_words
            if not overlap:
                continue
            # Overlap count dominates; coverage of the node's own label breaks
            # ties (so "Porosity" beats "Flux-Cored Welding" on a porosity
            # query); symptoms get a nudge — they're the natural entry point
            # for troubleshooting questions and carry the cause/fix edges.
            score = len(overlap) + len(overlap) / len(node_words)
            if node["type"] == "symptom":
                score += 0.5
            scored.append((score, node))
        scored.sort(key=lambda x: -x[0])
        return [n for _, n in scored[:limit]]

    def related_facts(self, query: str) -> str:
        """Human-readable related-knowledge lines for the matched subgraph."""
        matched = self._match_nodes(query)
        if not matched:
            return ""
        lines = []
        for node in matched:
            lines.append(
                f"- {node['label']} ({node['type']}, p.{node.get('page', '?')}): {node['description']}"
            )
            for e in self.in_edges.get(node["id"], []):
                src = self.nodes.get(e["source"])
                if src and e["relation"] == "causes":
                    lines.append(f"    <- caused by: {src['label']} — {src['description']}")
            for e in self.out_edges.get(node["id"], []):
                dst = self.nodes.get(e["target"])
                if not dst:
                    continue
                if e["relation"] == "fixed_by":
                    lines.append(f"    -> fix: {dst['label']} — {dst['description']}")
                elif e["relation"] == "applies_to":
                    lines.append(f"    (applies to {dst['label']})")
                elif e["relation"] == "causes":
                    lines.append(f"    -> can cause: {dst['label']}")
        return "\n".join(lines)


def get_graph() -> KnowledgeGraph:
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph(KB_DIR)
    return _graph

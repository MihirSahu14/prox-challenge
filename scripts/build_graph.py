"""Builds the lightweight knowledge graph from the vision-transcribed manual.

Extracts (via Claude structured outputs) a graph of:
    nodes: process | symptom | cause | fix | setting | component | spec
    edges: causes | fixed_by | requires | part_of | applies_to

from the sections where causal/relational knowledge lives (welding tips,
troubleshooting matrices, specifications, cable setup). Output:

    backend/data/kb/graph_nodes.json
    backend/data/kb/graph_edges.json

`search_knowledge` keyword-matches node labels and expands 1 hop so cause->fix
questions ("porosity in flux-cored welds") pull structured remedies even when
embedding similarity alone would miss them.

Usage: python scripts/build_graph.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "backend" / "data" / "kb"
CACHE = ROOT / "backend" / "data" / ".cache" / "graph"

MODEL = "claude-haiku-4-5"

# (label, doc, pages) groups extracted in separate calls, merged afterwards.
PAGE_GROUPS = [
    ("wire-welding-tips", "owner-manual.pdf", range(34, 38)),
    ("stick-tig-tips", "owner-manual.pdf", range(38, 41)),
    ("troubleshooting", "owner-manual.pdf", range(41, 46)),
    ("specs-and-polarity", "owner-manual.pdf", [7]),
    ("cable-setup", "quick-start-guide.pdf", [1, 2]),
]

SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "kebab-case slug"},
                    "type": {
                        "type": "string",
                        "enum": ["process", "symptom", "cause", "fix",
                                 "setting", "component", "spec"],
                    },
                    "label": {"type": "string"},
                    "description": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": ["id", "type", "label", "description", "page"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": ["causes", "fixed_by", "requires",
                                 "part_of", "applies_to"],
                    },
                },
                "required": ["source", "target", "relation"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nodes", "edges"],
    "additionalProperties": False,
}

PROMPT = """Extract a knowledge graph from this excerpt of the Vulcan OmniPro 220
welder documentation.

Rules:
- symptom nodes: observable problems (porosity, excessive spatter, burn-through,
  weak arc, wire birdnesting, welder won't start...).
- cause nodes: why a symptom happens (incorrect polarity, dirty workpiece,
  CTWD too long, wire feed too fast...).
- fix nodes: the corrective action, phrased as an instruction.
- Edge direction: cause --causes--> symptom; symptom --fixed_by--> fix;
  cause --fixed_by--> fix when the fix addresses the cause directly.
- process nodes: MIG, Flux-Cored, TIG, Stick. Use applies_to to scope a
  symptom/setting/spec to its process(es) whenever the text says so.
- setting/spec nodes for concrete machine facts (duty cycle ratings, polarity
  configuration per process, wire tension values, current ranges).
- Use applies_to edges to link settings/specs to their process.
- Slug ids: lowercase kebab-case, stable and descriptive (e.g. "porosity",
  "incorrect-polarity", "mig-duty-cycle-240v").
- Set page to the manual page the fact appears on (page markers are in the text).
- Extract exhaustively — every symptom/cause/fix row in troubleshooting tables.

TEXT:
{text}"""


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def extract_group(client, label: str, text: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    import hashlib
    key = hashlib.sha256(f"{label}||{text[:2000]}".encode()).hexdigest()[:32]
    cache_file = CACHE / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": PROMPT.format(text=text[:40000])}],
    )
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"group '{label}' hit max_tokens — split the page group further")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def main() -> None:
    load_dotenv(ROOT / ".env")
    client = anthropic.Anthropic()
    pages = json.loads((KB / "manual_pages.json").read_text(encoding="utf-8"))
    by_doc: dict[str, dict[int, str]] = {}
    for p in pages:
        by_doc.setdefault(p["doc"], {})[p["page"]] = p["text"]

    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()

    for label, doc, page_nums in PAGE_GROUPS:
        text = "\n\n".join(
            f"[page {n}]\n{by_doc[doc][n]}" for n in page_nums if n in by_doc.get(doc, {})
        )
        print(f"extracting {label} ({len(text)} chars)...")
        data = extract_group(client, label, text)
        for n in data["nodes"]:
            nid = slugify(n["id"])
            if nid not in nodes:
                nodes[nid] = {**n, "id": nid, "doc": doc}
        for e in data["edges"]:
            s, t = slugify(e["source"]), slugify(e["target"])
            if s != t:
                edges.add((s, t, e["relation"]))
        print(f"  +{len(data['nodes'])} nodes, +{len(data['edges'])} edges")

    # Drop edges pointing at nodes that were deduped away entirely.
    edge_list = [
        {"source": s, "target": t, "relation": r}
        for s, t, r in sorted(edges)
        if s in nodes and t in nodes
    ]

    (KB / "graph_nodes.json").write_text(
        json.dumps(list(nodes.values()), indent=1), encoding="utf-8")
    (KB / "graph_edges.json").write_text(
        json.dumps(edge_list, indent=1), encoding="utf-8")
    print(f"total: {len(nodes)} nodes, {len(edge_list)} edges")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()

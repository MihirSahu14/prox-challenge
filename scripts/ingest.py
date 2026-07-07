"""Knowledge-base ingestion pipeline for the Vulcan OmniPro 220 manuals.

Reads the PDFs in files/, produces the committed knowledge base under
backend/data/kb/:

    manual_pages.json   cleaned per-page text (markdown for vision-transcribed pages)
    images/*.png        cropped/full-page figures per figure_manifest.json
    figures.json        figure metadata + retrieval captions
    chunks.jsonl        text + image-caption chunks (one JSON object per line)
    embeddings.npy      float32, L2-normalized, row i <-> line i of chunks.jsonl

Claude vision (via ANTHROPIC_API_KEY in .env) is used for two things:
  - transcribing structurally complex pages (tables/infographics) to markdown,
    because raw text extraction garbles multi-column layouts
  - writing search-optimized captions for each figure

Both are cached under backend/data/.cache/vision/ keyed by content hash, so
re-runs don't re-spend API calls. --skip-vision falls back to raw text and
manifest titles (useful before an API key is configured).

Usage:
    python scripts/ingest.py [--skip-vision] [--force] [--skip-embed]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import fitz
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
KB = ROOT / "backend" / "data" / "kb"
IMAGES = KB / "images"
CACHE = ROOT / "backend" / "data" / ".cache" / "vision"
MANIFEST_PATH = KB / "figure_manifest.json"

VISION_MODEL = "claude-haiku-4-5"

# Owner-manual section map (1-indexed, inclusive), from the TOC on page 2.
SECTIONS = [
    ("Safety", 2, 6),
    ("Specifications", 7, 7),
    ("Controls", 8, 9),
    ("MIG / Flux-Cored Wire Welding", 10, 23),
    ("TIG / Stick Welding", 24, 33),
    ("Welding Tips", 34, 40),
    ("Maintenance", 41, 45),
    ("Parts List and Diagram", 46, 47),
    ("Warranty", 48, 48),
]

# Pages whose raw text extraction is unreliable (multi-column tables, infographics)
# -> transcribe with Claude vision instead.
COMPLEX_PAGES = {
    # 7: spec tables; 8-9: controls; 14/16/17/21: wire-install & settings
    # tables; 25/27: TIG/Stick setup (pathological 100K+-char extraction);
    # 34-40: welding tips incl. weld diagnosis photos; 41-45: maintenance +
    # troubleshooting matrices (two-column cause/fix tables garble badly);
    # 46-47: parts list/diagram
    "owner-manual.pdf": {7, 8, 9, 14, 16, 17, 21, 25, 27,
                         34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47},
    "quick-start-guide.pdf": {1, 2},
    "selection-chart.pdf": {1},
}

DOC_SECTIONS = {
    "quick-start-guide.pdf": "Quick Start Guide",
    "selection-chart.pdf": "Welding Process Selection Chart",
}


def section_for(doc: str, page: int) -> str:
    if doc == "owner-manual.pdf":
        for name, start, end in SECTIONS:
            if start <= page <= end:
                return name
        return "Owner's Manual"
    return DOC_SECTIONS.get(doc, doc)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    replacements = {
        " ": " ", "’": "'", "‘": "'",
        "“": '"', "”": '"', "–": "-", "—": "-",
        "ﬁ": "fi", "ﬂ": "fl", "®": "(R)",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Collapse runs of spaces from multi-column layouts; keep newlines.
    text = re.sub(r"[ \t]{3,}", "  ", text)
    return text


def cache_key(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()[:32]


def cached_vision_call(client, key: str, prompt: str, png_bytes: bytes, force: bool) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{key}.json"
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8"))["text"]
    response = client.messages.create(
        model=VISION_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": base64.standard_b64encode(png_bytes).decode(),
                }},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    cache_file.write_text(json.dumps({"text": text}), encoding="utf-8")
    return text


TRANSCRIBE_PROMPT = """Transcribe this welding-manual page into clean Markdown.

Rules:
- Reproduce ALL text content faithfully. Use the image to resolve column order
  in tables -- render every table as a proper Markdown table with correct
  column alignment (e.g. keep 120V and 240V spec columns separate).
- Preserve headings, numbered steps, and warnings as Markdown structure.
- For diagrams/illustrations, add a short parenthetical note describing what
  the diagram shows and its labeled callouts, e.g.
  "(Diagram: front panel showing Home Button, LCD Display, ...)".
- Output ONLY the Markdown, no preamble.

The raw (possibly garbled) text extraction is below for reference:

{raw_text}"""

CAPTION_PROMPT = """This image is a figure from the Vulcan OmniPro 220 welder's documentation,
titled "{title}". Write a retrieval-optimized description in 2-4 sentences:
name every labeled component, callout number, socket, or control visible; if
it's a diagnostic photo, describe the weld symptom shown; if it's a chart,
summarize what it lets the reader decide or look up. Then on a final line
write "KEYWORDS:" followed by 8-15 comma-separated search keywords.
Output only the description and keyword line."""


def extract_pages(client, skip_vision: bool, force: bool) -> list[dict]:
    """Step 1: per-page text, vision-transcribed where raw extraction garbles."""
    pages = []
    for pdf_path in sorted(FILES.glob("*.pdf")):
        doc_name = pdf_path.name
        doc = fitz.open(pdf_path)
        complex_pages = COMPLEX_PAGES.get(doc_name, set())
        for i, page in enumerate(doc, start=1):
            raw = normalize(page.get_text("text", sort=True))
            text = raw
            method = "raw"
            if i in complex_pages and not skip_vision and client is not None:
                pix = page.get_pixmap(dpi=150)
                key = cache_key("transcribe", doc_name, str(i), raw[:500])
                text = cached_vision_call(
                    client, key, TRANSCRIBE_PROMPT.format(raw_text=raw[:6000]),
                    pix.tobytes("png"), force,
                )
                method = "vision"
            pages.append({
                "doc": doc_name,
                "page": i,
                "section": section_for(doc_name, i),
                "method": method,
                "text": text,
            })
            print(f"  {doc_name} p{i:02d} [{method}] {len(text)} chars")
        doc.close()
    (KB / "manual_pages.json").write_text(
        json.dumps(pages, indent=1), encoding="utf-8")
    return pages


def extract_figures(client, skip_vision: bool, force: bool) -> list[dict]:
    """Step 2+3: crop figures per manifest, caption via Claude vision."""
    if not MANIFEST_PATH.exists():
        print("  no figure_manifest.json yet -- skipping figures")
        return []
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    IMAGES.mkdir(parents=True, exist_ok=True)
    figures = []
    docs: dict[str, fitz.Document] = {}
    for entry in manifest:
        doc_name, page_no = entry["source"], entry["page"]
        if doc_name not in docs:
            docs[doc_name] = fitz.open(FILES / doc_name)
        page = docs[doc_name][page_no - 1]
        r = page.rect
        bbox = entry.get("bbox_pct")
        clip = (
            fitz.Rect(
                r.x0 + bbox[0] * r.width, r.y0 + bbox[1] * r.height,
                r.x0 + bbox[2] * r.width, r.y0 + bbox[3] * r.height,
            )
            if bbox else None
        )
        out_path = IMAGES / f"{entry['figure_id']}.png"
        if not out_path.exists() or force:
            pix = page.get_pixmap(clip=clip, dpi=200 if bbox else 150)
            pix.save(out_path)
        caption, keywords = entry.get("title", entry["figure_id"]), []
        if not skip_vision and client is not None:
            png_bytes = out_path.read_bytes()
            key = cache_key("caption", entry["figure_id"],
                            hashlib.sha256(png_bytes).hexdigest()[:16])
            result = cached_vision_call(
                client, key,
                CAPTION_PROMPT.format(title=entry.get("title", entry["figure_id"])),
                png_bytes, force,
            )
            if "KEYWORDS:" in result:
                caption, kw = result.rsplit("KEYWORDS:", 1)
                caption = caption.strip()
                keywords = [k.strip() for k in kw.split(",") if k.strip()]
            else:
                caption = result.strip()
        figures.append({
            **entry,
            "section": section_for(doc_name, page_no),
            "caption": caption,
            "keywords": keywords,
            "image": f"images/{entry['figure_id']}.png",
        })
        print(f"  figure {entry['figure_id']} [caption: {len(caption)} chars]")
    for d in docs.values():
        d.close()
    (KB / "figures.json").write_text(
        json.dumps(figures, indent=1), encoding="utf-8")
    return figures


def chunk_pages(pages: list[dict], target_chars: int = 1400, overlap_chars: int = 200) -> list[dict]:
    """Step 4: split page text into ~300-400 token chunks on paragraph boundaries."""
    chunks = []
    for p in pages:
        paras = [s.strip() for s in p["text"].split("\n\n") if s.strip()]
        if not paras:
            continue
        buf: list[str] = []
        size = 0
        def flush():
            nonlocal buf, size
            if buf:
                text = "\n\n".join(buf)
                chunks.append({
                    "id": f"{Path(p['doc']).stem}_p{p['page']:02d}_c{sum(1 for c in chunks if c['doc'] == p['doc'] and c['page_start'] == p['page'])}",
                    "doc": p["doc"], "section": p["section"],
                    "page_start": p["page"], "page_end": p["page"],
                    "type": "text", "text": text,
                })
                # keep tail as overlap
                tail = text[-overlap_chars:]
                buf, size = [tail], len(tail)
        for para in paras:
            if size + len(para) > target_chars and size > overlap_chars:
                flush()
            buf.append(para)
            size += len(para)
        if size > overlap_chars or not any(
            c["doc"] == p["doc"] and c["page_start"] == p["page"] for c in chunks
        ):
            text = "\n\n".join(buf)
            chunks.append({
                "id": f"{Path(p['doc']).stem}_p{p['page']:02d}_c{sum(1 for c in chunks if c['doc'] == p['doc'] and c['page_start'] == p['page'])}",
                "doc": p["doc"], "section": p["section"],
                "page_start": p["page"], "page_end": p["page"],
                "type": "text", "text": text,
            })
    return chunks


def video_chunks() -> list[dict]:
    """Video moments (from scripts/ingest_video.py) join the same index."""
    path = KB / "video_frames.json"
    if not path.exists():
        return []
    moments = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "id": f"vid_{m['frame_id']}",
            "doc": m["video_title"], "section": "Product Video",
            "page_start": 0, "page_end": 0,
            "type": "video_frame", "frame_id": m["frame_id"],
            "timestamp": m["timestamp"],
            "text": f"Video moment at {m['timestamp']}: {m['caption']}"
                    + (f" Keywords: {', '.join(m['keywords'])}" if m["keywords"] else ""),
        }
        for m in moments
    ]


def figure_chunks(figures: list[dict]) -> list[dict]:
    return [
        {
            "id": f"fig_{f['figure_id']}",
            "doc": f["source"], "section": f["section"],
            "page_start": f["page"], "page_end": f["page"],
            "type": "image_caption", "figure_id": f["figure_id"],
            "text": f"{f.get('title', f['figure_id'])}. {f['caption']}"
                    + (f" Keywords: {', '.join(f['keywords'])}" if f["keywords"] else ""),
        }
        for f in figures
    ]


def embed_chunks(chunks: list[dict]) -> None:
    """Step 6: local embeddings + committed .npy index."""
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [f"{c['section']}: {c['text']}" for c in chunks]
    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    np.save(KB / "embeddings.npy", emb.astype("float32"))
    print(f"  embedded {len(chunks)} chunks -> {emb.shape}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-vision", action="store_true",
                        help="skip Claude vision calls (raw text + manifest titles only)")
    parser.add_argument("--skip-embed", action="store_true",
                        help="skip the embedding step")
    parser.add_argument("--force", action="store_true",
                        help="ignore caches, redo everything")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    client = None
    if not args.skip_vision:
        import os
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key == "your-api-key-here":
            print("WARNING: no real ANTHROPIC_API_KEY in .env -- falling back to --skip-vision")
            args.skip_vision = True
        else:
            import anthropic
            client = anthropic.Anthropic()

    KB.mkdir(parents=True, exist_ok=True)

    print("[1/4] extracting pages...")
    pages = extract_pages(client, args.skip_vision, args.force)

    print("[2/4] extracting + captioning figures...")
    figures = extract_figures(client, args.skip_vision, args.force)

    print("[3/4] chunking...")
    chunks = chunk_pages(pages) + figure_chunks(figures) + video_chunks()
    with (KB / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  {len(chunks)} chunks written")

    if not args.skip_embed:
        print("[4/4] embedding...")
        embed_chunks(chunks)
    print("done")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()

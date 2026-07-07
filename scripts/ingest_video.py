"""Video ingestion: turn the product video into timestamped, searchable moments.

Pipeline:
  1. Download the YouTube video once (yt-dlp, <=480p mp4, cached in .cache/).
  2. Sample a frame every SAMPLE_EVERY_S seconds with OpenCV.
  3. Drop near-duplicate frames (mean absolute pixel difference) so a static
     talking-head shot doesn't produce 40 identical moments.
  4. Caption each kept frame with Claude vision (timestamped, retrieval-tuned,
     content-hash cached like the manual figures).
  5. Write backend/data/kb/video_frames.json + frames as JPEGs under
     backend/data/kb/images/video/ (served by the existing /kb-images mount).

scripts/ingest.py picks up video_frames.json (if present) and embeds the
captions as type="video_frame" chunks in the same index as the manual, so one
semantic search covers text, figures, AND video moments.

Usage: python scripts/ingest_video.py [--force]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import cv2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "backend" / "data" / "kb"
FRAMES_DIR = KB / "images" / "video"
CACHE = ROOT / "backend" / "data" / ".cache"
VIDEO_CACHE = CACHE / "video"
CAPTION_CACHE = CACHE / "vision"

VIDEO_ID = "kxGDoGcnhBw"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
VIDEO_TITLE = "Vulcan OmniPro 220 product overview video"

MODEL = "claude-haiku-4-5"
SAMPLE_EVERY_S = 4.0
DIFF_THRESHOLD = 18.0  # mean abs pixel diff below this = near-duplicate, skip
MAX_FRAMES = 60

CAPTION_PROMPT = """This is a frame at {timestamp} from the Vulcan OmniPro 220 welder's official
product/overview video. Describe what this moment SHOWS or DEMONSTRATES in 1-3
sentences optimized for search: name any machine parts, controls, cables,
welding processes, on-screen text, or actions being performed. If it's just a
title card or talking head with no product content, reply exactly "SKIP".
Then, unless skipping, on a final line write "KEYWORDS:" followed by 6-12
comma-separated search keywords."""


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def download_video(force: bool) -> Path:
    VIDEO_CACHE.mkdir(parents=True, exist_ok=True)
    out = VIDEO_CACHE / f"{VIDEO_ID}.mp4"
    if out.exists() and not force:
        print(f"  using cached video {out.name}")
        return out
    import yt_dlp

    opts = {
        "format": "best[height<=480][ext=mp4]/best[height<=480]/best",
        "outtmpl": str(out),
        "quiet": True,
        "no_warnings": True,
    }
    print(f"  downloading {VIDEO_URL} ...")
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([VIDEO_URL])
    return out


def sample_frames(video_path: Path) -> list[tuple[float, "cv2.Mat"]]:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps
    print(f"  video: {fmt_ts(duration)} @ {fps:.1f}fps")

    kept: list[tuple[float, "cv2.Mat"]] = []
    prev_small = None
    t = 0.0
    while t < duration and len(kept) < MAX_FRAMES:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
        if prev_small is not None:
            diff = float(cv2.absdiff(small, prev_small).mean())
            if diff < DIFF_THRESHOLD:
                t += SAMPLE_EVERY_S
                continue
        prev_small = small
        kept.append((t, frame))
        t += SAMPLE_EVERY_S
    cap.release()
    print(f"  kept {len(kept)} distinct frames")
    return kept


def caption_frame(client, frame_id: str, jpg_bytes: bytes, timestamp: str, force: bool) -> str:
    CAPTION_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(b"vidcap||" + jpg_bytes[:4096] + timestamp.encode()).hexdigest()[:32]
    cache_file = CAPTION_CACHE / f"{key}.json"
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8"))["text"]
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpg_bytes).decode(),
                }},
                {"type": "text", "text": CAPTION_PROMPT.format(timestamp=timestamp)},
            ],
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    cache_file.write_text(json.dumps({"text": text}), encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    import anthropic
    client = anthropic.Anthropic()

    print("[1/3] downloading video...")
    video_path = download_video(args.force)

    print("[2/3] sampling frames...")
    frames = sample_frames(video_path)

    print("[3/3] captioning...")
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    moments = []
    for t, frame in frames:
        ts = fmt_ts(t)
        frame_id = f"video_{int(t):04d}s"
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            continue
        jpg_bytes = jpg.tobytes()
        result = caption_frame(client, frame_id, jpg_bytes, ts, args.force)
        if result.strip().upper().startswith("SKIP"):
            print(f"  {ts} SKIP")
            continue
        caption, keywords = result, []
        if "KEYWORDS:" in result:
            caption, kw = result.rsplit("KEYWORDS:", 1)
            keywords = [k.strip() for k in kw.split(",") if k.strip()]
        (FRAMES_DIR / f"{frame_id}.jpg").write_bytes(jpg_bytes)
        moments.append({
            "frame_id": frame_id,
            "t_seconds": int(t),
            "timestamp": ts,
            "video_id": VIDEO_ID,
            "video_title": VIDEO_TITLE,
            "youtube_url": f"{VIDEO_URL}&t={int(t)}s",
            "caption": caption.strip(),
            "keywords": keywords,
            "image": f"images/video/{frame_id}.jpg",
        })
        print(f"  {ts} ok ({len(caption)} chars)")

    (KB / "video_frames.json").write_text(json.dumps(moments, indent=1), encoding="utf-8")
    print(f"wrote {len(moments)} video moments -> kb/video_frames.json")
    print("now re-run: python scripts/ingest.py  (to fold video chunks into the index)")


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    main()

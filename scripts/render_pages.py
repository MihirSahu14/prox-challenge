"""One-off helper: rasterize every page of every source PDF to PNG.

Used for visually skimming pages while hand-authoring figure_manifest.json.
Output goes to backend/data/.cache/pages/ (gitignored).

Usage: python scripts/render_pages.py
"""

from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
OUT = ROOT / "backend" / "data" / ".cache" / "pages"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pdf_path in sorted(FILES.glob("*.pdf")):
        doc = fitz.open(pdf_path)
        stem = pdf_path.stem
        for i, page in enumerate(doc, start=1):
            out_path = OUT / f"{stem}_p{i:02d}.png"
            if out_path.exists():
                continue
            pix = page.get_pixmap(dpi=150)
            pix.save(out_path)
            print(f"wrote {out_path.relative_to(ROOT)} ({pix.width}x{pix.height})")
        doc.close()
    print("done")


if __name__ == "__main__":
    main()

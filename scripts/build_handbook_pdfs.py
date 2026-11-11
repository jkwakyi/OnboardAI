"""Generate the handbook PDFs from the handbook TXT files.

The TXT files in data/handbook/txt are the source of truth. This script
renders each one to data/handbook/pdf with the same stem, so the two formats
can never drift apart.

Run it from anywhere:

    python scripts/build_handbook_pdfs.py

A monospaced font is used and each source line is drawn as a single line, so
text extracted back out of the PDF matches the TXT closely. That matters:
POST /api/documents accepts both formats and the extracted sections should be
equivalent whichever one an HR administrator uploads.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

REPO_ROOT = Path(__file__).resolve().parents[1]
TXT_DIR = REPO_ROOT / "data" / "handbook" / "txt"
PDF_DIR = REPO_ROOT / "data" / "handbook" / "pdf"

FONT_NAME = "Courier"
FONT_SIZE = 9
LEADING = 12
MARGIN_LEFT = 54
MARGIN_TOP = 54
MARGIN_BOTTOM = 54


def _lines_per_page(page_height: float) -> int:
    """How many lines of text fit on one page."""
    usable = page_height - MARGIN_TOP - MARGIN_BOTTOM
    return int(usable // LEADING)


def render(txt_path: Path, pdf_path: Path) -> int:
    """Render one TXT file to PDF. Returns the page count."""
    lines = txt_path.read_text(encoding="utf-8").splitlines()

    page_width, page_height = LETTER
    pdf = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    pdf.setTitle(txt_path.stem)
    pdf.setAuthor("Larkfield Systems (fictional)")
    pdf.setSubject("Synthetic HR handbook for OnboardAI testing")

    capacity = _lines_per_page(page_height)
    pages = 0
    for start in range(0, len(lines), capacity):
        pdf.setFont(FONT_NAME, FONT_SIZE)
        y = page_height - MARGIN_TOP
        for line in lines[start : start + capacity]:
            # drawString ignores tabs, so expand them first.
            pdf.drawString(MARGIN_LEFT, y, line.expandtabs(4))
            y -= LEADING
        pdf.showPage()
        pages += 1

    pdf.save()
    return pages


def main() -> int:
    if not TXT_DIR.is_dir():
        print(f"No handbook source at {TXT_DIR}", file=sys.stderr)
        return 1

    sources = sorted(TXT_DIR.glob("*.txt"))
    if not sources:
        print(f"No .txt files in {TXT_DIR}", file=sys.stderr)
        return 1

    PDF_DIR.mkdir(parents=True, exist_ok=True)

    for txt_path in sources:
        pdf_path = PDF_DIR / f"{txt_path.stem}.pdf"
        pages = render(txt_path, pdf_path)
        print(f"{txt_path.name} -> {pdf_path.name} ({pages} pages)")

    print(f"\n{len(sources)} documents written to {PDF_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

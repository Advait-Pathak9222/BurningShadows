"""Render the submission documents to PDF and stamp running footers on them.

Chromium prints the HTML, which gives full control over typography and page breaks but
supports no CSS margin boxes, so the page numbers are drawn afterwards as an overlay. The
cover is left unstamped.

    python submission/build.py            builds both documents
    python submission/build.py solution   builds one
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]

DOCUMENTS = {
    "solution": ("solution.html", "ControlPlane_Detailed_Solution.pdf",
                 "ControlPlane  .  Detailed Solution Document"),
    "proposal": ("proposal.html", "ControlPlane_Business_Proposal.pdf",
                 "ControlPlane  .  Business Proposal"),
}

INK = Color(0.09, 0.07, 0.12)
MUTED = Color(0.42, 0.39, 0.47)
RULE = Color(0.89, 0.87, 0.93)


def find_chrome() -> Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("chrome") or shutil.which("chromium")
    if found:
        return Path(found)
    raise SystemExit("No Chromium browser found to print with.")


def print_html(html: Path, out: Path) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                str(find_chrome()),
                "--headless",
                "--disable-gpu",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                "--print-to-pdf-no-header",
                f"--print-to-pdf={out}",
                "--virtual-time-budget=20000",
                html.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def stamp(pdf: Path, label: str) -> None:
    """Draw a footer rule, the document label and a page number on every page but the cover."""
    reader = PdfReader(str(pdf))
    total = len(reader.pages)
    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if index > 1:
            # Read the size off the page itself, so a landscape figure page is stamped
            # along its own bottom edge rather than the portrait one.
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            buffer = io.BytesIO()
            pen = canvas.Canvas(buffer, pagesize=(width, height))
            pen.setStrokeColor(RULE)
            pen.setLineWidth(0.6)
            pen.line(45, 34, width - 45, 34)
            pen.setFont("Helvetica", 8)
            pen.setFillColor(MUTED)
            pen.drawString(45, 24, label)
            pen.setFont("Helvetica-Bold", 8)
            pen.setFillColor(INK)
            pen.drawRightString(width - 45, 24, f"Page {index} of {total}")
            pen.save()
            buffer.seek(0)
            page.merge_page(PdfReader(buffer).pages[0])
        writer.add_page(page)
    with pdf.open("wb") as handle:
        writer.write(handle)


def build(key: str) -> None:
    source, target, label = DOCUMENTS[key]
    html, out = HERE / source, HERE / target
    if not html.exists():
        raise SystemExit(f"missing {html}")
    print_html(html, out)
    stamp(out, label)
    pages = len(PdfReader(str(out)).pages)
    print(f"{target}  {pages} pages  {out.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    keys = sys.argv[1:] or list(DOCUMENTS)
    for name in keys:
        build(name)

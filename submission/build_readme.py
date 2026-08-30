"""Render README.md to a PDF that matches the other two submission documents.

The README is the canonical source. This only wraps it in the shared print stylesheet so a
reviewer can upload one file, and it rewrites repository relative image paths so the
diagrams resolve when Chromium prints from the submission folder.
"""

from __future__ import annotations

import re

import markdown
from build import DOCUMENTS, HERE, print_html, stamp
from pypdf import PdfReader

REPO = HERE.parent
OUT_HTML = HERE / "readme.html"
OUT_PDF = HERE / "ControlPlane_README.pdf"

SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ControlPlane README</title>
<link rel="stylesheet" href="assets/style.css">
<style>
  body {{ font-size: 9.8pt; }}
  h1 {{ display: none; }}
  h2 {{ font-size: 13pt; margin-top: 13pt; break-before: auto; }}
  h2:first-of-type {{ margin-top: 0; }}
  h3 {{ font-size: 10.6pt; }}
  table {{ font-size: 8.6pt; }}
  td, th {{ padding: 3.4pt 5pt; }}
  img {{ max-width: 100%; height: auto; }}
  p img {{ display: block; margin: 6pt auto; }}
  blockquote {{ border-left: 2.6pt solid var(--accent); background: var(--panel);
               margin: 7pt 0; padding: 6pt 9pt; }}
  blockquote p:last-child {{ margin-bottom: 0; }}
  div[align="center"] p:has(img) {{ text-align: center; }}
  .badges {{ display: none; }}
</style></head><body>
<div class="cover" style="height:auto;break-after:auto;padding-bottom:8mm;
     border-bottom:1.6pt solid var(--ink);margin-bottom:9mm">
  <div class="kicker">Accenture Innovation Challenge 2026 . Round 2 . Track 1</div>
  <div class="brand" style="font-size:32pt;margin-top:5mm">ControlPlane</div>
  <div class="doctype" style="font-size:14pt">Repository README</div>
  <div class="rule"></div>
  <p class="lede" style="font-size:10.6pt;margin-top:6mm">
    An assurance gateway that decides how much checking each AI answer is worth, and proves what it
    decided. This document is the repository README, rendered for upload.
    Source github.com/Advait&#8209;Pathak9222/BurningShadows
  </p>
</div>
{body}
</body></html>
"""


def build() -> None:
    text = (REPO / "README.md").read_text(encoding="utf-8")

    # The centred badge block is navigation, not content, so it goes.
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)\s*", "", text)
    # Drop the duplicated title, since the cover above already carries it.
    text = text.replace("# ControlPlane\n", "", 1)

    body = markdown.markdown(text, extensions=["tables", "fenced_code", "md_in_html"])
    # Repository relative paths have to resolve from submission/.
    body = body.replace('src="docs/images/', 'src="../docs/images/')

    OUT_HTML.write_text(SHELL.format(body=body), encoding="utf-8", newline="\n")
    print_html(OUT_HTML, OUT_PDF)
    stamp(OUT_PDF, "ControlPlane  .  Repository README")
    pages = len(PdfReader(str(OUT_PDF)).pages)
    print(f"{OUT_PDF.name}  {pages} pages  {OUT_PDF.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    assert DOCUMENTS  # imported for the shared chrome and stamping helpers
    build()

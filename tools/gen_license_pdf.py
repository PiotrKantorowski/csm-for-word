#!/usr/bin/env python3
"""Generuje LICENSE.pdf z LICENSE.txt.

Format:
- tytuł (pierwsza linia) + podtytuł (wersja)
- nagłówek z danymi kancelarii
- "§ N. NAGŁÓWEK" jako pogrubione nagłówki sekcji
- pozostałe wiersze jako zwykłe akapity
- separator poziomy (HR) w miejscu linii "===..."

Uruchomienie: python tools/gen_license_pdf.py
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "LICENSE.txt"
OUT = ROOT / "LICENSE.pdf"

# Wbudowane fonty PDF (Helvetica) nie zawierają polskich znaków — używamy
# TrueType z pełnym zestawem glifów. Arial jest obecny na każdym Windows
# (CSM to dodatek do Worda dla Windows); DejaVu jako fallback.
_FONT_CANDIDATES = [
    ("BodyFont", "BodyFont-Bold", "C:/Windows/Fonts/arial.ttf",
     "C:/Windows/Fonts/arialbd.ttf"),
]


def _register_fonts() -> tuple[str, str]:
    for regular, bold, reg_path, bold_path in _FONT_CANDIDATES:
        if Path(reg_path).exists() and Path(bold_path).exists():
            pdfmetrics.registerFont(TTFont(regular, reg_path))
            pdfmetrics.registerFont(TTFont(bold, bold_path))
            return regular, bold
    # Fallback: wbudowany Vera z reportlab (obsługuje polskie znaki)
    import reportlab
    fonts = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("BodyFont", str(fonts / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("BodyFont-Bold", str(fonts / "VeraBd.ttf")))
    return "BodyFont", "BodyFont-Bold"

SEP_RE = re.compile(r"^=+\s*$")
SECTION_RE = re.compile(r"^§\s*\d+\.\s")


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def build() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    regular, bold = _register_fonts()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CsmTitle", parent=styles["Title"], fontName=bold,
        fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "CsmSubtitle", parent=styles["Normal"], fontName=regular,
        fontSize=10, leading=13,
        alignment=TA_CENTER, textColor="#555555", spaceAfter=10,
    )
    header_style = ParagraphStyle(
        "CsmHeader", parent=styles["Normal"], fontName=regular,
        fontSize=9.5, leading=13,
        alignment=TA_CENTER, textColor="#333333",
    )
    section_style = ParagraphStyle(
        "CsmSection", parent=styles["Normal"], fontName=bold,
        fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "CsmBody", parent=styles["Normal"], fontName=regular,
        fontSize=9.5, leading=13,
        alignment=TA_JUSTIFY, spaceAfter=5,
    )

    story: list = []

    # Tytuł + wersja (linie 1-2)
    story.append(Paragraph(_esc(lines[0].strip()), title_style))
    if len(lines) > 1 and lines[1].strip():
        story.append(Paragraph(_esc(lines[1].strip()), subtitle_style))

    # Reszta nagłówka aż do pierwszego separatora — dane kancelarii
    idx = 2
    header_buf: list[str] = []
    while idx < len(lines) and not SEP_RE.match(lines[idx]):
        if lines[idx].strip():
            header_buf.append(_esc(lines[idx].strip()))
        idx += 1
    if header_buf:
        story.append(Paragraph("<br/>".join(header_buf), header_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.8, color="#888888",
                            spaceBefore=6, spaceAfter=8))

    # Ciało: akapity oddzielone pustymi liniami; separatory -> HR
    para_buf: list[str] = []

    def flush() -> None:
        if not para_buf:
            return
        text = " ".join(s.strip() for s in para_buf)
        style = section_style if SECTION_RE.match(text) else body_style
        story.append(Paragraph(_esc(text), style))
        para_buf.clear()

    for line in lines[idx + 1 :]:
        if SEP_RE.match(line):
            flush()
            story.append(HRFlowable(width="100%", thickness=0.6,
                                    color="#bbbbbb", spaceBefore=4,
                                    spaceAfter=6))
        elif not line.strip():
            flush()
        else:
            para_buf.append(line)
    flush()

    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title="Licencja Otwarta CSM",
    )
    doc.build(story)
    print(f"Zapisano {OUT} ({OUT.stat().st_size} bajtów)")


if __name__ == "__main__":
    build()

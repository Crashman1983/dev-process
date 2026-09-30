#!/usr/bin/env python3
"""build_overview_pdf — docs/UEBERBLICK.md as the designed PDF, in one run.

    python3 tools/build_overview_pdf.py [--out docs/Entwicklungsprozess-mit-KI-Agenten.pdf]

The PDF had been built by hand once and then stood still for ten releases while
the text moved on. This script rebuilds it from the Markdown: pandoc makes the
Word document, python-docx gives it the design (title page with the mark, green
chapter headings, a callout under each chapter heading, quiet tables, running
header and "Seite N" from the first text page), LibreOffice renders the PDF.

Needs: pandoc, LibreOffice (`soffice`), the Carlito font, and the Python packages
python-docx and cairosvg (not project dependencies — install them where you run
this). The page count and the text of every chapter are printed at the end, so a
rebuild can be compared with the previous one.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cairosvg
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/UEBERBLICK.md"
MARK = ROOT / "docs/assets/mark.svg"
DEFAULT_OUT = ROOT / "docs/Entwicklungsprozess-mit-KI-Agenten.pdf"

GREEN = RGBColor(0x1E, 0x6B, 0x45)
GREEN_HEX = "1E6B45"
TINT_HEX = "EAF3EC"
RULE_HEX = "C9B458"
TEXT = RGBColor(0x33, 0x33, 0x33)
GREY = RGBColor(0x6B, 0x6B, 0x6B)
FONT = "Carlito"
RUNNING_RIGHT = "Prinzipien, Mechanik, Weg in die Fläche"


def _prepare(md: str) -> tuple[str, dict]:
    """Split the title block off the Markdown: pandoc gets the chapters, the title page
    is built from the fields here. The PDF link and the setup pointers are web-only."""
    lines = md.splitlines()
    title = next(ln[2:].strip() for ln in lines if ln.startswith("# "))
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## "))
    head = [ln for ln in lines[:start] if ln.strip() and not ln.startswith(("<p", "# ", ">"))]
    meta = {
        "title": title,
        "subtitle": head[0].strip("*"),
        "kicker": head[1],
        "version": head[2],
        "link": head[3],
        "intro": head[4],
    }
    return "\n".join(lines[start:]) + "\n", meta


def _border(element, side: str, color: str, size: int = 8, space: int = 4) -> None:
    ppr = element.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    edge = OxmlElement(f"w:{side}")
    for key, value in (("val", "single"), ("sz", str(size)), ("space", str(space)), ("color", color)):
        edge.set(qn(f"w:{key}"), value)
    borders.append(edge)


def _shade(element_pr, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    element_pr.append(shd)


def _cell_borders(cell, bottom: str | None) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "right", "bottom"):
        edge = OxmlElement(f"w:{side}")
        if side == "bottom" and bottom:
            edge.set(qn("w:val"), "single")
            edge.set(qn("w:sz"), "4")
            edge.set(qn("w:color"), bottom)
        else:
            edge.set(qn("w:val"), "nil")
        borders.append(edge)
    tcpr.append(borders)


def _field(run, instruction: str) -> None:
    for kind, text in (("begin", None), (None, instruction), ("end", None)):
        if kind:
            node = OxmlElement("w:fldChar")
            node.set(qn("w:fldCharType"), kind)
        else:
            node = OxmlElement("w:instrText")
            node.set(qn("xml:space"), "preserve")
            node.text = text
        run._r.append(node)


def _style(doc, name: str):
    """A style by its written name — python-docx's lookup lower-cases built-in names
    ("heading 1"), pandoc writes them capitalised ("Heading 1")."""
    return next((s for s in doc.styles if s.name == name), None)


def _style_fonts(doc) -> None:
    for style in doc.styles:
        if style.type == 1:  # paragraph
            style.font.name = FONT
            rpr = style.element.get_or_add_rPr()
            fonts = rpr.find(qn("w:rFonts"))
            if fonts is None:
                fonts = OxmlElement("w:rFonts")
                rpr.append(fonts)
            for key in ("ascii", "hAnsi", "cs", "eastAsia"):
                fonts.set(qn(f"w:{key}"), FONT)
    body = _style(doc, "Normal")
    body.font.size = Pt(10)
    body.font.color.rgb = TEXT
    for name in ("Body Text", "First Paragraph", "Compact"):
        style = _style(doc, name)
        if style is not None:
            style.font.size = Pt(10)
            style.font.color.rgb = TEXT
            style.paragraph_format.space_after = Pt(6)
            style.paragraph_format.line_spacing = 1.15
    for name, size in (("Heading 1", 18), ("Heading 2", 12.5)):
        style = _style(doc, name)
        style.font.size = Pt(size)
        style.font.bold = name == "Heading 2"
        style.font.color.rgb = GREEN
        style.paragraph_format.space_before = Pt(18 if name == "Heading 1" else 12)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True
    link = _style(doc, "Hyperlink")
    if link is not None:
        link.font.color.rgb = GREEN


def _callouts(doc) -> None:
    """A block quote is the chapter's lead: tinted, a green bar on the left, green text."""
    for paragraph in doc.paragraphs:
        if paragraph.style.name not in ("Block Text", "Quote"):
            continue
        _shade(paragraph._p.get_or_add_pPr(), TINT_HEX)
        _border(paragraph._p, "left", GREEN_HEX, size=18, space=8)
        paragraph.paragraph_format.left_indent = Cm(0.2)
        paragraph.paragraph_format.space_after = Pt(10)
        for run in paragraph.runs:
            run.font.color.rgb = GREEN
            run.font.size = Pt(10.5)
            run.font.italic = False


TEXT_WIDTH_TW = 9298  # 16.4 cm in twips: the page width minus both margins


def _full_width(table, first_col_tw: int | None = None) -> None:
    """Stretch a table to the text width, keeping pandoc's column proportions; the layer
    table gets a fixed first column."""
    tblpr = table._tbl.tblPr
    width = tblpr.find(qn("w:tblW"))
    if width is None:
        width = OxmlElement("w:tblW")
        tblpr.append(width)
    width.set(qn("w:type"), "dxa")
    width.set(qn("w:w"), str(TEXT_WIDTH_TW))
    cols = table._tbl.tblGrid.findall(qn("w:gridCol"))
    old = [int(c.get(qn("w:w")) or 1) for c in cols]
    if first_col_tw and len(cols) == 2:
        new = [first_col_tw, TEXT_WIDTH_TW - first_col_tw]
    else:
        new = [round(TEXT_WIDTH_TW * w / sum(old)) for w in old]
    for col, w in zip(cols, new):
        col.set(qn("w:w"), str(w))
    for row in table.rows:
        for cell, w in zip(row.cells, new):
            tcw = cell._tc.get_or_add_tcPr().find(qn("w:tcW"))
            if tcw is None:
                tcw = OxmlElement("w:tcW")
                cell._tc.get_or_add_tcPr().append(tcw)
            tcw.set(qn("w:type"), "dxa")
            tcw.set(qn("w:w"), str(w))


def _tables(doc) -> None:
    for table in doc.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        header = [c.text.strip() for c in table.rows[0].cells]
        layers = header[:1] == ["Ebene"]  # the layer table: no header, a tinted first column
        if layers:
            table._tbl.remove(table.rows[0]._tr)
        _full_width(table, first_col_tw=2400 if layers else None)
        for r, row in enumerate(table.rows):
            is_head = r == 0 and not layers
            for c, cell in enumerate(row.cells):
                _cell_borders(cell, GREEN_HEX if is_head else "D9D9D9")
                if layers and c == 0:
                    _shade(cell._tc.get_or_add_tcPr(), TINT_HEX)
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after = Pt(3)
                    if layers and c == 0:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in paragraph.runs:
                        run.font.size = Pt(8.5)
                        if is_head or (layers and c == 0):
                            run.font.bold = True


def _title_page(doc, meta: dict, logo: Path) -> None:
    first = doc.paragraphs[0]

    def before(text: str = "", style: str | None = None):
        p = first.insert_paragraph_before(text, style)
        return p

    p = before()
    p.add_run().add_picture(str(logo), width=Cm(2.2))
    p.paragraph_format.space_before = Pt(40)
    p.paragraph_format.space_after = Pt(60)
    p = before()
    run = p.add_run(meta["title"])
    run.font.size, run.font.color.rgb = Pt(30), GREEN
    p.paragraph_format.space_after = Pt(8)
    p = before()
    run = p.add_run(meta["subtitle"])
    run.font.size, run.font.color.rgb = Pt(13), GREY
    p.paragraph_format.space_after = Pt(28)
    _border(p._p, "bottom", RULE_HEX, size=6, space=18)
    p = before()
    run = p.add_run(meta["kicker"])
    run.font.size, run.font.color.rgb = Pt(12), GREEN
    p.paragraph_format.space_before = Pt(20)
    for key in ("version", "link", "intro"):
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", meta[key])
        p = before()
        run = p.add_run(text)
        run.font.size, run.font.color.rgb = Pt(9), GREY
    p.add_run().add_break(WD_BREAK.PAGE)


def _running(doc, logo: Path, title: str) -> None:
    section = doc.sections[0]
    section.page_height, section.page_width = Cm(29.7), Cm(21.0)
    section.top_margin = section.bottom_margin = Cm(2.2)
    section.left_margin = section.right_margin = Cm(2.3)
    section.different_first_page_header_footer = True
    num = OxmlElement("w:pgNumType")
    num.set(qn("w:start"), "0")  # the title page is page 0: the first text page says "Seite 1"
    section._sectPr.append(num)
    head = section.header.paragraphs[0]
    head.add_run().add_picture(str(logo), width=Cm(0.4))
    left = head.add_run(f"  {title}")
    left.font.size, left.font.color.rgb = Pt(8), GREY
    head.paragraph_format.tab_stops.add_tab_stop(Cm(16.4), alignment=2)  # right
    right = head.add_run(f"\t{RUNNING_RIGHT}")
    right.font.size, right.font.color.rgb = Pt(8), GREY
    _border(head._p, "bottom", "D9D9D9", size=4, space=4)
    foot = section.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = foot.add_run("Seite ")
    run.font.size, run.font.color.rgb = Pt(8), GREY
    page = foot.add_run()
    page.font.size, page.font.color.rgb = Pt(8), GREY
    _field(page, "PAGE")


def _closing(doc) -> None:
    """The last line (where the template lives) stands apart: a rule above, small green."""
    filled = [p for p in doc.paragraphs if p.text.strip()]
    last = filled[-1]
    filled[-2].paragraph_format.keep_with_next = True  # never alone on a page
    _border(last._p, "top", "D9D9D9", size=4, space=8)
    last.paragraph_format.space_before = Pt(14)
    for run in last.runs:
        run.font.size, run.font.color.rgb = Pt(9), GREEN


def build(out: Path) -> None:
    for tool in ("pandoc", "soffice"):
        if not shutil.which(tool):
            raise SystemExit(f"build_overview_pdf: {tool} is missing")
    body, meta = _prepare(SOURCE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="overview-pdf-") as tmp:
        work = Path(tmp)
        (work / "body.md").write_text(body, encoding="utf-8")
        logo = work / "mark.png"
        cairosvg.svg2png(url=str(MARK), write_to=str(logo), output_width=512)
        subprocess.run(["pandoc", "body.md", "-f", "gfm", "-o", "raw.docx",
                        "--shift-heading-level-by=-1"], cwd=work, check=True)
        doc = Document(str(work / "raw.docx"))
        doc.core_properties.title = meta["title"]
        doc.core_properties.author = "dev-process"
        _style_fonts(doc)
        _callouts(doc)
        _tables(doc)
        _title_page(doc, meta, logo)
        _running(doc, logo, meta["title"])
        _closing(doc)
        doc.save(str(work / "overview.docx"))
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "overview.docx"],
                       cwd=work, check=True, capture_output=True)
        shutil.copy(work / "overview.pdf", out)
    print(f"build_overview_pdf: wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="the designed PDF of docs/UEBERBLICK.md")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    build(ap.parse_args(argv).out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

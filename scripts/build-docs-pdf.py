#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-docs-pdf.py
# Purpose: Render the maintained Markdown manuals into branded, print-ready PDF editions.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Full history: docs/CHANGELOG.md and Git history.
# Change log:
#   2026-09-11 - Added the Engineering Toolkit PDF edition.
#   2026-09-08 - Treat the advanced camera panel as a full-width interface image.
#   2026-09-07 - Consolidated the PDF plan around 19 owning Markdown documents.
#   2026-09-06 - Keep expanded player settings readable in manual screenshots.
#   2026-09-05 - Kept each PDF list marker with its wrapped item text.
#   2026-09-05 - Rendered paired gesture art side by side inside See it table cells.
#   2026-09-04 - Honoured explicit widths for standalone manual illustrations.
#   2026-09-02 - Added to VirtualGlove.
#   2026-09-03 - Standardized source documentation and maintenance metadata.
#   2026-09-03 - Added changelog, configuration, security, and contributor editions.
#   2026-09-03 - Added explicit page breaks and the illustrated gameplay handbook.
#   2026-09-03 - Added contextual gesture images inside gameplay control tables.
#   2026-09-04 - Added section-link destinations and kept headings with their following content.
#   2026-09-04 - Indented list markers and text consistently within the body margin.

"""Build polished, distributable VirtualGlove PDF guides."""

from __future__ import annotations

import html
import io
import math
import re
from functools import lru_cache
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from PIL import Image as PillowImage
from reportlab.platypus import (
    Image,
    KeepTogether,
    CondPageBreak,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "pdf"
LOGO = ROOT / "assets" / "virtualglove-logo.png"

NIGHT = colors.HexColor("#07111F")
INK = colors.HexColor("#111827")
BLUE = colors.HexColor("#087EBD")
CYAN = colors.HexColor("#24D8F5")
RED = colors.HexColor("#F01846")
PAPER = colors.HexColor("#F4F7FB")
GRID = colors.HexColor("#C8D4E3")
MUTED = colors.HexColor("#526175")
PALE_BLUE = colors.HexColor("#E7F7FC")


def normalize(text: str) -> str:
    """Replace typography and symbols that are unreliable in the bundled PDF fonts."""
    replacements = {
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
        "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"',
        "\u201d": '"', "\u2026": "...", "\u2192": "->", "\u2190": "<-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def inline(text: str) -> str:
    """Convert supported Markdown inline markup to ReportLab paragraph markup."""
    tokens: list[str] = []

    def hold(markup: str) -> str:
        """Temporarily protect generated ReportLab markup from later HTML escaping."""
        tokens.append(markup)
        return f"@@TOKEN{len(tokens) - 1}@@"

    text = normalize(text.strip())
    text = re.sub(
        r"`([^`]+)`",
        lambda match: hold(
            f'<font name="Courier" color="#087EBD">{html.escape(match.group(1))}</font>'
        ),
        text,
    )
    text = re.sub(
        r"\[([^]]+)\]\(([^)]+)\)",
        lambda match: hold(
            f'<link href="{html.escape(match.group(2), quote=True)}" color="#087EBD">'
            f'<u>{html.escape(match.group(1))}</u></link>'
        ),
        text,
    )
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    # Resolve outer Markdown links before the code spans they may contain.
    # Otherwise a label such as [`CHANGES.md`](CHANGES.md) inserts its protected
    # code token after that token's replacement pass has already happened.
    for index, markup in reversed(tuple(enumerate(tokens))):
        text = text.replace(f"@@TOKEN{index}@@", markup)
    return text


def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    """Create a styled paragraph from normalized Markdown text."""
    return Paragraph(inline(text), style)


PDF_IMAGE_DPI = 180


@lru_cache(maxsize=256)
def _pdf_image(path: str, pixel_width: int, pixel_height: int) -> bytes:
    """Return a print-sized copy without changing the maintained source artwork."""
    with PillowImage.open(path) as source:
        source.load()
        if source.width > pixel_width or source.height > pixel_height:
            source.thumbnail((pixel_width, pixel_height), PillowImage.Resampling.LANCZOS)
        buffer = io.BytesIO()
        source.save(buffer, "PNG", optimize=True)
        return buffer.getvalue()


def image_flowable(path: Path, max_width: float, max_height: float) -> Image:
    """Load and proportionally scale a print-sized copy within requested bounds."""
    with PillowImage.open(path) as source:
        width, height = source.size
    scale = min(max_width / width, max_height / height)
    rendered_width, rendered_height = width * scale, height * scale
    target_width = max(1, math.ceil(rendered_width / 72 * PDF_IMAGE_DPI))
    target_height = max(1, math.ceil(rendered_height / 72 * PDF_IMAGE_DPI))
    buffer = io.BytesIO(_pdf_image(str(path), target_width, target_height))
    image = Image(buffer, width=rendered_width, height=rendered_height)
    image._virtualglove_buffer = buffer
    image.hAlign = "CENTER"
    return image


def table_cell(
    cell: str,
    source: Path,
    style: ParagraphStyle,
):
    """Render a table cell as text, one image, or paired contextual images."""

    image_pattern = re.compile(
        r'<img\s+src="([^"]+)"\s+alt="([^"]*)"(?:\s+width="([0-9]+)")?\s*/?>',
    )
    image_match = image_pattern.fullmatch(cell.strip())
    if image_match:
        image_path = (source.parent / image_match.group(1)).resolve()
        if image_path.exists():
            if source.name == "ENCLOSURE_GUIDE.md" and int(image_match.group(3) or 0) >= 200:
                return image_flowable(image_path, 2.7 * inch, 1.75 * inch)
            if "images/matrix/" in cell and int(image_match.group(3) or 104) > 104:
                requested = int(image_match.group(3) or 104)
                return image_flowable(
                    image_path,
                    (1.75 if requested <= 200 else 2.6) * inch,
                    (1.2 if requested <= 200 else 1.7) * inch,
                )
            if int(image_match.group(3) or 0) >= 160:
                return image_flowable(image_path, 1.78 * inch, 1.08 * inch)
            if int(image_match.group(3) or 0) >= 128:
                return image_flowable(image_path, 1.35 * inch, 0.78 * inch)
            return image_flowable(image_path, 0.92 * inch, 0.48 * inch)

    image_matches = list(image_pattern.finditer(cell.strip()))
    if len(image_matches) > 1 and not image_pattern.sub("", cell.strip()).strip():
        images = []
        for match in image_matches:
            image_path = (source.parent / match.group(1)).resolve()
            if not image_path.exists():
                break
            images.append(image_flowable(image_path, 0.50 * inch, 0.48 * inch))
        if len(images) == len(image_matches):
            paired = Table([images], colWidths=[0.52 * inch] * len(images), hAlign="CENTER")
            paired.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            return paired
    return Paragraph(inline(cell), style)


def parse_table(
    lines: list[str],
    start: int,
    styles: dict[str, ParagraphStyle],
    source: Path,
):
    """Parse one Markdown table and return its flowable plus the next source line."""
    rows: list[list[str]] = []
    index = start
    while index < len(lines) and lines[index].strip().startswith("|"):
        rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
        index += 1
    if len(rows) > 1:
        rows.pop(1)
    image_cells = [
        (column, row_number)
        for row_number, row in enumerate(rows[1:], start=1)
        for column, cell in enumerate(row)
        if re.fullmatch(
            r'(?:<img\s+src="[^"]+"\s+alt="[^"]*"(?:\s+width="[0-9]+")?\s*/?>\s*)+',
            cell,
        )
    ]
    image_columns = {column for column, _row in image_cells}
    centered_head = ParagraphStyle("TableHeadCentered", parent=styles["table_head"], alignment=TA_CENTER)
    centered_body = ParagraphStyle("TableCentered", parent=styles["table"], alignment=TA_CENTER)
    formatted = [
        [table_cell(
            cell, source,
            centered_head if row_number == 0 and column in image_columns else
            centered_body if row_number > 0 and column in image_columns else
            styles["table_head"] if row_number == 0 else styles["table"],
        ) for column, cell in enumerate(row)]
        for row_number, row in enumerate(rows)
    ]
    columns = max(len(row) for row in formatted)
    if columns == 2:
        widths = [2.05 * inch, 4.55 * inch]
    elif columns == 3:
        widths = [2.0 * inch, 1.08 * inch, 3.52 * inch]
    elif columns == 4:
        widths = [1.25 * inch, 1.25 * inch, 1.25 * inch, 2.85 * inch]
    else:
        widths = [6.6 * inch / columns] * columns
    if source.name == "MATRIX_GUIDE.md" and columns == 3:
        widths = [1.8 * inch, 2.3 * inch, 2.5 * inch]
    elif source.name == "ENCLOSURE_GUIDE.md" and rows[0] == ["View", "UNO Q Case", "Controller Dock"]:
        widths = [0.55 * inch, 3.025 * inch, 3.025 * inch]
    elif source.name == "ARCHITECTURE.md" and columns == 3:
        widths = [1.4 * inch, 2.6 * inch, 2.6 * inch]
    elif source.name == "ARCHITECTURE.md" and columns == 4:
        widths = [1.2 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch]
    if "See it" in rows[0] and any("images/matrix/" in cell for row in rows for cell in row):
        if columns == 3:
            widths = [1.85 * inch, 1.05 * inch, 3.7 * inch]
        elif columns == 4:
            widths = [1.4 * inch, 1.0 * inch, 2.1 * inch, 2.1 * inch]
    if columns == 2 and any("images/matrix/" in cell for row in rows for cell in row):
        widths = [3.3 * inch, 3.3 * inch]
    elif "See it" in rows[0] and columns == 3 and image_columns:
        widths = [1.85 * inch, 1.35 * inch, 3.4 * inch]
    if rows[0] == ["Profile", "Matrix code", "See it"]:
        widths = [3.7 * inch, 1.85 * inch, 1.05 * inch]
    elif rows[0] == ["Program", "See it", "Try it with", "Know before playing"]:
        widths = [1.05 * inch, 2.05 * inch, 1.75 * inch, 1.75 * inch]
    if rows[0] == ["Game", "ROM SHA-256", "Input finding", "Shared profile"]:
        widths = [1.2 * inch, 1.5 * inch, 2.7 * inch, 1.2 * inch]
    if rows[0] == ["Port", "Protocol", "Direction", "Boundary"]:
        widths = [1.0 * inch, 0.9 * inch, 2.35 * inch, 2.35 * inch]
    if rows[0] == ["Lane", "Core", "Exact game image"]:
        widths = [1.2 * inch, 2.3 * inch, 3.1 * inch]
    table = Table(formatted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    alignment = [
        ("VALIGN", (column, row_number), (column, row_number), "MIDDLE")
        for column, row_number in image_cells
    ]
    alignment.extend(
        ("ALIGN", (column, 0), (column, -1), "CENTER")
        for column in image_columns
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 2, CYAN),
        ("GRID", (0, 1), (-1, -1), 0.35, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ] + alignment))
    return table, index


def parse_list(lines: list[str], start: int, styles: dict[str, ParagraphStyle]):
    """Parse one contiguous Markdown list and return its flowable plus the next source line."""
    ordered = bool(re.match(r"^\s*\d+\.", lines[start]))
    pattern = r"^\s*\d+\.\s+(.+)$" if ordered else r"^\s*[-*]\s+(.+)$"
    rows = []
    index = start
    item_number = 1
    while index < len(lines):
        match = re.match(pattern, lines[index])
        if not match:
            break
        parts = [match.group(1).strip()]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index]
            if re.match(r"^\s*(?:[-*]|\d+\.)\s+", candidate):
                break
            stripped = candidate.strip()
            if stripped.startswith(("#", "```", "|", ">", "![", "<p")):
                break
            parts.append(stripped)
            index += 1
        marker_style = ParagraphStyle(
            "OrderedListMarker" if ordered else "BulletListMarker",
            parent=styles["body"],
            alignment=TA_RIGHT,
            textColor=RED if ordered else BLUE,
            fontName="Helvetica-Bold",
        )
        marker = f"{item_number}." if ordered else "\u2022"
        rows.append([
            Paragraph(marker, marker_style),
            paragraph(" ".join(parts), styles["body"]),
        ])
        item_number += 1
        if index < len(lines) and not lines[index].strip():
            lookahead = index + 1
            if lookahead < len(lines) and re.match(pattern, lines[lookahead]):
                index = lookahead
                continue
            break
    listing = Table(rows, colWidths=[0.3 * inch, 6.3 * inch], hAlign="LEFT", splitByRow=1)
    listing.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 7),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return listing, index


def markdown_story(source: Path, styles: dict[str, ParagraphStyle]):
    """Convert the supported Markdown subset into a sequence of PDF flowables."""
    lines = source.read_text(encoding="utf-8").splitlines()
    story = []
    index = 0
    skipped_html = False
    skipped_title = False
    used_anchors: set[str] = set()
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("<p"):
            skipped_html = True
            index += 1
            continue
        if skipped_html:
            if line.endswith("</p>"):
                skipped_html = False
            index += 1
            continue
        if line == "---":
            story.append(Spacer(1, 8))
            index += 1
            continue
        if line == "<!-- PAGEBREAK -->":
            story.append(PageBreak())
            index += 1
            continue

        image_match = re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", line)
        html_image = re.fullmatch(
            r'<img\s+src="([^"]+)"\s+alt="([^"]*)"\s+width="([0-9]+)"\s*/?>', line,
        )
        if html_image:
            image_path = (source.parent / html_image.group(1)).resolve()
            if image_path.exists():
                width = min(int(html_image.group(3)) * 0.75, 6.1 * inch)
                story.append(KeepTogether([
                    image_flowable(image_path, width, 2.85 * inch),
                    paragraph(html_image.group(2), styles["caption"]),
                    Spacer(1, 10),
                ]))
            index += 1
            continue
        if image_match:
            image_path = (source.parent / image_match.group(2)).resolve()
            if image_path.exists():
                # Interface screenshots need enough space for labels to remain readable.
                screenshot = image_path.name in {
                    "debug-dashboard.png", "play-page.png", "learn-page.png", "tune-page.png",
                    "setup-page.png", "setup-camera.png", "games-section.png", "help-page.png", "help-technical.png", "player-settings.png",
                }
                architecture = image_path.parent.name == "architecture"
                image = image_flowable(image_path, 6.6 * inch if screenshot or architecture else 6.1 * inch,
                                       5.7 * inch if screenshot else 4.1 * inch if architecture else 2.85 * inch)
                group = [image, paragraph(image_match.group(1), styles["caption"])]
                # Keep a directly preceding heading with its illustration, too.
                if story and isinstance(story[-1], Paragraph) and story[-1].style.name in {"H2", "H3", "H4"}:
                    group.insert(0, story.pop())
                story.extend([KeepTogether(group), Spacer(1, 10)])
            index += 1
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2)
            # Match the Help renderer's stable heading IDs before normalizing typography.
            base_anchor = re.sub(r"[^a-z0-9]+", "-", re.sub(r"[`*_]", "", title).lower()).strip("-") or "section"
            anchor = base_anchor
            suffix = 2
            while anchor in used_anchors:
                anchor = f"{base_anchor}-{suffix}"
                suffix += 1
            used_anchors.add(anchor)
            if level == 1 and not skipped_title:
                skipped_title = True
                index += 1
                continue
            if level == 2 and story and (
                title.startswith("Stage ")
                or title.startswith("Daily ")
                or title.startswith("Workshop")
                or title.startswith("Program cards")
                or title in {"Troubleshooting", "How VirtualGlove selects a program"}
            ):
                story.append(CondPageBreak(2.25 * inch))
            story.append(CondPageBreak((1.6 if level == 2 else 1.25) * inch))
            story.append(Paragraph(f'<a name="{anchor}"/>{inline(title)}', styles[f"h{level}"]))
            index += 1
            continue

        if line.startswith(">"):
            quote = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip()[1:].strip())
                index += 1
            callout = Table([[paragraph(" ".join(quote), styles["callout"]) ]], colWidths=[6.6 * inch])
            callout.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.6, GRID),
                ("LINEBEFORE", (0, 0), (0, -1), 4, RED),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]))
            story.extend([callout, Spacer(1, 10)])
            continue

        if line.startswith("```"):
            language = line[3:].strip()
            index += 1
            code: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                rendered = normalize(lines[index]).replace("\t", "    ")
                # Preserve a copyable shell command while fitting long installer URLs.
                if language in ("sh", "bash") and rendered.startswith("curl -fLO https://"):
                    rendered = rendered.replace("curl -fLO ", "curl -fLO " + chr(92) + "\n  ", 1)
                    rendered = rendered.replace(" && bash ", " \\" + "\n  && bash ", 1)
                code.append(rendered)
                index += 1
            index += 1
            label = f"{language.upper()}\n" if language and language != "text" else ""
            code_box = Table(
                [[Preformatted(label + "\n".join(code), styles["code"])]],
                colWidths=[6.6 * inch],
                hAlign="LEFT",
            )
            code_box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), NIGHT),
                ("LINEBEFORE", (0, 0), (0, -1), 3, CYAN),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.extend([code_box, Spacer(1, 8)])
            continue

        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\|?\s*:?-+", lines[index + 1].strip()):
            table, index = parse_table(lines, index, styles, source)
            story.extend([table, Spacer(1, 10)])
            continue

        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[index]):
            listing, index = parse_list(lines, index, styles)
            story.append(listing)
            continue

        if line == "**First round:**":
            # Keep the card's exercise label with its short numbered exercise.
            story.append(CondPageBreak(1.35 * inch))
        parts = [line]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index].strip()
            if candidate.startswith(("#", "```", "|", "<p", "![", ">")) or candidate == "---" or re.match(r"^\s*(?:[-*]|\d+\.)\s+", lines[index]):
                break
            parts.append(candidate)
            index += 1
        story.append(paragraph(" ".join(parts), styles["body"]))
    return story


def style_sheet():
    """Create the branded typography and layout styles used by every guide."""
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle("CoverKicker", fontName="Courier-Bold", fontSize=10, leading=13, textColor=CYAN, alignment=TA_CENTER, spaceAfter=14),
        "cover_title": ParagraphStyle("CoverTitle", fontName="Helvetica-Bold", fontSize=27, leading=31, textColor=colors.white, alignment=TA_CENTER, spaceAfter=12),
        "cover_subtitle": ParagraphStyle("CoverSubtitle", fontName="Helvetica", fontSize=12, leading=17, textColor=colors.HexColor("#DCEAF4"), alignment=TA_CENTER, leftIndent=40, rightIndent=40),
        "cover_meta": ParagraphStyle("CoverMeta", fontName="Courier-Bold", fontSize=8.5, leading=11, textColor=CYAN, alignment=TA_CENTER),
        "h1": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=25, leading=29, textColor=INK, alignment=TA_CENTER, spaceAfter=16),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.white, backColor=NIGHT, borderPadding=(8, 10, 8, 10), spaceBefore=16, spaceAfter=10, keepWithNext=True),
        "h3": ParagraphStyle("H3", parent=base["Heading3"], fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=BLUE, spaceBefore=12, spaceAfter=5, keepWithNext=True),
        "h4": ParagraphStyle("H4", parent=base["Heading4"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=RED, spaceBefore=9, spaceAfter=4, keepWithNext=True),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.25, leading=13.2, textColor=INK, spaceAfter=8),
        "table": ParagraphStyle("Table", parent=base["BodyText"], fontName="Helvetica", fontSize=7.7, leading=10, textColor=INK),
        "table_head": ParagraphStyle("TableHead", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.8, leading=10, textColor=colors.white),
        "code": ParagraphStyle("Code", parent=base["Code"], fontName="Courier", fontSize=7.1, leading=9.5, textColor=colors.white),
        "caption": ParagraphStyle("Caption", parent=base["BodyText"], fontName="Helvetica-Oblique", fontSize=7.5, leading=9.5, textColor=MUTED, alignment=TA_CENTER, spaceBefore=4),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"], fontName="Helvetica", fontSize=8.8, leading=12.5, textColor=INK, alignment=TA_LEFT),
    }


def cover_story(title: str, subtitle: str, kind: str, styles: dict[str, ParagraphStyle]):
    """Build the title-page flowables for one guide."""
    logo = image_flowable(LOGO, 6.55 * inch, 2.5 * inch)
    return [
        Spacer(1, 0.35 * inch), logo, Spacer(1, 0.55 * inch),
        paragraph(kind.upper(), styles["cover_kicker"]),
        paragraph(title, styles["cover_title"]),
        paragraph(subtitle, styles["cover_subtitle"]),
        Spacer(1, 1.0 * inch),
        paragraph(f"2026 EDITION  /  IAIN BENNETT  /  MIT LICENSE", styles["cover_meta"]),
        PageBreak(),
    ]


def cover_page(canvas, document):
    """Draw the full-bleed branded cover background and metadata."""
    canvas.saveState()
    width, height = letter
    canvas.setFillColor(NIGHT)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    canvas.setFillColor(RED)
    canvas.rect(0, 0, width, 0.16 * inch, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, 0.16 * inch, width * 0.72, 0.05 * inch, fill=1, stroke=0)
    canvas.restoreState()


def page_decor(canvas, document):
    """Draw the repeating header, footer, and page number on content pages."""
    canvas.saveState()
    width, height = letter
    canvas.setFillColor(NIGHT)
    canvas.rect(0, height - 0.28 * inch, width, 0.28 * inch, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, height - 0.31 * inch, width * 0.68, 0.03 * inch, fill=1, stroke=0)
    canvas.setStrokeColor(GRID)
    canvas.line(document.leftMargin, 0.47 * inch, width - document.rightMargin, 0.47 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, 0.27 * inch, "VIRTUALGLOVE  /  IAIN BENNETT")
    canvas.drawRightString(width - document.rightMargin, 0.27 * inch, f"PAGE {document.page - 1}")
    canvas.restoreState()


def build(source: Path, destination: Path, title: str, subtitle: str, kind: str):
    """Render one Markdown source into a complete PDF guide."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = style_sheet()
    document = SimpleDocTemplate(
        str(destination), pagesize=letter,
        rightMargin=0.7 * inch, leftMargin=0.7 * inch,
        topMargin=0.55 * inch, bottomMargin=0.67 * inch,
        title=title, subject=subtitle, author="Iain Bennett",
        creator="VirtualGlove documentation builder",
    )
    story = cover_story(title, subtitle, kind, styles) + markdown_story(source, styles)
    document.build(story, onFirstPage=cover_page, onLaterPages=page_decor)


def _quick_base(canvas: Canvas, x: float, y: float, width: float = 112, depth: float = 62) -> None:
    canvas.setFillColor(colors.HexColor("#232A34"))
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(1.5)
    canvas.roundRect(x, y, width, depth, 7, fill=1, stroke=1)
    canvas.setFillColor(PAPER)
    canvas.roundRect(x + 7, y + 7, width - 14, depth - 14, 4, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#232A34"))
    for px, py in ((x + 12, y + 12), (x + width - 12, y + 12),
                   (x + 12, y + depth - 12), (x + width - 12, y + depth - 12)):
        canvas.circle(px, py, 4, fill=1, stroke=0)


def _quick_board(canvas: Canvas, x: float, y: float, width: float = 84, depth: float = 47) -> None:
    canvas.setFillColor(colors.HexColor("#079498"))
    canvas.setStrokeColor(colors.HexColor("#056A72"))
    canvas.roundRect(x, y, width, depth, 2, fill=1, stroke=1)
    canvas.setFillColor(colors.white)
    for px, py in ((x + 8, y + 7), (x + width - 8, y + 7),
                   (x + 8, y + depth - 7), (x + width - 8, y + depth - 7)):
        canvas.circle(px, py, 2.3, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#CBD5E1"))
    canvas.rect(x + width - 12, y + 14, 13, 18, fill=1, stroke=0)


def _quick_lid(canvas: Canvas, x: float, y: float, width: float = 112, depth: float = 62,
               dock: bool = False) -> None:
    canvas.setFillColor(colors.HexColor("#2D333D"))
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(1.4)
    canvas.roundRect(x, y, width, depth, 7, fill=1, stroke=1)
    canvas.setFillColor(PAPER)
    window_width = 31
    canvas.rect(x + (width - window_width) / 2, y + 13, window_width, 21, fill=1, stroke=0)
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(3)
    canvas.rect(x + (width - window_width) / 2 - 2, y + 11, window_width + 4, 25, fill=0, stroke=1)
    if dock:
        canvas.setFillColor(PAPER)
        canvas.rect(x + 12, y + depth - 17, width - 24, 12, fill=1, stroke=0)


def _quick_hub(canvas: Canvas, x: float, y: float, width: float = 112) -> None:
    canvas.setFillColor(colors.HexColor("#626B76"))
    canvas.setStrokeColor(NIGHT)
    canvas.roundRect(x, y, width, 28, 3, fill=1, stroke=1)
    canvas.setFillColor(colors.HexColor("#E5E7EB"))
    port_width = width * 0.13
    for fraction in (0.10, 0.33, 0.56, 0.79):
        canvas.rect(x + width * fraction, y - 1, port_width, 7, fill=1, stroke=0)


def _quick_part_icon(canvas: Canvas, kind: str, x: float, y: float) -> None:
    """Draw a compact parts-strip symbol."""
    if kind == "board":
        _quick_board(canvas, x - 19, y - 8, 38, 22)
    elif kind == "hub":
        _quick_hub(canvas, x - 25, y - 6, 50)
    elif kind == "base":
        _quick_base(canvas, x - 24, y - 10, 48, 27)
    elif kind == "lid":
        _quick_lid(canvas, x - 24, y - 10, 48, 27)
    elif kind == "finish":
        canvas.setStrokeColor(CYAN)
        canvas.setLineWidth(3)
        canvas.rect(x - 17, y - 8, 22, 15, fill=0, stroke=1)
        canvas.setFillColor(NIGHT)
        canvas.roundRect(x + 9, y - 7, 15, 15, 2, fill=1, stroke=0)
    elif kind == "hardware":
        canvas.setFillColor(colors.HexColor("#D7A83D"))
        for offset in (-14, -5, 4, 13):
            canvas.circle(x + offset, y + 4, 3.2, fill=1, stroke=0)
        canvas.setStrokeColor(colors.HexColor("#667085"))
        canvas.setLineWidth(2)
        for offset in (-14, -5, 4, 13):
            canvas.line(x + offset, y - 2, x + offset, y - 13)
    else:
        canvas.setStrokeColor(NIGHT)
        canvas.setLineWidth(3)
        canvas.line(x - 18, y - 10, x + 18, y + 12)
        canvas.circle(x - 20, y - 12, 4, fill=0, stroke=1)


def _pict_arrow(canvas: Canvas, x1: float, y1: float, x2: float, y2: float,
                colour: colors.Color = RED, line_width: float = 2.2) -> None:
    """Draw a bold motion arrow for a pictograph panel."""
    angle = math.atan2(y2 - y1, x2 - x1)
    canvas.setStrokeColor(colour)
    canvas.setLineWidth(line_width)
    canvas.line(x1, y1, x2, y2)
    size = 6
    canvas.line(x2, y2, x2 - size * math.cos(angle - 0.55),
                y2 - size * math.sin(angle - 0.55))
    canvas.line(x2, y2, x2 - size * math.cos(angle + 0.55),
                y2 - size * math.sin(angle + 0.55))


def _pict_check(canvas: Canvas, x: float, y: float, good: bool = True) -> None:
    """Draw the manual's positive check or stop mark."""
    colour = colors.HexColor("#168153") if good else RED
    canvas.setStrokeColor(colour)
    canvas.setLineWidth(2.8)
    canvas.circle(x, y, 9, fill=0, stroke=1)
    if good:
        canvas.line(x - 5, y, x - 1, y - 4)
        canvas.line(x - 1, y - 4, x + 6, y + 5)
    else:
        canvas.line(x - 5, y - 5, x + 5, y + 5)
        canvas.line(x - 5, y + 5, x + 5, y - 5)


def _pict_base(canvas: Canvas, x: float, y: float, width: float = 112,
               height: float = 52, dock: bool = False) -> None:
    """Draw a simplified black-line enclosure base."""
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(1.8)
    canvas.setFillColor(colors.white)
    canvas.roundRect(x, y, width, height, 6, fill=1, stroke=1)
    canvas.setLineWidth(0.9)
    canvas.roundRect(x + 7, y + 7, width - 14, height - 14, 3, fill=0, stroke=1)
    for px, py in ((x + 12, y + 12), (x + width - 12, y + 12),
                   (x + 12, y + height - 12), (x + width - 12, y + height - 12)):
        canvas.circle(px, py, 3.3, fill=0, stroke=1)
    if dock:
        canvas.line(x + width * 0.53, y + 5, x + width * 0.53, y + height - 5)


def _pict_board(canvas: Canvas, x: float, y: float, width: float = 74,
                height: float = 42) -> None:
    """Draw a simplified UNO Q with a highlighted USB-C connector."""
    canvas.setFillColor(colors.HexColor("#E3FBFD"))
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(1.6)
    canvas.roundRect(x, y, width, height, 2, fill=1, stroke=1)
    for px, py in ((x + 7, y + 7), (x + width - 7, y + 7),
                   (x + 7, y + height - 7), (x + width - 7, y + height - 7)):
        canvas.circle(px, py, 2, fill=0, stroke=1)
    canvas.setFillColor(CYAN)
    canvas.setStrokeColor(BLUE)
    canvas.rect(x + width - 7, y + height / 2 - 7, 10, 14, fill=1, stroke=1)


def _pict_lid(canvas: Canvas, x: float, y: float, width: float = 112,
              height: float = 52, dock: bool = False) -> None:
    """Draw a lid, Matrix opening, and optional Dock service opening."""
    canvas.setFillColor(colors.HexColor("#F3F5F8"))
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(1.8)
    canvas.roundRect(x, y, width, height, 6, fill=1, stroke=1)
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(2.4)
    canvas.rect(x + width / 2 - 16, y + height / 2 - 11, 32, 22, fill=0, stroke=1)
    if dock:
        canvas.setStrokeColor(NIGHT)
        canvas.setLineWidth(1.2)
        canvas.rect(x + width - 30, y + height - 13, 21, 8, fill=0, stroke=1)


def _pict_hub(canvas: Canvas, x: float, y: float, width: float = 92,
              height: float = 27) -> None:
    """Draw the Arduino USB-C Hub with its outward-facing ports."""
    canvas.setFillColor(colors.HexColor("#EEF1F5"))
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(1.7)
    canvas.roundRect(x, y, width, height, 3, fill=1, stroke=1)
    for offset in (9, 29, 49, 69):
        canvas.rect(x + offset, y - 1, 12, 6, fill=0, stroke=1)


def _pict_driver(canvas: Canvas, x: float, y: float,
                 heat_tool: bool = False) -> None:
    """Draw a hand-tool silhouette without relying on font glyphs."""
    canvas.setStrokeColor(NIGHT)
    canvas.setLineWidth(6)
    canvas.line(x, y, x + 22, y + 22)
    canvas.setLineWidth(2)
    canvas.line(x + 22, y + 22, x + 39, y + 39)
    if heat_tool:
        canvas.setStrokeColor(colors.HexColor("#D7A83D"))
        canvas.setLineWidth(3)
        canvas.line(x + 39, y + 39, x + 46, y + 46)
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(1.2)
        canvas.arc(x + 36, y + 37, x + 52, y + 53, 20, 140)


def _pictogram(canvas: Canvas, kind: str, x: float, y: float,
               width: float, height: float) -> None:
    """Draw one assembly action as line art with arrows and checks."""
    cx = x + width / 2
    if kind == "inserts":
        _pict_base(canvas, cx - 55, y + 10, 110, 50)
        targets = ((cx - 43, y + 22), (cx + 43, y + 22),
                   (cx - 43, y + 48), (cx + 43, y + 48))
        for index, (tx, ty) in enumerate(targets):
            sx = cx - 42 + index * 28
            canvas.setFillColor(colors.HexColor("#D7A83D"))
            canvas.setStrokeColor(NIGHT)
            canvas.circle(sx, y + 94, 4.2, fill=1, stroke=1)
            _pict_arrow(canvas, sx, y + 87, tx, ty + 6, BLUE, 1.5)
        _pict_driver(canvas, x + width - 48, y + 70, heat_tool=True)
        canvas.setFillColor(NIGHT)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(x + 8, y + 95, "x4")
    elif kind in {"board", "dock-board"}:
        dock = kind == "dock-board"
        base_width = 132 if dock else 112
        _pict_base(canvas, cx - base_width / 2, y + 8, base_width, 52, dock=dock)
        _pict_board(canvas, cx - 37, y + 74)
        _pict_arrow(canvas, cx - 23, y + 70, cx - 23, y + 54, BLUE)
        _pict_arrow(canvas, cx + 23, y + 70, cx + 23, y + 54, BLUE)
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(1.5)
        canvas.line(cx + 37, y + 95, x + width - 12, y + 95)
        canvas.setFillColor(RED)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawRightString(x + width - 8, y + 92, "USB-C")
    elif kind == "plug":
        canvas.setStrokeColor(NIGHT)
        canvas.setLineWidth(2)
        canvas.rect(x + 18, y + 67, 34, 28, fill=0, stroke=1)
        canvas.setFillColor(CYAN)
        canvas.rect(x + 49, y + 74, 8, 14, fill=1, stroke=1)
        canvas.setFillColor(colors.HexColor("#EEF1F5"))
        canvas.roundRect(x + 102, y + 73, 30, 16, 4, fill=1, stroke=1)
        canvas.rect(x + 94, y + 77, 9, 8, fill=1, stroke=1)
        _pict_arrow(canvas, x + 90, y + 81, x + 62, y + 81, BLUE)
        _pict_check(canvas, x + 145, y + 82, True)
        canvas.setStrokeColor(NIGHT)
        canvas.setLineWidth(2)
        canvas.rect(x + 18, y + 18, 34, 28, fill=0, stroke=1)
        canvas.setStrokeColor(RED)
        canvas.line(x + 91, y + 20, x + 59, y + 37)
        canvas.setLineWidth(5)
        canvas.line(x + 103, y + 14, x + 91, y + 20)
        _pict_check(canvas, x + 145, y + 31, False)
    elif kind in {"close", "dock-close"}:
        dock = kind == "dock-close"
        base_width = 132 if dock else 112
        _pict_base(canvas, cx - base_width / 2, y + 7, base_width, 48, dock=dock)
        _pict_lid(canvas, cx - base_width / 2, y + 72, base_width, 48, dock=dock)
        _pict_arrow(canvas, cx - 36, y + 68, cx - 36, y + 52, BLUE)
        _pict_arrow(canvas, cx + 36, y + 68, cx + 36, y + 52, BLUE)
        _pict_driver(canvas, x + width - 48, y + 77)
        _pict_check(canvas, x + width - 18, y + 22, True)
    elif kind == "hub":
        _pict_base(canvas, x + 10, y + 10, width - 20, 55, dock=True)
        _pict_hub(canvas, x + 56, y + 80, 92, 27)
        _pict_arrow(canvas, x + 105, y + 76, x + 105, y + 58, BLUE)
        canvas.setFillColor(RED)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawRightString(x + width - 8, y + 91, "PORTS OUT")
    elif kind == "cable":
        _pict_board(canvas, x + 10, y + 66, 62, 36)
        _pict_hub(canvas, x + 92, y + 72, 65, 23)
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(2.4)
        canvas.bezier(x + 96, y + 80, x + 75, y + 80,
                      x + 86, y + 55, x + 69, y + 80)
        _pict_check(canvas, x + width - 15, y + 107, True)
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(2.2)
        canvas.line(x + 42, y + 29, x + 70, y + 29)
        canvas.line(x + 70, y + 29, x + 58, y + 16)
        canvas.line(x + 58, y + 16, x + 92, y + 16)
        _pict_check(canvas, x + width - 15, y + 23, False)
    elif kind == "finish":
        _pict_lid(canvas, cx - 66, y + 34, 132, 58, dock=True)
        canvas.setStrokeColor(NIGHT)
        canvas.setLineWidth(1.3)
        for offset in (-33, -22, -11, 0, 11, 22, 33):
            canvas.line(cx + offset, y + 24, cx + offset + 5, y + 24)
        _pict_check(canvas, x + width - 18, y + 102, True)
        _pict_check(canvas, x + width - 18, y + 24, True)


def _pict_panel(canvas: Canvas, x: float, y: float, width: float, height: float,
                number: int, title: str, kind: str,
                accent: colors.Color) -> None:
    """Frame one word-light, numbered pictograph."""
    canvas.setFillColor(colors.white)
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(1)
    canvas.roundRect(x, y, width, height, 6, fill=1, stroke=1)
    canvas.setFillColor(accent)
    canvas.circle(x + 18, y + height - 18, 11, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(x + 18, y + height - 22, str(number))
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(x + 36, y + height - 21, title)
    _pictogram(canvas, kind, x + 7, y + 7, width - 14, height - 40)


def _pict_parts(canvas: Canvas, y: float) -> None:
    """Draw a visual parts inventory with only short identifying labels."""
    page_width, _ = landscape(letter)
    canvas.setFillColor(PALE_BLUE)
    canvas.roundRect(24, y, page_width - 48, 52, 7, fill=1, stroke=0)
    canvas.setFillColor(NIGHT)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(34, y + 36, "PARTS")
    items = [("board", "UNO Q"), ("hub", "HUB"), ("base", "BASE"),
             ("lid", "LID"), ("hardware", "M3 x8"),
             ("tools", "TOOLS"), ("finish", "FINISH")]
    item_width = 88
    for index, (kind, label) in enumerate(items):
        cx = 132 + index * item_width
        _quick_part_icon(canvas, kind, cx, y + 31)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.drawCentredString(cx, y + 7, label)


def build_enclosure_quick_reference(output: Path) -> None:
    """Build a single-page pictograph homage to flat-pack assembly manuals."""
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(output), pagesize=landscape(letter), pageCompression=1)
    canvas.setTitle("VirtualGlove Enclosure Assembly Quick Reference")
    canvas.setAuthor("Iain Bennett")
    page_width, page_height = landscape(letter)
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    canvas.setFillColor(NIGHT)
    canvas.rect(0, page_height - 58, page_width, 58, fill=1, stroke=0)
    canvas.drawImage(ImageReader(str(LOGO)), 22, page_height - 51,
                     width=138, height=38, preserveAspectRatio=True,
                     anchor="w", mask="auto")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 17)
    canvas.drawString(185, page_height - 27, "ENCLOSURE ASSEMBLY")
    canvas.setFillColor(CYAN)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(185, page_height - 42, "PICTOGRAPH WORKBENCH GUIDE")
    canvas.setFillColor(RED)
    canvas.roundRect(page_width - 169, page_height - 43, 145, 23, 11, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawCentredString(page_width - 96.5, page_height - 35,
                             "FIT COUPONS BEFORE ASSEMBLY")

    _pict_parts(canvas, 490)

    panel_width, panel_height, gap = 180, 166, 8
    canvas.setFillColor(BLUE)
    canvas.roundRect(24, 459, page_width - 48, 23, 6, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(35, 467, "UNO Q CASE")
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(page_width - 35, 467, "HUB REMAINS OUTSIDE")
    uno_steps = [("INSERTS x4", "inserts"), ("UNO Q", "board"),
                 ("USB-C FIT", "plug"), ("CLOSE", "close")]
    for index, (title, kind) in enumerate(uno_steps, 1):
        _pict_panel(canvas, 24 + (index - 1) * (panel_width + gap), 285,
                    panel_width, panel_height, index, title, kind, BLUE)

    canvas.setFillColor(RED)
    canvas.roundRect(24, 254, page_width - 48, 23, 6, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(35, 262, "CONTROLLER DOCK")
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(page_width - 35, 262, "UNO Q + HUB IN OPEN SERVICE BAY")
    dock_steps = [("UNO Q", "dock-board"), ("HUB", "hub"),
                  ("CABLE", "cable"), ("CLOSE + CLEAR", "finish")]
    for index, (title, kind) in enumerate(dock_steps, 1):
        _pict_panel(canvas, 24 + (index - 1) * (panel_width + gap), 80,
                    panel_width, panel_height, index, title, kind, RED)

    checks = [("POWER OFF", True), ("NO PINCH", True),
              ("PORTS + VENTS", True), ("FORCED LID", False)]
    chip_width = (page_width - 60) / 4
    for index, (label, good) in enumerate(checks):
        x = 24 + index * (chip_width + 4)
        canvas.setFillColor(colors.HexColor("#E9FFF7") if good else colors.HexColor("#FFF1F3"))
        canvas.setStrokeColor(colors.HexColor("#55B88A") if good else RED)
        canvas.roundRect(x, 28, chip_width, 38, 6, fill=1, stroke=1)
        _pict_check(canvas, x + 19, 47, good)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(x + 36, 44, label)
        if not good:
            canvas.setFillColor(RED)
            canvas.setFont("Helvetica-Bold", 6.5)
            canvas.drawString(x + 36, 34, "STOP - CHECK THE FIT")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(24, 12, "Detailed printing, fit, and troubleshooting: Controller Enclosure Guide")
    canvas.setFillColor(NIGHT)
    canvas.setFont("Helvetica-Bold", 6.5)
    canvas.drawRightString(page_width - 24, 12, "/help/enclosure")
    canvas.showPage()
    canvas.save()


def main():
    """Build every maintained PDF edition and report the generation date."""
    obsolete = {
        "Bad-Street-Brawler-Power-Glove-Programs.pdf",
        "VirtualGlove-Motion-Analysis.pdf",
        "Nestopia-PowerGlove-Changes.pdf",
        "Nestopia-PowerGlove-Core-Guide.pdf",
        "VirtualGlove-Dot-Test.pdf",
        "VirtualGlove-Early-Startup.pdf",
        "VirtualGlove-Guide-Asset-Reference.pdf",
        "VirtualGlove-Setup-Code-Review.pdf",
        "VirtualGlove-Third-Party-Components.pdf",
        "VirtualGlove-Web-Illustrations.pdf",
    }
    for name in obsolete:
        path = OUTPUT / name
        if path.exists():
            path.unlink()
    docs = ROOT / "docs"
    overview = ROOT / "README.md"
    install = docs / "INSTALL_README.md"
    cheatsheet = docs / "cheatsheet.md"
    third_party = ROOT / "THIRD_PARTY_NOTICES.md"
    changelog = docs / "CHANGELOG.md"
    configuration = docs / "CONFIGURATION_REFERENCE.md"
    security = docs / "SECURITY.md"
    contributing = docs / "CONTRIBUTING.md"
    gameplay = docs / "GAMEPLAY_GUIDE.md"
    input_audit = docs / "power-glove-rom-input-audit.md"
    native_sgb = docs / "super-glove-ball-native.md"
    direction_response = docs / "direction-response-benchmark.md"
    build(
        overview, OUTPUT / "VirtualGlove-Overview.pdf",
        "VirtualGlove Project Overview",
        "Architecture, controls, security, deployment, and project status.",
        "Project overview",
    )
    build(
        install, OUTPUT / "VirtualGlove-Guide.pdf",
        "VirtualGlove Installation Guide",
        "Install, pair, and play with the VirtualGlove Controller and supported consoles.",
        "Installation instructions",
    )
    build(
        cheatsheet, OUTPUT / "VirtualGlove-Quick-Reference.pdf",
        "VirtualGlove Quick Reference",
        "Current cabinet addresses, services, controls, and maintenance commands.",
        "Cabinet cheat sheet",
    )
    build(
        third_party, OUTPUT / "VirtualGlove-Third-Party-Notices.pdf",
        "Third-party Components and Notices",
        "Licenses, provenance, redistribution obligations, and verified component identities.",
        "Technical notice",
    )
    build(
        changelog, OUTPUT / "VirtualGlove-Changelog.pdf",
        "VirtualGlove Changelog",
        "Versioned features, fixes, security changes, and documentation updates.",
        "Release history",
    )
    build(
        configuration, OUTPUT / "VirtualGlove-Configuration-Reference.pdf",
        "VirtualGlove Configuration Reference",
        "Active files, installed copies, fields, secrets, and generated state.",
        "Technical reference",
    )
    build(
        security, OUTPUT / "VirtualGlove-Security.pdf",
        "VirtualGlove Security Policy",
        "Reporting, trust boundaries, network exposure, shutdown, and release integrity.",
        "Security policy",
    )
    build(
        contributing, OUTPUT / "VirtualGlove-Contributing.pdf",
        "Contributing to VirtualGlove",
        "Source style, testing, documentation, packaging, and pull-request expectations.",
        "Contributor guide",
    )
    build(
        gameplay, OUTPUT / "VirtualGlove-Gameplay-Guide.pdf",
        "Play with VirtualGlove",
        "Programs 1-14, nine cartridge programs, and a whole library to rediscover.",
        "Illustrated game handbook",
    )
    build(docs / "ARCHITECTURE.md", OUTPUT / "VirtualGlove-Architecture.pdf",
          "VirtualGlove Architecture",
          "System boundaries, recognition, tuning, game input, and deployment.",
          "Architecture and flows")
    build(docs / "MATRIX_GUIDE.md", OUTPUT / "VirtualGlove-Matrix-Guide.pdf",
          "VirtualGlove Matrix Display Guide",
          "Recognize animations, mode letters, pairing, and startup feedback.",
          "Display reference")
    build(input_audit, OUTPUT / "VirtualGlove-Input-Audit.pdf",
          "Power Glove Game Input Audit",
          "ROM evidence for native packets and conventional controller mappings.",
          "Compatibility evidence")
    build(native_sgb, OUTPUT / "VirtualGlove-Super-Glove-Ball-Native.pdf",
          "Super Glove Ball Native Compatibility",
          "Confirmed behavior, open questions, tracing, and safe fallback operation.",
          "Native compatibility record")
    build(direction_response, OUTPUT / "VirtualGlove-Direction-Response.pdf",
          "Native Movement Response and Validation",
          "Matched-state response, dot-core isolation, and camera-to-display evidence.",
          "Benchmark report")
    build(docs / "BUILD_YOUR_OWN.md", OUTPUT / "VirtualGlove-Build-Your-Own.pdf",
          "Build your own: parts, cost, and difficulty", "Parts, planning costs, tested hardware, and a staged first build.", "Community guide")
    build(docs / "NATIVE_EMULATION_EXPLAINED.md", OUTPUT / "VirtualGlove-Native-Emulation.pdf",
          "How native Power Glove emulation works", "Follow hand recognition through joystick and native game input.", "Community guide")
    build(docs / "TROUBLESHOOTING.md", OUTPUT / "VirtualGlove-Troubleshooting.pdf",
          "Troubleshooting by symptom", "Find the first failing stage, from the camera to the displayed game.", "Community guide")
    build(docs / "CAMERA_GUIDE.md", OUTPUT / "VirtualGlove-Camera-Guide.pdf",
          "VirtualGlove Camera Guide", "Choose, tune, and troubleshoot a camera without changing gesture recognition.", "User guide")
    build(docs / "ENCLOSURE_GUIDE.md", OUTPUT / "VirtualGlove-Enclosure-Guide.pdf",
          "VirtualGlove Controller Enclosure Guide", "Print and assemble the UNO Q Case or integrated Controller Dock.", "Workshop guide")
    build_enclosure_quick_reference(OUTPUT / "VirtualGlove-Enclosure-Quick-Reference.pdf")
    build(docs / "ENGINEERING_JOURNEY.md", OUTPUT / "VirtualGlove-Engineering-Journey.pdf",
          "VirtualGlove Engineering Journey", "One week of hypotheses, measurements, experiments, and play tests.", "Engineering history")
    build(docs / "ENGINEERING_TOOLKIT.md", OUTPUT / "VirtualGlove-Engineering-Toolkit.pdf",
          "VirtualGlove Engineering Toolkit", "Repeatable analysis, camera, tracing, and native-research workflows.", "Engineering guide")
    print(f"Built 22 PDF guides on {date.today().isoformat()}")


if __name__ == "__main__":
    main()

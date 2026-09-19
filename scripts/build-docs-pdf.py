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


def _assembly_parts_strip(canvas: Canvas, items: list[tuple[str, str]], y: float) -> None:
    """Draw the shared workbench inventory for the one-page assembly map."""
    page_width, _ = landscape(letter)
    x, width, height = 24, page_width - 48, 62
    canvas.setFillColor(PALE_BLUE)
    canvas.roundRect(x, y, width, height, 7, fill=1, stroke=0)
    canvas.setFillColor(NIGHT)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(x + 10, y + height - 14, "LAY OUT THE PARTS")
    item_width = (width - 112) / len(items)
    for index, (kind, label) in enumerate(items):
        left = x + 102 + index * item_width
        _quick_part_icon(canvas, kind, left + item_width / 2, y + 35)
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 6.7)
        canvas.drawCentredString(left + item_width / 2, y + 7, label)


def _assembly_step_row(canvas: Canvas, x: float, y: float, width: float,
                       number: int, title: str, note: str,
                       accent: colors.Color) -> None:
    """Draw one compact, numbered workbench instruction."""
    canvas.setFillColor(colors.white)
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.8)
    canvas.roundRect(x, y, width, 35, 5, fill=1, stroke=1)
    canvas.setFillColor(accent)
    canvas.circle(x + 18, y + 17.5, 10.5, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.drawCentredString(x + 18, y + 13.7, str(number))
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 8.3)
    canvas.drawString(x + 36, y + 21, title)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(x + 36, y + 9, note)


def _assembly_path_panel(canvas: Canvas, x: float, y: float, width: float,
                         title: str, subtitle: str, image_path: Path,
                         steps: list[tuple[str, str]],
                         accent: colors.Color) -> None:
    """Draw one enclosure path with an exploded view and four clear actions."""
    height = 296
    canvas.setFillColor(colors.white)
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(1)
    canvas.roundRect(x, y, width, height, 8, fill=1, stroke=1)
    canvas.setFillColor(accent)
    canvas.roundRect(x, y + height - 35, width, 35, 8, fill=1, stroke=0)
    canvas.rect(x, y + height - 35, width, 9, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(x + 14, y + height - 23, title)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(x + width - 14, y + height - 22, subtitle)
    canvas.drawImage(
        ImageReader(str(image_path)), x + 18, y + 157,
        width=width - 36, height=96, preserveAspectRatio=True,
        anchor="c", mask="auto",
    )
    canvas.setStrokeColor(colors.HexColor("#DDE5EF"))
    canvas.line(x + 15, y + 151, x + width - 15, y + 151)
    for index, (step_title, note) in enumerate(steps, 1):
        _assembly_step_row(
            canvas, x + 12, y + 112 - (index - 1) * 36,
            width - 24, index, step_title, note, accent,
        )


def _assembly_safety_chip(canvas: Canvas, x: float, y: float, width: float,
                          title: str, detail: str) -> None:
    """Draw one final inspection item."""
    canvas.setFillColor(colors.HexColor("#E9FFF7"))
    canvas.setStrokeColor(colors.HexColor("#55B88A"))
    canvas.setLineWidth(1)
    canvas.roundRect(x, y, width, 42, 6, fill=1, stroke=1)
    canvas.setStrokeColor(colors.HexColor("#168153"))
    canvas.setLineWidth(2.3)
    canvas.circle(x + 18, y + 21, 10, fill=0, stroke=1)
    canvas.line(x + 13, y + 21, x + 17, y + 17)
    canvas.line(x + 17, y + 17, x + 24, y + 25)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 7.8)
    canvas.drawString(x + 35, y + 24, title)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.8)
    canvas.drawString(x + 35, y + 11, detail)


def build_enclosure_quick_reference(output: Path) -> None:
    """Build a single-page, diagram-first enclosure assembly sheet."""
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(output), pagesize=landscape(letter), pageCompression=1)
    canvas.setTitle("VirtualGlove Enclosure Assembly Quick Reference")
    canvas.setAuthor("Iain Bennett")
    page_width, page_height = landscape(letter)
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    canvas.setFillColor(NIGHT)
    canvas.rect(0, page_height - 66, page_width, 66, fill=1, stroke=0)
    canvas.drawImage(ImageReader(str(LOGO)), 24, page_height - 58,
                     width=150, height=42, preserveAspectRatio=True,
                     anchor="w", mask="auto")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(200, page_height - 30, "ENCLOSURE ASSEMBLY")
    canvas.setFillColor(CYAN)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(200, page_height - 46, "ONE WORKBENCH SHEET / TWO BUILD PATHS")
    canvas.setFillColor(RED)
    canvas.roundRect(page_width - 174, page_height - 47, 150, 25, 12, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(page_width - 99, page_height - 38,
                             "PRINT THE FIT COUPONS FIRST")

    canvas.setFillColor(PALE_BLUE)
    canvas.roundRect(24, 490, page_width - 48, 46, 7, fill=1, stroke=0)
    canvas.setFillColor(NIGHT)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(36, 517, "CHOOSE ONE")
    canvas.setFillColor(BLUE)
    canvas.drawString(133, 517, "UNO Q CASE")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(133, 502, "Smallest build / hub remains outside")
    canvas.setFillColor(RED)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(432, 517, "CONTROLLER DOCK")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(432, 502, "UNO Q + hub travel as one unit")

    _assembly_parts_strip(
        canvas,
        [("board", "UNO Q"), ("hub", "USB-C HUB"), ("base", "BASE"),
         ("lid", "LID"), ("hardware", "INSERTS + SCREWS"),
         ("tools", "HEAT TOOL + DRIVER"), ("finish", "BEZEL + EMBLEM")],
        418,
    )

    _assembly_path_panel(
        canvas, 24, 110, 366, "UNO Q CASE", "HUB OUTSIDE",
        ROOT / "hardware" / "enclosures" / "previews" /
        "virtualglove-uno-case-exploded.png",
        [("Fit four inserts", "Heat squarely; stop flush; let them cool."),
         ("Mount the UNO Q", "USB-C faces the broad side opening."),
         ("Test the hub plug", "It enters straight without side pressure."),
         ("Close and finish", "Lid, four screws, bezel, emblem, feet.")],
        BLUE,
    )
    _assembly_path_panel(
        canvas, 402, 110, 366, "CONTROLLER DOCK", "HUB IN OPEN BAY",
        ROOT / "hardware" / "enclosures" / "previews" /
        "virtualglove-controller-dock-exploded.png",
        [("Mount the UNO Q", "Fit inserts; USB-C faces the opening."),
         ("Seat the hub", "Ports face outward in the open service bay."),
         ("Route the cable", "Gentle bend; keep it below the lid line."),
         ("Close and finish", "No pinch; add screws, bezel, emblem, feet.")],
        RED,
    )

    safety_width = (page_width - 60) / 4
    checks = [
        ("POWER OFF", "Disconnect before opening."),
        ("CABLE FREE", "No pinch or sharp bend."),
        ("AIR + PORTS", "Everything stays clear."),
        ("LID FLAT", "Never pull it down by screws."),
    ]
    for index, (title, detail) in enumerate(checks):
        _assembly_safety_chip(
            canvas, 24 + index * (safety_width + 4), 53,
            safety_width, title, detail,
        )
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(
        24, 27,
        "Full print settings, downloads, fit guidance, and troubleshooting: Controller Enclosure Guide",
    )
    canvas.setFillColor(NIGHT)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawRightString(page_width - 24, 27,
                           "virtualglove.local:8088/help/enclosure")
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

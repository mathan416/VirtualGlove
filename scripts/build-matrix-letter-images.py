#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/build-matrix-letter-images.py
# Purpose: Render documentation diagrams from the sketch's letter and numeric program glyphs.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-13 - Added Programs 1-14 from the firmware's numeric glyph renderer.
#   2026-09-04 - Added reproducible rounded LED diagrams for programs B-I.
# Full history: docs/CHANGELOG.md and Git history.

"""Build matching SVG and PNG diagrams without modifying the supplied photos."""

from pathlib import Path
import re
from PIL import Image, ImageDraw


def parse_glyphs(source: str, name: str, count: int) -> list[list[int]]:
    """Read one fixed-size glyph table from the firmware source."""
    block = re.search(rf'{name}\[{count}\]\[7\] = \{{(.*?)\n\}};', source, re.S).group(1)
    glyphs = [[int(n) for n in re.findall(r'\d+', row)]
              for row in re.findall(r'\{([^}]+)\}', block)]
    assert len(glyphs) == count and all(len(glyph) == 7 for glyph in glyphs)
    return glyphs


def render(name: str, placements: list[tuple[list[int], int]], out: Path) -> None:
    """Render firmware glyph placements into matching PNG and SVG diagrams."""
    image = Image.new('RGB', (520, 328), 'white')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 519, 327), radius=25,
                           fill='#071526', outline='#16364f', width=3)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="520" height="328" viewBox="0 0 520 328">',
           '<rect width="520" height="328" rx="25" fill="#071526"/>']
    for y in range(8):
        for x in range(13):
            lit = any(y < 7 and left <= x < left + 5 and
                      bool(glyph[y] & (1 << (left + 4 - x)))
                      for glyph, left in placements)
            cx, cy = 26 + x * 39, 27 + y * 39
            color = '#40ceff' if lit else '#17354c'
            if lit:
                draw.ellipse((cx-15, cy-15, cx+15, cy+15), fill='#083c94')
                svg.append('<circle cx="%d" cy="%d" r="15" fill="#083c94"/>' % (cx, cy))
            draw.rounded_rectangle((cx-9, cy-9, cx+9, cy+9), radius=5, fill=color)
            svg.append('<rect x="%d" y="%d" width="18" height="18" rx="5" fill="%s"/>' %
                       (cx-9, cy-9, color))
    image.save(out / (name + '.png'))
    (out / (name + '.svg')).write_text('\n'.join(svg + ['</svg>']) + '\n')


def main() -> None:
    """Read the real glyph bitmaps and place each in its 13-by-8 display grid."""
    root = Path(__file__).resolve().parent.parent
    source = (root / 'sketch/sketch.ino').read_text()
    letters = parse_glyphs(source, 'programGlyphs', 9)
    digits = parse_glyphs(source, 'digitGlyphs', 10)
    out = root / 'docs/images/matrix/programs'
    out.mkdir(parents=True, exist_ok=True)
    for letter, glyph in zip('ABCDEFGHI', letters):
        if letter != 'A':
            render(letter, [(glyph, 4)], out)
    for program in range(1, 15):
        placements = ([(digits[program], 4)] if program < 10 else
                      [(digits[1], 1), (digits[program - 10], 7)])
        render(str(program), placements, out)


if __name__ == '__main__':
    main()

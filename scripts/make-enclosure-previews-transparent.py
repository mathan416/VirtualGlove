#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/make-enclosure-previews-transparent.py
# Purpose: Remove the OpenSCAD documentation matte from enclosure preview PNGs.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-19 - Added repeatable matte removal for enclosure documentation renders.
# Full history: docs/CHANGELOG.md and Git history.

"""Convert the pale OpenSCAD preview matte to antialiased transparency."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PREVIEWS = ROOT / "hardware" / "enclosures" / "previews"
OPENSCAD_MATTE = (255, 255, 229)
MATTE_TOLERANCE = 64
FULLY_CLEAR_DISTANCE = 2

PREVIEW_NAMES = (
    "virtualglove-branding-insets.png",
    "virtualglove-controller-dock-v2-back.png",
    "virtualglove-controller-dock-v2-exploded.png",
    "virtualglove-controller-dock-v2-exterior.png",
    "virtualglove-controller-dock-v2-left.png",
    "virtualglove-controller-dock-v2-port-access.png",
    "virtualglove-controller-dock-v2-right.png",
    "virtualglove-lid-logo-options.png",
    "virtualglove-printable-branding.png",
)


def colour_distance(pixel: tuple[int, int, int, int]) -> int:
    """Return the largest RGB distance from the known OpenSCAD matte."""
    return max(abs(pixel[index] - OPENSCAD_MATTE[index]) for index in range(3))


def transparent_pixel(pixel: tuple[int, int, int, int], distance: int) -> tuple[int, int, int, int]:
    """Remove matte colour while retaining antialiased edge coverage."""
    if distance <= FULLY_CLEAR_DISTANCE:
        return (0, 0, 0, 0)
    alpha = round(
        255
        * (distance - FULLY_CLEAR_DISTANCE)
        / (MATTE_TOLERANCE - FULLY_CLEAR_DISTANCE)
    )
    alpha = max(1, min(254, alpha))
    coverage = alpha / 255
    foreground = []
    for channel, matte in zip(pixel[:3], OPENSCAD_MATTE):
        value = round((channel - matte * (1 - coverage)) / coverage)
        foreground.append(max(0, min(255, value)))
    return (*foreground, alpha)


def remove_matte(path: Path) -> None:
    """Remove matte-coloured pixels, including those visible through openings."""
    with Image.open(path) as source:
        image = source.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    corners = (pixels[0, 0], pixels[width - 1, 0], pixels[0, height - 1], pixels[width - 1, height - 1])
    if any(pixel[3] and colour_distance(pixel) > FULLY_CLEAR_DISTANCE for pixel in corners):
        raise ValueError(f"{path.name}: corners do not match the expected OpenSCAD matte")

    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            if not pixel[3]:
                continue
            distance = colour_distance(pixel)
            if distance < MATTE_TOLERANCE:
                pixels[x, y] = transparent_pixel(pixel, distance)

    image.save(path, optimize=True)


def verify(path: Path) -> None:
    """Require transparent corners and retained opaque model pixels."""
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    width, height = rgba.size
    corners = (
        rgba.getpixel((0, 0)),
        rgba.getpixel((width - 1, 0)),
        rgba.getpixel((0, height - 1)),
        rgba.getpixel((width - 1, height - 1)),
    )
    if any(pixel[3] != 0 for pixel in corners):
        raise ValueError(f"{path.name}: background corners are not transparent")
    alpha_min, alpha_max = rgba.getchannel("A").getextrema()
    if alpha_min != 0 or alpha_max != 255:
        raise ValueError(f"{path.name}: expected both transparent and opaque pixels")


def main() -> None:
    """Update or verify every matte-backed enclosure preview."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in PREVIEW_NAMES:
        path = PREVIEWS / name
        if not args.check:
            remove_matte(path)
        verify(path)
        print(f"PASS  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

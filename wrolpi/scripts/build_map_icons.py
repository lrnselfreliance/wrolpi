#!/usr/bin/env python3
"""Build the sprite sheet of the icons the map draws on overlays.

An overlay drawn with a style of its own names its icons ("hospital", "ham_radio").  The map does not use the
artwork such a style was made for; it draws WROLPi's own icons, which are the Maki and Temaki sets (both CC0, see
`modules/map/icons/NOTICE.txt`).

The sheet is the translation between the two: every icon is listed in its index under its own name and under
every other name it answers to (`modules/map/icons/aliases.json`), each in both spellings ("fire-station" and
"fire_station").  All of an icon's names point at the same pixels, so the map needs no table of its own.

The icons are signed distance fields ("sdf": true), which MapLibre can draw in any color and with a halo, so a
style's `icon-color` applies and an icon is readable over any basemap.

Run this after changing the icons or their aliases; the sheet it writes is committed:

    python3 wrolpi/scripts/build_map_icons.py
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy
import pymupdf
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ICONS_DIRECTORY = PROJECT_ROOT / 'modules' / 'map' / 'icons'
SPRITES_DIRECTORY = PROJECT_ROOT / 'modules' / 'map' / 'static' / 'sprites'
SPRITE_NAME = 'overlay-icons'

# The sets, in order: an icon of an earlier set is used when two share a name.
ICON_SETS = ('maki', 'temaki')

# An icon is drawn to fit a square of this many pixels (at pixel ratio 1), about the size of the basemap's icons.
ICON_SIZE = 21
# Room around the icon for its halo.
BUFFER = 3
# What MapLibre expects of a signed distance field: the edge of the shape is where alpha is three quarters, and
# alpha falls from full to none over this many pixels each side of it (TinySDF's `radius` and `cutoff`).
SDF_RADIUS = 8
SDF_CUTOFF = 0.25
# Each cell is rendered this many pixels across before it is reduced; more is a smoother edge.
RENDER_SIZE = 100
SHEET_COLUMNS = 32


def spellings(name: str) -> List[str]:
    """A name as styles write it: with underscores, and with hyphens."""
    return sorted({name, name.replace('-', '_'), name.replace('_', '-')})


def find_icons(icons_directory: Path = ICONS_DIRECTORY) -> Dict[str, Path]:
    """The SVG of each icon by name, except the excluded ones."""
    excluded = set(json.loads((icons_directory / 'exclude.json').read_text()))
    icons = dict()
    for icon_set in ICON_SETS:
        for path in sorted((icons_directory / 'svg' / icon_set).glob('*.svg')):
            if path.stem not in excluded and path.stem not in icons:
                icons[path.stem] = path
    return icons


def find_names(icons_directory: Path = ICONS_DIRECTORY) -> Dict[str, str]:
    """Every name the sheet answers to, and the icon it is.

    An alias comes before an icon's own name: what a name means on a map was chosen, and is not always the icon
    which happens to be called that ("tower" is an airport's control tower in one set)."""
    icons = find_icons(icons_directory)
    aliases = json.loads((icons_directory / 'aliases.json').read_text())
    names = dict()
    for icon in icons:
        for spelling in spellings(icon):
            names.setdefault(spelling, icon)
    # An icon's exact name is itself, whatever another icon's other spelling is.
    names.update({icon: icon for icon in icons})
    for alias, icon in sorted(aliases.items()):
        if icon not in icons:
            raise ValueError(f'The alias {alias!r} is of an icon which does not exist: {icon!r}')
        for spelling in spellings(alias):
            names[spelling] = icon
    return dict(sorted(names.items()))


def render_shape(svg: Path, cell: int, icon: int) -> numpy.ndarray:
    """Where the icon is, as a boolean array of `cell` by `cell`, the icon fit to the middle `icon` of it."""
    page = pymupdf.open(stream=svg.read_bytes(), filetype='svg')[0]
    scale = icon / max(page.rect.width, page.rect.height)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=True)
    alpha = numpy.frombuffer(pixmap.samples, dtype=numpy.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)[..., -1]
    shape = numpy.zeros((cell, cell), dtype=bool)
    top, left = (cell - pixmap.height) // 2, (cell - pixmap.width) // 2
    shape[top:top + pixmap.height, left:left + pixmap.width] = alpha > 127
    return shape


def nearest_distance(shape: numpy.ndarray, radius: int) -> numpy.ndarray:
    """The distance from each pixel to the nearest pixel of `shape`, up to `radius` (and `radius` beyond it)."""
    height, width = shape.shape
    padded = numpy.zeros((height + 2 * radius, width + 2 * radius), dtype=bool)
    padded[radius:radius + height, radius:radius + width] = shape
    distance = numpy.full(shape.shape, float(radius))
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d = (dy * dy + dx * dx) ** 0.5
            if d >= radius:
                continue
            shifted = padded[radius + dy:radius + dy + height, radius + dx:radius + dx + width]
            numpy.minimum(distance, numpy.where(shifted, d, radius), out=distance)
    return distance


def render_sdf(svg: Path, pixel_ratio: int) -> numpy.ndarray:
    """The signed distance field of an icon: the alpha of its cell of the sheet."""
    cell = (ICON_SIZE + 2 * BUFFER) * pixel_ratio
    # Render large, measure, then reduce.
    oversample = max(1, RENDER_SIZE // cell)
    shape = render_shape(svg, cell * oversample, ICON_SIZE * pixel_ratio * oversample)
    radius = SDF_RADIUS * oversample
    # Positive outside of the shape, negative inside of it, in pixels of the sheet.
    signed = (nearest_distance(shape, radius) - nearest_distance(~shape, radius)) / oversample
    alpha = 255 - 255 * (signed / SDF_RADIUS + SDF_CUTOFF)
    alpha = alpha.reshape(cell, oversample, cell, oversample).mean(axis=(1, 3))
    return numpy.clip(alpha.round(), 0, 255).astype(numpy.uint8)


def build_sprite(pixel_ratio: int, icons_directory: Path = ICONS_DIRECTORY):
    """Returns the sheet (an image) and its index (what each name is in it)."""
    icons = find_icons(icons_directory)
    cell = (ICON_SIZE + 2 * BUFFER) * pixel_ratio
    rows = -(-len(icons) // SHEET_COLUMNS)
    alpha = numpy.zeros((rows * cell, SHEET_COLUMNS * cell), dtype=numpy.uint8)
    cells = dict()
    for index, (icon, svg) in enumerate(icons.items()):
        y, x = (index // SHEET_COLUMNS) * cell, (index % SHEET_COLUMNS) * cell
        alpha[y:y + cell, x:x + cell] = render_sdf(svg, pixel_ratio)
        cells[icon] = dict(x=x, y=y, width=cell, height=cell, pixelRatio=pixel_ratio, sdf=True)

    # Black, shaped by the alpha.
    sheet = Image.fromarray(numpy.dstack([numpy.zeros_like(alpha)] * 3 + [alpha]), 'RGBA')
    index = {name: cells[icon] for name, icon in find_names(icons_directory).items()}
    return sheet, index


def main():
    parser = argparse.ArgumentParser(description='Build the sprite sheet of the map\'s overlay icons.')
    parser.add_argument('--output', type=Path, default=SPRITES_DIRECTORY, help='The directory to write the sheet to')
    args = parser.parse_args()

    for pixel_ratio, suffix in ((1, ''), (2, '@2x')):
        sheet, index = build_sprite(pixel_ratio)
        sheet.save(args.output / f'{SPRITE_NAME}{suffix}.png', optimize=True)
        (args.output / f'{SPRITE_NAME}{suffix}.json').write_text(json.dumps(index, separators=(',', ':')) + '\n')
        print(f'{SPRITE_NAME}{suffix}: {len(set(map(str, index.values())))} icons under {len(index)} names,'
              f' {sheet.width}x{sheet.height}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Draw the placeholder background for the Stats scene.

The Stats scene shows the player's numbers, but only the *numbers* are drawn at
runtime by Draw Text events — every static label lives in the background image.
That split is forced by the engine: the VWF glyph pool is 52 tiles
(0x100 - TEXT_BUFFER_START, see engine ui.h) and it is shared across
consecutive Draw Text calls, so a screen's worth of drawn text would wrap and
overwrite itself.

Labels are blitted from assets/fonts/gbs-mono.png, so the placeholder matches
the game's own lettering and stays on the 8px tile grid. The Draw Text events
in the scene switch to the same mono font with an inline !F:<id>! code, which
is what keeps the runtime values lined up with these labels at one char per
tile.

Real art can replace assets/backgrounds/stats.png at any time without touching
any scripting, as long as the label rows stay on the tile positions in LABELS
below (the scene's Draw Text coordinates are hard-coded to match).

Usage:
    python3 tools/gen_stats_bg.py
"""
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("Pillow is required: pip install pillow")

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

FONT = os.path.join(ROOT, "assets", "fonts", "gbs-mono.png")
OUT = os.path.join(ROOT, "assets", "backgrounds", "stats.png")

TILE = 8
COLS, ROWS = 20, 18
WIDTH, HEIGHT = COLS * TILE, ROWS * TILE

# The DMG palette every other background in the project uses.
PALETTE = [(7, 24, 33), (48, 104, 80), (134, 192, 108), (224, 248, 207)]
BLACK, WHITE = 0, 3

# Font sheet is 16x14 cells of 8x8, with cell 0 == char 32 (space).
FONT_COLS = 16
FIRST_CHAR = 32

# (tile_x, tile_y, text). Runtime values are drawn to the right of each label;
# see project/scenes/stats/scene.gbsres for the matching coordinates.
LABELS = [
    (4, 1, "THE NEW GUY"),
    (0, 3, "-" * COLS),
    (2, 5, "ENERGY"),
    (2, 7, "BRAINS"),
    (2, 9, "PATIENCE"),
    (2, 11, "DAY"),
    (0, 13, "-" * COLS),
    (4, 15, "START: BACK"),
]


def glyph(font, char):
    idx = ord(char) - FIRST_CHAR
    if idx < 0:
        raise ValueError(f"character {char!r} is below the font's first char")
    col, row = idx % FONT_COLS, idx // FONT_COLS
    box = (col * TILE, row * TILE, col * TILE + TILE, row * TILE + TILE)
    if box[2] > font.width or box[3] > font.height:
        raise ValueError(f"character {char!r} is outside the font sheet")
    return font.crop(box)


def main():
    # Flatten to plain black-on-white: the font sheet uses magenta as its
    # width marker, which must not survive into a 4-colour background.
    font = Image.open(FONT).convert("L").point(lambda v: 0 if v < 128 else 255)

    canvas = Image.new("L", (WIDTH, HEIGHT), 255)
    for tile_x, tile_y, text in LABELS:
        if tile_x + len(text) > COLS:
            raise ValueError(f"{text!r} at x={tile_x} runs past the screen edge")
        for offset, char in enumerate(text):
            canvas.paste(glyph(font, char), ((tile_x + offset) * TILE, tile_y * TILE))

    out = Image.new("P", (WIDTH, HEIGHT))
    flat = []
    for colour in PALETTE:
        flat.extend(colour)
    out.putpalette(flat + [0, 0, 0] * (256 - len(PALETTE)))
    out.putdata([BLACK if px < 128 else WHITE for px in canvas.tobytes()])
    out.save(OUT)
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({WIDTH}x{HEIGHT}, {len(LABELS)} labels)")


if __name__ == "__main__":
    main()

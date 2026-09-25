#!/usr/bin/env python3
"""Draw a 32x32 placeholder sprite for every enemy in enemies.yaml.

Each one is a labelled box: the enemy's name, wrapped and centred, inside a
framed card. That is enough to tell the enemies apart in a fight and to see
where the Enemy actor actually sits on screen, which is all the placeholder
has to do (DESIGN.md 6 — real art drops in at the same dimensions with no
scripting change).

Output is assets/sprites/enemy_<slug>.png, the slug being GB Studio's own
filename rule (lowercase, spaces to underscores) so "Coffee Machine" becomes
enemy_coffee_machine.png. enemies.yaml is *not* rewritten; point its `sprite:`
keys at these by hand once GB Studio has imported them.

Three things constrain the drawing:

* **Colour.** A Game Boy sprite has three colours plus transparency, and
  GB Studio keys transparency on #65FF00. The other three are the DMG palette
  the rest of the project's sprite art already uses.
* **Lettering.** The shared font sheet (assets/fonts/gbs-mono.png, used by
  gen_stats_bg.py) is 8x8, which fits four characters across 32px — "COFFEE
  MACHINE" would come out as unreadable four-letter rubble. So this script
  carries its own 3x5 font instead: 7 characters per line, 4 lines, which
  holds every name in the file.
* **Tiles.** GB Studio sprite tiles are 8x16, so 32x32 is 4 columns x 2 rows
  = 8 tile slots. The frame is drawn full-bleed, so almost none of them
  dedupe; budget ~8 unique tiles per enemy sprite.

Each .png gets its .gbsres sidecar written too. GB Studio does create one when
it first sees a new image, but that stub has an *empty* metasprite — no tiles
placed, numTiles 0 — so the sprite compiles to nothing and the enemy is
invisible. Placing 8 tiles x 8 enemies by hand in the sprite editor is the
alternative. Existing sidecars are patched, not replaced, so the ids GB Studio
already assigned survive.

Usage:
    python3 tools/gen_enemy_art.py           # draw every enemy
    python3 tools/gen_enemy_art.py --list    # names and paths, write nothing
"""
import argparse
import json
import os
import re
import sys
import uuid

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("PyYAML is required: uv sync (or pip install pyyaml)")

try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("Pillow is required: uv sync (or pip install pillow)")

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
YAML_PATH = os.path.join(ROOT, "enemies.yaml")
SPRITE_DIR = os.path.join(ROOT, "assets", "sprites")

SIZE = 32                      # 4 x 2 sprite tiles of 8x16

# Index into PALETTE below. Transparent must stay #65FF00 — GB Studio treats
# that exact value as the colour key and nothing else.
TRANSPARENT, DARK, MID, LIGHT = 0, 1, 2, 3
PALETTE = [(101, 255, 0), (7, 24, 33), (134, 192, 108), (224, 248, 207)]

# Card: 1px dark rule, 1px mid rule inside it, light field for the text.
BORDER = 2
PAD = BORDER
TEXT_W = TEXT_H = SIZE - 2 * PAD       # 28x28

GLYPH_W, GLYPH_H = 3, 5
ADVANCE, LEADING = GLYPH_W + 1, GLYPH_H + 1
MAX_COLS = (TEXT_W + 1) // ADVANCE     # 7
MAX_LINES = (TEXT_H + 1) // LEADING    # 4

# A 3x5 uppercase font. '#' is ink. Anything not here renders as a filled box,
# which is loud enough to notice in-game.
FONT = {
    "A": ".#. #.# ### #.# #.#",
    "B": "##. #.# ##. #.# ##.",
    "C": ".## #.. #.. #.. .##",
    "D": "##. #.# #.# #.# ##.",
    "E": "### #.. ##. #.. ###",
    "F": "### #.. ##. #.. #..",
    "G": ".## #.. #.# #.# .##",
    "H": "#.# #.# ### #.# #.#",
    "I": "### .#. .#. .#. ###",
    "J": "..# ..# ..# #.# .#.",
    "K": "#.# #.# ##. #.# #.#",
    "L": "#.. #.. #.. #.. ###",
    "M": "#.# ### ### #.# #.#",
    "N": "##. #.# #.# #.# #.#",
    "O": ".#. #.# #.# #.# .#.",
    "P": "##. #.# ##. #.. #..",
    "Q": ".#. #.# #.# ##. .##",
    "R": "##. #.# ##. #.# #.#",
    "S": ".## #.. .#. ..# ##.",
    "T": "### .#. .#. .#. .#.",
    "U": "#.# #.# #.# #.# ###",
    "V": "#.# #.# #.# #.# .#.",
    "W": "#.# #.# ### ### #.#",
    "X": "#.# #.# .#. #.# #.#",
    "Y": "#.# #.# .#. .#. .#.",
    "Z": "### ..# .#. #.. ###",
    "0": "### #.# #.# #.# ###",
    "1": ".#. ##. .#. .#. ###",
    "2": "##. ..# .#. #.. ###",
    "3": "##. ..# .#. ..# ##.",
    "4": "#.# #.# ### ..# ..#",
    "5": "### #.. ##. ..# ##.",
    "6": ".## #.. ### #.# ###",
    "7": "### ..# .#. #.. #..",
    "8": "### #.# ### #.# ###",
    "9": "### #.# ### ..# ##.",
    "-": "... ... ### ... ...",
    ".": "... ... ... ... .#.",
    "'": ".#. .#. ... ... ...",
    " ": "... ... ... ... ...",
}
TOFU = "### ### ### ### ###"


def slugify(name):
    """GB Studio's resource filename rule: lowercase, spaces to underscores."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower().replace(" ", "_"))


def wrap(name):
    """Split a name into centred lines that fit the card.

    Words longer than a line are hard-broken rather than dropped —
    "CONSTRUCTION" has to become CONSTRU/CTION or it cannot be shown at all.
    """
    lines, current = [], ""
    for word in name.upper().split():
        while len(word) > MAX_COLS:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:MAX_COLS])
            word = word[MAX_COLS:]
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= MAX_COLS:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > MAX_LINES:
        sys.exit(f"'{name}' needs {len(lines)} lines but only {MAX_LINES} fit "
                 f"in {SIZE}x{SIZE}; shorten it or widen the sprite")
    return lines


def draw_glyph(px, char, x, y):
    rows = FONT.get(char, TOFU).split()
    for dy, row in enumerate(rows):
        for dx, cell in enumerate(row):
            if cell == "#":
                px[x + dx, y + dy] = DARK


def draw_enemy(name):
    """One 32x32 labelled card, as a paletted image ready to save."""
    img = Image.new("P", (SIZE, SIZE), TRANSPARENT)
    img.putpalette([c for rgb in PALETTE for c in rgb])
    px = img.load()

    for y in range(SIZE):
        for x in range(SIZE):
            edge = min(x, y, SIZE - 1 - x, SIZE - 1 - y)
            px[x, y] = DARK if edge == 0 else MID if edge == 1 else LIGHT

    lines = wrap(name)
    block_h = LEADING * len(lines) - 1
    top = PAD + (TEXT_H - block_h) // 2
    for i, line in enumerate(lines):
        line_w = ADVANCE * len(line) - 1
        left = PAD + (TEXT_W - line_w) // 2
        for j, char in enumerate(line):
            draw_glyph(px, char, left + j * ADVANCE, top + i * LEADING)
    return img


# -------------------------------------------------------------- sprite sidecar
TILE_W, TILE_H = 8, 16                 # GB Studio sprite tiles are 8x16
COLS, ROWS = SIZE // TILE_W, SIZE // TILE_H
_ART_NS = uuid.UUID("d5f7a1e2-3333-4000-8000-000000000001")


def metasprite_tiles(name):
    """The 8 tile placements for one 32x32 frame.

    Coordinates are ORIGIN-relative, not canvas-relative, and y counts
    *upward* — the same convention gen_enemies.py's --draw-bar-art documents.
    originX is canvasWidth / 2 - 8, so the four columns run -8, 0, 8, 16, and
    the top row of tiles carries the *higher* y. Getting this wrong does not
    error: tiles land outside readSpriteData's mask, get marked Unknown, and
    Unknown matches anything during dedup, so the sprite renders as rubble.
    (Cross-checked against player_van01.png.gbsres, GB Studio's own 32x32.)
    """
    origin_x = SIZE // 2 - TILE_W
    sid = lambda k: str(uuid.uuid5(_ART_NS, f"{name}:{k}"))
    tiles = []
    for col in range(COLS):            # column-major, top tile before bottom
        for row in range(ROWS):
            tiles.append({
                "id": sid(f"tile{col}.{row}"),
                "x": col * TILE_W - origin_x,
                "y": (SIZE - TILE_H) - row * TILE_H,
                "sliceX": col * TILE_W, "sliceY": row * TILE_H,
                "flipX": False, "flipY": False,
                "palette": 0, "paletteIndex": 0,
                "objPalette": "OBP0", "priority": False,
            })
    return tiles


def unique_tile_count(img):
    """Unique 8x16 tiles after flip-aware dedup — what GB Studio will keep.

    numTiles is taken at face value by both the editor's "sprite tiles used in
    scene" counter and the compiler's per-scene budget; nothing recomputes it
    from the image, so an honest number here is what keeps the scene inside
    its tile budget.
    """
    px = img.convert("RGB").load()
    seen = []
    for row in range(ROWS):
        for col in range(COLS):
            tile = tuple(tuple(px[col * TILE_W + x, row * TILE_H + y]
                               for x in range(TILE_W)) for y in range(TILE_H))
            flips = {tile,
                     tuple(r[::-1] for r in tile),
                     tuple(tile[::-1]),
                     tuple(r[::-1] for r in tile[::-1])}
            if not any(t in seen for t in flips):
                seen.append(tile)
    return len(seen)


def write_sidecar(path, filename, img):
    """Fill in the metasprite for one enemy sprite, keeping any existing ids."""
    stem = filename[:-len(".png")]
    sid = lambda k: str(uuid.uuid5(_ART_NS, f"{filename}:{k}"))

    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            sprite = json.load(fh)
    else:
        sprite = {
            "_resourceType": "sprite", "id": sid("sprite"),
            "name": stem, "symbol": "sprite_" + slugify(stem),
            "states": [{"id": sid("state"), "name": "",
                        "animationType": "fixed", "flipLeft": False,
                        "animations": [{"id": sid(f"anim{i}"),
                                        "frames": [{"id": sid(f"frame{i}"),
                                                    "tiles": []}]}
                                       for i in range(8)]}],
            "canvasOriginX": 0, "canvasOriginY": 0,
            "boundsX": 0, "boundsY": -8, "boundsWidth": 16, "boundsHeight": 16,
            "animSpeed": 255, "checksum": "",
        }

    # Only the first animation of a "fixed" state ever runs; the other seven
    # slots stay empty. One frame, because these placeholders don't animate.
    sprite["states"][0]["animations"][0]["frames"][0]["tiles"] = \
        metasprite_tiles(filename)
    sprite["numTiles"] = unique_tile_count(img)
    sprite["canvasWidth"] = sprite["canvasHeight"] = SIZE
    sprite["filename"] = filename
    sprite["width"] = sprite["height"] = SIZE

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sprite, fh, indent=2)
        fh.write("\n")
    return sprite["numTiles"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="show what would be written, then stop")
    args = ap.parse_args()

    with open(YAML_PATH, encoding="utf-8") as fh:
        enemies = yaml.safe_load(fh).get("enemies") or []
    if not enemies:
        sys.exit(f"no 'enemies:' in {YAML_PATH}")

    os.makedirs(SPRITE_DIR, exist_ok=True)
    for enemy in enemies:
        name = enemy["name"]
        filename = f"enemy_{slugify(name)}.png"
        path = os.path.join(SPRITE_DIR, filename)
        label = "/".join(wrap(name))
        if args.list:
            print(f"{name:16} -> {filename:28} [{label}]")
            continue
        img = draw_enemy(name)
        img.save(path)
        tiles = write_sidecar(path + ".gbsres", filename, img)
        print(f"wrote {os.path.relpath(path, ROOT)}  [{label}]  {tiles} tiles")


if __name__ == "__main__":
    main()

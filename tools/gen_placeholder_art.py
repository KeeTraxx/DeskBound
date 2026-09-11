#!/usr/bin/env python3
"""Generate placeholder backgrounds for DeskBound.

These are deliberately crude blocked-out rooms so the game is playable and
testable before any real art exists. Real art drops in later without touching
scripting, as long as dimensions and the 4-colour indexed palette match.

Palette (matches the GB Studio template placeholder):
    0 = darkest   1 = dark   2 = light   3 = lightest
"""
import os

from PIL import Image, ImageDraw

PALETTE = [7, 24, 33, 48, 104, 80, 134, 192, 108, 224, 248, 207]
W, H = 160, 144

DARKEST, DARK, LIGHT, LIGHTEST = 0, 1, 2, 3


def new_bg(w=W, h=H, fill=LIGHTEST):
    im = Image.new("P", (w, h), fill)
    pal = PALETTE + [0] * (768 - len(PALETTE))
    im.putpalette(pal)
    return im


def checker_floor(d, x0, y0, x1, y1, a=LIGHTEST, b=LIGHT, size=16):
    """Tiled office carpet, aligned to the 8px tile grid."""
    for y in range(y0, y1, size):
        for x in range(x0, x1, size):
            c = a if ((x // size) + (y // size)) % 2 == 0 else b
            d.rectangle([x, y, min(x + size - 1, x1), min(y + size - 1, y1)], fill=c)


def box(d, x0, y0, x1, y1, fill=LIGHT, outline=DARKEST):
    d.rectangle([x0, y0, x1, y1], fill=fill, outline=outline)


def label(d, x, y, text, fill=DARKEST):
    """Tiny marker so each placeholder room is identifiable while testing."""
    d.text((x, y), text, fill=fill)


def walls(d, w=W, h=H):
    """Dark border wall, 8px thick — matches collision setup in scenes."""
    d.rectangle([0, 0, w - 1, 7], fill=DARK)
    d.rectangle([0, h - 8, w - 1, h - 1], fill=DARK)
    d.rectangle([0, 0, 7, h - 1], fill=DARK)
    d.rectangle([w - 8, 0, w - 1, h - 1], fill=DARK)


def desk(d, x, y, w=32, h=16):
    box(d, x, y, x + w - 1, y + h - 1, fill=LIGHT, outline=DARKEST)
    # monitor
    box(d, x + 8, y - 10, x + 23, y - 1, fill=DARKEST, outline=DARKEST)


def office_floor():
    im = new_bg()
    d = ImageDraw.Draw(im)
    checker_floor(d, 8, 8, W - 9, H - 9)
    walls(d)
    # cubicle desks
    desk(d, 24, 48)
    desk(d, 96, 48)
    desk(d, 24, 104)
    desk(d, 96, 104)
    # doorways: break room (left), print station (right), meeting (top)
    d.rectangle([0, 56, 7, 79], fill=LIGHTEST)
    d.rectangle([W - 8, 56, W - 1, 79], fill=LIGHTEST)
    d.rectangle([68, 0, 91, 7], fill=LIGHTEST)
    label(d, 66, 12, "OFFICE")
    return im


def break_room():
    im = new_bg()
    d = ImageDraw.Draw(im)
    checker_floor(d, 8, 8, W - 9, H - 9, a=LIGHTEST, b=LIGHT, size=8)
    walls(d)
    # counter
    box(d, 24, 32, 135, 55, fill=LIGHT)
    # the coffee machine itself
    box(d, 64, 8, 95, 39, fill=DARKEST)
    box(d, 72, 16, 87, 27, fill=LIGHT)
    # exit right
    d.rectangle([W - 8, 56, W - 1, 79], fill=LIGHTEST)
    label(d, 52, 120, "BREAK ROOM")
    return im


def print_station():
    im = new_bg()
    d = ImageDraw.Draw(im)
    checker_floor(d, 8, 8, W - 9, H - 9)
    walls(d)
    # the printer
    box(d, 56, 24, 103, 63, fill=DARK)
    box(d, 64, 32, 95, 47, fill=LIGHTEST)
    # paper recycling, eternally full
    box(d, 120, 96, 143, 127, fill=LIGHT)
    # exit left
    d.rectangle([0, 56, 7, 79], fill=LIGHTEST)
    label(d, 44, 120, "PRINT STATION")
    return im


def meeting_room():
    im = new_bg()
    d = ImageDraw.Draw(im)
    checker_floor(d, 8, 8, W - 9, H - 9, a=LIGHTEST, b=LIGHT, size=16)
    walls(d)
    # the big table
    box(d, 32, 48, 127, 103, fill=LIGHT)
    # twelve chairs, because of course
    for i in range(4):
        box(d, 40 + i * 24, 32, 55 + i * 24, 43, fill=DARK)
        box(d, 40 + i * 24, 108, 55 + i * 24, 119, fill=DARK)
    box(d, 16, 64, 27, 87, fill=DARK)
    box(d, 132, 64, 143, 87, fill=DARK)
    # exit bottom
    d.rectangle([68, H - 8, 91, H - 1], fill=LIGHTEST)
    label(d, 48, 16, "MEETING ROOM")
    return im


def battle_bg():
    """Neutral backdrop. Enemy sprite sits top-right, text box bottom."""
    im = new_bg(fill=LIGHTEST)
    d = ImageDraw.Draw(im)
    # horizon band so the enemy has something to stand on
    d.rectangle([0, 0, W - 1, 63], fill=LIGHTEST)
    d.rectangle([0, 64, W - 1, 71], fill=LIGHT)
    d.rectangle([0, 72, W - 1, H - 1], fill=LIGHTEST)
    # enemy platform
    d.ellipse([88, 48, 151, 71], fill=LIGHT, outline=DARK)
    # player platform
    d.ellipse([8, 80, 71, 103], fill=LIGHT, outline=DARK)
    return im


def title():
    im = new_bg(fill=DARKEST)
    d = ImageDraw.Draw(im)
    d.rectangle([16, 40, 143, 87], fill=LIGHTEST, outline=LIGHT)
    label(d, 56, 56, "DESKBOUND", fill=DARKEST)
    label(d, 40, 112, "PRESS START", fill=LIGHTEST)
    return im


SCENES = {
    "office_floor": office_floor,
    "break_room": break_room,
    "print_station": print_station,
    "meeting_room": meeting_room,
    "battle_bg": battle_bg,
    "title": title,
}


def write_sidecar(out, name):
    """GB Studio needs a .gbsres next to each PNG. Ids are stable across runs
    so regenerating art doesn't break scene references."""
    import json
    import uuid
    path = os.path.join(out, f"{name}.png.gbsres")
    if os.path.exists(path):
        return  # keep the existing id
    ns = uuid.UUID("d5f7a1e2-2222-4000-8000-000000000000")
    res = {
        "_resourceType": "background",
        "id": str(uuid.uuid5(ns, name)),
        "name": name,
        "symbol": f"bg_{name}",
        "tileColors": "",
        "filename": f"{name}.png",
        "width": W // 8, "height": H // 8,
        "imageWidth": W, "imageHeight": H,
        "autoColor": False,
    }
    json.dump(res, open(path, "w"), indent=2)


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "assets", "backgrounds")
    out = os.path.normpath(out)
    for name, fn in SCENES.items():
        im = fn()
        path = os.path.join(out, f"{name}.png")
        im.save(path)
        write_sidecar(out, name)
        # GB Studio caps mono backgrounds at 192 unique 8x8 tiles.
        tiles = count_tiles(im)
        flag = "" if tiles <= 192 else "  !! OVER 192-TILE LIMIT"
        print(f"wrote {os.path.basename(path)} {im.size} {tiles} tiles{flag}")


def count_tiles(im):
    px = im.load()
    w, h = im.size
    return len({tuple(px[tx + x, ty + y] for y in range(8) for x in range(8))
                for ty in range(0, h, 8) for tx in range(0, w, 8)})


if __name__ == "__main__":
    main()

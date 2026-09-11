#!/usr/bin/env python3
"""Helpers for emitting GB Studio 4 event JSON.

GB Studio stores scripts as nested event objects with generated UUIDs. Writing
that by hand is unreadable and easy to get subtly wrong, so scene/script
authoring goes through these constructors instead.

Event ids are generated deterministically from a counter so regenerating the
project produces a stable diff rather than a churn of fresh UUIDs.
"""
import uuid

_NS = uuid.UUID("d5f7a1e2-0000-4000-8000-000000000000")
_counter = {"n": 0}


def eid(tag=""):
    """Deterministic id so repeated generation yields stable files."""
    _counter["n"] += 1
    return str(uuid.uuid5(_NS, f"{tag}:{_counter['n']}"))


def reset_ids():
    _counter["n"] = 0


# ---------------------------------------------------------------- script values

def num(v):
    return {"type": "number", "value": v}


def var(var_id):
    return {"type": "variable", "value": str(var_id)}


def add(a, b):
    return {"type": "add", "valueA": a, "valueB": b}


def sub(a, b):
    return {"type": "sub", "valueA": a, "valueB": b}


def mul(a, b):
    return {"type": "mul", "valueA": a, "valueB": b}


def div(a, b):
    return {"type": "div", "valueA": a, "valueB": b}


def rnd(a):
    return {"type": "rnd", "value": a}


def vmax(a, b):
    return {"type": "max", "valueA": a, "valueB": b}


def vmin(a, b):
    return {"type": "min", "valueA": a, "valueB": b}


def ne(a, b):
    return {"type": "ne", "valueA": a, "valueB": b}


def mod(a, b):
    return {"type": "mod", "valueA": a, "valueB": b}


def vand(a, b):
    return {"type": "and", "valueA": a, "valueB": b}


def vor(a, b):
    return {"type": "or", "valueA": a, "valueB": b}


def eq(a, b):
    return {"type": "eq", "valueA": a, "valueB": b}


def gt(a, b):
    return {"type": "gt", "valueA": a, "valueB": b}


def gte(a, b):
    return {"type": "gte", "valueA": a, "valueB": b}


def lt(a, b):
    return {"type": "lt", "valueA": a, "valueB": b}


def lte(a, b):
    return {"type": "lte", "valueA": a, "valueB": b}


# --------------------------------------------------------------------- events

def ev(command, args=None, children=None):
    e = {"command": command, "args": args or {}, "id": eid(command)}
    if children:
        e["children"] = children
    return e


def text(*lines, avatar=None):
    """Display dialogue. Each argument is one text box."""
    args = {
        "text": list(lines) if len(lines) > 1 else lines[0],
        "avatarId": avatar or "",
        "clearPrevious": True,
    }
    return ev("EVENT_TEXT", args)


def set_var(var_id, value):
    return ev("EVENT_SET_VALUE", {"variable": str(var_id), "value": value})


def if_value(condition, true_children, false_children=None):
    """EVENT_IF — verified against src/lib/events/eventIf.js (arg key is 'condition')."""
    return ev(
        "EVENT_IF",
        {"condition": condition},
        {"true": true_children, "false": false_children or []},
    )


def menu(var_id, items, layout="menu", cancel_on_b=True, last_is_cancel=False):
    """Text: Display Menu. Sets var_id to the 1-based index chosen (0 = cancel)."""
    args = {
        "variable": str(var_id),
        "items": len(items),
        "layout": layout,
        "cancelOnLastOption": last_is_cancel,
        "cancelOnB": cancel_on_b,
    }
    for i, label in enumerate(items):
        args[f"option{i + 1}"] = label
    return ev("EVENT_MENU", args)


def switch_scene(scene_id, x=0, y=0, direction="down", fade_speed=2):
    """EVENT_SWITCH_SCENE.

    x and y are declared `type: "value"` in eventSceneSwitch.js, so they must
    be script-value objects — passing raw ints makes the compiler fail with
    "Didn't expect to get here".
    """
    return ev(
        "EVENT_SWITCH_SCENE",
        {
            "sceneId": scene_id,
            "x": x if isinstance(x, dict) else num(x),
            "y": y if isinstance(y, dict) else num(y),
            "direction": direction,
            "fadeSpeed": fade_speed,
        },
    )


def call_custom(script_id, args=None):
    a = {"customEventId": script_id}
    a.update(args or {})
    return ev("EVENT_CALL_CUSTOM_EVENT", a)


def wait(seconds=0.5):
    return ev("EVENT_WAIT", {"time": seconds, "units": "time", "frames": 30})


def shake(frames=10, magnitude=3):
    return ev("EVENT_CAMERA_SHAKE", {
        "time": 0.3, "units": "time", "frames": frames,
        "magnitude": {"type": "number", "value": magnitude},
        "shakeDirection": "horizontal",
    })


def loop(children):
    """EVENT_LOOP is an unconditional goto — there is NO break event in
    GB Studio, so prefer loop_while() for anything that must terminate."""
    return ev("EVENT_LOOP", {}, {"true": children})


def loop_while(condition, children):
    """EVENT_LOOP_WHILE — the only loop that can exit. Verified against
    src/lib/events/eventLoopWhile.js."""
    return ev("EVENT_LOOP_WHILE", {"condition": condition}, {"true": children})


def stop():
    return ev("EVENT_STOP", {})


def comment(t):
    return ev("EVENT_COMMENT", {"text": t})


def fade_in(speed=2):
    return ev("EVENT_FADE_IN", {"speed": speed})


def fade_out(speed=2):
    return ev("EVENT_FADE_OUT", {"speed": speed})


# --------------------------------------------------------------- collisions
# Values from the engine: TOP=1 BOTTOM=2 LEFT=4 RIGHT=8, so ALL=15 is solid.
COLLISION_NONE = 0
COLLISION_ALL = 15


def compress_8bit(values):
    """Port of GB Studio's compress8bitNumberArray.

    Format: two hex digits for the value, then either "!" (exactly one) or
    "<hexcount>+" for a run. Scene.collisions is stored in this form.
    """
    if not values:
        return ""
    out = ""
    prev = -1
    run = 0
    for v in values:
        if v != prev:
            if run == 1:
                out += "!"
            elif run > 0:
                out += f"{run:x}+"
            run = 0
            prev = v
            out += f"{prev % 256:02x}"
        run += 1
    if run == 1:
        out += "!"
    elif run > 0:
        out += f"{run:x}+"
    return out


def decompress_8bit(s):
    """Inverse of compress_8bit — used to verify round-trips."""
    out = []
    i = 0
    while i < len(s):
        val = int(s[i:i + 2], 16)
        i += 2
        if i >= len(s):
            return []
        if s[i] == "!":
            count = 1
            i += 1
        else:
            j = s.index("+", i)
            count = int(s[i:j], 16)
            i = j + 1
        out.extend([val] * count)
    return out

#!/usr/bin/env python3
"""Validate generated .gbsres files against GB Studio's own definitions.

GB Studio can only build from its GUI, so this stands in for a compile check.
It verifies, all against data extracted from the installed app rather than
against assumptions:

  1. every resource carries the fields its TypeBox schema requires
  2. every script event command exists in src/lib/events
  3. every event argument key is one the event actually declares
  4. every `type:"value"` field gets a script-value object, not a bare scalar
  5. every script value uses a real operator type
  6. no scene/background reference dangles
  7. every scene-switch lands on a walkable tile, clear of other triggers,
     and every trigger is reachable given the 8x16 sprite height
  8. actors/triggers live in <scene>/actors/ and <scene>/triggers/ — GB Studio
     binds them to a scene by directory, and silently discards orphans

Check 4 exists because it was missed the first time: EVENT_SWITCH_SCENE's
x/y are value fields, and passing raw ints compiled to
`Error: Didn't expect to get here` with no hint as to which field was wrong.

Run: python3 tools/validate.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EVENTS_DIR = "/home/lttrk/.cache/deskbound-build/extract/src/lib/events"

# Required fields per resource type, transcribed from the TypeBox schemas in
# the 4.3.2 app bundle (Type.Optional entries omitted).
REQUIRED = {
    "actor": [
        "_resourceType", "_index", "id", "symbol", "prefabId", "name",
        "coordinateType", "x", "y", "frame", "animate", "spriteSheetId",
        "paletteId", "direction", "moveSpeed", "animSpeed", "isPinned",
        "persistent", "collisionGroup", "collisionExtraFlags",
        "prefabScriptOverrides", "script", "startScript", "updateScript",
        "hit1Script", "hit2Script", "hit3Script",
    ],
    "trigger": [
        "_resourceType", "_index", "id", "symbol", "prefabId", "name",
        "x", "y", "width", "height", "prefabScriptOverrides",
        "script", "leaveScript",
    ],
    "scene": [
        "_resourceType", "_index", "id", "type", "name", "symbol", "x", "y",
        "width", "height", "backgroundId", "tilesetId", "colorModeOverride",
        "paletteIds", "spritePaletteIds", "autoFadeSpeed", "script",
        "playerHit1Script", "playerHit2Script", "playerHit3Script",
        "collisions",
    ],
    "background": [
        "_resourceType", "id", "name", "symbol", "filename",
        "width", "height", "imageWidth", "imageHeight",
    ],
}

BINARY_OPS = {
    "add", "sub", "mul", "div", "mod", "eq", "ne", "lt", "lte", "gt", "gte",
    "min", "max", "and", "or", "atan2", "shl", "shr", "bAND", "bOR", "bXOR",
}
UNARY_OPS = {"rnd", "abs", "isqrt", "not", "bNOT", "neg"}
LEAF_TYPES = {"number", "variable", "true", "false", "property", "expression",
              "direction", "indirect"}

SCRIPT_KEYS = ("script", "startScript", "updateScript", "leaveScript",
               "playerHit1Script", "playerHit2Script", "playerHit3Script",
               "hit1Script", "hit2Script", "hit3Script")


def load_event_defs():
    """Map EVENT_ID -> {field key: declared field type}, from engine sources.

    The field *type* matters as much as the key: fields declared `type:"value"`
    must receive a script-value object, not a bare number. Passing an int makes
    the compiler die with "Didn't expect to get here".
    """
    defs = {}
    if not os.path.isdir(EVENTS_DIR):
        print(f"! engine event sources not found at {EVENTS_DIR}")
        print("  (extract them from the flatpak asar — see MEMORY notes)")
        return None
    for path in glob.glob(os.path.join(EVENTS_DIR, "*.js")):
        src = open(path).read()
        m = re.search(r'const id = "([A-Z_0-9]+)"', src)
        if not m:
            continue
        fields = {}
        for km in re.finditer(r'key:\s*"([a-zA-Z0-9_]+)"', src):
            key = km.group(1)
            if key in fields:
                continue
            after = re.search(r'type:\s*"([a-zA-Z]+)"', src[km.end():km.end() + 300])
            if after:
                fields[key] = after.group(1)
        defs[m.group(1)] = fields
    return defs


# Field types that require a script-value object rather than a scalar.
VALUE_FIELD_TYPES = {"value"}


def is_script_value(v):
    return isinstance(v, dict) and "type" in v


def walk_events(events):
    for e in events or []:
        yield e
        for _, kids in (e.get("children") or {}).items():
            yield from walk_events(kids)


def check_value(value, where, problems):
    if not isinstance(value, dict):
        return
    t = value.get("type")
    if t in LEAF_TYPES:
        return
    if t in BINARY_OPS:
        if "valueA" not in value or "valueB" not in value:
            problems.append(f"{where}: binary op '{t}' missing operand")
        check_value(value.get("valueA"), where, problems)
        check_value(value.get("valueB"), where, problems)
    elif t in UNARY_OPS:
        if "value" not in value:
            problems.append(f"{where}: unary op '{t}' missing value")
        check_value(value.get("value"), where, problems)
    else:
        problems.append(f"{where}: unknown script value type '{t}'")


SPRITE_TILE_HEIGHT = 2  # 8x16 sprite mode occupies two vertical tiles


def decompress_8bit(s):
    """Port of GB Studio's decompress8bitNumberString (scene.collisions)."""
    out = []
    i = 0
    while i < len(s):
        val = int(s[i:i + 2], 16)
        i += 2
        if i >= len(s):
            return []
        if s[i] == "!":
            count, i = 1, i + 1
        else:
            j = s.index("+", i)
            count, i = int(s[i:j], 16), j + 1
        out.extend([val] * count)
    return out


def check_resource_layout(problems):
    """Actors and triggers must sit in <scene_dir>/actors|triggers/.

    GB Studio groups scene children by the path segment before "/actors/" or
    "/triggers/". Files written flat beside scene.gbsres load as orphans owned
    by no scene, and the next GUI save drops them — which silently deleted
    every actor and trigger in this project once already.
    """
    for path in glob.glob("project/scenes/**/*.gbsres", recursive=True):
        if path.endswith(".bak"):
            continue
        base = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))
        if base == "scene.gbsres":
            continue
        try:
            rtype = json.load(open(path)).get("_resourceType")
        except Exception:
            continue
        expected = {"actor": "actors", "trigger": "triggers"}.get(rtype)
        if expected and parent != expected:
            problems.append(
                f"{path}: {rtype} must live in a '{expected}/' directory "
                f"(found in '{parent}/') — GB Studio will not bind it to the "
                f"scene and will discard it on save")


def check_navigation(resources, problems):
    """Catch rooms you can enter but not leave.

    Two failures found this way, both invisible in the JSON: a trigger on the
    final tile row is unreachable because an 8x16 sprite never stands there,
    and an arrival point overlapping a return trigger bounces the player
    straight back where they came from.
    """
    scenes = {}
    for path, data in resources.get("scene", []):
        key = os.path.basename(os.path.dirname(path))
        scenes[data["id"]] = {
            "name": key, "w": data["width"], "h": data["height"],
            "collisions": decompress_8bit(data.get("collisions") or ""),
            "triggers": [],
        }
    by_dir = {s["name"]: sid for sid, s in scenes.items()}
    for path, data in resources.get("trigger", []):
        key = os.path.basename(os.path.dirname(path))
        if key in by_dir:
            scenes[by_dir[key]]["triggers"].append(data)

    for path, data in resources.get("trigger", []):
        key = os.path.basename(os.path.dirname(path))
        sid = by_dir.get(key)
        if not sid:
            continue
        sc = scenes[sid]
        # a trigger whose rows all sit below the last standable row is dead
        last_standable = sc["h"] - SPRITE_TILE_HEIGHT
        if data["y"] > last_standable:
            problems.append(
                f"{path}: trigger '{data['name']}' at y={data['y']} is unreachable "
                f"(8x16 sprite cannot stand below y={last_standable})")

    for rtype in ("scene", "actor", "trigger"):
        for path, data in resources.get(rtype, []):
            for skey in SCRIPT_KEYS:
                for e in walk_events(data.get(skey)):
                    if e.get("command") != "EVENT_SWITCH_SCENE":
                        continue
                    dest = scenes.get(e["args"].get("sceneId"))
                    if not dest:
                        continue
                    ax, ay = e["args"]["x"], e["args"]["y"]
                    if not (is_script_value(ax) and is_script_value(ay)):
                        continue
                    x, y = ax.get("value"), ay.get("value")
                    if not isinstance(x, int) or not isinstance(y, int):
                        continue
                    col = dest["collisions"]
                    if col and 0 <= y < dest["h"] and 0 <= x < dest["w"]:
                        if col[y * dest["w"] + x]:
                            problems.append(
                                f"{path}: arrives in {dest['name']} at ({x},{y}) "
                                f"which is a solid tile")
                    for t in dest["triggers"]:
                        for yy in range(y - SPRITE_TILE_HEIGHT + 1, y + 1):
                            if (t["x"] <= x < t["x"] + t["width"]
                                    and t["y"] <= yy < t["y"] + t["height"]):
                                problems.append(
                                    f"{path}: arrives in {dest['name']} at ({x},{y}) "
                                    f"overlapping trigger '{t['name']}' — player will "
                                    f"be bounced straight back")
                                break


def main():
    os.chdir(ROOT)
    problems = []
    event_defs = load_event_defs()

    resources = {}
    for path in glob.glob("project/**/*.gbsres", recursive=True) + \
            glob.glob("assets/**/*.gbsres", recursive=True):
        if path.endswith(".bak"):
            continue
        try:
            data = json.load(open(path))
        except Exception as exc:
            problems.append(f"{path}: unparseable ({exc})")
            continue
        rtype = data.get("_resourceType")
        resources.setdefault(rtype, []).append((path, data))

        # 1. required fields
        for field in REQUIRED.get(rtype, []):
            if field not in data:
                problems.append(f"{path}: missing required field '{field}'")

        # 2/3/4. script events
        for key in SCRIPT_KEYS:
            for e in walk_events(data.get(key)):
                cmd = e.get("command")
                if event_defs is not None:
                    if cmd not in event_defs:
                        problems.append(f"{path}: unknown event '{cmd}'")
                    else:
                        for arg, val in e.get("args", {}).items():
                            known = (arg in event_defs[cmd]
                                     or arg.startswith("__")
                                     or re.match(r"option\d", arg)
                                     or arg == "customEventId")
                            if not known:
                                problems.append(
                                    f"{path}: event {cmd} has unknown arg '{arg}'")
                                continue
                            ftype = event_defs[cmd].get(arg)
                            if ftype in VALUE_FIELD_TYPES and not is_script_value(val):
                                problems.append(
                                    f"{path}: {cmd}.{arg} is a '{ftype}' field but got "
                                    f"{val!r} — must be a script-value object "
                                    f"like {{'type':'number','value':N}}")
                for arg, val in e.get("args", {}).items():
                    if isinstance(val, dict) and "type" in val:
                        check_value(val, f"{path} [{cmd}.{arg}]", problems)

    # 5. reference integrity
    scene_ids = {d["id"] for _, d in resources.get("scene", [])}
    bg_ids = {d["id"] for _, d in resources.get("background", [])}
    for path, data in resources.get("scene", []):
        if data.get("backgroundId") not in bg_ids:
            problems.append(f"{path}: backgroundId does not resolve")
    for rtype in ("scene", "actor", "trigger"):
        for path, data in resources.get(rtype, []):
            for key in SCRIPT_KEYS:
                for e in walk_events(data.get(key)):
                    if e.get("command") == "EVENT_SWITCH_SCENE":
                        if e["args"].get("sceneId") not in scene_ids:
                            problems.append(f"{path}: switch to unknown scene")

    check_resource_layout(problems)
    check_navigation(resources, problems)

    counts = {k: len(v) for k, v in sorted(resources.items()) if k}
    print("resources:", counts)
    if event_defs:
        print(f"validated against {len(event_defs)} engine event definitions")

    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems[:40]:
            print("  -", p)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

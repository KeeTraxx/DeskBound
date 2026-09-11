#!/usr/bin/env python3
"""Generate the DeskBound battle from enemies.yaml.

GB Studio stores scripts as deeply nested JSON with UUIDs, so the whole
turn loop — one branch per enemy, per verb, per move — is miserable to author
in the GUI. This tool keeps the *content* in enemies.yaml and compiles it into
a single GB Studio custom script named "BattleScript".

It writes these files and touches nothing else in the project:

  project/scripts/battlescript.gbsres           the "BattleScript" custom script
  project/scripts/setbar.gbsres                 "SetBar" (only with "bars:")
  project/scenes/battle/actors/enemy.gbsres     actor whose sprite the script swaps
  project/scenes/battle/actors/playerbar.gbsres Composure meter (only with "bars:")
  project/scenes/battle/actors/enemybar.gbsres  Composure meter (only with "bars:")
  project/scenes/battle/scene.gbsres            On Init -> call BattleScript(Enemy)

A GB Studio custom script cannot reference a scene actor by id (the compiler
rejects it with "Unknown arg actor ..."), so the enemy sprite is an actor
*parameter* of the script, bound at the call site in the battle scene. That is
why this tool also owns the battle scene's On Init script and the enemy actor.

The Composure bars are set by BattleScript through a second generated script,
"SetBar". They cannot poll instead: a scene's On Init script is compiled with
VM_LOCK, and while a context holds that lock the VM scheduler runs no other
thread, so an actor On Update script never executes during a battle.

Usage:
    python3 tools/gen_enemies.py [--enemies enemies.yaml] [--dry-run]
    python3 tools/gen_enemies.py --simulate      # play the generated script and
                                                 # report win rates per strategy
    python3 tools/gen_enemies.py --draw-bar-art  # redraw the placeholder bar
                                                 # strip after changing bars:

Everything else in the project stays hand-authored in the GB Studio GUI.
"""
import argparse
import glob
import json
import os
import random
import re
import sys
import uuid

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not logic
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

SCRIPT_NAME = "BattleScript"
SCRIPT_SYMBOL = "script_battle"
ENEMY_ACTOR_NAME = "Enemy"
# Custom-script actor parameter slots. Inside the script events reference an
# actor as "0"; the call site binds it with the arg key "$actor[0]$".
ENEMY_ACTOR_SLOT = "0"
PLAYER_BAR_SLOT = "1"
ENEMY_BAR_SLOT = "2"
PLAYER_BAR_NAME = "PlayerBar"
ENEMY_BAR_NAME = "EnemyBar"

SETBAR_NAME = "SetBar"
SETBAR_SYMBOL = "script_setbar"
# SetBar's own parameter slots: the bar actor, plus value/max passed by value.
SETBAR_VALUE_SLOT = "V0"
SETBAR_MAX_SLOT = "V1"

# Globals the battle needs. They must already exist in project/variables.gbsres
# (create them in the GUI) — this tool never edits the variable list.
REQUIRED_VARS = [
    "enemy_id", "enemy_composure", "enemy_composure_max",
    "player_composure", "player_composure_max",
    "battle_menu_choice", "battle_act_choice", "battle_damage",
    "battle_temp", "battle_result", "battle_turn_count",
]

# battle_result values, also readable from the overworld after the fight.
RESULT_ONGOING, RESULT_WIN, RESULT_FLED, RESULT_LOST = 0, 1, 2, 3

DEFAULT_MESSAGES = {
    "status": "YOU  {player_composure}/{player_composure_max}\n"
              "THEM {enemy_composure}/{enemy_composure_max}",
    "hit": "It loses {damage}\nComposure.",
    "no_effect": "It barely notices.",
    "player_hit": "You lose {damage}\nComposure.",
}
DEFAULT_MENU = {"act": "ACT", "look": "LOOK", "flee": "FLEE"}
DEFAULT_FLEE = {
    "chance": 3,
    "out_of": 4,
    "success": "You walk away. The\nproblem remains, but\nso do you.",
    "failed": "You get as far as the\ndoor and change your\nmind.",
    "blocked": "You can't leave.",
}

MAX_VAR_VALUE = 32767  # GB Studio 4 globals are 16-bit

# Actor animSpeed is the engine's anim_tick. 255 is the editor's "None" — the
# only way to stop a sprite cycling its frames, since the `animate` flag is not
# emitted for actors in 4.2 and EVENT_ACTOR_SET_ANIMATE is deprecated and
# unimplemented. A bar whose frame *is* its value must never self-animate.
ANIM_SPEED_DEFAULT = 15
ANIM_SPEED_NONE = 255


def fail(msg):
    raise SystemExit(f"gen_enemies: {msg}")


# ----------------------------------------------------------------- event JSON
# Ids are derived from a counter rather than random UUIDs so regenerating
# produces a stable diff instead of churning every id in the file.
_NS = uuid.UUID("d5f7a1e2-0000-4000-8000-000000000000")
_counter = {"n": 0}


def eid(tag=""):
    _counter["n"] += 1
    return str(uuid.uuid5(_NS, f"{tag}:{_counter['n']}"))


def ev(command, args=None, children=None):
    e = {"command": command, "args": args or {}, "id": eid(command)}
    if children:
        e["children"] = children
    return e


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


def eq(a, b):
    return {"type": "eq", "valueA": a, "valueB": b}


def ne(a, b):
    return {"type": "ne", "valueA": a, "valueB": b}


def gt(a, b):
    return {"type": "gt", "valueA": a, "valueB": b}


def lt(a, b):
    return {"type": "lt", "valueA": a, "valueB": b}


def lte(a, b):
    return {"type": "lte", "valueA": a, "valueB": b}


def vand(a, b):
    return {"type": "and", "valueA": a, "valueB": b}


def _text(line):
    return ev("EVENT_TEXT", {
        "text": line,
        "avatarId": "",
        "clearPrevious": True,
    })


def make_say(roll_var):
    """Build the dialogue emitter, rolling variants on `roll_var`.

    A text field is a list of *variants*, each a list of steps. One variant is
    picked at random at runtime; its steps then play in order, one Display Text
    each. A single variant needs no roll at all.
    """

    def say(variants):
        if len(variants) == 1:
            return [_text(step) for step in variants[0]]
        cases = [(i, [_text(step) for step in variant])
                 for i, variant in enumerate(variants)]
        return ([set_var(roll_var, rnd(num(len(variants))))]
                + dispatch(var(roll_var), cases, catch_all=True))

    return say


def dispatch(value, cases, catch_all=False):
    """Nested if/else over `value` — cases are [(match, events), ...].

    Deliberately *not* a flat run of EVENT_IFs: only the taken branch is
    evaluated, so a branch is free to clobber the very variable being switched
    on. Dialogue variants and enemy move selection both roll `battle_temp`, and
    a flat chain would let a move's own text re-roll it into a second match.

    With catch_all the final case becomes the plain else — correct when the
    cases cover every value of a `rnd()`, and one comparison cheaper.
    """
    if not cases:
        return []
    node, rest = ([], cases) if not catch_all else (cases[-1][1], cases[:-1])
    for match, body in reversed(rest):
        node = [if_value(eq(value, num(match)), body, node)]
    return node


def set_var(var_id, value):
    return ev("EVENT_SET_VALUE", {"variable": str(var_id), "value": value})


def if_value(condition, true_children, false_children=None):
    return ev("EVENT_IF", {"condition": condition},
              {"true": true_children, "false": false_children or []})


def menu(var_id, items, layout="menu", cancel_on_b=False):
    args = {
        "variable": str(var_id),
        "items": len(items),
        "layout": layout,
        "cancelOnLastOption": False,
        "cancelOnB": cancel_on_b,
    }
    for i, label in enumerate(items):
        args[f"option{i + 1}"] = label
    return ev("EVENT_MENU", args)


def loop_while(condition, children):
    """The only loop GB Studio can exit — there is no break event."""
    return ev("EVENT_LOOP_WHILE", {"condition": condition}, {"true": children})


def actor_set_sprite(actor, sprite_id):
    return ev("EVENT_ACTOR_SET_SPRITE",
              {"actorId": actor, "spriteSheetId": sprite_id})


def actor_set_frame(actor, frame):
    return ev("EVENT_ACTOR_SET_FRAME", {"actorId": actor, "frame": frame})


def pop_state(fade_speed="2"):
    return ev("EVENT_SCENE_POP_STATE", {"fadeSpeed": fade_speed})


def call_custom(script_id, args=None):
    a = {"customEventId": script_id}
    a.update(args or {})
    return ev("EVENT_CALL_CUSTOM_EVENT", a)


def comment(body):
    return ev("EVENT_COMMENT", {"text": body})


# ------------------------------------------------------------------ project io
def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_variables():
    """name -> variable id, read from the project so ids can never drift."""
    path = os.path.join(ROOT, "project", "variables.gbsres")
    if not os.path.exists(path):
        fail(f"missing {path}")
    names = {}
    for v in load_json(path).get("variables", []):
        names[v["name"]] = v["id"]
    missing = [n for n in REQUIRED_VARS if n not in names]
    if missing:
        fail("project/variables.gbsres is missing required variables: "
             + ", ".join(missing))
    return names


SPRITE_DIR = os.path.join(ROOT, "assets", "sprites")


def load_sprites():
    """png file -> sprite sheet id, keyed the way enemies.yaml names sprites.

    The key is the path under assets/sprites/ ("actor.png", or
    "enemies/coffee.png" in a subfolder), not GB Studio's internal sprite
    *name*, so the YAML points at a file you can actually open.
    """
    sprites = {}
    pattern = os.path.join(SPRITE_DIR, "**", "*.png.gbsres")
    for sidecar in glob.glob(pattern, recursive=True):
        png = sidecar[:-len(".gbsres")]
        if not os.path.exists(png):
            continue  # sidecar without its image; GB Studio ignores it too
        sprites[os.path.relpath(png, SPRITE_DIR)] = load_json(sidecar)["id"]
    return sprites


def find_battle_scene():
    """Locate the scene named "Battle" (falling back to scenes/battle/)."""
    for path in sorted(glob.glob(os.path.join(ROOT, "project", "scenes", "*",
                                              "scene.gbsres"))):
        if load_json(path).get("name", "").strip().lower() == "battle":
            return path
    fallback = os.path.join(ROOT, "project", "scenes", "battle", "scene.gbsres")
    if os.path.exists(fallback):
        return fallback
    fail("no scene named \"Battle\" found under project/scenes/ — create one "
         "in GB Studio first")


# --------------------------------------------------------------- yaml loading
def var_ref(var_id):
    """Text interpolation token for a global, e.g. "$13$"."""
    return f"${int(var_id):02d}$" if str(var_id).isdigit() else f"${var_id}$"


class Substituter:
    """Replaces {damage}-style placeholders in any text with variable refs.

    Lets the YAML say "It loses {damage} Composure." instead of "$13$", which
    would otherwise bake variable *indices* into the writing.
    """

    def __init__(self, variables):
        self.tokens = {
            name: var_ref(variables[name]) for name in
            ("player_composure", "player_composure_max", "enemy_composure",
             "enemy_composure_max", "battle_turn_count", "enemy_id")
        }
        self.tokens["damage"] = var_ref(variables["battle_damage"])
        self.tokens["turn"] = var_ref(variables["battle_turn_count"])

    def __call__(self, body):
        if isinstance(body, list):
            return [self(line) for line in body]
        if not isinstance(body, str):
            fail(f"expected text, got {body!r}")
        return re.sub(r"\{(\w+)\}",
                      lambda m: self.tokens.get(m.group(1), m.group(0)), body)


def as_variants(value, where):
    """Normalise a text field to [[step, ...], ...] — variants of steps.

    Canonical form is a list of lists: one variant is picked at random, then
    its steps play in order. A flat list of strings is one variant with those
    steps, and a bare string is one variant with one step.
    """
    if isinstance(value, str):
        return [[value]]
    if not isinstance(value, list) or not value:
        fail(f"{where}: expected a non-empty list of dialogue variants")
    if all(isinstance(v, str) for v in value):
        return [list(value)]
    if not all(isinstance(v, list) for v in value):
        fail(f"{where}: mixes strings and lists — write every variant as its "
             "own list of steps")
    variants = []
    for i, variant in enumerate(value):
        if not variant or not all(isinstance(s, str) for s in variant):
            fail(f"{where}[{i}]: a variant must be a non-empty list of strings")
        variants.append(list(variant))
    return variants


def dialogue(value, where, subst):
    """Validate a text field's shape, then interpolate its placeholders."""
    return [[subst(step) for step in variant]
            for variant in as_variants(value, where)]


def parse_range(value, where):
    """Accept 5, "3-6" or [3, 6] and return an inclusive (lo, hi)."""
    if isinstance(value, bool):
        fail(f"{where}: expected a damage range, got {value!r}")
    if isinstance(value, int):
        lo = hi = value
    elif isinstance(value, str):
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", value)
        if not m:
            fail(f"{where}: bad damage range {value!r} (use 5 or \"3-6\")")
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
    elif isinstance(value, list) and len(value) == 2 and all(
            isinstance(v, int) for v in value):
        lo, hi = value
    else:
        fail(f"{where}: bad damage range {value!r} (use 5, \"3-6\" or [3, 6])")
    if lo > hi:
        fail(f"{where}: damage range {value!r} is backwards")
    if hi > MAX_VAR_VALUE:
        fail(f"{where}: damage {hi} exceeds the 16-bit variable range")
    return lo, hi


def damage_value(lo, hi):
    """Script value for a uniform roll in [lo, hi]. rnd(n) yields 0..n-1."""
    if lo == hi:
        return num(lo)
    return add(num(lo), rnd(num(hi - lo + 1)))


def require(mapping, key, where):
    if key not in mapping:
        fail(f"{where}: missing required key '{key}'")
    return mapping[key]


class Effect:
    """One ACT verb's result against one enemy, or one enemy move."""

    def __init__(self, raw, where, subst):
        if isinstance(raw, dict):
            self.lo, self.hi = parse_range(require(raw, "damage", where), where)
            self.text = (dialogue(raw["text"], f"{where} text", subst)
                         if "text" in raw else None)
            unknown = set(raw) - {"damage", "text"}
            if unknown:
                fail(f"{where}: unknown keys {sorted(unknown)}")
        else:
            self.lo, self.hi = parse_range(raw, where)
            self.text = None


class Enemy:
    def __init__(self, raw, index, actions, sprites, subst):
        if not isinstance(raw, dict):
            fail(f"enemies[{index}]: expected a mapping")
        self.name = require(raw, "name", f"enemies[{index}]")
        where = f"enemy '{self.name}'"
        self.id = raw.get("id", index + 1)
        if not isinstance(self.id, int) or self.id < 1:
            fail(f"{where}: id must be a positive integer")

        sprite_name = require(raw, "sprite", where)
        if sprite_name not in sprites:
            hint = ""
            if f"{sprite_name}.png" in sprites:
                hint = f" Did you mean '{sprite_name}.png'?"
            fail(f"{where}: no sprite file 'assets/sprites/{sprite_name}'."
                 f"{hint} Available: " + ", ".join(sorted(sprites)))
        self.sprite_id = sprites[sprite_name]
        self.sprite_name = sprite_name

        self.composure = require(raw, "composure", where)
        if not isinstance(self.composure, int) or not (
                0 < self.composure <= MAX_VAR_VALUE):
            fail(f"{where}: composure must be a positive integer")

        self.intro = dialogue(require(raw, "intro", where),
                              f"{where} intro", subst)
        self.look = dialogue(require(raw, "look", where),
                             f"{where} look", subst)
        self.defeat = dialogue(require(raw, "defeat", where),
                               f"{where} defeat", subst)

        take_damage = require(raw, "take_damage", where)
        if not isinstance(take_damage, dict):
            fail(f"{where}: take_damage must be a mapping of action -> damage")
        unknown = [a for a in take_damage if a not in actions]
        if unknown:
            fail(f"{where}: take_damage has actions not in the top-level "
                 f"'actions' list: {unknown}")
        missing = [a for a in actions if a not in take_damage]
        if missing:
            fail(f"{where}: take_damage is missing {missing}")
        self.take_damage = {
            action: Effect(take_damage[action],
                           f"{where} take_damage.{action}", subst)
            for action in actions
        }

        moves = require(raw, "moves", where)
        if not isinstance(moves, list) or not moves:
            fail(f"{where}: moves must be a non-empty list")
        self.moves = []
        for i, move in enumerate(moves):
            if not isinstance(move, dict) or "text" not in move:
                fail(f"{where} moves[{i}]: expected a mapping with 'text' "
                     "and 'damage'")
            self.moves.append(Effect(move, f"{where} moves[{i}]", subst))

        self.can_flee = raw.get("can_flee", True)
        self.flee_blocked = raw.get("flee_blocked")
        if self.flee_blocked:
            self.flee_blocked = dialogue(self.flee_blocked,
                                         f"{where} flee_blocked", subst)
        self.win_flag = raw.get("win_flag")

        unknown = set(raw) - {
            "id", "name", "sprite", "composure", "intro", "look", "defeat",
            "take_damage", "moves", "can_flee", "flee_blocked", "win_flag"}
        if unknown:
            fail(f"{where}: unknown keys {sorted(unknown)}")


class Config:
    def __init__(self, raw, variables, sprites):
        if not isinstance(raw, dict):
            fail("enemies.yaml must be a mapping")
        subst = Substituter(variables)

        enemies_raw = require(raw, "enemies", "enemies.yaml")
        if not isinstance(enemies_raw, list) or not enemies_raw:
            fail("enemies.yaml: 'enemies' must be a non-empty list")

        self.actions = raw.get("actions")
        if self.actions is None:
            first = enemies_raw[0]
            self.actions = list(first.get("take_damage", {}))
        if not self.actions or not all(isinstance(a, str) for a in self.actions):
            fail("enemies.yaml: 'actions' must be a list of verb names")
        if len(self.actions) > 8:
            fail("enemies.yaml: GB Studio menus hold at most 8 options, "
                 f"got {len(self.actions)} actions")

        self.enemies = [Enemy(e, i, self.actions, sprites, subst)
                        for i, e in enumerate(enemies_raw)]
        seen_ids, seen_names = {}, {}
        for e in self.enemies:
            if e.id in seen_ids:
                fail(f"enemy id {e.id} used by both '{seen_ids[e.id]}' and "
                     f"'{e.name}'")
            seen_ids[e.id] = e.name
            if e.name in seen_names:
                fail(f"duplicate enemy name '{e.name}'")
            seen_names[e.name] = True

        player = raw.get("player") or {}
        self.player_composure = player.get("composure", 100)
        if not isinstance(self.player_composure, int) or not (
                0 < self.player_composure <= MAX_VAR_VALUE):
            fail("player.composure must be a positive integer")

        self.messages = dict(DEFAULT_MESSAGES)
        self.messages.update(raw.get("messages") or {})
        self.messages = {k: dialogue(v, f"messages.{k}", subst)
                         for k, v in self.messages.items()}

        self.menu = dict(DEFAULT_MENU)
        self.menu.update(raw.get("menu") or {})

        self.flee = dict(DEFAULT_FLEE)
        self.flee.update(raw.get("flee") or {})
        if not isinstance(self.flee["out_of"], int) or self.flee["out_of"] < 1:
            fail("flee.out_of must be a positive integer")
        if not isinstance(self.flee["chance"], int) or not (
                0 <= self.flee["chance"] <= self.flee["out_of"]):
            fail("flee.chance must be between 0 and flee.out_of")
        for key in ("success", "failed", "blocked"):
            self.flee[key] = dialogue(self.flee[key], f"flee.{key}", subst)

        self.lose = dialogue(raw.get("lose") or [
            "You have run out of\nComposure.",
            "You quietly gather\nyour things.",
        ], "lose", subst)

        self.win_flags = {}
        for e in self.enemies:
            if e.win_flag:
                if e.win_flag not in variables:
                    fail(f"enemy '{e.name}': win_flag '{e.win_flag}' is not a "
                         "variable in project/variables.gbsres")
                self.win_flags[e.id] = variables[e.win_flag]

        unknown = set(raw) - {"enemies", "actions", "player", "messages",
                              "menu", "flee", "lose", "battle", "bars"}
        if unknown:
            fail(f"enemies.yaml: unknown top-level keys {sorted(unknown)}")

        battle = raw.get("battle") or {}
        self.enemy_x = battle.get("x", 9)
        self.enemy_y = battle.get("y", 5)

        self.bars = self._read_bars(raw.get("bars"), sprites)

    def _read_bars(self, bars, sprites):
        """Optional Composure meters. Absent 'bars:' means none are generated.

        GB Studio has no hook that fires when a variable changes, so each bar
        is an actor that polls its variable in its own On Update script.
        """
        if not bars:
            return None
        if not isinstance(bars, dict):
            fail("enemies.yaml: 'bars' must be a mapping")
        sprite = require(bars, "sprite", "bars")
        if sprite not in sprites:
            fail(f"bars: no sprite file 'assets/sprites/{sprite}'. Available: "
                 + ", ".join(sorted(sprites)))
        frames = bars.get("frames", 17)
        if not isinstance(frames, int) or frames < 2:
            fail("bars.frames must be an integer of 2 or more (one sprite "
                 "frame per fill level, empty through full)")
        # frame = composure * (frames - 1) / max, computed in 16-bit ints.
        headroom = MAX_VAR_VALUE // (frames - 1)
        if self.player_composure > headroom:
            fail(f"bars: player.composure {self.player_composure} × "
                 f"{frames - 1} frames overflows a 16-bit variable")
        for e in self.enemies:
            if e.composure > headroom:
                fail(f"bars: enemy '{e.name}' composure {e.composure} × "
                     f"{frames - 1} frames overflows a 16-bit variable")
        unknown = set(bars) - {"sprite", "frames", "width", "height",
                               "player", "enemy"}
        if unknown:
            fail(f"bars: unknown keys {sorted(unknown)}")
        place = lambda key, dx, dy: ((bars.get(key) or {}).get("x", dx),
                                     (bars.get(key) or {}).get("y", dy))
        return {
            "sprite": sprite,
            "sprite_id": sprites[sprite],
            "frames": frames,
            "player": place("player", 1, 15),
            "enemy": place("enemy", 11, 3),
        }


def build_setbar_script(cfg):
    """The "SetBar" custom script: show `value`/`max` on a bar actor.

    Kept as its own script rather than inlined so a hand-written script can
    refresh a bar too — drag SetBar in, pick the actor, pass the two values.
    """
    return [
        comment("Generated by tools/gen_enemies.py — sets a Composure bar's "
                "frame from a value and its maximum"),
        actor_set_frame("0", bar_fill_expression(cfg.bars["frames"],
                                                 SETBAR_VALUE_SLOT,
                                                 SETBAR_MAX_SLOT)),
    ]


def make_set_bar(cfg, V, setbar_id):
    """Emit a SetBar call, forwarding one of BattleScript's bar parameters."""

    def set_bar(slot, value_name, max_name):
        if not cfg.bars:
            return []
        return [call_custom(setbar_id, {
            f"$actor[0]$": slot,
            f"$variable[{SETBAR_VALUE_SLOT}]$": var(V[value_name]),
            f"$variable[{SETBAR_MAX_SLOT}]$": var(V[max_name]),
        })]

    return set_bar


# ----------------------------------------------------------- script generation
def build_battle_script(cfg, V, setbar_id):
    """The whole fight, as one GB Studio custom script."""
    say = make_say(V["battle_temp"])
    set_bar = make_set_bar(cfg, V, setbar_id)

    def per_enemy(body_of):
        """Branch on enemy_id, one case per enemy."""
        return dispatch(var(V["enemy_id"]),
                        [(e.id, body_of(e)) for e in cfg.enemies])

    s = [comment("Generated by tools/gen_enemies.py from enemies.yaml — "
                 "edits made here will be overwritten")]

    # --- setup: look up the enemy the overworld asked for -------------------
    s.append(comment("Load enemy from enemy_id"))
    s += per_enemy(lambda e: [
        set_var(V["enemy_composure"], num(e.composure)),
        set_var(V["enemy_composure_max"], num(e.composure)),
        actor_set_sprite(ENEMY_ACTOR_SLOT, e.sprite_id),
    ] + set_bar(ENEMY_BAR_SLOT, "enemy_composure", "enemy_composure_max")
      + say(e.intro))

    s += [
        set_var(V["player_composure"], num(cfg.player_composure)),
        set_var(V["player_composure_max"], num(cfg.player_composure)),
        set_var(V["battle_turn_count"], num(0)),
        set_var(V["battle_result"], num(RESULT_ONGOING)),
    ] + set_bar(PLAYER_BAR_SLOT, "player_composure", "player_composure_max")

    # --- one round ----------------------------------------------------------
    turn = [
        set_var(V["battle_turn_count"],
                add(var(V["battle_turn_count"]), num(1))),
        set_var(V["battle_damage"], num(0)),
        *say(cfg.messages["status"]),
        menu(V["battle_menu_choice"],
             [cfg.menu["act"], cfg.menu["look"], cfg.menu["flee"]],
             layout="menu"),
    ]

    # ACT — pick a verb, look up what it does to this enemy.
    def verbs_against(e):
        cases = []
        for i, action in enumerate(cfg.actions):
            effect = e.take_damage[action]
            body = say(effect.text) if effect.text else []
            body.append(set_var(V["battle_damage"],
                                damage_value(effect.lo, effect.hi)))
            cases.append((i + 1, body))
        return dispatch(var(V["battle_act_choice"]), cases)

    act = [menu(V["battle_act_choice"], cfg.actions, layout="dialogue")]
    act += per_enemy(verbs_against)
    act += [
        set_var(V["enemy_composure"],
                vmax(num(0), sub(var(V["enemy_composure"]),
                                 var(V["battle_damage"])))),
    ] + set_bar(ENEMY_BAR_SLOT, "enemy_composure", "enemy_composure_max") + [
        if_value(gt(var(V["battle_damage"]), num(0)),
                 say(cfg.messages["hit"]),
                 say(cfg.messages["no_effect"])),
    ]

    # LOOK — flavour only; costs no turn.
    look = per_enemy(lambda e: say(e.look))

    # FLEE — per enemy, either a dice roll or a flat refusal.
    def flee_from(e):
        if not e.can_flee:
            return say(e.flee_blocked or cfg.flee["blocked"])
        return [
            set_var(V["battle_temp"], rnd(num(cfg.flee["out_of"]))),
            if_value(
                lt(var(V["battle_temp"]), num(cfg.flee["chance"])),
                say(cfg.flee["success"])
                + [set_var(V["battle_result"], num(RESULT_FLED))],
                say(cfg.flee["failed"]),
            ),
        ]

    flee = per_enemy(flee_from)

    turn.append(if_value(
        eq(var(V["battle_menu_choice"]), num(1)), act,
        [if_value(eq(var(V["battle_menu_choice"]), num(2)), look, flee)]))

    # Win check runs before the enemy replies, so a killing blow ends it.
    turn.append(if_value(lte(var(V["enemy_composure"]), num(0)),
                         [set_var(V["battle_result"], num(RESULT_WIN))]))

    # --- enemy turn (skipped after LOOK, a successful flee, or a win) -------
    def moves_of(e):
        cases = []
        for i, move in enumerate(e.moves):
            hit = say(move.text) + [
                set_var(V["battle_damage"], damage_value(move.lo, move.hi)),
                set_var(V["player_composure"],
                        vmax(num(0), sub(var(V["player_composure"]),
                                         var(V["battle_damage"])))),
            ] + set_bar(PLAYER_BAR_SLOT, "player_composure",
                        "player_composure_max")
            hit.append(if_value(gt(var(V["battle_damage"]), num(0)),
                                say(cfg.messages["player_hit"])))
            cases.append((i, hit))
        # catch_all: the roll covers every move, and a move's own dialogue may
        # re-roll battle_temp, so the last case must not be re-tested.
        return ([set_var(V["battle_temp"], rnd(num(len(e.moves))))]
                + dispatch(var(V["battle_temp"]), cases, catch_all=True))

    enemy_turn = per_enemy(moves_of)

    turn.append(if_value(
        vand(ne(var(V["battle_menu_choice"]), num(2)),
             eq(var(V["battle_result"]), num(RESULT_ONGOING))),
        enemy_turn))

    turn.append(if_value(lte(var(V["player_composure"]), num(0)),
                         [set_var(V["battle_result"], num(RESULT_LOST))]))

    s.append(loop_while(eq(var(V["battle_result"]), num(RESULT_ONGOING)), turn))

    # --- resolution ---------------------------------------------------------
    def defeat_of(e):
        body = say(e.defeat)
        if e.id in cfg.win_flags:
            body.append(set_var(cfg.win_flags[e.id], num(1)))
        return body

    win = per_enemy(defeat_of)
    lose = say(cfg.lose)

    s.append(if_value(
        eq(var(V["battle_result"]), num(RESULT_WIN)), win,
        [if_value(eq(var(V["battle_result"]), num(RESULT_LOST)), lose)]))

    # Return to whichever scene pushed its state before the fight.
    s.append(pop_state())
    return s


# ------------------------------------------------------------------- emitting
_ID_NS = uuid.UUID("d5f7a1e2-2222-4000-8000-000000000000")


def stable_id(key):
    return str(uuid.uuid5(_ID_NS, key))


def write_setbar_resource(cfg, dry_run):
    """The SetBar custom script — only written when bars are configured."""
    if not cfg.bars:
        return None, None
    setbar_id = stable_id("setbar")
    resource = {
        "_resourceType": "script",
        "id": setbar_id,
        "name": SETBAR_NAME,
        "description": "Generated by tools/gen_enemies.py from enemies.yaml.",
        "variables": {
            SETBAR_VALUE_SLOT: {"id": SETBAR_VALUE_SLOT, "name": "Value",
                                "passByReference": False},
            SETBAR_MAX_SLOT: {"id": SETBAR_MAX_SLOT, "name": "Max",
                              "passByReference": False},
        },
        "actors": {"0": {"id": "0", "name": "Bar"}},
        "symbol": SETBAR_SYMBOL,
        "script": build_setbar_script(cfg),
    }
    path = os.path.join(ROOT, "project", "scripts", "setbar.gbsres")
    if not dry_run:
        save_json(path, resource)
    return setbar_id, path


def write_script_resource(cfg, V, setbar_id, dry_run):
    script_id = stable_id("battlescript")
    actors = {ENEMY_ACTOR_SLOT: {"id": ENEMY_ACTOR_SLOT,
                                 "name": ENEMY_ACTOR_NAME}}
    if cfg.bars:
        actors[PLAYER_BAR_SLOT] = {"id": PLAYER_BAR_SLOT,
                                   "name": PLAYER_BAR_NAME}
        actors[ENEMY_BAR_SLOT] = {"id": ENEMY_BAR_SLOT,
                                  "name": ENEMY_BAR_NAME}
    resource = {
        "_resourceType": "script",
        "id": script_id,
        "name": SCRIPT_NAME,
        "description": "Generated by tools/gen_enemies.py from enemies.yaml.",
        "variables": {},
        "actors": actors,
        "symbol": SCRIPT_SYMBOL,
        "script": build_battle_script(cfg, V, setbar_id),
    }
    path = os.path.join(ROOT, "project", "scripts", "battlescript.gbsres")
    if not dry_run:
        save_json(path, resource)
    return script_id, path, resource["script"]


def write_actor(scene_dir, key, name, index, sprite_id, pos, dry_run,
                update_script=(), pinned=False,
                anim_speed=ANIM_SPEED_DEFAULT):
    """Write one battle-scene actor.

    An existing file keeps its position, so nudging an actor in the GUI
    survives a regeneration; everything else is regenerated.
    """
    path = os.path.join(scene_dir, "actors", f"{key}.gbsres")
    existing = load_json(path) if os.path.exists(path) else {}
    actor = {
        "_resourceType": "actor",
        "id": existing.get("id", stable_id(f"battle_{key}_actor")),
        "_index": index,
        "name": name,
        "symbol": f"actor_battle_{index}",
        "prefabId": "",
        "coordinateType": "tiles",
        "x": existing.get("x", pos[0]),
        "y": existing.get("y", pos[1]),
        "frame": 0,
        "direction": "down",
        "spriteSheetId": sprite_id,
        "moveSpeed": 1,
        "animSpeed": anim_speed,
        "paletteId": "",
        "isPinned": pinned,
        "persistent": False,
        "collisionGroup": "",
        "collisionExtraFlags": [],
        "prefabScriptOverrides": {},
        "animate": False,
        "script": [],
        "startScript": [],
        "updateScript": list(update_script),
        "hit1Script": [],
        "hit2Script": [],
        "hit3Script": [],
    }
    if not dry_run:
        save_json(path, actor)
    return actor["id"], path


# Placeholder bar art. GB Studio sprite tiles are 8x16, so a bar cell is
# CELL_H tall and its width must divide into 8px columns.
CELL_H = 16
BAR_TRANSPARENT = (101, 255, 0)   # #65FF00 — GB Studio's sprite colour key
BAR_DARK = (7, 24, 33)
BAR_FILL = (134, 192, 108)
BAR_EMPTY = (224, 248, 207)
_ART_NS = uuid.UUID("d5f7a1e2-3333-4000-8000-000000000000")


def draw_bar_art(bars, dry_run):
    """Redraw the placeholder bar strip and its sprite sidecar from `bars:`.

    Separate from the normal run because the art is an *asset*: once drawn (or
    replaced with real art at the same dimensions) it just sits in
    assets/sprites/ like any other sprite. Regenerate when the width, height or
    frame count changes.
    """
    try:
        from PIL import Image
    except ImportError:
        fail("--draw-bar-art needs Pillow: pip install pillow")

    if not isinstance(bars, dict):
        fail("--draw-bar-art needs a 'bars:' section in enemies.yaml")
    name = require(bars, "sprite", "bars")
    frames = bars.get("frames", 17)
    width = bars.get("width", 64)
    height = bars.get("height", 8)
    if not isinstance(width, int) or width % 8 or not (8 <= width <= 160):
        fail("bars.width must be a multiple of 8 between 8 and 160 (the "
             "screen is 160px; each 8px column costs one hardware sprite)")
    if not isinstance(height, int) or not (2 <= height <= CELL_H):
        fail(f"bars.height must be between 2 and {CELL_H}")
    if not isinstance(frames, int) or frames < 2:
        fail("bars.frames must be an integer of 2 or more")

    steps = frames - 1
    top = (CELL_H - height) // 2
    img = Image.new("RGB", (width * frames, CELL_H), BAR_TRANSPARENT)
    px = img.load()
    for k in range(frames):
        ox = k * width
        filled = width * k // steps
        for x in range(width):
            px[ox + x, top] = BAR_DARK                  # top rule
            px[ox + x, top + height - 1] = BAR_DARK     # bottom rule
            for y in range(top + 1, top + height - 1):
                px[ox + x, y] = BAR_FILL if x < filled else BAR_EMPTY

    png_path = os.path.join(SPRITE_DIR, name)
    sidecar_path = png_path + ".gbsres"
    columns = width // 8
    sid = lambda k: str(uuid.uuid5(_ART_NS, f"{name}:{k}"))

    # Tile x/y are ORIGIN-relative, not canvas-relative. GB Studio's tile
    # optimiser masks each tile at (originX + x, originY - y) against a
    # canvas-sized image, where originX = canvasWidth / 2 - 8 (readSpriteData.ts)
    # — so a canvas-relative x pushes the right-hand tiles outside the mask,
    # where they are marked Unknown, and Unknown matches *any* tile during
    # deduplication. Every frame then renders as the same scrambled tiles.
    # (At canvasWidth 16 originX is 0 and the two conventions coincide, which
    # is why a narrow bar worked.)
    origin_x = 0 if width < 16 else width // 2 - 8

    def tile(k, col):
        return {"id": sid(f"tile{k}.{col}"), "x": col * 8 - origin_x, "y": 0,
                "sliceX": k * width + col * 8, "sliceY": 0,
                "flipX": False, "flipY": False, "palette": 0,
                "paletteIndex": 0, "objPalette": "OBP0", "priority": False}

    # A "fixed" state still carries eight animation slots; only the first runs.
    animations = [{"id": sid("anim0"), "frames": [
        {"id": sid(f"frame{k}"), "tiles": [tile(k, c) for c in range(columns)]}
        for k in range(frames)]}]
    animations += [{"id": sid(f"anim{i}"),
                    "frames": [{"id": sid(f"empty{i}"), "tiles": []}]}
                   for i in range(1, 8)]

    sprite = {
        "_resourceType": "sprite",
        "id": sid("sprite"),
        "name": name[:-len(".png")] if name.endswith(".png") else name,
        "symbol": "sprite_" + slugify(name.rsplit(".", 1)[0]),
        "states": [{"id": sid("state"), "name": "", "animationType": "fixed",
                    "flipLeft": False, "animations": animations}],
        "numTiles": frames * columns,
        "canvasOriginX": 0, "canvasOriginY": 0,
        "canvasWidth": width, "canvasHeight": CELL_H,
        "boundsX": 0, "boundsY": 0,
        "boundsWidth": width, "boundsHeight": height,
        "animSpeed": ANIM_SPEED_NONE,
        "filename": name,
        # GB Studio recomputes width/height/checksum/inode on load; the frame
        # slicing above is what it keeps.
        "width": width * frames, "height": CELL_H, "checksum": "",
    }
    if not dry_run:
        os.makedirs(os.path.dirname(png_path), exist_ok=True)
        img.convert("P", palette=Image.ADAPTIVE, colors=4).save(png_path)
        save_json(sidecar_path, sprite)
    return png_path, frames, width, columns


def slugify(name):
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def bar_fill_expression(frames, value_var, max_var):
    """Frame index for a Composure value: which fill level to show.

    Ceiling, not truncation: (value * steps + divisor - 1) / divisor, so a
    player on 1 Composure still shows a sliver and only a real 0 reads empty.
    The divisor is floored at 1 so the bar is harmless before a maximum is set.
    """
    divisor = vmax(num(1), var(max_var))
    return div(add(mul(var(value_var), num(frames - 1)), sub(divisor, num(1))),
               divisor)


def write_battle_actors(cfg, V, scene_dir, dry_run):
    """The Enemy actor, plus the two Composure bars when 'bars:' is set."""
    written = []
    bars = {}
    enemy_id, path = write_actor(
        scene_dir, "enemy", ENEMY_ACTOR_NAME, 0,
        # Placeholder only — BattleScript sets the real sprite on init.
        cfg.enemies[0].sprite_id, (cfg.enemy_x, cfg.enemy_y), dry_run)
    written.append((ENEMY_ACTOR_NAME, path))

    if cfg.bars:
        for index, (key, name, slot, pos) in enumerate((
            ("playerbar", PLAYER_BAR_NAME, PLAYER_BAR_SLOT,
             cfg.bars["player"]),
            ("enemybar", ENEMY_BAR_NAME, ENEMY_BAR_SLOT, cfg.bars["enemy"]),
        ), start=1):
            # No On Update script: the battle runs inside the scene's On Init,
            # which the compiler emits with VM_LOCK, and a locked context is
            # the *only* one the VM scheduler runs. An update script here would
            # never execute a single instruction. BattleScript calls SetBar
            # instead, at each Composure change.
            bar_id, path = write_actor(
                scene_dir, key, name, index, cfg.bars["sprite_id"], pos,
                dry_run, pinned=True, anim_speed=ANIM_SPEED_NONE)
            bars[slot] = bar_id
            written.append((name, path))
    return enemy_id, bars, written


def wire_battle_scene(scene_path, script_id, actor_id, bars, dry_run):
    """Point the battle scene's On Init at BattleScript, actors bound."""
    scene = load_json(scene_path)
    args = {f"$actor[{ENEMY_ACTOR_SLOT}]$": actor_id}
    for slot, bar_id in bars.items():
        args[f"$actor[{slot}]$"] = bar_id
    scene["script"] = [call_custom(script_id, args)]
    if not dry_run:
        save_json(scene_path, scene)
    return scene_path


# ------------------------------------------------------------------ simulation
# Balance is checked by *interpreting the generated event tree* rather than by
# re-implementing the damage rules, so what gets measured is what ships.
def _eval(value, V):
    kind = value["type"]
    if kind == "number":
        return value["value"]
    if kind == "variable":
        return V.get(value["value"], 0)
    if kind == "rnd":
        return random.randrange(_eval(value["value"], V))
    a, b = _eval(value["valueA"], V), _eval(value["valueB"], V)
    ops = {
        "add": lambda: a + b, "sub": lambda: a - b, "max": lambda: max(a, b),
        "mul": lambda: a * b,
        # GBVM divides integers, truncating; the generator floors divisors at 1.
        "div": lambda: a // b if b else 0,
        "eq": lambda: int(a == b), "ne": lambda: int(a != b),
        "gt": lambda: int(a > b), "lt": lambda: int(a < b),
        "lte": lambda: int(a <= b), "and": lambda: int(bool(a) and bool(b)),
    }
    if kind not in ops:
        fail(f"simulation: unhandled script value '{kind}'")
    return ops[kind]()


def _run(events, V, choose, budget):
    for e in events:
        command, args = e["command"], e.get("args", {})
        children = e.get("children", {})
        if command == "EVENT_SET_VALUE":
            V[args["variable"]] = _eval(args["value"], V)
        elif command == "EVENT_IF":
            branch = "true" if _eval(args["condition"], V) else "false"
            _run(children.get(branch, []), V, choose, budget)
        elif command == "EVENT_LOOP_WHILE":
            while _eval(args["condition"], V):
                budget["turns"] -= 1
                if budget["turns"] < 0:
                    raise RuntimeError("battle never ended")
                _run(children["true"], V, choose, budget)
        elif command == "EVENT_MENU":
            options = [args[f"option{i + 1}"] for i in range(args["items"])]
            V[args["variable"]] = choose(args["variable"], options)
        elif command == "EVENT_SCENE_POP_STATE":
            return
        elif command not in ("EVENT_TEXT", "EVENT_COMMENT",
                             "EVENT_ACTOR_SET_SPRITE", "EVENT_ACTOR_SET_FRAME",
                             # SetBar only moves a sprite frame
                             "EVENT_CALL_CUSTOM_EVENT"):
            fail(f"simulation: unhandled event '{command}'")


def simulate(cfg, V, script, runs):
    """Win rate and average turn count per strategy, per enemy."""
    strategies = ["random"] + list(cfg.actions)
    width = max(12, max(len(s) for s in strategies) + 6)
    header = f"{'enemy':>16}" + "".join(f"{s:>{width}}" for s in strategies)
    print("\nbalance (%d games per cell)\n%s" % (runs, header))

    for enemy in cfg.enemies:
        row = f"{enemy.name:>16}"
        for strategy in strategies:
            wins, turns = 0, 0
            for _ in range(runs):
                state = {V["enemy_id"]: enemy.id}

                def choose(variable, options, strategy=strategy):
                    if variable == V["battle_menu_choice"]:
                        return 1  # always ACT
                    if strategy == "random":
                        return random.randrange(1, len(options) + 1)
                    return options.index(strategy) + 1

                _run(script, state, choose, {"turns": 500})
                wins += state[V["battle_result"]] == RESULT_WIN
                turns += state[V["battle_turn_count"]]
            row += f"{100 * wins / runs:>{width - 6}.1f}% {turns / runs:>4.1f}t"
        print(row)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--enemies", default=os.path.join(ROOT, "enemies.yaml"),
                    help="path to enemies.yaml (default: repo root)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and report without writing any file")
    ap.add_argument("--draw-bar-art", action="store_true",
                    help="redraw the placeholder Composure bar strip and its "
                         "sprite sidecar from the 'bars:' section, then carry "
                         "on as normal")
    ap.add_argument("--simulate", nargs="?", type=int, const=2000,
                    metavar="RUNS",
                    help="play the generated script RUNS times per strategy "
                         "and report win rates (default 2000)")
    args = ap.parse_args()

    if not os.path.exists(args.enemies):
        fail(f"no such file: {args.enemies}")
    with open(args.enemies) as f:
        raw = yaml.safe_load(f)

    if args.draw_bar_art:
        png, frames, width, columns = draw_bar_art(raw.get("bars"),
                                                   args.dry_run)
        print(f"{'would draw' if args.dry_run else 'drew'} "
              f"{os.path.relpath(png, ROOT)}  ({frames} frames, {width}px "
              f"wide = {columns} hardware sprites per bar)")

    variables = load_variables()
    sprites = load_sprites()
    if not sprites:
        fail("no sprites found under assets/sprites/")
    cfg = Config(raw, variables, sprites)
    V = {name: variables[name] for name in REQUIRED_VARS}

    scene_path = find_battle_scene()
    scene_dir = os.path.dirname(scene_path)

    setbar_id, setbar_path = write_setbar_resource(cfg, args.dry_run)
    script_id, script_path, script = write_script_resource(
        cfg, V, setbar_id, args.dry_run)
    actor_id, bars, actors = write_battle_actors(cfg, V, scene_dir,
                                                 args.dry_run)
    wire_battle_scene(scene_path, script_id, actor_id, bars, args.dry_run)

    prefix = "would write" if args.dry_run else "wrote"
    rel = lambda p: os.path.relpath(p, ROOT)
    print(f"{prefix} {rel(script_path)}  ({SCRIPT_NAME}, "
          f"{len(cfg.enemies)} enemies, {len(cfg.actions)} actions)")
    if setbar_path:
        print(f"{prefix} {rel(setbar_path)}  ({SETBAR_NAME}: bar actor, "
              "value, max)")
    for name, path in actors:
        print(f"{prefix} {rel(path)}  ({name} actor)")
    print(f"{prefix} {rel(scene_path)}  (On Init -> {SCRIPT_NAME})")
    if cfg.bars:
        print(f"  bars: {cfg.bars['sprite']}, {cfg.bars['frames']} frames, "
              f"set via {SETBAR_NAME} at each Composure change")
    for e in cfg.enemies:
        flags = "" if e.can_flee else ", no flee"
        print(f"  #{e.id} {e.name}: composure {e.composure}, "
              f"sprite {e.sprite_name}, {len(e.moves)} moves{flags}")

    if args.simulate:
        simulate(cfg, V, script, args.simulate)


if __name__ == "__main__":
    main()

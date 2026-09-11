#!/usr/bin/env python3
"""Generate the DeskBound GB Studio project resources.

Authoring GB Studio scenes/scripts as JSON by hand is unreadable, so the game
content lives here as Python data and is compiled into .gbsres files.

Run:  python3 tools/gen_placeholder_art.py && python3 tools/build_project.py

Design reference: DESIGN.md
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbs
from gbs import (
    num, var, add, sub, mul, div, rnd, vmax, eq, gt, gte, lt, lte,
    text, set_var, if_value, menu, switch_scene, call_custom, wait,
    shake, comment, fade_in, compress_8bit, COLLISION_ALL, COLLISION_NONE,
)

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ------------------------------------------------------------------ variables
# Index into project/variables.gbsres — GB Studio references globals by number.
V = {
    "player_composure": 0, "player_composure_max": 1, "player_nerve": 2,
    "player_patience": 3,
    "enemy_id": 4, "enemy_composure": 5, "enemy_composure_max": 6,
    "enemy_nerve": 7, "enemy_patience": 8, "enemy_last_move": 9,
    "battle_menu_choice": 10, "battle_act_choice": 11, "battle_power": 12,
    "battle_damage": 13, "battle_temp": 14, "battle_result": 15,
    "battle_turn_count": 16, "battle_heal": 17,
    "bar_filled": 18, "bar_temp": 19,
    "story_flag_coffee": 20, "story_flag_printer": 21, "story_flag_boss": 22,
    "loss_count": 23,
}

# Player baseline. Generous on purpose — see DESIGN.md §9.1.
PLAYER_COMPOSURE = 100
PLAYER_NERVE = 8
PLAYER_PATIENCE = 12

# Weakest verbs still chip, so no enemy can become unwinnable by stubbornness.
# Verified by simulation: every strategy wins ~100% of fights. See §9.1.
# The boss needs a higher floor: its weak verb (FIX) has no heal attached, so
# a player who locks onto FIX would otherwise lose ~78% of the time.
WEAK_VERB_FLOOR = 3
BOSS_VERB_FLOOR = 7
# Boss SHRUG heals AND chips — without the chip, SHRUG-spam is an infinite
# stalemate (simulated: 800/800 stalls at chip 0, 0 stalls at chip 2).
BOSS_SHRUG_CHIP = 2
BOSS_SHRUG_HEAL = 12
# Enemy damage is scaled down so fights last long enough to show the jokes.
ENEMY_DAMAGE_SCALE_NUM, ENEMY_DAMAGE_SCALE_DEN = 7, 10

COFFEE, PRINTER, MEETING = 1, 2, 3

ENEMIES = {
    COFFEE: {
        "name": "Coffee Machine",
        "composure": 60, "nerve": 6, "patience": 4,
        "intro": "A DIRTY COFFEE MACHINE\nblocks the counter.\nIt is encrusted.",
        "look": "Beneath the grime, a\nsticker: \"CLEAN ME :)\"\nIt is from 2019.",
        "defeat": "The coffee machine is\ndefeated. It dispenses,\nfinally, a decent cup.",
        # verb -> (power, flavour). Power 0 = no damage.
        "acts": {
            1: (12, "You descale it. It\nshudders with something\nlike relief."),
            2: (4,  "You talk to it. It\ngurgles noncommittally."),
            3: (2,  "You email Facilities.\nAuto-closed as a\nduplicate ticket."),
            4: (10, "You drink it black and\nbitter, like it wants.\nIt respects this."),
        },
        "moves": [
            (5, "It dispenses something\nat exactly body\ntemperature.", "dmg"),
            (3, "It drips. Onto the\ncounter you just\ncleaned.", "dmg"),
            (0, "OUT OF BEANS, it\nannounces, with beans\nclearly visible.", "nerve"),
        ],
    },
    PRINTER: {
        "name": "The Printer",
        "composure": 65, "nerve": 9, "patience": 8,
        "intro": "THE PRINTER stirs.\nIt has never worked.\nIt is not sorry.",
        "look": "Tray 2 is open. Tray 2\nis always open. There is\nnothing in tray 2.",
        "defeat": "The printer is defeated.\nIt prints your document.\nIt prints it correctly.",
        "acts": {
            1: (3,  "You open tray 2. There\nis no jam in tray 2.\nThere never is."),
            2: (0,  "You say \"please.\" It\nemits one sheet of a\ndocument from 2017."),
            3: (16, "You CC the office\nmanager. Bureaucracy is\nthe only language it fears."),
            4: (6,  "You walk away. It beeps,\nwounded by the\nindifference."),
        },
        "moves": [
            (7, "PC LOAD LETTER. Nobody\nhas ever known what\nthis means.", "dmg"),
            (6, "It reports a paper jam.\nThere is no paper.\nThere is no jam.", "dmg"),
            (0, "TONER LOW, it says,\nat 94% toner.", "nerve"),
        ],
    },
    MEETING: {
        "name": "The Meeting",
        "composure": 105, "nerve": 12, "patience": 10,
        "intro": "THE MEETING THAT COULD'VE\nBEEN AN EMAIL begins.\nIt has no agenda.",
        "look": "Twelve attendees. Eleven\nare on mute. One is\neating.",
        "defeat": "The meeting ends. It is\n17:02. You are free.\nYou go home.",
        "acts": {
            1: (5,  "You propose an agenda.\nSomeone says \"good point\"\nand continues."),
            2: (14, "You say the quiet part:\n\"Could this have been\nan email?\""),
            3: (8,  "You send the follow-up\nemail DURING the meeting.\nDeeply illegal. Effective."),
            4: (0,  "You stop resisting.\nYou let it wash over you."),  # heals, handled below
        },
        "moves": [
            (8, "Let's circle back to\nthat.", "dmg"),
            (7, "This'll be quick, it\nsays. It is 45 minutes.", "dmg"),
            (9, "Any other business?\nSomeone has other\nbusiness.", "dmg"),
        ],
    },
}

ACT_NAMES = {1: "FIX", 2: "TALK", 3: "EMAIL", 4: "SHRUG"}



def slugify(name, fallback):
    """Mirror GB Studio's resource filename rule: lowercase, spaces to
    underscores, invalid path characters stripped."""
    out = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name or "").strip()
    out = out.lower().replace(" ", "_")
    return out or fallback


# ------------------------------------------------------------------ collisions
SCENE_W, SCENE_H = 20, 18


def solid_border(openings=()):
    """Mark the 1-tile border solid, except for the given door openings.

    `openings` is a list of (x, y, w, h) rects left walkable. Without this the
    player can stroll off the edge of every room — scene.collisions was empty
    before, which meant nothing at all was solid.
    """
    grid = [[COLLISION_NONE] * SCENE_W for _ in range(SCENE_H)]
    for x in range(SCENE_W):
        grid[0][x] = COLLISION_ALL
        grid[SCENE_H - 1][x] = COLLISION_ALL
    for y in range(SCENE_H):
        grid[y][0] = COLLISION_ALL
        grid[y][SCENE_W - 1] = COLLISION_ALL
    for (ox, oy, ow, oh) in openings:
        for y in range(oy, min(oy + oh, SCENE_H)):
            for x in range(ox, min(ox + ow, SCENE_W)):
                grid[y][x] = COLLISION_NONE
    return compress_8bit([c for row in grid for c in row])


# ------------------------------------------------------------------ bar drawing
def health_bar_text(label, cur_var, max_var):
    """GB Studio renders %D-style variable interpolation in dialogue.

    A real pixel bar would need tiles; showing the numbers is honest, readable
    and costs nothing. Format: "COMPOSURE  34/60".
    """
    return f"{label}\\n${cur_var}$/${max_var}$"


# ------------------------------------------------------------------ battle script
def build_battle_script(scene_ids):
    """The whole turn loop for the shared battle scene.

    Structure:
        on init -> load enemy stats by enemy_id -> intro text
                -> LOOP { player turn ; enemy turn ; win/lose checks }
    """
    s = []
    s.append(comment("DeskBound battle — generated by tools/build_project.py"))

    # --- load enemy stats -----------------------------------------------
    s.append(comment("Load enemy stats from enemy_id"))
    for eid_, e in ENEMIES.items():
        s.append(if_value(
            eq(var(V["enemy_id"]), num(eid_)),
            [
                set_var(V["enemy_composure"], num(e["composure"])),
                set_var(V["enemy_composure_max"], num(e["composure"])),
                set_var(V["enemy_nerve"], num(e["nerve"])),
                set_var(V["enemy_patience"], num(e["patience"])),
                text(e["intro"]),
            ],
        ))

    # player stats fresh each battle (difficulty: always winnable)
    s.append(set_var(V["player_composure"], num(PLAYER_COMPOSURE)))
    s.append(set_var(V["player_composure_max"], num(PLAYER_COMPOSURE)))
    s.append(set_var(V["player_nerve"], num(PLAYER_NERVE)))
    s.append(set_var(V["player_patience"], num(PLAYER_PATIENCE)))
    s.append(set_var(V["battle_turn_count"], num(0)))
    s.append(set_var(V["battle_result"], num(0)))

    # --- main loop -------------------------------------------------------
    turn = []
    turn.append(set_var(V["battle_turn_count"],
                        add(var(V["battle_turn_count"]), num(1))))

    # Status line, shown every round so the player can read the fight.
    turn.append(text(
        f"YOU  ${V['player_composure']}$/${V['player_composure_max']}$\\n"
        f"THEM ${V['enemy_composure']}$/${V['enemy_composure_max']}$"
    ))

    # ---- top level menu: ACT / LOOK / FLEE
    turn.append(menu(V["battle_menu_choice"], ["ACT", "LOOK", "FLEE"],
                     layout="menu", cancel_on_b=False))

    # LOOK — flavour only, does NOT consume the turn (DESIGN.md §3.2)
    look_branch = []
    for eid_, e in ENEMIES.items():
        look_branch.append(if_value(
            eq(var(V["enemy_id"]), num(eid_)),
            [text(e["look"])],
        ))

    # FLEE
    flee_branch = []
    boss_refusals = [
        "You can't leave. It's\nin your calendar.",
        "You stand up. Eleven\npeople look at you.\nYou sit back down.",
        "The invite has no\ndecline button. You\ncheck. Twice.",
    ]
    flee_branch.append(if_value(
        eq(var(V["enemy_id"]), num(MEETING)),
        # Boss: always refused, costs no turn.
        [
            set_var(V["battle_temp"], rnd(num(3))),
            if_value(eq(var(V["battle_temp"]), num(0)),
                     [text(boss_refusals[0])],
                     [if_value(eq(var(V["battle_temp"]), num(1)),
                               [text(boss_refusals[1])],
                               [text(boss_refusals[2])])]),
        ],
        # Regular enemy: 75% success
        [
            set_var(V["battle_temp"], rnd(num(4))),
            if_value(
                gt(var(V["battle_temp"]), num(0)),
                [
                    text("You walk away. The\nproblem remains, but\nso do you."),
                    set_var(V["battle_result"], num(2)),
                ],
                [text("You get as far as the\ndoor and remember you\nneed coffee.")],
            ),
        ],
    ))

    # ACT — submenu of the four verbs
    act_branch = []
    act_branch.append(menu(V["battle_act_choice"],
                           ["FIX", "TALK", "EMAIL", "SHRUG"],
                           layout="dialogue", cancel_on_b=False))

    # per (enemy x verb) lookup -> power + flavour  (DESIGN.md §5.3)
    for eid_, e in ENEMIES.items():
        per_enemy = []
        for act_id, (power, flavour) in e["acts"].items():
            body = [text(flavour)]
            if eid_ == MEETING and act_id == 4:
                # SHRUG heals against the boss — and still chips, because a
                # pure heal makes SHRUG-spam an unwinnable stalemate.
                body.append(set_var(
                    V["player_composure"],
                    gbs.vmin(var(V["player_composure_max"]),
                             add(var(V["player_composure"]), num(BOSS_SHRUG_HEAL)))))
                body.append(text(f"You recover {BOSS_SHRUG_HEAL}\nComposure."))
                body.append(set_var(V["battle_power"], num(BOSS_SHRUG_CHIP)))
            else:
                # Floor weak verbs so no fight can become unwinnable.
                floor = BOSS_VERB_FLOOR if eid_ == MEETING else WEAK_VERB_FLOOR
                body.append(set_var(V["battle_power"], num(max(power, floor))))
            per_enemy.append(if_value(eq(var(V["battle_act_choice"]), num(act_id)), body))
        act_branch.append(if_value(eq(var(V["enemy_id"]), num(eid_)), per_enemy))

    # damage = max(1, power + nerve - patience/2 + rnd(4)), only if power > 0
    act_branch.append(if_value(
        gt(var(V["battle_power"]), num(0)),
        [
            set_var(V["battle_damage"], vmax(num(1), add(
                sub(add(var(V["battle_power"]), var(V["player_nerve"])),
                    div(var(V["enemy_patience"]), num(2))),
                rnd(num(4))))),
            set_var(V["enemy_composure"],
                    vmax(num(0), sub(var(V["enemy_composure"]), var(V["battle_damage"])))),
            # feedback by severity
            if_value(
                gte(var(V["battle_power"]), num(10)),
                [shake(), text("It reels. Something\nrattles loose.")],
                [if_value(lte(var(V["battle_power"]), num(3)),
                          [text("It barely notices.")],
                          [])],
            ),
        ],
    ))

    # dispatch the top menu
    turn.append(if_value(
        eq(var(V["battle_menu_choice"]), num(1)),
        act_branch,
        [if_value(eq(var(V["battle_menu_choice"]), num(2)),
                  look_branch,
                  flee_branch)],
    ))

    # ---- win check before the enemy acts (sets battle_result; the
    #      LOOP_WHILE condition below is what actually exits the fight)
    turn.append(if_value(
        lte(var(V["enemy_composure"]), num(0)),
        [set_var(V["battle_result"], num(1))],
    ))

    # ---- enemy turn (skipped if the player LOOKed, fled, or already won)
    enemy_turn = []
    enemy_turn.append(set_var(V["battle_temp"], rnd(num(3))))
    for eid_, e in ENEMIES.items():
        per_enemy = []
        for mi, (mpow, mline, mkind) in enumerate(e["moves"]):
            body = [text(mline)]
            if mkind == "dmg":
                body.append(set_var(V["battle_damage"], vmax(num(1), div(
                    mul(add(
                        sub(add(num(mpow), var(V["enemy_nerve"])),
                            div(var(V["player_patience"]), num(2))),
                        rnd(num(3))),
                        num(ENEMY_DAMAGE_SCALE_NUM)),
                    num(ENEMY_DAMAGE_SCALE_DEN)))))
                body.append(set_var(
                    V["player_composure"],
                    vmax(num(0), sub(var(V["player_composure"]), var(V["battle_damage"])))))
            else:
                # morale chip: lower player Nerve, floor at 4 so it can't stall out
                body.append(set_var(V["player_nerve"],
                                    vmax(num(4), sub(var(V["player_nerve"]), num(2)))))
            per_enemy.append(if_value(eq(var(V["battle_temp"]), num(mi)), body))
        enemy_turn.append(if_value(eq(var(V["enemy_id"]), num(eid_)), per_enemy))

    # low-composure warning
    enemy_turn.append(if_value(
        lte(var(V["player_composure"]), num(15)),
        [text("Your eye twitches.")],
    ))

    turn.append(if_value(
        gbs.vand(gbs.ne(var(V["battle_menu_choice"]), num(2)),   # LOOK is free
                 eq(var(V["battle_result"]), num(0))),          # still fighting
        enemy_turn,
    ))

    # lose check
    turn.append(if_value(
        lte(var(V["player_composure"]), num(0)),
        [set_var(V["battle_result"], num(3))],
    ))

    # battle_result: 0 = ongoing, 1 = win, 2 = fled, 3 = lost.
    # Any non-zero value ends the loop.
    s.append(gbs.loop_while(eq(var(V["battle_result"]), num(0)), turn))

    # --- resolution -------------------------------------------------------
    # WIN
    win = []
    for eid_, e in ENEMIES.items():
        flag = {COFFEE: "story_flag_coffee", PRINTER: "story_flag_printer",
                MEETING: "story_flag_boss"}[eid_]
        win.append(if_value(
            eq(var(V["enemy_id"]), num(eid_)),
            [text(e["defeat"]), set_var(V[flag], num(1))],
        ))

    # LOSE — comedic, never punishing (DESIGN.md §9.2)
    lose = [
        set_var(V["loss_count"], add(var(V["loss_count"]), num(1))),
        text("You have run out of\nComposure."),
        text("You quietly gather\nyour things."),
    ]
    lose.append(if_value(
        gte(var(V["loss_count"]), num(3)),
        [text("You go home early.\nAgain.\nHR has noticed.")],
        [if_value(eq(var(V["loss_count"]), num(2)),
                  [text("You go home early.\nAgain. Nobody notices.")],
                  [text("You go home. It's 14:30.\nNobody notices.")])],
    ))
    lose.append(text("Tomorrow, you try\nagain."))

    s.append(if_value(
        eq(var(V["battle_result"]), num(1)), win,
        [if_value(eq(var(V["battle_result"]), num(3)), lose, [])],
    ))

    # return to whichever room we came from
    ret = []
    for eid_, scene_key in ((COFFEE, "break_room"), (PRINTER, "print_station"),
                            (MEETING, "meeting_room")):
        ret.append(if_value(
            eq(var(V["enemy_id"]), num(eid_)),
            [switch_scene(scene_ids[scene_key], x=9, y=13, direction="down")],
        ))
    s.extend(ret)
    return s


# ------------------------------------------------------------------ scenes
def encounter_script(enemy_id, battle_scene_id, flag_var, already_text):
    """Actor script for an office thing: fight it, unless already beaten."""
    return [
        if_value(
            eq(var(V[flag_var]), num(1)),
            [text(already_text)],
            [
                set_var(V["enemy_id"], num(enemy_id)),
                switch_scene(battle_scene_id, x=0, y=0),
            ],
        )
    ]


def main():
    gbs.reset_ids()
    # Read background ids from the .gbsres sidecars rather than a temp file,
    # so the build is reproducible from a clean checkout.
    bg = {}
    for path in glob.glob(os.path.join(ROOT, "assets", "backgrounds", "*.png.gbsres")):
        data = json.load(open(path))
        bg[data["name"]] = data["id"]
    missing = {"title", "office_floor", "break_room", "print_station",
               "meeting_room", "battle_bg"} - set(bg)
    if missing:
        raise SystemExit(
            f"Missing backgrounds: {sorted(missing)}\n"
            "Run: python3 tools/gen_placeholder_art.py")

    import uuid
    ns = uuid.UUID("d5f7a1e2-1111-4000-8000-000000000000")
    sid = lambda k: str(uuid.uuid5(ns, k))

    scene_ids = {k: sid(k) for k in
                 ["title", "office_floor", "break_room", "print_station",
                  "meeting_room", "battle"]}

    actor_sprite = "581d34d0-9591-4e6e-a609-1d94f203b0cd"  # template actor

    scenes = {}

    # ---- title
    scenes["title"] = {
        "type": "LOGO", "background": bg["title"], "x": 200, "y": 80,
        "script": [
            text("DESKBOUND\n\nIt is Monday."),
            switch_scene(scene_ids["office_floor"], x=9, y=8, direction="down"),
        ],
        "actors": [],
    }

    # ---- office floor
    scenes["office_floor"] = {
        "type": "TOPDOWN", "background": bg["office_floor"], "x": 200, "y": 300,
        # doors: left (break), right (print), top (meeting)
        "collisions": solid_border([(0, 7, 1, 3), (19, 7, 1, 3), (8, 0, 3, 1)]),
        "script": [
            if_value(
                eq(var(V["story_flag_boss"]), num(1)),
                [text("You went home. The day\nis over. You won.")],
            ),
        ],
        "actors": [
            {
                "name": "Coworker", "x": 6, "y": 6, "sprite": actor_sprite,
                "script": [
                    if_value(
                        eq(var(V["story_flag_coffee"]), num(0)),
                        [text("Morning! Careful with the\ncoffee machine. It's...\nhaving a week.")],
                        [if_value(
                            eq(var(V["story_flag_printer"]), num(0)),
                            [text("Coffee's fixed? Bold.\nThe printer's next.\nGood luck with that.")],
                            [text("Meeting room. 17:00.\nNo agenda. I'm sorry.")],
                        )],
                    ),
                    text("Keep your Composure up.\nWhen it runs out, you\ngo home early."),
                ],
            },
            {
                "name": "Sign West", "x": 1, "y": 8, "sprite": actor_sprite,
                "script": [text("<- BREAK ROOM")],
            },
            {
                "name": "Sign East", "x": 18, "y": 8, "sprite": actor_sprite,
                "script": [text("PRINT STATION ->")],
            },
        ],
        "triggers": [
            {"name": "to_break", "x": 0, "y": 7, "w": 2, "h": 3,
             "script": [switch_scene(scene_ids["break_room"], x=17, y=8, direction="left")]},
            {"name": "to_print", "x": 18, "y": 7, "w": 2, "h": 3,
             "script": [switch_scene(scene_ids["print_station"], x=2, y=8, direction="right")]},
            {"name": "to_meeting", "x": 8, "y": 0, "w": 3, "h": 2,
             "script": [
                 if_value(
                     gbs.vand(eq(var(V["story_flag_coffee"]), num(1)),
                              eq(var(V["story_flag_printer"]), num(1))),
                     [switch_scene(scene_ids["meeting_room"], x=9, y=15, direction="up")],
                     [text("The meeting isn't until\n17:00. There is coffee\nand printing to survive\nfirst.")],
                 )
             ]},
        ],
    }

    # ---- break room
    scenes["break_room"] = {
        "type": "TOPDOWN", "background": bg["break_room"], "x": 20, "y": 300,
        "collisions": solid_border([(19, 7, 1, 3)]),
        "script": [],
        "actors": [{
            "name": "Coffee Machine", "x": 9, "y": 4, "sprite": actor_sprite,
            "script": encounter_script(
                COFFEE, scene_ids["battle"], "story_flag_coffee",
                "The coffee machine hums,\npeacefully. You have an\nunderstanding."),
        }],
        "triggers": [
            {"name": "to_office", "x": 18, "y": 7, "w": 2, "h": 3,
             "script": [switch_scene(scene_ids["office_floor"], x=2, y=8, direction="right")]},
        ],
    }

    # ---- print station
    scenes["print_station"] = {
        "type": "TOPDOWN", "background": bg["print_station"], "x": 380, "y": 300,
        "collisions": solid_border([(0, 7, 1, 3)]),
        "script": [],
        "actors": [{
            "name": "Printer", "x": 9, "y": 6, "sprite": actor_sprite,
            "script": encounter_script(
                PRINTER, scene_ids["battle"], "story_flag_printer",
                "The printer prints.\nCorrectly. You don't\nquestion it."),
        }],
        "triggers": [
            {"name": "to_office", "x": 0, "y": 7, "w": 2, "h": 3,
             "script": [switch_scene(scene_ids["office_floor"], x=17, y=8, direction="left")]},
        ],
    }

    # ---- meeting room
    scenes["meeting_room"] = {
        "type": "TOPDOWN", "background": bg["meeting_room"], "x": 200, "y": 20,
        "collisions": solid_border([(8, 16, 3, 2)]),
        "script": [],
        "actors": [{
            "name": "The Meeting", "x": 9, "y": 8, "sprite": actor_sprite,
            "script": encounter_script(
                MEETING, scene_ids["battle"], "story_flag_boss",
                "The room is empty.\nThe meeting is over.\nYou may go home."),
        }],
        "triggers": [
            # y=16 not 17: with 8x16 sprites the player origin can never reach
            # the final row of an 18-tile scene, making a y=17 trigger dead.
            # Arrive at y=3, not y=2: an 8x16 sprite spans two tiles, so a
            # y=2 arrival overlaps the to_meeting trigger and bounces the
            # player straight back into this room.
            {"name": "to_office", "x": 8, "y": 16, "w": 3, "h": 2,
             "script": [switch_scene(scene_ids["office_floor"], x=9, y=3, direction="down")]},
        ],
    }

    # ---- battle (shared)
    scenes["battle"] = {
        "type": "POINTNCLICK", "background": bg["battle_bg"], "x": 560, "y": 160,
        "script": build_battle_script(scene_ids),
        "actors": [],
        "triggers": [],
    }

    # ---- emit
    out_dir = os.path.join(ROOT, "project", "scenes")
    for i, (key, sc) in enumerate(scenes.items()):
        d = os.path.join(out_dir, key)
        os.makedirs(d, exist_ok=True)
        # GB Studio associates actors/triggers with a scene by DIRECTORY:
        # it groups them by the path segment before "/actors/" or "/triggers/".
        # Writing them flat next to scene.gbsres makes them orphans that belong
        # to no scene — the app loads the project without them and silently
        # drops them on the next save.
        actors_dir = os.path.join(d, "actors")
        triggers_dir = os.path.join(d, "triggers")
        os.makedirs(actors_dir, exist_ok=True)
        os.makedirs(triggers_dir, exist_ok=True)

        actors = []
        for j, a in enumerate(sc.get("actors", [])):
            # Field set matches ActorResource in the GB Studio 4.3 TypeBox
            # schema — prefabId / coordinateType / collisionExtraFlags /
            # prefabScriptOverrides are required, not optional.
            actors.append({
                "_resourceType": "actor",
                "id": sid(f"{key}_actor_{j}"),
                "_index": j,
                "name": a["name"],
                "symbol": f"actor_{key}_{j}",
                "prefabId": "",
                "coordinateType": "tiles",
                "x": a["x"], "y": a["y"],
                "frame": 0, "direction": "down",
                "spriteSheetId": a["sprite"],
                "moveSpeed": 1, "animSpeed": 15,
                "paletteId": "", "isPinned": False,
                "persistent": False, "collisionGroup": "",
                "collisionExtraFlags": [],
                "prefabScriptOverrides": {},
                "animate": False, "script": a["script"],
                "startScript": [], "updateScript": [],
                "hit1Script": [], "hit2Script": [], "hit3Script": [],
            })
            fname = slugify(a["name"], f"actor_{j}")
            json.dump(actors[-1],
                      open(os.path.join(actors_dir, f"{fname}.gbsres"), "w"),
                      indent=2)

        triggers = []
        for j, t in enumerate(sc.get("triggers", [])):
            tr = {
                "_resourceType": "trigger",
                "id": sid(f"{key}_trigger_{j}"),
                "_index": j,
                "name": t["name"],
                "symbol": f"trigger_{key}_{j}",
                "prefabId": "",
                "prefabScriptOverrides": {},
                "x": t["x"], "y": t["y"],
                "width": t["w"], "height": t["h"],
                "script": t["script"],
                "leaveScript": [],
            }
            triggers.append(tr)
            fname = slugify(t["name"], f"trigger_{j}")
            json.dump(tr, open(os.path.join(triggers_dir, f"{fname}.gbsres"), "w"),
                      indent=2)

        scene = {
            "_resourceType": "scene",
            "id": scene_ids[key],
            "_index": i,
            "name": key.replace("_", " ").title(),
            "backgroundId": sc["background"],
            "tilesetId": "",
            "width": 20, "height": 18,
            "type": sc["type"],
            "colorModeOverride": "none",
            "paletteIds": [], "spritePaletteIds": [],
            "collisions": sc.get("collisions", ""),
            "autoFadeSpeed": 1,
            "symbol": f"scene_{key}",
            "x": sc["x"], "y": sc["y"],
            "script": sc["script"],
            "playerHit1Script": [], "playerHit2Script": [], "playerHit3Script": [],
        }
        json.dump(scene, open(os.path.join(d, "scene.gbsres"), "w"), indent=2)
        print(f"wrote scene {key}: {len(sc.get('actors', []))} actors, "
              f"{len(sc.get('triggers', []))} triggers")

    # settings: start on title
    sp = os.path.join(ROOT, "project", "settings.gbsres")
    st = json.load(open(sp))
    st["startSceneId"] = scene_ids["title"]
    st["startX"] = 0
    st["startY"] = 0
    json.dump(st, open(sp, "w"), indent=2)
    print("updated settings.gbsres startSceneId ->", scene_ids["title"])



if __name__ == "__main__":
    main()

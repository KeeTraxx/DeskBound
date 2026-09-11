# DeskBound

A Pokémon-inspired turn-based RPG for the Game Boy, where an office worker
battles the mildly infuriating objects of corporate life.

Built with [GB Studio](https://www.gbstudio.dev/) 4. See [DESIGN.md](DESIGN.md)
for the full game design.

## Status

Playable vertical slice with **placeholder art**:

- Title screen → office floor → three battles → ending
- Complete turn-based battle system (ACT / LOOK / FLEE, four verbs)
- Three enemies, each with unique per-verb responses and their own move sets
- Comedic loss handling — you go home early, never a game over

**All art is programmer-generated placeholder.** Blocked-out rooms and
rectangles, there to make the game testable. Swapping in real art requires no
scripting changes as long as dimensions match — see [DESIGN.md §6](DESIGN.md).

## Building the project files

Scenes and scripts are **generated**, not hand-edited. GB Studio stores scripts
as deeply nested JSON with UUIDs, which is unreadable and error-prone to author
by hand, so the game content lives in Python and compiles to `.gbsres`.

```sh
python3 tools/gen_placeholder_art.py   # backgrounds + .gbsres sidecars
python3 tools/build_project.py         # scenes, actors, triggers, scripts
python3 tools/validate.py              # check against GB Studio's own schemas
```

Run all three after changing anything in `tools/`.

> **Editing caution:** changes made in the GB Studio GUI to generated scenes
> will be overwritten the next time you run `build_project.py`. Treat
> `tools/build_project.py` as the source of truth, or stop regenerating once
> you start editing in the GUI.

### Resource layout matters

Actors and triggers **must** live in `project/scenes/<scene>/actors/` and
`project/scenes/<scene>/triggers/`. GB Studio binds scene children by
directory — it groups them on the path segment before `/actors/` or
`/triggers/`. Files written flat next to `scene.gbsres` load as orphans
belonging to no scene, and the next save in the GUI **silently deletes them**.
`validate.py` enforces this.

### Adding a position-based transition

Use a **trigger**, not a position check in the scene script. A scene's script
is On Init: it runs once at load and never again, so it cannot detect the
player walking somewhere later. Scenes have no update-script slot.
(`$self$` also doesn't resolve to the player in a scene script — the player is
referenced as `"player"`.)

### `tools/`

| File | Purpose |
|---|---|
| `gen_placeholder_art.py` | Draws the placeholder backgrounds; enforces the 192-tile budget |
| `gbs.py` | Constructors for GB Studio event JSON (verified against the engine) |
| `build_project.py` | Game content — enemies, dialogue, battle logic — and the emitter |
| `validate.py` | Validates output against GB Studio's schemas and event definitions |

## Playing it

Open `DeskBound.gbsproj` in GB Studio and hit Run (or Build → ROM).

The project targets GB Studio `4.2.0 / release 10`. The installed flatpak is
4.3.2, whose own templates are still on that same format version, so no project
upgrade is needed.

## Verification

GB Studio only builds from its GUI — there is no `gb-studio-cli` in the
flatpak — so this repo can't compile a ROM unattended. Two things stand in:

**`tools/validate.py`** checks every generated resource against data extracted
from the installed app itself: the TypeBox resource schemas, all 151 event
definitions, their per-field *types*, and the script-value operator set. It
catches unknown events, misspelled argument keys, scalars passed where a
script-value object is required, malformed expressions, and dangling
references.

**Battle balance is simulated.** The tuning constants in `build_project.py`
were fitted by running the shipped damage formulas over thousands of games
per strategy. Current results:

| Enemy | random | optimal | worst | always FIX | always SHRUG |
|---|---|---|---|---|---|
| Coffee Machine | 100% · 5.0t | 100% · 3.9t | 100% · 7.4t | 100% · 3.9t | 100% · 4.1t |
| The Printer | 100% · 6.6t | 100% · 3.7t | 100% · 11.2t | 100% · 11.2t | 100% · 7.1t |
| The Meeting | 100% · 9.1t | 100% · 6.0t | 100% · 16.6t | 99.9% · 9.6t | 100% · 16.6t |

Every strategy wins and none stalls, matching the "comedic and easy" design
goal, while optimal play stays about twice as fast as stubborn play.

**Two playtest bugs found and fixed** (awaiting your re-test): the meeting
room had no usable exit — its trigger sat on the final tile row, which an
8x16 sprite can never stand on — and leaving it dropped the player on top of
the return trigger, bouncing them back. Scene collision data was also empty,
so no wall was solid. `validate.py` now checks trigger reachability, arrival
walkability, and arrival/trigger overlap.

**One compile failure found and fixed**:
`EVENT_SWITCH_SCENE` was given raw integers for its `x`/`y` fields,
which are declared `type: "value"` and need script-value objects. The compiler
reported only `Error: Didn't expect to get here`, so `validate.py` now
type-checks value fields and reproduces that failure locally.

**Not yet verified:** gameplay itself. Text layout on a 160×144 screen, menu
widths, and pacing all need a real playtest.

## Known gaps

- No audio (the GB Studio template's `template.mod` is still the only track)
- Enemies use the default actor sprite — no distinct enemy graphics
- No save/load
- Rooms are open floor apart from the outer walls; desks and tables are drawn
  but not solid
- Battle "sprites" are absent; the battle scene is backdrop plus text

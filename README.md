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

## Enemies and the battle script

The game is authored in the GB Studio GUI — **except the battle**. One fight is
a branch per enemy × per verb × per move, which is miserable to click together
and unreadable as JSON, so enemies live in [`enemies.yaml`](enemies.yaml) and
compile into a GB Studio custom script named **BattleScript**:

```sh
python3 tools/gen_enemies.py            # --dry-run to validate without writing
```

That writes these files and touches nothing else:

| File | Contents |
|---|---|
| `project/scripts/battlescript.gbsres` | the `BattleScript` custom script — the whole turn loop |
| `project/scripts/setbar.gbsres` | `SetBar` — shows a value on a bar actor (only with `bars:`) |
| `project/scenes/battle/actors/enemy.gbsres` | the actor whose sprite `BattleScript` swaps per enemy |
| `project/scenes/battle/actors/playerbar.gbsres` | Composure meter for `player_composure` (only with `bars:`) |
| `project/scenes/battle/actors/enemybar.gbsres` | Composure meter for `enemy_composure` (only with `bars:`) |
| `project/scenes/battle/scene.gbsres` | On Init → call `BattleScript`, with all three actors bound |

The overworld starts a fight the way it already does: set `enemy_id`, push
scene state, switch to the battle scene. `BattleScript` reads `enemy_id`, sets
the enemy sprite and stats, runs the fight, sets `battle_result`
(1 = win, 2 = fled, 3 = lost) plus the enemy's `win_flag`, and pops back.

Adding an enemy is a YAML block — name, sprite, composure, `take_damage` per
ACT verb, `look`/`intro`/`defeat` text, and moves with their own damage ranges.
`sprite` is a `.png` under `assets/sprites/` (`actor.png`, or
`enemies/coffee.png` in a subfolder), resolved through that file's `.gbsres`
sidecar. Every text field is a list of **variants**, each variant a list of
**steps**:

```yaml
look:
  - - "First box of variant one."
    - "Second box, same variant."
  - - "Variant two, shown instead."
```

One variant is rolled at random each time the line comes up, then its steps
play in order, one Display Text each. That's where extra flavour goes — enemy
moves and damage reports repeat a dozen times per fight.

Ranges are inclusive and accept `5`, `"3-6"` or `[3, 6]`. Any text may use
`{damage}`, `{player_composure}`, `{enemy_composure}` and friends, which become
GB Studio variable interpolation.

> **Editing caution:** the battle scene's On Init script, its `Enemy` actor and
> `BattleScript` are regenerated wholesale. Edit `enemies.yaml`, not those.
> Everything else in the project is safe to edit in the GUI. The tool never
> touches `project/variables.gbsres` — the globals it needs (`enemy_id`,
> `battle_result`, …) must already exist there.

### Resource layout matters

Actors and triggers **must** live in `project/scenes/<scene>/actors/` and
`project/scenes/<scene>/triggers/`. GB Studio binds scene children by
directory — it groups them on the path segment before `/actors/` or
`/triggers/`. Files written flat next to `scene.gbsres` load as orphans
belonging to no scene, and the next save in the GUI **silently deletes them**.
`gen_enemies.py` writes the `Enemy` actor into that layout for this reason.

### Adding a position-based transition

Use a **trigger**, not a position check in the scene script. A scene's script
is On Init: it runs once at load and never again, so it cannot detect the
player walking somewhere later. Scenes have no update-script slot.
(`$self$` also doesn't resolve to the player in a scene script — the player is
referenced as `"player"`.)

### Composure bars are pushed, not polled

A bar is an actor whose sprite has one frame per fill level; showing a value
means setting its animation frame. `BattleScript` does that through a second
generated script, **`SetBar`** (parameters: the bar actor, a value, a maximum),
called at every point Composure changes:

```
SetBar:  Set Frame on Bar = (value * 16 + max - 1) / max     # 17 frames, ceiling
```

The ceiling means only a real 0 shows an empty bar; 1 Composure still shows a
sliver. The divisor is floored at 1 so the bar is harmless before a maximum is
set. `BattleScript` takes the two bars as actor parameters (`PlayerBar`,
`EnemyBar`) and forwards them to `SetBar` — the compiler allows that, because
`isActorField` special-cases `$actor[...]` keys.

**An On Update script cannot do this job.** GB Studio has no hook that fires
when a variable changes, so the obvious alternative is a bar actor that polls
its variable every frame. It never runs: `compileData.ts` compiles a scene's On
Init script with `lock = true`, which emits `VM_LOCK`, and the VM scheduler
(`vm.c`: `if (!vm_lock_state) executing_ctx = first_ctx;`) then re-runs *only*
the locking context. The whole battle lives in On Init, so it holds the lock for
the entire fight and every other thread — including actor update scripts — is
frozen. A polled bar shows frame 0 forever.

A bar actor must also have **Animation Speed: None** (`animSpeed: 255`), or the
engine cycles its 17 frames on its own and the bar fills and empties on a loop
regardless of Composure. The actor `animate` flag does *not* prevent this — in
4.2 it isn't emitted for actors at all, `EVENT_ACTOR_SET_ANIMATE` is deprecated,
and `actorSetAnimate` logs "not implemented". The only control that reaches the
engine is `anim_tick`, which is what `animSpeed` compiles to.

`assets/sprites/composure_bar.png` is placeholder art: a 17-frame strip,
64×16 per cell, empty through full, `#65FF00` as transparency. Change
`bars.width` / `bars.height` / `bars.frames` and re-run with `--draw-bar-art`
to redraw it and its sidecar; redraw it by hand at the same dimensions and the
sidecar keeps working, since GB Studio recomputes a sprite's file metadata on
load but preserves the frame slicing in the `.gbsres`.

**Tile coordinates in a sprite sidecar are origin-relative, not
canvas-relative.** `readSpriteData.ts` masks each tile at
`(originX + tile.x, originY - tile.y)` against a canvas-sized image, where
`originX = canvasWidth / 2 - 8` and y counts *upward*. Anything landing outside
that mask is marked `Unknown`, and `Unknown` matches **any** tile during
deduplication — so wrongly-placed tiles silently collapse frames into each
other and every frame renders the same. At canvas width 16 the origin is 0 and
the two conventions coincide, which hides the mistake until you widen a sprite.
The same convention means the actor's x is the **centre** of the bar, so a 64px
bar needs `x >= 4` tiles to stay on screen.

**The width costs hardware sprites.** GB Studio sprite tiles are 8×16, so a
64px bar is **8 OAM sprites**, and the Game Boy drops anything past **10
sprites on one scanline**. Each bar sits on its own rows, so they don't compete
with each other — but keep the enemy sprite off those rows, or parts of the bar
will flicker out. VRAM is not the problem: the 136 tile slots in the strip are
only **3 distinct tiles** (empty, half, full) once GB Studio dedupes them.

### Why the generated branches are nested if/else

`BattleScript` switches on `battle_temp` twice over: once to pick the enemy's
move, and again inside that move to pick a dialogue variant. A flat run of
`EVENT_IF`s would evaluate every case, so the inner re-roll could match a
second move and the enemy would attack twice in one turn. Every generated
branch chain is therefore nested if/else — once a branch is taken, no later
case is tested, and the branch is free to reuse the variable it switched on.

### Why the enemy sprite is an actor *parameter*

A GB Studio custom script cannot name a scene actor by id — the compiler
rejects it with `Unknown arg actor ...`, because the script compiles once and
is shared across scenes. Actors reach a custom script only as parameters
(slot `"0"` inside the script, bound as `"$actor[0]$"` at the call site). That
is why `gen_enemies.py` owns the battle scene's On Init call and the `Enemy`
actor: they are the binding. Global variables have no such restriction, so
`BattleScript` reads and writes them directly.

## Playing it

Open `DeskBound.gbsproj` in GB Studio and hit Run (or Build → ROM).

The project targets GB Studio `4.2.0 / release 10`. The installed flatpak is
4.3.2, whose own templates are still on that same format version, so no project
upgrade is needed.

## Verification

GB Studio only builds from its GUI — there is no `gb-studio-cli` in the
flatpak — so this repo can't compile a ROM unattended. Two things stand in:

**`gen_enemies.py --dry-run` validates the data**: unknown sprite names,
missing or backwards damage ranges, duplicate enemy ids, actions an enemy
doesn't answer for, `win_flag`s that aren't real variables, and unknown keys
all fail loudly with the offending enemy named. The event JSON it emits was
checked against GB Studio 4.2.0's own event definitions and the TypeBox
`ScriptResource` schema.

**Battle balance is simulated** by *interpreting the generated event tree* —
the same `EVENT_IF` / `EVENT_LOOP_WHILE` / `EVENT_SET_VALUE` nodes the engine
runs — rather than re-implementing the formulas, so the table reflects the
shipped script (2000 games per cell):

| Enemy | random | always THINK | always TALK | always EMAIL | always SHRUG |
|---|---|---|---|---|---|
| Coffee Machine | 100% · 7.0t | 100% · 4.4t | 100% · 10.5t | 100% · 13.8t | 100% · 5.7t |
| The Printer | 100% · 7.6t | 99.9% · 14.8t | 100% · 11.3t | 100% · 4.0t | 100% · 8.6t |
| The Meeting | 100% · 10.1t | 100% · 12.1t | 100% · 6.7t | 100% · 11.0t | 100% · 12.8t |

Every strategy wins and none stalls, matching the "comedic and easy" design
goal, while optimal play stays about twice as fast as stubborn play.

**Not yet verified:** the generated script has never been compiled by GB Studio,
and gameplay itself. Text layout on a 160×144 screen, menu widths, and pacing
all need a real playtest.

## Known gaps

- No audio (the GB Studio template's `template.mod` is still the only track)
- Enemies point at placeholder sprites (`actor`, `static`) — drop real enemy
  sprite `.png`s into `assets/sprites/` and point `enemies.yaml` at them
- `composure_bar.png` is a programmer-drawn 17-frame strip; bar placement
  (`bars.player` / `bars.enemy` in `enemies.yaml`) is a guess until playtested
- No save/load
- Rooms are open floor apart from the outer walls; desks and tables are drawn
  but not solid

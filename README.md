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
uv sync                                 # once, creates .venv/ with pyyaml + pillow
uv run tools/gen_enemies.py             # --dry-run to validate without writing
```

That writes two scripts and nothing else — no scene, no actors:

| File | Contents |
|---|---|
| `project/scripts/battlescript.gbsres` | the `BattleScript` custom script — the turn loop |
| `project/scripts/battle_<enemy>.gbsres` | one per enemy: its dialogue, verbs, moves and reward |
| `project/scripts/setbar.gbsres` | `SetBar` — shows a value on a bar actor (only with `bars:`) |

**Why one script per enemy:** a compiled script is a single module, and a
module must fit in one 16KB ROM bank. With every enemy inlined, `BattleScript`
reached 26KB at eight enemies and the linker rejected it
(`BankPack: ERROR! Area _CODE_, bank 255, size 26044 is too large`). Each enemy
now compiles to its own module — roughly 3KB each — dispatched on a phase
parameter (`setup / act / look / flee / move / defeat`) that `BattleScript`
passes when it calls in. Only `BattleScript` is bound to the scene; the enemy
scripts are called, never wired by hand. Renaming or deleting an enemy removes
its old script on the next run (only files this tool stamped are touched).

(`--draw-bar-art` additionally redraws the placeholder bar sprite under
`assets/sprites/`.)

**Wiring is yours.** A custom script can't name a scene actor by id, so the
actors the battle touches are actor *parameters*. Drop `BattleScript` into the
battle scene's On Init and bind them from its dropdowns:

| Parameter | Bind to |
|---|---|
| `Enemy` | the actor whose sprite the fight swaps per enemy |
| `PlayerBar` / `EnemyBar` | two actors using `energy_bar.png`, each set to **Animation Speed: None** |

`SetBar` is a normal custom script too — drag it into any script to refresh a
bar by hand.

### Hooks

A `hooks:` block calls a script *you* wrote whenever the battle moves a value:

```yaml
hooks:
  player_changed: PlayerValuesChanged
  player_fainted: Faint
```

The script is resolved by name from `project/scripts/` and is never rewritten
by the tool.

| Hook | Fires |
|---|---|
| `player_changed` | after every write to `player_energy` — battle setup, each enemy hit, and a reward |
| `player_fainted` | once, when Energy reaches 0, after the lose text and before the scene pops |

`player_fainted` is where going home and sleeping belongs (DESIGN.md §9.2). If
that script switches scenes, `BattleScript`'s closing Scene Pop State never
runs — a scene change kills every running script — so the hook can take over
the flow entirely.

**A hook is called with no arguments** and reads globals directly, which a
custom script can do: only `V0`-`V9` are parameters, every other variable
reference is the global itself. So a hook must declare **no parameters** —
generation fails if it does, because an unbound argument doesn't fail the GB
Studio build, it silently compiles to whichever variable the context defaults
to.

The overworld starts a fight the way it already does: set `enemy_id`, push
scene state, switch to the battle scene. `BattleScript` reads `enemy_id`, sets
the enemy sprite and stats, runs the fight, sets `battle_result`
(1 = win, 2 = fled, 3 = lost) plus the enemy's `win_flag`, and pops back.

### Battle rewards

An enemy may carry a `reward:` block, applied only on a win:

```yaml
reward:
  energy: 12          # healed, clamped to player_energy_max
  max_energy: 10      # widens the tank — and adds the same to current Energy
  brains: 1           # player_brains
  text:
    - - "You drink it. It is\nactually good.\n\n+12 Energy."
```

Amounts take the same forms as damage (`5`, `"3-6"`, `[3, 6]`); a range is
rolled once and reused, so a ranged `max_energy` moves the maximum and the
current value by the same number. Gains land *before* the text, so the bar has
already grown by the time the player reads about it, and each one fires the
`player_changed` hook. Reward text has no amount placeholder — if the number is
fixed, write it into the line yourself.

`brains` is raised but nothing in the battle reads it: damage comes from the
per-verb ranges in `enemies.yaml`, not a stat. It is there for the overworld
(and for a future damage formula) to use.

**The player's Energy is the overworld's**, not the battle's:
`player_energy` and `player_energy_max` are globals that `BattleScript` only
ever subtracts damage from and adds rewards to — it never initialises them — so
damage carries from one fight to the next. Two consequences to handle outside the battle — set
`player_energy_max` before the first fight (the bar divides by it), and
restore Energy after a loss, or the next battle ends on its first round
because Energy is already 0.

Adding an enemy is a YAML block — name, sprite, energy, `take_damage` per
ACT verb, `look`/`intro`/`defeat` text, and moves with their own damage ranges.
Its `id` is what the overworld writes to `enemy_id`; ids may start at 0 so a
picker can use a bare `rnd(n)`, though bear in mind an unset `enemy_id` is also
0. Omitted, an id is the enemy's position in the list counting from 1.
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
`{damage}`, `{player_energy}`, `{enemy_energy}` and friends, which become
GB Studio variable interpolation.

> **Editing caution:** `BattleScript` and `SetBar` are rewritten wholesale on
> every run — edit `enemies.yaml`, not them. Everything else, scenes and actors
> included, is yours to edit in the GUI; the tool never opens those files. Nor
> does it touch `project/variables.gbsres` — the globals it needs (`enemy_id`,
> `battle_result`, …) must already exist there.

### Resource layout matters

Actors and triggers **must** live in `project/scenes/<scene>/actors/` and
`project/scenes/<scene>/triggers/`. GB Studio binds scene children by
directory — it groups them on the path segment before `/actors/` or
`/triggers/`. Files written flat next to `scene.gbsres` load as orphans
belonging to no scene, and the next save in the GUI **silently deletes them**.
(`gen_enemies.py` writes no actors, but the rule bites anything you add by
hand outside the GUI.)

### Adding a position-based transition

Use a **trigger**, not a position check in the scene script. A scene's script
is On Init: it runs once at load and never again, so it cannot detect the
player walking somewhere later. Scenes have no update-script slot.
(`$self$` also doesn't resolve to the player in a scene script — the player is
referenced as `"player"`.)

### Energy bars are pushed, not polled

A bar is an actor whose sprite has one frame per fill level; showing a value
means setting its animation frame. `BattleScript` does that through a second
generated script, **`SetBar`** (parameters: the bar actor, a value, a maximum),
called at every point Energy changes:

```
SetBar:  Set Frame on Bar = (value * 16 + max - 1) / max     # 17 frames, ceiling
```

The ceiling means only a real 0 shows an empty bar; 1 Energy still shows a
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
regardless of Energy. The actor `animate` flag does *not* prevent this — in
4.2 it isn't emitted for actors at all, `EVENT_ACTOR_SET_ANIMATE` is deprecated,
and `actorSetAnimate` logs "not implemented". The only control that reaches the
engine is `anim_tick`, which is what `animSpeed` compiles to.

`assets/sprites/energy_bar.png` is placeholder art: a 17-frame strip,
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
The same convention means the actor's x is the **centre** of the bar, so place
a 64px bar at `x >= 4` tiles to keep it on screen.

**`numTiles` in a sprite sidecar is believed, not recomputed.** Both the
editor's "sprite tiles used in scene" counter and the compiler's per-scene
budget (`compileData.ts` → `getSpriteTileCount`) read the value straight from
the `.gbsres`; nothing derives it from the image. `--draw-bar-art` therefore
counts the unique 8x16 tiles the way `readSpriteData.ts` does — after
deduplication, flips included — rather than the number of tile *slots*. For the
64px bar that is **3**, not 136.

**The width costs hardware sprites.** GB Studio sprite tiles are 8×16, so a
64px bar is **8 OAM sprites**, and the Game Boy drops anything past **10
sprites on one scanline**. Each bar sits on its own rows, so they don't compete
with each other — but keep the enemy sprite off those rows, or parts of the bar
will flicker out. VRAM is not the problem: the 136 tile slots in the strip are
only **3 distinct tiles** (empty, half, full) once GB Studio dedupes them.

### Returning to a Shoot Em' Up scene sets its scroll direction

`shmup_init` starts with `shooter_direction = PLAYER.dir` — a SHMUP scene takes
its scroll axis from whichever way the player happens to be facing when the
scene loads. In free movement `shmup_update` rewrites `PLAYER.dir` to UP or DOWN
as soon as you press up or down, and `Scene Push State` saves that direction,
which `Scene Pop State` restores *before* `state_init` runs.

So a battle entered while dodging vertically returns Street to a **vertically**
scrolling shooter: the horizontal auto-scroll stops and left/right steer freely.
Street is 200x18 tiles — exactly one screen tall — so there is nowhere to scroll
vertically and it just looks like the scene lost its type.

The fix belongs at *push* time, not on return: `StartBattle` faces the player
along the scroll axis (Actor Set Direction → Player → Right) **before** Scene
Push State, so the direction that comes back is the one the scene needs. Setting
it in the scene's On Init is too late — `state_init` has already read it.

### The Enemy actor should start as the *largest* enemy sprite

`BattleScript` swaps the Enemy actor's sprite through an actor *parameter*, and
that defeats GB Studio's reservation for swapped sprites. `compileData.ts` keys
its `actorsExclusiveLookup` by `event.args.actorId` — for a parameter that is
the literal slot `"0"`, never the scene actor's id — so `generateGBVMData.ts`
emits `reserve_tiles: 0` for the actor that actually gets swapped.

With `reserve_tiles` at 0 the engine puts that actor in the *shared* sprite
pool (`data_manager.c`), and `vm_actor_set_spritesheet` then does
`load_sprite(actor->base_tile, …)` with no bounds check. Swapping in a sprite
with more tiles than the actor's base sprite writes straight over the tiles
that follow it.

So give the Enemy actor a default sprite at least as large as the biggest
enemy it can become. Today `actor_animated.png` is 8 unique tiles while the
actor's base `actor.png` is 3 — five tiles of overspill whenever the boss
appears.

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

Prebuilt `.gb` ROMs are attached to each
[release](https://github.com/KeeTraxx/DeskBound/releases).

## CI builds

[`.github/workflows/build-rom.yml`](.github/workflows/build-rom.yml) compiles a
ROM on every pull request, uploads it as a build artifact, and — on a `v*` tag
— attaches `DeskBound-<tag>.gb` to the matching GitHub release. It is also a
reusable workflow, and pushes to `main` reach it that way, through the Pages
workflow below (see [Web player](#web-player)) rather than directly — otherwise
every push to `main` would compile the same ROM twice.

No Linux distribution of GB Studio ships `gb-studio-cli` (the flatpak, the
AppImage and the `.deb` are all just the Electron app), so the workflow builds
the CLI from the `chrismaltby/gb-studio` source at `GB_STUDIO_VERSION`, pinned
to **4.3.2** to match the flatpak used locally. `make:rom` reads the project
without writing it back, so the 4.2.0-format `.gbsproj` is migrated in memory
only and the checkout is left alone. Two things about the build are non-obvious
and worth keeping:

- **GBDK comes out of the official release, not `yarn fetch-deps`.** That script
  downloads the rolling `gbdk-next` build, which no longer links against the
  bundled engine — it dies at the link step with
  `?ASlink-Warning-Undefined Global '.IF'`. The workflow unpacks the `.deb`'s
  `app.asar` and takes the pinned `buildTools/linux-x64` the release ships.
- **The build greps its own log for `No compiler for command`.** If the CLI
  can't resolve an event handler it skips the event, still exits 0, and emits a
  ROM with the scripts silently missing (roughly half the size). The grep turns
  that into a failed build.

The CLI has to run from the full GB Studio source tree — it loads event
definitions from `src/lib/events` at runtime rather than from its webpack
bundle, which is exactly how that silent-skip failure happens.

## Web player

`web/` is a Svelte + Vite page that runs the ROM in the browser through
[`game-koi`](https://www.npmjs.com/package/game-koi). Locally, `just` builds the
ROM and starts the dev server; `tools/build-rom.sh` drops the result at
`web/public/DeskBound.gb`, which is a build output and stays gitignored.

[`.github/workflows/pages.yml`](.github/workflows/pages.yml) publishes that page
to GitHub Pages on every push to `main`. Because the ROM isn't in the
repository, the workflow first calls `build-rom.yml`, then copies the resulting
artifact to `web/public/DeskBound.gb` before `npm run build`.

The site is served from `https://keetraxx.github.io/DeskBound/`, not from a
domain root, so the build has to know its prefix: `actions/configure-pages`
resolves it and the workflow passes it to Vite as `BASE_PATH` (see
`web/vite.config.ts`). Anything fetched at runtime has to go through
`import.meta.env.BASE_URL` for the same reason — `fetch('/DeskBound.gb')` would
404 on Pages while working fine in `vite dev`.

**This needs Pages switched on once, by hand:** Settings → Pages → Source →
*GitHub Actions*. Until then `deploy-pages` fails with a "Pages site not found"
error.

## Verification

Besides the CI build above, two checks cover the parts a compiler can't:

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

**Not yet verified:** gameplay itself. The generated script compiles and links
(CI builds a 256 KB ROM), but text layout on a 160×144 screen, menu widths, and
pacing all need a real playtest.

## Known gaps

- Nothing plays music yet. Two original tracks exist — `lounge_elevator.mod`
  and `coffee_break.mod` (regenerate with `python3 tools/gen_music.py`) — but no
  scene has a Play Music event, so the game is still silent in-engine
- Enemies point at placeholder sprites (`actor`, `static`) — drop real enemy
  sprite `.png`s into `assets/sprites/` and point `enemies.yaml` at them
- `energy_bar.png` is a programmer-drawn 17-frame strip; bar placement
  (`bars.player` / `bars.enemy` in `enemies.yaml`) is a guess until playtested
- No save/load
- Rooms are open floor apart from the outer walls; desks and tables are drawn
  but not solid

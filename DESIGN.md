# DeskBound — Game Design Document

> A Pokémon-inspired turn-based RPG where an office worker battles the mildly
> infuriating objects of corporate life.

**Engine:** GB Studio (project `4.2.0`, installed app `4.3.2`) · **Platform:** Game Boy (DMG, mono) · **Author:** KeeTraxx

---

## 1. Concept

You are **the New Guy**, hired Monday morning into an open-plan office, with
one work week ahead of you. The building's objects have opinions. The coffee machine is passive-aggressive. The
printer has never once worked. The meeting that could have been an email is,
somehow, sentient.

You fight them. Not with fire and water, but with **Patience and Passive
Aggression**.

The joke that carries the whole game: the stakes are *absurdly low* and everyone
treats them as *life or death*. A jammed printer is framed as a boss battle,
complete with a health bar and a dramatic defeat line.

### Tone

Dry, deadpan, sympathetic. The office things are annoying but not evil — the
game is affectionate about the tedium, not bitter. Think *Office Space* by way
of a Game Boy manual.

---

## 2. Core Loop

The game is **one work week**. You wake up at home on Monday; Friday evening the
credits roll. Everything else nests inside that.

```
WEEK    Monday ─ Tuesday ─ Wednesday ─ Thursday ─ Friday  →  ending
          │
DAY       wake at home → commute → office floor → go home → sleep
                                        │    ↑
BATTLE                             encounter → turn-based fight
```

1. **Wake** at home. The opening line depends on which day it is.
2. **Commute** through the street — dodging traffic, not fighting it.
3. **Explore** the office in top-down view. Talk to coworkers, read the
   passive-aggressive fridge notes.
4. **Encounter** an office thing by interacting with it (no random encounters —
   see §7 Design Decisions).
5. **Battle** it in a turn-based fight on a dedicated battle scene.
6. **Go home** — by walking out at the end of the day, or because your Energy
   ran out and the day ended without asking you (§9.2).
7. **Sleep.** Energy comes back, the day advances. After Friday, the game ends.

**Energy is the week's currency, not the battle's.** It does not reset between
fights — it carries from one encounter to the next and only returns when you
sleep. A bad fight is therefore paid for in *daylight*: the one resource the
game will never give you more of is days, and there are five.

---

## 3. The Battle System

This is the heart of the game and the part that is pure scripting — no art
dependency beyond a static battle backdrop and one enemy sprite each.

### 3.1 Stats

Both player and enemy use three stats. **There is no MP/resource meter** — move
choice is driven by *which enemy you're facing*, not by spending a currency.

| Stat | Meaning |
|---|---|
| **Energy (HP)** | How much nonsense you can absorb before you snap. Hits 0 → you lose. |
| **Brains (ATK)** | How sharply your moves land. |
| **Patience (DEF)** | How well you absorb theirs. |

Variables are 16-bit (0–65535) in GB Studio 4, so there's no need to squeeze
numbers into a byte. Realistic ranges: Energy 20–120, Brains/Patience 5–40.

### 3.2 Turn Structure

Strictly alternating, player-first. No speed stat — it adds a turn-order branch
without adding much fun.

```
┌─ PLAYER TURN ─────────────────────────────────────┐
│ Top menu: ACT / LOOK / FLEE                       │
│   ACT  → submenu: THINK / TALK / EMAIL / INTERACT │
│          → resolve per-enemy effect               │
│   LOOK → flavour text only, no effect,            │
│          does NOT consume the turn                │
│   FLEE → attempt to escape (may fail)             │
│ Apply damage → check enemy Energy ≤ 0             │
└──────────────────┬────────────────────────────────┘
                   ↓ enemy still standing
┌─ ENEMY TURN ───────────────────────────────────┐
│ Pick move via weighted rnd()                   │
│ Show witty enemy line → resolve → apply dmg    │
│ Check player Energy ≤ 0                        │
└──────────────────┬─────────────────────────────┘
                   ↓
             back to PLAYER TURN
```

**LOOK does not consume a turn.** It's an information verb, not a tactical
choice — punishing curiosity would discourage reading the jokes, which are the
actual content of the game.

### 3.3 Damage Formula

Kept simple and readable as a GB Studio math expression:

```
damage = max(1, (move_power + player_Brains) - (enemy_Patience / 2) + rnd(4))
```

- `max(1, …)` guarantees every hit does *something* — no frustrating zero-damage turns.
- `rnd(4)` adds 0–3 variance so fights aren't fully deterministic.
- Integer division rounds down, which is fine here.

`move_power` is not a fixed property of the move — it is **looked up per
(move × enemy)** from the table in §3.5.

### 3.4 The Four ACT Verbs

Each verb is an *approach*, not an attack. None is universally good.

| Verb | Approach |
|---|---|
| **THINK** | Work out what is actually wrong. Diagnose it. |
| **TALK** | Negotiate with it. Address the thing as a person. |
| **EMAIL** | Escalate in writing. Paper trail. |
| **INTERACT** | Get hands-on. Touch it, move it, press the button. |

### 3.5 Per-Enemy Effects — the core mechanic

**Every verb does something different against every enemy.** This replaces both
the type chart and the MP economy: the puzzle is *reading the enemy* and finding
its two good verbs, and the comedy lives in the mismatches.

Power values below feed `move_power` in §3.3. Negative or zero power means the
move does something other than damage.

#### Dirty Coffee Machine · Energy 60 · Brains 6 · Patience 4
*Encrusted. Judgmental. Has seen things.*

| Verb | Pow | Result |
|---|---|---|
| **THINK** | **12** | You work out that nobody has descaled it since 2019. It shudders, seen at last. *Strong.* |
| TALK | 4 | "You talk to the coffee machine. It gurgles noncommittally." |
| EMAIL | 2 | "You email Facilities. The ticket is auto-closed as duplicate." *Weak.* |
| **INTERACT** | **10** | You pop the side panel and poke around inside. Something was not meant to be there. *Strong.* |

**Lesson taught:** understanding it and getting hands-on both work. Escalation doesn't.

#### The Printer · Energy 65 · Brains 9 · Patience 8
*It has never worked. It will never work. It is not sorry.*

| Verb | Pow | Result |
|---|---|---|
| THINK | 3 | You deduce, correctly, that the jam is in tray 2. There is no jam in tray 2. There has never been a jam in tray 2. *Weak.* |
| TALK | 0 | You say "please." The printer emits one sheet of a document from 2017. *No damage.* |
| **EMAIL** | **16** | You CC the office manager. Bureaucracy is the only language it fears. *Strong.* |
| INTERACT | 6 | You open every tray at once. Something falls out that is not paper. |

**Lesson taught:** the verb that won last fight is now the worst one. THINK fails
here precisely because it succeeded against the coffee machine.

#### The Meeting That Could've Been An Email · Energy 105 · Brains 12 · Patience 10 · **BOSS**
*It has no agenda. It has twelve attendees. It has already run over.*

| Verb | Pow | Result |
|---|---|---|
| THINK | 5 | You work out what this meeting is for. It is for nothing. Knowing this does not help. *Weak.* |
| **TALK** | **14** | You say the quiet part: "Could this have been an email?" *Strong.* |
| EMAIL | 8 | You send the follow-up email *during* the meeting. Deeply illegal. Effective. |
| INTERACT | 6 | You share your screen without being asked. Nobody objects fast enough. |

**Lesson taught:** the boss can't be reasoned out or escalated away — it must be named
aloud. INTERACT (butting in without asking) gets some purchase, but TALK's
directness is what actually lands.

### 3.6 Enemy Moves — all with flavour text

Each enemy has three moves picked by weighted `rnd()`. Every one prints a line;
the enemy turn is a punchline delivery system.

**Dirty Coffee Machine**
| Move | Effect | Line |
|---|---|---|
| Lukewarm Betrayal | dmg | "It dispenses something at exactly body temperature." |
| Passive Drip | dmg, low | "It drips. Slowly. Onto the counter you just cleaned." |
| Out Of Beans | −2 Brains | "OUT OF BEANS, it announces, with beans clearly visible." |

**The Printer**
| Move | Effect | Line |
|---|---|---|
| PC LOAD LETTER | dmg, halves Patience | "PC LOAD LETTER. No one has ever known what this means." |
| Phantom Jam | dmg | "It reports a paper jam. There is no paper. There is no jam." |
| Toner Low | −2 Brains | "TONER LOW, it says, at 94% toner." |

**The Meeting**
| Move | Effect | Line |
|---|---|---|
| Circle Back | repeats last move free | "Let's circle back to that." *(It circles back.)* |
| Quick Sync | dmg | "This'll be quick, it says. It is 45 minutes." |
| Any Other Business | dmg, scales w/ turns | "Any other business? Someone has other business." |

### 3.7 Battle Feedback

Without animation work, **text does the heavy lifting**. Every hit prints a
result line drawn from the tables above, plus a severity line:

- Strong hit: "It reels. Something rattles loose."
- Weak hit: "It barely notices."
- Player low: "Your eye twitches."
- Victory: "The coffee machine is defeated. It dispenses, finally, a decent cup."

Plus cheap non-art juice: screen shake on heavy hits, a flash on strong hits,
and emote bubbles (the template already ships anger / sweat / shock / sleep
emotes — perfect for this).

---

## 4. Structure & Content (v1 scope)

One office floor, one work week, five days that all end the same way: at home,
asleep.

| Day | Beat | Content |
|---|---|---|
| **Monday** | First day | Intro, movement tutorial. A coworker explains Energy. Break room: **Dirty Coffee Machine**. |
| **Tuesday** | It repeats | Print station: **The Printer** — punishes reusing the verb that won yesterday. |
| **Wednesday** | Midweek | *Open.* Exploration and NPC chatter today; room for enemy #4. |
| **Thursday** | Nearly | *Open.* Foreshadows the invite that has already appeared in your calendar. |
| **Friday** | 17:00 | Boss — **The Meeting That Could've Been An Email**. Win → you go home for the weekend. Credits. |

Three enemies exist today, so Wednesday and Thursday currently pass as commute
and exploration. Adding an enemy is a block in `enemies.yaml`, not a new scene
— the week has the slots, the content just isn't written yet.

**Friday always arrives.** The week is not a series of gates: it runs out on
schedule whether or not you have beaten anything, and the ending reflects what
you actually got done. There is no failure state, only a Friday with more or
fewer things crossed off.

Estimated playtime: 15–20 minutes. Deliberately small — a complete, polished
short game beats an unfinished sprawling one.

---

## 5. Technical Plan

### 5.1 Scenes

| Scene | Type | Purpose |
|---|---|---|
| `title` | LOGO | Title screen, press START |
| `home` | TOPDOWN | Wake up, choose transport, sleep at the end of the day |
| `street` | SHMUP | The commute — dodge traffic, don't fight it |
| `office_floor` | TOPDOWN | Main explorable area |
| `break_room` | TOPDOWN | Coffee machine encounter |
| `print_station` | TOPDOWN | Printer encounter |
| `meeting_room` | TOPDOWN | Boss encounter |
| `battle` | POINTNCLICK | **Shared battle scene** (see below) |
| `stats` | POINTNCLICK | Your numbers, on START from anywhere (see §5.7) |
| `ending` | TOPDOWN | Friday evening. What you got done |

`home` is both ends of a day: the wake-up that advances `dayOfWeek` and restores
Energy, and the bed you are sent to when Energy hits 0.

**Key architectural decision:** *one* reusable battle scene, not one per enemy.
Before triggering a battle, the overworld sets `enemy_id`; the battle scene's
On Init loads that enemy's stats and effect table. Adding enemy #4 is a data
change, not a new scene.

`POINTNCLICK` is used for the battle scene so there's no player actor wandering
around during a fight.

### 5.2 Variables

```
Player:   player_energy, player_energy_max, player_brains, player_patience
Enemy:    enemy_id, enemy_energy, enemy_energy_max,
          enemy_brains, enemy_patience, enemy_last_move
Battle:   battle_menu_choice, battle_act_choice, battle_power,
          battle_damage, battle_temp, battle_result, battle_turn_count
Week:     dayOfWeek, transport, commute_time
Progress: story_flag_coffee, story_flag_printer, story_flag_boss
UI:       stats_return
```

Notably absent: caffeine/MP and all item counters.

**`player_energy` belongs to the overworld, not the battle.** `BattleScript`
subtracts damage from it and adds a win's reward to it, but never initialises
it, so damage carries between fights within a day; the
wake-up script at `home` is the only thing that puts Energy back, and
`dayOfWeek` is the only thing that says the week has ended. Keeping the restore
out of the battle is what makes the day — rather than the fight — the unit of
difficulty.

### 5.3 The effect lookup

The one genuinely fiddly bit. GB Studio has no arrays, so the
(enemy × verb) → power table is a nested conditional inside a custom event:

```
LookupPower(enemy_id, act_choice) → battle_power
  if enemy_id == 1:  if act == THINK → 12, TALK → 4, EMAIL → 2, INTERACT → 10
  if enemy_id == 2:  ...
```

12 branches total for three enemies. Verbose but flat, readable, and trivial to
extend. Flavour text is selected by the same branch.

### 5.4 Custom Events (reusable script functions)

- `LookupPower(enemy_id, act_choice)` → `battle_power`
- `CalcDamage` → `battle_damage`
- `ApplyDamageToEnemy` / `ApplyDamageToPlayer`
- `LoadEnemyStats(enemy_id)`
- `EnemyTakeTurn`
- `DrawHealthBars`

### 5.5 Health Bars

Drawn as a row of text characters in the dialogue box rather than as sprites:
`[████░░░░]` computed by `bar_filled = (energy * 8) / energy_max`. Costs
no tiles and no art, and reads clearly on a DMG screen.

### 5.6 Build & verification

GB Studio ships only as a flatpak GUI here (no `gb-studio-cli`), **but** the
full GBDK toolchain is bundled inside `resources/app.asar` under
`buildTools/linux-x64`. Extracted to `~/.cache/deskbound-build/extract/`, it
compiles real ROMs headlessly — verified by building a 32KB test ROM with
SDCC 4.5.1.

Two setup gotchas, both already solved: extraction drops exec bits (`chmod -R +x
bin libexec`, else `sdcpp` fails with a misleading `cannot execute 'cc1'`), and
`GBDKDIR` must be exported with a trailing slash.

This means **I can compile and sanity-check the game without the GUI.** Full
GB Studio project compilation still routes through the app's own build pipeline,
so the GUI remains the source of truth for a final build — but the toolchain
being present de-risks the whole project.

**Version note (resolved):** the project reports `_version: 4.2.0 / _release: 10`
while the installed app is 4.3.2 — but the 4.3.2 app's *own* bundled templates
are also `4.2.0 / release 10`. The project format did not change between those
app versions, so **no upgrade is required** and no migration risk exists.

### 5.7 The stats screen

START opens the `stats` scene from anywhere except the title, and returns you to
the exact tile you were standing on. Four engine facts shape how it is wired:

- **Input bindings die on every scene change** (`events_init` on
  `EXCEPTION_CHANGE_SCENE`), so `AttachStatsButton` has to be called from each
  scene's On Init. It cannot be bound once.
- **Input scripts only fire while the VM is unlocked**, and scene On Init,
  actor and trigger scripts all compile with `VM_LOCK`. START is therefore dead
  during any dialogue — and dead for the whole fight, since the battle runs
  inside the battle scene's On Init. The `battle` scene deliberately does *not*
  call `AttachStatsButton`; it doesn't need to.
- **Pop Scene State re-runs the target scene's On Init.** That is why `home`
  wraps its day setup in a `stats_return` guard: without it, coming back would
  re-run `NewDay` and hand the player a free full heal. `street` needs no guard
  — its On Init is idempotent and `camera_x`/`camera_y` survive a scene load, so
  the commute resumes. Every other scene that binds START clears `stats_return`
  on entry, so the flag can never leak into a later visit to `home`.
- **Only the numbers are drawn at runtime.** The VWF glyph pool is 52 tiles and
  is shared across consecutive Draw Text calls, so every static label lives in
  `assets/backgrounds/stats.png` (regenerate with `tools/gen_stats_bg.py`). The
  Draw Text events switch to GBS Mono via an inline `!F:<id>!` code, which is
  what keeps values at one character per tile and aligned with those labels.

---

## 6. Art Requirements

This is the part I cannot do well — listing it explicitly so it's clear what a
human artist needs to supply.

| Asset | Spec | Priority |
|---|---|---|
| Office floor background | 160×144+, 8px grid, ≤192 unique tiles | High |
| Break room / print station / meeting room backgrounds | same | High |
| Battle backdrop | 160×144, simple | High |
| Player sprite (4-dir walk) | 16×16, 8x16 sprite mode | High |
| Enemy battle sprites ×3 | ~32×32 | High |
| Coworker NPC sprites ×2–3 | 16×16 | Medium |
| Title screen | 160×144 | Medium |

**Interim plan:** I generate flat placeholder graphics (blocked-out rooms,
labelled rectangles for enemies) so the game is *playable and testable*
immediately. Real art swaps in later without touching any scripting, as long as
dimensions match.

### Audio

The template ships `template.mod`. v1 needs: title theme, office ambience,
battle theme, victory jingle. Low priority — the game is playable silent.

---

## 7. Design Decisions & Rationale

**No MP / resource meter.** *(Your call — and it makes the design better.)* With
per-enemy effects doing the work, an MP bar would have meant tracking two
puzzles at once: "which verb is right" *and* "can I afford it". The first is the
interesting one. Dropping MP also means no consumable to balance and no
resource-starvation failure state.

**No items.** *(Your call.)* Items in a 20-minute game are mostly inventory UI
for a healing button. The damage floor and generous starting Energy (see
§9.1) already guarantee every fight is winnable without one.

**Per-enemy verb effects instead of a type chart.** A type chart needs ≥6
enemies before players can feel it. Three hand-written enemies × four verbs =
12 bespoke jokes, which is *more* content and *less* system.

**No random encounters.** Every battle is a deliberate interaction with a
visible object. Random encounters pad a large world; a 20-minute office game is
all signal — and forced battles while walking would be genuinely annoying rather
than *comedically* annoying.

**No catching / party system.** The obvious Pokémon riff would be recruiting
office objects. Good idea, doubles the systems work. Held for v2.

**LOOK is free.** See §3.2 — charging a turn for reading flavour text would
train players to skip the writing.

**One shared battle scene.** See §5.1 — the biggest maintenance win available
in a GB Studio project of this shape.

---

## 8. Risks & Open Questions

- **Tile budget.** GB Studio backgrounds cap at 192 unique tiles (mono).
  Mitigation: repetitive, modular office furniture — thematically perfect anyway.
- **Script complexity.** The §5.3 lookup is the main sprawl risk. Mitigation:
  custom events, aggressively.
- **Menu text width.** The old 6-character menu limit was lifted, but screen
  width still binds: the ACT submenu renders as a 2x2 grid inside the text
  box, giving each verb a real 64px column. `gen_enemies.py`'s
  `check_menu_width` measures every verb against the actual font and fails
  the build if one doesn't fit — `INTERACT` is the tightest so far at 61px.
- **Sprite height vs. tile geometry.** Sprites are 8x16, so the player occupies
  two vertical tiles and can never stand on the bottom row of a scene. Exit
  triggers must sit at `height - 2` or above, and arrival points must not
  overlap a return trigger.
- ~~Project version upgrade.~~ **Resolved** — no format change between app 4.2.0 and 4.3.2; see §5.6.

### Resolved decisions

1. **Difficulty: comedic and easy.** The player should essentially always win.
   Tuning follows from this — see §9.
2. **Losing: comedic, never punishing.** No game-over screen, no lost progress.
   See §9.2.
3. **FLEE: works on regular enemies, refused by the boss** with a retort.
   See §9.3.
4. **Player name: fixed.** You are "the New Guy". No name-entry flow in v1.

---

## 9. Difficulty & Failure

### 9.1 Tuning for "you basically always win"

Easy does not mean *frictionless* — it means the player never feels stuck or
punished. Concretely:

- **Player stats are generous:** Energy 100 to start the day, Brains 8,
  Patience 12. Energy is a *daily* budget spent across every fight before
  bedtime, so "generous" means a day holds several encounters, not that each
  fight starts full.
- **`max(1, …)` in the damage formula** means no turn is ever wasted.
- **Weak verbs have a damage floor** (`WEAK_VERB_FLOOR = 3`, and `7` for the
  boss). Without it, a player who stubbornly repeats one verb can hit an
  unwinnable fight — see the simulation results below.
- **Enemy damage is scaled to 7/10**, so fights run long enough to show the
  jokes rather than ending in three turns.

The design target: a player choosing at random should still win every fight.
A player who *reads the enemy* wins roughly twice as fast. Skill changes pace,
not outcome.

#### Verified by simulation

The damage ranges in `enemies.yaml` were tuned by interpreting the *generated*
`BattleScript` event tree directly (2000 games per cell), so the numbers below
are the shipped script's behaviour, not a re-implementation of it:

| Enemy | random | always THINK | always TALK | always EMAIL | always INTERACT |
|---|---|---|---|---|---|
| Coffee (60 HP) | 100% · 7.0t | 100% · 4.4t | 100% · 10.5t | 100% · 13.8t | 100% · 5.7t |
| Printer (65 HP) | 100% · 7.6t | 99.8% · 14.8t | 100% · 11.3t | 100% · 4.0t | 100% · 8.6t |
| Meeting (105 HP) | 100% · 9.9t | 100% · 12.1t | 100% · 6.7t | 100% · 11.0t | 100% · 12.8t |

Every strategy wins; none stalls. Optimal play is ~2× faster than stubborn
play, so reading the enemy is rewarded with pace rather than survival.

### 9.2 Running out of Energy

You don't get a game over. You **go home and sleep.**

```
Your Energy hits 0.
  → "You have run out of Energy."
  → "You quietly gather your things."
  → "You go home early. Nobody notices."
  → Fade out. You sleep.
  → Next morning: Energy restored, dayOfWeek advances.
```

The battle ends (`battle_result = 3`), says its line, and calls the
`player_fainted` hook — the `Faint` script — which is what walks you home. Anything already beaten stays beaten — the story flags
are what persist. The enemy you collapsed against, though, is back at full
Energy tomorrow: `BattleScript` re-initialises enemy Energy at the start of
every fight. Persisting per-enemy damage would need a variable per enemy, and
the week already provides the difficulty relief that partial damage used to.

**The cost is the day, not the progress.** That is the whole reason the week
exists. A player who collapses every afternoon still reaches Friday; they just
arrive with fewer things crossed off, and the ending says so. Failure is a
shorter day, which is exactly how the joke should land — the game cannot bring
itself to punish you, it can only let time pass.

Repeated collapses add escalating one-liners on the way out ("You go home early.
Again." / "HR has noticed."), turning failure into a joke generator rather than
a wall.

**Open: how much Energy sleep gives back.** Full restore keeps the comedic
promise that every morning is a clean slate. A partial restore would let a bad
Monday echo into Tuesday and make the week genuinely tense. This is the main
difficulty dial left, and it is a single value in the overworld's wake-up
script — the battle never touches it (§5.2).

### 9.3 FLEE

| Context | Result |
|---|---|
| Regular enemy | Succeeds ~75% (`rnd(4) > 0`). "You walk away. The problem remains, but so do you." |
| Regular enemy, failed | Costs the turn. "You get as far as the door and remember you need coffee." |
| **Boss** | **Always refused, no turn lost.** |

Boss refusal lines (cycled):
- "You can't leave. It's in your calendar."
- "You stand up. Eleven people look at you. You sit back down."
- "The meeting invite has no decline button. You check. Twice."

Refusing without consuming the turn keeps it a joke rather than a trap — trying
to flee the boss costs nothing but dignity.

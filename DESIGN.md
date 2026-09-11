# DeskBound — Game Design Document

> A Pokémon-inspired turn-based RPG where an office worker battles the mildly
> infuriating objects of corporate life.

**Engine:** GB Studio (project `4.2.0`, installed app `4.3.2`) · **Platform:** Game Boy (DMG, mono) · **Author:** KeeTraxx

---

## 1. Concept

You are **the New Guy**, hired Monday morning into an open-plan office. The
building's objects have opinions. The coffee machine is passive-aggressive. The
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

```
Explore office floor  →  Encounter an infuriating thing  →  Turn-based battle
        ↑                                                          │
        └───────────  Gain Composure / story progress  ←───────────┘
```

1. **Explore** the office in top-down view. Talk to coworkers, read the
   passive-aggressive fridge notes.
2. **Encounter** an office thing by interacting with it (no random encounters —
   see §7 Design Decisions).
3. **Battle** it in a turn-based fight on a dedicated battle scene.
4. **Progress**: winning unlocks the next area of the floor. The day advances.

---

## 3. The Battle System

This is the heart of the game and the part that is pure scripting — no art
dependency beyond a static battle backdrop and one enemy sprite each.

### 3.1 Stats

Both player and enemy use three stats. **There is no MP/resource meter** — move
choice is driven by *which enemy you're facing*, not by spending a currency.

| Stat | Meaning |
|---|---|
| **Composure (HP)** | How much nonsense you can absorb before you snap. Hits 0 → you lose. |
| **Nerve (ATK)** | How hard your moves land. |
| **Patience (DEF)** | How well you absorb theirs. |

Variables are 16-bit (0–65535) in GB Studio 4, so there's no need to squeeze
numbers into a byte. Realistic ranges: Composure 20–120, Nerve/Patience 5–40.

### 3.2 Turn Structure

Strictly alternating, player-first. No speed stat — it adds a turn-order branch
without adding much fun.

```
┌─ PLAYER TURN ────────────────────────────────┐
│ Top menu: ACT / LOOK / FLEE                  │
│   ACT  → submenu: FIX / TALK / EMAIL / SHRUG │
│          → resolve per-enemy effect          │
│   LOOK → flavour text only, no effect,       │
│          does NOT consume the turn           │
│   FLEE → attempt to escape (may fail)        │
│ Apply damage → check enemy Composure ≤ 0     │
└──────────────────┬───────────────────────────┘
                   ↓ enemy still standing
┌─ ENEMY TURN ─────────────────────────────────┐
│ Pick move via weighted rnd()                 │
│ Show witty enemy line → resolve → apply dmg  │
│ Check player Composure ≤ 0                   │
└──────────────────┬───────────────────────────┘
                   ↓
             back to PLAYER TURN
```

**LOOK does not consume a turn.** It's an information verb, not a tactical
choice — punishing curiosity would discourage reading the jokes, which are the
actual content of the game.

### 3.3 Damage Formula

Kept simple and readable as a GB Studio math expression:

```
damage = max(1, (move_power + player_Nerve) - (enemy_Patience / 2) + rnd(4))
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
| **FIX** | Engage with the problem practically. |
| **TALK** | Reason with it. Address the thing as a person. |
| **EMAIL** | Escalate in writing. Paper trail. |
| **SHRUG** | Disengage. Accept the absurdity. |

### 3.5 Per-Enemy Effects — the core mechanic

**Every verb does something different against every enemy.** This replaces both
the type chart and the MP economy: the puzzle is *reading the enemy* and finding
its two good verbs, and the comedy lives in the mismatches.

Power values below feed `move_power` in §3.3. Negative or zero power means the
move does something other than damage.

#### Dirty Coffee Machine · Composure 60 · Nerve 6 · Patience 4
*Encrusted. Judgmental. Has seen things.*

| Verb | Pow | Result |
|---|---|---|
| **FIX** | **12** | You descale it. It shudders with something like relief. *Strong.* |
| TALK | 4 | "You talk to the coffee machine. It gurgles noncommittally." |
| EMAIL | 2 | "You email Facilities. The ticket is auto-closed as duplicate." *Weak.* |
| **SHRUG** | **10** | You drink it black and bitter, like it wants. It respects this. *Strong.* |

**Lesson taught:** practical action and acceptance both work. Escalation doesn't.

#### The Printer · Composure 65 · Nerve 9 · Patience 8
*It has never worked. It will never work. It is not sorry.*

| Verb | Pow | Result |
|---|---|---|
| FIX | 3 | You open tray 2. There is no jam in tray 2. There is never a jam in tray 2. *Weak.* |
| TALK | 0 | You say "please." The printer emits one sheet of a document from 2017. *No damage.* |
| **EMAIL** | **16** | You CC the office manager. Bureaucracy is the only language it fears. *Strong.* |
| SHRUG | 6 | You walk away. It beeps, wounded by the indifference. |

**Lesson taught:** the verb that won last fight is now the worst one. FIX fails
here precisely because it succeeded against the coffee machine.

#### The Meeting That Could've Been An Email · Composure 105 · Nerve 12 · Patience 10 · **BOSS**
*It has no agenda. It has twelve attendees. It has already run over.*

| Verb | Pow | Result |
|---|---|---|
| FIX | 5 | You propose an agenda. Someone says "good point" and continues. *Weak.* |
| **TALK** | **14** | You say the quiet part: "Could this have been an email?" *Strong.* |
| EMAIL | 8 | You send the follow-up email *during* the meeting. Deeply illegal. Effective. |
| **SHRUG** | **2** | You stop resisting. **Restores 12 Composure** and still chips. Survival, mostly. |

**Lesson taught:** the boss can't be fixed or escalated away — it must be named
aloud, and SHRUG flips from attack to heal, so the fight has a sustain option.

### 3.6 Enemy Moves — all with flavour text

Each enemy has three moves picked by weighted `rnd()`. Every one prints a line;
the enemy turn is a punchline delivery system.

**Dirty Coffee Machine**
| Move | Effect | Line |
|---|---|---|
| Lukewarm Betrayal | dmg | "It dispenses something at exactly body temperature." |
| Passive Drip | dmg, low | "It drips. Slowly. Onto the counter you just cleaned." |
| Out Of Beans | −2 Nerve | "OUT OF BEANS, it announces, with beans clearly visible." |

**The Printer**
| Move | Effect | Line |
|---|---|---|
| PC LOAD LETTER | dmg, halves Patience | "PC LOAD LETTER. No one has ever known what this means." |
| Phantom Jam | dmg | "It reports a paper jam. There is no paper. There is no jam." |
| Toner Low | −2 Nerve | "TONER LOW, it says, at 94% toner." |

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

A single office floor, one in-game day, three battles.

| # | Beat | Content |
|---|---|---|
| 1 | **9:00 Arrival** | Intro, tutorial on movement. Coworker explains Composure. |
| 2 | **Break Room** | Battle 1 — Dirty Coffee Machine. Teaches ACT verbs. |
| 3 | **The Corridor** | Exploration, NPC chatter, hints about the printer. |
| 4 | **Print Station** | Battle 2 — The Printer. Punishes reusing FIX. |
| 5 | **17:00 Meeting Room** | Boss — The Meeting. Win → you go home. Credits. |

Estimated playtime: 15–20 minutes. Deliberately small — a complete, polished
short game beats an unfinished sprawling one.

---

## 5. Technical Plan

### 5.1 Scenes

| Scene | Type | Purpose |
|---|---|---|
| `title` | LOGO | Title screen, press START |
| `office_floor` | TOPDOWN | Main explorable area |
| `break_room` | TOPDOWN | Coffee machine encounter |
| `print_station` | TOPDOWN | Printer encounter |
| `meeting_room` | TOPDOWN | Boss encounter |
| `battle` | POINTNCLICK | **Shared battle scene** (see below) |

**Key architectural decision:** *one* reusable battle scene, not one per enemy.
Before triggering a battle, the overworld sets `enemy_id`; the battle scene's
On Init loads that enemy's stats and effect table. Adding enemy #4 is a data
change, not a new scene.

`POINTNCLICK` is used for the battle scene so there's no player actor wandering
around during a fight.

### 5.2 Variables

```
Player:   player_composure, player_composure_max, player_nerve, player_patience
Enemy:    enemy_id, enemy_composure, enemy_composure_max,
          enemy_nerve, enemy_patience, enemy_last_move
Battle:   battle_menu_choice, battle_act_choice, battle_power,
          battle_damage, battle_temp, battle_result, battle_turn_count
Progress: story_flag_coffee, story_flag_printer, story_flag_boss
```

Notably absent: caffeine/MP and all item counters.

### 5.3 The effect lookup

The one genuinely fiddly bit. GB Studio has no arrays, so the
(enemy × verb) → power table is a nested conditional inside a custom event:

```
LookupPower(enemy_id, act_choice) → battle_power
  if enemy_id == 1:  if act == FIX → 12, TALK → 4, EMAIL → 2, SHRUG → 10
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
`[████░░░░]` computed by `bar_filled = (composure * 8) / composure_max`. Costs
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
for a healing button. SHRUG-as-heal against the boss covers the sustain need
without an inventory screen.

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
  width still binds. `FIX/TALK/EMAIL/SHRUG` are all ≤5 chars — comfortably safe.
- **Sprite height vs. tile geometry.** Sprites are 8x16, so the player occupies
  two vertical tiles and can never stand on the bottom row of a scene. Exit
  triggers must sit at `height - 2` or above, and arrival points must not
  overlap a return trigger. Both are now checked by `tools/validate.py`.
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

- **Player stats are generous:** Composure 100, Nerve 8, Patience 12.
- **`max(1, …)` in the damage formula** means no turn is ever wasted.
- **Weak verbs have a damage floor** (`WEAK_VERB_FLOOR = 3`, and `7` for the
  boss). Without it, a player who stubbornly repeats one verb can hit an
  unwinnable fight — see the simulation results below.
- **Enemy damage is scaled to 7/10**, so fights run long enough to show the
  jokes rather than ending in three turns.
- **The boss's SHRUG heals 12 *and* chips for 2.** The chip is essential: with
  a pure heal, SHRUG-spam is an infinite stalemate (simulated: 800/800 games
  never terminated).

The design target: a player choosing at random should still win every fight.
A player who *reads the enemy* wins roughly twice as fast. Skill changes pace,
not outcome.

#### Verified by simulation

`tools/` constants were tuned against a simulation of the exact shipped
formulas (3000 games per cell):

| Enemy | random | optimal | worst | always FIX | always SHRUG |
|---|---|---|---|---|---|
| Coffee (60 HP) | 100% · 5.0t | 100% · 3.9t | 100% · 7.4t | 100% · 3.9t | 100% · 4.1t |
| Printer (65 HP) | 100% · 6.6t | 100% · 3.7t | 100% · 11.2t | 100% · 11.2t | 100% · 7.1t |
| Meeting (105 HP) | 100% · 9.1t | 100% · 6.0t | 100% · 16.6t | 99.9% · 9.6t | 100% · 16.6t |

Every strategy wins; none stalls. Optimal play is ~2× faster than stubborn
play, so reading the enemy is rewarded with pace rather than survival.

### 9.2 Losing (0 Composure)

You don't get a game over. You **go home early.**

```
Your Composure hits 0.
  → "You have run out of Composure."
  → "You quietly gather your things."
  → "You go home. It's 14:30. Nobody notices."
  → Fade out. Next morning. Same day, again.
  → Re-enter the battle at full Composure.
```

The enemy keeps any damage you already did **the first time you retry** — so a
second attempt is always shorter. This is invisible generosity: it reads as
comedy, functions as difficulty relief, and means even a losing player advances.

Repeated losses add escalating one-liners on the way out ("You go home early.
Again." / "HR has noticed."), turning failure into a joke generator rather than
a wall.

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

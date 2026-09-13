#!/usr/bin/env python3
"""Generate ProTracker .mod songs for the GB Studio music folder.

GB Studio's MOD support is not general-purpose ProTracker: the four MOD
channels map straight onto the Game Boy's four hardware channels, and the
*sample slot* picks which hardware timbre plays. That mapping is baked into
`assets/music/template.mod`, whose 31 sample slots are named after what they
actually do on hardware (see SAMPLES below):

    ch1, ch2 -> pulse   (slots 1-4: duty cycle)
    ch3      -> wave    (slots 8-15: wavetable shape)
    ch4      -> noise   (slots 16-31: periodic / white noise)

So a song here is *only* pattern data. This script copies the template's
header and sample blob verbatim and rewrites the title, order table and
patterns, which is why the output is byte-identical in size to the template.

Effect vocabulary is deliberately narrow — Cxx (set volume) and ECx (note cut)
are what `lounge_elevator.mod` already uses and are known to survive the
MOD -> Game Boy conversion. Notes ring forever on GB hardware, so every note
gets an explicit C00 at its end row; that is what makes the staccato comping
and plucked bass read as jazz rather than as a drone.

Timing: 4 rows per beat at speed 6, so the Fxx tempo byte is the literal BPM
and a 64-row pattern is exactly 4 bars of 4/4.

Usage:
    python3 tools/gen_music.py               # write every song
    python3 tools/gen_music.py coffee_break  # write one
"""
import os
import struct
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(HERE, os.pardir, "assets", "music")
TEMPLATE = os.path.join(MUSIC_DIR, "template.mod")

# --- MOD layout constants -------------------------------------------------
PATTERN_OFFSET = 1084          # after 20b title + 31 samples * 30b + 130b order
PATTERN_BYTES = 64 * 4 * 4     # 64 rows * 4 channels * 4 bytes
ROWS = 64
ROWS_PER_BAR = 16              # 4 rows/beat * 4 beats
BARS_PER_PATTERN = ROWS // ROWS_PER_BAR

# --- Sample slots, by what they are on Game Boy hardware ------------------
PULSE_50 = 2        # fullest pulse -> lead
PULSE_12 = 4        # thinnest pulse -> comping, sits behind the lead
WAVE_SAW = 13       # sawtooth wave -> upright-ish bass
NOISE_KICK = 16     # periodic noise 1, played low
NOISE_RIDE = 24     # white noise B, played high
NOISE_SNARE = 26    # white noise F, played mid

# --- Effects --------------------------------------------------------------
def vol(v):
    """Cxx - set channel volume (0-64)."""
    return 0xC00 | v

def cut(tick):
    """ECx - cut the note after `tick` ticks."""
    return 0xEC0 | tick

def speed(ticks):
    """Fxx below 0x20 - ticks per row."""
    return 0xF00 | ticks

def tempo(bpm):
    """Fxx at 0x20 or above - beats per minute (4 rows/beat at speed 6)."""
    return 0xF00 | bpm

SILENCE = vol(0)

# --- Note periods ---------------------------------------------------------
NOTE_NAMES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
# Amiga period table, finetune 0. Octave 1 is where the wave channel bass
# lives; the pulse channels sit in octaves 3-4.
OCTAVES = {
    1: [1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906],
    2: [856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453],
    3: [428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226],
    4: [214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113],
    5: [107, 101, 95, 90, 85, 80, 76, 71, 67, 64, 60, 57],
}

def period(note):
    """'A#3' -> Amiga period."""
    return OCTAVES[int(note[2])][NOTE_NAMES.index(note[:2])]


class Channel:
    """One MOD channel, addressed by absolute row.

    Writes never clobber: a note placed on a row wins over a trailing C00 from
    the previous note, which is what lets each voice be written as independent
    (row, note, duration) events without hand-checking for collisions.
    """

    def __init__(self, sample):
        self.sample = sample
        self.cells = {}  # row -> (period, sample, effect)

    def note(self, row, name, duration, volume, sample=None, tail=SILENCE):
        if row >= ROWS:
            return
        self.cells[row] = (period(name), sample or self.sample, vol(volume))
        end = row + duration
        if tail is not None and end < ROWS and end not in self.cells:
            self.cells[end] = (0, 0, tail)

    def hit(self, row, name, volume, sample, tick=None):
        """Percussion: one note, cut either by ECx or by a trailing C00."""
        if row >= ROWS:
            return
        eff = cut(tick) if tick is not None else vol(volume)
        self.cells[row] = (period(name), sample, eff)
        if tick is None and row + 1 < ROWS and row + 1 not in self.cells:
            self.cells[row + 1] = (0, 0, SILENCE)

    def effect(self, row, eff):
        if row in self.cells:
            per, samp, _ = self.cells[row]
            self.cells[row] = (per, samp, eff)
        else:
            self.cells[row] = (0, 0, eff)

    def encode(self, row):
        per, samp, eff = self.cells.get(row, (0, 0, 0))
        return bytes([
            (samp & 0xF0) | ((per >> 8) & 0x0F),
            per & 0xFF,
            ((samp & 0x0F) << 4) | ((eff >> 8) & 0x0F),
            eff & 0xFF,
        ])


def build_pattern(channels):
    out = bytearray()
    for row in range(ROWS):
        for ch in channels:
            out += ch.encode(row)
    return bytes(out)


def write_mod(path, title, patterns, order):
    with open(TEMPLATE, "rb") as fh:
        template = bytearray(fh.read())

    samples = bytes(template[PATTERN_OFFSET + 4 * PATTERN_BYTES:])
    header = template[:PATTERN_OFFSET]
    header[0:20] = title.encode("ascii")[:20].ljust(20, b"\0")
    header[950] = len(order)
    header[951] = 127  # restart position; ProTracker convention for "loop all"
    header[952:952 + 128] = bytes(order).ljust(128, b"\0")

    body = b"".join(patterns)
    assert len(body) == len(patterns) * PATTERN_BYTES
    with open(path, "wb") as fh:
        fh.write(bytes(header) + body + samples)


def write_gbsres(mod_path, name):
    """GB Studio 4 discovers assets through a sibling .gbsres descriptor."""
    res_path = mod_path + ".gbsres"
    if os.path.exists(res_path):
        return False  # keep the existing id so scene references stay valid
    import json
    with open(res_path, "w") as fh:
        json.dump({
            "_resourceType": "music",
            "id": str(uuid.uuid4()),
            "name": name,
            "symbol": "song_" + name,
            "settings": {},
            "filename": os.path.basename(mod_path),
            "type": "mod",
        }, fh, indent=2)
        fh.write("\n")
    return True


# ==========================================================================
# Coffee Break - a happy jazz loop
# ==========================================================================
# 16 bars in F major over a I-vi-ii-V core with a Bb / Bdim7 bridge, which is
# the most "cheerful standard" set of changes that still sounds like jazz on
# three voices. Bars are grouped 4-4-4-4 and land back on C7 so the loop point
# resolves instead of restarting cold.

BPM = 128

# Walking bass: one note per beat on the wave channel, octave 1-2.
BASS = [
    ["F-1", "A-1", "C-2", "E-2"],    # Fmaj7
    ["D-2", "C-2", "A-1", "F-1"],    # Dm7
    ["G-1", "A#1", "D-2", "F-2"],    # Gm7
    ["E-2", "D-2", "C-2", "A#1"],    # C7
    ["F-1", "A-1", "C-2", "E-2"],    # Fmaj7
    ["D-2", "F-2", "E-2", "D-2"],    # Dm7
    ["G-1", "A#1", "D-2", "C-2"],    # Gm7
    ["C-2", "A#1", "A-1", "G-1"],    # C7
    ["A#1", "D-2", "F-2", "D-2"],    # Bbmaj7
    ["B-1", "D-2", "F-2", "G#1"],    # Bdim7
    ["C-2", "A-1", "C-2", "E-2"],    # Fmaj7/C
    ["A-1", "C#2", "E-2", "G-2"],    # A7
    ["D-2", "C-2", "A#1", "A-1"],    # Dm7
    ["G-1", "B-1", "D-2", "F-2"],    # G7
    ["G-1", "A#1", "D-2", "F-2"],    # Gm7
    ["C-2", "E-2", "G-2", "A#1"],    # C7 -> loops to F
]

# Lead: (row-in-bar, note, length in rows). Rows 0/4/8/12 are beats, 2/6/10/14
# are the off-beats that carry the syncopation.
LEAD = [
    [(0, "C-4", 3), (4, "A-3", 2), (6, "C-4", 2), (8, "D-4", 4), (12, "C-4", 4)],
    [(0, "A-3", 3), (4, "F-3", 2), (6, "A-3", 2), (8, "C-4", 2), (10, "A-3", 2), (12, "G-3", 4)],
    [(0, "A#3", 3), (4, "D-4", 2), (6, "C-4", 2), (8, "A#3", 4), (12, "A-3", 4)],
    [(0, "G-3", 2), (2, "A-3", 2), (4, "A#3", 4), (8, "G-3", 4), (12, "E-3", 3)],
    [(0, "F-3", 3), (4, "A-3", 3), (8, "C-4", 3), (12, "E-4", 3)],
    [(0, "D-4", 2), (2, "C-4", 2), (4, "A-3", 4), (8, "F-3", 4), (12, "A-3", 3)],
    [(0, "A#3", 3), (4, "A-3", 2), (6, "A#3", 2), (8, "D-4", 4), (12, "F-4", 4)],
    [(0, "E-4", 3), (4, "D-4", 2), (6, "C-4", 2), (8, "A#3", 4), (12, "G-3", 3)],
    [(0, "D-4", 3), (4, "F-4", 2), (6, "D-4", 2), (8, "C-4", 4), (12, "A#3", 4)],
    [(0, "B-3", 3), (4, "D-4", 2), (6, "F-4", 2), (8, "G#4", 4), (12, "F-4", 3)],
    [(0, "E-4", 3), (4, "C-4", 2), (6, "A-3", 2), (8, "C-4", 4), (12, "A-3", 3)],
    [(0, "C#4", 3), (4, "E-4", 2), (6, "G-4", 2), (8, "E-4", 4), (12, "C#4", 3)],
    [(0, "D-4", 3), (4, "F-4", 2), (6, "E-4", 2), (8, "D-4", 4), (12, "C-4", 4)],
    [(0, "B-3", 3), (4, "D-4", 2), (6, "F-4", 2), (8, "D-4", 4), (12, "B-3", 3)],
    [(0, "A#3", 3), (4, "D-4", 3), (8, "F-4", 3), (12, "D-4", 3)],
    [(0, "E-4", 3), (4, "D-4", 2), (6, "C-4", 2), (8, "G-3", 3), (12, "A#3", 4)],
]

# Comping: the 3rd and 7th of each chord only. Those two notes are what make a
# chord sound major/minor/dominant, so a single channel alternating between
# them spells the changes without needing real chords.
GUIDE_TONES = [
    ["E-3", "A-2"],   # Fmaj7
    ["F-3", "C-3"],   # Dm7
    ["F-3", "A#2"],   # Gm7
    ["E-3", "A#2"],   # C7
    ["E-3", "A-2"],   # Fmaj7
    ["F-3", "C-3"],   # Dm7
    ["F-3", "A#2"],   # Gm7
    ["E-3", "A#2"],   # C7
    ["D-3", "A-2"],   # Bbmaj7
    ["D-3", "G#2"],   # Bdim7
    ["E-3", "A-2"],   # Fmaj7/C
    ["G-3", "C#3"],   # A7
    ["F-3", "C-3"],   # Dm7
    ["F-3", "B-2"],   # G7
    ["F-3", "A#2"],   # Gm7
    ["E-3", "A#2"],   # C7
]
COMP_OFFBEAT = [2, 10]       # push against the beat
COMP_PUSH = [0, 6, 12]       # denser figure to close each 4-bar group

# Ride cymbal on 1, 2, 2&, 3, 4, 4& - the standard jazz ride rhythm.
RIDE_ROWS = [0, 4, 6, 8, 12, 14]
FILL_ROWS = [2, 6, 10, 14]

VOL_LEAD = 44
VOL_COMP = 22
VOL_BASS = 56
VOL_RIDE = 18
VOL_SNARE = 34
VOL_KICK = 48


def coffee_break():
    patterns = []
    for pat in range(len(BASS) // BARS_PER_PATTERN):
        lead = Channel(PULSE_50)
        comp = Channel(PULSE_12)
        bass = Channel(WAVE_SAW)
        drums = Channel(NOISE_RIDE)

        for local_bar in range(BARS_PER_PATTERN):
            bar = pat * BARS_PER_PATTERN + local_bar
            base = local_bar * ROWS_PER_BAR

            for row, name, length in LEAD[bar]:
                lead.note(base + row, name, length, VOL_LEAD)

            # Two guide tones cycled over the bar's rhythmic figure.
            figure = COMP_PUSH if bar % 4 == 3 else COMP_OFFBEAT
            tones = GUIDE_TONES[bar]
            for i, row in enumerate(figure):
                comp.note(base + row, tones[i % len(tones)], 2, VOL_COMP)

            for beat, name in enumerate(BASS[bar]):
                # 3 rows of a 4-row beat: the gap is the pluck.
                bass.note(base + beat * 4, name, 3, VOL_BASS)

            rows = dict.fromkeys(RIDE_ROWS, "ride")
            rows[10] = "snare" if bar % 2 else "ride"
            if bar % 4 == 0:
                rows[0] = "kick"          # mark the top of each 4-bar group
            if bar == len(BASS) - 1:
                rows.update(dict.fromkeys(FILL_ROWS, "snare"))  # turnaround fill
            for row, kind in sorted(rows.items()):
                if kind == "ride":
                    drums.hit(base + row, "A-4", VOL_RIDE, NOISE_RIDE)
                elif kind == "snare":
                    drums.hit(base + row, "C-3", VOL_SNARE, NOISE_SNARE)
                else:
                    drums.hit(base + row, "C-2", VOL_KICK, NOISE_KICK)

        if pat == 0:
            # Both halves of the timing setup need their own cell, and comp is
            # the only voice not playing on rows 0-1.
            comp.effect(0, speed(6))
            comp.effect(1, tempo(BPM))

        patterns.append(build_pattern([lead, comp, bass, drums]))
    return patterns


SONGS = {
    "coffee_break": ("Coffee Break", coffee_break),
}


def main():
    wanted = sys.argv[1:] or sorted(SONGS)
    for name in wanted:
        if name not in SONGS:
            sys.exit("unknown song %r (have: %s)" % (name, ", ".join(sorted(SONGS))))
        title, build = SONGS[name]
        patterns = build()
        path = os.path.normpath(os.path.join(MUSIC_DIR, name + ".mod"))
        write_mod(path, title, patterns, list(range(len(patterns))))
        fresh = write_gbsres(path, name)
        print("wrote %s (%d patterns, %d bars)%s" % (
            os.path.relpath(path, os.path.join(HERE, os.pardir)),
            len(patterns),
            len(patterns) * BARS_PER_PATTERN,
            "" if fresh else " [kept existing .gbsres]",
        ))


if __name__ == "__main__":
    main()

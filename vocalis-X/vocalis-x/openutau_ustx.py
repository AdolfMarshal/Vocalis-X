"""
openutau_ustx.py — Vocalis-X
Generates OpenUTAU .ustx project files for Raine Rena DiffSinger 2.01.

Pitch priority:
  1. basic_pitch melody extracted from reference vocals (if available)
  2. Chord tones from chord_extractor (if available)
  3. Scale-aware random walk (last resort)

Timing:
  - Beat-grid syllable_hits from groove template
  - Fallback: even spacing

Steps loop: DELETED.
"""

import uuid
import re
import json
import random
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SINGER_NAME   = "雷音レナ・Raine Rena 2.01"
PHONEMIZER    = "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer"

RENA_MIN      = 55   # G3
RENA_MAX      = 81   # A5
RENA_MID      = 68   # G#4
RENA_MID_TONE = RENA_MID  # backwards compat

SWEET_MIN     = 60   # C4 — comfortable floor
SWEET_MAX     = 72   # C5 — comfortable ceiling (one octave, centred)

EXPRESSIONS_BLOCK = """expressions:
  dyn:
    name: dynamics (curve)
    abbr: dyn
    type: Curve
    min: -240
    max: 120
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  pitd:
    name: pitch deviation (curve)
    abbr: pitd
    type: Curve
    min: -1200
    max: 1200
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  clr:
    name: voice color
    abbr: clr
    type: Options
    min: 0
    max: -1
    default_value: 0
    is_flag: false
    options: []
    skip_output_if_default: false
  eng:
    name: resampler engine
    abbr: eng
    type: Options
    min: 0
    max: 1
    default_value: 0
    is_flag: false
    options:
    - ""
    - worldline
    skip_output_if_default: false
  vel:
    name: velocity
    abbr: vel
    type: Numerical
    min: 0
    max: 200
    default_value: 100
    is_flag: false
    flag: ""
    skip_output_if_default: false
  vol:
    name: volume
    abbr: vol
    type: Numerical
    min: 0
    max: 200
    default_value: 100
    is_flag: false
    flag: ""
    skip_output_if_default: false
  atk:
    name: attack
    abbr: atk
    type: Numerical
    min: 0
    max: 200
    default_value: 100
    is_flag: false
    flag: ""
    skip_output_if_default: false
  dec:
    name: decay
    abbr: dec
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  gen:
    name: gender
    abbr: gen
    type: Numerical
    min: -100
    max: 100
    default_value: 0
    is_flag: true
    flag: g
    skip_output_if_default: false
  genc:
    name: gender (curve)
    abbr: genc
    type: Curve
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  bre:
    name: breath
    abbr: bre
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: true
    flag: B
    skip_output_if_default: false
  brec:
    name: breathiness (curve)
    abbr: brec
    type: Curve
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  lpf:
    name: lowpass
    abbr: lpf
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: true
    flag: H
    skip_output_if_default: false
  norm:
    name: normalize
    abbr: norm
    type: Numerical
    min: 0
    max: 100
    default_value: 86
    is_flag: true
    flag: P
    skip_output_if_default: false
  mod:
    name: modulation
    abbr: mod
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  alt:
    name: alternate
    abbr: alt
    type: Numerical
    min: 0
    max: 16
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  dir:
    name: direct
    abbr: dir
    type: Options
    min: 0
    max: 1
    default_value: 0
    is_flag: false
    options:
    - off
    - on
    skip_output_if_default: false
  shft:
    name: tone shift
    abbr: shft
    type: Numerical
    min: -36
    max: 36
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  tenc:
    name: tension (curve)
    abbr: tenc
    type: Curve
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  voic:
    name: voicing (curve)
    abbr: voic
    type: Curve
    min: 0
    max: 100
    default_value: 100
    is_flag: false
    flag: ""
    skip_output_if_default: false
exp_selectors:
- dyn
- pitd
- clr
- eng
- vel
- vol
- atk
- dec
- gen
- bre
exp_primary: 0
exp_secondary: 1
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(word: str) -> str:
    w = re.sub(r"[^A-Za-z']+", "", word)
    return w or "la"

def _clamp(tone: int) -> int:
    return max(RENA_MIN, min(RENA_MAX, int(tone)))

def _to_sweet(tone: int) -> int:
    t = int(tone)
    while t < SWEET_MIN: t += 12
    while t > SWEET_MAX: t -= 12
    return _clamp(t)

def _ticks(sec: float, bpm: float) -> int:
    return max(1, int((sec / 60.0) * bpm * 480))


def _normalize_section_name(raw: str) -> str:
    n = (raw or "").strip().lower()
    if n.startswith("verse") or n.startswith("stanza"):
        return "Verse"
    if n.startswith("chorus"):
        return "Chorus"
    if n.startswith("bridge"):
        return "Bridge"
    if n.startswith("intro"):
        return "Intro"
    if n.startswith("interlude"):
        return "Interlude"
    if n.startswith("outro"):
        return "Outro"
    return "Verse"


def _parse_lyrics_sections(lyrics: str) -> list:
    sections = []
    current = {"name": "Verse", "lines": []}
    tag_re = re.compile(r"^\[(.+)\]$")
    for raw in lyrics.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = tag_re.match(line)
        if m:
            if current["lines"] or current["name"] in ("Intro", "Interlude", "Outro"):
                sections.append(current)
            current = {"name": _normalize_section_name(m.group(1)), "lines": []}
            continue
        words = [w for w in line.split() if _clean(w)]
        if words:
            current["lines"].append(words)
    if current["lines"] or current["name"] in ("Intro", "Interlude", "Outro"):
        sections.append(current)
    if not sections:
        sections = [{"name": "Verse", "lines": [["la"]]}]
    # Keep only a single trailing empty section marker.
    cleaned = []
    for s in sections:
        if s["lines"] or s["name"] in ("Intro", "Interlude", "Outro"):
            cleaned.append(s)
    return cleaned or [{"name": "Verse", "lines": [["la"]]}]


def _section_silent_bars(name: str) -> int:
    if name == "Intro":
        return 4
    if name == "Interlude":
        return 4
    if name == "Outro":
        return 2
    return 0


def _section_range(name: str, base_tone: int) -> tuple:
    if name == "Chorus":
        return (_clamp(base_tone - 9), _clamp(base_tone + 10))
    if name == "Bridge":
        return (_clamp(base_tone - 8), _clamp(base_tone + 8))
    if name == "Verse":
        return (_clamp(base_tone - 7), _clamp(base_tone + 7))
    return (_clamp(base_tone - 8), _clamp(base_tone + 8))


def _split_word_syllables(word: str) -> list:
    """
    Lightweight syllable splitter for English-like tokens.
    Keeps behavior generic for generated lyrics without extra deps.
    """
    w = _clean(word).lower()
    if not w:
        return []
    vowels = "aeiouy"
    parts = []
    cur = w[0]
    for ch in w[1:]:
        prev_v = cur[-1] in vowels
        now_v = ch in vowels
        if prev_v != now_v:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    parts.append(cur)
    # Merge tiny fragments to avoid over-fragmentation.
    merged = []
    for p in parts:
        if merged and (len(p) == 1 or len(merged[-1]) == 1):
            merged[-1] += p
        else:
            merged.append(p)
    return merged or [w]


def _estimate_stress(syllable: str, idx: int, total: int) -> float:
    """
    Heuristic stress score in [0,1].
    Higher for longer/vowel-heavy syllables and line endings.
    """
    s = syllable.lower()
    vowels = sum(1 for c in s if c in "aeiouy")
    score = 0.25
    score += min(0.35, len(s) * 0.04)
    score += min(0.25, vowels * 0.08)
    if idx == total - 1:
        score += 0.15
    if idx == 0:
        score += 0.08
    return max(0.0, min(1.0, score))


def _nearest(items: list, target: int) -> int:
    if not items:
        return int(target)
    return min(items, key=lambda x: abs(int(x) - int(target)))


def _snap_to_scale(tone: int, scale_notes: list) -> int:
    t = _clamp(tone)
    valid = sorted(set(_clamp(n) for n in (scale_notes or []) if RENA_MIN <= int(n) <= RENA_MAX))
    if not valid:
        return _to_sweet(t)
    return _nearest(valid, t)


def _limit_leap(prev_tone: int, next_tone: int, max_leap: int = 5) -> int:
    if abs(next_tone - prev_tone) <= max_leap:
        return _clamp(next_tone)
    return _clamp(prev_tone + (max_leap if next_tone > prev_tone else -max_leap))


def _chord_target_pool(ch: dict) -> list:
    tones = [int(t) for t in (ch.get("chord_tones") or [])]
    bass = int(ch.get("bass_note", RENA_MID))
    pool = []
    for t in tones:
        ts = _to_sweet(t)
        pool.extend([_clamp(ts - 12), _clamp(ts), _clamp(ts + 12)])
    pool.extend([_to_sweet(bass), _to_sweet(bass + 4), _to_sweet(bass + 7)])
    return sorted(set([p for p in pool if RENA_MIN <= p <= RENA_MAX]))


def _smooth_tones(seq: list) -> list:
    if len(seq) < 3:
        return [_clamp(x) for x in seq]
    out = [int(seq[0])]
    for i in range(1, len(seq) - 1):
        tri = sorted([int(seq[i - 1]), int(seq[i]), int(seq[i + 1])])
        out.append(tri[1])  # median-3 smoother
    out.append(int(seq[-1]))
    return [_clamp(x) for x in out]


def _harmonic_lock_notes(
    notes: list,
    chords: list,
    scale_notes: list,
    phrase_size: int = 8,
    max_leap: int = 5,
) -> list:
    if not notes:
        return []

    locked = []
    prev = _clamp(int(notes[0]["tone"]))
    for i, n in enumerate(notes):
        t = float(n.get("time", 0.0))
        tone = _clamp(int(n.get("tone", prev)))
        ch = _chord_at(chords, t) if chords else {"chord_tones": [tone], "bass_note": tone}

        # Strong beats and phrase ends anchor to chord tones first.
        is_strong = (i % 2 == 0)
        is_phrase_end = ((i + 1) % phrase_size == 0)
        if is_strong or is_phrase_end:
            tone = _nearest(_chord_target_pool(ch), tone)

        # Keep melody in key center.
        tone = _snap_to_scale(tone, scale_notes)

        # Keep intervals singable.
        tone = _limit_leap(prev, tone, max_leap=max_leap)

        # Phrase cadence resolves to bass/root neighborhood.
        if is_phrase_end:
            cadence_pool = _chord_target_pool(ch)
            if cadence_pool:
                tone = _nearest(cadence_pool, tone)
                tone = _snap_to_scale(tone, scale_notes)

        locked.append({"time": t, "duration": float(n.get("duration", 0.4)), "tone": tone})
        prev = tone

    smoothed = _smooth_tones([n["tone"] for n in locked])
    for i, t in enumerate(smoothed):
        locked[i]["tone"] = t
    return locked


# ── Groove loader ─────────────────────────────────────────────────────────────

def _load_groove(name=None):
    d = Path("swagger_templates")
    if not d.exists():
        return None
    if name:
        t = d / name
        if t.exists():
            print(f"🧬 DNA: {t.name}")
            return json.load(open(t))
    files = list(d.glob("*.json"))
    if not files:
        return None
    c = random.choice(files)
    print(f"🎲 Random DNA: {c.name}")
    return json.load(open(c))


# ── Pitch source 1: basic_pitch ───────────────────────────────────────────────

def _load_melody(vocals_path: str) -> list:
    """
    Run basic_pitch on isolated vocals WAV.
    Returns [{time, duration, tone}] sorted by time.
    """
    try:
        from basic_pitch.inference import predict
        print(f"🎤 basic_pitch: {Path(vocals_path).name}")
        _, _, note_events = predict(vocals_path)
        notes = []
        for ev in note_events:
            start, end, midi, conf = float(ev[0]), float(ev[1]), int(ev[2]), float(ev[3])
            if (end - start) >= 0.05 and conf > 0.4:
                notes.append({"time": start, "duration": end - start, "tone": midi})
        notes.sort(key=lambda x: x["time"])
        print(f"✅ {len(notes)} melody notes")
        return notes
    except ImportError:
        print("⚠️  basic_pitch not installed — pip install basic-pitch")
        return []
    except Exception as e:
        print(f"⚠️  basic_pitch error: {e}")
        return []


def _load_midi_melody(midi_path: str) -> list:
    """
    Load melody notes from MIDI file.
    Returns [{time, duration, tone}] sorted by time.
    """
    try:
        import pretty_midi  # type: ignore
        pm = pretty_midi.PrettyMIDI(midi_path)
        notes = []
        for inst in pm.instruments:
            # Ignore drum tracks for melody use.
            if getattr(inst, "is_drum", False):
                continue
            for n in inst.notes:
                start = float(n.start)
                end = float(n.end)
                if end - start < 0.05:
                    continue
                notes.append({"time": start, "duration": end - start, "tone": int(n.pitch)})
        notes.sort(key=lambda x: x["time"])
        print(f"🎼 MIDI melody: {Path(midi_path).name} ({len(notes)} notes)")
        return notes
    except ImportError:
        print("⚠️  pretty_midi not installed — pip install pretty_midi")
        return []
    except Exception as e:
        print(f"⚠️  MIDI parse error: {e}")
        return []


def _melody_at(notes: list, t: float, prev: int) -> int:
    """Closest melody note to time t, transposed into Rena's sweet zone."""
    if not notes:
        return prev
    best = min(notes, key=lambda n: abs(n["time"] - t))
    pc = best["tone"] % 12
    # All candidate tones with this pitch class in sweet zone
    candidates = [pc + 12*o for o in range(3, 8)
                  if SWEET_MIN <= pc + 12*o <= SWEET_MAX]
    if not candidates:
        candidates = [_to_sweet(best["tone"])]
    # Prefer the one closest to previous tone (smooth voice leading)
    return _clamp(min(candidates, key=lambda x: abs(x - prev)))


# ── Pitch source 2: chord tones ───────────────────────────────────────────────

def _chord_at(chords: list, t: float) -> dict:
    if not chords:
        return {"chord_tones": [RENA_MID], "bass_note": RENA_MID}
    best = chords[0]
    for c in chords:
        if c["time"] <= t:
            best = c
        else:
            break
    return best

def _chord_tone(tones: list, prev: int, joy: float, sadness: float,
                is_end: bool, bass: int, strong_beat: bool = False) -> int:
    if is_end:
        return _clamp(_to_sweet(bass))
    sweet = sorted(set(_to_sweet(t) for t in tones)) or [RENA_MID]
    if strong_beat and len(sweet) > 2:
        sweet = sweet[:2] + [sweet[-1]]  # bias to stable chord degrees
    idx = min(range(len(sweet)), key=lambda i: abs(sweet[i] - prev))
    if joy > 0.5:
        idx = min(idx + 1, len(sweet) - 1)
    elif sadness > 0.4:
        idx = max(idx - 1, 0)
    if random.random() < 0.15:
        return _clamp(random.choice(sweet))
    return _clamp(sweet[idx])


# ── Pitch source 3: random walk ───────────────────────────────────────────────

def _walk(num: int, base: int, scale: list, joy: float,
          sadness: float, tension: float) -> list:
    scale = sorted(set(_clamp(n) for n in (scale or [])
                       if RENA_MIN <= n <= RENA_MAX))
    if len(scale) < 4:
        scale = list(range(RENA_MIN, RENA_MAX + 1, 2))

    idx = min(range(len(scale)), key=lambda i: abs(scale[i] - base))
    center = len(scale) // 2

    if joy > 0.5:      up, leap, rep = 0.60, 0.25, 0.10
    elif sadness > 0.4: up, leap, rep = 0.35, 0.10, 0.22
    elif tension > 0.4: up, leap, rep = 0.50, 0.40, 0.05
    else:               up, leap, rep = 0.52, 0.18, 0.15

    out = []
    for _ in range(num):
        out.append(scale[idx])
        if random.random() >= rep:
            step = random.choice([2, 3]) if random.random() < leap else 1
            grav = (idx - center) / max(len(scale), 1) * 0.3
            bias = max(0.2, min(0.8, up - grav))
            d    = 1 if random.random() < bias else -1
            idx  = max(0, min(len(scale) - 1, idx + d * step))
    return out


# ── Note YAML ─────────────────────────────────────────────────────────────────

def _note(pos, dur, tone, lyric, vp, vd, breath=False, pitch_in_y=0, pitch_out_y=0):
    if breath:
        return (
            f"  - position: {pos}\n    duration: {dur}\n"
            f"    tone: {tone}\n    lyric: AP\n"
            f"    pitch:\n      data:\n"
            f"      - {{x: -25, y: 0, shape: io}}\n"
            f"      - {{x: 25, y: 0, shape: io}}\n"
            f"      snap_first: true\n"
            f"    vibrato: {{length: 0, period: 0, depth: 0, "
            f"in: 0, out: 0, shift: 0, drift: 0, vol_link: 0}}\n"
            f"    tuning: 0\n    phoneme_expressions: []\n"
            f"    phoneme_overrides: []"
        )
    l = lyric
    if "'" in l or '"' in l:
        l = '"' + l.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return (
        f"  - position: {pos}\n    duration: {dur}\n"
        f"    tone: {tone}\n    lyric: {l}\n"
        f"    pitch:\n      data:\n"
        f"      - {{x: -25, y: {int(pitch_in_y)}, shape: io}}\n"
        f"      - {{x: 25, y: {int(pitch_out_y)}, shape: io}}\n"
        f"      snap_first: true\n"
        f"    vibrato: {{length: 60, period: {vp}, "
        f"depth: {vd}, in: 10, out: 10, "
        f"shift: 0, drift: 0, vol_link: 0}}\n"
        f"    tuning: 0\n    phoneme_expressions: []\n"
        f"    phoneme_overrides: []"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def build_ustx(
    lyrics: str,
    bpm: int = 120,
    base_tone: int = RENA_MID,
    emotion: dict = None,
    darkness: float = 0.2,
    energy: float = 0.5,
    scale_notes: list = None,
    is_minor: bool = False,
    groove_template: str = None,
    chords: list = None,
    vocals_path: str = None,    # isolated vocals WAV for basic_pitch
    melody_midi_path: str = None,
) -> str:

    emotion  = emotion or {}
    joy      = float(emotion.get("joy",     0.3) or 0.3)
    sadness  = float(emotion.get("sadness", 0.2) or 0.2)
    tension  = float(emotion.get("tension", 0.1) or 0.1)
    darkness = float(darkness or 0.2)
    energy   = float(energy   or 0.5)

    base_tone = _clamp(int(base_tone - darkness*6 - sadness*5 + joy*3 + energy*2))
    vib_d     = max(6,  min(40,  int(15 + sadness*18 - joy*7)))
    vib_p     = max(90, min(260, int(175 + sadness*45 - tension*25)))

    sections = _parse_lyrics_sections(lyrics)
    words = []
    silent_shift_bars = 0
    for s_idx, sec in enumerate(sections):
        if not sec["lines"]:
            silent_shift_bars += _section_silent_bars(sec["name"])
            continue
        for l_idx, line_words in enumerate(sec["lines"]):
            line_syllables = []
            for w_idx, w in enumerate(line_words):
                sylls = _split_word_syllables(w)
                if not sylls:
                    sylls = [_clean(w)]
                for syl in sylls:
                    line_syllables.append((w_idx, syl))
            for syl_idx, (w_idx, syl) in enumerate(line_syllables):
                words.append({
                    "word": syl,
                    "sec_idx": s_idx,
                    "line_idx": l_idx,
                    "word_idx_in_line": w_idx,
                    "section_name": sec["name"],
                    "prefill_bars": silent_shift_bars,
                    "syll_idx_in_line": syl_idx,
                    "line_syll_count": len(line_syllables),
                    "stress": _estimate_stress(syl, syl_idx, len(line_syllables)),
                })
            silent_shift_bars = 0
    if not words:
        words = [{
            "word": "la",
            "sec_idx": 0,
            "line_idx": 0,
            "word_idx_in_line": 0,
            "section_name": "Verse",
            "prefill_bars": 0,
            "syll_idx_in_line": 0,
            "line_syll_count": 1,
            "stress": 0.6,
        }]
    total = len(words)

    # ── Load pitch sources (priority order) ────────────────────────────
    # 1. melody_composer (best dynamic phrase leader)
    # 2. MIDI melody (MT3 or external transcription)
    # 3. basic_pitch from isolated vocals
    # 4. Chord tones (harmonic fallback)
    # 5. Random walk (last resort)

    composed_melody = []
    if chords:
        try:
            from melody_composer import compose_melody
            composed_melody = compose_melody(
                chords=chords,
                bpm=float(bpm),
                num_words=total,
                joy=joy, sadness=sadness,
                tension=tension, energy=energy,
            )
            if composed_melody:
                composed_melody = _harmonic_lock_notes(
                    composed_melody,
                    chords=chords,
                    scale_notes=scale_notes or [],
                    phrase_size=8,
                    max_leap=5,
                )
            print(f"🎼 Pitch: melody_composer ({len(composed_melody)} notes)")
        except Exception as e:
            print(f"⚠️  melody_composer failed: {e}")

    midi_melody = _load_midi_melody(melody_midi_path) if melody_midi_path else []

    # Keep one pitch leader to avoid contradictory note sources.
    if composed_melody:
        if melody_midi_path:
            print("🎯 Pitch source locked: melody_composer (MIDI bypassed)")
        elif vocals_path:
            print("🎯 Pitch source locked: melody_composer (basic_pitch bypassed)")
    if midi_melody and not composed_melody and vocals_path:
        print("🎯 Pitch source locked: MIDI melody (basic_pitch bypassed)")
    melody = _load_melody(vocals_path) if (vocals_path and not composed_melody and not midi_melody) else []
    has_composed = bool(composed_melody)
    has_midi     = bool(midi_melody)
    has_m        = bool(melody)
    has_c        = bool(chords)

    if not has_composed and not has_midi and not has_m:
        if has_c: print(f"🎸 Pitch: chord tones ({len(chords)} chords)")
        else:     print(f"🎲 Pitch: random walk")

    walk = _walk(total, base_tone, scale_notes or [], joy, sadness, tension)

    groove     = _load_groove(groove_template)
    notes_yaml = []
    part_dur   = 0
    used       = set()
    events     = []
    phrase_size = 8

    def pick(i, t, prev, section_name, line_end=False, section_end=False):
        # Priority 1: melody_composer (Melody RNN or rule engine)
        if has_composed and i < len(composed_melody):
            tone = _clamp(composed_melody[i]["tone"])
        # Priority 2: MIDI melody (e.g., MT3 transcription)
        elif has_midi:
            tone = _melody_at(midi_melody, t, prev)
        # Priority 3: basic_pitch from reference vocals
        elif has_m:
            tone = _melody_at(melody, t, prev)
        # Priority 4: chord tones
        elif has_c:
            ch  = _chord_at(chords, t)
            end = (i == total - 1)
            strong = (i % 2 == 0)
            tone = _chord_tone(ch["chord_tones"], prev, joy, sadness, end, ch["bass_note"], strong_beat=strong)
        # Priority 4: random walk
        else:
            tone = walk[i]

        lo, hi = _section_range(section_name, base_tone)
        tone = max(lo, min(hi, tone))

        # Strong cadence at line/section ends.
        if has_c and (line_end or section_end):
            ch = _chord_at(chords, t)
            pool = sorted(set(_to_sweet(x) for x in (ch.get("chord_tones") or [])))
            if pool:
                tone = min(pool, key=lambda x: abs(x - tone))
        return _clamp(tone)

    # ── PATH A: groove timing ────────────────────────────────────────────
    if groove and (groove.get("word_slots") or groove.get("syllable_hits")):
        hits    = groove.get("word_slots") or groove.get("syllable_hits")
        breaths = groove.get("breaths", [])
        bpm     = int(groove.get("tempo", bpm) or bpm)
        brange  = [(b["start"], b["end"]) for b in breaths]

        def _hit_time(hit):
            if isinstance(hit, dict):
                # Support both {"time": ...} and {"start": ...} groove shapes.
                t = hit.get("time", hit.get("start", 0.0))
                return float(t or 0.0)
            return float(hit)

        def in_b(t):  return any(s <= t <= e for s, e in brange)
        def pre_b(t): return any(0 < t - e < 1.5 for _, e in brange)

        prev = base_tone
        prev_phrase = -1
        last_end_tp = _ticks((silent_shift_bars * 4.0 * 60.0) / max(bpm, 1), bpm)
        line_break_ticks = 140
        section_break_ticks = 260

        for i, itm in enumerate(words):
            if i >= len(hits):
                break
            h     = hits[i]
            st    = _hit_time(h)
            clean = _clean(itm["word"])
            next_same_line = (i + 1 < len(words) and
                              words[i + 1]["sec_idx"] == itm["sec_idx"] and
                              words[i + 1]["line_idx"] == itm["line_idx"])
            next_same_sec = (i + 1 < len(words) and words[i + 1]["sec_idx"] == itm["sec_idx"])
            line_end = not next_same_line
            sec_end = not next_same_sec
            tone  = pick(i, st, prev, itm["section_name"], line_end=line_end, section_end=sec_end)
            interval = tone - prev
            prev  = tone

            lead_ticks = itm["prefill_bars"] * 1920
            tp = _ticks(st, bpm) + lead_ticks
            # Microtiming push/pull by stress and section role.
            stress = float(itm.get("stress", 0.5))
            swing = int((stress - 0.5) * 20)
            if itm["section_name"] == "Chorus":
                swing += 6
            elif itm["section_name"] == "Verse":
                swing -= 2
            tp += swing
            while tp in used: tp += 5
            min_gap_ticks = 30
            tp = max(tp, last_end_tp + min_gap_ticks)
            used.add(tp)

            if i + 1 < len(hits):
                nt = _hit_time(hits[i + 1])
                raw_sec = max(0.1, nt - st - 0.1) if in_b(nt) else max(0.1, nt - st)
                # Anti-swallow timing: syllable-stress-weighted minimum duration.
                min_sec = min(0.58, max(0.12, 0.10 + 0.015 * len(clean) + 0.06 * stress))
                sec_scale = 1.0
                if itm["section_name"] == "Chorus":
                    sec_scale = 0.95  # slightly tighter for punch
                elif itm["section_name"] == "Bridge":
                    sec_scale = 1.05
                td = _ticks(max(min_sec, raw_sec * sec_scale), bpm)
            else:
                td = _ticks(0.4, bpm)
            td = max(120, td)
            if line_end:
                td += 50
            # Strong syllables get a little more hold.
            td = int(td * (1.0 + 0.12 * max(0.0, stress - 0.5)))

            # Interval-based pitch gesture for natural transitions.
            in_y = 0
            out_y = 0
            if abs(interval) >= 3:
                out_y = 18 if interval > 0 else -18
            elif stress > 0.68:
                in_y = -10
                out_y = 8

            ph = i // phrase_size
            if ph != prev_phrase and prev_phrase != -1:
                ap = max(0, tp - 120)
                while ap in used: ap += 5
                if ap > 0:
                    used.add(ap)
                    events.append({
                        "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                        "pos": ap,
                        "dur": 100,
                        "tone": tone,
                        "lyric": "AP",
                        "breath": True,
                        "pitch_in_y": 0,
                        "pitch_out_y": 0,
                    })
            prev_phrase = ph

            if pre_b(st):
                br = max(0, tp - 150)
                while br in used: br += 5
                if br > 0:
                    used.add(br)
                    events.append({
                        "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                        "pos": br,
                        "dur": 120,
                        "tone": tone,
                        "lyric": "br",
                        "breath": True,
                        "pitch_in_y": 0,
                        "pitch_out_y": 0,
                    })

            events.append({
                "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                "pos": tp,
                "dur": td,
                "tone": tone,
                "lyric": clean,
                "breath": False,
                "pitch_in_y": in_y,
                "pitch_out_y": out_y,
            })
            if line_end:
                events.append({
                    "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                    "pos": tp + td,
                    "dur": line_break_ticks,
                    "tone": tone,
                    "lyric": "AP",
                    "breath": True,
                    "pitch_in_y": 0,
                    "pitch_out_y": 0,
                })
            if sec_end:
                events.append({
                    "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                    "pos": tp + td + line_break_ticks,
                    "dur": section_break_ticks,
                    "tone": tone,
                    "lyric": "AP",
                    "breath": True,
                    "pitch_in_y": 0,
                    "pitch_out_y": 0,
                })
            last_end_tp = max(last_end_tp, tp + td)
            part_dur = max(part_dur, tp + td)

    # ── PATH B: even spacing ─────────────────────────────────────────────
    else:
        print("⚠️  No groove — even spacing")
        nd   = max(180, min(960, int(480 * (1.0 + sadness*0.8 - energy*0.4))))
        gap  = max(60, int(nd * (0.15 + sadness*0.1)))
        pos  = 0
        prev = base_tone

        for i, itm in enumerate(words):
            clean = _clean(itm["word"])
            st    = (pos / 480.0) * (60.0 / max(bpm, 1))
            next_same_line = (i + 1 < len(words) and
                              words[i + 1]["sec_idx"] == itm["sec_idx"] and
                              words[i + 1]["line_idx"] == itm["line_idx"])
            next_same_sec = (i + 1 < len(words) and words[i + 1]["sec_idx"] == itm["sec_idx"])
            line_end = not next_same_line
            sec_end = not next_same_sec
            tone  = pick(i, st, prev, itm["section_name"], line_end=line_end, section_end=sec_end)
            interval = tone - prev
            prev  = tone

            stress = float(itm.get("stress", 0.5))
            dur = nd + (60 if i % 4 == 0 else 0)
            dur = int(dur * (1.0 + 0.14 * max(0.0, stress - 0.5)))
            p   = max(0, pos + (-15 if i%3==1 else (10 if i%3==2 else 0)))
            p  += int((stress - 0.5) * 16)
            p  += itm["prefill_bars"] * 1920
            in_y = 0
            out_y = 0
            if abs(interval) >= 3:
                out_y = 18 if interval > 0 else -18
            elif stress > 0.68:
                in_y = -10
                out_y = 8

            if i % 8 == 7 and i > 0:
                events.append({
                    "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                    "pos": p + dur,
                    "dur": 80,
                    "tone": tone,
                    "lyric": "AP",
                    "breath": True,
                    "pitch_in_y": 0,
                    "pitch_out_y": 0,
                })

            events.append({
                "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                "pos": p,
                "dur": dur,
                "tone": tone,
                "lyric": clean,
                "breath": False,
                "pitch_in_y": in_y,
                "pitch_out_y": out_y,
            })
            if line_end:
                events.append({
                    "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                    "pos": p + dur,
                    "dur": 140,
                    "tone": tone,
                    "lyric": "AP",
                    "breath": True,
                    "pitch_in_y": 0,
                    "pitch_out_y": 0,
                })
            if sec_end:
                events.append({
                    "part_key": (itm["sec_idx"], itm["line_idx"], itm["section_name"]),
                    "pos": p + dur + 140,
                    "dur": 260,
                    "tone": tone,
                    "lyric": "AP",
                    "breath": True,
                    "pitch_in_y": 0,
                    "pitch_out_y": 0,
                })
            pos     += dur + gap
            part_dur = max(pos, 480)

    # Build a single voice part for the whole song.
    events = sorted(events, key=lambda e: e["pos"])
    if not events:
        events = [{
            "pos": 0,
            "dur": 480,
            "tone": _clamp(base_tone),
            "lyric": "la",
            "breath": False,
            "pitch_in_y": 0,
            "pitch_out_y": 0,
        }]

    part_pos = min(e["pos"] for e in events)
    rel_notes = []
    end_pos = 0
    for e in events:
        rel_pos = max(0, e["pos"] - part_pos)
        end_pos = max(end_pos, rel_pos + e["dur"])
        rel_notes.append(
            _note(
                rel_pos,
                e["dur"],
                e["tone"],
                e["lyric"],
                vib_p,
                vib_d,
                e["breath"],
                pitch_in_y=e.get("pitch_in_y", 0),
                pitch_out_y=e.get("pitch_out_y", 0),
            )
        )
    parts_yaml = [(
        f"- duration: {end_pos + 480}\n"
        f"  name: Main\n"
        f"  comment: \"\"\n"
        f"  track_no: 0\n"
        f"  position: {part_pos}\n"
        f"  notes:\n{chr(10).join(rel_notes)}\n"
        f"  curves: []"
    )]

    return f"""name: Vocalis-X Project
comment: ""
output_dir: Vocal
cache_dir: UCache
ustx_version: "0.9"
resolution: 480
bpm: {bpm}
beat_per_bar: 4
beat_unit: 4
{EXPRESSIONS_BLOCK}key: 0
time_signatures:
- bar_position: 0
  beat_per_bar: 4
  beat_unit: 4
tempos:
- position: 0
  bpm: {bpm}
tracks:
- singer: "{SINGER_NAME}"
  phonemizer: "{PHONEMIZER}"
  renderer_settings:
    renderer: DIFFSINGER
  track_name: Track1
  track_color: Blue
  mute: false
  solo: false
  volume: 0
  pan: 0
  track_expressions: []
  voice_color_names:
  - '01: normal'
  - '02: soft'
  - '03: strong'
voice_parts:
{chr(10).join(parts_yaml)}
wave_parts: []
"""


def write_ustx(
    lyrics: str,
    bpm: int = 120,
    base_tone: int = RENA_MID,
    emotion: dict = None,
    darkness: float = 0.2,
    energy: float = 0.5,
    scale_notes: list = None,
    is_minor: bool = False,
    groove_template: str = None,
    chords: list = None,
    vocals_path: str = None,
    melody_midi_path: str = None,
) -> Path:
    text = build_ustx(
        lyrics, bpm, base_tone, emotion, darkness, energy,
        scale_notes, is_minor, groove_template, chords, vocals_path, melody_midi_path
    )
    name = f"vocalisx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.ustx"
    out  = OUTPUT_DIR / name
    out.write_text(text, encoding="utf-8")
    print(f"📝 USTX: {out}")
    return out

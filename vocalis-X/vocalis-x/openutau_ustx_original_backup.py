"""
openutau_ustx.py — Vocalis-X
Generates OpenUTAU .ustx for Raine Rena DiffSinger 2.01.

Pitch design (fixed):
  - All notes locked to ONE octave (D4-D5 sweet zone)
  - On phrase start: sing root of chord
  - Within phrase: step through chord tones (root→3rd→5th→3rd→root)
  - On phrase end: return to root
  - No octave jumps, no random walks across multiple octaves
  - Voice leading: max 7 semitones between consecutive notes
"""

import uuid, re, json, random
from pathlib import Path
from datetime import datetime
from basic_pitch_melody import extract_melody_notes, melody_to_tone_sequence

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SINGER_NAME   = "雷音レナ・Raine Rena 2.01"
PHONEMIZER    = "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer"
RENA_MIN      = 55
RENA_MAX      = 81
RENA_MID      = 68
RENA_MID_TONE = RENA_MID
SWEET_MIN     = 62   # D4 — comfortable floor
SWEET_MAX     = 74   # D5 — comfortable ceiling

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
  mod+:
    name: modulation plus
    abbr: mod+
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
  shfc:
    name: tone shift (curve)
    abbr: shfc
    type: Curve
    min: -1200
    max: 1200
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


def _clean(w):
    return re.sub(r"[^A-Za-z']+", "", w) or "la"

def _clamp(t):
    return max(RENA_MIN, min(RENA_MAX, int(t)))

def _ticks(sec, bpm):
    return max(1, int((sec / 60.0) * bpm * 480))

def _load_groove(name=None):
    d = Path("swagger_templates")
    if not d.exists(): return None
    if name:
        t = d / name
        if t.exists():
            print(f"🧬 DNA: {t.name}")
            return json.load(open(t))
    files = list(d.glob("*.json"))
    if not files: return None
    c = random.choice(files)
    print(f"🎲 Random DNA: {c.name}")
    return json.load(open(c))

def _chord_at(chords, t):
    if not chords:
        return {"tones": [RENA_MID], "root": RENA_MID, "bass_note": RENA_MID, "chord_name": "?"}
    best = chords[0]
    for c in chords:
        if c["time"] <= t: best = c
        else: break
    return best

def _clamp_to_sweet(tone):
    """Keep tone within comfortable singing zone."""
    while tone < SWEET_MIN: tone += 12
    while tone > SWEET_MAX: tone -= 12
    return _clamp(tone)


def _pick_tone(tones, root, prev_tone, joy, sadness, is_phrase_start, is_phrase_end, word_pos_in_phrase, phrase_len):
    """
    Pick one MIDI note. Core rules:
    1. Phrase start → root note of chord
    2. Phrase end → root note of chord
    3. Within phrase → step through chord tones with voice leading
    4. Maximum jump = 5 semitones (no octave leaps)
    5. All tones clamped to sweet zone (D4-D5)
    """
    root_sweet = _clamp_to_sweet(root)

    if is_phrase_start or is_phrase_end:
        return root_sweet

    # Sort tones within sweet zone
    sweet_tones = sorted(set(_clamp_to_sweet(t) for t in tones))
    if not sweet_tones:
        sweet_tones = [root_sweet]

    # Remove duplicates that map to same value
    sweet_tones = sorted(set(sweet_tones))

    # Voice leading: find tone closest to prev_tone, max 5 semitones away
    prev_sweet = _clamp_to_sweet(prev_tone)
    candidates = [t for t in sweet_tones if abs(t - prev_sweet) <= 5]
    if not candidates:
        # All too far — just pick closest
        candidates = [min(sweet_tones, key=lambda t: abs(t - prev_sweet))]

    # Emotion: joy leans up, sadness leans down
    if joy > 0.5 and len(candidates) > 1:
        candidates = candidates[-2:]   # upper options
    elif sadness > 0.4 and len(candidates) > 1:
        candidates = candidates[:2]    # lower options

    # Avoid repeating same note more than twice in a row
    non_repeat = [t for t in candidates if t != prev_sweet]
    if non_repeat and random.random() < 0.6:
        return random.choice(non_repeat)

    return random.choice(candidates)


def _note_yaml(pos, dur, tone, lyric, vp, vd, silent=False):
    vib = (f"{{length: 0, period: 0, depth: 0, in: 0, out: 0, shift: 0, drift: 0, vol_link: 0}}"
           if silent else
           f"{{length: 60, period: {vp}, depth: {vd}, in: 10, out: 10, shift: 0, drift: 0, vol_link: 0}}")
    return (
        f"  - position: {pos}\n    duration: {dur}\n"
        f"    tone: {tone}\n    lyric: {lyric}\n"
        f"    pitch:\n      data:\n"
        f"      - {{x: -25, y: 0, shape: io}}\n"
        f"      - {{x: 25, y: 0, shape: io}}\n"
        f"      snap_first: true\n"
        f"    vibrato: {vib}\n"
        f"    tuning: 0\n    phoneme_expressions: []\n"
        f"    phoneme_overrides: []"
    )


def build_ustx(
    lyrics, bpm=120, base_tone=RENA_MID, emotion=None,
    darkness=0.2, energy=0.5, scale_notes=None, is_minor=False,
    groove_template=None, chords=None,instrumental_path=None,   
):
    emotion  = emotion or {}
    joy      = float(emotion.get("joy",     0.3) or 0.3)
    sadness  = float(emotion.get("sadness", 0.2) or 0.2)
    tension  = float(emotion.get("tension", 0.1) or 0.1)
    darkness = float(darkness or 0.2)
    energy   = float(energy   or 0.5)

    vib_depth  = max(6,  min(40,  int(15 + sadness*18 - joy*7)))
    vib_period = max(90, min(260, int(175 + sadness*45 - tension*25)))

    raw_words   = [w for line in lyrics.strip().splitlines() for w in line.strip().split()]
    raw_words   = [w for line in lyrics.strip().splitlines() for w in line.strip().split()]

    # Extract melody from instrumental if available
    melody_notes = []
    if instrumental_path and Path(instrumental_path).exists():

     print(f"🎼 Extracting melody from: {instrumental_path}")

    extracted = extract_melody_notes(instrumental_path)

    melody_notes = melody_to_tone_sequence(
        extracted,
        len(raw_words)
    )

    if groove_template and isinstance(groove_template, (str, Path)):
        instrumental_path = Path(groove_template)

        if instrumental_path.exists():
            try:
                extracted = extract_melody_notes(str(instrumental_path))
                melody_notes = melody_to_tone_sequence(extracted, len(raw_words))
                print(f"🎤 Melody extracted: {len(melody_notes)} notes")
            except Exception as e:
                print(f"⚠️ Melody extraction failed: {e}")

    raw_words   = raw_words or ["la"]
    total_words = len(raw_words)
    raw_words   = raw_words or ["la"]
    total_words = len(raw_words)

    groove     = _load_groove(groove_template)
    notes_yaml = []
    part_dur   = 0
    has_chords = bool(chords)

    print(f"🎸 {'Chord-aware' if has_chords else 'Fallback'} | {total_words} words")

    # ── PATH A: Beat-grid groove ──────────────────────────────────────────────
    if groove and groove.get("word_slots"):
        slots   = groove["word_slots"]
        breaths = groove.get("breaths", [])
        bpm     = int(groove.get("tempo", bpm))
        breath_ranges = [(b["start"], b["end"]) for b in breaths]

        def in_breath(t):
            return any(s <= t <= e for s, e in breath_ranges)
        def breath_just_ended(t, w=1.5):
            return any(0 < t - e < w for s, e in breath_ranges)

        used    = set()
        prev_t  = _clamp_to_sweet(base_tone)
        prev_ph = -1

        # Pre-compute phrase sizes for position tracking
        phrase_sizes = {}
        for slot in slots:
            ph = slot["phrase_idx"]
            phrase_sizes[ph] = phrase_sizes.get(ph, 0) + 1

        phrase_word_pos = {}  # track position within current phrase

        for i, raw in enumerate(raw_words):
            if i >= len(slots): break
            slot = slots[i]
            t    = slot["time"]
            ph   = slot["phrase_idx"]

            # Track word position within phrase
            if ph not in phrase_word_pos:
                phrase_word_pos[ph] = 0
            word_pos = phrase_word_pos[ph]
            phrase_word_pos[ph] += 1
            phrase_len = phrase_sizes.get(ph, 8)

            is_start = (word_pos == 0)
            is_end   = (word_pos == phrase_len - 1 or i == total_words - 1)

            # Get chord
            if has_chords:
                chord = _chord_at(chords, t)
                tones = chord.get("tones", chord.get("chord_tones", [RENA_MID]))
                root  = chord.get("root", chord.get("bass_note", RENA_MID))
            else:
                tones = scale_notes or [RENA_MID]
                root  = tones[0]

            tone   = _pick_tone(tones, root, prev_t, joy, sadness, is_start, is_end, word_pos, phrase_len)
            prev_t = tone

            tick = _ticks(t, bpm)
            while tick in used: tick += 5
            used.add(tick)

            if i+1 < len(slots):
                nt = slots[i+1]["time"]
                raw_dur = nt - t
                if in_breath(nt): raw_dur = max(0.1, raw_dur - 0.15)
                tick_dur = _ticks(raw_dur, bpm)
            else:
                tick_dur = _ticks(0.4, bpm)
            tick_dur = max(120, tick_dur)

            # AP at phrase boundary
            if ph != prev_ph and prev_ph != -1:
                ap = max(0, tick - 120)
                while ap in used: ap += 5
                if ap > 0:
                    used.add(ap)
                    notes_yaml.append(_note_yaml(ap, 100, tone, "AP", vib_period, vib_depth, silent=True))

            prev_ph = ph

            # br after breath gap
            if breath_just_ended(t):
                br = max(0, tick - 150)
                while br in used: br += 5
                if br > 0:
                    used.add(br)
                    notes_yaml.append(_note_yaml(br, 120, tone, "br", vib_period, vib_depth, silent=True))

            notes_yaml.append(_note_yaml(tick, tick_dur, tone, _clean(raw), vib_period, vib_depth))
            part_dur = max(part_dur, tick + tick_dur)

    # ── PATH B: No groove ────────────────────────────────────────────────────
    else:
        print("⚠️  No groove — even spacing")
        note_dur = max(180, min(960, int(480 * (1.0 + sadness*0.8 - energy*0.4))))
        rest_gap = max(60, int(note_dur * 0.15))
        pos      = 0
        prev_t   = _clamp_to_sweet(base_tone)

        for i, raw in enumerate(raw_words):
            slot_t   = (pos / 480.0) * (60.0 / max(bpm, 1))
            is_start = (i % 8 == 0)
            is_end   = (i % 8 == 7 or i == total_words - 1)
            if has_chords:
                chord = _chord_at(chords, slot_t)
                tones = chord.get("tones", [RENA_MID])
                root  = chord.get("root", RENA_MID)
            else:
                tones = scale_notes or [RENA_MID]
                root  = tones[0]
            if melody_notes and i < len(melody_notes):
             tone = _clamp_to_sweet(melody_notes[i])
        else:
         tone = _pick_tone(
        tones,
        root,
        prev_t,
        joy,
        sadness,
        is_start,
        is_end,
        word_pos,
        phrase_len
 )
        prev_t = tone
        dur = note_dur + (60 if i % 4 == 0 else 0)
        if is_end:
            notes_yaml.append(_note_yaml(pos+dur, 80, tone, "AP", vib_period, vib_depth, silent=True))
            notes_yaml.append(_note_yaml(pos, dur, tone, _clean(raw), vib_period, vib_depth))
            pos += dur + rest_gap
            part_dur = max(pos, 480)

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
- duration: {part_dur + 960}
  name: Vocalis-X Part
  comment: ""
  track_no: 0
  position: 0
  notes:
{chr(10).join(notes_yaml)}
  curves: []
wave_parts: []
"""


def write_ustx(
    lyrics, bpm=120, base_tone=RENA_MID, emotion=None,
    darkness=0.2, energy=0.5, scale_notes=None, is_minor=False,
    groove_template=None, chords=None,instrumental_path=None, 
) -> Path:
    text = build_ustx(lyrics, bpm, base_tone, emotion, darkness, energy,
                      scale_notes, is_minor, groove_template, chords,instrumental_path=instrumental_path,   )
    name = f"vocalisx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.ustx"
    out  = OUTPUT_DIR / name
    out.write_text(text, encoding="utf-8")
    return out
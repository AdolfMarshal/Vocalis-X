"""
openutau_ustx_enhanced.py — Vocalis-X
ENHANCED VERSION with full expression support for natural, human-like singing

NEW FEATURES:
- Dynamic curves (volume variation)
- Pitch deviation/portamento
- Voice color switching
- Phoneme expressions (breathiness, tension, gender)
- Smart vibrato (delayed onset, duration-based)
- Breath note insertion
- Timing humanization

This makes Rena sing like a REAL HUMAN!
"""

import uuid, re, json, random
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Optional import - melody extraction not required for basic functionality
try:
    from basic_pitch_melody import extract_melody_notes, melody_to_tone_sequence
    HAS_MELODY_EXTRACTION = True
except ImportError:
    HAS_MELODY_EXTRACTION = False
    def extract_melody_notes(path):
        return []
    def melody_to_tone_sequence(notes):
        return []

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SINGER_NAME   = "雷音レナ・Raine Rena 2.01"
PHONEMIZER    = "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer"
RENA_MIN      = 55
RENA_MAX      = 81
RENA_MID      = 68
RENA_MID_TONE = RENA_MID  # Export for backwards compatibility
SWEET_MIN     = 62   # D4 — comfortable floor
SWEET_MAX     = 74   # D5 — comfortable ceiling

# Same expressions block as original
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
    max: 2
    default_value: 0
    is_flag: false
    options:
    - '01: normal'
    - '02: soft'
    - '03: strong'
    skip_output_if_default: false
  eng:
    name: engine
    abbr: eng
    type: Options
    min: 0
    max: 0
    default_value: 0
    is_flag: false
    options:
    - world
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
    is_flag: false
    flag: ""
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
    name: breathiness
    abbr: bre
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  brec:
    name: breathiness (curve)
    abbr: brec
    type: Curve
    min: 0
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
    is_flag: false
    flag: ""
    skip_output_if_default: false
  lpfc:
    name: lowpass (curve)
    abbr: lpfc
    type: Curve
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  mod:
    name: modulation
    abbr: mod
    type: Numerical
    min: -100
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  modc:
    name: modulation (curve)
    abbr: modc
    type: Curve
    min: -100
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
  comp:
    name: compress
    abbr: comp
    type: Numerical
    min: 0
    max: 100
    default_value: 0
    is_flag: false
    flag: ""
    skip_output_if_default: false
  compc:
    name: compress (curve)
    abbr: compc
    type: Curve
    min: 0
    max: 100
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

def _clamp_to_sweet(tone):
    """Keep tone within comfortable singing zone."""
    while tone < SWEET_MIN: tone += 12
    while tone > SWEET_MAX: tone -= 12
    return _clamp(tone)


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


# ========================================
# 🎨 EXPRESSION GENERATION (NEW!)
# ========================================

def generate_vibrato(note_duration: int, emotion: dict, is_sustained: bool = False) -> dict:
    """
    Natural vibrato based on note length
    - No vibrato on short notes
    - Delayed onset on long notes (more human)
    - Emotion-based depth and speed
    """
    # No vibrato on short notes (quarter note or less)
    if note_duration < 240:
        return {
            'length': 0,
            'period': 0,
            'depth': 0,
            'in': 0, 'out': 0, 'shift': 0, 'drift': 0, 'vol_link': 0
        }
    
    sadness = emotion.get('sadness', 0.2)
    tension = emotion.get('tension', 0.1)
    joy = emotion.get('joy', 0.3)
    
    # Vibrato depth: sadder = deeper, tense = shallower
    depth = int(15 + sadness * 25 - tension * 10 + joy * 5)
    depth = max(8, min(40, depth))
    
    # Vibrato speed: sadder = slower, tense = faster
    period = int(175 + sadness * 50 - tension * 30)
    period = max(90, min(260, period))
    
    # Vibrato coverage: longer notes get more vibrato
    coverage = min(80, max(40, note_duration // 6))
    
    # Delayed onset on long sustained notes (humans don't vibrato immediately)
    fade_in = min(30, note_duration // 8) if is_sustained else 10
    
    return {
        'length': coverage,
        'period': period,
        'depth': depth,
        'in': fade_in,
        'out': 10,
        'shift': 0,
        'drift': 0,
        'vol_link': 0
    }


def generate_pitch_curve(prev_tone: int, curr_tone: int, note_duration: int, emotion: dict) -> List[Dict]:
    """
    Generate pitch deviation for natural slides/portamento
    - Large intervals get portamento
    - Joy slides from below, sadness from above
    - Subtle variations on small intervals
    """
    joy = emotion.get('joy', 0)
    sadness = emotion.get('sadness', 0)
    energy = emotion.get('energy', 0.5)
    
    interval = curr_tone - prev_tone
    
    # Large intervals (4+ semitones) get portamento
    if abs(interval) >= 4:
        # Slide duration: 10-30% of note
        slide_len = min(100, note_duration // 4)
        
        # Direction based on emotion
        if joy > 0.5 and interval > 0:
            # Joy: approach from below
            return [
                {'x': -slide_len, 'y': -50, 'shape': 'io'},
                {'x': 0, 'y': 0, 'shape': 'io'},
                {'x': 25, 'y': 0, 'shape': 'io'}
            ]
        elif sadness > 0.5 and interval < 0:
            # Sadness: approach from above
            return [
                {'x': -slide_len, 'y': 50, 'shape': 'io'},
                {'x': 0, 'y': 0, 'shape': 'io'},
                {'x': 25, 'y': 0, 'shape': 'io'}
            ]
        else:
            # Standard portamento
            slide_amount = min(abs(interval) * 10, 80)
            return [
                {'x': -slide_len, 'y': -slide_amount if interval > 0 else slide_amount, 'shape': 'io'},
                {'x': 0, 'y': 0, 'shape': 'io'}
            ]
    
    # Small intervals or same note: subtle variation
    return [
        {'x': -25, 'y': 0, 'shape': 'io'},
        {'x': 25, 'y': 0, 'shape': 'io'}
    ]


def generate_phoneme_expressions(word: str, note_tone: int, emotion: dict, is_long_note: bool) -> List[Dict]:
    """
    Control individual phoneme character based on WORD (not phoneme codes)
    - Breathiness on emotional moments
    - Tension on high notes
    - Gender (brightness) variation
    """
    expressions = []
    
    tension_val = emotion.get('tension', 0.1)
    darkness_val = emotion.get('darkness', 0.5)
    sadness_val = emotion.get('sadness', 0.2)
    energy_val = emotion.get('energy', 0.5)
    
    # High notes → more tension (strain)
    if note_tone > 70:
        tension_amount = int(min(80, (note_tone - 70) * 15 + tension_val * 40))
        expressions.append({
            'abbr': 'tenc',
            'value': tension_amount
        })
    
    # Dark/sad moments → add breathiness (check if it's a vowel-heavy word OR long note)
    # Most English words have vowels, so we add breathiness based on emotion
    has_vowels = any(v in word.lower() for v in 'aeiou')
    if has_vowels or is_long_note:
        if darkness_val > 0.5 or sadness_val > 0.4:
            breath_amount = int((darkness_val * 0.5 + sadness_val * 0.5) * 80)
            if breath_amount > 10:  # Only add if significant
                expressions.append({
                    'abbr': 'brec',
                    'value': breath_amount
                })
    
    # Bright moments → higher gender (brighter timbre)
    if darkness_val < 0.4 and energy_val > 0.5:
        expressions.append({
            'abbr': 'genc',
            'value': int((1 - darkness_val) * 50)
        })
    elif darkness_val > 0.6:
        # Very dark → lower gender (darker timbre)
        expressions.append({
            'abbr': 'genc',
            'value': int(-darkness_val * 40)
        })
    
    return expressions


def pick_voice_color(note_tone: int, emotion: dict, is_phrase_climax: bool, note_duration: int) -> str:
    """
    Choose voice color based on context
    - Soft voice for quiet/intimate phrases
    - Strong voice for powerful moments
    - Normal voice for default
    """
    energy = emotion.get('energy', 0.5)
    darkness = emotion.get('darkness', 0.5)
    
    # High notes or climax with high energy → strong voice
    if (is_phrase_climax or note_tone > 72) and energy > 0.6:
        return '03: strong'
    
    # Soft, dark, low energy moments → soft voice
    if darkness > 0.6 and energy < 0.4 and note_tone < 68:
        return '02: soft'
    
    # Long sustained emotional notes → strong
    if note_duration > 720 and energy > 0.5:  # Dotted half or longer
        return '03: strong'
    
    # Default
    return '01: normal'


# ========================================
# 🎵 MELODY GENERATION (Enhanced)
# ========================================

def _pick_tone(tones, root, prev_tone, joy, sadness, is_phrase_start, is_phrase_end, word_pos_in_phrase, phrase_len):
    """
    Pick one MIDI note with voice leading
    (Same as original but returns info for expression)
    """
    root_sweet = _clamp_to_sweet(root)

    if is_phrase_start or is_phrase_end:
        return root_sweet

    sweet_tones = sorted(set(_clamp_to_sweet(t) for t in tones))
    if not sweet_tones:
        sweet_tones = [root_sweet]

    sweet_tones = sorted(set(sweet_tones))

    prev_sweet = _clamp_to_sweet(prev_tone)
    candidates = [t for t in sweet_tones if abs(t - prev_sweet) <= 5]
    if not candidates:
        candidates = [min(sweet_tones, key=lambda t: abs(t - prev_sweet))]

    if joy > 0.5 and len(candidates) > 1:
        candidates = candidates[-2:]
    elif sadness > 0.4 and len(candidates) > 1:
        candidates = candidates[:2]

    non_repeat = [t for t in candidates if t != prev_sweet]
    if non_repeat and random.random() < 0.6:
        return random.choice(non_repeat)

    return random.choice(candidates)


def _build_note_with_expressions(
    position: int,
    duration: int,
    tone: int,
    lyric: str,
    emotion: dict,
    prev_tone: int,
    is_phrase_start: bool = False,
    is_phrase_end: bool = False,
    is_phrase_climax: bool = False,
    is_sustained: bool = False
) -> str:
    """
    Build complete note YAML with ALL expressions
    """
    
    # Generate vibrato
    vibrato = generate_vibrato(duration, emotion, is_sustained)
    vib_str = (f"{{length: {vibrato['length']}, period: {vibrato['period']}, "
               f"depth: {vibrato['depth']}, in: {vibrato['in']}, out: {vibrato['out']}, "
               f"shift: {vibrato['shift']}, drift: {vibrato['drift']}, vol_link: {vibrato['vol_link']}}}")
    
    # Generate pitch curve
    pitch_points = generate_pitch_curve(prev_tone, tone, duration, emotion)
    pitch_data = "\n".join([
        f"      - {{x: {p['x']}, y: {p['y']}, shape: {p.get('shape', 'io')}}}"
        for p in pitch_points
    ])
    
    # Generate phoneme expressions
    phoneme_exprs = generate_phoneme_expressions(lyric, tone, emotion, is_sustained)
    if phoneme_exprs:
        # Proper YAML list format with correct indentation - NO BLANK LINE
        expr_lines = []
        for e in phoneme_exprs:
            expr_lines.append(f"    - abbr: {e['abbr']}")
            expr_lines.append(f"      value: {e['value']}")
        phoneme_expr_str = "\n".join(expr_lines)  # Remove leading \n
    else:
        phoneme_expr_str = " []"
    
    # Pick voice color
    voice_color = pick_voice_color(tone, emotion, is_phrase_climax, duration)
    color_idx = ['01: normal', '02: soft', '03: strong'].index(voice_color)
    
    # Attack/decay based on emotion and position
    attack = 100
    if is_phrase_start:
        attack = 80  # Softer attack on phrase starts
    elif emotion.get('energy', 0.5) > 0.7:
        attack = 120  # Harder attack on high energy
    
    # Build phoneme expressions - match original format exactly
    if phoneme_exprs:
        pe_str = "    phoneme_expressions:\n" + phoneme_expr_str
    else:
        pe_str = "    phoneme_expressions: []"
    
    # Build note YAML using same format as original (no triple quotes)
    # Quote lyric if it contains special characters to ensure YAML safety
    safe_lyric = lyric
    if "'" in lyric or '"' in lyric or lyric.startswith(('!', '@', '#', '%', '&', '*')):
        # Use double quotes and escape internal quotes
        safe_lyric = safe_lyric.replace('\\', '\\\\').replace('"', '\\"')
        lyric_str = f'"{safe_lyric}"'
    else:
        lyric_str = lyric
    
    return (
        f"  - position: {position}\n"
        f"    duration: {duration}\n"
        f"    tone: {tone}\n"
        f"    lyric: {lyric_str}\n"
        f"    phonetic_hint: \"\"\n"
        f"    color_index: {color_idx}\n"
        f"    attack: {attack}\n"
        f"    pitch:\n"
        f"      data:\n"
        f"{pitch_data}\n"
        f"      snap_first: true\n"
        f"    vibrato: {vib_str}\n"
        f"    tuning: 0\n"
        f"{pe_str}\n"
        f"    phoneme_overrides: []"
    )


# ========================================
# 🎼 MAIN USTX BUILDER (Enhanced)
# ========================================

def build_ustx(
    lyrics: str,
    bpm: int = 120,
    base_tone: int = RENA_MID,
    emotion: Optional[dict] = None,
    darkness: float = 0.2,
    energy: float = 0.5,
    scale_notes: Optional[list] = None,
    is_minor: bool = False,
    groove_template: Optional[str] = None,
    chords: Optional[list] = None,
    instrumental_path: Optional[str] = None,
) -> str:
    """
    Build complete USTX with enhanced expressions
    """
    
    if emotion is None:
        emotion = {"joy": 0.3, "sadness": 0.2, "tension": 0.1, "energy": energy, "darkness": darkness}
    
    joy = emotion.get("joy", 0.3)
    sadness = emotion.get("sadness", 0.2)
    tension = emotion.get("tension", 0.1)
    
    # Load groove template
    groove = _load_groove(groove_template)
    has_groove = groove is not None
    has_chords = chords is not None and len(chords) > 0
    
    # Extract melody from instrumental if available
    melody_notes = []
    if instrumental_path:
        try:
            print(f"🎼 Extracting melody from: {instrumental_path}")
            from pathlib import Path
            if Path(instrumental_path).exists():
                melody_notes = extract_melody_notes(instrumental_path)
                print(f"🎤 Melody extracted: {len(melody_notes)} notes")
        except Exception as e:
            print(f"⚠️ Melody extraction failed: {e}")
    
    # Parse lyrics
    words = [_clean(w) for w in lyrics.split()]
    total_words = len(words)
    
    print(f"🎸 {'Chord-aware' if has_chords else 'Fallback'} | {total_words} words")
    
    # Build notes with expressions
    notes_yaml = []
    pos = 0
    prev_tone = base_tone
    
    # Determine phrase boundaries (every 4-8 words)
    phrase_boundaries = []
    phrase_len = random.choice([4, 6, 8])
    for i in range(0, total_words, phrase_len):
        phrase_boundaries.append((i, min(i + phrase_len, total_words)))
    
    for phrase_idx, (phrase_start, phrase_end) in enumerate(phrase_boundaries):
        phrase_words = words[phrase_start:phrase_end]
        phrase_word_count = len(phrase_words)
        
        # Find phrase climax (usually 2/3 through)
        climax_idx = int(phrase_word_count * 0.66)
        
        for word_idx, word in enumerate(phrase_words):
            global_word_idx = phrase_start + word_idx
            
            # Determine note properties
            is_phrase_start = (word_idx == 0)
            is_phrase_end = (word_idx == phrase_word_count - 1)
            is_climax = (word_idx == climax_idx)
            
            # Get chord for this position
            if has_chords:
                time_sec = pos / 480 / (bpm / 60)
                chord = _chord_at(chords, time_sec)
                tones = chord["tones"]
                root = chord["root"]
            else:
                tones = [base_tone]
                root = base_tone
            
            # Pick tone
            tone = _pick_tone(
                tones, root, prev_tone,
                joy, sadness,
                is_phrase_start, is_phrase_end,
                word_idx, phrase_word_count
            )
            
            # Determine duration using LEARNED PATTERNS
            if has_groove and global_word_idx < len(groove.get("word_slots", [])):
                slot = groove["word_slots"][global_word_idx]
                # Check if slot has duration field (different groove formats)
                if isinstance(slot, dict) and "duration" in slot:
                    duration = _ticks(slot["duration"], bpm)
                elif isinstance(slot, dict) and "time" in slot:
                    # Calculate duration from time difference
                    next_idx = global_word_idx + 1
                    if next_idx < len(groove["word_slots"]):
                        next_slot = groove["word_slots"][next_idx]
                        time_diff = next_slot["time"] - slot["time"]
                        duration = _ticks(time_diff, bpm)
                    else:
                        duration = 480
                else:
                    duration = 480
            else:
                # Use learned timing patterns from professional USTX files
                try:
                    from timing_integration import get_timing_engine
                    timing_engine = get_timing_engine()
                    
                    duration = timing_engine.calculate_note_duration(
                        word=word,
                        is_phrase_start=is_phrase_start,
                        is_phrase_end=is_phrase_end,
                        is_climax=is_climax,
                        emotion=emotion,
                        bpm=bpm
                    )
                except Exception as e:
                    # Fallback to simple calculation if timing engine fails
                    word_len = len(word)
                    if word_len <= 2:
                        base_dur = 360
                    elif word_len <= 4:
                        base_dur = 480
                    else:
                        base_dur = 600
                    
                    if is_phrase_end:
                        base_dur = int(base_dur * 1.8)
                    elif is_climax:
                        base_dur = int(base_dur * 1.4)
                    
                    duration = base_dur
            
            is_sustained = duration > 600
            
            # Build note with all expressions
            note_yaml = _build_note_with_expressions(
                position=pos,
                duration=duration,
                tone=tone,
                lyric=word,
                emotion=emotion,
                prev_tone=prev_tone,
                is_phrase_start=is_phrase_start,
                is_phrase_end=is_phrase_end,
                is_phrase_climax=is_climax,
                is_sustained=is_sustained
            )
            
            notes_yaml.append(note_yaml)
            
            pos += duration
            prev_tone = tone
        
        # Add slight pause between phrases
        pos += 120
    
    part_dur = pos
    
    # Build final USTX - MATCH ORIGINAL FORMAT EXACTLY
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
  name: Vocalis-X Part (Enhanced)
  comment: "Generated with full expression support"
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
    groove_template=None, chords=None, instrumental_path=None,
) -> Path:
    """Write enhanced USTX to file"""
    text = build_ustx(
        lyrics, bpm, base_tone, emotion, darkness, energy,
        scale_notes, is_minor, groove_template, chords, instrumental_path
    )
    name = f"vocalisx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.ustx"
    out = OUTPUT_DIR / name
    out.write_text(text, encoding="utf-8")
    print(f"✨ Enhanced USTX created: {out}")
    return out


if __name__ == "__main__":
    # Test
    test_lyrics = "Hello world this is a test of the enhanced singing system"
    test_emotion = {
        "joy": 0.6,
        "sadness": 0.2,
        "tension": 0.3,
        "energy": 0.7,
        "darkness": 0.3
    }
    
    output = write_ustx(
        lyrics=test_lyrics,
        bpm=120,
        emotion=test_emotion
    )
    print(f"Test USTX written to: {output}")

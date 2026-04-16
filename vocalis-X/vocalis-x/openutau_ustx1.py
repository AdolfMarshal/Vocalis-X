import uuid
import re
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SINGER_NAME = "雷音レナ・Raine Rena 2.01"
# Use internal phonemizer ID so OpenUtau applies it reliably.
PHONEMIZER = "OpenUtau.Core.DiffSinger.DiffSingerARPAPlusEnglishPhonemizer"

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


def _clean_word(word: str) -> str:
    w = re.sub(r"[^A-Za-z']+", "", word)
    return w or "la"


def build_ustx(
    lyrics: str,
    bpm: int = 120,
    base_tone: int = 72,
    emotion: dict = None,
    darkness: float = 0.2,
    energy: float = 0.5,
) -> str:
    # Emotion-aware melody shaping.
    emotion = emotion or {}
    joy = float(emotion.get("joy", 0.3) or 0.3)
    sadness = float(emotion.get("sadness", 0.2) or 0.2)
    tension = float(emotion.get("tension", 0.1) or 0.1)
    darkness = float(darkness if darkness is not None else 0.2)
    energy = float(energy if energy is not None else 0.5)

    # Base pitch - sad/dark = lower, joy/energy = higher.
    base_tone = int(base_tone - (darkness * 8) - (sadness * 6) + (joy * 4))
    base_tone = max(48, min(84, base_tone))

    # Note duration - sad = longer holds, high energy = shorter.
    note_dur = int(480 * (1.0 + sadness * 0.8 - energy * 0.4))
    note_dur = max(180, min(960, note_dur))
    rest_gap = int(note_dur * 0.2)

    # Melody contour - tension = climbing steps, sadness = falling.
    if tension > 0.4:
        steps = [0, 2, 4, 5, 4, 2, 4, 7]   # climbing, tense
    elif sadness > 0.4:
        steps = [0, -1, -2, -1, -3, -2, -1, 0]  # falling, melancholic
    elif joy > 0.5:
        steps = [0, 2, 4, 2, 5, 4, 2, 4]   # bouncy, bright
    else:
        steps = [0, 1, 2, 1, 0, -1, 0, 2]  # neutral
    words = []
    for line in lyrics.strip().splitlines():
        for w in line.strip().split():
            words.append(_clean_word(w))

    if not words:
        words = ["la"]

    resolution = 480
    quarter = 480

    notes_yaml = []
    position = 0
    for i, word in enumerate(words):
        tone = base_tone + steps[i % len(steps)]
        # Vibrato - sadness = deep slow, joy = light fast
        vibrato_depth = int(15 + sadness * 20 - joy * 8)
        vibrato_period = int(175 + sadness * 50 - tension * 30)
        vibrato_depth = max(6, min(40, vibrato_depth))
        vibrato_period = max(90, min(260, vibrato_period))

        notes_yaml.append(
            f"  - position: {position}\n"
            f"    duration: {note_dur}\n"
            f"    tone: {tone}\n"
            f"    lyric: {word}\n"
            f"    pitch:\n"
            f"      data:\n"
            f"      - {{x: -25, y: 0, shape: io}}\n"
            f"      - {{x: 25, y: 0, shape: io}}\n"
            f"      snap_first: true\n"
            f"    vibrato: {{length: 60, period: {vibrato_period}, depth: {vibrato_depth}, in: 10, out: 10, shift: 0, drift: 0, vol_link: 0}}\n"
            f"    tuning: 0\n"
            f"    phoneme_expressions: []\n"
            f"    phoneme_overrides: []"
        )
        position += note_dur + rest_gap

    part_duration = max(position, quarter)

    ustx = f"""name: Vocalis-X Project
comment: ""
output_dir: Vocal
cache_dir: UCache
ustx_version: "0.9"
resolution: {resolution}
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
- duration: {part_duration}
  name: Vocalis-X Part
  comment: ""
  track_no: 0
  position: 0
  notes:
{chr(10).join(notes_yaml)}
  curves: []
wave_parts: []
"""
    return ustx


def write_ustx(
    lyrics: str,
    bpm: int = 120,
    base_tone: int = 72,
    emotion: dict = None,
    darkness: float = 0.2,
    energy: float = 0.5,
) -> Path:
    ustx_text = build_ustx(
        lyrics,
        bpm=bpm,
        base_tone=base_tone,
        emotion=emotion,
        darkness=darkness,
        energy=energy,
    )
    name = f"vocalisx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.ustx"
    out_path = OUTPUT_DIR / name
    out_path.write_text(ustx_text, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    sample = """hello world, I am calling tonight
hold the light and guide me home
every word is clear and bright
hello world, we sing as one
"""
    path = write_ustx(sample, bpm=120, base_tone=72)
    print(f"Wrote USTX: {path}")

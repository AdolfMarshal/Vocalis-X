"""
librosa_analysis.py — Vocalis-X
Analyzes a MusicGen instrumental WAV and extracts musical features
that are used to make Rena's singing match the mood of the music.

Usage:
    from librosa_analysis import analyze_instrumental, blend_with_user_emotion

    result = analyze_instrumental("output/abc123.wav")
    blended = blend_with_user_emotion(result, user_joy=0.4, ...)
"""

import numpy as np

# ── Music theory constants ────────────────────────────────────────────────────
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]
NOTE_NAMES  = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

# Rena Raine stable range: G3 (55) to A5 (81)
RENA_MIN_TONE = 55   # G3
RENA_MAX_TONE = 81   # A5
RENA_MID_TONE = 68   # G#4 — comfortable center


def midi_to_note(midi: int) -> str:
    return NOTE_NAMES[midi % 12] + str((midi // 12) - 1)


def clamp_to_rena_range(tone: int) -> int:
    """Clamp a MIDI note to Rena's stable singing range G3–A5."""
    return max(RENA_MIN_TONE, min(RENA_MAX_TONE, int(tone)))


def get_scale_tones(root_midi: int, mode: str) -> list:
    """
    Return absolute MIDI tones within Rena's range for the given key/mode.
    Covers 1-2 octaves so there are enough notes for melody steps.
    """
    offsets = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    root_pc = root_midi % 12

    # Find octave base that puts root near RENA_MID_TONE
    octave_base = (RENA_MID_TONE // 12) * 12 + root_pc
    if octave_base < RENA_MIN_TONE:
        octave_base += 12
    if octave_base > RENA_MAX_TONE:
        octave_base -= 12

    tones = set()
    for octave_shift in [-12, 0, 12]:
        for s in offsets:
            t = clamp_to_rena_range(octave_base + octave_shift + s)
            tones.add(t)

    return sorted(tones)


# ── Key detection profiles (Krumhansl-Schmuckler) ────────────────────────────
_MAJOR_PROFILE = np.array([6.35,2.23,3.48,2.33,4.38,4.09,
                            2.52,5.19,2.39,3.66,2.29,2.88])
_MINOR_PROFILE = np.array([6.33,2.68,3.52,5.38,2.60,3.53,
                            2.54,4.75,3.98,2.69,3.34,3.17])


def _detect_key(chroma_mean: np.ndarray):
    major_scores, minor_scores = [], []
    for i in range(12):
        rc = np.roll(chroma_mean, -i)
        major_scores.append(np.corrcoef(rc, _MAJOR_PROFILE)[0, 1])
        minor_scores.append(np.corrcoef(rc, _MINOR_PROFILE)[0, 1])
    bm = int(np.argmax(major_scores))
    bn = int(np.argmax(minor_scores))
    if max(major_scores) >= max(minor_scores):
        return bm, "major"
    return bn, "minor"


# ── Main analysis function ────────────────────────────────────────────────────

def analyze_instrumental(path: str) -> dict:
    """
    Analyze a WAV file and return musical features for USTX generation.

    Returns dict with keys:
        tempo, beat_times, key_midi, key_name, mode, scale_tones,
        energy, tension, joy, sadness, darkness, suggested_base_tone
    """
    try:
        import librosa
    except ImportError:
        print("⚠️  librosa not installed — run: pip install librosa")
        return _fallback_result()

    print(f"🎵 Analyzing: {path}")

    try:
        y, sr = librosa.load(path, mono=True)
    except Exception as e:
        print(f"⚠️  Could not load audio: {e}")
        return _fallback_result()

    # Tempo & beats
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.atleast_1d(tempo)[0])
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    except Exception:
        tempo, beat_times = 120.0, []

    # Key
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
        key_midi, mode = _detect_key(chroma)
        key_name = NOTE_NAMES[key_midi]
    except Exception:
        key_midi, mode, key_name = 0, "major", "C"

    # Energy (RMS)
    try:
        rms_mean = float(librosa.feature.rms(y=y)[0].mean())
        energy = float(np.clip(rms_mean / 0.2, 0.0, 1.0))
    except Exception:
        energy = 0.5

    # Brightness / darkness (spectral centroid)
    try:
        centroid_mean = float(librosa.feature.spectral_centroid(y=y, sr=sr)[0].mean())
        brightness = float(np.clip((centroid_mean - 500) / 3500, 0.0, 1.0))
        darkness = 1.0 - brightness
    except Exception:
        brightness, darkness = 0.5, 0.5

    # Tension (zero crossing rate)
    try:
        zcr_mean = float(librosa.feature.zero_crossing_rate(y=y)[0].mean())
        tension = float(np.clip(zcr_mean / 0.15, 0.0, 1.0))
    except Exception:
        tension = 0.3

    # Derive joy and sadness
    tempo_factor = float(np.clip((tempo - 60.0) / 120.0, 0.0, 1.0))
    mode_factor  = 1.0 if mode == "major" else 0.0

    joy = float(np.clip(
        0.4 * tempo_factor +
        0.3 * mode_factor  +
        0.2 * energy       +
        0.1 * brightness,
        0.0, 1.0
    ))
    sadness = float(np.clip(
        0.3 * (1.0 - tempo_factor) +
        0.3 * (1.0 - mode_factor)  +
        0.2 * (1.0 - energy)       +
        0.2 * darkness,
        0.0, 1.0
    ))

    # Scale tones within Rena's range
    scale_tones = get_scale_tones(key_midi, mode)

    # Best base tone for Rena in this key/emotion
    emotion_offset = int(joy * 4 - sadness * 4 - darkness * 3)
    target = clamp_to_rena_range(RENA_MID_TONE + emotion_offset)
    suggested_base = min(scale_tones, key=lambda t: abs(t - target))

    result = {
        "tempo":              round(tempo, 1),
        "beat_times":         beat_times[:16],
        "key_midi":           key_midi,
        "key_name":           key_name,
        "mode":               mode,
        "scale_tones":        scale_tones,
        "energy":             round(energy, 3),
        "tension":            round(tension, 3),
        "joy":                round(joy, 3),
        "sadness":            round(sadness, 3),
        "darkness":           round(darkness, 3),
        "suggested_base_tone": suggested_base,
    }

    print(f"  ✅ Tempo: {result['tempo']} BPM | Key: {key_name} {mode}")
    print(f"  ✅ Energy: {result['energy']} | Joy: {result['joy']} | Sadness: {result['sadness']} | Darkness: {result['darkness']}")
    print(f"  ✅ Rena base tone: {suggested_base} ({midi_to_note(suggested_base)})")
    return result


def blend_with_user_emotion(
    music: dict,
    user_joy:      float = 0.3,
    user_sadness:  float = 0.2,
    user_tension:  float = 0.1,
    user_energy:   float = 0.5,
    user_darkness: float = 0.2,
    music_weight:  float = 0.5,
) -> dict:
    """
    Blend music analysis with user slider values.
    music_weight=0.5 → equal weight between music and user.
    music_weight=0.8 → Rena reacts 80% to the music, 20% to user sliders.
    """
    w = float(np.clip(music_weight, 0.0, 1.0))
    u = 1.0 - w
    return {
        "joy":      round(w * music["joy"]     + u * user_joy,      3),
        "sadness":  round(w * music["sadness"] + u * user_sadness,   3),
        "tension":  round(w * music["tension"] + u * user_tension,   3),
        "energy":   round(w * music["energy"]  + u * user_energy,    3),
        "darkness": round(w * music["darkness"]+ u * user_darkness,  3),
    }


def _fallback_result() -> dict:
    return {
        "tempo": 120.0, "beat_times": [],
        "key_midi": 0, "key_name": "C", "mode": "major",
        "scale_tones": get_scale_tones(0, "major"),
        "energy": 0.5, "tension": 0.3,
        "joy": 0.3, "sadness": 0.2, "darkness": 0.2,
        "suggested_base_tone": RENA_MID_TONE,
    }


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "sample.wav"
    result = analyze_instrumental(path)
    print("\nFull result:")
    for k, v in result.items():
        if k != "beat_times":
            print(f"  {k}: {v}")
    blended = blend_with_user_emotion(result, music_weight=0.6)
    print("\nBlended emotion (60% music / 40% user defaults):")
    for k, v in blended.items():
        print(f"  {k}: {v}")

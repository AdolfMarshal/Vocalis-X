"""
chord_extractor.py — Vocalis-X
Extracts chord root + tones per beat. Locked to ONE octave near Rena's mid range.

Design principle:
  - Rena sings in ONE comfortable octave (D4-D5 range, MIDI 62-74)
  - Chord tones are only generated within that octave — no octave jumping
  - Root note is always included and preferred on phrase starts/ends
  - 3rd and 5th fill in the melodic movement within the phrase
"""

import numpy as np
import json
import os

try:
    import librosa
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False

NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

CHORD_TEMPLATES = {
    "maj":  [0, 4, 7],
    "min":  [0, 3, 7],
    "7":    [0, 4, 7, 10],
    "maj7": [0, 4, 7, 11],
    "min7": [0, 3, 7, 10],
    "dim":  [0, 3, 6],
    "aug":  [0, 4, 8],
    "sus4": [0, 5, 7],
}

# Rena's comfortable singing range — ONE octave, no jumping
# D4 to D5 is Rena's sweetspot (not too low, not strained high)
RENA_SWEET_MIN = 62   # D4
RENA_SWEET_MAX = 74   # D5
RENA_SWEET_MID = 68   # G#4
RENA_ABS_MIN   = 55   # G3 (hard floor)
RENA_ABS_MAX   = 81   # A5 (hard ceiling)


def _chord_tones_single_octave(root_pc: int, intervals: list) -> dict:
    """
    Generate chord tones in ONE octave near Rena's sweet spot.
    Returns dict with root, third, fifth, all as MIDI notes.
    No multi-octave spanning — everything in one comfortable register.
    """
    # Find the root in Rena's sweet zone
    root_candidate = RENA_SWEET_MIN + root_pc
    while root_candidate < RENA_SWEET_MIN:
        root_candidate += 12
    while root_candidate > RENA_SWEET_MAX:
        root_candidate -= 12
    # If still out of range, allow slight extension
    if root_candidate < RENA_ABS_MIN:
        root_candidate += 12
    if root_candidate > RENA_ABS_MAX:
        root_candidate -= 12

    # Build all chord tones from that root in ONE octave
    tones = []
    for iv in intervals:
        t = root_candidate + iv
        if RENA_ABS_MIN <= t <= RENA_ABS_MAX:
            tones.append(t)

    # If no tones fit, just use the root
    if not tones:
        tones = [root_candidate]

    return {
        "root":       root_candidate,
        "tones":      sorted(tones),
        "bass_note":  root_candidate,  # root = bass in our system
    }


def _match_chord(chroma_vector: np.ndarray):
    """Match 12-element chroma to best chord. Returns (root_pc, type, score)."""
    best_score, best_root, best_type = -1, 0, "min"
    norm_c = chroma_vector / (np.linalg.norm(chroma_vector) + 1e-8)
    for root in range(12):
        for chord_type, intervals in CHORD_TEMPLATES.items():
            template = np.zeros(12)
            for iv in intervals:
                template[(root + iv) % 12] = 1.0
            norm_t = template / (np.linalg.norm(template) + 1e-8)
            score  = float(np.dot(norm_c, norm_t))
            if score > best_score:
                best_score, best_root, best_type = score, root, chord_type
    return best_root, best_type, best_score


def extract_chords(audio_path: str) -> list:
    """
    Extract chord at every beat. All chord tones locked to one octave.
    Returns list of {time, chord_name, root, tones, bass_note}
    """
    if not LIBROSA_OK:
        print("librosa not installed")
        return []

    print(f"\n🎸 Chord extraction: {os.path.basename(audio_path)}")
    y, sr  = librosa.load(audio_path, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    tempo  = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)

    print(f"   {tempo:.1f} BPM | {len(beat_times)} beats")

    chords     = []
    prev_chord = None

    for i, beat_time in enumerate(beat_times):
        f_start = beat_frames[i]
        f_end   = beat_frames[i+1] if i+1 < len(beat_frames) else f_start + 10
        beat_chroma = chroma[:, f_start:f_end].mean(axis=1)

        root_pc, chord_type, score = _match_chord(beat_chroma)
        intervals  = CHORD_TEMPLATES[chord_type]
        chord_data = _chord_tones_single_octave(root_pc, intervals)

        type_label = "" if chord_type == "maj" else chord_type
        entry = {
            "beat_idx":   i,
            "time":       round(float(beat_time), 4),
            "chord_name": f"{NOTE_NAMES[root_pc]}{type_label}",
            "root_pc":    root_pc,
            "chord_type": chord_type,
            "root":       chord_data["root"],
            "tones":      chord_data["tones"],
            "bass_note":  chord_data["bass_note"],
            # keep chord_tones as alias for backward compat
            "chord_tones": chord_data["tones"],
        }
        chords.append(entry)
        prev_chord = entry

    # Show chord changes
    print("   Chord progression:")
    prev_name = None
    for c in chords:
        if c["chord_name"] != prev_name:
            tone_names = [f"{NOTE_NAMES[t%12]}{t//12-1}" for t in c["tones"]]
            print(f"     {c['time']:6.2f}s  {c['chord_name']:<6}  root={NOTE_NAMES[c['root_pc']]}{c['root']//12-1}  tones={tone_names}")
            prev_name = c["chord_name"]

    return chords


def get_chord_at_time(chords: list, t: float) -> dict:
    if not chords:
        return {"tones": [RENA_SWEET_MID], "root": RENA_SWEET_MID,
                "bass_note": RENA_SWEET_MID, "chord_name": "?", "chord_tones": [RENA_SWEET_MID]}
    best = chords[0]
    for c in chords:
        if c["time"] <= t:
            best = c
        else:
            break
    return best


def save_chords(chords, path):
    with open(path, 'w') as f:
        json.dump(chords, f, indent=2)


def load_chords(path):
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python chord_extractor.py path/to/no_vocals.wav")
    else:
        chords = extract_chords(sys.argv[1])
        out = sys.argv[1].replace(".wav", "_chords.json")
        save_chords(chords, out)
        print(f"Saved: {out}")
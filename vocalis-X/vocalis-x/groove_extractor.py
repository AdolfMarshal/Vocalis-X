"""
groove_extractor.py — Vocalis-X
Extracts musical structure from vocals.wav for use as a singing template.

What this extracts (and WHY):
  beat_times:   Exact beat timestamps → Rena snaps to beat grid, not random onsets
  phrases:      2-bar/4-bar boundaries → one lyric line per phrase
  word_slots:   Beat-subdivided word timing → words land on beats or 8th notes
  section_keys: Key per 10s window → verse gets minor, chorus gets major separately
  breaths:      Silence gaps > 300ms → real breath injection points
  tempo:        Detected BPM → Rena sings at actual song tempo
"""

import os
import glob
import json
import numpy as np

try:
    import librosa
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False
    print("librosa not installed. Run: pip install librosa")

NOTE_NAMES     = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
MAJOR_SCALE    = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE    = [0, 2, 3, 5, 7, 8, 10]
_MAJOR_PROFILE = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
_MINOR_PROFILE = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
RENA_MIN = 55
RENA_MAX = 81
RENA_MID = 68


def _detect_key_from_chroma(chroma_mean):
    major_scores, minor_scores = [], []
    for i in range(12):
        rc = np.roll(chroma_mean, -i)
        major_scores.append(float(np.corrcoef(rc, _MAJOR_PROFILE)[0, 1]))
        minor_scores.append(float(np.corrcoef(rc, _MINOR_PROFILE)[0, 1]))
    bm = int(np.argmax(major_scores))
    bn = int(np.argmax(minor_scores))
    if max(major_scores) >= max(minor_scores):
        return bm, "major"
    return bn, "minor"


def _build_scale_tones(root_pc, mode):
    offsets = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    base = (RENA_MID // 12) * 12 + root_pc
    if base < RENA_MIN: base += 12
    if base > RENA_MAX: base -= 12
    tones = set()
    for shift in [-12, 0, 12]:
        for s in offsets:
            t = max(RENA_MIN, min(RENA_MAX, base + shift + s))
            tones.add(t)
    return sorted(tones)


def _detect_sections(y, sr, window_sec=10.0):
    """Detect key per time window — verse minor, chorus major separately."""
    duration = float(librosa.get_duration(y=y, sr=sr))
    sections = []
    t = 0.0
    while t < duration:
        end = min(t + window_sec, duration)
        seg = y[int(t * sr):int(end * sr)]
        if len(seg) < sr * 0.5:
            t = end
            continue
        try:
            chroma = librosa.feature.chroma_cqt(y=seg, sr=sr).mean(axis=1)
            key_pc, mode = _detect_key_from_chroma(chroma)
        except Exception:
            key_pc, mode = 0, "major"
        sections.append({
            "start":       round(t, 3),
            "end":         round(end, 3),
            "key_pc":      key_pc,
            "key_name":    NOTE_NAMES[key_pc],
            "mode":        mode,
            "scale_tones": _build_scale_tones(key_pc, mode),
        })
        t = end
    return sections


def _extract_beat_grid(y, sr):
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    tempo = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    return tempo, beat_times


def _build_phrase_grid(beat_times, beats_per_phrase=8):
    """
    Build phrase boundaries every N beats (default 8 = 2 bars of 4/4).
    Also builds 8th-note subdivisions within each phrase for word placement.
    """
    phrases = []
    n = len(beat_times)
    for i in range(0, n, beats_per_phrase):
        end_idx      = min(i + beats_per_phrase, n - 1)
        phrase_beats = beat_times[i:end_idx + 1]
        subdivisions = []
        for j in range(len(phrase_beats) - 1):
            b0 = phrase_beats[j]
            b1 = phrase_beats[j + 1]
            subdivisions.append(round(b0, 4))
            subdivisions.append(round((b0 + b1) / 2.0, 4))
        phrases.append({
            "start":          round(phrase_beats[0], 4),
            "end":            round(phrase_beats[-1], 4),
            "beat_start_idx": i,
            "beat_end_idx":   end_idx,
            "subdivisions":   subdivisions,
        })
    return phrases


def _extract_breaths(y, sr, min_silence_sec=0.3, top_db=35):
    intervals = librosa.effects.split(y, top_db=top_db)
    breaths = []
    for i in range(len(intervals) - 1):
        gs = intervals[i][1] / sr
        ge = intervals[i + 1][0] / sr
        dur = ge - gs
        if dur >= min_silence_sec:
            breaths.append({"start": round(gs, 4), "end": round(ge, 4), "duration": round(dur, 4)})
    return breaths


def _extract_onsets(y, sr):
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_times = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            units="time",
            backtrack=False,
            pre_max=20,
            post_max=20,
            pre_avg=100,
            post_avg=100,
            delta=0.2,
            wait=10,
        )
        return [round(float(t), 4) for t in onset_times.tolist()]
    except Exception:
        return []


def _snap_slots_to_onsets(slots, phrase_start, phrase_end, onset_times, max_shift=0.18):
    if not onset_times:
        return slots
    in_phrase = [t for t in onset_times if phrase_start <= t <= phrase_end]
    if not in_phrase:
        return slots
    snapped = []
    for s in slots:
        nearest = min(in_phrase, key=lambda t: abs(t - s))
        if abs(nearest - s) <= max_shift:
            snapped.append(round(float(nearest), 4))
        else:
            snapped.append(round(float(s), 4))
    return snapped


def _build_word_slots(phrases, breaths, total_slots=250, onset_times=None):
    """
    Assign word timing slots to beat subdivisions across all phrases.
    Words land ON the beat grid — not on random syllable onsets.
    """
    if not phrases:
        return []

    breath_before = set()
    for b in breaths:
        for i, p in enumerate(phrases):
            if i > 0 and abs(p["start"] - b["end"]) < 0.6:
                breath_before.add(i)

    total_dur  = phrases[-1]["end"] - phrases[0]["start"]
    word_slots = []
    word_idx   = 0

    for p_idx, phrase in enumerate(phrases):
        if word_idx >= total_slots:
            break
        subs = phrase["subdivisions"]
        if not subs:
            continue

        phrase_dur        = phrase["end"] - phrase["start"]
        proportion        = phrase_dur / total_dur if total_dur > 0 else 1.0 / len(phrases)
        words_this_phrase = max(1, round(proportion * total_slots))
        words_this_phrase = min(words_this_phrase, total_slots - word_idx)

        avail = subs[1:] if p_idx in breath_before and len(subs) > 2 else subs

        if words_this_phrase >= len(avail):
            slots_to_use = list(avail)
            while len(slots_to_use) < words_this_phrase:
                slots_to_use.append(avail[-1])
        else:
            step         = len(avail) / words_this_phrase
            slots_to_use = [avail[int(i * step)] for i in range(words_this_phrase)]

        slots_to_use = _snap_slots_to_onsets(
            slots_to_use,
            phrase_start=phrase["start"],
            phrase_end=phrase["end"],
            onset_times=onset_times or [],
            max_shift=0.18,
        )

        for i, t in enumerate(slots_to_use):
            word_slots.append({
                "word_idx":   word_idx,
                "time":       round(float(t), 4),
                "phrase_idx": p_idx,
                "on_beat":    (i % 2 == 0),
            })
            word_idx += 1

    return word_slots


def extract_groove(vocal_path, output_json_path, beats_per_phrase=8):
    if not LIBROSA_OK:
        print("librosa required. pip install librosa")
        return None

    print(f"\n🎤 Extracting: {os.path.basename(os.path.dirname(vocal_path))}")

    try:
        y, sr = librosa.load(vocal_path, sr=None, mono=True)
    except Exception as e:
        print(f"Could not load: {e}")
        return None

    duration = float(librosa.get_duration(y=y, sr=sr))
    print(f"   Duration: {duration:.1f}s")

    print("   Extracting beat grid...")
    tempo, beat_times = _extract_beat_grid(y, sr)
    print(f"   Tempo: {tempo:.1f} BPM | {len(beat_times)} beats")

    print("   Building phrase grid...")
    phrases = _build_phrase_grid(beat_times, beats_per_phrase=beats_per_phrase)
    print(f"   {len(phrases)} phrases")

    print("   Detecting key per section...")
    sections = _detect_sections(y, sr)
    key_counts = {}
    for s in sections:
        k = f"{s['key_name']} {s['mode']}"
        key_counts[k] = key_counts.get(k, 0) + 1
    dominant = max(key_counts, key=key_counts.get)
    print(f"   Dominant key: {dominant}")

    print("   Detecting breaths...")
    breaths = _extract_breaths(y, sr)
    print(f"   {len(breaths)} breath points")

    print("   Detecting vocal onsets...")
    onset_times = _extract_onsets(y, sr)
    print(f"   {len(onset_times)} onsets")

    print("   Building word slots...")
    word_slots = _build_word_slots(phrases, breaths, total_slots=250, onset_times=onset_times)
    print(f"   {len(word_slots)} slots built")

    groove = {
        "source_file":      vocal_path,
        "total_duration":   round(duration, 4),
        "tempo":            round(tempo, 2),
        "time_signature":   "4/4",
        "beats_per_phrase": beats_per_phrase,
        "beat_times":       [round(t, 4) for t in beat_times],
        "phrases":          phrases,
        "word_slots":       word_slots,
        # Backward-compat alias for older consumers.
        "syllable_hits":    [ws["time"] for ws in word_slots],
        "onset_times":      onset_times,
        "section_keys":     sections,
        "breaths":          breaths,
    }

    with open(output_json_path, 'w') as f:
        json.dump(groove, f, indent=2)

    print(f"   Saved: {output_json_path}")
    return groove


if __name__ == "__main__":
    DEMUCS_OUTPUT_DIR = "separated/htdemucs"
    TEMPLATE_DIR      = "swagger_templates"
    os.makedirs(TEMPLATE_DIR, exist_ok=True)

    print("Scanning for Demucs vocal tracks...")
    vocal_files = glob.glob(os.path.join(DEMUCS_OUTPUT_DIR, "*", "vocals.wav"))

    if not vocal_files:
        print(f"No vocals.wav found in {DEMUCS_OUTPUT_DIR}")
    else:
        print(f"Found {len(vocal_files)} tracks\n")
        for vp in vocal_files:
            song_name   = os.path.basename(os.path.dirname(vp))
            output_path = os.path.join(TEMPLATE_DIR, f"{song_name}_groove.json")
            extract_groove(vp, output_path)
        print("\nALL DONE!")

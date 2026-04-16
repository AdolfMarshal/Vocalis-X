"""
melody_composer.py — Vocalis-X
====================================
The CONDUCTOR layer between chord_extractor and openutau_ustx.

Pipeline:
    WAV → chord_extractor → [Am, F, C, G...]
                                    ↓
                            melody_composer  ← YOU ARE HERE
                                    ↓
                    [{time, tone, duration}, ...]
                                    ↓
                           openutau_ustx → Rena sings

Uses Google Magenta's Melody RNN — a model trained on millions of MIDI
files to generate melodies that are musically coherent over chord progressions.

Falls back to a music-theory rule engine if Magenta isn't installed.

INSTALL:
    pip install magenta
    # If that conflicts with your venv:
    pip install note-seq pretty_midi tensorflow
"""

import os
import random
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

# ── Constants ────────────────────────────────────────────────────────────────

RENA_MIN   = 55   # G3
RENA_MAX   = 81   # A5
SWEET_MIN  = 60   # C4 — comfortable floor
SWEET_MAX  = 72   # C5 — comfortable ceiling

NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

# Chord → scale degrees that sound good over it
# Used by the fallback rule engine
CHORD_GOOD_INTERVALS = {
    "maj":  [0, 4, 7, 2, 9],        # root, 3rd, 5th, 2nd, 6th
    "min":  [0, 3, 7, 2, 10],       # root, b3, 5th, 2nd, b7
    "7":    [0, 4, 7, 10, 2],       # dominant 7
    "maj7": [0, 4, 7, 11, 2],       # major 7
    "min7": [0, 3, 7, 10, 2],       # minor 7
    "dim":  [0, 3, 6, 9],           # diminished
    "aug":  [0, 4, 8],              # augmented
    "sus4": [0, 5, 7, 2],           # suspended
}

# ── Magenta Melody RNN ────────────────────────────────────────────────────────

def _try_magenta(
    chords: List[Dict],
    bpm: float,
    total_beats: int,
    temperature: float = 1.1,
) -> Optional[List[Dict]]:
    """
    Use Magenta Melody RNN to generate a melody over the chord progression.
    Returns list of {time, duration, tone} or None if Magenta unavailable.
    """
    try:
        from magenta.models.melody_rnn import melody_rnn_sequence_generator
        from magenta.models.shared import sequence_generator_bundle
        from note_seq import constants as ns_constants
        from note_seq.protobuf import generator_pb2, music_pb2
        import note_seq
    except ImportError:
        return None

    print("🎼 Magenta Melody RNN: generating melody...")

    try:
        # ── Download / load checkpoint ───────────────────────────────────
        bundle_dir  = Path.home() / "magenta" / "models" / "melody_rnn"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_file = bundle_dir / "attention_rnn.mag"

        if not bundle_file.exists():
            print("   Downloading attention_rnn checkpoint (~50MB)...")
            import urllib.request
            url = ("https://storage.googleapis.com/magentadata/models/"
                   "melody_rnn/attention_rnn.mag")
            urllib.request.urlretrieve(url, bundle_file)
            print("   Downloaded.")

        bundle    = sequence_generator_bundle.read_bundle_file(str(bundle_file))
        generator = melody_rnn_sequence_generator.MelodyRnnSequenceGenerator(
            model=melody_rnn_sequence_generator.MelodyRnnModel(
                melody_rnn_sequence_generator.default_configs["attention_rnn"]
            ),
            details=bundle.generator_details,
            steps_per_quarter=4,
            bundle=bundle,
        )
        generator.initialize()

        # ── Build chord sequence for the generator ────────────────────────
        # Magenta wants a NoteSequence with chord annotations
        primer_seq = music_pb2.NoteSequence()
        primer_seq.tempos.add().qpm = bpm

        seconds_per_beat = 60.0 / bpm

        # Add chord annotations
        for i, chord in enumerate(chords):
            annotation       = primer_seq.text_annotations.add()
            annotation.time  = chord["time"]
            annotation.text  = chord["chord_name"]
            annotation.annotation_type = (
                music_pb2.NoteSequence.TextAnnotation.CHORD_SYMBOL
            )

        total_seconds = total_beats * seconds_per_beat

        # Primer: one bar of silence (lets model start fresh)
        primer_seq.total_time = seconds_per_beat * 4

        # ── Generation request ────────────────────────────────────────────
        generator_options = generator_pb2.GeneratorOptions()
        generator_options.args["temperature"].float_value     = temperature
        generator_options.args["beam_size"].int_value         = 1
        generator_options.args["branch_factor"].int_value     = 1
        generator_options.args["steps_per_iteration"].int_value = 1

        section = generator_options.generate_sections.add()
        section.start_time = primer_seq.total_time
        section.end_time   = total_seconds

        generated = generator.generate(primer_seq, generator_options)

        # ── Convert NoteSequence → our format ────────────────────────────
        melody_notes = []
        for note in generated.notes:
            if note.start_time < primer_seq.total_time:
                continue  # skip primer
            tone = _transpose_to_sweet(note.pitch)
            melody_notes.append({
                "time":     round(note.start_time, 4),
                "duration": round(note.end_time - note.start_time, 4),
                "tone":     tone,
            })

        melody_notes.sort(key=lambda x: x["time"])
        print(f"   ✅ {len(melody_notes)} notes generated by Melody RNN")
        return melody_notes

    except Exception as e:
        print(f"   ⚠️  Melody RNN failed: {e}")
        return None


# ── Rule-based fallback conductor ─────────────────────────────────────────────

def _rule_based_melody(
    chords: List[Dict],
    bpm: float,
    num_words: int,
    joy: float       = 0.3,
    sadness: float   = 0.2,
    tension: float   = 0.1,
    energy: float    = 0.5,
) -> List[Dict]:
    """
    Music-theory rule engine. Generates a melody that:
    - Uses notes from the current chord (never clashes)
    - Has an arch shape (builds to a peak, resolves down)
    - Moves stepwise most of the time (no random leaps)
    - Resolves to root note at phrase endings
    - Varies rhythm naturally (not all quarter notes)

    This is what a songwriter does manually — automated.
    """
    print("🎼 Rule engine: composing melody over chords...")

    seconds_per_beat = 60.0 / bpm
    melody           = []
    prev_tone        = 65   # start mid-range (F4)

    # Phrase structure: 8 words per phrase
    phrase_size  = 8
    num_phrases  = max(1, num_words // phrase_size)

    # Overall song arc — starts mid, peaks at 2/3 through, resolves
    def _song_position_bias(word_idx: int) -> float:
        """Returns 0.0 (low/dark) to 1.0 (high/bright) based on song position."""
        pos = word_idx / max(num_words - 1, 1)
        # Arch: rises to peak at 65%, falls back
        if pos < 0.65:
            return pos / 0.65
        else:
            return 1.0 - (pos - 0.65) / 0.35

    word_idx = 0

    for phrase_idx in range(num_phrases + 1):
        phrase_start_word = phrase_idx * phrase_size
        phrase_end_word   = min(phrase_start_word + phrase_size, num_words)

        if phrase_start_word >= num_words:
            break

        # Phrase-level arc: each phrase has its own rise/fall
        phrase_len = phrase_end_word - phrase_start_word

        for pos_in_phrase in range(phrase_len):
            if word_idx >= num_words:
                break

            # ── Get chord at this time ────────────────────────────────
            # Approximate time based on word index
            approx_time = word_idx * seconds_per_beat * 1.2
            chord       = _chord_at_time(chords, approx_time)
            root_pc     = chord.get("root_pc", 0)
            chord_type  = chord.get("chord_type", "maj")
            intervals   = CHORD_GOOD_INTERVALS.get(chord_type, [0, 4, 7])

            # ── Build available notes in sweet zone ───────────────────
            available = _build_chord_notes(root_pc, intervals)
            if not available:
                available = [60, 64, 67]  # C major fallback

            # ── Decide target register based on song arc ──────────────
            arc        = _song_position_bias(word_idx)
            phrase_arc = pos_in_phrase / max(phrase_len - 1, 1)

            # Emotion shifts the arc
            arc = arc + (joy - 0.3) * 0.2 - (sadness - 0.2) * 0.15

            # Split available notes into low/mid/high thirds
            low   = [n for n in available if n < 64]
            mid   = [n for n in available if 64 <= n <= 68]
            high  = [n for n in available if n > 68]

            if arc > 0.7 and high:
                target_pool = high
            elif arc > 0.35 and mid:
                target_pool = mid
            elif low:
                target_pool = low
            else:
                target_pool = available

            # ── Phrase ending: resolve to root ────────────────────────
            is_phrase_end = (pos_in_phrase == phrase_len - 1)
            if is_phrase_end:
                root_notes = [n for n in available
                              if n % 12 == root_pc]
                if root_notes:
                    target_pool = root_notes

            # ── Voice leading: pick note closest to prev_tone ─────────
            # But bias toward target_pool
            if target_pool and random.random() < 0.75:
                tone = min(target_pool, key=lambda n: abs(n - prev_tone))
            else:
                tone = min(available, key=lambda n: abs(n - prev_tone))

            # ── Avoid large leaps (> 4 semitones) ─────────────────────
            # If leap is big, step toward target instead
            if abs(tone - prev_tone) > 4:
                direction = 1 if tone > prev_tone else -1
                # Find nearest available note 1-2 steps in direction
                step_targets = [n for n in available
                                if 0 < direction * (n - prev_tone) <= 3]
                if step_targets:
                    tone = min(step_targets,
                               key=lambda n: abs(n - prev_tone))

            tone      = _clamp(tone)
            prev_tone = tone

            # ── Rhythm: vary note duration naturally ──────────────────
            # Beat position within phrase affects duration
            beat_in_phrase = pos_in_phrase % 4

            if is_phrase_end:
                # Phrase endings hold longer
                dur = seconds_per_beat * random.uniform(1.5, 2.5)
            elif beat_in_phrase == 0:
                # Downbeats are slightly longer
                dur = seconds_per_beat * random.uniform(0.9, 1.3)
            elif energy > 0.6:
                # High energy = faster notes
                dur = seconds_per_beat * random.uniform(0.4, 0.8)
            elif sadness > 0.5:
                # Sad = slower, more sustained
                dur = seconds_per_beat * random.uniform(0.8, 1.4)
            else:
                dur = seconds_per_beat * random.uniform(0.5, 1.1)

            melody.append({
                "time":     round(approx_time, 4),
                "duration": round(dur, 4),
                "tone":     tone,
            })

            word_idx += 1

    print(f"   ✅ {len(melody)} notes from rule engine")
    return melody


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_chord_notes(root_pc: int, intervals: list) -> list:
    """All MIDI notes for this chord within Rena's sweet zone."""
    notes = set()
    for octave in range(3, 8):
        for iv in intervals:
            n = root_pc + iv + octave * 12
            if SWEET_MIN <= n <= SWEET_MAX:
                notes.add(n)
    return sorted(notes)


def _transpose_to_sweet(tone: int) -> int:
    """Octave-shift any MIDI note into Rena's sweet zone."""
    t = int(tone)
    while t < SWEET_MIN: t += 12
    while t > SWEET_MAX: t -= 12
    return max(RENA_MIN, min(RENA_MAX, t))


def _clamp(tone: int) -> int:
    return max(RENA_MIN, min(RENA_MAX, int(tone)))


def _chord_at_time(chords: list, t: float) -> dict:
    if not chords:
        return {"root_pc": 0, "chord_type": "maj",
                "chord_tones": [60, 64, 67], "bass_note": 60}
    best = chords[0]
    for c in chords:
        if c["time"] <= t:
            best = c
        else:
            break
    return best


# ── Public API ────────────────────────────────────────────────────────────────

def compose_melody(
    chords:     List[Dict],
    bpm:        float,
    num_words:  int,
    joy:        float = 0.3,
    sadness:    float = 0.2,
    tension:    float = 0.1,
    energy:     float = 0.5,
    temperature: float = 1.1,   # Melody RNN creativity (0.5=safe, 1.5=wild)
) -> List[Dict]:
    """
    Main entry point. Returns [{time, duration, tone}] for every word.

    Tries Magenta Melody RNN first (best quality).
    Falls back to rule engine if Magenta not installed.

    Args:
        chords:     output of chord_extractor.extract_chords()
        bpm:        song tempo
        num_words:  number of lyric words to cover
        joy/sadness/tension/energy: emotion values from librosa_analysis
        temperature: Melody RNN randomness (higher = more adventurous)
    """
    if not chords:
        print("⚠️  No chords provided — melody will be pentatonic walk")

    total_beats = int(num_words * 1.5)  # rough beat count

    # Try Magenta first
    notes = _try_magenta(chords, bpm, total_beats, temperature)

    # Fall back to rule engine
    if not notes:
        notes = _rule_based_melody(
            chords, bpm, num_words,
            joy=joy, sadness=sadness,
            tension=tension, energy=energy,
        )

    # Ensure we have enough notes for every word
    while len(notes) < num_words:
        # Repeat last note slightly varied
        last = notes[-1] if notes else {"time": 0, "duration": 0.5, "tone": 65}
        notes.append({
            "time":     last["time"] + last["duration"],
            "duration": last["duration"],
            "tone":     _clamp(last["tone"] + random.choice([-2, 0, 2])),
        })

    return notes[:num_words]
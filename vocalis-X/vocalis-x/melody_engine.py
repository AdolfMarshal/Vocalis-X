# melody_engine.py
# Vocalis-X Melody Intelligence Engine
# Combines:
# - chord following
# - scale following
# - emotional contour
# - phrase resolution
# - human-like melodic motion

import random

# Human singing interval probabilities
STEP_INTERVALS = [-2, -1, 1, 2]
STEP_WEIGHTS   = [0.22, 0.28, 0.28, 0.22]

LEAP_INTERVALS = [-5, -4, 4, 5, 7]
LEAP_WEIGHTS   = [0.10, 0.15, 0.15, 0.10, 0.05]


def closest_note_in_scale(note, scale):
    return min(scale, key=lambda x: abs(x - note))


def pick_next_note(prev_note, chord_tones, scale_tones, emotion):

    joy = emotion.get("joy", 0.3)
    sadness = emotion.get("sadness", 0.2)
    tension = emotion.get("tension", 0.1)

    # 75% stepwise motion, 25% leap
    if random.random() < 0.75:
        interval = random.choices(STEP_INTERVALS, STEP_WEIGHTS)[0]
    else:
        interval = random.choices(LEAP_INTERVALS, LEAP_WEIGHTS)[0]

    # Emotion bias
    if joy > sadness and interval < 0:
        interval = abs(interval)

    if sadness > joy and interval > 0:
        interval = -interval

    candidate = prev_note + interval

    # snap to scale
    candidate = closest_note_in_scale(candidate, scale_tones)

    return candidate


def generate_phrase(
    chord_tones,
    scale_tones,
    start_note,
    length,
    emotion,
    resolve=True
):

    melody = []

    prev = start_note

    for i in range(length):

        if i == 0:
            note = random.choice(chord_tones)

        elif resolve and i == length - 1:
            note = random.choice(chord_tones)

        else:
            note = pick_next_note(prev, chord_tones, scale_tones, emotion)

        melody.append(note)
        prev = note

    return melody


def generate_melody_from_chords(
    chords,
    beat_times,
    scale_tones,
    emotion,
    notes_per_beat=1
):

    melody = []

    prev_note = random.choice(scale_tones)

    for beat_idx, beat_time in enumerate(beat_times):

        chord = chords[min(beat_idx, len(chords)-1)]

        chord_tones = chord["tones"]

        phrase = generate_phrase(
            chord_tones,
            scale_tones,
            prev_note,
            length=notes_per_beat,
            emotion=emotion
        )

        melody.extend(phrase)

        prev_note = phrase[-1]

    return melody
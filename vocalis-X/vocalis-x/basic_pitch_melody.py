# basic_pitch_melody.py
# Vocalis-X melody extraction using Spotify Basic Pitch

from basic_pitch.inference import predict
import numpy as np


def extract_melody_notes(audio_path, min_duration=0.05):
    """
    Extract melody MIDI notes from audio using Spotify Basic Pitch.

    Returns list of MIDI notes aligned in time order.
    """

    print(f"🎼 Extracting melody from: {audio_path}")

    model_output, midi_data, note_events = predict(audio_path)

    notes = []

    for event in note_events:

        start_time = event[0]
        end_time   = event[1]
        midi_note  = int(event[2])
        confidence = event[3]

        duration = end_time - start_time

        if duration >= min_duration and confidence > 0.4:
            notes.append({
                "time": start_time,
                "duration": duration,
                "tone": midi_note
            })

    notes.sort(key=lambda x: x["time"])

    print(f"✅ Extracted {len(notes)} melody notes")

    return notes


def melody_to_tone_sequence(notes, total_words):

    if not notes:
        return [60] * total_words

    tones = []

    for i in range(total_words):

        idx = int(i * len(notes) / total_words)

        tones.append(notes[idx]["tone"])

    return tones
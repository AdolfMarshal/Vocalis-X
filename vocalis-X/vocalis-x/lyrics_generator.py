from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


VALID_TIME_SIGNATURES = {"3/4", "4/4", "6/8"}


@dataclass
class LyricsDraft:
    title: str
    structure: List[str]
    lyrics: str
    notes: List[str]


def _normalize_song_type(song_type: str) -> str:
    value = (song_type or "").strip()
    if not value:
        raise ValueError("song_type is required.")
    return value


def _normalize_time_signature(time_signature: str) -> str:
    value = (time_signature or "").strip()
    if value not in VALID_TIME_SIGNATURES:
        raise ValueError("time_signature must be one of 3/4, 4/4, or 6/8.")
    return value


def _normalize_description(description: str) -> str:
    value = re.sub(r"\s+", " ", (description or "").strip())
    if len(value) < 20:
        raise ValueError("description must be at least 20 characters long.")
    return value


def _extract_keywords(description: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", description.lower())
    seen = []
    stop = {
        "about",
        "after",
        "before",
        "because",
        "between",
        "through",
        "without",
        "should",
        "would",
        "could",
        "there",
        "their",
        "where",
        "which",
        "while",
        "heart",
        "music",
        "song",
        "lyrics",
    }
    for word in words:
        if word in stop or word in seen:
            continue
        seen.append(word)
        if len(seen) == 5:
            break
    return seen or ["midnight", "memory", "motion"]


def _title_case(words: List[str]) -> str:
    return " ".join(word.capitalize() for word in words[:2])


def _meter_hint(time_signature: str, bpm: int) -> str:
    if time_signature == "3/4":
        return "a swaying pulse with phrases that turn every three beats"
    if time_signature == "6/8":
        return "a rolling pulse with longer lifted endings across six eighth notes"
    if bpm >= 140:
        return "a driving four-beat pulse with short punchy lines"
    return "a steady four-beat pulse with balanced verse and chorus lines"


def _song_type_hint(song_type: str) -> str:
    lowered = song_type.lower()
    if "rap" in lowered or "hip" in lowered:
        return "lean into internal rhyme, direct imagery, and confident cadence"
    if "worship" in lowered or "gospel" in lowered:
        return "use uplifting language, communal imagery, and a singable hook"
    if "ballad" in lowered:
        return "use emotional confessional lines with a wider melodic hook"
    if "rock" in lowered:
        return "use strong physical imagery and a chorus that lands hard"
    if "folk" in lowered:
        return "use simple visual storytelling and plainspoken lines"
    if "r&b" in lowered or "soul" in lowered:
        return "use intimate phrasing and smooth repeated motifs"
    return "keep the language vivid, memorable, and easy to sing"


def generate_lyrics(song_type: str, time_signature: str, bpm: int, description: str) -> LyricsDraft:
    song_type = _normalize_song_type(song_type)
    time_signature = _normalize_time_signature(time_signature)
    description = _normalize_description(description)

    if bpm < 40 or bpm > 240:
        raise ValueError("bpm must be between 40 and 240.")

    keywords = _extract_keywords(description)
    title = _title_case(keywords)
    meter_hint = _meter_hint(time_signature, bpm)
    style_hint = _song_type_hint(song_type)
    structure = ["Verse 1", "Pre-Chorus", "Chorus", "Verse 2", "Bridge", "Chorus"]

    lead = keywords[0]
    support = keywords[1] if len(keywords) > 1 else "fire"
    image = keywords[2] if len(keywords) > 2 else "shadow"
    turn = keywords[3] if len(keywords) > 3 else "echo"
    anchor = keywords[4] if len(keywords) > 4 else "light"

    lyrics = "\n".join(
        [
            "[Verse 1]",
            f"I kept your {lead} in the back of my throat tonight",
            f"Walking on {support} while the city bent into {image}",
            f"Every small silence hit harder than it looked outside",
            f"I heard our name in the rails and the windows of {turn}",
            "",
            "[Pre-Chorus]",
            f"If this is the last time the room gives back our {anchor}",
            "Let the words come clean, let the breath stay brave",
            "",
            "[Chorus]",
            f"We are not done with the flame, not done with the {lead}",
            f"Hold me through the drop, through the dark, through the {support}",
            f"I will sing it plain till the walls give up their {anchor}",
            "If the night runs wild, we run louder",
            "",
            "[Verse 2]",
            f"I learned your rhythm from the shape of a closing door",
            f"Counted out the hurt till the floor moved under {image}",
            f"Now the air tastes sharp and honest like a storm before dawn",
            f"And the old fear breaks when I answer it with {turn}",
            "",
            "[Bridge]",
            f"Leave the doubt in the wires, leave the bruise in the blue light",
            f"Take the pulse, take the spark, take the weight off the skyline",
            "If we fall, let it sound like a promise",
            "",
            "[Chorus]",
            f"We are not done with the flame, not done with the {lead}",
            f"Hold me through the drop, through the dark, through the {support}",
            f"I will sing it plain till the walls give up their {anchor}",
            "If the night runs wild, we run louder",
        ]
    )

    notes = [
        f"Written for {song_type} lyrics with {time_signature} meter at {bpm} BPM.",
        f"Line shaping target: {meter_hint}.",
        f"Writing direction: {style_hint}.",
        f"Prompt basis: {description}",
    ]

    return LyricsDraft(
        title=title,
        structure=structure,
        lyrics=lyrics,
        notes=notes,
    )

"""
prompt_builder.py - Vocalis-X

Prompt policy:
- If the user provides a creative prompt, pass it through as-is.
- Do not inject hardcoded genre, instrumentation, mood, or quality suffixes.
- Only fall back to semantic fields when no creative prompt was supplied.
"""


def build_prompt(semantic):
    raw_prompt = (getattr(semantic, "creative_prompt", None) or "").strip()
    if raw_prompt:
        return raw_prompt

    parts = []

    music_config = getattr(semantic, "music_config", None)
    if music_config and getattr(music_config, "genre", None):
        parts.append(music_config.genre.strip())

    instrumentation = [item for item in (getattr(semantic, "instrumentation", None) or []) if item]
    if instrumentation:
        parts.append(", ".join(instrumentation))

    energy = getattr(semantic, "energy", None)
    if energy is not None:
        if energy > 0.7:
            parts.append("fast, energetic")
        elif energy < 0.3:
            parts.append("slow, calm")

    darkness = getattr(semantic, "darkness", None)
    if darkness is not None:
        if darkness > 0.7:
            parts.append("dark, intense")
        elif darkness < 0.3:
            parts.append("bright, uplifting")

    emotion = getattr(semantic, "emotion", None)
    if emotion is not None:
        if getattr(emotion, "tension", 0) > 0.6:
            parts.append("tense, dramatic")
        elif getattr(emotion, "joy", 0) > getattr(emotion, "sadness", 0):
            parts.append("uplifting, heroic")
        elif getattr(emotion, "sadness", 0) > getattr(emotion, "joy", 0):
            parts.append("melancholic")

    return ", ".join(dict.fromkeys(parts))

import json
import os
import re
from pathlib import Path
import urllib.error
import urllib.request
from typing import Optional


class LyricsLLMError(RuntimeError):
    pass


_ENV_LOADED = False


def _load_project_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value:
                os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    _load_project_env()
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return value.strip()


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise LyricsLLMError("LLM lyrics response was not valid JSON.")


def _message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    raise LyricsLLMError("LLM response content was not a string.")


def generate_lyrics_with_llm(song_type: str, time_signature: str, bpm: int, description: str) -> Optional[dict]:
    api_key = _env("OPENAI_API_KEY") or _env("LYRICS_LLM_API_KEY")
    if not api_key:
        return None

    model = _env("LYRICS_LLM_MODEL", "gpt-4o-mini")
    base_url = _env("LYRICS_LLM_BASE_URL", "https://api.openai.com/v1")
    endpoint = base_url.rstrip("/") + "/chat/completions"
    is_huggingface_router = "router.huggingface.co" in base_url

    payload = {
        "model": model,
        "temperature": 0.9,
        "max_tokens": 900,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional songwriter. Return only JSON with keys "
                    "title, structure, lyrics, notes. structure must be an array of section names. "
                    "lyrics must be complete sectioned lyrics with labels like [Verse 1]. "
                    "notes must be a short array of craft notes about meter, tone, and hook."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write complete lyrics for a {song_type} song.\n"
                    f"Time signature: {time_signature}\n"
                    f"BPM: {bpm}\n"
                    f"Description: {description}\n"
                    "Honor the meter in line length and pacing."
                ),
            },
        ],
    }
    if not is_huggingface_router:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise LyricsLLMError(f"LLM request failed with HTTP {exc.code}: {error_body}")
    except Exception as exc:
        raise LyricsLLMError(f"LLM request failed: {exc}")

    try:
        response_payload = json.loads(body)
        content = _message_content_to_text(response_payload["choices"][0]["message"]["content"])
    except Exception as exc:
        raise LyricsLLMError(f"LLM response shape was unexpected: {exc}. Body: {body[:800]}")

    result = _extract_json(content)
    if not isinstance(result.get("structure"), list) or not result.get("lyrics"):
        raise LyricsLLMError("LLM lyrics response was missing required fields.")
    return result

"""Voice-over. Groq's hosted Orpheus model by default; other providers can be added.

The hosted Orpheus model speaks English (and Arabic in a separate model). For other
languages, register another provider: a function `(text, voice) -> wav bytes`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from . import audio
from .errors import ClapperError
from .http import client
from .paths import safe

GROQ_SPEECH_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_DEFAULT_MODEL = "canopylabs/orpheus-v1-english"
GROQ_VOICES = ("autumn", "diana", "hannah", "austin", "daniel", "troy")
DEFAULT_VOICE = "autumn"
MAX_CHARS = 1500  # longer text is split at sentence ends and joined again


def explain(status: int, body: str, model: str) -> str:
    """Turn an API error into something the agent (and its user) can act on."""
    text = (body or "")[:300]
    if "model_terms_required" in text or "requires terms acceptance" in text:
        return (
            "Groq needs a one-time acceptance of the terms for this speech model. The "
            "organisation owner can do that at "
            f"https://console.groq.com/playground?model={model.replace('/', '%2F')} - "
            "after that this tool works without further changes."
        )
    if status == 401:
        return f"Groq rejects the key (HTTP 401). Is GROQ_API_KEY correct? {text}"
    if status == 403:
        return (
            "Groq refuses access (HTTP 403). Check GROQ_API_KEY and the organisation's "
            f"rights. {text}"
        )
    if status == 429:
        return f"Groq rate limit reached (HTTP 429). Try again later. {text}"
    return f"Speech synthesis failed (HTTP {status}): {text}"


def groq(text: str, voice: str) -> bytes:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        raise ClapperError("GROQ_API_KEY is not set. Get a key at https://console.groq.com.")
    model = os.getenv("GROQ_TTS_MODEL", GROQ_DEFAULT_MODEL)
    with client(300) as c:
        r = c.post(
            GROQ_SPEECH_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "input": text, "voice": voice, "response_format": "wav"},
        )
    if r.status_code != 200:
        raise ClapperError(explain(r.status_code, r.text, model))
    return r.content


PROVIDERS: dict[str, Callable[[str, str], bytes]] = {"groq": groq}


def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Sentence-aware chunks of at most `limit` characters (a longer sentence is cut)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current = ""
    for s in sentences:
        while len(s) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(s[:limit])
            s = s[limit:]
        if current and len(current) + 1 + len(s) > limit:
            chunks.append(current)
            current = s
        else:
            current = f"{current} {s}".strip()
    if current:
        chunks.append(current)
    return chunks


def voiceover(project: str, text: str, filename: str, voice: str = DEFAULT_VOICE) -> dict:
    if not text.strip():
        raise ClapperError("text is empty.")
    name = re.sub(r"[^A-Za-z0-9_-]", "-", filename.strip())[:80].strip("-")
    if not name:
        raise ClapperError("filename must contain letters or digits (no extension).")
    provider = os.getenv("CLAPPER_TTS_PROVIDER", "groq")
    if provider not in PROVIDERS:
        raise ClapperError(f"Unknown TTS provider {provider!r}. Available: {sorted(PROVIDERS)}")
    chosen = voice.strip().lower()
    if provider == "groq" and chosen not in GROQ_VOICES:
        chosen = DEFAULT_VOICE  # reported in the result, so a changed voice is visible
    parts = [PROVIDERS[provider](chunk, chosen) for chunk in split_text(text)]
    for part in parts:
        problem = audio.not_speech(part)
        if problem:
            raise ClapperError(problem)
    data = parts[0] if len(parts) == 1 else audio.stitch(parts)
    rel_path = f"public/audio/{name}.wav"
    target = safe(project, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "ok": True,
        "path": rel_path,
        "voice": chosen,
        "provider": provider,
        "characters": len(text),
        "remotion_usage": f'<Audio src={{staticFile("audio/{name}.wav")}} />',
    }

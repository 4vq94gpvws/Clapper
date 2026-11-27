"""Word-level captions for a voice-over, via Groq Whisper. Writes `<audio>.captions.json`
next to the audio file, ready for a Remotion <Captions> component."""

from __future__ import annotations

import json
import os

from .errors import ClapperError
from .http import client
from .paths import rel, safe

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def clean(whisper: dict, language: str) -> dict:
    words = [
        {
            "word": w["word"].strip(),
            "start": float(w.get("start", 0)),
            "end": float(w.get("end", 0)),
        }
        for w in whisper.get("words") or []
        if (w.get("word") or "").strip()
    ]
    return {
        "language": whisper.get("language", language or "auto"),
        "duration": whisper.get("duration", 0),
        "text": (whisper.get("text") or "").strip(),
        "words": words,
    }


def transcribe(project: str, audio_path: str, language: str = "") -> dict:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        raise ClapperError("GROQ_API_KEY is not set. Get a key at https://console.groq.com.")
    source = safe(project, audio_path, must_exist=True)
    data = source.read_bytes()
    if not data:
        raise ClapperError(f"{audio_path} is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise ClapperError(f"{audio_path} is larger than 25 MB; cut it into shorter parts.")
    fields = {
        "model": GROQ_WHISPER_MODEL,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word",
    }
    if language:
        fields["language"] = language
    with client(180) as c:
        r = c.post(
            GROQ_WHISPER_URL,
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (source.name, data, "audio/wav")},
            data=fields,
        )
    if r.status_code != 200:
        raise ClapperError(f"Groq transcription failed (HTTP {r.status_code}): {r.text[:300]}")
    result = clean(r.json(), language)
    if not result["words"]:
        raise ClapperError("Whisper returned no word-level timestamps.")
    out = source.with_suffix(".captions.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    saved = rel(project, out)
    static = saved.removeprefix("public/")
    return {
        "saved_to": saved,
        "words": len(result["words"]),
        "duration_seconds": result["duration"],
        "language": result["language"],
        "sample": result["words"][:5],
        "remotion_usage": f'<Captions src={{staticFile("{static}")}} />',
    }

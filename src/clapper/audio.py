"""WAV helpers: stitch fragments, and check that an API answer is really speech.

A TTS API can answer HTTP 200 with a hum or silence. Writing that to disk would overwrite a
good file with the same name, so we look at the samples first.
"""

from __future__ import annotations

import array
import io
import sys
import wave

WINDOW_S = 0.1
MIN_DISTINCT = 32  # a window of speech has many distinct sample values; a hum has few
MIN_LIVE_SHARE = 0.5


def wav_pcm(data: bytes) -> tuple[int, int, int, bytes] | None:
    """(channels, sample rate, bits, pcm) from a WAV, or None if it is not one.

    Walks the chunks itself: streaming APIs write 0xFFFFFFFF as the data length, which the
    stdlib `wave` module cannot read. Then everything up to the end of the file counts.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos, fmt = 12, None
    while pos + 8 <= len(data):
        name = data[pos : pos + 4]
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        start = pos + 8
        if name == b"fmt ":
            fmt = data[start : start + 16]
        elif name == b"data":
            end = len(data) if size == 0xFFFFFFFF else min(len(data), start + size)
            if fmt is None or len(fmt) < 16:
                return None
            return (
                int.from_bytes(fmt[2:4], "little"),
                int.from_bytes(fmt[4:8], "little"),
                int.from_bytes(fmt[14:16], "little"),
                data[start:end],
            )
        pos = start + size + (size & 1)
    return None


def not_speech(data: bytes) -> str | None:
    """Why this audio is not speech, or None if it looks like speech."""
    wav = wav_pcm(data or b"")
    if wav is None:
        head = (data or b"")[:80].decode("utf-8", "replace")
        return f"The API did not return a readable WAV file (starts with {head!r}); nothing saved."
    channels, rate, bits, pcm = wav
    if bits != 16 or not rate or not channels:
        return None  # only 16-bit PCM is judged on content
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    size = max(1, int(rate * channels * WINDOW_S))
    windows = [samples[i : i + size] for i in range(0, len(samples) - size + 1, size)]
    if not windows:
        return "The API returned a WAV file without audio; nothing saved."
    live = sum(1 for w in windows if len(set(w)) >= MIN_DISTINCT)
    if live / len(windows) < MIN_LIVE_SHARE:
        return (
            f"The API returned audio without speech (HTTP 200, but only {live} of "
            f"{len(windows)} windows of {WINDOW_S:g}s sound like a voice). Nothing saved. "
            "Try again later."
        )
    return None


def stitch(parts: list[bytes], pause_ms: int = 300) -> bytes:
    """Join WAV fragments with silence between them. The first readable fragment sets the
    format; a fragment that does not match it is skipped."""
    decoded = [p for p in (wav_pcm(part) for part in parts if part) if p]
    if not decoded:
        raise ValueError("none of the fragments was a readable WAV file")
    channels, rate, bits, _ = decoded[0]
    width = bits // 8
    silence = b"\x00" * int(rate * channels * width * pause_ms / 1000)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        first = True
        for ch, sr, b, pcm in decoded:
            if (ch, sr, b) != (channels, rate, bits):
                continue
            if not first:
                w.writeframes(silence)
            w.writeframes(pcm[: len(pcm) // (ch * width) * ch * width])
            first = False
    return out.getvalue()

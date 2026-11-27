import io
import math
import struct
import wave

import httpx
import pytest

from clapper import audio, tts
from clapper.errors import ClapperError


def tone(seconds=1.0, rate=16000, freq=220, streamed=False) -> bytes:
    """A voice-like WAV: a swept tone with plenty of distinct sample values."""
    n = int(seconds * rate)
    pcm = struct.pack(
        f"<{n}h",
        *(int(12000 * math.sin(2 * math.pi * (freq + i / 200) * i / rate)) for i in range(n)),
    )
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    data = bytearray(out.getvalue())
    if streamed:  # what a streaming API writes: unknown lengths
        data[4:8] = b"\xff\xff\xff\xff"
        data[data.index(b"data") + 4 : data.index(b"data") + 8] = b"\xff\xff\xff\xff"
    return bytes(data)


def silence(seconds=1.0, rate=16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return out.getvalue()


def test_speech_passes_and_silence_or_garbage_does_not():
    assert audio.not_speech(tone()) is None
    assert "without speech" in audio.not_speech(silence())
    assert "readable WAV" in audio.not_speech(b"error code: 1010")


def test_a_streamed_wav_with_unknown_length_is_read():
    parsed = audio.wav_pcm(tone(0.5, streamed=True))
    assert parsed and parsed[1] == 16000 and len(parsed[3]) == 16000  # 0.5 s of 16-bit samples
    assert audio.not_speech(tone(streamed=True)) is None


def test_stitch_joins_with_a_pause_and_skips_mismatched_formats():
    joined = audio.stitch([tone(0.5), tone(0.5), tone(0.5, rate=8000)], pause_ms=100)
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getframerate() == 16000
        assert (
            w.getnframes() == 8000 + 1600 + 8000
        )  # two parts and one pause; the 8 kHz one skipped


def test_stitch_with_nothing_readable_raises():
    with pytest.raises(ValueError):
        audio.stitch([b"nope"])


def test_split_text_keeps_sentences_whole_and_cuts_overlong_ones():
    assert tts.split_text("One. Two. Three.", limit=100) == ["One. Two. Three."]
    assert tts.split_text("One. Two. Three.", limit=9) == ["One. Two.", "Three."]
    assert tts.split_text("x" * 25, limit=10) == ["x" * 10, "x" * 10, "x" * 5]


class FakeGroq:
    """Stands in for api.groq.com; records requests."""

    def __init__(self, status=200, body=None):
        self.status, self.body, self.requests = status, body, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, content=self.body if self.body is not None else tone())


@pytest.fixture
def groq(monkeypatch):
    fake = FakeGroq()
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    real = httpx.Client
    monkeypatch.setattr(
        "clapper.http.httpx.Client",
        lambda **kw: real(transport=httpx.MockTransport(fake), **kw),
    )
    return fake


def test_voiceover_without_a_key_names_the_variable():
    with pytest.raises(ClapperError, match="GROQ_API_KEY"):
        tts.voiceover("p", "Hello there.", "intro")


def test_voiceover_saves_the_wav_and_reports_the_voice(groq, work):
    out = tts.voiceover("p", "Hello there.", "intro", voice="troy")
    assert out["path"] == "public/audio/intro.wav" and out["voice"] == "troy"
    assert (work / "p" / "public" / "audio" / "intro.wav").stat().st_size > 1000
    sent = groq.requests[0]
    assert sent.headers["user-agent"].startswith("clapper/")  # never the library default
    assert sent.headers["authorization"] == "Bearer gsk_test"


def test_an_unknown_voice_falls_back_and_says_so(groq):
    assert tts.voiceover("p", "Hi.", "a", voice="nonsense")["voice"] == "autumn"


def test_a_long_text_is_sent_in_several_requests_and_joined(groq):
    text = " ".join(f"Sentence number {i} is here." for i in range(120))
    tts.voiceover("p", text, "long")
    assert len(groq.requests) > 1


def test_a_hum_is_not_saved_over_a_good_file(groq, work):
    tts.voiceover("p", "Good take.", "take")
    good = (work / "p" / "public" / "audio" / "take.wav").read_bytes()
    groq.body = silence()
    with pytest.raises(ClapperError, match="without speech"):
        tts.voiceover("p", "Bad take.", "take")
    assert (work / "p" / "public" / "audio" / "take.wav").read_bytes() == good


@pytest.mark.parametrize(
    "status,body,expect",
    [
        (401, "no", "GROQ_API_KEY"),
        (429, "slow", "rate limit"),
        (400, '{"error":{"code":"model_terms_required"}}', "one-time acceptance"),
    ],
)
def test_api_errors_are_explained(groq, status, body, expect):
    groq.status, groq.body = status, body.encode()
    with pytest.raises(ClapperError, match=expect):
        tts.voiceover("p", "Hi.", "a")


def test_filenames_cannot_escape(groq, work):
    out = tts.voiceover("p", "Hi.", "../../evil")
    assert out["path"].startswith("public/audio/") and ".." not in out["path"]

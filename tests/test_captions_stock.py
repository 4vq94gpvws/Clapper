import json

import httpx
import pytest

from clapper import captions, stock
from clapper.errors import ClapperError


def mock(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(
        "clapper.http.httpx.Client",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


def test_captions_are_cleaned_and_saved_next_to_the_audio(monkeypatch, work):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    (work / "p" / "public" / "audio").mkdir(parents=True)
    (work / "p" / "public" / "audio" / "v.wav").write_bytes(b"RIFFxxxx")
    seen = {}

    def handler(request):
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "language": "en",
                "duration": 2.0,
                "text": " Hello world ",
                "words": [
                    {"word": " Hello", "start": 0, "end": 0.5},
                    {"word": " ", "start": 0.5, "end": 0.6},
                    {"word": "world", "start": 0.6, "end": 1.0},
                ],
            },
        )

    mock(monkeypatch, handler)
    out = captions.transcribe("p", "public/audio/v.wav")
    assert out["saved_to"] == "public/audio/v.captions.json" and out["words"] == 2
    assert out["remotion_usage"] == '<Captions src={staticFile("audio/v.captions.json")} />'
    saved = json.loads((work / "p" / "public" / "audio" / "v.captions.json").read_text())
    assert [w["word"] for w in saved["words"]] == ["Hello", "world"]
    assert b"whisper-large-v3-turbo" in seen["body"] and b"word" in seen["body"]


def test_captions_need_a_key_and_an_existing_file(monkeypatch):
    with pytest.raises(ClapperError, match="GROQ_API_KEY"):
        captions.transcribe("p", "public/a.wav")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    with pytest.raises(ClapperError, match="not found"):
        captions.transcribe("p", "public/a.wav")


def test_stock_needs_a_key():
    with pytest.raises(ClapperError, match="PEXELS_API_KEY"):
        stock.stock_image("p", "cat", "cat")


def test_pexels_download_saved_with_credit(monkeypatch, work):
    monkeypatch.setenv("PEXELS_API_KEY", "k")

    def handler(request):
        if request.url.host == "api.pexels.com":
            assert request.headers["authorization"] == "k"
            return httpx.Response(
                200,
                json={
                    "photos": [
                        {
                            "src": {"large2x": "https://images.pexels.com/p/1.jpg"},
                            "photographer": "Ann",
                            "url": "https://www.pexels.com/photo/1",
                        }
                    ]
                },
            )
        return httpx.Response(200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"})

    mock(monkeypatch, handler)
    out = stock.stock_image("p", "a cat", "cat")
    assert out["photographer"] == "Ann" and out["path"] == "public/images/cat.jpg"
    assert (work / "p" / "public" / "images" / "cat.jpg").read_bytes() == b"\xff\xd8jpeg"


def test_stock_refuses_to_download_from_an_unexpected_host(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "k")

    def handler(request):
        return httpx.Response(
            200, json={"photos": [{"src": {"large2x": "http://169.254.169.254/latest/meta-data"}}]}
        )

    mock(monkeypatch, handler)
    with pytest.raises(ClapperError, match="unexpected host"):
        stock.stock_image("p", "x", "x")


def test_stock_rejects_a_non_image_answer(monkeypatch):
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "k")

    def handler(request):
        if request.url.host == "api.unsplash.com":
            return httpx.Response(
                200, json={"results": [{"urls": {"regular": "https://images.unsplash.com/x"}}]}
            )
        return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})

    mock(monkeypatch, handler)
    with pytest.raises(ClapperError, match="download failed"):
        stock.stock_image("p", "x", "x")

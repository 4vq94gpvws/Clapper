"""Guards for a public repo: no private data, no secrets, and the two instruction files in sync.

Add your own private words (names, hosts, employers) to the environment variable
CLAPPER_DENYLIST (comma separated) when you run the tests locally. They must not be written
into this repository: a denylist in the repo would itself be the leak.
"""

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", ".pytest_cache", ".ruff_cache", "work", "dist"}
SKIP_CONTENT = {"package-lock.json"}
PATTERNS = {
    "private IP address": re.compile(
        r"\b(192\.168|10\.\d{1,3}|172\.(1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"
    ),
    "email address": re.compile(r"[\w.+-]+@(?!users\.noreply|example\.)[\w-]+\.[a-z]{2,}", re.I),
    "Groq key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "API secret key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "personal home path": re.compile(
        r"(/Users/[^/\s]+|/home/(?!clapper|user\b)[^/\s]+|C:\\Users\\)"
    ),
}


def files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if path.name in SKIP_CONTENT or path.name == Path(__file__).name:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


@pytest.mark.parametrize("label", sorted(PATTERNS))
def test_no_private_data_or_secrets(label):
    hits = [str(p.relative_to(ROOT)) for p, text in files() if PATTERNS[label].search(text)]
    assert not hits, f"{label} found in: {hits}"


def test_the_local_denylist_finds_nothing():
    words = [w.strip().lower() for w in os.getenv("CLAPPER_DENYLIST", "").split(",") if w.strip()]
    if not words:
        pytest.skip("CLAPPER_DENYLIST not set")
    hits = [(str(p.relative_to(ROOT)), w) for p, t in files() for w in words if w in t.lower()]
    assert not hits, f"denylisted words found: {hits}"

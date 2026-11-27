"""One place for outgoing HTTP: an honest User-Agent and the same error mapping everywhere.

Groq's edge rejects the default python client UA with a bare 403 ("error code: 1010")
before it even checks the key, so we always send our own.
"""

from __future__ import annotations

import httpx

from . import __version__

USER_AGENT = f"clapper/{__version__}"


def client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

"""Stock photos from Pexels or Unsplash, saved into the project's public/ folder.

Set PEXELS_API_KEY or UNSPLASH_ACCESS_KEY. The result includes the photographer and the
page URL: both services ask for credit, so put it in the video description or end card.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from .errors import ClapperError
from .http import client
from .paths import safe

ORIENTATIONS = ("landscape", "portrait", "square")
MAX_IMAGE_BYTES = 25 * 1024 * 1024
ALLOWED_HOSTS = ("images.pexels.com", "images.unsplash.com")


def _pexels(c, key: str, query: str, orientation: str) -> dict:
    r = c.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "orientation": orientation, "per_page": 1},
        headers={"Authorization": key},
    )
    if r.status_code != 200:
        raise ClapperError(f"Pexels error (HTTP {r.status_code}): {r.text[:200]}")
    photos = r.json().get("photos") or []
    if not photos:
        raise ClapperError(f"No Pexels result for {query!r}.")
    p = photos[0]
    return {
        "url": p["src"].get("large2x") or p["src"]["original"],
        "photographer": p.get("photographer", ""),
        "page": p.get("url", ""),
        "source": "pexels",
    }


def _unsplash(c, key: str, query: str, orientation: str) -> dict:
    mapped = {"square": "squarish"}.get(orientation, orientation)
    r = c.get(
        "https://api.unsplash.com/search/photos",
        params={"query": query, "orientation": mapped, "per_page": 1},
        headers={"Authorization": f"Client-ID {key}"},
    )
    if r.status_code != 200:
        raise ClapperError(f"Unsplash error (HTTP {r.status_code}): {r.text[:200]}")
    results = r.json().get("results") or []
    if not results:
        raise ClapperError(f"No Unsplash result for {query!r}.")
    p = results[0]
    return {
        "url": p["urls"]["regular"],
        "photographer": (p.get("user") or {}).get("name", ""),
        "page": (p.get("links") or {}).get("html", ""),
        "source": "unsplash",
    }


def stock_image(project: str, query: str, filename: str, orientation: str = "landscape") -> dict:
    if orientation not in ORIENTATIONS:
        raise ClapperError(f"orientation must be one of {ORIENTATIONS}.")
    name = re.sub(r"[^A-Za-z0-9_-]", "-", filename.strip())[:80].strip("-")
    if not name:
        raise ClapperError("filename must contain letters or digits (no extension).")
    pexels, unsplash = (
        os.getenv("PEXELS_API_KEY", "").strip(),
        os.getenv("UNSPLASH_ACCESS_KEY", "").strip(),
    )
    if not (pexels or unsplash):
        raise ClapperError(
            "No stock image key set. Set PEXELS_API_KEY (https://www.pexels.com/api/) "
            "or UNSPLASH_ACCESS_KEY (https://unsplash.com/developers)."
        )
    with client(60) as c:
        hit = (
            _pexels(c, pexels, query, orientation)
            if pexels
            else _unsplash(c, unsplash, query, orientation)
        )
        host = urlparse(hit["url"]).hostname or ""
        if host not in ALLOWED_HOSTS:
            raise ClapperError(f"Refusing to download from unexpected host {host!r}.")
        img = c.get(hit["url"])
    if img.status_code != 200 or not img.headers.get("content-type", "").startswith("image/"):
        raise ClapperError(f"Image download failed (HTTP {img.status_code}).")
    if len(img.content) > MAX_IMAGE_BYTES:
        raise ClapperError("The image is larger than 25 MB.")
    rel_path = f"public/images/{name}.jpg"
    target = safe(project, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(img.content)
    return {
        "ok": True,
        "path": rel_path,
        "source": hit["source"],
        "photographer": hit["photographer"],
        "page": hit["page"],
        "remotion_usage": f'<Img src={{staticFile("images/{name}.jpg")}} />',
    }

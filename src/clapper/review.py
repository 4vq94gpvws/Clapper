"""Versions of a video and review comments on its timeline.

A human watches a version and leaves comments ("0:12.4 - make the star smaller"). The agent
reads the open comments, makes the next version, and records which comments it resolved and
what changed. Only the agent knows what it changed, so it reports that itself; the server
does not diff videos.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

from .errors import ClapperError
from .paths import project_dir, safe, work_root

KINDS = ("changed", "new")
MAX_TEXT = 2000
MAX_CHANGES = 100
SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
  project TEXT NOT NULL, number INTEGER NOT NULL, file TEXT NOT NULL,
  created REAL NOT NULL, PRIMARY KEY (project, number));
CREATE TABLE IF NOT EXISTS changes (
  project TEXT NOT NULL, version INTEGER NOT NULL,
  t_from REAL NOT NULL, t_to REAL NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, at REAL NOT NULL,
  text TEXT NOT NULL, created REAL NOT NULL,
  resolved_in INTEGER);
"""


def timecode(seconds: float | None) -> str:
    """0:12.4 / 1:02:03.5 - the same form a human sees on the timeline."""
    s = max(0.0, float(seconds or 0))
    tenths = int(round(s * 10))
    h, rest = divmod(tenths, 36000)
    m, rest = divmod(rest, 600)
    sec, t = divmod(rest, 10)
    return f"{h}:{m:02d}:{sec:02d}.{t}" if h else f"{m}:{sec:02d}.{t}"


@contextmanager
def _db():
    path = work_root() / ".clapper" / "review.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_comment(project: str, at: float, text: str) -> dict:
    project_dir(project)
    text = (text or "").strip()
    if not text or len(text) > MAX_TEXT:
        raise ClapperError(f"A comment needs 1-{MAX_TEXT} characters.")
    if not 0 <= at <= 86_400:
        raise ClapperError("at is the time in seconds from the start of the video.")
    with _db() as db:
        cur = db.execute(
            "INSERT INTO comments (project, at, text, created) VALUES (?,?,?,?)",
            (project, float(at), text, time.time()),
        )
    return {"ok": True, "id": cur.lastrowid, "at": timecode(at)}


def comments(project: str, status: str = "open") -> dict:
    if status not in ("open", "resolved", "all"):
        raise ClapperError("status must be open, resolved or all.")
    where = {
        "open": "AND resolved_in IS NULL",
        "resolved": "AND resolved_in IS NOT NULL",
        "all": "",
    }
    with _db() as db:
        rows = db.execute(
            f"SELECT * FROM comments WHERE project=? {where[status]} ORDER BY at, id", (project,)
        ).fetchall()
    return {
        "project": project,
        "comments": [
            {
                "id": r["id"],
                "at": timecode(r["at"]),
                "seconds": r["at"],
                "text": r["text"],
                "resolved_in_version": r["resolved_in"],
            }
            for r in rows
        ],
    }


def _check_changes(changes: list[dict]) -> list[tuple[float, float, str, str]]:
    if len(changes) > MAX_CHANGES:
        raise ClapperError(f"At most {MAX_CHANGES} changes per version.")
    out = []
    for i, c in enumerate(changes, 1):
        try:
            start, end = float(c["from"]), float(c["to"])
            kind, text = str(c["kind"]), str(c["text"]).strip()
        except (KeyError, TypeError, ValueError) as e:
            raise ClapperError(
                f"Change {i}: use {{'from': seconds, 'to': seconds, "
                "'kind': 'changed'|'new', 'text': '...'}"
            ) from e
        if kind not in KINDS or not text or len(text) > MAX_TEXT or not 0 <= start <= end:
            raise ClapperError(
                f"Change {i} is invalid: kind must be one of {KINDS}, text 1-{MAX_TEXT} "
                "characters, and 0 <= from <= to."
            )
        out.append((start, end, kind, text))
    return out


def add_version(
    project: str, file: str, changes: list[dict] | None = None, resolved: list[int] | None = None
) -> dict:
    """Record a new version. Validates everything first, then writes in one transaction."""
    target = safe(project, file, must_exist=True)
    if target.suffix.lower() != ".mp4":
        raise ClapperError("A version is an .mp4 file.")
    parsed = _check_changes(changes or [])
    ids = sorted(set(resolved or []))
    with _db() as db:
        if ids:
            marks = ",".join("?" * len(ids))
            open_ids = {
                r["id"]
                for r in db.execute(
                    f"SELECT id FROM comments WHERE project=? AND resolved_in IS NULL "
                    f"AND id IN ({marks})",
                    (project, *ids),
                )
            }
            missing = [i for i in ids if i not in open_ids]
            if missing:
                raise ClapperError(f"Not open comments of this project: {missing}")
        number = db.execute(
            "SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE project=?", (project,)
        ).fetchone()[0]
        db.execute("INSERT INTO versions VALUES (?,?,?,?)", (project, number, file, time.time()))
        db.executemany(
            "INSERT INTO changes VALUES (?,?,?,?,?,?)",
            [(project, number, a, b, k, t) for a, b, k, t in parsed],
        )
        if ids:
            db.execute(
                f"UPDATE comments SET resolved_in=? WHERE project=? AND id IN ({marks})",
                (number, project, *ids),
            )
    return {"ok": True, "version": number, "file": file, "changes": len(parsed), "resolved": ids}


def versions(project: str) -> dict:
    with _db() as db:
        vs = db.execute(
            "SELECT * FROM versions WHERE project=? ORDER BY number", (project,)
        ).fetchall()
        out = []
        for v in vs:
            ch = db.execute(
                "SELECT * FROM changes WHERE project=? AND version=? ORDER BY t_from",
                (project, v["number"]),
            ).fetchall()
            out.append(
                {
                    "version": v["number"],
                    "file": v["file"],
                    "changes": [
                        {
                            "from": timecode(c["t_from"]),
                            "to": timecode(c["t_to"]),
                            "kind": c["kind"],
                            "text": c["text"],
                        }
                        for c in ch
                    ],
                }
            )
    return {"project": project, "versions": out}

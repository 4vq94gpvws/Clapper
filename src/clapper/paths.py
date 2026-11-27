"""Everything the server touches lives under one work directory, split per project.

Every path an agent hands us goes through `safe()`: relative only, no `..`, and the
resolved path (symlinks included) must stay inside the project directory.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import ClapperError

_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MAX_WRITE_BYTES = 5 * 1024 * 1024


def work_root() -> Path:
    return Path(os.getenv("CLAPPER_WORK", "/work")).resolve()


def project_dir(project: str, create: bool = True) -> Path:
    if not _SLUG.match(project or ""):
        raise ClapperError(
            "Invalid project name. Use lowercase letters, digits, '-' or '_' (max 64 characters)."
        )
    path = work_root() / project
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def safe(project: str, rel: str, *, must_exist: bool = False) -> Path:
    """Absolute path of `rel` inside the project, or ClapperError."""
    if not rel or rel.startswith(("/", "~")) or "\\" in rel or "\x00" in rel:
        raise ClapperError(f"Invalid path: {rel!r}. Use a path relative to the project.")
    base = project_dir(project).resolve()
    path = (base / rel).resolve()
    if path != base and base not in path.parents:
        raise ClapperError(f"Path is outside the project: {rel!r}")
    if must_exist and not path.exists():
        raise ClapperError(f"File not found in project {project!r}: {rel}")
    return path


def rel(project: str, path: Path) -> str:
    return path.resolve().relative_to(project_dir(project).resolve()).as_posix()

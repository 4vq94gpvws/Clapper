"""Plain file access inside a project, so an agent can write Remotion code or Blender
scripts even when it has no access to the container's filesystem."""

from __future__ import annotations

from .errors import ClapperError
from .paths import MAX_WRITE_BYTES, project_dir, rel, safe

_HIDDEN = {"node_modules", ".jobs"}


def write_file(project: str, path: str, content: str) -> dict:
    data = content.encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        raise ClapperError(f"File too large to write ({len(data)} bytes, max {MAX_WRITE_BYTES}).")
    target = safe(project, path)
    if target.is_dir():
        raise ClapperError(f"{path} is a directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"ok": True, "path": path, "bytes": len(data)}


def read_file(project: str, path: str, max_bytes: int = 200_000) -> dict:
    target = safe(project, path, must_exist=True)
    if not target.is_file():
        raise ClapperError(f"{path} is not a file.")
    raw = target.read_bytes()
    try:
        text = raw[:max_bytes].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ClapperError(f"{path} is a binary file ({len(raw)} bytes).") from e
    return {"path": path, "bytes": len(raw), "truncated": len(raw) > max_bytes, "content": text}


def list_files(project: str, subdir: str = "") -> dict:
    base = safe(project, subdir, must_exist=True) if subdir else project_dir(project)
    out = []
    for p in sorted(base.rglob("*")):
        parts = set(p.relative_to(base).parts)
        if parts & _HIDDEN or p.is_symlink() or not p.is_file():
            continue
        out.append({"path": rel(project, p), "bytes": p.stat().st_size})
        if len(out) >= 500:
            break
    return {"project": project, "files": out}

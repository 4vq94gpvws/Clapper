"""Render with Blender in the background.

The agent writes a Python script that builds the scene and renders it. We run it as
`blender --background --python <script> -- <output>`; the script reads its output path from
the arguments after `--`. A Python exception makes Blender exit non-zero, so a broken script
is an error instead of a silent empty render.
"""

from __future__ import annotations

import os
import re
import shutil

from . import jobs
from .errors import ClapperError
from .paths import project_dir, safe

_FRAME = re.compile(r"\bFra:(\d+)")


def binary() -> str | None:
    return os.getenv("CLAPPER_BLENDER") or shutil.which("blender")


def progress_for(frames: int | None):
    def parse(line: str) -> int | None:
        if not frames:
            return None
        m = _FRAME.search(line)
        return min(99, round(100 * int(m.group(1)) / frames)) if m else None

    return parse


def start(project: str, script: str, output: str, frames: int | None = None) -> dict:
    exe = binary()
    if not exe:
        raise ClapperError(
            "Blender is not installed here. The Docker image has it on amd64; on arm64 "
            "(Apple Silicon) it is left out. Set CLAPPER_BLENDER to use your own."
        )
    if not script.endswith(".py"):
        raise ClapperError("The script must be a .py file, e.g. 'blender/scene.py'.")
    if not (output.startswith("out/") and output.lower().endswith((".mp4", ".png", ".mkv"))):
        raise ClapperError("The output must be .mp4, .mkv or .png under out/.")
    if frames is not None and not 1 <= frames <= 100_000:
        raise ClapperError("frames must be between 1 and 100000.")
    script_path = safe(project, script, must_exist=True)
    out_path = safe(project, output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        exe,
        "--background",
        "--noaudio",
        "--python-exit-code",
        "1",
        "--python",
        str(script_path),
        "--",
        str(out_path),
    ]
    job = jobs.start(
        project,
        "blender",
        argv,
        cwd=project_dir(project),
        output=out_path,
        output_rel=output,
        progress=progress_for(frames),
    )
    return {"ok": True, "job": job, "status": "running", "output": output}

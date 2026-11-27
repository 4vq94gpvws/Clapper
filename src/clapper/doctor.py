"""One call that tells the agent (and the human) what works in this install."""

from __future__ import annotations

import os
import shutil
import subprocess

from . import __version__, blender, remotion
from .paths import work_root


def _run(argv: list[str]) -> str | None:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""


def report() -> dict:
    work = work_root()
    exe = blender.binary()
    return {
        "version": __version__,
        "work_dir": str(work),
        "work_dir_writable": work.is_dir() and os.access(work, os.W_OK),
        "ffmpeg": _run(["ffmpeg", "-version"]) if shutil.which("ffmpeg") else None,
        "node": _run([os.getenv("CLAPPER_NODE", "node"), "--version"]),
        "remotion_installed": remotion.modules_dir().is_dir(),
        "chromium": os.path.exists(remotion.chromium()),
        "blender": _run([exe, "--version"]) if exe else None,
        "gpu": _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        if shutil.which("nvidia-smi")
        else None,
        "keys": {  # only whether they are set, never their value
            "GROQ_API_KEY (voice-over, captions)": bool(os.getenv("GROQ_API_KEY")),
            "PEXELS_API_KEY or UNSPLASH_ACCESS_KEY (stock images)": bool(
                os.getenv("PEXELS_API_KEY") or os.getenv("UNSPLASH_ACCESS_KEY")
            ),
        },
    }

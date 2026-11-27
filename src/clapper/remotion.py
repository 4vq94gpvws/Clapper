"""Render a Remotion video from a React file the agent wrote.

Contract for the agent's file: it exports `GeneratedVideo` (the component) and
`GENERATED_VIDEO_DURATION` (frames at 30 fps). Each render gets its own entry file, so two
renders in one project do not trip over each other, and the code can still
`import ... from './Captions'` because it lives in `src/`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import jobs
from .errors import ClapperError
from .paths import project_dir, safe

FPS = 30
_RENDERED = re.compile(r"Rendered\s+(\d+)\s*/\s*(\d+)")
_ENCODED = re.compile(r"Encoded\s+(\d+)\s*/\s*(\d+)")


def modules_dir() -> Path:
    return Path(os.getenv("CLAPPER_RENDER_MODULES", "/opt/render/node_modules"))


def chromium() -> str:
    return os.getenv("CLAPPER_CHROMIUM", "/usr/local/bin/chromium-container")


def progress(line: str) -> int | None:
    """Rendering frames is most of the work (80%), encoding the rest."""
    if m := _RENDERED.search(line):
        done, total = int(m.group(1)), int(m.group(2))
        return round(80 * done / total) if total else None
    if m := _ENCODED.search(line):
        done, total = int(m.group(1)), int(m.group(2))
        return 80 + round(20 * done / total) if total else None
    return None


def entry_source(job_id: str, width: int, height: int) -> str:
    return (
        "import React from 'react';\n"
        "import { Composition, registerRoot } from 'remotion';\n"
        f"import {{ GeneratedVideo, GENERATED_VIDEO_DURATION }} from './.job-{job_id}';\n"
        "const Root: React.FC = () => (\n"
        '  <Composition id="GeneratedVideo" component={GeneratedVideo}\n'
        f"    durationInFrames={{GENERATED_VIDEO_DURATION}} fps={{{FPS}}}\n"
        f"    width={{{int(width)}}} height={{{int(height)}}} />\n"
        ");\n"
        "registerRoot(Root);\n"
    )


def check(project: str, code: str, output: str, width: int, height: int) -> tuple[Path, Path]:
    if not (output.startswith("out/") and output.lower().endswith(".mp4")):
        raise ClapperError("The output must be an .mp4 under out/, e.g. 'out/video-v1.mp4'.")
    if not (code.startswith("src/") and code.endswith((".tsx", ".jsx"))):
        raise ClapperError("The code must be a .tsx file under src/, e.g. 'src/Video.tsx'.")
    if not (16 <= width <= 7680 and 16 <= height <= 4320):
        raise ClapperError("Width and height must be between 16 and 7680 / 4320 pixels.")
    return safe(project, code, must_exist=True), safe(project, output)


def start(project: str, code: str, output: str, width: int = 1920, height: int = 1080) -> dict:
    source, out_path = check(project, code, output, width, height)
    modules = modules_dir()
    if not modules.is_dir():
        raise ClapperError(
            f"Remotion is not installed ({modules} is missing). Use the Docker image, "
            "or set CLAPPER_RENDER_MODULES to a node_modules with remotion installed."
        )
    root = project_dir(project)
    link = root / "node_modules"
    if not link.exists():
        link.symlink_to(modules)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    job_id = os.urandom(6).hex()
    job_code = root / "src" / f".job-{job_id}.tsx"
    entry = root / "src" / f".entry-{job_id}.tsx"
    job_code.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    entry.write_text(entry_source(job_id, width, height), encoding="utf-8")

    def cleanup() -> None:
        for p in (job_code, entry):
            p.unlink(missing_ok=True)

    argv = [
        os.getenv("CLAPPER_NODE", "node"),
        str(modules / "@remotion" / "cli" / "remotion-cli.js"),
        "render",
        f"src/.entry-{job_id}.tsx",
        "GeneratedVideo",
        output,
        f"--browser-executable={chromium()}",
        "--gl=angle",
        "--overwrite",
    ]
    job = jobs.start(
        project,
        "remotion",
        argv,
        cwd=root,
        output=out_path,
        output_rel=output,
        progress=progress,
        on_finish=cleanup,
        job_id=job_id,
    )
    return {"ok": True, "job": job, "status": "running", "output": output}

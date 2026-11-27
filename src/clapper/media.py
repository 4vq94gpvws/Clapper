"""Look at a result: probe a video and pull a frame out of it as an image the agent can see."""

from __future__ import annotations

import json
import shutil
import subprocess

from .errors import ClapperError
from .paths import rel, safe

MAX_FRAME_WIDTH = 1280
_VIDEO = (".mp4", ".mkv", ".mov", ".webm", ".png", ".jpg", ".jpeg")


def _need_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise ClapperError("ffmpeg/ffprobe are not installed here (the Docker image has them).")


def _checked(project: str, path: str):
    target = safe(project, path, must_exist=True)
    if target.suffix.lower() not in _VIDEO:
        raise ClapperError(f"{path} is not a video or image file.")
    return target


def info(project: str, path: str) -> dict:
    _need_ffmpeg()
    target = _checked(project, path)
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(target),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if out.returncode != 0:
        raise ClapperError(f"ffprobe could not read {path}: {out.stderr.strip()[:300]}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    return {
        "path": rel(project, target),
        "bytes": int(data["format"].get("size", 0)),
        "duration_seconds": float(data["format"].get("duration", 0)),
        "video": video
        and {
            "codec": video["codec_name"],
            "width": video["width"],
            "height": video["height"],
            "fps": video.get("r_frame_rate"),
        },
        "has_audio": audio is not None,
        "audio_codec": audio and audio["codec_name"],
    }


def frame_png(project: str, path: str, at: float = 0.0) -> bytes:
    """PNG bytes of the frame at `at` seconds, scaled down to at most 1280 px wide."""
    _need_ffmpeg()
    if at < 0:
        raise ClapperError("at must be 0 or more (seconds).")
    target = _checked(project, path)
    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{at:.3f}",
            "-i",
            str(target),
            "-frames:v",
            "1",
            "-vf",
            f"scale='min({MAX_FRAME_WIDTH},iw)':-2",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        capture_output=True,
        timeout=120,
    )
    if out.returncode != 0 or not out.stdout:
        raise ClapperError(
            f"No frame at {at}s of {path}. Is the time inside the video? "
            f"{out.stderr.decode(errors='replace').strip()[:200]}"
        )
    return out.stdout

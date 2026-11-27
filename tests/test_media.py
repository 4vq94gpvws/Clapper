import asyncio
import os
import shutil
import subprocess
import sys

import pytest

from clapper import media
from clapper.errors import ClapperError
from clapper.paths import safe

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


@pytest.fixture
def clip(work):
    path = safe("p", "out/c.mp4")
    path.parent.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:d=2:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=d=2",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return "out/c.mp4"


def test_info(clip):
    out = media.info("p", clip)
    assert out["video"]["width"] == 320 and out["video"]["height"] == 180
    assert out["has_audio"] and 1.9 < out["duration_seconds"] < 2.2


def test_frame_is_a_png_of_the_right_colour(clip):
    data = media.frame_png("p", clip, 1.0)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_time_past_the_end_is_an_error(clip):
    with pytest.raises(ClapperError, match="No frame"):
        media.frame_png("p", clip, 60)


def test_only_media_files_and_inside_the_project(clip, work):
    (work / "p" / "notes.txt").write_text("x")
    with pytest.raises(ClapperError, match="not a video"):
        media.info("p", "notes.txt")
    other = safe("q", "out/c.mp4")
    other.parent.mkdir(parents=True)
    other.write_bytes(b"x")
    with pytest.raises(ClapperError, match="outside"):
        media.frame_png("p", "../q/out/c.mp4")


def test_the_frame_tool_returns_an_image_through_mcp(clip, work):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "clapper.server"],
            env={**os.environ, "CLAPPER_WORK": str(work)},
        )
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            return await s.call_tool("video_frame", {"path": clip, "at": 0.5, "project": "p"})

    result = asyncio.run(go())
    assert not result.isError and result.content[0].type == "image"
    assert result.content[0].mimeType == "image/png"

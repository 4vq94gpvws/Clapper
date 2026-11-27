"""The MCP server: tool definitions and the two ways to run it.

stdio (default): the client starts the process, e.g. `docker run -i --rm <image>`.
http: `CLAPPER_TRANSPORT=http` serves streamable HTTP on CLAPPER_PORT (default 8770) and
requires CLAPPER_TOKEN; clients send `Authorization: Bearer <token>`.
"""

import hmac
import os
import sys

from mcp.server.fastmcp import FastMCP, Image
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from . import (
    __version__,
    blender,
    captions,
    doctor,
    files,
    jobs,
    media,
    remotion,
    review,
    setup,
    stock,
    tts,
)

INSTRUCTIONS = """\
Clapper makes videos. Work inside a project (default "default"); every path is relative to
it: code in src/, assets in public/, results in out/.

Typical flow: write_file src/Video.tsx -> voiceover -> captions -> stock_image ->
render_remotion -> poll render_status until done -> video_frame (look at it) -> video_version.
Blender scenes go through write_file blender/scene.py -> render_blender. Renders take minutes:
start one, then poll render_status; never wait inside one call. Call doctor first if
something does not work.
Review comments from a human are read with video_comments; resolve them in video_version.
"""

mcp = FastMCP(
    "clapper",
    instructions=INSTRUCTIONS,
    host="0.0.0.0",
    port=int(os.getenv("CLAPPER_PORT", "8770")),
)


@mcp.tool(name="doctor")
def doctor_tool() -> dict:
    """Check what works in this install: ffmpeg, Node, Remotion, Chromium, Blender, GPU, and
    which API keys are set (never their values). Call this first when something fails."""
    return doctor.report()


@mcp.tool()
def write_file(path: str, content: str, project: str = "default") -> dict:
    """Write a text file in the project (Remotion code, a Blender script, a JSON file)."""
    return files.write_file(project, path, content)


@mcp.tool()
def read_file(path: str, project: str = "default") -> dict:
    """Read a text file from the project."""
    return files.read_file(project, path)


@mcp.tool()
def list_files(subdir: str = "", project: str = "default") -> dict:
    """List the files in a project (or a folder of it): code, assets and rendered videos."""
    return files.list_files(project, subdir)


@mcp.tool()
def voiceover(text: str, filename: str, voice: str = "autumn", project: str = "default") -> dict:
    """Create a voice-over as public/audio/<filename>.wav. Needs GROQ_API_KEY. The default
    model is English; voices: autumn, diana, hannah, austin, daniel, troy. The result names
    the voice actually used."""
    return tts.voiceover(project, text, filename, voice)


@mcp.tool(name="captions")
def captions_tool(audio_path: str, language: str = "", project: str = "default") -> dict:
    """Word-level captions for an audio file, saved next to it as <name>.captions.json.
    Needs GROQ_API_KEY. language is an optional ISO 639-1 code; empty means auto-detect."""
    return captions.transcribe(project, audio_path, language)


@mcp.tool()
def stock_image(
    query: str, filename: str, orientation: str = "landscape", project: str = "default"
) -> dict:
    """Download one stock photo to public/images/<filename>.jpg. Needs PEXELS_API_KEY or
    UNSPLASH_ACCESS_KEY. The result has the photographer and page URL for credit."""
    return stock.stock_image(project, query, filename, orientation)


@mcp.tool()
def render_remotion(
    code: str, output: str, width: int = 1920, height: int = 1080, project: str = "default"
) -> dict:
    """Start a Remotion render in the background and return a job id. `code` is a .tsx file
    under src/ that exports GeneratedVideo (the component) and GENERATED_VIDEO_DURATION
    (frames at 30 fps). `output` is an .mp4 under out/. Poll render_status."""
    return remotion.start(project, code, output, width, height)


@mcp.tool()
def render_blender(
    script: str, output: str, frames: int | None = None, project: str = "default"
) -> dict:
    """Start a Blender render in the background and return a job id. `script` is a Python
    file that builds the scene and renders to the path in sys.argv after '--'. Pass the
    frame count to get a percentage. Poll render_status."""
    return blender.start(project, script, output, frames)


@mcp.tool()
def render_status(job: str, project: str = "default") -> dict:
    """Status of a render: running (with percent), done (with bytes) or error (with the end of
    the log)."""
    return jobs.status(project, job)


@mcp.tool()
def video_info(path: str, project: str = "default") -> dict:
    """Duration, resolution, codecs and audio presence of a rendered video."""
    return media.info(project, path)


@mcp.tool()
def video_frame(path: str, at: float = 0.0, project: str = "default") -> Image:
    """One frame of a video at `at` seconds, as an image you can look at. Check your render
    with this (text cut off, overlaps, empty placeholders) before telling the user it is done."""
    return Image(data=media.frame_png(project, path, at), format="png")


@mcp.tool()
def video_comment(at: float, text: str, project: str = "default") -> dict:
    """Add a review comment at a time (seconds) on the timeline of a project's video."""
    return review.add_comment(project, at, text)


@mcp.tool()
def video_comments(status: str = "open", project: str = "default") -> dict:
    """Review comments on the timeline: open, resolved or all."""
    return review.comments(project, status)


@mcp.tool()
def video_version(
    file: str,
    changes: list[dict] | None = None,
    resolved_comments: list[int] | None = None,
    project: str = "default",
) -> dict:
    """Record a new version of the video. `changes` is a list of {from, to, kind, text} (seconds;
    kind 'changed' or 'new') describing what you changed; `resolved_comments` are the ids of
    the open comments this version fixes."""
    return review.add_version(project, file, changes, resolved_comments)


@mcp.tool()
def video_versions(project: str = "default") -> dict:
    """All versions of a project's video with what changed in each."""
    return review.versions(project)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


class BearerAuth:
    """Pure ASGI middleware: every request except /healthz needs the bearer token."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/healthz":
            sent = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(sent, b"Bearer " + self.token):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


def http_app():
    token = os.getenv("CLAPPER_TOKEN", "").strip()
    if len(token) < 16:
        sys.exit(
            "CLAPPER_TOKEN must be set (at least 16 characters) for HTTP mode. "
            "Generate one with: openssl rand -hex 32"
        )
    return BearerAuth(mcp.streamable_http_app(), token)


def main() -> None:
    if "--version" in sys.argv:
        print(__version__)
        return
    if "--print-instructions" in sys.argv:
        print(setup.instructions(), end="")
        return
    if "--print-config" in sys.argv:
        rest = sys.argv[sys.argv.index("--print-config") + 1 :]
        if not rest:
            sys.exit("usage: --print-config codex|claude [--image NAME]")
        image_name = rest[rest.index("--image") + 1] if "--image" in rest[1:] else None
        print(setup.print_config(rest[0], image_name), end="")
        return
    if "--doctor" in sys.argv:  # works without an MCP client: `docker run --rm <image> --doctor`
        import json

        print(json.dumps(doctor.report(), indent=2))
        return
    transport = os.getenv("CLAPPER_TRANSPORT", "stdio").lower()
    if transport == "http":
        import uvicorn

        uvicorn.run(http_app(), host="0.0.0.0", port=mcp.settings.port, log_level="info")
    elif transport == "stdio":
        mcp.run(transport="stdio")
    else:
        sys.exit(f"Unknown CLAPPER_TRANSPORT {transport!r}; use stdio or http.")


if __name__ == "__main__":
    main()

"""The server through the real MCP protocol, not by calling the functions directly."""

import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

TOOLS = {
    "doctor",
    "video_info",
    "video_frame",
    "write_file",
    "read_file",
    "list_files",
    "voiceover",
    "captions",
    "stock_image",
    "render_remotion",
    "render_blender",
    "render_status",
    "video_comment",
    "video_comments",
    "video_version",
    "video_versions",
}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_stdio_lists_tools_and_runs_one(work):
    async def go():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "clapper.server"],
            env={**os.environ, "CLAPPER_WORK": str(work)},
        )
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            wrote = await s.call_tool("write_file", {"path": "src/a.tsx", "content": "x"})
            bad = await s.call_tool("read_file", {"path": "../etc/passwd"})
            return names, wrote, bad

    names, wrote, bad = asyncio.run(go())
    assert names == TOOLS
    assert not wrote.isError and (work / "default" / "src" / "a.tsx").read_text() == "x"
    message = bad.content[0].text.lower()
    assert bad.isError and ("outside" in message or "invalid" in message)


@pytest.fixture
def http_server(work):
    port = free_port()
    env = {
        **os.environ,
        "CLAPPER_WORK": str(work),
        "CLAPPER_TRANSPORT": "http",
        "CLAPPER_PORT": str(port),
        "CLAPPER_TOKEN": "t" * 32,
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "clapper.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise AssertionError("server did not start")
    yield port
    proc.terminate()
    proc.wait(5)


def test_http_requires_the_token(http_server):
    url = f"http://127.0.0.1:{http_server}/mcp"
    assert httpx.post(url, json={}).status_code == 401
    assert httpx.post(url, json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert httpx.get(f"http://127.0.0.1:{http_server}/healthz").status_code == 200


def test_http_with_the_token_lists_tools(http_server):
    async def go():
        url = f"http://127.0.0.1:{http_server}/mcp"
        async with streamablehttp_client(url, headers={"Authorization": "Bearer " + "t" * 32}) as (
            r,
            w,
            _,
        ):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return {t.name for t in (await s.list_tools()).tools}

    assert asyncio.run(go()) == TOOLS


def test_http_refuses_to_start_without_a_token(work):
    env = {**os.environ, "CLAPPER_WORK": str(work), "CLAPPER_TRANSPORT": "http"}
    env.pop("CLAPPER_TOKEN", None)
    out = subprocess.run(
        [sys.executable, "-m", "clapper.server"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode != 0 and "CLAPPER_TOKEN" in out.stderr

"""Print ready-made client configuration, so nobody has to copy snippets by hand:

docker run --rm <image> --print-config codex  >> ~/.codex/config.toml
docker run --rm <image> --print-config claude        # an .mcp.json for Claude Code
docker run --rm <image> --print-instructions > AGENTS.md
"""

from __future__ import annotations

import json
import os
from importlib import resources

DEFAULT_IMAGE = "ghcr.io/OWNER/clapper:latest"
KEYS = ("GROQ_API_KEY", "PEXELS_API_KEY", "UNSPLASH_ACCESS_KEY")
DOCKER_ARGS = [
    "run",
    "-i",
    "--rm",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "-v",
    "clapper-work:/work",
]


def image() -> str:
    return os.getenv("CLAPPER_IMAGE", DEFAULT_IMAGE)


def args(image_name: str) -> list[str]:
    out = list(DOCKER_ARGS)
    for key in KEYS:
        out += ["-e", key]
    return [*out, image_name]


def codex_toml(image_name: str) -> str:
    quoted = ", ".join(json.dumps(a) for a in args(image_name))
    keys = ", ".join(json.dumps(k) for k in KEYS)
    return (
        "# clapper (added by --print-config codex)\n"
        "[mcp_servers.clapper]\n"
        'command = "docker"\n'
        f"args = [{quoted}]\n"
        "# Codex starts MCP servers with a minimal environment: list the keys it may pass on.\n"
        f"env_vars = [{keys}]\n"
        "# Run `docker pull` once first; the image is large and the first start is slow.\n"
        "startup_timeout_sec = 120\n"
        "tool_timeout_sec = 600\n"
    )


def claude_json(image_name: str) -> str:
    cfg = {"mcpServers": {"clapper": {"command": "docker", "args": args(image_name)}}}
    return json.dumps(cfg, indent=2) + "\n"


def instructions() -> str:
    return resources.files("clapper").joinpath("instructions.md").read_text(encoding="utf-8")


def print_config(kind: str, image_name: str | None = None) -> str:
    name = image_name or image()
    if kind == "codex":
        return codex_toml(name)
    if kind == "claude":
        return claude_json(name)
    raise SystemExit(f"Unknown client {kind!r}; use codex or claude.")

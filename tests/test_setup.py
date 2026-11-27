import json
import subprocess
import sys
import tomllib
from pathlib import Path

from clapper import setup

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    out = subprocess.run(
        [sys.executable, "-m", "clapper.server", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_codex_config_is_valid_toml_with_the_keys_codex_reads():
    cfg = tomllib.loads(run("--print-config", "codex", "--image", "ghcr.io/example/f:1"))
    server = cfg["mcp_servers"]["clapper"]
    assert server["command"] == "docker"
    assert server["args"][-1] == "ghcr.io/example/f:1"
    assert server["args"][:3] == ["run", "-i", "--rm"]
    # every key forwarded into the container must also be allowed through Codex's env filter
    forwarded = [a for i, a in enumerate(server["args"]) if i and server["args"][i - 1] == "-e"]
    assert set(forwarded) == set(server["env_vars"]) == set(setup.KEYS)
    assert server["startup_timeout_sec"] >= 60 and server["tool_timeout_sec"] >= 300


def test_claude_config_is_valid_json():
    cfg = json.loads(run("--print-config", "claude"))
    assert cfg["mcpServers"]["clapper"]["command"] == "docker"


def test_the_image_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLAPPER_IMAGE", "ghcr.io/me/x:2")
    assert setup.print_config("codex").count("ghcr.io/me/x:2") == 1


def test_no_secret_value_ever_appears_in_printed_config(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_super_secret_value_12345")
    assert "gsk_super_secret_value_12345" not in setup.print_config("codex")


def test_the_three_copies_of_the_instructions_agree():
    body = setup.instructions()
    assert run("--print-instructions") == body
    skill = (
        (ROOT / "skills/clapper/SKILL.md")
        .read_text(encoding="utf-8")
        .split("---\n", 2)[2]
        .lstrip("\n")
    )
    assert skill == body
    assert (ROOT / "AGENTS.md").read_text(encoding="utf-8").startswith(body)

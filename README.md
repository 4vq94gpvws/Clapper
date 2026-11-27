# clapper

An [MCP](https://modelcontextprotocol.io) server that lets an AI agent make videos. It works
with any MCP client (built for Codex first; also Claude Code, Cursor, ...) and ships as one Docker image, so
there is nothing to install besides Docker.

- **Render** with Remotion (React -> mp4) or Blender (3D, with optional GPU), as background
  jobs the agent polls.
- **Voice-over and captions** (Groq: Orpheus for speech, Whisper for word-level timestamps).
- **Stock photos** (Pexels or Unsplash) with the credit line you must show.
- **Look at the result**: `video_info` and `video_frame` give the agent a frame it can
  actually see before it tells you the video is done.
- **Versions and review comments**: leave comments on the timeline, the agent makes the next
  version, resolves them and records what changed. Stored in a SQLite file in your volume.
- **Sandboxed**: the code the agent writes (React, Blender Python) runs inside the container
  and only sees the `/work` volume.

## Quick start

You need Docker, and an API key for whatever you want to use (all optional, see
[Keys](#keys)). The model that drives the agent comes from your MCP client; this server does
not call any LLM.

### 1. Codex

```bash
docker pull ghcr.io/4vq94gpvws/clapper:latest        # once; the image is large
docker run --rm ghcr.io/4vq94gpvws/clapper:latest --print-config codex >> ~/.codex/config.toml
export GROQ_API_KEY=...                               # whichever keys you want, see Keys
```

Restart Codex; the `clapper` tools are there (`codex mcp list` shows the server). The
`--print-config` command writes the exact `[mcp_servers.clapper]` block, including
`env_vars`: Codex starts MCP servers with a minimal environment and only passes on the
variables listed there, so without that line your API keys would not reach the container.

Give Codex the working instructions by putting them in the folder you work in:

```bash
docker run --rm ghcr.io/4vq94gpvws/clapper:latest --print-instructions >> AGENTS.md
```

(or `~/.codex/AGENTS.md` for all projects). Then ask: *"Make a 20 second explainer video about
how a bike dynamo works, with a voice-over and captions."* If something does not work, ask
Codex to call the `doctor` tool, or run `docker run --rm <image> --doctor` yourself.

### Other clients (stdio)

The client starts the container itself. For Claude Code,
`docker run --rm <image> --print-config claude` prints the `.mcp.json`; any other client
that can launch a command takes the same `docker run -i --rm ... <image>` line (see
[`examples/`](examples/)). Rendered videos live in the `clapper-work` volume. To keep them in
a normal folder instead, replace it with `-v /absolute/path/to/work:/work` and add
`--user <uid>:<gid>` (your own ids; `id -u`, `id -g`).

### 2. Or run it as a service (HTTP)

```bash
cp .env.example .env          # set CLAPPER_TOKEN: openssl rand -hex 32
docker compose up -d          # endpoint: http://127.0.0.1:8770/mcp
```

Clients send `Authorization: Bearer <CLAPPER_TOKEN>`. The server refuses to start in HTTP
mode without a token. It listens on loopback only; put a TLS proxy in front of it to expose
it ([`examples/http-client.md`](examples/http-client.md)).

### Instructions for the agent

[`AGENTS.md`](AGENTS.md) (for Codex and other tools that read it) and
[`skills/clapper/SKILL.md`](skills/clapper/SKILL.md) (Claude Code skill; the repo is also
a Claude Code plugin) hold the same working instructions: plan, assets, render, look, version.
The server also sends a short version of them to every client as its MCP instructions.

Then ask your agent: *"Make a 20 second explainer video about how a bike dynamo works, with a
voice-over and captions."* Call the `doctor` tool first if something does not work.

## Keys

| Variable | Used for | Without it |
|---|---|---|
| `GROQ_API_KEY` | `voiceover`, `captions` | those two tools say which key to set |
| `PEXELS_API_KEY` or `UNSPLASH_ACCESS_KEY` | `stock_image` | that tool says which key to set |
| `CLAPPER_TOKEN` | HTTP mode only | the server will not start |

Everything else (Remotion and Blender renders, frames, versions) needs no key. Keys are only
read from the environment; they are never written to disk or returned by a tool (`doctor`
reports only whether they are set).

The default speech model is English-only. Other languages need another provider: register a
function in `tts.PROVIDERS` and select it with `CLAPPER_TTS_PROVIDER`.

## Tools

| Tool | What it does |
|---|---|
| `doctor` | What works here: ffmpeg, Node, Remotion, Chromium, Blender, GPU, which keys are set |
| `write_file`, `read_file`, `list_files` | Files inside a project |
| `voiceover`, `captions`, `stock_image` | Assets into `public/` |
| `render_remotion`, `render_blender`, `render_status` | Background renders and their progress |
| `video_info`, `video_frame` | Inspect a result; a frame as an image |
| `video_comment`, `video_comments`, `video_version`, `video_versions` | Timeline review and versions |

## GPU

Blender renders on the CPU by default. With an NVIDIA GPU and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/),
add `--gpus all` to `docker run` (or use `docker-compose.gpu.yml`) and have the Blender script
select the Cycles CUDA device. Check that it is really used: a missing driver makes Blender
fall back to the CPU without an error. Docker on macOS has no GPU access.

## Security model

- The container is the sandbox: render code can only see `/work`. The compose file drops all
  capabilities and sets `no-new-privileges`. Chromium runs with its own sandbox off, because
  the container provides the isolation.
- All agent-supplied paths are confined to their project directory (symlinks included).
- The tools have network access (they must reach Groq and Pexels), and so does the code the
  agent writes. There is no egress filter. If that matters to you, run the container on a
  network with one.
- HTTP mode needs a bearer token and binds to loopback in the compose file.

See [`SECURITY.md`](SECURITY.md) to report a problem.

## Platforms

`linux/amd64` has everything. On `linux/arm64` (Apple Silicon, Raspberry Pi) the image has no
Blender, because blender.org publishes no Linux arm64 build; Remotion works, and
`render_blender` says so.

## Status

Verified in CI and by hand: the Python tools and their tests, the MCP protocol over stdio and
HTTP (including the token), a real Remotion render (video, audio, captions) with Chromium,
and that the Codex CLI (0.172.0) accepts the configuration printed by `--print-config codex`.

**Not yet verified:** building the Docker image, Blender inside it, Codex actually launching the
container and passing the API keys on (`env_vars`), and the live Groq, Pexels and Unsplash APIs
(the tests use fakes that mimic the response shapes). Treat the first release as a preview and
please report what breaks.

## Licenses

The code in this repository is [MIT](LICENSE) licensed. That does not change the terms of the
things it uses, listed below.

**Remotion has its own license.** It is free for individuals, for-profit organizations of up
to 3 employees, and non-profits; larger for-profit organizations need a company license from
Remotion. Read it at <https://www.remotion.dev/docs/license> before using this. Blender is
GPL and is downloaded when you build the image, not stored in this repository. Groq, Pexels
and Unsplash have their own terms of use. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

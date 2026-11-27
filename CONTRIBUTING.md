# Contributing

Thanks for helping. Bug reports, fixes, new tools and docs are all welcome.

## Set up

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests && ruff format --check src tests
pytest -q
```

Tests need no API keys and no Docker: network calls are replaced by fakes, and renders use stub
CLIs. If you have ffmpeg installed, the media tests run too.

## Pull requests

- One change per PR, with a test that fails without it. Fix first, then prove it.
- Keep the tools' behaviour honest: an error should say what to do, and a tool must never claim
  success it has not checked (an empty output file is an error, not a result).
- Never put secrets, personal paths, hostnames or e-mail addresses in the repo.
  `tests/test_repo_hygiene.py` checks the common shapes. To also check your own private words,
  run the tests with `CLAPPER_DENYLIST="yourname,yourhost"`; do not commit that list.
- Agent instructions live in `src/clapper/instructions.md`. `AGENTS.md` and
  `skills/clapper/SKILL.md` are copies; a test fails when they drift apart.
- Adding a dependency, a Docker base image change, or a new network call? Say why in the PR.

## Adding a tool

1. Put the logic in its own module under `src/clapper/` (plain functions, raise
   `ClapperError` with an actionable message).
2. Register it in `server.py` with a docstring the agent can use.
3. Add the tool name to `TOOLS` in `tests/test_protocol.py`, and tests for the module.
4. Mention it in the README tool table.

## Reporting security problems

See [`SECURITY.md`](SECURITY.md). Do not open a public issue for those.

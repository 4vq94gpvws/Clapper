"""Background jobs for long renders.

A render can take many minutes, longer than an agent should wait on one tool call. `start`
returns a job id at once; the agent polls `status`. The state lives in
`<project>/.jobs/<id>.json`, so it survives a read by another process. A job whose process
is gone (container restarted) is reported as an error rather than as running forever.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

from .errors import ClapperError
from .paths import project_dir

JOB_ID = re.compile(r"^[0-9a-f]{12}$")
TAIL_LINES = 40
TAIL_CHARS = 1500
_LIVE: dict[str, subprocess.Popen] = {}
_LOCK = threading.Lock()


def timeout_s() -> int:
    try:
        return max(60, int(os.getenv("CLAPPER_RENDER_TIMEOUT", "3600")))
    except ValueError:
        return 3600


def _state_path(project: str, job: str) -> Path:
    return project_dir(project) / ".jobs" / f"{job}.json"


def _write(project: str, job: str, state: dict) -> None:
    folder = _state_path(project, job).parent
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{job}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, _state_path(project, job))


def start(
    project: str,
    kind: str,
    argv: Sequence[str],
    *,
    cwd: Path,
    output: Path,
    output_rel: str,
    progress: Callable[[str], int | None] | None = None,
    env: dict[str, str] | None = None,
    on_finish: Callable[[], None] | None = None,
    job_id: str | None = None,
) -> str:
    job = job_id or uuid.uuid4().hex[:12]
    state = {
        "job": job,
        "kind": kind,
        "status": "running",
        "percent": 0,
        "output": output_rel,
        "started": time.time(),
    }
    _write(project, job, state)
    thread = threading.Thread(
        target=_run,
        args=(project, job, list(argv), cwd, output, progress, env, on_finish, state),
        daemon=True,
    )
    thread.start()
    return job


def _cleanup(on_finish: Callable[[], None] | None) -> None:
    if on_finish:
        try:
            on_finish()
        except OSError:
            pass  # a leftover temp file must not turn a finished render into an error


def _run(project, job, argv, cwd, output, progress, env, on_finish, state) -> None:
    log: list[str] = []
    started = time.time()
    last_write = 0.0
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
            start_new_session=True,  # own process group, so a timeout also stops Chromium
        )
    except OSError as e:
        state.update(status="error", error=f"could not start {argv[0]}: {e}")
        _cleanup(on_finish)
        _write(project, job, state)
        return
    with _LOCK:
        _LIVE[job] = proc
    state["pid"] = proc.pid
    _write(project, job, state)

    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass

    timer = threading.Timer(timeout_s(), _kill)
    timer.daemon = True
    timer.start()
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            if not line:
                continue
            log.append(line)
            del log[:-TAIL_LINES]
            pct = progress(line) if progress else None
            if pct is not None and time.time() - last_write > 1.0:
                state["percent"] = pct
                _write(project, job, state)
                last_write = time.time()
        code = proc.wait()
    finally:
        timer.cancel()
        with _LOCK:
            _LIVE.pop(job, None)
    tail = "\n".join(log)[-TAIL_CHARS:]
    if timed_out.is_set():
        state.update(status="error", error=f"render exceeded {timeout_s() // 60} minutes")
    elif code != 0 or not output.is_file() or output.stat().st_size == 0:
        state.update(status="error", error=tail or f"process exited with code {code}")
    else:
        state.update(status="done", percent=100, bytes=output.stat().st_size)
    state["seconds"] = int(time.time() - started)
    if state["status"] == "error":
        state["log_tail"] = tail
    # Clean up first, then announce the result: whoever sees "done" can rely on the temp
    # files being gone.
    _cleanup(on_finish)
    _write(project, job, state)


def status(project: str, job: str) -> dict:
    if not JOB_ID.match(job or ""):
        raise ClapperError("Invalid job id.")
    try:
        state = json.loads(_state_path(project, job).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ClapperError(f"No job {job} in project {project!r}.") from e
    with _LOCK:
        alive = job in _LIVE
    if state.get("status") == "running" and not alive and time.time() - state["started"] > 5:
        state.update(
            status="error", error="the render stopped without a result (server restarted?)"
        )
    return state

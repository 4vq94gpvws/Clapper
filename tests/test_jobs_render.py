import sys
import time

import pytest

from clapper import blender, files, jobs, remotion
from clapper.errors import ClapperError
from clapper.paths import project_dir


def wait(project, job, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        state = jobs.status(project, job)
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def run(code, output="out/x.mp4", progress=None, project="p"):
    root = project_dir(project)
    (root / "out").mkdir(exist_ok=True)
    return jobs.start(
        project,
        "test",
        [sys.executable, "-c", code],
        cwd=root,
        output=root / output,
        output_rel=output,
        progress=progress,
    )


def test_a_job_that_writes_its_output_is_done():
    job = run("open('out/x.mp4','wb').write(b'1234')")
    state = wait("p", job)
    assert state["status"] == "done" and state["bytes"] == 4 and state["percent"] == 100


def test_a_failing_process_reports_the_end_of_its_log():
    state = wait("p", run("print('boom happened'); raise SystemExit(3)"))
    assert state["status"] == "error" and "boom happened" in state["error"]


def test_exit_zero_without_output_is_still_an_error():
    state = wait("p", run("print('quiet')"))
    assert state["status"] == "error"


def test_progress_lines_update_the_percentage():
    code = (
        "import time\nprint('Rendered 5/10', flush=True)\ntime.sleep(1.3)\n"
        "print('Rendered 6/10', flush=True)\nopen('out/x.mp4','wb').write(b'x')"
    )
    job = run(code, progress=remotion.progress)
    time.sleep(0.8)
    assert jobs.status("p", job)["percent"] == 40
    assert wait("p", job)["status"] == "done"


def test_a_timeout_kills_the_job(monkeypatch):
    monkeypatch.setattr(jobs, "timeout_s", lambda: 1)
    state = wait("p", run("import time; time.sleep(30)"))
    assert state["status"] == "error" and "exceeded" in state["error"]


def test_a_job_without_a_live_process_is_not_reported_running_forever(work):
    job = "abcdef123456"
    jobs._write("p", job, {"job": job, "status": "running", "started": time.time() - 60})
    assert jobs.status("p", job)["status"] == "error"


def test_bad_job_ids_are_refused():
    for bad in ("../x", "short", ""):
        with pytest.raises(ClapperError):
            jobs.status("p", bad)


def test_remotion_progress_weights_rendering_and_encoding():
    assert remotion.progress("Rendered 10/20") == 40
    assert remotion.progress("Encoded 10/20") == 90
    assert remotion.progress("nothing") is None


def test_remotion_input_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAPPER_RENDER_MODULES", str(tmp_path / "missing"))
    files.write_file("p", "src/V.tsx", "x")
    with pytest.raises(ClapperError, match=r"\.mp4"):
        remotion.start("p", "src/V.tsx", "out/v.mov")
    with pytest.raises(ClapperError, match="src/"):
        remotion.start("p", "V.tsx", "out/v.mp4")
    with pytest.raises(ClapperError, match="not found"):
        remotion.start("p", "src/Nope.tsx", "out/v.mp4")
    with pytest.raises(ClapperError, match="not installed"):
        remotion.start("p", "src/V.tsx", "out/v.mp4")


def test_remotion_renders_through_a_stub_cli(tmp_path, monkeypatch, work):
    """The real CLI is only in the Docker image; here a stub plays its part to check the
    wiring: entry file, job copy, argv, cleanup and the finished output."""
    modules = tmp_path / "node_modules"
    cli = modules / "@remotion" / "cli"
    cli.mkdir(parents=True)
    (cli / "remotion-cli.js").write_text(
        "const fs=require('fs');const a=process.argv;"
        "const entry=fs.readFileSync(a[3],'utf8');"
        "if(!entry.includes('GENERATED_VIDEO_DURATION'))process.exit(2);"
        "console.log('Rendered 1/1');fs.mkdirSync('out',{recursive:true});"
        "fs.writeFileSync(a[5],'mp4');"
    )
    monkeypatch.setenv("CLAPPER_RENDER_MODULES", str(modules))
    files.write_file("p", "src/V.tsx", "export const GeneratedVideo=()=>null;")
    started = remotion.start("p", "src/V.tsx", "out/v.mp4", 1280, 720)
    state = wait("p", started["job"])
    assert state["status"] == "done", state
    assert (work / "p" / "out" / "v.mp4").read_text() == "mp4"
    assert not list((work / "p" / "src").glob(".entry-*")) and not list(
        (work / "p" / "src").glob(".job-*")
    )


def test_blender_without_a_binary_explains_itself(monkeypatch):
    monkeypatch.delenv("CLAPPER_BLENDER", raising=False)
    monkeypatch.setattr(blender.shutil, "which", lambda _: None)
    with pytest.raises(ClapperError, match="Blender is not installed"):
        blender.start("p", "blender/scene.py", "out/a.mp4")


def test_blender_runs_a_script_with_the_output_after_the_dashes(tmp_path, monkeypatch, work):
    stub = tmp_path / "blender"
    stub.write_text(
        "#!/bin/sh\n"
        'while [ "$1" != "--" ]; do shift; done; shift\n'
        'echo "Fra:5 Mem:1M"; printf x > "$1"\n'
    )
    stub.chmod(0o755)
    monkeypatch.setenv("CLAPPER_BLENDER", str(stub))
    files.write_file("p", "blender/scene.py", "import bpy")
    started = blender.start("p", "blender/scene.py", "out/a.mp4", frames=10)
    assert wait("p", started["job"])["status"] == "done"
    assert (work / "p" / "out" / "a.mp4").read_text() == "x"


def test_cleanup_runs_before_a_job_is_reported_finished():
    """A finished job must not leave temp files behind: when the status says done or error,
    the cleanup has already run. (CI caught the reverse order as a flaky test.)"""
    seen = {}
    root = project_dir("p")
    (root / "out").mkdir(exist_ok=True)

    def cleanup():
        seen["status_during_cleanup"] = jobs.status("p", job_id)["status"]

    job_id = "abcdef012345"
    jobs.start(
        "p",
        "test",
        [sys.executable, "-c", "open('out/x.mp4','wb').write(b'1')"],
        cwd=root,
        output=root / "out" / "x.mp4",
        output_rel="out/x.mp4",
        on_finish=cleanup,
        job_id=job_id,
    )
    assert wait("p", job_id)["status"] == "done"
    assert seen["status_during_cleanup"] == "running"

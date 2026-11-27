import json
import subprocess
import sys


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "clapper.server", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_version():
    assert run("--version").stdout.strip().count(".") == 2


def test_doctor_reports_without_leaking_key_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_super_secret_value")
    out = subprocess.run(
        [sys.executable, "-m", "clapper.server", "--doctor"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "gsk_super_secret_value" not in out.stdout
    report = json.loads(out.stdout)
    assert report["keys"]["GROQ_API_KEY (voice-over, captions)"] is True

import pytest

from clapper import files
from clapper.errors import ClapperError
from clapper.paths import safe


@pytest.mark.parametrize("bad", ["../x", "/etc/passwd", "a/../../x", "~/x", "a\\b", "", "x\x00y"])
def test_paths_outside_the_project_are_refused(bad):
    with pytest.raises(ClapperError):
        safe("p", bad)


@pytest.mark.parametrize("bad", ["Up", "a b", "../x", "", "a" * 65, "-x"])
def test_bad_project_names_are_refused(bad):
    with pytest.raises(ClapperError):
        safe(bad, "src/x.tsx")


def test_a_symlink_cannot_lead_out_of_the_project(work, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    files.write_file("p", "src/a.tsx", "x")
    (work / "p" / "src" / "link").symlink_to(outside)
    with pytest.raises(ClapperError):
        files.read_file("p", "src/link")


def test_write_read_list_roundtrip():
    files.write_file("p", "src/Video.tsx", "export const a = 1;")
    assert files.read_file("p", "src/Video.tsx")["content"] == "export const a = 1;"
    assert [f["path"] for f in files.list_files("p")["files"]] == ["src/Video.tsx"]


def test_list_hides_node_modules_and_job_state(work):
    files.write_file("p", "src/a.tsx", "x")
    (work / "p" / "node_modules").mkdir()
    (work / "p" / "node_modules" / "big.js").write_text("x")
    (work / "p" / ".jobs").mkdir()
    (work / "p" / ".jobs" / "j.json").write_text("{}")
    assert [f["path"] for f in files.list_files("p")["files"]] == ["src/a.tsx"]


def test_oversized_write_is_refused():
    with pytest.raises(ClapperError):
        files.write_file("p", "big.txt", "x" * (5 * 1024 * 1024 + 1))

import pytest

from clapper import files, review
from clapper.errors import ClapperError


def mp4(project="p", name="out/v1.mp4"):
    files.write_file(project, name, "not really a video")  # content is not inspected


def test_timecode():
    assert review.timecode(12.4) == "0:12.4"
    assert review.timecode(0) == "0:00.0"
    assert review.timecode(3723.46) == "1:02:03.5"
    assert review.timecode(None) == "0:00.0"


def test_a_round_resolves_comments_and_numbers_versions():
    mp4()
    a = review.add_comment("p", 12.4, "make the star smaller")["id"]
    b = review.add_comment("p", 40, "lamp should pulse")["id"]
    assert [c["id"] for c in review.comments("p")["comments"]] == [a, b]

    v1 = review.add_version("p", "out/v1.mp4")
    assert v1["version"] == 1
    mp4(name="out/v2.mp4")
    v2 = review.add_version(
        "p",
        "out/v2.mp4",
        changes=[{"from": 12, "to": 15.5, "kind": "changed", "text": "star smaller"}],
        resolved=[a],
    )
    assert v2["version"] == 2
    assert [c["id"] for c in review.comments("p")["comments"]] == [b]
    assert review.comments("p", "resolved")["comments"][0]["resolved_in_version"] == 2
    listed = review.versions("p")["versions"]
    assert listed[1]["changes"][0] == {
        "from": "0:12.0",
        "to": "0:15.5",
        "kind": "changed",
        "text": "star smaller",
    }


def test_a_bad_resolved_id_writes_nothing():
    mp4()
    review.add_comment("p", 1, "x")
    with pytest.raises(ClapperError):
        review.add_version("p", "out/v1.mp4", resolved=[999])
    assert review.versions("p")["versions"] == []
    assert len(review.comments("p")["comments"]) == 1


def test_comments_of_another_project_cannot_be_resolved():
    mp4("a")
    mp4("b")
    other = review.add_comment("b", 1, "x")["id"]
    with pytest.raises(ClapperError):
        review.add_version("a", "out/v1.mp4", resolved=[other])


@pytest.mark.parametrize(
    "change",
    [
        {"from": 5, "to": 2, "kind": "changed", "text": "x"},
        {"from": 0, "to": 1, "kind": "deleted", "text": "x"},
        {"from": 0, "to": 1, "kind": "new", "text": " "},
        {"from": 0, "to": 1},
    ],
)
def test_invalid_changes_are_refused(change):
    mp4()
    with pytest.raises(ClapperError):
        review.add_version("p", "out/v1.mp4", changes=[change])


def test_a_version_must_be_an_existing_mp4():
    with pytest.raises(ClapperError):
        review.add_version("p", "out/missing.mp4")
    files.write_file("p", "out/a.txt", "x")
    with pytest.raises(ClapperError):
        review.add_version("p", "out/a.txt")

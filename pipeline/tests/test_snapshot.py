import json
from datetime import date
from urllib.error import HTTPError

import pytest

from schedule_pipeline import build, snapshot

PAGE = "https://www.example.lt/atlieku-grafikai"
FILES = [("https://www.example.lt/uploads/a.pdf", b"a"), ("https://www.example.lt/f/b.pdf", b"b")]


def test_snapshots_load():
    registry, taken = snapshot.load_registry()
    points, taken_points = snapshot.load_points()
    assert len(registry.settlements) > 1000
    assert len(points) > 50_000
    assert taken == taken_points
    durpiu = [p for p in points if p.settlement == 10937 and p.street == 1559497]
    assert durpiu and 54.7 < durpiu[0].lat < 54.9


def test_falls_back_to_snapshot_when_blocked():
    def blocked():
        raise HTTPError("https://get.data.gov.lt", 500, "Internal Server Error", {}, None)

    data, note = build.live_or_snapshot(
        "Address Register", blocked, lambda: ("snapshot", "2026-10-11")
    )
    assert data == "snapshot"
    assert "live source unavailable" in note and "2026-10-11" in note


def test_old_snapshot_asks_for_refresh(monkeypatch):
    def blocked():
        raise TimeoutError("timed out")

    class Later(date):
        @classmethod
        def today(cls):
            return date(2027, 1, 1)

    monkeypatch.setattr(build, "date", Later)
    _, note = build.live_or_snapshot("Address points", blocked, lambda: ([], "2026-10-11"))
    assert note.endswith(
        "please refresh it: cd pipeline && uv run python -m schedule_pipeline.snapshot --register"
    )


def saved(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def test_a_copy_whose_files_did_not_change_is_left_as_it_is(tmp_path):
    copy = tmp_path / "copy"
    assert snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", FILES, date(2026, 11, 1))
    before = saved(copy)
    assert sorted(before) == ["a.pdf", "b.pdf", "copy.json", "page.html"]
    # New markup and the same files, in another order: nothing is written, not even takenAt,
    # so the daily refresh has nothing to commit.
    files = list(reversed(FILES))
    assert not snapshot.save_site_copy(copy, PAGE, b"<p>new</p>", files, date(2026, 11, 22))
    assert saved(copy) == before
    assert json.loads(before["copy.json"])["takenAt"] == "2026-11-01"


@pytest.mark.parametrize(
    ("page", "files"),
    [
        (PAGE, [FILES[0], ("https://www.example.lt/f/b.pdf", b"b, corrected")]),
        (PAGE, [*FILES, ("https://www.example.lt/f/c.pdf", b"c")]),
        (PAGE, FILES[:1]),
        ("https://www.example.lt/kitas-puslapis", FILES),
    ],
    ids=["a file changed", "a file added", "a file removed", "another page"],
)
def test_a_copy_whose_files_changed_is_replaced(tmp_path, page, files):
    copy = tmp_path / "copy"
    snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", FILES, date(2026, 11, 1))
    assert snapshot.save_site_copy(copy, page, b"<p>new</p>", files, date(2026, 11, 22))
    names = [url.rsplit("/", 1)[1] for url, _ in files]
    index = {"takenAt": "2026-11-22", "page": page, "files": names}
    assert json.loads((copy / "copy.json").read_text(encoding="utf-8")) == index
    contents = {name: content for name, (_, content) in zip(names, files, strict=True)}
    assert saved(copy) == {
        **contents,
        "page.html": b"<p>new</p>",
        "copy.json": (copy / "copy.json").read_bytes(),
    }


def test_another_page_kept_as_a_file_is_compared_as_a_page(tmp_path):
    other = "https://www.example.lt/kitas-puslapis/2332"
    copy = tmp_path / "copy"
    files = [(other, b"<p>other page</p>"), *FILES]
    snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", files, date(2026, 11, 1), [other])
    before = saved(copy)
    # Its new markup alone is no change...
    files = [(other, b"<p>other page, new markup</p>"), *FILES]
    assert not snapshot.save_site_copy(
        copy, PAGE, b"<p>page</p>", files, date(2026, 11, 2), [other]
    )
    assert saved(copy) == before
    # ...but it has to be there.
    (copy / "2332").unlink()
    assert snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", files, date(2026, 11, 3), [other])
    assert (copy / "2332").read_bytes() == b"<p>other page, new markup</p>"


def test_a_damaged_copy_is_replaced(tmp_path):
    copy = tmp_path / "copy"
    snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", FILES, date(2026, 11, 1))
    (copy / "b.pdf").unlink()
    assert snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", FILES, date(2026, 11, 22))
    assert (copy / "b.pdf").read_bytes() == b"b"
    (copy / "copy.json").write_text("{", encoding="utf-8")
    assert snapshot.save_site_copy(copy, PAGE, b"<p>page</p>", FILES, date(2026, 11, 23))


def test_the_options_choose_what_is_refreshed(monkeypatch):
    done = []
    monkeypatch.setattr(snapshot, "save_register", lambda: done.append("register"))
    monkeypatch.setattr(snapshot, "save_copies", lambda: done.append("copies") or 0)
    assert snapshot.main(["--register"]) == 0
    assert done == ["register"]
    assert snapshot.main(["--copies"]) == 0
    assert done == ["register", "copies"]
    assert snapshot.main([]) == 0
    assert done == ["register", "copies", "register", "copies"]


def test_a_copy_that_fails_doesnt_stop_the_others(monkeypatch, tmp_path, capsys):
    def refused(folder):
        raise OSError("HTTP Error 403: Forbidden")

    refreshed = []
    copies = [
        ("A r.", refused, tmp_path / "a"),
        ("B r.", lambda folder: refreshed.append(folder) or True, tmp_path / "b"),
        ("C r.", lambda folder: refreshed.append(folder) and False, tmp_path / "c"),
    ]
    monkeypatch.setattr(snapshot, "site_copies", lambda: copies)
    assert snapshot.main(["--copies"]) == 1
    assert refreshed == [tmp_path / "b", tmp_path / "c"]
    out, err = capsys.readouterr()
    assert "B r.: saved the page and its files" in out
    assert "C r.: no change to the files" in out
    assert "A r.: the copy in" in err and "HTTP Error 403" in err
    monkeypatch.setattr(snapshot, "site_copies", lambda: copies[1:])
    assert snapshot.main(["--copies"]) == 0


def test_every_site_copy_is_committed():
    """Each copy the refresh saves is in pipeline/data, where its module reads it."""
    copies = snapshot.site_copies()
    labels = ["Šilutės r.", "Kėdainių r.", "Ukmergės r.", "Širvintų r.", "Švenčionių r."]
    assert [label for label, _, _ in copies] == labels
    for _, save, folder in copies:
        assert callable(save)
        assert json.loads((folder / snapshot.SITE_COPY_INDEX).read_text(encoding="utf-8"))["files"]

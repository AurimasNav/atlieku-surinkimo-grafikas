import json

from schedule_pipeline import regions


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_lists_every_region_folder_of_the_site(tmp_path):
    # Vilniaus r.: rows of Nemenčinė without a `provider`, and a part of Nemėžio.
    write(
        tmp_path / "schedule.json",
        {
            "providers": [{"id": "nemezio"}],
            "areas": [{"kind": "household"}, {"kind": "glass", "provider": "nemezio"}],
        },
    )
    write(tmp_path / "addresses.json", {})
    # Kauno švara: schedules per address.
    write(
        tmp_path / "kauno-r" / "schedule.json",
        {"provider": {"id": "kauno-svara"}, "elderships": [{"id": "akademijos"}]},
    )
    write(tmp_path / "kauno-r" / "points.json", {})
    write(tmp_path / "kauno-r" / "addresses" / "babtu.json", {})
    write(tmp_path / "kauno-r" / "addresses" / "akademijos.json", {})
    # A folder no app knows yet, and one whose addresses.json isn't there.
    write(
        tmp_path / "panevezio-ratc" / "schedule.json",
        {"providers": [{"id": "panevezys"}, {"id": "pasvalys"}], "areas": []},
    )
    write(tmp_path / "panevezio-ratc" / "addresses.json", {})
    write(tmp_path / "jurbarko-r" / "schedule.json", {"providers": [{"id": "jurbarkas"}]})
    # Not regions: the privacy policy and the monitoring files.
    (tmp_path / "privacy").mkdir()
    (tmp_path / "privacy" / "index.html").write_text("<html></html>", encoding="utf-8")
    write(tmp_path / "status.json", {})

    assert regions.main(["--site", str(tmp_path)]) == 0

    published = json.loads((tmp_path / "regions.json").read_text(encoding="utf-8"))
    assert published == {
        "schemaVersion": 1,
        "regions": [
            {
                "path": "",
                "kind": "settlements",
                "files": ["schedule.json", "addresses.json"],
                "providers": ["nemencine", "nemezio"],
            },
            {
                "path": "jurbarko-r/",
                "kind": "settlements",
                "files": ["schedule.json"],
                "providers": ["jurbarkas"],
            },
            {
                "path": "kauno-r/",
                "kind": "addresses",
                "files": ["schedule.json", "points.json"],
                "elderships": ["akademijos", "babtu"],
                "providers": ["kauno-svara"],
            },
            {
                "path": "panevezio-ratc/",
                "kind": "settlements",
                "files": ["schedule.json", "addresses.json"],
                "providers": ["panevezys", "pasvalys"],
            },
        ],
    }


def test_the_root_names_nemencine_once(tmp_path):
    # schedule.json lists Nemenčinė among its companies; its rows still have no `provider`.
    write(
        tmp_path / "schedule.json",
        {"providers": [{"id": "nemencine"}, {"id": "nemezio"}], "areas": [{"kind": "glass"}]},
    )
    assert regions.collect(tmp_path)["regions"][0]["providers"] == ["nemencine", "nemezio"]


def test_no_data_is_an_error(tmp_path):
    (tmp_path / "privacy").mkdir()
    assert regions.main(["--site", str(tmp_path)]) == 1
    assert not (tmp_path / "regions.json").exists()

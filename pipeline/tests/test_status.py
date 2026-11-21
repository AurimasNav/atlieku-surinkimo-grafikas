import json

from schedule_pipeline import status


def test_metrics_for_both_sources(tmp_path):
    (tmp_path / "kauno-r").mkdir()
    (tmp_path / "schedule.json").write_text(
        json.dumps(
            {
                "generatedAt": "2026-11-16T04:20:00+00:00",
                "warnings": 3,
                "areas": [{"kind": "household"}, {"kind": "household"}, {"kind": "glass"}],
                "locations": [{}, {}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "kauno-r" / "schedule.json").write_text(
        json.dumps(
            {
                "generatedAt": "2026-11-15T04:20:00+00:00",
                "warnings": 1,
                "stats": {"addresses": 39290, "areas": {"food": 13, "household": 43}},
            }
        ),
        encoding="utf-8",
    )
    assert status.main(["--site", str(tmp_path)]) == 0

    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_generated_timestamp_seconds{source="nemencine"} 1794802800' in text
    assert 'siuksliaveze_data_generated_timestamp_seconds{source="kauno"} 1794716400' in text
    assert 'siuksliaveze_data_areas{source="nemencine",kind="household"} 2' in text
    assert 'siuksliaveze_data_places{source="kauno"} 39290' in text
    assert 'siuksliaveze_data_warnings{source="nemencine"} 3' in text
    assert "# TYPE siuksliaveze_data_warnings gauge" in text
    published = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert published["sources"]["kauno"]["areas"] == {"food": 13, "household": 43}


def test_kaisiadorys_is_a_source_of_its_own(tmp_path):
    # Published in kauno-r/ with Kauno r. (schedule_pipeline.svara), counted apart.
    (tmp_path / "kauno-r").mkdir()
    (tmp_path / "kauno-r" / "schedule.json").write_text(
        json.dumps(
            {
                "generatedAt": "2026-11-21T04:20:00+00:00",
                "warnings": 3,
                "stats": {"addresses": 39200, "areas": {"food": 13, "household": 43}},
                "otherMunicipalities": [
                    {
                        "id": "kaisiadorys",
                        "name": "Kaišiadorių r.",
                        "stats": {"addresses": 7726, "areas": {"household": 36}},
                        "warnings": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    sources = status.collect(tmp_path)["sources"]
    assert sources["kauno"]["places"] == 39200
    assert sources["kaisiadorys"] == {
        "generatedAt": "2026-11-21T04:20:00+00:00",
        "areas": {"household": 36},
        "places": 7726,
        "warnings": 0,
    }


def test_no_data_is_an_error(tmp_path):
    assert status.main(["--site", str(tmp_path)]) == 1

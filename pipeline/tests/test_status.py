import json
from datetime import date

import pytest

from schedule_pipeline import build, status
from schedule_pipeline.model import Provider


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
        "newWarnings": 0,
    }


def test_kaisiadorys_comes_from_its_own_folder(tmp_path):
    # Since its operator changed (November 2026) Kaišiadorių r. has a folder of its own
    # (schedule_pipeline.kaisiadorys), the same source id: an old kauno-r part of it doesn't count.
    test_kaisiadorys_is_a_source_of_its_own(tmp_path)
    mine = {"provider": "kaisiadorys"}
    (tmp_path / "kaisiadoriu-r").mkdir()
    (tmp_path / "kaisiadoriu-r" / "schedule.json").write_text(
        json.dumps(
            {
                "generatedAt": "2026-11-27T04:20:00+00:00",
                "providers": [
                    {
                        "id": "kaisiadorys",
                        "generatedAt": "2026-11-27T04:20:00+00:00",
                        "warnings": 1,
                        "warningTexts": ["not linked to any settlement: household: Kapinės"],
                    }
                ],
                "areas": [
                    {"id": "a", "kind": "household", "dates": ["2026-12-29"], **mine},
                    {"id": "b", "kind": "glass", "dates": ["2026-12-17"], **mine},
                ],
                "locations": [{"id": "g1", "schedule": {"household": {"area": "a"}}, **mine}],
            }
        ),
        encoding="utf-8",
    )
    sources = status.collect(tmp_path)["sources"]
    assert sources["kauno"]["places"] == 39200
    assert sources["kaisiadorys"] == {
        "generatedAt": "2026-11-27T04:20:00+00:00",
        "areas": {"glass": 1, "household": 1},
        "places": 1,
        "warnings": 1,
        "lastDate": {"glass": "2026-12-17", "household": "2026-12-29"},
        "newWarnings": 1,
    }


def test_no_data_is_an_error(tmp_path):
    assert status.main(["--site", str(tmp_path)]) == 1


# --- new warnings: those pipeline/known-warnings.json doesn't list ----------------------


def test_normalise_leaves_out_what_changes_from_run_to_run():
    assert status.normalise(
        "2026 m- birželis-gruodis mėn  Buitinių atliekų surinkimo grafikasP.xlsx row 715: kept as"
        " text, no exact dates: 'kas antras mėnesio trečiadienis'"
    ) == (
        "# m- # mėn  Buitinių atliekų surinkimo grafikasP.xlsx row #: kept as"
        " text, no exact dates: 'kas antras mėnesio trečiadienis'"
    )
    # A site copy: its date and age, and whatever the site answered.
    copy = "https://www.zarasai.lt/x/269: unavailable ({}); used the copy from {} ({})"
    expected = "https://www.zarasai.lt/x/#: unavailable; used the copy"
    for error, taken, age in (
        ("HTTP Error 403: Forbidden", "2026-11-22", "0 days old"),
        ("<urlopen error timed out>", "2026-10-01", "52 days old"),
        ("HTTP Error 503: Service Unavailable (retry)", "2026-11-21", "1 day old"),
    ):
        assert status.normalise(copy.format(error, taken, age)) == expected
    # Words stay as they are: a new place name is a new warning.
    assert status.normalise("not linked to any settlement: household: Stražininkai") == (
        "not linked to any settlement: household: Stražininkai"
    )


@pytest.mark.parametrize(
    "text",
    [
        'not linked to any settlement: household: SB "Girios -7"',
        "not a settlement or a street: household: Kelmės miestas 3: S. Nėries g.",
        "not a settlement or a street: household: Naujasodžių k.: Linų g. 2",
        "not a settlement or a street: glass: Šeduvos miesto sen.: Sausio 13-osios g.",
        "not a settlement of the eldership: household: Bogušiai (Marijampolio sen.)",
        # A month in a place's name stays too.
        "not a settlement or a street: household: Zarasų sen.: Liepkalnio k.",
    ],
)
def test_normalise_keeps_a_places_numbers(text):
    # A place's numbers are part of its name, and these warnings have no row numbers.
    assert status.normalise(text) == text


def test_another_place_or_route_with_other_numbers_is_new():
    known = {
        status.normalise(t)
        for t in (
            'not linked to any settlement: household: SB "Girios -7"',
            "not a settlement or a street: household: Naujasodžių k.: Linų g. 2",
            "not a settlement or a street: household: Kelmės miestas 1: P. Cvirkos g.",
            "Mišrių komunalinių grafikas1.doc route 3*: 2026-12-03 isn't a day of the rule"
            " 'ketvirtadieniai'",
        )
    }
    assert status.new_warnings(
        [
            'not linked to any settlement: household: SB "Girios -8"',
            "not a settlement or a street: household: Naujasodžių k.: Linų g. 14",
            "not a settlement or a street: household: Kelmės miestas 3: P. Cvirkos g.",
            # Another route is other places.
            "Mišrių komunalinių grafikas1.doc route 13*: 2026-12-03 isn't a day of the rule"
            " 'ketvirtadieniai'",
            # The same route on another date: known.
            "Mišrių komunalinių grafikas1.doc route 3*: 2027-01-07 isn't a day of the rule"
            " 'ketvirtadieniai'",
        ],
        known,
    ) == [
        'not linked to any settlement: household: SB "Girios -8"',
        "not a settlement or a street: household: Naujasodžių k.: Linų g. 14",
        "not a settlement or a street: household: Kelmės miestas 3: P. Cvirkos g.",
        "Mišrių komunalinių grafikas1.doc route 13*: 2026-12-03 isn't a day of the rule"
        " 'ketvirtadieniai'",
    ]


def test_next_half_years_file_keeps_its_warnings_known():
    # Nemenčinė posts a file per half year; its name has the months. The rules kept as text
    # stay the same warnings whichever half year the file is of.
    rule = ": kept as text, no exact dates: 'kas antras mėnesio trečiadienis'"
    known = {
        status.normalise(
            f"2026 m- birželis-gruodis mėn  Buitinių atliekų surinkimo grafikasP.xlsx row 715{rule}"
        )
    }
    for name in (
        "2027 m- sausis-birželis mėn  Buitinių atliekų surinkimo grafikasP.xlsx",
        "2027 m- sausio–birželio mėn  Buitinių atliekų surinkimo grafikasP.xlsx",
        "2027 m- liepa-gruodis mėn  Buitinių atliekų surinkimo grafikasP.xlsx",
    ):
        assert status.new_warnings([f"{name} row 20{rule}"], known) == [], name
    # Another rule is new; so is another file.
    other = ": kept as text, no exact dates: 'kas antras mėnesio penktadienis'"
    assert status.new_warnings(
        [
            f"2027 m- sausis-birželis mėn  Buitinių atliekų surinkimo grafikasP.xlsx row 20{other}",
            f"2027 m- sausis-birželis mėn  Konteinerių grafikas.xlsx row 20{rule}",
        ],
        known,
    ) == [
        f"2027 m- sausis-birželis mėn  Buitinių atliekų surinkimo grafikasP.xlsx row 20{other}",
        f"2027 m- sausis-birželis mėn  Konteinerių grafikas.xlsx row 20{rule}",
    ]
    # The months of a rule, after the file name, stay: another month is another rule.
    assert status.normalise("G.xlsx row 4: kept as text, no exact dates: 'liepos mėn. 1 d.'") == (
        "G.xlsx row #: kept as text, no exact dates: 'liepos mėn. # d.'"
    )


COPY = "https://www.zarasai.lt/x/: unavailable (HTTP Error 403: Forbidden); used the copy from {}"


def test_a_site_copy_used_is_never_new():
    # Six sites refuse GitHub's runners on some days and answer on others: reading their copy
    # needs nobody to act, so it is never new, listed or not.
    copy = COPY.format("2026-11-02 (23 days old)")
    assert status.used_the_copy(copy)
    assert not status.used_the_copy("not linked to any settlement: household: Kopija")
    assert status.new_warnings([copy, "row 3: kept as text"], set()) == ["row 3: kept as text"]


def test_write_known_never_lists_a_site_copy_used(tmp_path):
    # Acknowledged on a day the site answered, or on a day it didn't: the same file, so the next
    # refusal isn't new either way.
    known = tmp_path / "known-warnings.json"
    known.write_text(json.dumps({"zarasai": ["old"]}), encoding="utf-8")
    for texts in (
        ["row 3: kept as text"],
        [COPY.format("2026-11-02 (0 days old)"), "row 4: kept as text"],
    ):
        site = site_with(tmp_path / "site", [part("zarasai", texts)])
        assert status.main(["--site", str(site), "--known", str(known), "--write-known"]) == 0
        assert json.loads(known.read_text(encoding="utf-8")) == {"zarasai": ["row #: kept as text"]}
    site_with(site, [part("zarasai", [COPY.format("2026-11-03 (1 day old)")])])
    assert status.main(["--site", str(site), "--known", str(known)]) == 0
    report = json.loads((site / "warnings.json").read_text(encoding="utf-8"))
    assert report["sources"]["zarasai"]["new"] == []
    assert report["sources"]["zarasai"]["known"] == [COPY.format("2026-11-03 (1 day old)")]


def test_split_new_leaves_out_what_is_already_live():
    # The live check of a PR: a new warning the published data has as new too is already live
    # (the alert fires anyway); only the others are the PR's.
    report = {
        "sources": {
            "nemezio": {"new": ["f.xlsx row 12: kept as text", "not linked: Naujas"]},
            "sakiai": {"new": ["row 3: other"]},
            "trakai": {"new": []},
        }
    }
    published = {
        "sources": {
            # Row numbers moved since the daily run: still the same warning.
            "nemezio": {"new": ["f.xlsx row 9: kept as text"], "known": []},
            # The PR's warning is known on the site: not live.
            "sakiai": {"new": [], "known": ["row 3: other"]},
        }
    }
    mine, already = status.split_new(report, published)
    assert mine == {"nemezio": ["not linked: Naujas"], "sakiai": ["row 3: other"]}
    assert already == {"nemezio": ["f.xlsx row 12: kept as text"]}
    # Before the daily job published warnings.json: all of them are the PR's.
    mine, already = status.split_new(report, None)
    assert mine == {
        "nemezio": ["f.xlsx row 12: kept as text", "not linked: Naujas"],
        "sakiai": ["row 3: other"],
    }
    assert already == {}


def site_with(site, providers):
    """A site with schedule.json of these providers' parts (as build.merge_parts writes it)."""
    site.mkdir(exist_ok=True)
    data = {
        "generatedAt": "2026-11-22T04:20:00+00:00",
        "areas": [{"kind": "household", "provider": p["id"]} for p in providers],
        "locations": [],
        "providers": providers,
    }
    (site / "schedule.json").write_text(json.dumps(data), encoding="utf-8")
    return site


def part(source, texts, **more):
    entry = {"id": source, "generatedAt": "2026-11-22T04:20:00+00:00"}
    if texts is None:
        return {**entry, "warnings": more.pop("warnings", 0), **more}
    return {**entry, "warnings": len(texts), "warningTexts": texts, **more}


def test_new_warnings_are_those_the_baseline_doesnt_list(tmp_path):
    site = site_with(
        tmp_path,
        [
            # Row numbers moved, the place is known: nothing new.
            part("nemezio", ["f.xlsx row 12: kept as text", "not linked to any settlement: A"]),
            # A new place, twice (two kinds), and a known one.
            part(
                "sakiai",
                [
                    "not linked to any settlement: household: Naujas",
                    "not linked to any settlement: glass: Naujas",
                    "not linked to any settlement: household: Senas",
                ],
            ),
            # Published before the builds published the texts: 6 warnings, none known to be new.
            part("kalvarija", None, warnings=6),
            # A source the baseline doesn't have yet: all of its warnings are new.
            part("trakai", ["page 2: packaging of 'X' on 2026-11-17, not on its weekday"]),
        ],
    )
    known = {
        "nemezio": {"f.xlsx row #: kept as text", "not linked to any settlement: A"},
        "sakiai": {"not linked to any settlement: household: Senas"},
        "kalvarija": set(),
    }
    sources = status.collect(site, known)["sources"]
    assert {s: (d["warnings"], d["newWarnings"]) for s, d in sources.items()} == {
        "nemezio": (2, 0),
        "sakiai": (3, 2),
        "kalvarija": (6, 0),
        "trakai": (1, 1),
    }
    text = status.metrics(status.collect(site, known))
    assert "# TYPE siuksliaveze_data_new_warnings gauge" in text
    assert 'siuksliaveze_data_new_warnings{source="sakiai"} 2' in text
    assert 'siuksliaveze_data_new_warnings{source="kalvarija"} 0' in text
    # The old count stays what it was.
    assert 'siuksliaveze_data_warnings{source="kalvarija"} 6' in text


def test_kauno_svara_and_its_other_municipalities_have_texts(tmp_path):
    (tmp_path / "kauno-r").mkdir()
    (tmp_path / "kauno-r" / "schedule.json").write_text(
        json.dumps(
            {
                "generatedAt": "2026-11-21T04:20:00+00:00",
                "warnings": 2,
                "warningTexts": ["3 rows skipped: waste type „X“", "12 rows skipped: no date"],
                "stats": {"addresses": 39200, "areas": {"household": 43}},
                "otherMunicipalities": [
                    {
                        "id": "kaisiadorys",
                        "stats": {"addresses": 7726, "areas": {"household": 36}},
                        "warnings": 1,
                        "warningTexts": ["1 rows skipped: waste type „Y“"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    known = {"kauno": {"# rows skipped: waste type „X“", "# rows skipped: no date"}}
    sources = status.collect(tmp_path, known)["sources"]
    assert sources["kauno"]["newWarnings"] == 0
    assert sources["kaisiadorys"]["newWarnings"] == 1


def test_write_known_acknowledges_the_sites_warnings(tmp_path):
    site = site_with(
        tmp_path / "site",
        [
            part("nemezio", ["b row 3", "a: Žąsinas", "b row 4"]),
            part("kalvarija", None, warnings=6),
        ],
    )
    known = tmp_path / "known-warnings.json"
    known.write_text(
        json.dumps({"nemezio": ["gone"], "kalvarija": ["kept"], "zarasai": ["not built"]}),
        encoding="utf-8",
    )
    assert status.main(["--site", str(site), "--known", str(known), "--write-known"]) == 0
    # Sorted, each once, UTF-8 as it is, one entry a line, a newline at the end. A warning the
    # source no longer gives is dropped; sources without texts on this site keep theirs.
    assert known.read_bytes().decode("utf-8") == (
        "{\n"
        '  "kalvarija": [\n    "kept"\n  ],\n'
        '  "nemezio": [\n    "a: Žąsinas",\n    "b row #"\n  ],\n'
        '  "zarasai": [\n    "not built"\n  ]\n'
        "}\n"
    )
    published = json.loads((site / "status.json").read_text(encoding="utf-8"))
    assert published["sources"]["nemezio"]["newWarnings"] == 0
    # Then a new one appears.
    site_with(site, [part("nemezio", ["b row 9", "a: Žąsinas", "a: Naujas"])])
    assert status.main(["--site", str(site), "--known", str(known)]) == 0
    assert 'siuksliaveze_data_new_warnings{source="nemezio"} 1' in (site / "metrics.txt").read_text(
        encoding="utf-8"
    )
    report = json.loads((site / "warnings.json").read_text(encoding="utf-8"))
    assert report["sources"]["nemezio"]["new"] == ["a: Naujas"]
    assert report["sources"]["nemezio"]["known"] == ["b row 9", "a: Žąsinas"]


def test_without_a_baseline_every_warning_is_new(tmp_path, capsys):
    site = site_with(tmp_path / "site", [part("nemezio", ["a", "b"])])
    missing = tmp_path / "none.json"
    assert status.main(["--site", str(site), "--known", str(missing)]) == 0
    assert "every warning counts as new" in capsys.readouterr().err
    assert (
        status.collect(site, status.load_known(missing))["sources"]["nemezio"]["newWarnings"] == 2
    )
    # --write-known creates it.
    assert status.main(["--site", str(site), "--known", str(missing), "--write-known"]) == 0
    assert json.loads(missing.read_text(encoding="utf-8")) == {"nemezio": ["a", "b"]}


def test_the_committed_baseline_is_sorted_and_normalised():
    if not status.KNOWN.exists():
        pytest.skip("no pipeline/known-warnings.json yet")
    text = status.KNOWN.read_text(encoding="utf-8")
    known = json.loads(text)
    assert list(known) == sorted(known)
    for source, texts in known.items():
        assert texts == sorted(set(texts)), source
        assert all(status.normalise(t) == t for t in texts), source
        # Never new, so never listed (status.known_from).
        assert not any(status.used_the_copy(t) for t in texts), source
    # As --write-known writes it, so acknowledging changes only the lines that changed.
    assert text == json.dumps(known, ensure_ascii=False, indent=2) + "\n"


def test_the_warnings_page(tmp_path):
    site = site_with(
        tmp_path,
        [
            part("nemezio", ['not linked: <script>alert(1)</script> & "Ąžuolas"']),
            part("sakiai", ["row 1: known"]),
            part("kalvarija", None, warnings=6),
        ],
    )
    known = tmp_path / "known.json"
    known.write_text(json.dumps({"sakiai": ["row #: known"]}), encoding="utf-8")
    assert status.main(["--site", str(site), "--known", str(known)]) == 0
    page = (site / "warnings.html").read_text(encoding="utf-8")
    # A section a source, as the alert links them (warnings.html#<source>).
    for source in ("nemezio", "sakiai", "kalvarija"):
        assert f'<section id="{source}">' in page
    # Escaped, so a source's text can't add markup; no scripts at all.
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;Ąžuolas&quot;" in page
    assert "<script" not in page
    # New ones first, marked; the source with new ones heads the list.
    nemezio = page[page.index('<section id="nemezio">') :]
    nemezio = nemezio[: nemezio.index("</section>")]
    assert 'class="new">New: not in pipeline/known-warnings.json' in nemezio
    assert page.index('<section id="nemezio">') < page.index('<section id="kalvarija">')
    sakiai = page[page.index('<section id="sakiai">') :]
    assert "<h3>Known</h3>" in sakiai[: sakiai.index("</section>")]
    assert "Published before the builds published their warnings" in page
    assert '<strong class="new">1 new</strong>' in page
    # Times in Vilnius time.
    assert "2026-11-22 06:20 (Vilnius)" in page


# --- the builds publish the texts next to the count ---------------------------------------


PROVIDER = Provider("sakiai", "UAB „X“", "https://example.lt/", frozenset())


def a_part(**more):
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-11-22T04:20:00+00:00",
        "files": [],
        "coverage": {},
        "matching": {},
        "areas": [
            {"id": "h-1", "kind": "household", "name": "X", "dates": [], "provider": "sakiai"}
        ],
        "locations": [],
        **more,
    }


def test_build_parts_publishes_the_warnings_of_each_part(monkeypatch):
    def download(today, keep_days):
        return [], [
            "https://example.lt/: unavailable (x); used the copy from 2026-11-22 (0 days old)"
        ]

    monkeypatch.setattr(build, "build_dataset", lambda *args: (a_part(), ["row 3: kept as text"]))
    source = build.Source(PROVIDER, download, None, {})
    (result,) = build.build_parts((source,), None, date(2026, 11, 22), 31, None)
    texts = [
        "https://example.lt/: unavailable (x); used the copy from 2026-11-22 (0 days old)",
        "row 3: kept as text",
    ]
    assert result.part["warnings"] == 2 and result.part["warningTexts"] == texts
    merged = build.merge_parts([(PROVIDER, result.part)])
    assert merged["providers"][0]["warnings"] == 2
    assert merged["providers"][0]["warningTexts"] == texts
    # Kept as it was when the part's build fails the next day (published_part).
    kept = build.published_part(merged, PROVIDER)
    assert kept["warnings"] == 2 and kept["warningTexts"] == texts
    assert build.merge_parts([(PROVIDER, kept)])["providers"] == merged["providers"]


def test_a_part_published_before_the_texts_keeps_its_count_only():
    old = build.merge_parts([(PROVIDER, a_part(warnings=6))])
    assert "warningTexts" not in old["providers"][0]
    kept = build.published_part(old, PROVIDER)
    assert kept["warnings"] == 6 and "warningTexts" not in kept

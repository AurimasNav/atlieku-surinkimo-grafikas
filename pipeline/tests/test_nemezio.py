"""UAB „Nemėžio komunalininkas“: the page, the PDFs, the place lists and the merged data."""

import copy
import dataclasses
import functools
import json
from datetime import date

import pytest
from test_parsers import REGISTRY, all_sources, fixture

from schedule_pipeline import build, nemezio, status
from schedule_pipeline.build import NEMENCINE, NEMEZIO, Source, ValidationError, build_dataset
from schedule_pipeline.locations import garden_label, split_places
from schedule_pipeline.model import SourceFile

HOUSEHOLD = "Grafikas mišrių 2026 (10-12).xlsx - 2026 (10-12).pdf"
PACKAGING = "Grafikas pakuočių 2026 (10-12).xlsx - 2026 (10-12).pdf"
NEMENCINE_ELDERSHIPS = NEMENCINE.provider.elderships


def nemezio_sources():
    base = "https://www.nkom.lt/uploads/Atliek%C5%B3%20grafikai/"
    return [
        (
            SourceFile("household", base + "h.pdf", HOUSEHOLD),
            fixture("nemezio-household-2026-q4.pdf"),
        ),
        (
            SourceFile("packaging", base + "p.pdf", PACKAGING),
            fixture("nemezio-packaging-2026-q4.pdf"),
        ),
    ]


# --- the page ----------------------------------------------------------------


def test_finds_the_quarterly_files_on_the_page():
    pdfs, spreadsheets = nemezio.find_files(fixture("nemezio-page.html").decode("utf-8"))
    names = {(f.kind, f.file_name) for f in pdfs}
    assert names == {
        ("household", HOUSEHOLD),
        ("packaging", PACKAGING),
        ("household", "Grafikas mišriu 2026 (07-09).pdf"),
        ("packaging", "Grafikas pakuociu 2026 (07-09).pdf"),
    }
    # Relative links under the page's <base>, with the spaces and letters encoded.
    current = next(f for f in pdfs if f.file_name == HOUSEHOLD)
    assert current.url == (
        "https://www.nkom.lt/uploads/Atliek%C5%B3%20grafikai/"
        "Grafikas%20mi%C5%A1ri%C5%B3%202026%20(10-12).xlsx%20-%202026%20(10-12).pdf"
    )
    # Garden community pictures under uploads/ aren't schedules.
    assert all(f.file_name.startswith("Grafikas") for f in pdfs + spreadsheets)
    assert {f.file_name for f in spreadsheets} >= {"Grafikas mišriu 2026 (04-06) 2.xlsx"}


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        (HOUSEHOLD, "household"),
        ("Grafikas mišriu 2026 (07-09).pdf", "household"),
        ("Grafikas misriu 2027 (01-03).pdf", "household"),
        (PACKAGING, "packaging"),
        ("Grafikas pakuociu 2027 (01-03).pdf", "packaging"),
        ("SB Galanta.jpg", None),
    ],
)
def test_classifies_by_file_name(name, kind):
    assert nemezio.classify(name) == kind


def test_period_from_the_file_name():
    assert nemezio.file_period(HOUSEHOLD) == (date(2026, 10, 1), date(2026, 12, 31))
    assert nemezio.file_period("Grafikas mišriu 2026 (04-06) 2.xlsx") == (
        date(2026, 4, 1),
        date(2026, 6, 30),
    )
    assert nemezio.file_period("Grafikas 2026.pdf") is None


def test_selects_the_current_quarter_and_the_previous_one_while_it_is_kept():
    pdfs, spreadsheets = nemezio.find_files(fixture("nemezio-page.html").decode("utf-8"))
    required, optional = nemezio.select_files(pdfs, date(2026, 11, 17), keep_days=31)
    assert {f.file_name for f in required} == {HOUSEHOLD, PACKAGING}
    assert optional == []
    # Mid October, the July-September files still have dates within keep_days.
    required, optional = nemezio.select_files(pdfs, date(2026, 10, 15), keep_days=31)
    assert {f.file_name for f in required} == {HOUSEHOLD, PACKAGING}
    assert {f.file_name for f in optional} == {
        "Grafikas mišriu 2026 (07-09).pdf",
        "Grafikas pakuociu 2026 (07-09).pdf",
    }
    # Only recent periods published as a spreadsheet alone are worth a warning.
    assert nemezio.unreadable(pdfs, spreadsheets, date(2026, 11, 17), 31) == []


def test_picks_up_the_next_quarter_when_it_is_linked():
    html = (
        fixture("nemezio-page.html")
        .decode("utf-8")
        .replace(
            "</body>",
            '<a href="uploads/Atliekų grafikai/Grafikas mišrių 2027 (01-03).pdf">I</a></body>',
        )
    )
    pdfs, _ = nemezio.find_files(html)
    required, _ = nemezio.select_files(pdfs, date(2026, 12, 28), keep_days=31)
    assert {f.file_name for f in required} == {
        "Grafikas mišrių 2027 (01-03).pdf",  # the newest
        HOUSEHOLD,  # still running
        PACKAGING,
    }


# --- the PDFs ----------------------------------------------------------------


@pytest.fixture(scope="module")
def household():
    return nemezio.parse_household(fixture("nemezio-household-2026-q4.pdf"), HOUSEHOLD)


@pytest.fixture(scope="module")
def packaging():
    return nemezio.parse_packaging(fixture("nemezio-packaging-2026-q4.pdf"), PACKAGING)


def test_household_rows(household):
    houses = [a for a in household.areas if a.group == "Individualūs namai"]
    shared = [a for a in household.areas if a.group == "Daugiabučiai namai"]
    assert (len(houses), len(shared)) == (89, 54)
    assert all(a.provider == "nemezio" for a in household.areas)
    row = next(a for a in houses if a.name.startswith("Bildžiai, Bukiškės"))
    assert row.district == "Lavoriškių"
    assert sorted(row.dates)[:3] == [date(2026, 10, 6), date(2026, 10, 20), date(2026, 11, 3)]
    assert len(row.dates) == 7
    # Footnotes ("DĖMESIO", "PASTABA", ...) are not rows.
    assert not any(a.name.startswith(("DĖMESIO", "PASTABA", "Atliekų")) for a in household.areas)


def test_shared_container_sites_get_weekly_dates_or_a_note(household):
    by_name = {a.name: a for a in household.areas}
    weekly = by_name["Juodšilių k. (Durpių g. 7, 10)"]
    assert weekly.group == "Daugiabučiai namai"
    assert weekly.weekday == "Trečiadienis"
    assert len(weekly.dates) == 13
    assert all(d.weekday() == 2 for d in weekly.dates)
    assert min(weekly.dates) >= date(2026, 10, 1) and max(weekly.dates) <= date(2026, 12, 31)
    # "Every other Tuesday" doesn't say which weeks: shown as text.
    every_other = by_name["Kalvelių k. (Žaliašalio g. 17, 19, Kenos g. 14)"]
    assert every_other.note == "Kas antrą antradienį" and not every_other.dates


def test_packaging_and_glass_from_one_file(packaging):
    kinds = [a.kind for a in packaging.areas]
    assert (kinds.count("packaging"), kinds.count("glass")) == (45, 45)
    name = (
        "Nemėžis (Draugystės g., Kaštonų g., Mėnulio g., Naujakurių g., Šveicarų g., "
        "Topolių g., Minsko pl.), Kuprioniškės, Ašmenos kelias"
    )
    rows = {a.kind: a for a in packaging.areas if a.name == name}
    assert sorted(rows["packaging"].dates) == [
        date(2026, 10, 9),
        date(2026, 11, 11),
        date(2026, 12, 8),
    ]
    assert sorted(rows["glass"].dates) == [date(2026, 10, 1)]
    assert rows["packaging"].id != rows["glass"].id


def test_unknown_day_format_fails_loudly():
    assert nemezio.parse_days("2, 16,30") == [2, 16, 30]
    assert nemezio.parse_days("1 3 , 2 7") == [13, 27]
    with pytest.raises(ValueError):
        nemezio.parse_days("kas antrą")


# --- places ------------------------------------------------------------------


def test_split_places():
    assert split_places("Akmenynė, Mažeikiai (be Kairėnų ir Girios g.), Gaidūnai") == [
        "Akmenynė",
        "Mažeikiai (be Kairėnų ir Girios g.)",
        "Gaidūnai",
    ]
    # A missing comma after a bracket.
    assert split_places("Pagiriai (Kalno g.) Melekonys (Pienių g.)") == [
        "Pagiriai (Kalno g.)",
        "Melekonys (Pienių g.)",
    ]


def test_garden_labels():
    assert garden_label("SB „Rasa“- Piktakonių k.")[1] == "SB „Rasa“"
    assert garden_label('SB"Migūnai"')[1] == "SB „Migūnai“"
    assert garden_label("SB „Aidas- 1“")[1] == "SB „Aidas-1“"
    assert garden_label("Skaidiškės") is None
    # "Sb" (Mažeikių r. 2027) is the same garden as "SB"; a word that starts with "Sb" or "sb"
    # isn't a garden.
    assert garden_label("Sb „Šaltinėlis“") == garden_label("SB „Šaltinėlis“")
    assert garden_label("Sb „Šaltinėlis“")[1] == "SB „Šaltinėlis“"
    for word in ("Sbarro", "Sbėgimo g.", "sbarro", "Asb „Rasa“", "S. Bajoro g."):
        assert garden_label(word) is None, word


@pytest.fixture(scope="module")
def dataset():
    data, warnings = build_dataset(
        nemezio_sources(), REGISTRY, today=date(2026, 11, 17), keep_days=31, source=NEMEZIO
    )
    return data, warnings


@pytest.fixture(scope="module")
def place(dataset):
    data, _ = dataset
    areas = {a["id"]: a for a in data["areas"]}
    locations = {(loc["name"], loc["type"], loc["district"]): loc for loc in data["locations"]}

    def lookup(name, district, kind="household", street=None, settlement_type=None):
        loc = next(
            v
            for (n, t, d), v in locations.items()
            if n == name and d == district and settlement_type in (None, t)
        )
        schedule = loc.get("schedule", {}).get(kind)
        if schedule is None:
            return loc, None
        if street is not None:
            key = next(k for k, label in loc["streets"] if label == street)
            return loc, sorted(areas[i]["name"] for i in schedule["streets"][key])
        if "area" in schedule:
            return loc, areas[schedule["area"]]["name"]
        return loc, schedule

    return lookup


def test_every_place_belongs_to_nemezio(dataset):
    data, _ = dataset
    assert {loc["district"] for loc in data["locations"]} == nemezio.PROVIDER.elderships
    assert all(loc["provider"] == "nemezio" for loc in data["locations"])
    assert all(a["provider"] == "nemezio" for a in data["areas"])
    assert all(f["provider"] == "nemezio" for f in data["files"])
    assert len(data["locations"]) == 372
    assert data["matching"]["household.none"] <= 25
    assert data["matching"]["unmatchedRows"] == 0


def test_one_row_lists_many_settlements(place):
    _, gaidunai = place("Gaidūnai", "Mickūnų")
    _, akmenyne = place("Akmenynė", "Mickūnų")
    assert gaidunai == akmenyne
    assert gaidunai.startswith("Akmenynė, Dėdoniškės, Mažeikiai (be Kairėnų ir Girios g.)")


def test_streets_left_out_with_be(place):
    # Household: "Mažeikiai (be Kairėnų ir Girios g.)" in one row, Kairėnų g. in another.
    _, kairenu = place("Mažeikiai", "Mickūnų", street="Kairėnų g.")
    _, aguonu = place("Mažeikiai", "Mickūnų", street="Aguonų g.")
    assert len(kairenu) == 1 and kairenu[0].endswith("Mažeikių k. (Kairėnų g.)")
    assert len(aguonu) == 1 and aguonu[0].startswith("Akmenynė, Dėdoniškės, Mažeikiai (be")


def test_a_street_left_out_only_in_part_stays_in(place):
    # "Grigaičiai (be Verslo, Svyrių, M. K. Oginskio, Pergalės g. iki 1-31)": Pergalės g. is in
    # both rows, Verslo g. only in the other.
    _, pergales = place("Grigaičiai", "Šatrininkų", "packaging", street="Pergalės g.")
    _, verslo = place("Grigaičiai", "Šatrininkų", "packaging", street="Verslo g.")
    assert len(pergales) == 2
    assert verslo == [
        "Karklėnai, Grigaičiai (Verslo, Svyrių, M. K. Oginskio, Pergalės g. nuo 35 iki galo)"
    ]


def test_genitive_with_type_and_streets(place):
    loc, rows = place("Mickūnai", "Mickūnų", street="Gaidūnų g.", settlement_type="mstl.")
    assert loc["type"] == "mstl."
    assert any(r.startswith("Akmenynė, Dėdoniškės") for r in rows)


def test_roman_numerals(place):
    for name in ("Uosininkai I", "Uosininkai II", "Uosininkai III"):
        _, row = place(name, "Mickūnų", "packaging")
        assert "Uosininkai I, II, III" in row
    # "Kuosinės I" (genitive) is Kuosinė I.
    _, row = place("Kuosinė I", "Medininkų", "packaging")
    assert row.startswith("Medininkai, Dvarčiai")


def test_garden_communities_are_a_street_choice(place):
    loc, rows = place("Kalveliai", "Marijampolio", street="SB „Atžalynas-2“")
    assert 'Kalveliai (SB "Atžalynas-2")' in rows
    _, village = place("Kalveliai", "Marijampolio")
    assert village not in rows
    # Packaging: 'Skaidiškės (Dunaikos, ...), Minsko pl., SB "Skaistė"'.
    _, rows = place("Skaidiškės", "Nemėžio", "packaging", street="SB „Skaistė“")
    assert rows == [next(r for r in rows if r.startswith("Skaidiškės (Dunaikos"))]


def test_a_garden_in_its_village_row_needs_no_street(place):
    # "Juočikiai, ..., Piktakonys, SB “Rasa“- Piktakonių k.": one row for all of Piktakonys.
    loc, row = place("Piktakonys", "Marijampolio")
    assert "SB “Rasa“" in row
    assert "streets" not in loc


def test_apartment_rows_are_a_choice_next_to_the_houses(place):
    _, rows = place("Juodšiliai", "Juodšilių", street="Šv. Uršulės g.")
    assert rows == [
        "Juodšiliai (A. Krepštul, Miško, Mokyklos, Pušų, Reisleravos, Šv. Uršulės, Žemaičių g.)",
        "Juodšilių k. (Uršulės g. 25)",
        "Juodšilių k. (Šv. Uršulės g. 21)",
    ]


def test_same_names_elsewhere_are_not_linked(dataset):
    # Kalveliai (Kalvelių sen.) and Kalveliai (Marijampolio sen.) get their own eldership's rows.
    data, _ = dataset
    areas = {a["id"]: a for a in data["areas"]}
    for loc in data["locations"]:
        for schedule in loc.get("schedule", {}).values():
            ids = [schedule.get("area")] + schedule.get("candidates", [])
            ids += [i for rows in schedule.get("streets", {}).values() for i in rows]
            assert all(areas[i]["district"] == loc["district"] for i in ids if i)


def test_rows_of_other_companies_are_ignored():
    # Nemenčinė's data never contains Nemėžio's elderships, even where a row names a village
    # that exists only there (Nemenčinės sen. "Zatišius" is not Rukainių sen. Zatišius).
    data, warnings = nemencine_build()
    assert {loc["district"] for loc in data["locations"]} <= NEMENCINE_ELDERSHIPS
    assert not any("provider" in loc for loc in data["locations"])
    assert not any("provider" in a for a in data["areas"])
    assert "not linked to any settlement: household: Zatišius" in warnings


def test_validation_thresholds():
    sources = [s for s in nemezio_sources() if s[0].kind == "household"]
    with pytest.raises(ValidationError, match="packaging"):
        build_dataset(sources, REGISTRY, today=date(2026, 11, 17), keep_days=31, source=NEMEZIO)


# --- one file, two companies ---------------------------------------------------


def nemencine_part():
    part, warnings = nemencine_build()
    return {**copy.deepcopy(part), "warnings": len(warnings)}


@functools.cache
def nemencine_build():
    return build_dataset(all_sources(), REGISTRY, today=date(2026, 10, 11), keep_days=31)


def fake(source: Source, download) -> Source:
    return dataclasses.replace(source, download=download)


def offline(error: Exception):
    def download(today, keep_days):
        raise error

    return download


def files_of(sources):
    return lambda today, keep_days: (sources, [])


def test_merged_file_keeps_old_apps_working(dataset):
    nemezio_part = {**dataset[0], "warnings": len(dataset[1])}
    merged = build.merge_parts(
        [(NEMENCINE.provider, nemencine_part()), (NEMEZIO.provider, nemezio_part)]
    )
    assert merged["schemaVersion"] == 1
    assert [p["id"] for p in merged["providers"]] == ["nemencine", "nemezio"]
    assert merged["providers"][1]["url"] == "https://www.nkom.lt/kita.html"
    ids = [loc["id"] for loc in merged["locations"]]
    assert len(ids) == len(set(ids)) == 686 + 372
    area_ids = [a["id"] for a in merged["areas"]]
    assert len(area_ids) == len(set(area_ids))
    # Individual houses first within each kind, as before.
    household = [a for a in merged["areas"] if a["kind"] == "household"]
    assert household[0]["group"] == "Individualūs namai"
    assert household[-1]["group"] == "Daugiabučiai namai"


def test_nemezio_failure_keeps_its_published_part(dataset):
    nemezio_part = {**dataset[0], "warnings": 4}
    published = build.merge_parts(
        [(NEMENCINE.provider, nemencine_part()), (NEMEZIO.provider, nemezio_part)]
    )
    sources = (
        fake(NEMENCINE, files_of(all_sources())),
        fake(NEMEZIO, offline(OSError("nkom.lt is down"))),
    )
    results = build.build_parts(sources, REGISTRY, date(2026, 10, 11), 31, lambda: published)
    assert results[0].error is None
    assert "nkom.lt is down" in results[1].error
    kept = results[1].part
    assert kept["generatedAt"] == nemezio_part["generatedAt"]
    assert len(kept["locations"]) == 372 and kept["warnings"] == 4
    merged = build.merge_parts([(r.provider, r.part) for r in results])
    assert len(merged["locations"]) == 686 + 372


def test_nemencine_failure_keeps_its_published_part(dataset):
    # Data published before there were several companies has no `providers`.
    published = nemencine_part()
    sources = (
        fake(NEMENCINE, offline(ValueError("new format"))),
        fake(NEMEZIO, files_of(nemezio_sources())),
    )
    results = build.build_parts(sources, REGISTRY, date(2026, 11, 17), 31, lambda: published)
    assert "new format" in results[0].error
    assert results[0].part["generatedAt"] == published["generatedAt"]
    assert len(results[0].part["locations"]) == 686
    assert results[1].error is None and len(results[1].part["locations"]) == 372


def test_nemezio_failure_without_published_part_leaves_it_out():
    published = nemencine_part()  # nothing of Nemėžio's published yet
    sources = (
        fake(NEMENCINE, files_of(all_sources())),
        fake(NEMEZIO, offline(OSError("timeout"))),
    )
    results = build.build_parts(sources, REGISTRY, date(2026, 10, 11), 31, lambda: published)
    assert results[1].part is None and results[1].error
    merged = build.merge_parts([(r.provider, r.part) for r in results if r.part])
    assert [p["id"] for p in merged["providers"]] == ["nemencine"]


def test_nemencine_failure_without_published_data_fails_the_build():
    sources = (fake(NEMENCINE, offline(OSError("down"))), fake(NEMEZIO, files_of([])))
    with pytest.raises(ValidationError, match="no published data"):
        build.build_parts(sources, REGISTRY, date(2026, 11, 17), 31, lambda: {"areas": []})


def test_strict_build_fails_on_any_provider():
    sources = (fake(NEMENCINE, files_of(all_sources())), fake(NEMEZIO, offline(OSError("x"))))
    with pytest.raises(OSError):
        build.build_parts(sources, REGISTRY, date(2026, 10, 11), 31, None)


def test_status_reports_each_company(tmp_path, dataset):
    nemezio_part = {**dataset[0], "warnings": 2}
    merged = build.merge_parts(
        [(NEMENCINE.provider, nemencine_part()), (NEMEZIO.provider, nemezio_part)]
    )
    merged["providers"][1]["generatedAt"] = "2026-11-15T04:20:00+00:00"
    (tmp_path / "schedule.json").write_text(json.dumps(merged), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_generated_timestamp_seconds{source="nemezio"} 1794716400' in text
    assert 'siuksliaveze_data_places{source="nemezio"} 372' in text
    assert 'siuksliaveze_data_places{source="nemencine"} 686' in text
    assert 'siuksliaveze_data_warnings{source="nemezio"} 2' in text
    assert 'siuksliaveze_data_areas{source="nemezio",kind="glass"} 45' in text

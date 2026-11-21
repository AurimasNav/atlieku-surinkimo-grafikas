"""Jonavos r.: the two pages of UAB „Jonavos paslaugos“, its nine PDFs (one per eldership and the
town's), their routes with mixed waste of each contract's frequency, and yesterday's rows for a
file that can't be read."""

import json
from datetime import date, timedelta
from urllib.parse import unquote

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, jonava, regions, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
STORAGE = "https://www.jonavospaslaugos.lt/storage/"
# The files the pages link, by their names, and their copies in fixtures/jonava.
COPIES = {
    "2026-m.--grafikas-Bukonių-seniūnija.pdf": "bukoniu.pdf",
    "2026-m.--grafikas-buvusios-Ruklos-seniūnija.pdf": "ruklos.pdf",
    "2026-m.--grafikas-Kulvos-seniūnija.pdf": "kulvos.pdf",
    "2026-m.--grafikas-Upninkų-seniūnija.pdf": "upninku.pdf",
    "2026-m.--grafikas-Užusalių-seniūnija.pdf": "uzusaliu.pdf",
    "2026-m.--grafikas-Šilų-seniūnija.pdf": "silu.pdf",
    "2026-m.--grafikas-Šveicarijos-seniūnija.pdf": "sveicarijos.pdf",
    "2026-m.--grafikas-Žeimių-seniūnija.pdf": "zeimiu.pdf",
    "Maketas-grafikas-2026-Derinimui-2.pdf": "jonavos-m.pdf",
}
REGISTRY = "jonava/registry-jonavos-r-2026-11-21.json"
TWICE, ONCE, WEEKLY = (
    "2 kartus per mėnesį (pagal sutartį)",
    "Kartą per mėnesį (pagal sutartį)",
    "Kartą per savaitę (pagal sutartį)",
)


def serve(url, timeout=0):
    """The saved pages and files, as jonava.http.get."""
    if url == jonava.PAGE_URL:
        return fixture("jonava/page.html")
    if url == jonava.TOWN_PAGE_URL:
        return fixture("jonava/page-town.html")
    return fixture(f"jonava/{COPIES[unquote(url.rsplit('/', 1)[-1])]}")


def parsed(copy, section, year=2026):
    file = jonava.ScheduleFile("household", f"{STORAGE}{copy}", copy, group=section, year=year)
    return jonava.parse_file(file, fixture(f"jonava/{copy}")).areas


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the pages, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(jonava.http, "get", serve)
        files, warnings = jonava.download(TODAY, 366)
        registry = Registry.load(FIXTURES / REGISTRY)
        data, more = build_dataset(files, registry, TODAY, 366, jonava.source())
    return files, data, warnings + more


def place(data, name, kind=None):
    return next(
        loc for loc in data["locations"] if loc["name"] == name and kind in (None, loc["type"])
    )


def rows(data, name, waste="household", kind=None):
    """The rows of a place by their group (None for one row)."""
    schedule = place(data, name, kind)["schedule"][waste]
    ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    by_id = {a["id"]: a for a in data["areas"]}
    return {by_id[i].get("group"): by_id[i] for i in ids}


# --- the pages ---------------------------------------------------------------


def test_finds_a_file_per_eldership_and_the_towns_by_their_links():
    files = jonava.find_files(fixture("jonava/page.html").decode("utf-8"), jonava.PAGE_URL)
    files += jonava.find_files(
        fixture("jonava/page-town.html").decode("utf-8"), jonava.TOWN_PAGE_URL
    )
    assert sorted(f.file_name for f in files) == sorted(COPIES)
    # "Rūklos sen. 2026 m." is the former Ruklos sen.
    assert sorted(f.group for f in files) == sorted(jonava.SECTIONS)
    assert {(f.kind, f.year) for f in files} == {("household", 2026)}
    # Not the rules for people with disabilities, nor the other pages.
    assert all(f.url.startswith(STORAGE) for f in files)


def test_next_years_file_of_an_eldership_is_read_next_to_this_years():
    def file(section, year):
        return jonava.ScheduleFile(
            "household", f"{STORAGE}{section}{year}.pdf", "x", group=section, year=year
        )

    files = [file(s, 2026) for s in jonava.SECTIONS] + [file("Kulvos", 2027), file("Šilų", 2025)]
    chosen, warnings = jonava.select_files(files, TODAY)
    assert sorted(f.year for f in chosen if f.group == "Kulvos") == [2026, 2027]
    assert len(chosen) == 10 and warnings == []
    with pytest.raises(build.ValidationError, match="Žeimių"):
        jonava.select_files([f for f in files if f.group != "Žeimių"], TODAY)


def test_a_link_and_a_file_name_of_other_years_fail():
    html = f'<a href="{STORAGE}1/2027-m.--grafikas-Kulvos-seniūnija.pdf">Kulvos sen. 2026 m.</a>'
    with pytest.raises(ValueError, match="a file of 2027, its link says 2026"):
        jonava.find_files(html, jonava.PAGE_URL)


# --- the tables ------------------------------------------------------------------


def test_mixed_waste_of_each_frequency_packaging_and_glass():
    areas = {(a.kind, a.group): a for a in parsed("bukoniu.pdf", "Bukonių")}
    assert set(areas) == {
        ("household", TWICE),
        ("household", ONCE),
        ("packaging", None),
        ("glass", None),
    }
    twice, once = areas[("household", TWICE)], areas[("household", ONCE)]
    # "2; 16; 30 | 13; 27 | ..." and "2; 30 | 27 | ...": Fridays.
    assert sorted(twice.dates)[:3] == [date(2026, 1, 2), date(2026, 1, 16), date(2026, 1, 30)]
    assert len(twice.dates) == 26 and len(once.dates) == 13 and once.dates < twice.dates
    assert twice.weekday == once.weekday == "Penktadienis"
    # "6 | | | 15 | | | 10 | | | 2 |": glass four times a year.
    assert sorted(areas[("glass", None)].dates) == [
        date(2026, 1, 6),
        date(2026, 4, 15),
        date(2026, 7, 10),
        date(2026, 10, 2),
    ]
    assert twice.name.startswith("Bukonių sen.: Biržuliai, Bukonys,")
    assert twice.name.endswith("Dovydonys Šilų s. Vainiai")
    assert {a.district for a in areas.values()} == {"Jonavos r."}


def test_the_towns_weekly_mixed_waste():
    areas = {(a.kind, a.group): a for a in parsed("jonavos-m.pdf", "Jonavos miesto")}
    weekly = areas[("household", WEEKLY)]
    # "Kiekvieną KETVIRTADIENĮ (DĖMESIO: vietoje sausio 1 d. konteineriai bus aptarnaujami sausio
    # 3 d.)": every Thursday of 2026, but 1 January is on the 3rd.
    thursdays = {date(2026, 1, 1) + timedelta(days=7 * week) for week in range(53)}
    assert weekly.dates == (thursdays - {date(2026, 1, 1)}) | {date(2026, 1, 3)}
    assert weekly.weekday == "Ketvirtadienis"
    assert len(areas) == 5  # mixed waste of three frequencies, packaging and glass


@pytest.mark.parametrize(
    ("label", "group"),
    [
        ("Komunalinės (buitinės) atliekos (pagal sutartį 2 k/mėn.)", TWICE),
        ("Komunalinės (buitinės) atliekos (pagal sutartį 1 k/mėn.)", ONCE),
        ("Komunalinės (buitinės) atliekos (pagal sutartį 1 k/sav.)", WEEKLY),
        ("Komunalinės (buitinės) atliekos", None),
    ],
)
def test_the_frequency_of_a_contract(label, group):
    assert jonava.frequency(label) == group


@pytest.mark.parametrize(
    "text",
    [
        "Kiekvieną dieną",
        "Kiekvieną KETVIRTADIENĮ, išskyrus šventes",
        "Kiekvieną KETVIRTADIENĮ (DĖMESIO: vietoje sausio 2 d. konteineriai bus aptarnaujami "
        "sausio 3 d.)",
    ],
)
def test_anything_else_than_a_weekly_rule_fails(text):
    with pytest.raises(ValueError):
        jonava._weekly(text, 2026, "x")


def test_a_title_of_another_eldership_or_year_fails():
    with pytest.raises(ValueError, match="the title says Bukonių 2026, the link Kulvos 2026"):
        parsed("bukoniu.pdf", "Kulvos")
    with pytest.raises(ValueError, match="the link Bukonių 2027"):
        parsed("bukoniu.pdf", "Bukonių", year=2027)


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 266
    # Every place with mixed waste has two rows or three (the town's): the app asks.
    assert (stats["household.ambiguous"], stats["household.none"]) == (189, 77)
    assert (stats["packaging.single"], stats["glass.single"]) == (189, 189)
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 19, "packaging": 9, "glass": 9}
    # The garden communities, once per waste type.
    assert len(warnings) == 15
    assert all(": SB „" in w for w in warnings)


def test_a_village(built):
    _, data, _ = built
    # Biržuliai, Bukonių sen.
    found = rows(data, "Biržuliai")
    assert set(found) == {TWICE, ONCE}
    twice, once = found[TWICE]["dates"], found[ONCE]["dates"]
    assert (len(twice), twice[0], twice[-1]) == (26, "2026-01-02", "2026-12-18")
    assert (len(once), once[0], once[-1]) == (13, "2026-01-02", "2026-12-04")


def test_the_town_and_the_places_of_other_elderships(built):
    _, data, _ = built
    # "Jonavos miestas": the whole town, every street.
    town = place(data, "Jonava", "m.")
    assert set(rows(data, "Jonava", kind="m.")) == {WEEKLY, TWICE, ONCE}
    assert "streets" not in town and "streets" not in town["schedule"]["household"]
    # "Kulvos s. - Paupė, Melnytėlė": Melnytėlė is of Jonavos sen. in the register.
    assert place(data, "Melnytėlė")["district"] == "Jonavos"
    assert set(rows(data, "Melnytėlė")) == {WEEKLY, TWICE, ONCE}
    # "Šilų s. - Liepa, ... Laukogaliai": Liepos (Šilų sen.) and Laukagaliai (Jonavos sen.).
    for name in ("Liepos", "Laukagaliai"):
        assert set(rows(data, name)) == {WEEKLY, TWICE, ONCE}
    # "Šilų s. Vainiai" in Bukonių sen.'s file.
    assert next(iter(rows(data, "Vainiai").values()))["name"].startswith("Bukonių sen.:")
    # The former Ruklos sen.: "Ruklos k., Ruklos miestelis".
    for kind in ("k.", "mstl."):
        found = rows(data, "Rukla", kind=kind)
        assert next(iter(found.values()))["name"].startswith("Ruklos sen.:")
    # "Vašeikiai" is Vešeikiai, "Skryniai" Skrynės: near names in their elderships.
    assert rows(data, "Vešeikiai") and rows(data, "Skrynės")


# --- a file that can't be read, and the folder -----------------------------------


def test_a_file_that_cant_be_read_keeps_yesterdays_rows(built):
    files, data, _ = built
    published = merge_parts(
        [(jonava.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-20"})],
        jonava.PAGE_URL,
    )
    town = next(f for f, _ in files if f.group == "Jonavos miesto")
    result = jonava.parse_or_keep(town, b"", lambda: published)
    assert sorted((a.kind, a.group or "") for a in result.areas) == [
        ("glass", ""),
        ("household", TWICE),
        ("household", ONCE),
        ("household", WEEKLY),
        ("packaging", ""),
    ]
    assert "yesterday's 5 rows of Jonavos miesto sen. are kept" in result.warnings[0]
    with pytest.raises(ValueError, match="not downloaded"):
        jonava.parse_or_keep(town, b"", None)


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(jonava.http, "get", serve)
    monkeypatch.setattr(jonava.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(jonava.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "jonavos-r"
    assert jonava.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["jonava"]
    assert regions.region(tmp_path, out) == {
        "path": "jonavos-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["jonava"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="jonava"} 189' in text

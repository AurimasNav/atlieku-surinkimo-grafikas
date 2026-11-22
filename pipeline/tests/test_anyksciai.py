"""Anykščių r.: the page of UAB „Anykščių komunalinis ūkis“, its two PDFs (the villages' and the
town's), a revision of a year's file, the routes' places and yesterday's rows for a file that
can't be read."""

import json
from datetime import date

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import anyksciai, build, regions, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
UPLOADS = "http://anykom.lt/assets/uploads"
VILLAGES = f"{UPLOADS}/2026/03/421f0ee1.pdf"
TOWN = f"{UPLOADS}/2025/12/02c3dd29.pdf"
# The files the page links, and their copies in fixtures/anyksciai.
COPIES = {VILLAGES: "kaimai-2026.pdf", TOWN: "miestas-2026.pdf"}
REGISTRY = "anyksciai/registry-anyksciu-r-2026-11-21.json"
RIGHT = "Anykščių miestas, DEŠINYSIS UPĖS KRANTAS"
LEFT = "Anykščių miestas, KAIRYSIS UPĖS KRANTAS"


def serve(url, timeout=0):
    """The saved page and files, as anyksciai.http.get."""
    if url == anyksciai.PAGE_URL:
        return fixture("anyksciai/page.html")
    return fixture(f"anyksciai/{COPIES[url]}")


def file(url, group="", year=2026, uploaded=(2026, 3)):
    name = url.rsplit("/", 1)[-1]
    return anyksciai.ScheduleFile("household", url, name, group=group, year=year, uploaded=uploaded)


def parsed(url, group, year=2026):
    return anyksciai.parse_file(file(url, group, year), fixture(f"anyksciai/{COPIES[url]}"))


def by_name(areas, prefix):
    return {a.kind: a for a in areas if a.name.startswith(prefix)}


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(anyksciai.http, "get", serve)
        files, warnings = anyksciai.download(TODAY, 366)
        registry = Registry.load(FIXTURES / REGISTRY)
        data, more = build_dataset(files, registry, TODAY, 366, anyksciai.source())
    return files, data, warnings + more


def place(data, name, district=None, kind=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and district in (None, loc["district"])
        and kind in (None, loc["type"])
    )


def rows(data, name, waste="household", district=None, kind=None):
    """The names of the rows of a place."""
    schedule = place(data, name, district, kind)["schedule"][waste]
    ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    by_id = {a["id"]: a for a in data["areas"]}
    return [by_id[i]["name"] for i in ids]


# --- the page ----------------------------------------------------------------


def test_finds_the_villages_and_the_towns_file_by_their_links():
    files = anyksciai.find_files(fixture("anyksciai/page.html").decode("utf-8"))
    assert [(f.url, f.group, f.year, f.uploaded) for f in files] == [
        (TOWN, anyksciai.TOWN, 2026, (2025, 12)),
        (VILLAGES, "", 2026, (2026, 3)),
    ]
    # Not bulky waste nor the washing of containers.
    assert {f.kind for f in files} == {"household"}


def test_a_revision_of_a_years_file_is_read_in_place_of_the_first():
    # The villages' 2026 file was first uploaded in December 2025; the page linked the one of
    # March 2026 in its place, by the same text. Linked next to each other, either way round.
    text = "MIŠRIŲ IR ANTRINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 M."
    first = f'<p><a href="{UPLOADS}/2025/12/421f0ee1-2.pdf">{text}</a></p>'
    revised = f'<p><a href="{VILLAGES}">{text}</a></p>'
    town = (
        f'<p><a href="{TOWN}">MIŠRIŲ, ANTRINIŲ IR BIOLOGINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 '
        "M.</a> (Anykščių miestas)</p>"
    )
    for html in (first + revised + town, revised + first + town):
        chosen, warnings = anyksciai.select_files(anyksciai.find_files(html), TODAY)
        assert [f.url for f in chosen] == [VILLAGES, TOWN]
        assert warnings == ["421f0ee1-2.pdf: not read, 421f0ee1.pdf is a newer schedule for 2026"]


def test_links_without_the_text_of_a_schedule_are_not_read():
    # In 2025 the number before the title linked an older file ("1. "); the town's file is told
    # by "(Anykščių miestas)" after its link.
    html = (
        f'<p><a href="{UPLOADS}/2024/10/1e6bb88a.pdf">1. </a> <a href="{TOWN}">MIŠRIŲ IR '
        "ANTRINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 M.</a> (Anykščių miestas)</p>"
        f'<p><a href="{UPLOADS}/2026/09/1909866d.pdf">3. STAMBIAGABARIČIŲ ATLIEKŲ IŠVEŽIMO '
        "GRAFIKAS</a></p>"
    )
    assert [(f.url, f.group) for f in anyksciai.find_files(html)] == [(TOWN, anyksciai.TOWN)]


def test_next_years_files_are_read_next_to_this_years():
    files = [
        file(VILLAGES),
        file(TOWN, anyksciai.TOWN),
        file(f"{UPLOADS}/2026/12/a.pdf", year=2027, uploaded=(2026, 12)),
        file(f"{UPLOADS}/2025/01/b.pdf", year=2025, uploaded=(2025, 1)),
    ]
    chosen, warnings = anyksciai.select_files(files, TODAY)
    assert sorted((f.group, f.year) for f in chosen) == [
        ("", 2026),
        ("", 2027),
        (anyksciai.TOWN, 2026),
    ]
    assert warnings == []
    with pytest.raises(build.ValidationError, match="no schedule of Anykščių miestas"):
        anyksciai.select_files(files[:1], TODAY)


# --- the routes ------------------------------------------------------------------


def test_the_villages_routes():
    areas = parsed(VILLAGES, "").areas
    assert sorted({a.kind for a in areas}) == ["glass", "household", "packaging"]
    # 23 routes: Troškūnai, Kavarskas, Naujieji Elmininkai and Svėdasai on their own, on the
    # day of the villages of the same number ("1. Vėjeliškis, ...", "1. Troškūnai, ...").
    assert len({a.name for a in areas}) == 23 and len(areas) == 69
    route = by_name(areas, "Vėjeliškis, Piktagalys")
    assert route["household"].name == "Vėjeliškis, Piktagalys, Naujonys, Zablackai"
    # "8 5 5 2 7 4 2 6 3 1 5 3": the first Thursday of the month.
    household = sorted(route["household"].dates)
    assert (household[0], household[-1], len(household)) == (
        date(2026, 1, 8),
        date(2026, 12, 3),
        12,
    )
    assert route["household"].weekday == "Ketvirtadienis"
    assert route["packaging"].dates == route["household"].dates
    # "| | 5 | | | 4 | | | 3 | | | 3": glass in March, June, September and December.
    assert sorted(route["glass"].dates) == [
        date(2026, 3, 5),
        date(2026, 6, 4),
        date(2026, 9, 3),
        date(2026, 12, 3),
    ]
    # "8,22": Troškūnai twice in January.
    troskunai = by_name(areas, "Troškūnai")["household"].dates
    assert {date(2026, 1, 8), date(2026, 1, 22)} <= troskunai and len(troskunai) == 13
    # Gyliai, revised in March: packaging "5 2 2,30 _ 4 1,29 _ 3 7 5 3 7", no April or July.
    gyliai = by_name(areas, "Gylių k.")["packaging"].dates
    assert {d.month for d in gyliai} == {1, 2, 3, 5, 6, 8, 9, 10, 11, 12}
    assert {date(2026, 3, 30), date(2026, 6, 29), date(2026, 9, 7)} <= gyliai
    assert {a.district for a in areas} == {"Anykščių r."}


def test_the_towns_routes():
    areas = parsed(TOWN, anyksciai.TOWN).areas
    assert sorted((a.name, a.kind) for a in areas) == [
        (RIGHT, kind) for kind in ("glass", "green", "household", "packaging")
    ] + [(LEFT, kind) for kind in ("glass", "green", "household", "packaging")]
    right = by_name(areas, RIGHT)
    # "12,26 9 9 13 ...": once a month, twice in January, on Mondays.
    assert sorted(right["household"].dates)[:3] == [
        date(2026, 1, 12),
        date(2026, 1, 26),
        date(2026, 2, 9),
    ]
    assert right["household"].weekday == "Pirmadienis"
    # Biodegradable waste: twice a month from April to October.
    assert len(right["green"].dates) == 19


def test_a_heading_of_another_year_or_file_fails():
    with pytest.raises(ValueError, match="isn't the file its link says"):
        parsed(TOWN, "")
    with pytest.raises(ValueError, match="isn't the file its link says"):
        parsed(VILLAGES, anyksciai.TOWN)
    with pytest.raises(ValueError, match=r"a schedule of \[2026\], its link says 2027"):
        parsed(VILLAGES, "", year=2027)


def test_a_day_the_month_doesnt_have_fails():
    block = anyksciai._Block(["1. Gyliai"], "x", months=[float(i) for i in range(12)])
    block.labels = [anyksciai._Label("household", 0, 10, ["MIŠRIŲ"])]
    block.rows = [(5, {2: "30"})]
    with pytest.raises(ValueError, match="month 2 of 2026 has no day 30"):
        block.dates(2026)


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 749
    # The town's two banks, and three villages two routes name: the app asks.
    assert (stats["household.single"], stats["household.ambiguous"]) == (276, 4)
    assert (stats["packaging.single"], stats["glass.single"]) == (276, 276)
    assert (stats["green.ambiguous"], stats["green.none"]) == (1, 748)
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 25, "packaging": 25, "glass": 25, "green": 2}
    # Places the register doesn't have, once per waste type of their route.
    unknown = ("Šaltupio sodai", "Šiauliai", "Aknystų SGN.", "Krivickai")
    assert sorted(warnings) == sorted(
        f"not a settlement or a street: {kind}: Anykščių r.: {name}"
        for name in unknown
        for kind in ("household", "packaging", "glass")
    )


def test_the_town(built):
    _, data, _ = built
    # "Anykščių miestas, DEŠINYSIS/KAIRYSIS UPĖS KRANTAS": all of the town; the app asks which
    # bank of the Šventoji.
    town = place(data, "Anykščiai", kind="m.")
    assert "streets" not in town
    for waste in ("household", "packaging", "glass", "green"):
        assert sorted(rows(data, "Anykščiai", waste, kind="m.")) == [RIGHT, LEFT]
    # The village of the same name next to it isn't in the files.
    assert "schedule" not in place(data, "Anykščiai", kind="vs.")


def test_villages(built):
    _, data, _ = built
    # Acceptance: Šeimyniškėliai (Anykščių sen.), route 10, mixed waste on 14 January ... 9
    # December 2026, a Wednesday a month.
    (name,) = rows(data, "Šeimyniškėliai")
    assert name.startswith("Šeimyniškėliai, Pavariai, Niūronys")
    area = next(a for a in data["areas"] if a["name"] == name and a["kind"] == "household")
    assert (area["dates"][0], area["dates"][-1], len(area["dates"])) == (
        "2026-01-14",
        "2026-12-09",
        12,
    )
    # Places of the register by other names: Senieji Elmininkai, Pavariai.
    for village in ("Elmininkai I", "Elmininkai II", "Pavarės II"):
        assert rows(data, village) == [name]
    # "I Svirnai", "II Svirnai".
    assert rows(data, "Svirnai I") == rows(data, "Svirnai II")


def test_places_of_one_name(built):
    _, data, _ = built
    # "Pienionys, Jokūbava, Ažuožeriai" (Anykščių sen.) and "Mackeliškiai, Pienionys" (Kavarsko
    # sen.): of the eldership of the places next to them.
    assert rows(data, "Pienionys", district="Anykščių")[0].startswith("Pienionys, Jokūbava")
    assert rows(data, "Pienionys", district="Kavarsko")[0].startswith("Varšauka,")
    assert rows(data, "Jokūbava", district="Anykščių")[0].startswith("Pienionys, Jokūbava")
    assert "schedule" not in place(data, "Jokūbava", district="Kavarsko")
    # "Kavarskas mst." is the town; "Kavarskas" in another route the village.
    assert rows(data, "Kavarskas", kind="m.") == ["Kavarskas mst."]
    assert rows(data, "Kavarskas", kind="vs.")[0].startswith("Pienionys, Jokūbava")
    # "II Kurkliai" in one route, "Kurkliai" in another: Kurkliai II is the first's, Kurkliai I
    # and the town the other's.
    assert rows(data, "Kurkliai II")[0].startswith("Liūdiškiai,")
    for name, kind in (("Kurkliai I", "k."), ("Kurkliai", "mstl.")):
        assert rows(data, name, kind=kind)[0].startswith("Šližiai,")
    # A village two routes name: the app asks.
    assert len(rows(data, "Bajorai")) == 2


# --- a file that can't be read, and the folder -----------------------------------


def test_a_file_that_cant_be_read_keeps_yesterdays_rows(built):
    files, data, _ = built
    published = merge_parts(
        [(anyksciai.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-20"})],
        anyksciai.PAGE_URL,
    )
    town = next(f for f, _ in files if f.group == anyksciai.TOWN)
    result = anyksciai.parse_or_keep(town, b"", lambda: published)
    assert sorted({a.name for a in result.areas}) == [RIGHT, LEFT]
    assert len(result.areas) == 8
    assert "yesterday's 8 rows of Anykščių miestas are kept" in result.warnings[0]
    villages = next(f for f, _ in files if f.group == "")
    assert len(anyksciai.parse_or_keep(villages, b"", lambda: published).areas) == 69
    with pytest.raises(ValueError, match="not downloaded"):
        anyksciai.parse_or_keep(town, b"", None)


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(anyksciai.http, "get", serve)
    monkeypatch.setattr(anyksciai.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(anyksciai.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "anyksciu-r"
    assert anyksciai.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["anyksciai"]
    assert regions.region(tmp_path, out) == {
        "path": "anyksciu-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["anyksciai"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="anyksciai"} 280' in text

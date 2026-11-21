"""Raseinių r.: the page of UAB „Raseinių komunalinės paslaugos“, its 25 PDFs (a mixed waste and a
packaging file per eldership, one green waste file), their routes, and yesterday's rows for a
file that can't be read."""

import json
from datetime import date
from urllib.parse import unquote

import pytest
from pdfplumber.utils.exceptions import PdfminerException
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, raseiniai, regions, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
UPLOADS = "https://www.rkp.lt/uploads/"
FOLDER = f"{UPLOADS}2026%20met%C5%B3%20atliek%C5%B3%20surinkimo%20grafikai/"
# The files the page links, by their names, and their copies in fixtures/raseiniai.
COPIES = {
    "Ariogalos m. mišrios komunalinės atliekos.pdf": "ariogalos-m-mka.pdf",
    "Ariogalos m. pakuočių atliekos.pdf": "ariogalos-m-pak.pdf",
    "Ariogalos sen. mišrios komunalinės atliekos.pdf": "ariogalos-mka.pdf",
    "Ariogalos sen. pakuočių atliekos.pdf": "ariogalos-pak.pdf",
    "Betygalos sen. mišrios komunalinės atliekos.pdf": "betygalos-mka.pdf",
    "Betygalos sen. pakuočių atliekos.pdf": "betygalos-pak.pdf",
    "Biologiškai skaidžios atliekos.pdf": "zalios.pdf",
    "Girkalnio sen. mišrios komunalinės atliekos.pdf": "girkalnio-mka.pdf",
    "Girkalnio sen. pakuočių atliekos.pdf": "girkalnio-pak.pdf",
    "Kalnujų sen. mišrios komunalinės atliekos.pdf": "kalnuju-mka.pdf",
    "Kalnujų sen. pakuočių atliekos.pdf": "kalnuju-pak.pdf",
    "Nemakščių sen. mišrios komunalinės atliekos.pdf": "nemaksciu-mka.pdf",
    "Nemakščių sen. pakuočių atliekos.pdf": "nemaksciu-pak.pdf",
    "Pagojukų sen. mišrios komunalinės atliekos.pdf": "pagojuku-mka.pdf",
    "Pagojukų sen. pakuočių atliekos.pdf": "pagojuku-pak.pdf",
    "Paliepių sen. mišrios komunalinės atliekos.pdf": "paliepiu-mka.pdf",
    "Paliepių sen. pakuočių atliekos.pdf": "paliepiu-pak.pdf",
    "Raseinių m. MKA.pdf": "raseiniu-m-mka.pdf",
    "Raseinių m. pakuočių atliekos.pdf": "raseiniu-m-pak.pdf",
    "Raseinių sen. mišrios komunalinės atliekos.pdf": "raseiniu-mka.pdf",
    "Raseinių sen. pakuočių atliekos.pdf": "raseiniu-pak.pdf",
    "Viduklės sen. mišrios komunalinės atliekos.pdf": "vidukles-mka.pdf",
    "Viduklės sen. pakuočių atliekos.pdf": "vidukles-pak.pdf",
    "Šiluvos sen. mišrios komunalinės atliekos.pdf": "siluvos-mka.pdf",
    "Šiluvos sen. pakuočių atliekos.pdf": "siluvos-pak.pdf",
}
REGISTRY = "raseiniai/registry-raseiniu-r-2026-11-21.json"


def serve(url, timeout=0):
    """The saved page and files, as raseiniai.http.get."""
    if url == raseiniai.PAGE_URL:
        return fixture("raseiniai/page.html")
    return fixture(f"raseiniai/{COPIES[unquote(url.rsplit('/', 1)[-1])]}")


def registry():
    return Registry.load(FIXTURES / REGISTRY)


def parsed(copy, kind, eldership, year=2026):
    file = raseiniai.ScheduleFile(kind, f"{FOLDER}{copy}", copy, group=eldership, year=year)
    return raseiniai.parse_file(file, fixture(f"raseiniai/{copy}")).areas


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(raseiniai.http, "get", serve)
        files, warnings = raseiniai.download(TODAY, 366)
        data, more = build_dataset(files, registry(), TODAY, 366, raseiniai.source())
    return files, data, warnings + more


def place(data, name, kind=None):
    return next(
        loc for loc in data["locations"] if loc["name"] == name and kind in (None, loc["type"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def street_rows(data, settlement, waste, label):
    """The rows of a street; None if it's left to the app."""
    location = place(data, settlement, "m.")
    key = next(key for key, text in location["streets"] if text == label)
    return location["schedule"][waste]["streets"].get(key)


# --- the page ----------------------------------------------------------------


def test_finds_a_file_per_eldership_and_kind_by_the_texts_of_the_page():
    files = raseiniai.find_files(fixture("raseiniai/page.html").decode("utf-8"))
    assert sorted(f.file_name for f in files) == sorted(COPIES)
    kinds = {(f.group, f.kind) for f in files}
    assert kinds == {(e, k) for e in raseiniai.ELDERSHIPS for k in ("household", "packaging")} | {
        ("", "green")
    }
    # Links relative to <base href="https://www.rkp.lt/">, encoded.
    assert all(f.url.startswith(UPLOADS) and " " not in f.url for f in files)
    # The year of the folder; Raseinių m. MKA.pdf is in none.
    town = next(f for f in files if f.file_name == "Raseinių m. MKA.pdf")
    assert town.year is None and town.group == "Raseinių miesto"
    assert {f.year for f in files if f is not town} == {2026}


def test_a_file_outside_the_folder_of_its_year_gets_its_workbooks_year(built):
    files, _, warnings = built
    assert len(files) == 25
    town = next(f for f, _ in files if f.file_name == "Raseinių m. MKA.pdf")
    # "2026 metų UAB RKP atliekų surinkimo grafikas.xlsx", the PDF's title.
    assert town.year == 2026
    assert not any("year" in w or "not read" in w for w in warnings)


def test_next_years_files_are_read_next_to_this_years():
    def file(year, group="Betygalos", kind="household"):
        return raseiniai.ScheduleFile(
            kind, f"{UPLOADS}{year}/{group}.pdf", "x.pdf", group=group, year=year
        )

    everything = [
        file(2026, e, k) for e in raseiniai.ELDERSHIPS for k in ("household", "packaging")
    ]
    everything += [file(2026, "", "green"), file(2027), file(2025, "Kalnujų")]
    chosen, warnings = raseiniai.select_files(everything, TODAY)
    betygala = [f.year for f in chosen if (f.group, f.kind) == ("Betygalos", "household")]
    assert betygala == [2026, 2027] and len(chosen) == 26 and warnings == []


def test_a_page_without_a_file_of_every_eldership_fails():
    files = raseiniai.find_files(fixture("raseiniai/page.html").decode("utf-8"))
    files = [f for f in files if (f.group, f.kind) != ("Viduklės", "packaging")]
    for file in files:
        file.year = 2026
    with pytest.raises(build.ValidationError, match="Viduklės packaging"):
        raseiniai.select_files(files, TODAY)


def test_bulky_waste_and_the_rules_are_not_read():
    page = fixture("raseiniai/page.html").decode("utf-8")
    names = {f.file_name for f in raseiniai.find_files(page)}
    assert "2026 metų GRAFIKAS specifinių atliekų surinkimo.pdf" not in names
    assert "Atliekų tvarkymo taisyklės..pdf" not in names


# --- the blocks ------------------------------------------------------------------


def test_mixed_waste_once_a_month_in_the_villages():
    areas = parsed("betygalos-mka.pdf", "household", "Betygalos")
    assert len(areas) == 4 and {a.kind for a in areas} == {"household"}
    armonai = next(a for a in areas if a.name.startswith("Betygalos sen.: Armonų k., Berteškių"))
    # "14 11 12 08 13 10 08 12 09 14 11 09"
    assert sorted(armonai.dates)[:3] == [date(2026, 1, 14), date(2026, 2, 11), date(2026, 3, 12)]
    assert len(armonai.dates) == 12 and max(armonai.dates) == date(2026, 12, 9)
    assert {a.district for a in areas} == {"Raseinių r."}
    assert {a.provider for a in areas} == {"raseiniai"}


def test_packaging_and_four_glass_pickups_by_the_columns_of_their_days():
    areas = {a.kind: a for a in parsed("betygalos-pak.pdf", "packaging", "Betygalos")}
    assert len(areas["packaging"].dates) == 12
    # "Stiklo pakuotė 19 21 14 19" in February, May, August and November.
    assert sorted(areas["glass"].dates) == [
        date(2026, 2, 19),
        date(2026, 5, 21),
        date(2026, 8, 14),
        date(2026, 11, 19),
    ]


def test_a_file_without_its_elderships_heading_gets_the_links():
    # "Raseinių sen. mišrios komunalinės atliekos.pdf" starts with its first route's places.
    areas = parsed("raseiniu-mka.pdf", "household", "Raseinių")
    assert len(areas) == 6 and all(a.name.startswith("Raseinių sen.: ") for a in areas)


def test_the_green_waste_file_has_the_blocks_of_several_elderships():
    areas = parsed("zalios.pdf", "green", "")
    assert len(areas) == 20 and {a.kind for a in areas} == {"green"}
    sections = {a.name.split(":")[0] for a in areas}
    assert {"Raseinių miesto sen.", "Ariogalos miesto sen.", "Šiluvos sen."} <= sections
    # The block at the foot of page 1, whose dates pdfplumber's table finder loses.
    foot = next(a for a in areas if a.name.startswith("Raseinių sen.: Arškainių k."))
    assert len(foot.dates) == 14
    assert min(foot.dates) == date(2026, 4, 21) and max(foot.dates) == date(2026, 11, 3)
    # From April to November.
    assert {d.month for a in areas for d in a.dates} == set(range(4, 12))


def test_the_year_of_the_folder_must_agree_with_the_workbooks():
    with pytest.raises(ValueError, match="a file of 2027 printed from a 2026 workbook"):
        parsed("kalnuju-mka.pdf", "household", "Kalnujų", year=2027)


def test_the_heading_of_another_eldership_fails():
    with pytest.raises(ValueError, match="Betygalos sen. in the file of Girkalnio"):
        parsed("betygalos-mka.pdf", "household", "Girkalnio")


def test_a_waste_type_the_files_kind_doesnt_have_fails():
    with pytest.raises(ValueError, match=r"a row of \['packaging'\]"):
        parsed("betygalos-pak.pdf", "household", "Betygalos")


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 554
    assert (stats["household.single"], stats["household.byStreet"]) == (552, 2)
    assert stats.get("household.none", 0) == 0
    assert (stats["packaging.single"] + stats["packaging.byStreet"], stats["glass.none"]) == (
        122,
        432,
    )
    assert stats["green.single"] + stats["green.byStreet"] == 30
    kinds = {a["kind"]: 0 for a in data["areas"]}
    for area in data["areas"]:
        kinds[area["kind"]] += 1
    assert kinds == {"household": 43, "packaging": 25, "glass": 25, "green": 20}
    assert len(warnings) == 13


def test_a_village(built):
    _, data, _ = built
    # Armonai, Betygalos sen.: "Armonų k., Berteškių k., Betygalos mstl., ...".
    dates = row(data, place(data, "Armonai")["schedule"]["household"]["area"])["dates"]
    assert (len(dates), dates[0], dates[-1]) == (12, "2026-01-14", "2026-12-09")


def test_the_towns_streets(built):
    _, data, _ = built
    # Parts of a street: choices for it ("Vytauto g. nuo Nr. 36" and "Vytauto g. Nr. 1-36").
    vytauto = street_rows(data, "Ariogala", "household", "Vytauto g.")
    assert [row(data, r)["dates"][0] for r in vytauto] == ["2026-01-07", "2026-01-14"]
    # No route has the whole street ("Bažnyčios g. (nuo Kosmonautų g. iki Vilniaus g.)", "(nuo
    # Vilniaus g. iki Žvyryno g.)"): its parts' routes and the town's other one.
    baznycios = street_rows(data, "Raseiniai", "household", "Bažnyčios g.")
    parts = [r for r in baznycios if "Bažnyčios g. (nuo" in row(data, r)["name"]]
    assert len(baznycios) == 3 and len(parts) == 2
    # The streets of the 2026-01-05 file: December "10;31".
    aguonu = street_rows(data, "Raseiniai", "household", "Aguonų g.")
    assert row(data, aguonu[0])["dates"][-2:] == ["2026-12-10", "2026-12-31"]
    # A street no route names is left to the app, never "no pickup".
    assert street_rows(data, "Raseiniai", "household", "Darbininkų g.") is None
    for waste, schedule in place(data, "Raseiniai", "m.")["schedule"].items():
        assert all(schedule.get("streets", {}).values()), waste
    # Viduklė, a small town: its route.
    assert place(data, "Viduklė")["schedule"]["household"]["area"]


def test_garden_communities_arent_read_as_the_sodu_street(built):
    _, data, warnings = built
    # "Bralinskių k., sodų bedrija "Rakava"": the whole village, not its Sodų g.
    assert "area" in place(data, "Bralinskiai")["schedule"]["household"]
    assert 'not a settlement or a street: household: Raseinių sen.: SB "Rakava"' in warnings


# --- next year -------------------------------------------------------------------


def test_next_years_file_of_an_eldership_continues_its_routes_on_its_own():
    def file(group, year, *names):
        areas = [
            Area("household", name, district="Raseinių r.", dates={date(year, 1, 14 + i)})
            for i, name in enumerate(names)
        ]
        return SourceFile("household", f"{UPLOADS}{group}{year}.pdf", "x.pdf", group=group), (
            ParseResult(areas)
        )

    betygala = file("Betygalos", 2026, "Betygalos sen.: Armonų k., Berteškių k.")
    reworded = file("Betygalos", 2027, "Betygalos sen.: Berteškių k., Armonų k.")
    girkalnis = file("Girkalnio", 2026, "Girkalnio sen.: Biliūnų k.")
    warnings = raseiniai.combine([betygala, reworded, girkalnis], registry(), date(2026, 12, 20))
    assert betygala[1].areas[0].dates == {date(2026, 1, 14), date(2027, 1, 14)}
    assert reworded[1].areas == []
    # Girkalnio sen.'s 2027 file isn't posted yet: no warning, and no minimum to fail.
    assert warnings == []


# --- a file that can't be read, and the folder -----------------------------------


def test_a_file_that_cant_be_read_keeps_yesterdays_rows(built, monkeypatch):
    files, data, _ = built
    published = merge_parts(
        [(raseiniai.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-20"})],
        raseiniai.PAGE_URL,
    )
    broken = next(f for f, _ in files if f.file_name.startswith("Betygalos sen. mi"))
    result = raseiniai.parse_or_keep(broken, b"%PDF-1.4 broken", lambda: published)
    assert len(result.areas) == 4 and {a.kind for a in result.areas} == {"household"}
    assert all(a.name.startswith("Betygalos sen.: ") for a in result.areas)
    before = {a["id"] for a in data["areas"] if a["name"].startswith("Betygalos sen.: ")}
    assert {a.id for a in result.areas} <= before
    assert "yesterday's 4 household rows of Betygalos sen. are kept" in result.warnings[0]
    # The live check (--strict) fails instead.
    with pytest.raises(PdfminerException):
        raseiniai.parse_or_keep(broken, b"%PDF-1.4 broken", None)
    # A file that couldn't be downloaded comes empty.
    with pytest.raises(ValueError, match="not downloaded"):
        raseiniai.parse_file(broken, b"")


def test_the_folder(built, tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(raseiniai.http, "get", serve)
    monkeypatch.setattr(raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "raseiniu-r"
    assert raseiniai.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["raseiniai"]
    assert (out / "addresses.json").exists()
    assert regions.region(tmp_path, out) == {
        "path": "raseiniu-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["raseiniai"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="raseiniai"} 554' in text
    assert 'siuksliaveze_data_areas{source="raseiniai",kind="green"}' in text


def test_a_file_of_no_year_has_its_workbooks():
    file = SourceFile(
        "household", f"{UPLOADS}x.pdf", "Raseinių m. MKA.pdf", group="Raseinių miesto"
    )
    areas = raseiniai.parse_file(file, fixture("raseiniai/raseiniu-m-mka.pdf")).areas
    assert len(areas) == 3 and {d.year for a in areas for d in a.dates} == {2026}

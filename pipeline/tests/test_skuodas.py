"""Skuodo r.: the municipality's page, its three spreadsheets (a legacy .xls of mixed waste, .xlsx
of packaging and of glass), their routes and places."""

import io
import json
from dataclasses import replace
from datetime import date

import openpyxl
import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, regions, skuodas, status
from schedule_pipeline.build import build_dataset
from schedule_pipeline.model import Area, ParseResult
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
UPLOADS = "https://skuodas.lt/wp-content/uploads/"
# The files the page links, by their names, and their copies in fixtures/skuodas.
COPIES = {
    "cia-1.xls": "misrios-2026.xls",
    "cia.xlsx": "pakuotes-2026.xlsx",
    "cia-2.xlsx": "stiklo-2026.xlsx",
}
KINDS = {"cia-1.xls": "household", "cia.xlsx": "packaging", "cia-2.xlsx": "glass"}
REGISTRY = "skuodas/registry-skuodo-r-2026-11-21.json"


def serve(url, timeout=0):
    """The saved page and files, as skuodas.http.get."""
    if url == skuodas.PAGE_URL:
        return fixture("skuodas/page.html")
    return fixture(f"skuodas/{COPIES[url.removeprefix(UPLOADS)]}")


def registry():
    return Registry.load(FIXTURES / REGISTRY)


def source(name, year=2026):
    return skuodas.ScheduleFile(KINDS[name], f"{UPLOADS}{name}", name, year=year)


def parsed(name, content=None, year=2026):
    content = content or fixture(f"skuodas/{COPIES[name]}")
    return skuodas.parse_file(source(name, year), content)


def area(areas, prefix):
    return next(a for a in areas if a.name.startswith(prefix))


def edited(copy, **cells):
    """A copy of an .xlsx fixture with some cells changed."""
    book = openpyxl.load_workbook(io.BytesIO(fixture(f"skuodas/{copy}")))
    for cell, value in cells.items():
        book.active[cell] = value
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(skuodas.http, "get", serve)
        files, warnings = skuodas.download(TODAY, 366)
        data, more = build_dataset(files, registry(), TODAY, 366, skuodas.SOURCE)
    return files, data, warnings + more


def place(data, name, kind=None):
    return next(
        loc for loc in data["locations"] if loc["name"] == name and kind in (None, loc["type"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


# --- the page ----------------------------------------------------------------


def test_finds_the_files_by_the_texts_of_their_paragraphs():
    files, warnings = skuodas.find_files(fixture("skuodas/page.html").decode("utf-8"))
    # Each is linked by "čia": the paragraph says what it is.
    assert [(f.file_name, f.kind, f.year) for f in files] == [
        ("cia-1.xls", "household", 2026),
        ("cia.xlsx", "packaging", 2026),
        ("cia-2.xlsx", "glass", 2026),
    ]
    assert all(f.url.startswith(UPLOADS) for f in files) and warnings == []


def test_packaging_but_glass_is_packaging():
    assert skuodas.file_kind("pakuočių (išskyrus stiklo) ir popieriaus atliekų") == "packaging"
    assert skuodas.file_kind("stiklo pakuočių atliekų surinkimo") == "glass"
    assert skuodas.file_kind("mišrių komunalinių atliekų surinkimo grafiką") == "household"
    assert skuodas.file_kind("Atliekų tvarkymo taisyklės") is None


def test_next_years_files_are_read_next_to_this_years():
    def file(kind, year, name="x.xlsx"):
        return skuodas.ScheduleFile(kind, f"{UPLOADS}{kind}{year}{name}", name, year=year)

    files = [file(k, 2026) for k in skuodas.KINDS] + [file("household", 2027), file("glass", 2025)]
    chosen, warnings = skuodas.select_files(files, TODAY)
    assert [(f.kind, f.year) for f in chosen] == [
        ("household", 2026),
        ("household", 2027),
        ("packaging", 2026),
        ("glass", 2026),
    ]
    assert warnings == []
    # Once 2026 is over, without newer files: the last ones, with a warning.
    chosen, warnings = skuodas.select_files(files[1:], date(2027, 1, 5))
    assert [(f.kind, f.year) for f in chosen] == [
        ("household", 2027),
        ("packaging", 2026),
        ("glass", 2026),
    ]
    assert warnings == [
        "no packaging schedule for 2027 on the page",
        "no glass schedule for 2027 on the page",
    ]
    # Two of one year: the one linked last.
    again = file("glass", 2026, "y.xlsx")
    chosen, warnings = skuodas.select_files([*files, again], TODAY)
    assert again in chosen and "x.xlsx: not read, y.xlsx is a newer glass schedule" in warnings[0]


def test_a_page_without_a_file_of_each_kind_fails():
    files, _ = skuodas.find_files(fixture("skuodas/page.html").decode("utf-8"))
    with pytest.raises(build.ValidationError, match="no glass schedule on the page"):
        skuodas.select_files([f for f in files if f.kind != "glass"], TODAY)


# --- the tables ------------------------------------------------------------------


def test_mixed_waste_every_two_weeks_from_the_legacy_workbook():
    areas = parsed("cia-1.xls").areas
    # 10 routes and Skuodas's old and new town; not the shared containers.
    assert len(areas) == 12 and {a.kind for a in areas} == {"household"}
    assert not any("bendrojo naudojimo" in a.name for a in areas)
    kernai = area(areas, "Skuodo sen.: Mažieji Rūšupiai; Puodkaliai; Kernai")
    # "Pirmadienis, kas 14 d.": "5, 19", "2, 16", "2, 16, 30", ...; not the hidden columns of
    # 2025 dates next to the table.
    assert sorted(kernai.dates)[:3] == [date(2026, 1, 5), date(2026, 1, 19), date(2026, 2, 2)]
    assert len(kernai.dates) == 26 and max(kernai.dates) == date(2026, 12, 21)
    assert {d.year for a in areas for d in a.dates} == {2026}
    assert kernai.weekday == "Pirmadienis"
    # "Kevirtadienis, kas 14 d.", a typo.
    assert area(areas, "Šačių sen., Barstyčių sen.").weekday == "Ketvirtadienis"
    assert {a.district for a in areas} == {"Skuodo r."}
    assert {a.provider for a in areas} == {"skuodas"}


def test_the_town_every_week():
    areas = parsed("cia-1.xls").areas
    # "kiekvieną pirmadienį", "kiekvieną penktadienį": every one of the year.
    old = area(areas, "Skuodo miesto senamiestis")
    new = area(areas, "Skuodo miesto naujamiestis")
    assert (len(old.dates), min(old.dates), old.weekday) == (52, date(2026, 1, 5), "Pirmadienis")
    assert (len(new.dates), max(new.dates), new.weekday) == (52, date(2026, 12, 25), "Penktadienis")


def test_packaging_on_the_day_of_its_roman_numeral():
    areas = parsed("cia.xlsx").areas
    assert len(areas) == 6 and {a.kind for a in areas} == {"packaging"}
    town = area(areas, "Skuodo miesto sen.: Skuodo m.")
    # "II": Tuesdays; "2, 30" in June.
    assert town.weekday == "Antradienis" and len(town.dates) == 13
    assert {date(2026, 6, 2), date(2026, 6, 30)} <= town.dates
    # "VII": the file's dates are Sundays.
    assert area(areas, "Aleksandrijos sen.:").weekday == "Sekmadienis"


def test_glass_five_times_a_year():
    areas = parsed("cia-2.xlsx").areas
    assert len(areas) == 7 and {a.kind for a in areas} == {"glass"}
    assert {len(a.dates) for a in areas} == {5}
    town = area(areas, "Skuodo miesto sen.: Skuodo m. - Apuolės g.")
    assert sorted(town.dates) == [
        date(2026, 1, 7),
        date(2026, 3, 23),
        date(2026, 6, 9),
        date(2026, 9, 1),
        date(2026, 11, 24),
    ]


def test_a_title_of_another_year_or_waste_type_fails():
    with pytest.raises(ValueError, match="isn't of 2027"):
        parsed("cia.xlsx", year=2027)
    glass = skuodas.ScheduleFile("packaging", f"{UPLOADS}cia-2.xlsx", "cia-2.xlsx", year=2026)
    with pytest.raises(ValueError, match="isn't of packaging"):
        skuodas.parse_file(glass, fixture("skuodas/stiklo-2026.xlsx"))


def test_strict_cells():
    with pytest.raises(ValueError, match="month 2 of 2026 has no day 30"):
        parsed("cia.xlsx", edited("pakuotes-2026.xlsx", D7="10, 30"))
    with pytest.raises(ValueError, match=r"unrecognised days '13 d\.'"):
        parsed("cia.xlsx", edited("pakuotes-2026.xlsx", C7="13 d."))
    with pytest.raises(ValueError, match="a cell outside the table: 'x'"):
        parsed("cia.xlsx", edited("pakuotes-2026.xlsx", O7="x"))
    with pytest.raises(ValueError, match="not a day of the week: 'IX'"):
        parsed("cia.xlsx", edited("pakuotes-2026.xlsx", A7="IX"))
    with pytest.raises(ValueError, match=r"months \[1, 2, 4"):
        parsed("cia.xlsx", edited("pakuotes-2026.xlsx", E6="Balandis"))


def test_dates_off_the_day_of_the_week_of_their_row():
    # "III" for a route on Tuesdays: the wrong year, or the wrong day.
    with pytest.raises(ValueError, match="the dates aren't on Trečiadienis"):
        parsed("cia.xlsx", edited("pakuotes-2026.xlsx", A7="III"))
    # One date moved: a warning.
    result = parsed("cia.xlsx", edited("pakuotes-2026.xlsx", C7=14))
    assert result.warnings == ["cia.xlsx row 7: 2026-01-14 is a Trečiadienis, not Antradienis"]


def test_hidden_columns_arent_read():
    book = openpyxl.load_workbook(io.BytesIO(fixture("skuodas/pakuotes-2026.xlsx")))
    book.active["P7"] = "2025-01-14"
    book.active.column_dimensions["P"].hidden = True
    out = io.BytesIO()
    book.save(out)
    assert len(parsed("cia.xlsx", out.getvalue()).areas) == 6


# --- the places ----------------------------------------------------------------


def test_counts(built):
    files, data, warnings = built
    assert len(files) == 3
    stats = data["matching"]
    assert stats["locations"] == 174
    # The town's two parts: the app asks which.
    assert (stats["household.single"], stats["household.ambiguous"]) == (149, 1)
    # Villages of Skuodo and Ylakių sen. the mixed waste file doesn't name.
    assert stats["household.none"] == 24
    assert (stats["packaging.single"], stats["packaging.none"]) == (167, 7)
    assert (stats["glass.single"], stats["glass.byStreet"], stats["glass.none"]) == (164, 1, 9)
    kinds = {}
    for a in data["areas"]:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    assert kinds == {"household": 12, "packaging": 6, "glass": 7}
    assert warnings == [
        "not a settlement or a street: packaging: Šačių sen.: (no places after it)",
        "not a settlement or a street: packaging: Šačių sen.: Giršinų k.",
    ]


def test_a_village(built):
    _, data, _ = built
    # Kernai, "Skuodo sen.: Mažieji Rūšupiai; Puodkaliai; Kernai; Šakaliai".
    dates = row(data, place(data, "Kernai")["schedule"]["household"]["area"])["dates"]
    assert (len(dates), dates[0], dates[-1]) == (26, "2026-01-05", "2026-12-21")
    # Typos and other endings: "Mildydžiai", "Viliotės Užpelkė", "Pakalniškės", "Ivoiškės k.".
    for name in ("Milvydžiai", "Viliotės Užpelkis", "Ivoniškė"):
        assert place(data, name)["schedule"]["packaging"]["area"], name
    assert "household" in place(data, "Viliotės Užpelkis")["schedule"]
    skuodo = [p for p in data["locations"] if p["name"] == "Pakalniškiai"]
    assert all("household" in p["schedule"] for p in skuodo)


def test_whole_elderships_and_the_villages_named_on_their_own(built):
    _, data, _ = built

    def mixed(name, kind=None):
        return row(data, place(data, name, kind)["schedule"]["household"]["area"])["name"]

    # "Lenkimų sen., Mosėdžio sen.: Plaušiniai; ...; Tauzai. Skuodo raj. sen.: Skuodo
    # priemiestis": all of Lenkimų sen., some villages of Mosėdžio sen. and Skuodo sen.
    route = "Lenkimų sen., Mosėdžio sen.: Plaušiniai"
    assert mixed("Lenkimai", "mstl.").startswith(route)
    assert mixed("Tauzai").startswith(route)
    assert mixed("Skuodo Priemiestis").startswith(route)
    # "Mosėdžio sen., Skuodo sen.: Būdvietė": the rest of Mosėdžio sen.
    assert mixed("Mosėdis").startswith("Mosėdžio sen., Skuodo sen.: Būdvietė")
    assert mixed("Būdvietė").startswith("Mosėdžio sen., Skuodo sen.: Būdvietė")
    assert mixed("Barstyčiai") == "Šačių sen., Barstyčių sen."
    # Villages no mixed waste route names have none: left to the app.
    assert "household" not in place(data, "Šekai").get("schedule", {})


def test_the_town(built):
    _, data, _ = built
    skuodas_ = place(data, "Skuodas", "m.")
    # Its old and new town, which the register doesn't have: the app asks.
    names = {row(data, r)["name"] for r in skuodas_["schedule"]["household"]["candidates"]}
    assert names == {"Skuodo miesto naujamiestis", "Skuodo miesto senamiestis"}
    assert "area" in skuodas_["schedule"]["packaging"]
    # Glass by street: 60 of its 85 streets, the others left to the app, never "no pickup".
    glass = skuodas_["schedule"]["glass"]["streets"]
    assert len(glass) == 60 and all(glass.values())
    labels = dict(skuodas_["streets"])
    by_label = {labels[key]: rows for key, rows in glass.items()}
    # "J. Sudimto g.", "D. Poškos g.": the register's Jono Sudimto g., Dionyzo Poškos g.
    assert "Jono Sudimto g." in by_label and "Dionyzo Poškos g." in by_label
    assert row(data, by_label["Vytauto g."][0])["dates"][0] == "2026-01-28"
    assert "Agrastų g." not in by_label


# --- next year -------------------------------------------------------------------


def test_next_years_file_continues_the_routes(monkeypatch):
    def result(year, *names):
        areas = [
            Area("glass", name, district="Skuodo r.", dates={date(year, 1, 7 + i)})
            for i, name in enumerate(names)
        ]
        return source("cia-2.xlsx", year), ParseResult(areas)

    this = result(2026, "Ylakių sen.: Augzelių k., Bučių k.", "Notėnų sen.: Baidotų k.")
    reworded = result(2027, "Ylakių sen.: Bučių k., Augzelių k.", "Notėnų sen.: Burvių k.")
    # Next year's file is checked when it's posted: two routes are too few.
    with pytest.raises(ValueError, match="only 2 glass routes in the 2027 file"):
        skuodas.combine([this, reworded], registry(), date(2026, 12, 20))
    monkeypatch.setattr(skuodas, "MUNICIPALITY", replace(skuodas.MUNICIPALITY, min_areas={}))
    warnings = skuodas.combine([this, reworded], registry(), date(2026, 12, 20))
    assert this[1].areas[0].dates == {date(2026, 1, 7), date(2027, 1, 7)}
    assert reworded[1].areas == []
    assert len(warnings) == 2 and "Notėnų sen.: Burvių k." in warnings[0]


# --- the folder ------------------------------------------------------------------


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(skuodas.http, "get", serve)
    monkeypatch.setattr(skuodas.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(skuodas.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "skuodo-r"
    assert skuodas.main(["--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["skuodas"]
    assert data["providers"][0]["name"] == "Skuodo rajono savivaldybė"
    assert (out / "addresses.json").exists()
    assert regions.region(tmp_path, out) == {
        "path": "skuodo-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["skuodas"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # Kaltys, Liaudiškiai, Remezai and Visgaudžiai (Ylakių sen.) are in none of the files.
    assert 'siuksliaveze_data_places{source="skuodas"} 170' in text
    assert 'siuksliaveze_data_areas{source="skuodas",kind="glass"} 7' in text

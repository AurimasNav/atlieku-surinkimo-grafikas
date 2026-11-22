"""Elektrėnų sav.: the pages of UAB „Elektrėnų komunalinis ūkis“ (eku.lt), found from its list of
the years' pages, their tables of three layouts, the village whose packaging is collected a day
earlier, the towns' individual houses, next year's pages, and the folder."""

import json
from datetime import date

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, elektrenai, regions, status
from schedule_pipeline.build import build_dataset
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 22)
REGISTRY = "elektrenai/registry-elektrenu-sav-2026-11-22.json"
# The pages, by the number their URLs end with, and their copies in fixtures/elektrenai.
COPIES = {
    "569": "grafikai.html",
    "651": "2025.html",
    "629": "2025-rusiuoju.html",
    "627": "2025-buitiniu.html",
    "628": "2025-antriniu.html",
    "652": "2026.html",
    "654": "2026-rusiuoju.html",
    "656": "2026-buitiniu.html",
    "653": "2026-antriniu.html",
}
HOUSEHOLD = "Buitinių atliekų išvežimo grafikas"
PACKAGING = "Antrinių (rūšiuojamų) atliekų išvežimo grafikas"


def serve(url, timeout=0):
    """The saved pages, as elektrenai.http.get."""
    return fixture(f"elektrenai/{COPIES[url.rsplit('/', 1)[-1]]}")


def page(kind, year=2026):
    title, copy = (HOUSEHOLD, "buitiniu") if kind == "household" else (PACKAGING, "antriniu")
    source = elektrenai.SchedulePage(
        kind, f"https://www.eku.lt/{copy}", copy, year=year, title=title
    )
    return source, fixture(f"elektrenai/{year}-{copy}.html")


def parsed(kind, year=2026):
    return elektrenai.parse_file(*page(kind, year))


def build_part(today=TODAY):
    files, warnings = elektrenai.download(today, 400, serve)
    registry = Registry.load(FIXTURES / REGISTRY)
    data, more = build_dataset(files, registry, today, 400, elektrenai.SOURCE)
    return files, data, warnings + more


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the pages, with every date of the year kept."""
    return build_part()


def place(data, name, kind=None, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and kind in (None, loc["type"])
        and district in (None, loc["district"])
    )


def rows(data, name, waste="household", kind=None, district=None, street=None):
    """A place's rows of a kind (of a street of it, or of its other streets)."""
    location = place(data, name, kind, district)
    schedule = location["schedule"][waste]
    if street:
        key = next(k for k, label in location["streets"] if label == street)
        ids = schedule["streets"][key]
    else:
        ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    by_id = {a["id"]: a for a in data["areas"]}
    return [by_id[i] for i in ids]


# --- the pages ---------------------------------------------------------------


def test_finds_the_years_pages_and_their_schedules():
    files, warnings = elektrenai.download(TODAY, 31, serve)
    assert [(f.kind, f.year, f.file_name) for f, _ in files] == [
        ("household", 2026, f"2026 m. {HOUSEHOLD}"),
        ("packaging", 2026, f"2026 m. {PACKAGING}"),
    ]
    assert [f.url for f, _ in files] == [
        "https://www.eku.lt/2026-m./rusiuoju-buitines-atliekas/buitiniu-atlieku-isvezimo-grafikas/656",
        "https://www.eku.lt/2026-m./rusiuoju-buitines-atliekas/antriniu-rusiuojamu-atlieku-isvezimo-grafikas/653",
    ]
    # The households that don't sort and bulky waste aren't read, without a warning.
    assert warnings == []


def test_this_years_page_and_later_ones_else_the_newest():
    years = [(2025, "a"), (2026, "b")]
    assert elektrenai.select_years(years, TODAY) == ([(2026, "b")], [])
    assert elektrenai.select_years(years, date(2025, 12, 1)) == ([(2025, "a"), (2026, "b")], [])
    # In January, before next year's page: this year's, whose routes keep their last dates.
    assert elektrenai.select_years(years, date(2027, 1, 5)) == ([(2026, "b")], ["no page of 2027"])
    with pytest.raises(build.ValidationError, match="two pages of one year"):
        elektrenai.select_years([*years, (2026, "c")], TODAY)


def test_a_later_years_page_without_its_schedules_yet_is_left_out():
    def get(url):
        if url.endswith("/569"):
            # The list of years with a page of 2027.
            html = fixture("elektrenai/grafikai.html")
            start = html.index(b'<ul class="menu-list">', html.index(b'"childlist_cont"'))
            link = b'<li><a href="/x/2027-m./700"><span class="text">2027 m.</span></a></li>'
            return html[: start + 22] + link + html[start + 22 :]
        if url.endswith("/700"):
            # The 2026 page, without its pages yet.
            html = fixture("elektrenai/2026.html").replace(b"2026 m.", b"2027 m.")
            start = html.index(b'<ul class="menu-list">', html.index(b'"childlist_cont"'))
            end = html.index(b"</ul>", start)
            return html[: start + 22] + html[end:]
        return serve(url)

    files, warnings = elektrenai.download(TODAY, 31, get)
    assert [f.year for f, _ in files] == [2026, 2026]
    assert warnings == [
        "2027 m.: 0 pages of the households that sort their waste; the page of 2027 isn't read yet"
    ]
    # This year's page without them fails.
    with pytest.raises(elektrenai.NotListed):
        elektrenai.download(date(2027, 1, 5), 31, get)


def test_a_page_titled_otherwise_or_of_another_year_fails():
    source, content = page("household")
    with pytest.raises(ValueError, match="is titled 'Buitinių atliekų išvežimo grafikas'"):
        elektrenai.parse_file(
            elektrenai.SchedulePage("household", "u", "x", year=2026, title=PACKAGING), content
        )
    with pytest.raises(ValueError, match="isn't under the page of 2027"):
        elektrenai.parse_file(
            elektrenai.SchedulePage("household", "u", "x", year=2027, title=HOUSEHOLD), content
        )


# --- the tables ------------------------------------------------------------------


def test_the_mixed_waste_tables():
    areas = {a.name: a for a in parsed("household").areas}
    assert len(areas) == 13 and {a.kind for a in areas.values()} == {"household"}
    # "2026 m. | Dienos (over two columns)": twice a month.
    town = areas[
        "Elektrėnų individualių namų kvartalo, Abromiškių k. – Orio g., Perkūnkiemio g. "
        "Alinkos k., Sabališkių k., Šarkinės k."
    ]
    assert len(town.dates) == 24 and town.weekday == "Ketvirtadienis"
    assert sorted(town.dates)[:3] == [date(2026, 1, 8), date(2026, 1, 22), date(2026, 2, 5)]
    assert max(town.dates) == date(2026, 12, 17)
    # Once a month, on Tuesdays and Thursdays: no weekday.
    vievis = areas["Vievio miesto individualūs namai"]
    assert len(vievis.dates) == 12 and vievis.weekday is None
    assert {a.district for a in areas.values()} == {"Elektrėnų sav."}


def test_the_packaging_tables_of_months_and_of_dates():
    areas = {(a.kind, a.name): a for a in parsed("packaging").areas}
    # Nine routes of packaging and glass, and Dumblikas' packaging.
    kinds = sorted(kind for kind, _ in areas)
    assert kinds == ["glass"] * 9 + ["packaging"] * 10
    # "Mėnuo | Popierius-Plastikas | Stiklas" with "22 d." and "-".
    town = next(a for (k, n), a in areas.items() if k == "glass" and n.startswith("Elektrėnų"))
    assert sorted(town.dates) == [
        date(2026, 3, 17),
        date(2026, 6, 30),
        date(2026, 9, 24),
        date(2026, 12, 22),
    ]
    # "STIKLAS | PLASTIKAS IR POPIERIUS" with "2026-01-27".
    glass = areas[("glass", "Vievio miesto individualūs namai")]
    assert sorted(glass.dates) == [
        date(2026, 2, 4),
        date(2026, 5, 6),
        date(2026, 8, 5),
        date(2026, 11, 3),
    ]
    packaging = areas[("packaging", "Vievio miesto individualūs namai")]
    assert len(packaging.dates) == 12 and packaging.weekday == "Antradienis"


def test_the_village_whose_packaging_is_collected_a_day_earlier():
    areas = parsed("packaging").areas
    route = "Vievio seniūnijos Balceriškių, Baltamiškio, Burbiškių, {}Joteliūnų, Kazimieriškių"
    glass = next(a for a in areas if a.kind == "glass" and a.name.startswith(route.format("")[:40]))
    assert glass.name.startswith(route.format("Dumbliko, "))
    packaging = next(a for a in areas if a.name.startswith(route.format("")))
    dumblikas = next(a for a in areas if a.name == "Vievio seniūnijos Dumbliko kaimas")
    assert (dumblikas.kind, packaging.kind) == ("packaging", "packaging")
    assert min(packaging.dates) == date(2026, 1, 22) and min(dumblikas.dates) == date(2026, 1, 21)
    assert {d.toordinal() + 1 for d in dumblikas.dates} == {d.toordinal() for d in packaging.dates}
    assert dumblikas.weekday == "Trečiadienis"


def test_last_years_pages_read_too():
    # Other spellings and cells ("2 d."), the same layouts.
    assert len(parsed("household", 2025).areas) == 13
    assert len(parsed("packaging", 2025).areas) == 18


MONTHS = "Sausis Vasaris Kovas Balandis Gegužė Birželis Liepa Rugpjūtis Rugsėjis Spalis Lapkritis"


def test_strict_tables():
    def dates(*rows, kinds=("household",), year=2026):
        cells = [[elektrenai._Cell([text]) for text in row] for row in rows]
        return elektrenai._table(cells, year, kinds, "x")

    # The first Tuesday of each month of 2026.
    tuesdays = ["06", "03", "03", "07", "05", "02", "07", "04", "01", "06", "03", "01"]
    months = [*MONTHS.split(), "Gruodis"]
    good = [("2026 m.", "Dienos"), *zip(months, tuesdays, strict=True)]
    # "Dienos" over two columns: twice a month, two weeks apart.
    double = [[elektrenai._Cell(["2026 m."]), elektrenai._Cell(["Dienos"], colspan=2)]]
    double += [
        [elektrenai._Cell([m]), elektrenai._Cell([d]), elektrenai._Cell([str(int(d) + 14)])]
        for m, d in good[1:]
    ]
    assert len(elektrenai._table(double, 2026, ("household",), "x")["household"]) == 24
    assert len(dates(*good)["household"]) == 12
    # "2026" without "m." (the page of households that don't sort has it).
    assert len(dates(("2026", "Dienos"), *good[1:])["household"]) == 12
    with pytest.raises(ValueError, match="a table of 2025 on the page of 2026"):
        dates(("2025 m.", "Dienos"), *good[1:])
    with pytest.raises(ValueError, match=r"months \[2, 1"):
        dates(good[0], good[2], good[1], *good[3:])
    with pytest.raises(ValueError, match="not days: '5 ir 19'"):
        dates(*good[:5], ("Gegužė", "5 ir 19"), *good[6:])
    with pytest.raises(ValueError, match="day 30 of 2026-02"):
        dates(good[0], good[1], ("Vasaris", "30"), *good[3:])
    with pytest.raises(ValueError, match="a column of 'Maistas'"):
        dates(("Mėnuo", "Popierius", "Maistas"), ("Sausis", "6", "8"), kinds=("packaging", "glass"))
    with pytest.raises(ValueError, match="expected"):
        dates(("Mėnuo", "Popierius"), *good[1:], kinds=("packaging", "glass"))
    with pytest.raises(ValueError, match="2025-02-04 on the page of 2026"):
        dates(("STIKLAS", "PLASTIKAS"), ("2025-02-04", ""), kinds=("glass", "packaging"))
    with pytest.raises(ValueError, match="not a date: '4 vasario'"):
        dates(("STIKLAS", "PLASTIKAS"), ("4 vasario", ""), kinds=("glass", "packaging"))
    with pytest.raises(ValueError, match="no glass dates"):
        dates(("STIKLAS", "PLASTIKAS"), ("", "2026-02-04"), kinds=("glass", "packaging"))
    # 2026's Tuesdays are Saturdays and Sundays in 2024.
    with pytest.raises(ValueError, match="weekends"):
        dates(("Mėnuo", "Dienos"), *good[1:], year=2024)


def test_notes_and_text_outside_the_tables():
    source, content = page("packaging")
    html = content.decode("utf-8")
    note = "<p>Rūšiuojamų atliekų išvežimas nemokamas.</p>"
    assert note in html
    moved = html.replace(note, "<p>Gruodžio 22 d. išvežimas perkeliamas.</p>", 1)
    with pytest.raises(ValueError, match="a note next to the table: 'Gruodžio 22 d."):
        elektrenai.parse_file(source, moved.encode())
    source, content = page("household")
    html = content.decode("utf-8")
    loose = html.replace('<div class="topicslist">', "<p>Grafikas gali keistis.</p><div>", 1)
    with pytest.raises(ValueError, match="text outside the schedules: 'Grafikas gali keistis.'"):
        elektrenai.parse_file(source, loose.encode())


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 246
    assert (stats["household.single"], stats["household.byStreet"]) == (164, 2)
    assert (stats["household.ambiguous"], stats["household.none"]) == (2, 78)
    assert (stats["packaging.single"], stats["packaging.byStreet"]) == (163, 1)
    assert (stats["glass.single"], stats["glass.byStreet"]) == (163, 1)
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 13, "packaging": 10, "glass": 9}
    assert sorted(warnings) == sorted(
        ['not linked to any settlement: household: Sodų "Klevas"']
        + [
            f"not a settlement or a street: {kind}: Elektrėnų sav.: {name}"
            for kind in ("household", "packaging", "glass")
            for name in (
                "Paalkių k.",
                "Senųjų Abromiškių k.",
                "Senųjų Sabališkių k.",
                'SB "Klevas"',
            )
        ]
    )


def test_a_village_and_its_dates(built):
    _, data, _ = built
    # Gilučiai, "Diekcioriškių k., Gabriliavos k., Gilučių k., ...": the first Tuesday of each
    # month.
    (row,) = rows(data, "Gilučiai")
    assert row["name"].startswith("Diekcioriškių k., Gabriliavos k., Gilučių k.,")
    assert (len(row["dates"]), row["dates"][0], row["dates"][-1]) == (
        12,
        "2026-01-06",
        "2026-12-01",
    )
    assert row["weekday"] == "Antradienis"
    (row,) = rows(data, "Gilučiai", "packaging")
    assert row["name"].startswith("Diekcioriškių k. Gabriliavos k. Gilučių k.")


def test_the_towns(built):
    _, data, _ = built
    # Elektrėnai: its individual houses' route, but Marių g., in the route of Belezai and others.
    (row,) = rows(data, "Elektrėnai")
    assert row["name"].startswith("Elektrėnų individualių namų kvartalo,")
    assert (len(row["dates"]), row["dates"][0], row["dates"][-1]) == (
        24,
        "2026-01-08",
        "2026-12-17",
    )
    (row,) = rows(data, "Elektrėnai", street="Marių g.")
    assert row["name"].startswith("Baubonių k., Belezų k.,")
    (row,) = rows(data, "Elektrėnai", "packaging", street="Marių g.")
    assert row["name"].startswith("Baubonių k. Belezų k.")
    (row,) = rows(data, "Elektrėnai", "glass")
    assert row["name"].startswith("Elektrėnų individualių namų kvartalo,")
    # No street gets "no pickup".
    streets = place(data, "Elektrėnai")["schedule"]["household"]["streets"]
    assert all(streets.values())
    # Vievis: its individual houses' routes, the whole town.
    for waste in ("household", "packaging", "glass"):
        (row,) = rows(data, "Vievis", waste)
        assert row["name"] == "Vievio miesto individualūs namai"
    # Semeliškės, the small town, and the village of its name.
    (town,) = rows(data, "Semeliškės", kind="mstl.")
    (village,) = rows(data, "Semeliškės", kind="k.")
    assert town is village and town["name"].startswith("Aleksandravos k., Budilių k.,")


def test_streets_of_a_village_and_villages_of_two_elderships(built):
    _, data, _ = built
    # Abromiškės: Orio g. and Perkūnkiemio g. in Elektrėnai's route, the rest in its own.
    (row,) = rows(data, "Abromiškės", street="Orio g.")
    assert row["name"].startswith("Elektrėnų individualių namų kvartalo,")
    (row,) = rows(data, "Abromiškės", street="Perkūnkiemio g.")
    assert row["name"].startswith("Elektrėnų individualių namų kvartalo,")
    (row,) = rows(data, "Abromiškės")
    assert row["name"].startswith("Abromiškių k., Geibonių k.,")
    # Packaging names all of Abromiškės in Elektrėnai's route.
    (row,) = rows(data, "Abromiškės", "packaging")
    assert row["name"].startswith("Elektrėnų individualių namų kvartalo,")
    # Navasiolkai of Semeliškių sen. and of Beižionių sen., each in its own ("(Semeliškių
    # sen.)", "(Beižonių sen.)", "(Smeliškių sen.)").
    (row,) = rows(data, "Navasiolkai", district="Semeliškių")
    assert row["name"].startswith("Aleksandravos k.,")
    (row,) = rows(data, "Navasiolkai", district="Beižionių")
    assert row["name"].startswith("Antakalnio VS.,")
    (row,) = rows(data, "Navasiolkai", "packaging", district="Beižionių")
    assert row["name"].startswith("Antakalnio VS.")
    # "Laičių k.": Laičiai of Semeliškių sen. and of Beižionių sen. (no addresses) both.
    for district in ("Semeliškių", "Beižionių"):
        (row,) = rows(data, "Laičiai", district=district)
        assert row["name"].startswith("Baubonių k.,")


def test_the_spellings(built):
    _, data, _ = built
    # "Pastrėvio Peliūnų k.": two villages.
    for name in ("Pastrėvys", "Peliūnai"):
        (row,) = rows(data, name, "packaging")
        assert row["name"].startswith("Baubonių k. Belezų k.")
    # "Srošiūnų k." (Strošiūnai), "Tvertinės k." (Tvertiniai), "Pievaičių VS.", "Sen.
    # Kietaviškių k.", "Klon. Mijaugonių k.".
    assert rows(data, "Strošiūnai")[0]["name"].startswith("Diekcioriškių k.")
    assert rows(data, "Tvertinės")[0]["name"].startswith("Aleksandravos k.")
    assert rows(data, "Pievaičiai")[0]["name"].startswith("Abromiškių k.")
    assert rows(data, "Senosios Kietaviškės")[0]["name"].startswith("Ašakienių k.")
    (row,) = rows(data, "Kloniniai Mijaugonys", "packaging")
    assert row["name"].startswith("Ašakienių k. Gilūšio k.")
    # Two lists of Vievio sen. name Skynimai and Streipūnai: the app asks.
    names = sorted(r["name"][:30] for r in rows(data, "Skynimai"))
    assert names == ["Vievio seniūnijos Baltamiškio,", "Vievio seniūnijos Ąžuolinės, A"]
    # Dumblikas: no mixed waste route names it; its packaging is a day earlier.
    assert "household" not in place(data, "Dumblikas")["schedule"]
    (row,) = rows(data, "Dumblikas", "packaging")
    assert row["name"] == "Vievio seniūnijos Dumbliko kaimas"
    (row,) = rows(data, "Dumblikas", "glass")
    assert "Dumbliko," in row["name"]


def test_next_years_pages_continue_this_years_routes():
    # As if it were November 2025, with the 2026 pages listed: the routes that cover the same
    # places continue.
    files, data, warnings = build_part(date(2025, 11, 22))
    assert [f.year for f, _ in files] == [2025, 2025, 2026, 2026]
    (row,) = rows(data, "Gilučiai")
    assert (row["dates"][0], row["dates"][-1], len(row["dates"])) == (
        "2025-01-07",
        "2026-12-01",
        24,
    )
    # Elektrėnai's route gained Orio g. and Perkūnkiemio g. of Abromiškės in 2026: it waits.
    (row,) = rows(data, "Elektrėnai")
    assert row["dates"][-1] == "2025-12-18"
    assert any("the 2026 route 'Elektrėnų individualių namų kvartalo" in w for w in warnings)


# --- the folder ----------------------------------------------------------------


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(elektrenai.http, "get", serve)
    monkeypatch.setattr(elektrenai.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(elektrenai.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "elektrenu-sav"
    assert elektrenai.main(["--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["elektrenai"]
    assert data["providers"][0]["url"] == elektrenai.START_URL
    assert regions.region(tmp_path, out) == {
        "path": "elektrenu-sav/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["elektrenai"],
    }
    addresses = json.loads((out / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > elektrenai.MUNICIPALITY.min_address_points
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="elektrenai"} 169' in text

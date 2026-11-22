"""Širvintų r.: the municipality's two pages, its mixed waste PDFs (two layouts, periods of their
own) and its packaging PDF, the places of their routes, the periods and the published folder."""

import json
from collections import Counter
from dataclasses import replace
from datetime import date

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, regions, sirvintos, snapshot, status
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "sirvintos" / "registry-sirvintu-r-2026-11-22.json")
TODAY = date(2026, 11, 22)
UPLOADS = "https://www.sirvintos.lt/data/public/uploads/"
# The files the pages link, and their copies in fixtures/sirvintos/.
COPIES = {
    "misrios-grafikas-2026-m_06-16.pdf": "misrios-2026-06-12.pdf",
    "grafikas-mk-2026-m..pdf": "misrios-2026-04-06.pdf",
    "sirvintos-2026-m.-grafikas.pdf": "antrines-2026.pdf",
    "grafikas-sirvintos-mka-2025-2026.pdf": "misrios-2025-05-2026-04.pdf",
}
PAGES = {
    sirvintos.MIXED_PAGE: "misrios-page.html",
    sirvintos.RECYCLABLES_PAGE: "antrines-page.html",
}


def page_files(page=sirvintos.MIXED_PAGE):
    return sirvintos.find_files(fixture(f"sirvintos/{PAGES[page]}").decode("utf-8"), page)


def content(file):
    return fixture(f"sirvintos/{COPIES[file.file_name]}")


def dated(file):
    """The file with the months of its table."""
    file = replace(file)
    file.start, file.end = sirvintos.read_period(file, content(file))
    return file


JUNE, APRIL, PACKAGING = (dated(f) for f in page_files()[0])
# May 2025 - April 2026, as the page linked it in 2025.
YEAR = dated(
    sirvintos.ScheduleFile(
        "household",
        f"{UPLOADS}2025/04/grafikas-sirvintos-mka-2025-2026.pdf",
        "grafikas-sirvintos-mka-2025-2026.pdf",
        text="ŠIRVINTŲ RAJONO GYVENTOJŲ MIŠRIŲ KOMUNALINIŲ ATLIEKŲ IŠVEŽIMO 2025 M. 05 MĖN.–2026 "
        "M. 04 MĖN. GRAFIKAS",
    )
)


def parsed(file):
    return sirvintos.parse_file(file, content(file))


@pytest.fixture(scope="module")
def part():
    files = [(f, content(f)) for f in (JUNE, PACKAGING)]
    return build_dataset(files, REGISTRY, TODAY, 31, sirvintos.SOURCE)


def place(data, name, district=None, kind_of_place=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and district in (None, loc["district"])
        and kind_of_place in (None, loc["type"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def rows_of(data, name, kind, street=None, district=None, kind_of_place=None):
    """The names of a place's rows (or of one of its streets'), their first 40 letters."""
    location = place(data, name, district, kind_of_place)
    schedule = location["schedule"][kind]
    if street is None:
        ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    else:
        key = next(k for k, label in location["streets"] if label == street)
        ids = schedule["streets"][key]
    return sorted(row(data, i)["name"][:40].rstrip() for i in ids)


def by_start(result, start, kind="household"):
    return next(a for a in result.areas if a.kind == kind and a.name.startswith(start))


# The beginnings of the June-December routes' names, as rows_of gives them.
ZIBALAI = "ZIBALŲ SEN. Anciūnų k., Antininavos k.,"
TOWN_1 = "ŠIRVINTŲ MIESTAS Individualios valdos: Z"
TOWN_2 = "ŠIRVINTŲ MIESTAS Individualios valdos: S"
VIESOS = "ŠIRVINTŲ SEN. Akmenių k., Augūnijos k.,"
ALIONYS = "ALIONIŲ SEN. Adolinos k., Alionių I k.,"


# --- the pages ---------------------------------------------------------------


def test_finds_the_files_by_their_links():
    files, warnings = page_files()
    assert [(f.kind, COPIES[f.file_name]) for f in files] == [
        ("household", "misrios-2026-06-12.pdf"),
        ("household", "misrios-2026-04-06.pdf"),
        ("packaging", "antrines-2026.pdf"),
    ]
    assert warnings == []
    assert JUNE.url == f"{UPLOADS}2026/06/misrios-grafikas-2026-m_06-16.pdf"
    # The packaging page links the same file.
    files, _ = page_files(sirvintos.RECYCLABLES_PAGE)
    assert [f.url for f in files] == [PACKAGING.url]


def test_the_periods_are_the_months_of_the_tables():
    assert (JUNE.start, JUNE.end) == (date(2026, 6, 1), date(2026, 12, 31))
    assert (APRIL.start, APRIL.end) == (date(2026, 4, 1), date(2026, 6, 30))
    assert (PACKAGING.start, PACKAGING.end) == (date(2026, 1, 1), date(2026, 12, 31))
    assert (YEAR.start, YEAR.end) == (date(2025, 5, 1), date(2026, 4, 30))


def test_the_months_a_link_names():
    assert sirvintos.link_period(APRIL.text) == (date(2026, 4, 1), date(2026, 6, 30))
    assert sirvintos.link_period(YEAR.text) == (date(2025, 5, 1), date(2026, 4, 30))
    assert sirvintos.link_period(JUNE.text) is None
    assert sirvintos.link_period(PACKAGING.text) is None


def test_a_link_for_other_months_fails():
    other = replace(APRIL, text=APRIL.text.replace("04 - 06", "07 - 09"))
    with pytest.raises(ValueError, match="its link says"):
        sirvintos.read_period(other, content(APRIL))
    other = replace(JUNE, text=JUNE.text.replace("2026", "2027"))
    with pytest.raises(ValueError, match="its link says"):
        sirvintos.read_period(other, content(JUNE))


def periods(files):
    return [(f.kind, f.start.isoformat(), f.end.isoformat()) for f in files]


def test_reads_the_files_with_dates_still_to_publish():
    selected, warnings = sirvintos.select_files([JUNE, APRIL, PACKAGING], TODAY)
    assert periods(selected) == [
        ("household", "2026-06-01", "2026-12-31"),
        ("packaging", "2026-01-01", "2026-12-31"),
    ]
    assert warnings == []
    # On 20 June April-June's last dates are still published: both are read.
    selected, _ = sirvintos.select_files([JUNE, APRIL, PACKAGING], date(2026, 6, 20))
    assert periods(selected)[:2] == [
        ("household", "2026-04-01", "2026-06-30"),
        ("household", "2026-06-01", "2026-12-31"),
    ]


def test_a_late_period_keeps_the_last_one():
    selected, _ = sirvintos.select_files([JUNE, APRIL, PACKAGING], date(2027, 2, 15))
    assert periods(selected) == [
        ("household", "2026-06-01", "2026-12-31"),
        ("packaging", "2026-01-01", "2026-12-31"),
    ]


def test_of_two_files_for_one_period_the_one_uploaded_last_is_read():
    newer = replace(JUNE, url=f"{UPLOADS}2026/07/patikslintas.pdf", file_name="patikslintas.pdf")
    selected, warnings = sirvintos.select_files([JUNE, newer, PACKAGING], TODAY)
    assert [f.file_name for f in selected][0] == "patikslintas.pdf"
    assert warnings == [
        f"{JUNE.file_name}: not read, patikslintas.pdf is a newer mixed waste schedule for "
        "2026-06-01 - 2026-12-31"
    ]


def test_pages_without_packaging_fail():
    with pytest.raises(ValidationError, match="no packaging schedule"):
        sirvintos.select_files([JUNE, APRIL], TODAY)


def test_links_of_other_schedules_are_reported():
    html = (
        '<a href="/a.pdf">Didelių gabaritų atliekų surinkimo grafikas</a>'
        '<a href="/b.pdf">Pusiau požeminių konteinerių plovimo grafikas</a>'
        '<a href="/c.pdf">Vietinės rinkliavos dydžiai</a>'
    )
    files, warnings = sirvintos.find_files(html, sirvintos.MIXED_PAGE)
    assert files == []
    assert warnings == [
        "a.pdf ('Didelių gabaritų atliekų surinkimo grafikas'): a schedule of no kind we read",
        "b.pdf ('Pusiau požeminių konteinerių plovimo grafikas'): a schedule of no kind we read",
    ]


def serve(url, timeout=0):
    """The pages and their files, from the fixtures."""
    if url in PAGES:
        return fixture(f"sirvintos/{PAGES[url]}")
    for name, copy in COPIES.items():
        if url.endswith(f"/{name}"):
            return fixture(f"sirvintos/{copy}")
    raise OSError(f"HTTP Error 404: {url}")


def test_downloads_the_files_with_dates_still_to_publish(monkeypatch):
    asked: list[str] = []

    def get(url, timeout=0):
        asked.append(url)
        return serve(url)

    monkeypatch.setattr(sirvintos.http, "get", get)
    files, warnings = sirvintos.download(TODAY, 31)
    assert [(f.file_name, f.start, f.end) for f, _ in files] == [
        (JUNE.file_name, date(2026, 6, 1), date(2026, 12, 31)),
        (PACKAGING.file_name, date(2026, 1, 1), date(2026, 12, 31)),
    ]
    assert files[0][1] == content(JUNE)
    assert warnings == []
    # Each page once and each linked file once (April-June to read its months).
    assert sorted(asked) == sorted([*PAGES, JUNE.url, APRIL.url, PACKAGING.url])


def test_old_files_are_not_downloaded(monkeypatch):
    old = (
        f'<a href="{UPLOADS}2023/04/grafikas-2023-2024-m..pdf">ŠIRVINTŲ RAJONO GYVENTOJŲ MIŠRIŲ '
        "KOMUNALINIŲ ATLIEKŲ IŠVEŽIMO 2023 M. 05 MĖN.–2024 M. 04 MĖN. GRAFIKAS</a>"
    ).encode()

    def get(url, timeout=0):
        if url == sirvintos.MIXED_PAGE:
            return serve(url) + old
        if "2023" in url:
            raise AssertionError(url)
        return serve(url)

    monkeypatch.setattr(sirvintos.http, "get", get)
    files, _ = sirvintos.download(TODAY, 31)
    assert [f.file_name for f, _ in files] == [JUNE.file_name, PACKAGING.file_name]


# --- the tables ------------------------------------------------------------------


def names(result, kind="household"):
    return [a.name for a in result.areas if a.kind == kind]


def test_mixed_waste_june_to_december():
    result = parsed(JUNE)
    assert len(names(result)) == 20
    assert {(a.kind, a.district, a.provider) for a in result.areas} == {
        ("household", "Širvintų r.", "sirvintos")
    }
    # A table per route: its places, then a day each month (the town's twice from June to
    # September).
    first = by_start(result, "ZIBALŲ SEN. Aukštadvario k.")
    assert sorted(first.dates) == [
        date(2026, 6, 1),
        date(2026, 7, 6),
        date(2026, 8, 3),
        date(2026, 9, 7),
        date(2026, 10, 5),
        date(2026, 11, 2),
        date(2026, 12, 7),
    ]
    assert first.weekday == "Pirmadienis"
    town = by_start(result, TOWN_1)
    assert len(town.dates) == 11 and town.weekday == "Antradienis"
    assert town.name.endswith("Plento g. nuo Nr. 58 iki 90.")
    assert result.warnings == []


def test_mixed_waste_april_to_june():
    # The other layout: the route's name, then its places. Lines of spaces 3 points above some
    # days: "25", not "2 5".
    result = parsed(APRIL)
    assert len(names(result)) == 20
    route = by_start(result, "ALIONIŲ SEN. Arliškių k.")
    assert sorted(route.dates) == [date(2026, 4, 27), date(2026, 5, 25), date(2026, 6, 22)]
    # The first route's 11 April is a Saturday (after Easter Monday).
    assert result.warnings == [
        "grafikas-mk-2026-m..pdf: household of 'ZIBALŲ SEN. Aukštadvario k., Degsnių k., "
        "Juozapavos k., Jusi' on 2026-04-11, not on its weekday (Pirmadienis)"
    ]


def test_mixed_waste_may_to_april():
    # A table across the new year: May 2025 to April 2026; "-" for no pickup in a month.
    result = parsed(YEAR)
    assert len(names(result)) == 20
    route = by_start(result, "GELVONŲ SEN. Cegelnės k.")
    december = sorted(d for d in route.dates if d.month in (12, 1))
    assert december == [date(2025, 12, 4), date(2025, 12, 31)]
    assert max(route.dates) == date(2026, 4, 2)


def test_packaging_and_glass():
    result = parsed(PACKAGING)
    assert len(names(result, "packaging")) == 20
    assert len(names(result, "glass")) == 20
    alionys = by_start(result, "ALIONIŲ SENIŪNIJA: Visa seniūnija", "packaging")
    assert alionys.name == "ALIONIŲ SENIŪNIJA: Visa seniūnija, išskyrus Kvakšių k"
    assert len(alionys.dates) == 13 and alionys.weekday == "Pirmadienis"
    glass = by_start(result, "ALIONIŲ SENIŪNIJA: Visa seniūnija", "glass")
    assert sorted(glass.dates) == [
        date(2026, 2, 10),
        date(2026, 5, 5),
        date(2026, 7, 28),
        date(2026, 10, 20),
    ]
    # The last place of Širvintų sen. doesn't fit its cell: read from the words' positions.
    last = by_start(result, "ŠIRVINTŲ SENIŪNIJA: Širvintų k. (išskyrus", "packaging")
    assert last.name.endswith("Girelės vs., Šeipūnų k., Meižių k.,")
    assert "Aukštųjų Viesų k." in last.name
    assert min(last.dates) == date(2026, 1, 19) and max(last.dates) == date(2026, 12, 21)


def test_a_title_of_another_kind_fails(monkeypatch):
    monkeypatch.setitem(sirvintos.TITLES, "household", "antrin")
    with pytest.raises(ValueError, match="isn't of household"):
        parsed(JUNE)


def test_too_few_routes_fail(monkeypatch):
    monkeypatch.setitem(sirvintos.MIN_ROUTES, "household", 21)
    with pytest.raises(ValueError, match="only 20 routes"):
        parsed(JUNE)


def test_dates_off_their_weekday_fail(monkeypatch):
    # Days a month off (the wrong months): the routes' dates scatter over the week.
    table = sirvintos.read(JUNE, content(JUNE))
    for route in table.routes:
        route.dates = {k: {d.replace(month=d.month - 1) for d in v} for k, v in route.dates.items()}
    monkeypatch.setattr(sirvintos, "read", lambda source, data: table)
    with pytest.raises(ValueError, match="aren't on one working day"):
        parsed(JUNE)


def test_rows_of_other_waste_types_fail(monkeypatch):
    monkeypatch.delitem(sirvintos.ROW_KINDS, "stiklas")
    with pytest.raises(ValueError, match="a row of 'STIKLAS'"):
        parsed(PACKAGING)


# --- the places ------------------------------------------------------------------


def test_counts(part):
    data, warnings = part
    assert len(data["areas"]) == 60
    stats = data["matching"]

    def counts(kind):
        return [stats[f"{kind}.{s}"] for s in ("single", "byStreet", "ambiguous", "none")]

    assert counts("household") == [402, 3, 8, 57]
    assert counts("packaging") == counts("glass") == [282, 2, 1, 185]
    assert len(data["locations"]) == 470


def test_settlements_without_a_schedule(part):
    data, _ = part
    points, _ = snapshot.load_points(snapshot.SIRVINTOS_ADDRESSES_FILE)
    addresses = Counter(f"g{p.settlement}" for p in points)

    def without(kind):
        return Counter(
            {
                (loc["name"], loc["district"], loc["type"]): addresses[loc["id"]]
                for loc in data["locations"]
                if kind not in loc.get("schedule", {})
            }
        )

    # Mixed waste: places no file names, most without addresses: 142 of 11,992 addresses in
    # November 2026. The file names the other type of a name ("Daubariškio vs.").
    household = without("household")
    assert len(household) == 57 and sum(household.values()) == 142
    assert household.most_common(2) == [
        (("Daubariškis", "Musninkų", "k."), 17),
        (("Motiejūnai II", "Širvintų", "k."), 16),
    ]
    # Packaging leaves out more: Griciūnai (380 addresses) and Juodė of Jauniūnų sen., ...
    packaging = without("packaging")
    assert len(packaging) == 185 and sum(packaging.values()) == 1648
    assert packaging.most_common(1) == [(("Griciūnai", "Jauniūnų", "k."), 380)]


def test_acceptance_examples(part):
    data, _ = part
    # Zibalai (mstl.), "ZIBALŲ SEN. Anciūnų k., ..., Zibalų mstl.": a Monday a month, 15 June ->
    # 21 December 2026 in the file.
    assert rows_of(data, "Zibalai", "household", kind_of_place="mstl.") == [ZIBALAI]
    zibalai = by_start(parsed(JUNE), "ZIBALŲ SEN. Anciūnų k.")
    assert (min(zibalai.dates), max(zibalai.dates)) == (date(2026, 6, 15), date(2026, 12, 21))
    assert len(zibalai.dates) == 7
    # Širvintos, Vilniaus g.: Tuesdays, twice a month to September, 9 June -> 22 December.
    assert rows_of(data, "Širvintos", "household", "Vilniaus g.", "Širvintų miesto") == [TOWN_1]
    town = by_start(parsed(JUNE), TOWN_1)
    assert (min(town.dates), max(town.dates)) == (date(2026, 6, 9), date(2026, 12, 22))
    # Zibalai's packaging, "ZIBALŲ SENIŪNIJA: Zibalai,Anciūnų k., ...".
    assert rows_of(data, "Zibalai", "packaging", kind_of_place="mstl.") == [
        "ZIBALŲ SENIŪNIJA: Zibalai,Anciūnų k.,Bei"
    ]


def test_the_streets_of_the_town(part):
    data, _ = part
    town = place(data, "Širvintos", "Širvintų miesto")
    for street, expected in (
        ("Upelio g.", [TOWN_1]),
        ("Staviškių g.", [TOWN_2]),
        ("Ateities g.", [TOWN_2]),  # "Ateities."
        ("Giminių g.", [TOWN_2]),  # "Giminių g,."
        # Some houses of a street are the street, as ecoservice.Routes reads them: "Zibalų g. Nr.
        # 19,21" and "Zibalų g. nuo Nr.18", "Totorių g. iki Nr. 12" and "Totorių g.12" in the
        # two routes (the app asks), "Musninkų g. iki Nr. 19", "Plento g. nuo Nr. 58 iki 90."
        ("Zibalų g.", [TOWN_2, TOWN_1]),
        ("Totorių g.", [TOWN_2, TOWN_1]),
        ("Musninkų g.", [TOWN_1]),
        ("Plento g.", [TOWN_1]),
    ):
        assert rows_of(data, "Širvintos", "household", street, "Širvintų miesto") == expected
    named = town["schedule"]["household"]["streets"]
    assert len(named) == 46
    # Streets no route names are left to the app, which offers the town's routes; "L.Giros
    # g." and "P.Cvirkos g." aren't the register's.
    unnamed = {label for key, label in town["streets"] if key not in named}
    assert {"I. Šeiniaus g.", "Pavasario g.", "Parko g.", "Saulės g."} <= unnamed
    assert len(unnamed) == 11
    assert "none" not in town["schedule"]["household"]
    # Packaging: "ŠIRVINTŲ SENIŪNIJA: Širvintų miestas: Ateities g., ...".
    assert rows_of(data, "Širvintos", "packaging", "Ateities g.", "Širvintų miesto") == [
        "ŠIRVINTŲ SENIŪNIJA: Širvintų miestas: At"
    ]


def test_a_village_in_the_town_s_list(part):
    data, _ = part
    # "..., Tvenkinio g., Kalnalaukio k., Staviškių g., ...": the village, and the streets after
    # it the town's. The route of Žemosios Viesios names it too: the app asks.
    assert rows_of(data, "Kalnalaukis", "household") == [TOWN_2, VIESOS]
    assert rows_of(data, "Širvintos", "household", "Staviškių g.", "Širvintų miesto") == [TOWN_2]


def test_streets_of_villages(part):
    data, _ = part
    # "Bajorų k. (Pušų g.)" and "Bajorų k.(Bajorų g.)", two routes of Alionių sen.
    assert rows_of(data, "Bajorai", "household", "Pušų g.") == [ALIONYS]
    assert rows_of(data, "Bajorai", "household", "Bajorų g.") == [
        "ALIONIŲ SEN. Arliškių k., Bajorų k.(Bajo"
    ]
    # "Širvintų k. (Družų g., Zosinos g.)" and "Širvintų k. (išskyrus Družų g., Zosinos g.)".
    village = "Širvintos"
    assert rows_of(data, village, "packaging", "Družų g.", "Širvintų") == [
        "ŠIRVINTŲ SENIŪNIJA: Širvintų k. (Družų g"
    ]
    assert rows_of(data, village, "packaging", district="Širvintų") == [
        "ŠIRVINTŲ SENIŪNIJA: Širvintų k. (išskyru"
    ]


def test_a_whole_eldership_but_some_villages(part):
    data, _ = part
    # "ALIONIŲ SENIŪNIJA: Visa seniūnija, išskyrus Kvakšių k": every place of Alionių sen. but
    # Kvakšiai, which has a row of its own.
    whole = "ALIONIŲ SENIŪNIJA: Visa seniūnija, išsky"
    assert rows_of(data, "Adolina", "packaging") == [whole]
    assert rows_of(data, "Kvakšiai", "glass") == ["ALIONIŲ SENIŪNIJA: Kvakšių k."]
    # "ČIOBIŠKIO SENIŪNIJA: Visa seniūnija".
    assert all(
        "packaging" in loc["schedule"]
        for loc in data["locations"]
        if loc["district"] == "Čiobiškio"
    )


def test_names_written_otherwise(part):
    data, _ = part
    for name, district, expected in (
        ("Žiūriai", "Zibalų", "ZIBALŲ SEN. Aukštadvario k., Degsnių k.,"),  # "Žiūrų k."
        ("Peliškiai", "Širvintų", ALIONYS),  # "Peliškiškių vs."
        ("Stavarygala", "Gelvonų", "GELVONŲ SEN. Cegelnės k., Dabužynės k.,"),  # "Staravygalos"
        ("Aukštosios Viesos", "Širvintų", "GELVONŲ SEN. Bagaslaviškio k., Bagaslavi"),  # "Aukštujų"
        ("Astruvka", "Čiobiškio", "ČIOBIŠKIO SEN. Astruvka, Babriškėlio k.,"),
        ("Bilotai", "Musninkų", "MUSNINKŲ SEN. Katūniškių k., Lydekupės v"),  # "Bilotai."
    ):
        assert rows_of(data, name, "household", district=district) == [expected], name


def test_places_in_two_routes_ask(part):
    data, _ = part
    asked = {
        (loc["name"], loc["district"])
        for loc in data["locations"]
        if "candidates" in loc.get("schedule", {}).get("household", {})
    }
    assert asked == {
        ("Daciūnai", "Širvintų"),
        ("Juodė", "Jauniūnų"),
        ("Kalnalaukis", "Širvintų"),
        ("Kazliškiai", "Širvintų"),
        ("Kvakšiai", "Alionių"),
        ("Motiejūnai", "Širvintų"),
        ("Nečionys", "Širvintų"),
        ("Paširvintis", "Širvintų"),
        ("Šalkiškės", "Jauniūnų"),
    }


def test_warnings(part):
    _, warnings = part
    household = [
        "Musninkų sen.: Lydekupės vs.",
        "Širvintų sen.: Sapnų vs.",
        "Širvintų sen.: SB Vasara",
        "Širvintų m.: L.Giros g.",
        "Širvintų m.: P.Cvirkos g.",
        "Širvintų m.: Ristūnų g.",
        "Kernavės sen.: Boguliubos vs.",
        "Kernavės sen.: Dailidžionių k.",
        "Kernavės sen.: Dailidžionių vs.",
        "Zibalų sen.: Groblės k.",
        "Musninkų sen.: Mantinionių k.",
        "Nečionių k.: Elektrinės g.",
        "Nečionių k.: Motiejūnų g.",
        "Kvakšių k.: Svajonių g.",
    ]
    packaging = ["Širvintų m.: L. Giros g.", "Širvintų m.: Miško g.", "Širvintų m.: P. Cvirkos g."]
    expected = [f"not a settlement or a street: household: {p}" for p in household] + [
        f"not a settlement or a street: {kind}: {p}"
        for p in packaging
        for kind in ("packaging", "glass")
    ]
    assert sorted(warnings) == sorted(expected)


# --- the periods -----------------------------------------------------------------


def test_the_next_period_continues_the_routes_of_the_same_places():
    # 25 May 2026: June-December linked next to April-June.
    files = [(f, parsed(f)) for f in (APRIL, JUNE)]
    warnings = sirvintos.combine(files, REGISTRY, date(2026, 5, 25))
    april, june = (result for _, result in files)
    assert june.areas == []
    # 18 routes name the same places: their rows get the dates to December. In June Ilgabradė
    # moved from the Bartkuškio route ("Ilgabradės k.") to Kabaldos' ("Ilgabradės vs."): those
    # two wait for June.
    assert sum(max(a.dates) > date(2026, 7, 1) for a in april.areas) == 18
    assert warnings == [
        "Širvintų r. household: the 2026-06-01 place 'JAUNIŪNŲ SEN. Ilgabradės vs. ŠIRVINTŲ SEN. "
        "Kabaldos k., Kria' doesn't match one 2026-04-01 place; its dates are left out until "
        "2026-06-01",
        "Širvintų r. household: the 2026-06-01 place 'JAUNIŪNŲ SEN. Bartkuškio k., Draučių k., "
        "Graužių k., Jauniūn' doesn't match one 2026-04-01 place; its dates are left out until "
        "2026-06-01",
        "Širvintų r. household: the 2026-04-01 place 'ŠIRVINTŲ SEN. Kabaldos k., Kriaunaitiškių "
        "vs., Paširvintis, ' has no dates for 2026-06-01",
        "Širvintų r. household: the 2026-04-01 place 'JAUNIŪNŲ SEN. Bartkuškio k., Draučių k., "
        "Graužių k., Ilgabra' has no dates for 2026-06-01",
    ]
    # From June the new period is the one in force.
    files = [(f, parsed(f)) for f in (APRIL, JUNE)]
    assert sirvintos.combine(files, REGISTRY, date(2026, 6, 20)) == []
    assert [len(result.areas) for _, result in files] == [0, 20]


def test_a_file_that_starts_in_the_last_one_s_months_replaces_it():
    # April-June starts in May-April's April: its April dates, not the year's.
    later = parsed(APRIL)
    for area in later.areas:
        area.dates = {d.replace(day=d.day + 1) if d.month == 4 else d for d in area.dates}
    files = [(YEAR, parsed(YEAR)), (APRIL, later)]
    assert sirvintos.combine(files, REGISTRY, date(2026, 3, 25)) == []
    first = by_start(files[0][1], "ZIBALŲ SEN. Aukštadvario k.")
    assert sorted(d for d in first.dates if d.month == 4) == [date(2026, 4, 12)]
    assert max(first.dates) == date(2026, 6, 1)


def test_a_period_that_ends_without_the_next():
    files = [(f, content(f)) for f in (JUNE, PACKAGING)]
    data, warnings = build_dataset(files, REGISTRY, date(2027, 1, 20), 31, sirvintos.SOURCE)
    assert warnings[:2] == [
        "the mixed waste schedule ended on 2026-12-31; no newer one is read",
        "the packaging schedule ended on 2026-12-31; no newer one is read",
    ]
    # The routes keep their last dates, 31 days on.
    zibalai = place(data, "Zibalai", kind_of_place="mstl.")
    assert row(data, zibalai["schedule"]["household"]["area"])["dates"] == ["2026-12-21"]


def test_the_next_period_in_place_of_the_last():
    # Linked in place of the last before it starts: the last one's December dates are lost.
    later = replace(JUNE, start=date(2027, 1, 1), end=date(2027, 6, 30))
    result = parsed(JUNE)
    for area in result.areas:
        area.dates = {d.replace(year=2027, month=d.month - 5) for d in area.dates}
    warnings = sirvintos.combine([(later, result)], REGISTRY, date(2026, 12, 20))
    assert warnings == ["no mixed waste schedule for today; the next starts on 2027-01-01"]


# --- the published folder --------------------------------------------------------


def test_published_folder_and_its_metrics(part, tmp_path):
    data, warnings = part
    built = [(sirvintos.PROVIDER, {**data, "warnings": len(warnings)})]
    dataset = merge_parts(built, sirvintos.MIXED_PAGE)
    assert [p["id"] for p in dataset["providers"]] == ["sirvintos"]
    assert all(a["provider"] == "sirvintos" for a in dataset["areas"])
    folder = tmp_path / "sirvintu-r"
    folder.mkdir()
    (folder / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    (folder / "addresses.json").write_text("{}", encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # 413 with mixed waste, and 24 with packaging only (Daubariškis k. of Musninkų sen., ...).
    assert 'siuksliaveze_data_places{source="sirvintos"} 437' in text
    assert 'siuksliaveze_data_areas{source="sirvintos",kind="glass"} 20' in text
    assert 'siuksliaveze_data_warnings{source="sirvintos"} 20' in text
    # regions.json lists the folder, so installed apps download it.
    assert regions.collect(tmp_path)["regions"] == [
        {
            "path": "sirvintu-r/",
            "kind": "settlements",
            "files": ["schedule.json", "addresses.json"],
            "providers": ["sirvintos"],
        }
    ]


def refused(url, timeout=0):
    raise OSError("HTTP Error 403: Forbidden")


def test_main_writes_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(sirvintos.http, "get", serve)
    monkeypatch.setattr(sirvintos.raseiniai.address_register, "fetch", refused)
    monkeypatch.setattr(sirvintos.raseiniai.address_points, "fetch", refused)
    assert sirvintos.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["sirvintos"]
    assert data["source"] == sirvintos.MIXED_PAGE
    addresses = json.loads((tmp_path / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > sirvintos.MUNICIPALITY.min_address_points


def test_the_copy_when_the_site_refuses_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(sirvintos.http, "get", serve)
    copy = tmp_path / "copy"
    sirvintos.save_copy(copy, TODAY)
    # As Ukmergės r.'s: the mixed waste page, the packaging page as a file named after its URL,
    # every file the job downloads (April-June too, for its months), and copy.json.
    index = json.loads((copy / "copy.json").read_text(encoding="utf-8"))
    assert index["takenAt"] == "2026-11-22" and index["page"] == sirvintos.MIXED_PAGE
    assert index["files"] == ["2332", JUNE.file_name, APRIL.file_name, PACKAGING.file_name]

    monkeypatch.setattr(sirvintos.http, "get", refused)
    monkeypatch.setattr(sirvintos, "COPY_DIR", copy)
    files, warnings = sirvintos.download(TODAY, 31)
    assert [f.file_name for f, _ in files] == [JUNE.file_name, PACKAGING.file_name]
    assert files[1][1] == content(PACKAGING)
    assert warnings == [
        f"{sirvintos.MIXED_PAGE}: unavailable (HTTP Error 403: Forbidden); used the copy from "
        "2026-11-22 (0 days old)"
    ]
    # Over 60 days old, it asks for a refresh; the routes keep their last dates meanwhile.
    _, warnings = sirvintos.download(date(2027, 1, 25), 31)
    assert warnings[0].endswith("uv run python -m schedule_pipeline.snapshot")
    # Without a copy, the error.
    monkeypatch.setattr(sirvintos, "COPY_DIR", tmp_path / "none")
    with pytest.raises(OSError, match="403"):
        sirvintos.download(TODAY, 31)


def test_the_committed_copy_can_be_built(monkeypatch):
    """The copy in pipeline/data, as the daily job reads it on GitHub's runners (it is
    refreshed, so only that it builds: build_dataset checks the counts)."""
    monkeypatch.setattr(sirvintos.http, "get", refused)
    files, warnings = sirvintos.download(date.today(), 31)
    assert "used the copy from" in warnings[0]
    assert {f.kind for f, _ in files} == {"household", "packaging"}
    build_dataset(files, REGISTRY, date.today(), 31, sirvintos.SOURCE)


def test_pages_without_the_files_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(sirvintos.http, "get", lambda url, timeout=0: b"<html></html>")
    monkeypatch.setattr(build, "live_or_snapshot", lambda name, live, snap: (snap()[0], None))
    assert sirvintos.main(["--out", str(tmp_path)]) == 1
    assert not (tmp_path / "schedule.json").exists()

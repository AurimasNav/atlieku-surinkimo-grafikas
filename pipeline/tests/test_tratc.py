"""Telšių RATC: the pages of Mažeikių r., Telšių r., Plungės r. and Rietavo sav., the yearly
spreadsheets, the routes and the joined years."""

import dataclasses
import io
import json
import re
from datetime import date
from urllib.parse import unquote

import openpyxl
import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import status, tratc
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "tratc" / "registry-mazeikiu-r-2026-11-17.json")
TODAY = date(2026, 11, 17)
HOUSEHOLD_2026 = "Mazeikiai_-misriu-grafikas-_2026-1.xlsx"
HOUSEHOLD_2027 = "2027-MKA-grafikas-MAZEIKIAI.xlsx"
FOOD_2026 = "Mazeikiai-biologiskai-skaidzios-ir-maisto-atl.-grafikas-2026.xlsx"
FOOD_2027 = "2027-bioskaidzios-atliekos-MAZEIKIAI.xlsx"
PACKAGING_2026 = "Mazeikiai_pakuociu-grafikas-_2026.xlsx"


def page_files():
    return tratc.find_files(fixture("tratc/page.html").decode("utf-8"))


def sources(today=TODAY):
    files, _ = tratc.select_files(page_files(), today)
    return [(f, fixture(f"tratc/{f.file_name}")) for f in files]


@pytest.fixture(scope="module")
def part():
    data, warnings = build_dataset(sources(), REGISTRY, TODAY, 31, tratc.SOURCE)
    return data, warnings


def place(data, name, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name and district in (None, loc["district"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


# --- the page ----------------------------------------------------------------


def test_finds_the_spreadsheets_on_the_page():
    files = page_files()
    assert {(f.kind, f.file_name) for f in files} == {
        ("household", HOUSEHOLD_2026),
        ("household", HOUSEHOLD_2027),
        ("food", FOOD_2026),
        ("food", FOOD_2027),
        ("packaging", PACKAGING_2026),
    }
    assert all(f.url.startswith("https://tratc.lt/wp-content/uploads/") for f in files)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        (HOUSEHOLD_2026, "household"),
        (HOUSEHOLD_2027, "household"),
        ("2027-MKA-Plunge-exel.xlsx", "household"),
        ("2028_MKA_grafikas_MAZEIKIAI.xlsx", "household"),
        (FOOD_2026, "food"),
        (FOOD_2027, "food"),
        (PACKAGING_2026, "packaging"),
        ("2027-Pakuociu-stiklo-Plunge-exel.xlsx", "packaging"),
        # Bulky waste is collected by registration.
        ("2027-Stambiagabariciu-grafikas-MAZEIKIAI.xlsx", None),
        ("DGA-surinkimo-grafikas-2026-m.-Plunges-raj.-sav.xlsx", None),
        # Apartment buildings alone: their shared containers, no list of places.
        ("2027-m.-daugiabuciai-bioskaidzios-grafikas-Plunge.xlsx", None),
        ("2027-m.-indiv-bioskaidzios-grafikas-PLUNGE.xlsx", "food"),
        ("2028-indiv-ir-daugiabuciu-maisto-grafikas.xlsx", "food"),
        ("mazeikiai.png", None),
    ],
)
def test_classifies_by_file_name(name, kind):
    assert tratc.classify(name) == kind


def test_unknown_spreadsheets_are_reported(monkeypatch):
    html = fixture("tratc/page.html").decode("utf-8")
    html += '<a href="/wp-content/uploads/2027/10/2028-komunaliniu-atlieku-grafikas.xlsx">x</a>'
    unknown = []
    assert len(tratc.find_files(html, unknown=unknown)) == 5
    # Bulky waste is known and left out on purpose.
    assert unknown == ["2028-komunaliniu-atlieku-grafikas.xlsx"]

    monkeypatch.setattr(
        tratc.http, "get", lambda url, timeout=0: html.encode() if url == tratc.PAGE_URL else b""
    )
    # Its name says nothing and its content isn't a schedule.
    _, warnings = tratc.download(tratc.MAZEIKIAI, TODAY, 31)
    assert warnings == [
        "2028-komunaliniu-atlieku-grafikas.xlsx: a spreadsheet of no kind we know; not read"
    ]


def test_year_from_the_file_name():
    assert tratc.file_year(HOUSEHOLD_2026) == 2026
    assert tratc.file_year(HOUSEHOLD_2027) == 2027
    assert tratc.file_year("grafikas.xlsx") is None
    assert tratc.file_year("grafikas-2026-2027.xlsx") is None


def test_reads_this_year_and_later():
    files, warnings = tratc.select_files(page_files(), TODAY)
    assert len(files) == 5 and warnings == []

    # In January last year's files are done; packaging for the new year isn't published yet, so
    # the newest one is still read, with a warning.
    files, warnings = tratc.select_files(page_files(), date(2027, 1, 5))
    assert {f.file_name for f in files} == {HOUSEHOLD_2027, FOOD_2027, PACKAGING_2026}
    assert warnings == ["no packaging schedule for 2027 on the page"]


def test_a_corrected_file_replaces_the_original():
    base = "https://tratc.lt/wp-content/uploads"
    old = SourceFile("household", f"{base}/2025/10/misriu-2026.xlsx", "misriu-2026.xlsx")
    new = SourceFile("household", f"{base}/2026/04/misriu-2026-1.xlsx", "misriu-2026-1.xlsx")
    for linked in ([old, new], [new, old]):
        files, warnings = tratc.select_files(linked, TODAY)
        assert files == [new]
        assert warnings == [
            "misriu-2026.xlsx: not read, misriu-2026-1.xlsx is a newer household schedule for 2026"
        ]


# --- the spreadsheets ----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(28, [28]), (28.0, [28]), ("5; 19", [5, 19]), ("3;31", [3, 31]), ("3; 17;31", [3, 17, 31])]
    + [(None, []), ("  ", [])],
)
def test_parse_days(value, expected):
    assert tratc.parse_days(value) == expected


@pytest.mark.parametrize("value", ["antradienis", "32", 2.5, "5-19", date(2027, 1, 5)])
def test_parse_days_rejects_anything_else(value):
    with pytest.raises(ValueError):
        tratc.parse_days(value)


def test_household_file():
    file = SourceFile("household", "https://x/h.xlsx", HOUSEHOLD_2027)
    result = tratc.parse_file(file, fixture(f"tratc/{HOUSEHOLD_2027}"))
    assert len(result.areas) == 21 and result.warnings == []
    town = next(a for a in result.areas if a.name == "Viekšniai")
    assert len(town.dates) == 26
    assert {date(2027, 1, 4), date(2027, 1, 18), date(2027, 12, 20)} <= town.dates
    # The notes and signatures under the table aren't routes.
    assert not any("SUDERINTA" in a.name or "PASTABOS" in a.name for a in result.areas)


def test_packaging_file_has_two_rows_per_route():
    file = SourceFile("packaging", "https://x/p.xlsx", PACKAGING_2026)
    result = tratc.parse_file(file, fixture(f"tratc/{PACKAGING_2026}"))
    packaging = [a for a in result.areas if a.kind == "packaging"]
    glass = [a for a in result.areas if a.kind == "glass"]
    assert len(packaging) == len(glass) == 17
    town = next(a for a in packaging if a.name == "Viekšniai")
    assert town.weekday == "Antradienis"
    assert {date(2026, 1, 27), date(2026, 12, 1), date(2026, 12, 29)} <= town.dates
    assert len(town.dates) == 13
    # The glass row has no route text of its own: it is the route of the row above.
    town_glass = next(a for a in glass if a.name == "Viekšniai")
    assert town_glass.weekday == "Ketvirtadienis"
    assert town_glass.dates == {
        date(2026, 3, 19),
        date(2026, 6, 11),
        date(2026, 9, 3),
        date(2026, 11, 26),
    }
    # Shared containers of apartment buildings have weekday rules, not dates.
    assert len(result.warnings) == 1 and "shared containers" in result.warnings[0]


def workbook(rows, hidden=()):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "2027"
    for cells in rows:
        sheet.append(cells)
    for letter in hidden:
        sheet.column_dimensions[letter].hidden = True
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


MONTHS = ["Sausis", "Vasaris", "Kovas", "Balandis", "Gegužė", "Birželis", "Liepa"]
MONTHS += ["Rugpjūtis", "Rugsėjis", "Spalis", "Lapkritis", "Gruodis"]
TEST_FILE = SourceFile("household", "https://x/h.xlsx", "h-2027.xlsx")


def test_hidden_columns_are_not_read():
    # Seen in this publisher's files: stale numbers left in columns hidden from the reader.
    content = workbook(
        [["Nr.", "Maršrutas", *MONTHS], [1, "Viekšniai", 31, 31, "9; 23", *[None] * 9]],
        hidden=("C", "D"),
    )
    result = tratc.parse_file(TEST_FILE, content)
    assert result.areas[0].dates == {date(2027, 3, 9), date(2027, 3, 23)}


def test_hidden_rows_are_not_read():
    book = openpyxl.Workbook()
    sheet = book.active
    for cells in (["Nr.", "Maršrutas", *MONTHS], [1, "Viekšniai", 5], [2, "Seda", 6]):
        sheet.append(cells)
    sheet.title = "2027"
    sheet.row_dimensions[3].hidden = True
    buffer = io.BytesIO()
    book.save(buffer)
    result = tratc.parse_file(TEST_FILE, buffer.getvalue())
    assert [a.name for a in result.areas] == ["Viekšniai"]


def test_year_in_the_sheet_must_be_the_year_of_the_file():
    # A date above the table ("SUDERINTA 2026-09-15") must not turn 2027 into 2026.
    content = workbook(
        [["SUDERINTA 2026-09-15"], ["Nr.", "Maršrutas", *MONTHS], [1, "Viekšniai", 5]]
    )
    with pytest.raises(ValueError, match="the file name says 2027"):
        tratc.parse_file(TEST_FILE, content)


def test_unreadable_cell_fails_loudly():
    content = workbook([["Nr.", "Maršrutas", *MONTHS], [1, "Viekšniai", "kas savaitę"]])
    with pytest.raises(ValueError, match="row 2: unrecognised day list"):
        tratc.parse_file(TEST_FILE, content)


def test_file_without_a_table_fails():
    with pytest.raises(ValueError, match="no schedule table"):
        tratc.parse_file(TEST_FILE, workbook([["Grafikas"]]))


# --- routes --------------------------------------------------------------------


def test_counts(part):
    data, _ = part
    kinds = [a["kind"] for a in data["areas"]]
    assert {k: kinds.count(k) for k in set(kinds)} == {
        "household": 21,
        "packaging": 17,
        "glass": 17,
        "food": 4,
    }
    stats = data["matching"]
    assert stats["locations"] == 190 and stats["unmatchedRows"] == 0
    assert stats["household.single"] >= 130 and stats["packaging.single"] >= 150
    # Food waste is collected in Mažeikiai town only.
    assert stats["food.byStreet"] == 1 and stats["food.none"] == 189
    assert all(loc["provider"] == "mazeikiai" for loc in data["locations"])


def test_town_is_split_by_street(part):
    data, _ = part
    town = place(data, "Mažeikiai")
    streets = {label: key for key, label in town["streets"]}
    household = town["schedule"]["household"]["streets"]
    first = row(data, household[streets["Žemaitės g."]][0])
    assert first["name"].startswith("Žagarėlės g. miesto sen.")
    assert {"2026-11-10", "2026-11-24"} <= set(first["dates"])
    # A street written with a typo ("Zastaičių g."), and one with a full first name in the
    # register ("K. Kavecko g." is "Konrado Kavecko g.").
    assert household[streets["Zastaučių g."]]
    assert household[streets["Konrado Kavecko g."]]
    # Another route on another street.
    other = row(data, household[streets["Vilniaus g."]][0])
    assert other["id"] != first["id"]
    # A street no route names (apartment buildings with shared containers) has no pickups,
    # instead of a choice between all the routes of the town.
    assert household[streets["Draugystės g."]] == []
    assert town["schedule"]["food"]["streets"][streets["Rasos 3-ioji g."]] == []
    # All four kinds of waste for a street of private houses.
    kinds = tratc.MAZEIKIAI.min_areas
    assert all(town["schedule"][k]["streets"][streets["Žemaitės g."]] for k in kinds)


def test_garden_communities_are_choices_of_the_town(part):
    data, _ = part
    town = place(data, "Mažeikiai")
    streets = {label: key for key, label in town["streets"]}
    household = town["schedule"]["household"]["streets"]
    garden = household[streets["SB „Rasa“"]]
    assert "SB Rasa" in row(data, garden[0])["name"]
    # Its numbered streets lead to the same row; the ordinary street of a similar name
    # ("Ašvos g." next to SB „Ašva“) keeps its own.
    assert household[streets["Rasos 3-ioji g."]] == garden
    assert household[streets["Ašvos Sodo 2-oji g."]] == household[streets["SB „Ašva“"]]
    assert household[streets["Ašvos g."]] != household[streets["SB „Ašva“"]]


def test_villages_get_the_row_of_their_route(part):
    data, _ = part
    village = place(data, "Laižuva")
    assert "streets" not in village
    household = row(data, village["schedule"]["household"]["area"])
    assert household["name"].startswith("Lendriškiai, Laižuva")
    assert row(data, village["schedule"]["packaging"]["area"])["weekday"] == "Antradienis"
    assert "food" not in village["schedule"]
    # "Tučiai I ir II" are two villages.
    one, two = place(data, "Tučiai I"), place(data, "Tučiai II")
    assert one["schedule"]["household"] == two["schedule"]["household"]
    # A typo: "Padvarnikai" is Padvarninkai.
    assert "household" in place(data, "Padvarninkai")["schedule"]


def test_villages_of_the_same_name(part):
    data, _ = part
    # Packaging names the eldership: "Lėlaičiai (Tirkšlių sen.)", "Lėlaičiai (Šerkšnėnų sen.)".
    north = place(data, "Lėlaičiai", "Tirkšlių")["schedule"]
    south = place(data, "Lėlaičiai", "Šerkšnėnų")["schedule"]
    assert row(data, north["packaging"]["area"])["name"].startswith("Gauryliai")
    assert row(data, south["packaging"]["area"])["name"].startswith("Rubikai")
    # Mixed waste only says "Užlieknė, Lėlaičiai, Žibikai, ...": the one where its neighbours
    # in the row are.
    assert row(data, north["household"]["area"])["name"].startswith("Užlieknė")
    assert "household" not in south


def test_names_that_match_nothing_are_reported(part):
    _, warnings = part
    unknown = [w for w in warnings if w.startswith("not a settlement or a street")]
    assert any("Lūšė" in w for w in unknown)
    assert len(unknown) <= 6


# --- this year and the next ------------------------------------------------------


def test_next_year_continues_the_same_routes(part):
    data, warnings = part
    # 2027 renumbers the routes and writes some differently (SB „Obuoliukas“ / SB Obuoliukas):
    # still one row per route, with the dates of both years.
    assert data["coverage"]["household"]["to"] == "2027-12-31"
    assert data["coverage"]["food"]["to"] > "2027-12-01"
    assert data["coverage"]["packaging"]["to"] == "2026-12-31"  # 2027 isn't published yet
    village = row(data, place(data, "Urvikiai")["schedule"]["household"]["area"])
    assert {"2026-11-26", "2026-12-24", "2027-01-21", "2027-12-23"} <= set(village["dates"])
    assert not any("covers other places" in w for w in warnings)
    assert all(a["current"] for a in data["areas"])


def routes(*rows):
    return ParseResult(
        [Area("household", name, dates={day}, provider="mazeikiai") for name, day in rows]
    )


NO_MINIMUM = dataclasses.replace(tratc.MAZEIKIAI, min_areas={})


def test_two_routes_never_continue_one():
    this_year = routes(("Viekšniai", date(2026, 12, 7)), ("Seda", date(2026, 12, 8)))
    # A route split in two with wording that reads as the same places.
    next_year = routes(("Viekšniai", date(2027, 1, 4)), ("Viekšniai (dalis)", date(2027, 1, 11)))
    file = SourceFile("household", "https://x/h.xlsx", "h.xlsx")
    parsed = [(file, this_year), (file, next_year)]
    warnings = tratc.combine(parsed, REGISTRY, date(2026, 12, 1), NO_MINIMUM)
    assert this_year.areas[0].dates == {date(2026, 12, 7)}
    assert sum("doesn't match one 2026 route" in w for w in warnings) == 2
    # Routes of this year that end with it are named too.
    assert sum("has no dates for 2027" in w for w in warnings) == 2


def test_next_year_is_checked_when_it_appears():
    this_year = routes(("Viekšniai", date(2026, 12, 7)))
    next_year = routes(("Viekšniai", date(2027, 1, 4)))
    file = SourceFile("household", "https://x/h.xlsx", "h.xlsx")
    with pytest.raises(ValueError, match="only 1 household routes in the 2027 file"):
        tratc.combine([(file, this_year), (file, next_year)], REGISTRY, date(2026, 12, 1))


def test_a_changed_route_waits_for_its_year():
    this_year = ParseResult(
        [
            Area("household", "Viekšniai", dates={date(2026, 12, 7)}, provider="mazeikiai"),
            Area("household", "Seda, Užežerė", dates={date(2026, 12, 8)}, provider="mazeikiai"),
        ]
    )
    next_year = ParseResult(
        [
            Area("household", "Viekšniai.", dates={date(2027, 1, 4)}, provider="mazeikiai"),
            Area("household", "Seda", dates={date(2027, 1, 5)}, provider="mazeikiai"),
        ]
    )
    file = SourceFile("household", "https://x/h.xlsx", "h.xlsx")
    parsed = [(file, this_year), (file, next_year)]
    warnings = tratc.combine(parsed, REGISTRY, date(2026, 12, 1), NO_MINIMUM)
    assert this_year.areas[0].dates == {date(2026, 12, 7), date(2027, 1, 4)}
    assert this_year.areas[1].dates == {date(2026, 12, 8)}
    assert next_year.areas == []
    assert len(warnings) == 2 and "the 2027 route 'Seda'" in warnings[0]
    assert "the 2026 route 'Seda, Užežerė' has no dates for 2027" in warnings[1]


PACKAGING_2027 = "2027-pakuotes-stiklas-grafikas-MAZEIKAI.xlsx"


def test_a_garden_written_sb_continues_its_route():
    # Mažeikių r. 2027 packaging and glass, linked after the page of 17 Nov: route 4 writes
    # "Sb „Šaltinėlis“" (2026: "SB „Šaltinėlis“"), "SB Ąžuolas" without quotes and
    # "Hipodromo g.,Troškučių g." without a space. The same places: its 2027 dates join the
    # 2026 route, of packaging and of glass.
    url = f"https://tratc.lt/wp-content/uploads/2026/11/{PACKAGING_2027}"
    files = [
        *sources(),
        (SourceFile("packaging", url, PACKAGING_2027), fixture(f"tratc/{PACKAGING_2027}")),
    ]
    data, warnings = build_dataset(files, REGISTRY, TODAY, 31, tratc.SOURCE)
    assert not [w for w in warnings if w.startswith(("packaging:", "glass:"))]
    town = place(data, "Mažeikiai")
    streets = {label: key for key, label in town["streets"]}
    for kind in ("packaging", "glass"):
        rows = data["areas"]
        assert sum(a["kind"] == kind for a in rows) == 17
        # Every route of 2026 continues into 2027.
        assert all(a["dates"][-1] > "2027" for a in rows if a["kind"] == kind)
        (garden,) = town["schedule"][kind]["streets"][streets["SB „Šaltinėlis“"]]
        route = row(data, garden)
        assert route["name"].startswith("Kalnėnų g., Kaštonų g.")
        assert route["dates"][0] < "2027" < route["dates"][-1]
        assert town["schedule"][kind]["streets"][streets["Kalnėnų g."]] == [garden]
        assert row(data, place(data, "Troškučiai")["schedule"][kind]["area"]) == route


def test_january_without_the_new_packaging_file():
    today = date(2027, 1, 5)
    data, _ = build_dataset(sources(today), REGISTRY, today, 31, tratc.SOURCE)
    # The places stay linked to last year's rows, which keep their last dates.
    village = place(data, "Laižuva")["schedule"]
    assert row(data, village["packaging"]["area"])["dates"] == ["2026-12-15"]
    assert row(data, village["household"]["area"])["dates"][0] == "2027-01-11"


def test_missing_kind_fails():
    household = [s for s in sources() if s[0].kind != "packaging"]
    with pytest.raises(ValidationError, match="no packaging schedule file"):
        build_dataset(household, REGISTRY, TODAY, 31, tratc.SOURCE)


# --- the published file ------------------------------------------------------------


def test_published_file_and_its_metrics(part, tmp_path):
    data, warnings = part
    data = {**data, "warnings": len(warnings)}
    dataset = merge_parts([(tratc.PROVIDER, data)], tratc.PAGE_URL)
    assert dataset["source"] == tratc.PAGE_URL
    assert [p["id"] for p in dataset["providers"]] == ["mazeikiai"]
    assert all(a["provider"] == "mazeikiai" for a in dataset["areas"])

    (tmp_path / "mazeikiu-r").mkdir()
    (tmp_path / "mazeikiu-r" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_areas{source="mazeikiai",kind="food"} 4' in text
    # Settlements with a schedule, not all 190 of the municipality.
    assert 'siuksliaveze_data_places{source="mazeikiai"} 157' in text
    # 2027-12-31: the last mixed waste pickup published.
    last = 'siuksliaveze_data_last_date_timestamp_seconds{source="mazeikiai",kind="household"}'
    assert f"{last} 1830211200" in text


# --- Telšių r., Plungės r. and Rietavo sav. ----------------------------------------------

DAY = date(2026, 11, 21)  # when the pages and files of the other municipalities were saved
REGISTRIES = {
    "telsiai": "registry-telsiu-r-2026-11-21.json",
    "plunge": "registry-plunges-r-2026-11-21.json",
    "rietavas": "registry-rietavo-sav-2026-11-21.json",
}
OTHERS = {m.provider.id: m for m in tratc.MUNICIPALITIES if m.provider.id in REGISTRIES}


def serve(url, timeout=0):
    """The saved pages and files of the other municipalities, as tratc.http.get."""
    for municipality in OTHERS.values():
        if url == municipality.provider.url:
            return fixture(f"tratc/page-{municipality.provider.id}.html")
    return fixture(f"tratc/{unquote(url.rsplit('/', 1)[-1])}")


@pytest.fixture(scope="module")
def parts():
    """Each municipality's part, built as the daily job does from its page."""
    built = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tratc.http, "get", serve)
        for key, municipality in OTHERS.items():
            files, warnings = tratc.download(municipality, DAY, 31)
            registry = Registry.load(FIXTURES / "tratc" / REGISTRIES[key])
            data, more = build_dataset(files, registry, DAY, 31, tratc.source(municipality))
            built[key] = (files, data, warnings + more)
    return built


def schedule_of(data, name, kind="household", district=None):
    return place(data, name, district)["schedule"][kind]


def street_rows(data, town, kind, label):
    """The rows of a street; None if it's left to the app."""
    location = place(data, town)
    key = next(key for key, text in location["streets"] if text == label)
    return location["schedule"][kind]["streets"].get(key)


def test_a_name_that_says_nothing_is_read_by_its_title():
    for name in ("Kopija-Plunge-2026-grafikas-003-3.xlsx", "Kopija-Rietavas-2026-grafikas.xlsx"):
        assert tratc.classify(name) is None
        assert tratc.classify_content(fixture(f"tratc/{name}")) == "packaging"
    assert tratc.classify_content(fixture("tratc/Rietavo-MKA-2026-Grafikas-2.xlsx")) == "household"
    assert tratc.classify_content(b"<html>Not found</html>") is None


def test_the_schedules_of_each_municipality(parts):
    names = {key: {(f.kind, f.file_name) for f, _ in files} for key, (files, *_) in parts.items()}
    assert names["telsiai"] == {("household", "2026-misriu_KP_SP_viesinimui-07.xlsx")}
    # This year's and next year's files; bulky waste ("DGA", "stambiagabarites") isn't read.
    assert names["plunge"] == {
        ("household", "MKA-atlieku-surinkimo-grafikas-Plunges-raj.sav_.-2026-03-12-men.xlsx"),
        ("household", "2027-MKA-Plunge-exel.xlsx"),
        ("packaging", "Kopija-Plunge-2026-grafikas-003-3.xlsx"),
        ("packaging", "2027-Pakuociu-stiklo-Plunge-exel.xlsx"),
        ("food", "Kopija-2026-m.-maisto-atliekos-Plunge.xlsx"),
    }
    # The 2027 mixed waste file of Rietavo sav. isn't out yet.
    assert names["rietavas"] == {
        ("household", "Rietavo-MKA-2026-Grafikas-2.xlsx"),
        ("packaging", "Kopija-Rietavas-2026-grafikas.xlsx"),
        ("packaging", "2027-pakuociu-stiklo-grafikas-RIETAVAS.xlsx"),
    }


@pytest.mark.parametrize(("value", "expected"), [(14.28, [14, 28]), (1.15, [1, 15])])
def test_two_days_typed_with_a_dot(value, expected):
    # Rietavo sav.: "14.28" in December, which the spreadsheet stores as a number.
    assert tratc.parse_days(value) == expected


@pytest.mark.parametrize("value", [5.1, 28.14, 14.285])
def test_numbers_that_are_no_two_days(value):
    with pytest.raises(ValueError):
        tratc.parse_days(value)


def parse(name, kind, key):
    return tratc.parse_file(
        SourceFile(kind, f"https://x/{name}", name), fixture(f"tratc/{name}"), OTHERS[key].provider
    )


def test_one_file_with_three_kinds_of_waste():
    # Telšių r.: a row per kind ("mišrios", "KP", "SP") under each route.
    result = parse("2026-misriu_KP_SP_viesinimui-07.xlsx", "household", "telsiai")
    kinds = [a.kind for a in result.areas]
    assert {k: kinds.count(k) for k in set(kinds)} == {
        "household": 20,
        "packaging": 20,
        "glass": 20,
    }
    assert result.warnings == []
    # The routes of shared containers are in hidden rows.
    assert not any(a.name.startswith("Didieji") for a in result.areas)
    route = [a for a in result.areas if a.name.startswith("Tryškių seniūnijos: Bėdakiai")]
    household = next(a for a in route if a.kind == "household")
    assert len(household.dates) == 26
    assert min(household.dates) == date(2026, 1, 6) and max(household.dates) == date(2026, 12, 22)
    glass = next(a for a in route if a.kind == "glass")
    assert glass.dates == {
        date(2026, 1, 19),
        date(2026, 4, 20),
        date(2026, 7, 13),
        date(2026, 10, 26),
    }


def test_routes_of_shared_containers_and_businesses_are_not_read():
    result = parse("2027-MKA-Plunge-exel.xlsx", "household", "plunge")
    assert len(result.areas) == 13
    assert not any(re.search(r"juridin|daugiabu", a.name) for a in result.areas)
    assert result.warnings == [
        "2027-MKA-Plunge-exel.xlsx [MKA] row 33: shared containers; not read"
    ]
    assert all(a.kind == "household" and a.weekday for a in result.areas)


PLUNGE_FOOD_2027 = "2027-m.-indiv-bioskaidzios-grafikas-PLUNGE.xlsx"
APARTMENTS_FOOD_2027 = "2027-m.-daugiabuciai-bioskaidzios-grafikas-Plunge.xlsx"


def test_notes_under_the_table_are_not_routes():
    # Plungės r. 2027 food waste: two notes in the route column under the table (in 2026 they
    # were above it).
    result = parse(PLUNGE_FOOD_2027, "food", "plunge")
    assert len(result.areas) == 5 and result.warnings == []
    assert {min(a.dates) for a in result.areas} == {date(2027, 1, 14), date(2027, 1, 15)}
    # Only those notes: another route without dates is still reported.
    content = workbook(
        [
            ["Nr.", "Maršrutas", *MONTHS],
            [1, "Viekšniai", 5],
            [None, "Prašome konteinerius išstumti iki 8 val. ryto. Jei dėl techninių kliūčių"],
            [None, "Raudonai pažymėti - perkeltas iš kito maršruto."],
            [2, "Seda"],
        ]
    )
    result = tratc.parse_file(TEST_FILE, content)
    assert [a.name for a in result.areas] == ["Viekšniai"]
    assert result.warnings == ["h-2027.xlsx [2027] row 5: no dates for 'Seda'"]


def test_food_waste_of_apartment_buildings_is_left_out(monkeypatch):
    # Plungės r. 2027: food waste in two files uploaded the same month, the one for apartment
    # buildings linked last. It isn't a correction of the other: one column for the town's
    # apartment buildings, the months in rows, no list of places.
    plunge = OTHERS["plunge"]
    links = "".join(
        f'<a href="https://tratc.lt/wp-content/uploads/2026/11/{name}">xlsx</a>'
        for name in (PLUNGE_FOOD_2027, APARTMENTS_FOOD_2027)
    )
    page = fixture("tratc/page-plunge.html") + links.encode()
    asked = []

    def get(url, timeout=0):
        asked.append(url)
        return page if url == plunge.provider.url else serve(url)

    monkeypatch.setattr(tratc.http, "get", get)
    files, warnings = tratc.download(plunge, DAY, 31)
    food = sorted(f.file_name for f, _ in files if f.kind == "food")
    assert food == [PLUNGE_FOOD_2027, "Kopija-2026-m.-maisto-atliekos-Plunge.xlsx"]
    # Left out by its name, without a warning, and not even downloaded.
    assert warnings == []
    assert not any(APARTMENTS_FOOD_2027 in url for url in asked)
    with pytest.raises(ValueError, match="no schedule table found"):
        parse(APARTMENTS_FOOD_2027, "food", "plunge")
    # The 2027 routes continue the five of 2026.
    registry = Registry.load(FIXTURES / "tratc" / REGISTRIES["plunge"])
    data, more = build_dataset(files, registry, DAY, 31, tratc.source(plunge))
    rows = [a for a in data["areas"] if a["kind"] == "food"]
    assert len(rows) == 5
    assert all(a["dates"][0] < "2027" and a["dates"][-1] > "2027-12" for a in rows)
    assert not [w for w in more if w.startswith("food:") or PLUNGE_FOOD_2027 in w]
    dates = row(data, schedule_of(data, "Babrungas", "food")["area"])["dates"]
    assert {"2026-12-17", "2027-01-14", "2027-12-16"} <= set(dates)


def test_a_second_line_of_a_row():
    # Plungės r. 2026: a second date of January or February in the line below ("3" over "23"),
    # the route's other cells merged. Those months are hidden: the file is for March-December.
    result = parse(
        "MKA-atlieku-surinkimo-grafikas-Plunges-raj.sav_.-2026-03-12-men.xlsx",
        "household",
        "plunge",
    )
    route = next(a for a in result.areas if a.name.startswith("Alsėdžių sen.:"))
    assert min(route.dates) == date(2026, 3, 9) and max(route.dates) == date(2026, 12, 28)
    assert not any(d.month < 3 for a in result.areas for d in a.dates)
    title = ["Nr.", "Maršrutas", "Diena", "Atliekų rūšis", *MONTHS]
    rows = [title, [1, "Seda", "", "Mišrios komunalinės atliekos", 3], [None, None, None, None, 23]]
    second = tratc.parse_file(TEST_FILE, workbook(rows)).areas
    assert [(a.kind, sorted(a.dates)) for a in second] == [
        ("household", [date(2027, 1, 3), date(2027, 1, 23)])
    ]
    assert result.warnings == [
        "MKA-atlieku-surinkimo-grafikas-Plunges-raj.sav_.-2026-03-12-men.xlsx [MKA] row 31: "
        "shared containers; not read"
    ]


def test_telsiai_villages_streets_and_gardens(parts):
    _, data, warnings = parts["telsiai"]
    kinds = [a["kind"] for a in data["areas"]]
    assert {k: kinds.count(k) for k in set(kinds)} == {
        "household": 20,
        "packaging": 20,
        "glass": 20,
    }
    assert sum(1 for loc in data["locations"] if "household" in loc.get("schedule", {})) >= 230
    # "Degaičių" in a list of streets of Telšiai is Degaičių g., not the village.
    village = row(data, schedule_of(data, "Degaičiai")["area"])
    assert village["name"].startswith("Degaičių seniūnijos:")
    assert row(data, street_rows(data, "Telšiai", "household", "Degaičių g.")[0])[
        "name"
    ].startswith("Telšių miesto Aguonų")
    # A street without its type is the "g.", "Ežero skg." the other one.
    first = street_rows(data, "Telšiai", "household", "Degaičių skg.")
    assert row(data, first[0])["name"].startswith("Telšių miesto Aukštoji")
    assert street_rows(data, "Telšiai", "household", "Ežero skg.") == first
    # A street no route names isn't "no pickup": the file leaves out streets of private houses
    # (Išdegos Pušies g.). The app offers the town's routes.
    assert street_rows(data, "Telšiai", "household", "Išdegos Pušies g.") is None
    assert street_rows(data, "Telšiai", "household", "Luokės skg.") is None
    assert all(schedule_of(data, "Telšiai")["streets"].values())
    # Gardens after "Sodai :": the streets named after them ("Austelės g." of Siraičiai is
    # named in the same route).
    gardens = street_rows(data, "Siraičiai", "household", "Austelės g.")
    assert row(data, gardens[0])["name"].startswith("Sodai : Aitvaras")
    assert row(data, schedule_of(data, "Siraičiai")["area"])["name"].startswith("Ryškėnų seniūnija")
    # "D.Palūkstis", "Sarakai I-II", and "Viešvėnai" next to "Viešvėnai II" in another route.
    assert schedule_of(data, "Didysis Palūkstis")["area"]
    assert schedule_of(data, "Sarakai I") == schedule_of(data, "Sarakai II")
    assert schedule_of(data, "Viešvėnai I") != schedule_of(data, "Viešvėnai II")
    assert any("not a settlement or a street: household: Jampolė" in w for w in warnings)


def test_plunge_sections_lists_and_next_year(parts):
    _, data, warnings = parts["plunge"]
    # "Žemaičių Kalvarijos sen.:" is one eldership; its town and village of one name.
    for kind in ("mstl.", "k."):
        location = next(
            loc
            for loc in data["locations"]
            if loc["name"] == "Žemaičių Kalvarija" and loc["type"] == kind
        )
        assert row(data, location["schedule"]["household"]["area"])["name"].startswith(
            "Žemaičių Kalvarijos sen.:"
        )
    # The 2027 route continues the 2026 one: the dates of both years.
    dates = row(data, schedule_of(data, "Šateikiai")["area"])["dates"]
    assert {"2026-11-03", "2026-12-29", "2027-01-12", "2027-12-28"} <= set(dates)
    # A route that changed waits for its year.
    assert any("the 2026 route 'Babrungo sen.: Babrungėnų k." in w for w in warnings)
    # Two parts of Medsėdžiai in two routes: the app asks.
    assert len(schedule_of(data, "Medsėdžiai")["candidates"]) == 2
    # Food waste: "Pakerai (Skalsos g.)" in one route, "Pakerai (išskyrus Skalsos g.)" in another.
    food = schedule_of(data, "Pakerai", "food")
    assert row(data, food["area"])["name"].startswith("Dariaus ir Girėno g. nuo Stoties g.")
    assert street_rows(data, "Pakerai", "food", "Skalsos g.") != [food["area"]]
    # Streets of Plungė in the packaging routes, with their types.
    both = street_rows(data, "Plungė", "packaging", "Žemaitės skg.")
    assert street_rows(data, "Plungė", "packaging", "Žemaitės g.") == both
    assert row(data, both[0])["name"].startswith("Plungės m.individualių namų: Žemaitės g.")


def test_rietavas_villages_of_one_name_and_the_town(parts):
    _, data, _ = parts["rietavas"]
    # Patyris of Medingėnų sen. and of Rietavo sen., in two sections of two routes.
    east = row(data, schedule_of(data, "Patyris", district="Medingėnų")["area"])
    west = row(data, schedule_of(data, "Patyris", district="Rietavo")["area"])
    assert east["name"].startswith("Daugėdų sen.:") and west["name"].startswith(
        "Rietavo miesto sen.:"
    )
    # "14.28": the last two pickups of the year.
    village = row(data, schedule_of(data, "Kungiai")["area"])
    assert village["dates"][-2:] == ["2026-12-14", "2026-12-28"]
    # "Sauslaukis (Rasos g.)" in one packaging route, "Sauslaukis" in another.
    packaging = schedule_of(data, "Sauslaukis", "packaging")
    assert street_rows(data, "Sauslaukis", "packaging", "Rasos g.") != [packaging["area"]]
    # The town: by street for mixed waste, a street no route names left to the app; one route
    # for packaging.
    assert street_rows(data, "Rietavas", "household", "Atgimimo g.")
    assert street_rows(data, "Rietavas", "household", "Lankų g.") is None
    packaging = row(data, schedule_of(data, "Rietavas", "packaging")["area"])
    assert packaging["name"].startswith("Rietavo m.individualių namų")


def test_one_file_for_the_four_municipalities(part, parts, tmp_path):
    mazeikiai, warnings = part
    built = [(tratc.PROVIDER, {**mazeikiai, "warnings": len(warnings)})]
    built += [
        (OTHERS[key].provider, {**data, "warnings": len(more)})
        for key, (_, data, more) in parts.items()
    ]
    dataset = merge_parts(built, tratc.PAGES)
    assert [p["id"] for p in dataset["providers"]] == ["mazeikiai", "telsiai", "plunge", "rietavas"]
    # Mažeikių r.'s part is as it was published on its own.
    assert [a for a in dataset["areas"] if a["provider"] == "mazeikiai"] == sorted(
        mazeikiai["areas"], key=lambda a: (a["kind"], a["name"].casefold())
    )
    (tmp_path / "mazeikiu-r").mkdir()
    (tmp_path / "mazeikiu-r" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # A source each, by its provider.
    assert 'siuksliaveze_data_places{source="mazeikiai"} 157' in text
    for key in ("telsiai", "plunge", "rietavas"):
        assert f'siuksliaveze_data_areas{{source="{key}",kind="household"}}' in text
    assert 'siuksliaveze_data_areas{source="plunge",kind="food"} 5' in text


def test_a_live_source_that_failed_is_not_tried_again():
    # The register's sites block cloud servers; each try costs its retries.
    calls = []

    def blocked():
        calls.append(1)
        raise OSError("HTTP Error 403: Forbidden")

    down: set[str] = set()
    for _ in range(3):
        with pytest.raises(OSError):
            tratc._once(blocked, "points", down)()
    assert len(calls) == 1 and down == {"points"}

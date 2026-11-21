"""Kretingos r.: the page of Kretingos komunalininkas, its PDFs, their routes, the half years of
mixed waste and the published folder."""

import json
from collections import defaultdict
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, kretinga, regions, status
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.locations import variant_key
from schedule_pipeline.model import Area, ParseResult
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "kretinga" / "registry-kretingos-r-2026-11-21.json")
TODAY = date(2026, 11, 21)
UPLOADS = "https://www.kretkom.lt/uploads/"
# The page's files and their copies in fixtures/kretinga/.
COPIES = {
    "2026 m- mišrios atliekos  I pusmetis.pdf": "misrios-2026-h1.pdf",
    "GRAFIKAS 2026 m- mišrios atliekos  II pusmetis (7-12 mėn).pdf": "misrios-2026-h2.pdf",
    "2026 m- PA grafikas.pdf": "pakuotes-2026.pdf",
    "Maisto atliekų surinkimas 2026 m.pdf": "maisto-2026.pdf",
    "Žaliųjų-biriųjų atliekų išvežimo grafikas Kretingos mieste 2026 m- 04-11 mėn_.pdf": (
        "zaliosios-2026.pdf"
    ),
}


def page_files():
    return kretinga.find_files(fixture("kretinga/page.html").decode("utf-8"))


def by_name(files, name):
    return next(f for f in files if f.file_name == name)


H1, H2, PACKAGING, FOOD, GREEN = (by_name(page_files()[0], name) for name in COPIES)


def content(file):
    return fixture(f"kretinga/{COPIES[file.file_name]}")


def parsed(file):
    return kretinga.parse_file(file, content(file))


@pytest.fixture(scope="module")
def part():
    files = [H2, PACKAGING, FOOD, GREEN]
    return build_dataset([(f, content(f)) for f in files], REGISTRY, TODAY, 31, kretinga.SOURCE)


def place(data, name, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name and district in (None, loc["district"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def route(data, area_id):
    """The route's number: "1 MARŠRUTAS. ..." is 1."""
    return int(row(data, area_id)["name"].split()[0])


def street(data, location, label):
    key = next(k for k, name in location["streets"] if name == label)
    return location["schedule"], key


def routes_of(data, name, kind, label, district=None):
    location = place(data, name, district)
    schedule, key = street(data, location, label)
    return sorted(route(data, i) for i in schedule[kind]["streets"][key])


# --- the page ----------------------------------------------------------------


def test_finds_the_files_by_their_links():
    files, warnings = page_files()
    found = [(f.kind, f.year, f.months, f.file_name) for f in files]
    assert found == [
        ("household", 2026, (1, 6), "2026 m- mišrios atliekos  I pusmetis.pdf"),
        (
            "household",
            2026,
            (7, 12),
            "GRAFIKAS 2026 m- mišrios atliekos  II pusmetis (7-12 mėn).pdf",
        ),
        ("packaging", 2026, (1, 12), "2026 m- PA grafikas.pdf"),
        # Linked by an image with only a title.
        ("food", 2025, (7, 12), "Maisto atliekų surinkimas 2025 II pusmetis.pdf"),
        ("food", 2026, (1, 12), "Maisto atliekų surinkimas 2026 m.pdf"),
        # The link names no months; the file's name does.
        (
            "green",
            2026,
            (4, 11),
            "Žaliųjų-biriųjų atliekų išvežimo grafikas Kretingos mieste 2026 m- 04-11 mėn_.pdf",
        ),
    ]
    # Bulky waste, branches, and the places of textile and cooking oil containers aren't read.
    assert warnings == []
    assert H2.url.startswith(f"{UPLOADS}GRAFIKAS%202026%20m-%20mi%C5%A1rios%20atliekos")
    assert (H2.start, H2.end) == (date(2026, 7, 1), date(2026, 12, 31))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026 m. Mišrių komunalinių atliekų išvežimo grafikas (07-12 mėn.)", (2026, (7, 12))),
        ("2027 m- mišrios atliekos  I pusmetis.pdf", (2027, (1, 6))),
        ("GRAFIKAS 2027 m- mišrios atliekos  II pusmetis.pdf", (2027, (7, 12))),
        ("ŽALIŲJŲ-BIRIŲJŲ ... GRAFIKAS 2026 m. balandžio–lapkričio mėn.", (2026, (4, 11))),
        ("STIKLO ... VALDŲ 2026 METAIS (01-12 MĖN.)", (2026, (1, 12))),
        ("2026 m- PA grafikas.pdf", (2026, None)),
        ("Tekstilė.pdf", (None, None)),
    ],
)
def test_the_period_in_words(text, expected):
    assert kretinga.period(text) == expected


def file(kind, year, months=None, name=None):
    name = name or f"{kind}-{year}-{months}.pdf"
    return kretinga.ScheduleFile(kind, f"{UPLOADS}{name}", name, year=year, months=months)


def test_reads_the_files_with_dates_still_to_publish():
    files, _ = page_files()
    selected, warnings = kretinga.select_files(files, TODAY)
    # Not the first half of 2026 nor the food waste of 2025: they ended.
    assert selected == [H2, PACKAGING, FOOD, GREEN] and warnings == []
    # In June, both halves: the next is read as soon as it's linked.
    selected, _ = kretinga.select_files(files, date(2026, 6, 20))
    assert [f for f in selected if f.kind == "household"] == [H1, H2]


def test_the_next_half_year_is_read_when_it_is_linked():
    next_half = file("household", 2027, (1, 6))
    selected, _ = kretinga.select_files([H2, next_half, PACKAGING], date(2026, 12, 20))
    assert selected == [H2, next_half, PACKAGING]
    # In January the last half still has dates to publish, for a month.
    selected, _ = kretinga.select_files([H2, next_half, PACKAGING], date(2027, 1, 20))
    assert selected[:2] == [H2, next_half]
    selected, _ = kretinga.select_files([H2, next_half, PACKAGING], date(2027, 2, 2))
    assert selected[0] == next_half


def test_a_late_half_year_keeps_the_last_one():
    # Nothing runs to today: the latest file is read, and its routes keep their last dates.
    selected, _ = kretinga.select_files([H1, H2, PACKAGING], date(2027, 3, 1))
    assert selected == [H2, PACKAGING]


def test_a_correction_linked_after_the_original_is_read():
    correction = file("household", 2026, (7, 12), "misrios-pataisytas.pdf")
    selected, warnings = kretinga.select_files([H2, correction, PACKAGING], TODAY)
    assert selected == [correction, PACKAGING]
    assert warnings[0] == (
        f"{H2.file_name}: not read, misrios-pataisytas.pdf is a newer mixed waste schedule for "
        "2026-07-01 - 2026-12-31"
    )
    assert "no food waste schedule on the page" in warnings


def test_a_missing_mixed_waste_file_fails():
    with pytest.raises(ValidationError, match="no mixed waste schedule on the page"):
        kretinga.select_files([PACKAGING], TODAY)


def test_a_link_without_a_year_is_reported():
    html = '<a href="/uploads/grafikas.pdf">Mišrių komunalinių atliekų išvežimo grafikas</a>'
    html += '<a href="/uploads/x.pdf">Naujas atliekų išvežimo grafikas 2026</a>'
    files, warnings = kretinga.find_files(html)
    assert files == []
    assert warnings == [
        "grafikas.pdf ('Mišrių komunalinių atliekų išvežimo grafikas'): no year in its link or "
        "name; not read",
        "x.pdf ('Naujas atliekų išvežimo grafikas 2026'): a schedule of no kind we read",
    ]


# --- the files -----------------------------------------------------------------


def dates(area):
    return sorted(area.dates)


def test_mixed_waste_july_to_december():
    areas = parsed(H2).areas
    assert len(areas) == 10 and {a.kind for a in areas} == {"household"}
    first = areas[0]
    assert first.name.startswith("1 MARŠRUTAS. Kretingos m gatvės: J. Basanavičiaus g., ")
    assert first.name.endswith("Tuzai, Kretingos miesto daugiabučiai.")
    assert first.district == "Kretingos r." and first.provider == "kretinga"
    assert first.weekday == "Pirmadienis"
    assert dates(first)[:3] == [date(2026, 7, 13), date(2026, 7, 27), date(2026, 8, 10)]
    assert dates(first)[-1] == date(2026, 12, 28) and len(first.dates) == 13
    # "13, 27," under August and "10, 24" under September.
    fourth = areas[3]
    assert {d for d in fourth.dates if d.month in (8, 9)} == {
        date(2026, 8, 13),
        date(2026, 8, 27),
        date(2026, 9, 10),
        date(2026, 9, 24),
    }
    # Route 7 runs on to page 2: its places are read whole.
    assert areas[6].name.endswith("SB “Vienybė”. Kretingos miesto daugiabučiai.")
    assert "Nemuno g., Neringos g., Nidos g." in areas[6].name
    # The empty line of 2-point letters under route 1 ("11") isn't read.
    assert areas[1].name.startswith("2 MARŠRUTAS.")


def test_mixed_waste_january_to_june():
    areas = parsed(H1).areas
    assert len(areas) == 10
    assert dates(areas[0])[0] == date(2026, 1, 12) and dates(areas[0])[-1] == date(2026, 6, 29)
    assert all(d.month <= 6 for a in areas for d in a.dates)


def test_packaging_and_glass():
    areas = parsed(PACKAGING).areas
    assert [a.kind for a in areas] == ["packaging", "glass"] * 15
    packaging, glass = areas[0], areas[1]
    assert len(packaging.dates) == 12 and dates(packaging)[0] == date(2026, 1, 12)
    # Once a quarter, under the months of its column.
    assert [(d.month, d.day) for d in dates(glass)] == [(2, 23), (5, 25), (8, 24), (11, 23)]
    assert glass.weekday == "Pirmadienis"


def test_food_waste_of_kretinga():
    # The row of the shared containers ("Pagal poreikį") isn't read.
    (area,) = parsed(FOOD).areas
    assert (area.kind, area.name) == ("food", "KRETINGOS MIESTO individualios valdos")
    assert [(d.month, d.day) for d in dates(area)[:4]] == [(1, 14), (1, 28), (2, 11), (2, 25)]
    # Wednesdays, weekly from May to September, and 5 May (a Tuesday), as published.
    assert len(area.dates) == 36 and area.weekday is None
    assert {d.weekday() for d in area.dates if d != date(2026, 5, 5)} == {2}


def test_green_waste_of_kretinga():
    # Its months are written bottom to top.
    areas = parsed(GREEN).areas
    assert [a.kind for a in areas] == ["green"] * 3
    assert areas[0].name.startswith("Kretingos miesto gatvės: J. Basanavičiaus, Kalno, ")
    assert dates(areas[0]) == [
        date(2026, 4, 7),
        date(2026, 4, 28),
        date(2026, 5, 19),
        date(2026, 6, 9),
        date(2026, 6, 30),
        date(2026, 7, 21),
        date(2026, 8, 11),
        date(2026, 9, 1),
        date(2026, 9, 22),
        date(2026, 10, 13),
        date(2026, 11, 3),
    ]


def test_a_title_for_other_months_than_the_link_fails():
    wrong = file("household", 2026, (1, 6), H2.file_name)
    with pytest.raises(ValueError, match=r"is for 2026 \(7, 12\), the link for 2026 \(1, 6\)"):
        kretinga.parse_file(wrong, content(H2))


def test_a_file_of_another_kind_fails():
    wrong = file("household", 2026, (1, 12), PACKAGING.file_name)
    with pytest.raises(ValueError, match="no household dates for route 1"):
        kretinga.parse_file(wrong, content(PACKAGING))


def test_dates_off_their_weekday_fail(monkeypatch):
    # The wrong year: route 1's Mondays of 2026 are Sundays in 2025.
    monkeypatch.setattr(kretinga, "period", lambda text: (2025, (7, 12)))
    with pytest.raises(ValueError, match="the dates of route 1 aren't on one working day"):
        kretinga.parse_file(file("household", 2025, (7, 12)), content(H2))


def table(*rows, title="GRAFIKAS 2026 M. (07-08 MĖN.)"):
    return lambda content: (title, [list(r) for r in rows])


ROUTE = ("1 MARŠRUTAS. Kaimai: Abakai.", "", "")
MONTHS = ("", "Liepa", "Rugpjūtis")


@pytest.mark.parametrize(
    ("rows", "error"),
    [
        ((ROUTE, MONTHS, ("Mišrios komunalinės atliekos", "6, 2O", "3")), "unrecognised days"),
        ((ROUTE, MONTHS, ("Mišrios komunalinės atliekos", "6, 32", "3")), "day is out of range"),
        ((ROUTE, ("", "Liepa", "Spalis"), ("Mišrios", "6", "3")), r"months \[7, 10\]"),
        ((ROUTE, MONTHS, ("Didžiosios atliekos", "6", "3")), "unknown row"),
        ((MONTHS, ("Mišrios komunalinės atliekos", "6", "3")), "days before the first route"),
        ((ROUTE, MONTHS, ("Mišrios komunalinės atliekos", "6", "3")) * 2, r"routes \[1, 1\]"),
    ],
)
def test_strict_about_the_tables(monkeypatch, rows, error):
    monkeypatch.setattr(kretinga, "_tables", table(*rows))
    monkeypatch.setattr(kretinga, "MIN_ROUTES", {"household": 1})
    with pytest.raises(ValueError, match=error):
        kretinga.parse_file(file("household", 2026, (7, 8)), b"")


def test_too_few_routes_fail(monkeypatch):
    rows = (ROUTE, MONTHS, ("Mišrios komunalinės atliekos", "6, 20", "3, 17"))
    monkeypatch.setattr(kretinga, "_tables", table(*rows))
    with pytest.raises(ValueError, match=r"only 1 routes \(expected at least 8\)"):
        kretinga.parse_file(file("household", 2026, (7, 8)), b"")


# --- the places ----------------------------------------------------------------


def test_counts(part):
    data, warnings = part
    assert data["matching"] == {
        "food.none": 193,
        "food.single": 1,
        "glass.byStreet": 5,
        "glass.none": 72,
        "glass.single": 117,
        "green.byStreet": 1,
        "green.none": 193,
        "household.ambiguous": 1,
        "household.byStreet": 5,
        "household.none": 25,
        "household.single": 163,
        "locations": 194,
        "packaging.byStreet": 5,
        "packaging.none": 72,
        "packaging.single": 117,
        "unmatchedRows": 0,
    }
    assert len(data["areas"]) == 44


def test_acceptance_examples():
    # Every mixed waste date of the second half of 2026, as in the file.
    files = [(f, content(f)) for f in (H2, PACKAGING)]
    data, _ = build_dataset(files, REGISTRY, date(2026, 7, 1), 31, kretinga.SOURCE)
    kretingsodis = row(data, place(data, "Kretingsodis")["schedule"]["household"]["area"])
    assert kretingsodis["name"].startswith("1 MARŠRUTAS.")
    assert (kretingsodis["dates"][0], kretingsodis["dates"][-1]) == ("2026-07-13", "2026-12-28")
    assert len(kretingsodis["dates"]) == 13 and kretingsodis["weekday"] == "Pirmadienis"
    darbenai = row(data, place(data, "Darbėnai")["schedule"]["household"]["area"])
    assert darbenai["name"].startswith("9 MARŠRUTAS. Kaimai: Darbėnų mstl.")
    assert (darbenai["dates"][0], darbenai["dates"][-1]) == ("2026-07-09", "2026-12-24")
    assert len(darbenai["dates"]) == 13 and darbenai["weekday"] == "Ketvirtadienis"


def test_towns_of_one_route(part):
    data, _ = part
    for name, household, packaging in (
        ("Salantai", 10, 10),
        ("Darbėnai", 9, 5),
        ("Kartena", 5, 13),
    ):
        schedule = place(data, name)["schedule"]
        assert route(data, schedule["household"]["area"]) == household
        assert route(data, schedule["packaging"]["area"]) == packaging
        assert route(data, schedule["glass"]["area"]) == packaging
        assert set(schedule["household"]) == {"area"}


def test_the_streets_of_kretinga(part):
    data, _ = part
    kretinga_ = place(data, "Kretinga")
    assert set(kretinga_["schedule"]["household"]) == {"streets"}
    assert routes_of(data, "Kretinga", "household", "J. Basanavičiaus g.") == [1]
    assert routes_of(data, "Kretinga", "household", "Jono Karolio Chodkevičiaus g.") == [4]
    assert routes_of(data, "Kretinga", "household", "Malūno tak.") == [7]
    # Some houses of a street: the routes that name it share it, and the app asks.
    assert routes_of(data, "Kretinga", "household", "Palangos g.") == [1, 6]
    assert routes_of(data, "Kretinga", "household", "Taikos g.") == [2, 3]
    assert routes_of(data, "Kretinga", "household", "Vilniaus g.") == [4, 6]
    # Packaging: written without types ("J Basanavičiaus", "Palangos g 1-16").
    assert routes_of(data, "Kretinga", "packaging", "J. Basanavičiaus g.") == [2]
    assert routes_of(data, "Kretinga", "packaging", "Palangos g.") == [2, 4]
    assert routes_of(data, "Kretinga", "packaging", "Beržų skg.") == [1]
    # Green waste: three routes of the town's streets, without numbers in their text.
    schedule, key = street(data, kretinga_, "Taikos g.")
    (green,) = schedule["green"]["streets"][key]
    assert row(data, green)["name"].startswith("Kretingos miesto gatvės: Melioratorių, ")
    # The town's food waste is one route for all of it.
    food = row(data, kretinga_["schedule"]["food"]["area"])
    assert food["name"] == "KRETINGOS MIESTO individualios valdos"
    assert set(kretinga_["schedule"]["food"]) == {"area"}


def test_streets_no_route_names_are_left_to_the_app(part):
    data, _ = part
    # Not in the household rows' list of streets: the app offers the town's routes. Nothing
    # gets an empty list (no pickup) anywhere.
    schedule, key = street(data, place(data, "Kretinga"), "Genių g.")
    assert key not in schedule["household"]["streets"]
    schedule, key = street(data, place(data, "Kretinga"), "Gandrų g.")  # of SB „Draugystė“
    assert key not in schedule["household"]["streets"]
    assert not [
        (loc["name"], kind)
        for loc in data["locations"]
        for kind, r in loc.get("schedule", {}).items()
        if any(not rows for rows in r.get("streets", {}).values())
    ]
    named = len(place(data, "Kretinga")["schedule"]["household"]["streets"])
    assert (named, len(place(data, "Kretinga")["streets"])) == (175, 274)


def test_villages_of_one_name(part):
    data, _ = part
    # "Tinteliai (Kretingos sen.)", "Tinteliai (Kūlupėnų sen.)".
    tinteliai = place(data, "Tinteliai", "Kretingos")["schedule"]
    assert route(data, tinteliai["household"]["area"]) == 9
    assert route(data, tinteliai["packaging"]["area"]) == 5
    assert route(data, place(data, "Tinteliai", "Kūlupėnų")["schedule"]["household"]["area"]) == 10
    # "Kalniškiai" in a route of Kartenos sen.'s villages: Kalniškiai of Kartenos sen.
    assert route(data, place(data, "Kalniškiai", "Kartenos")["schedule"]["household"]["area"]) == 5
    assert "schedule" not in place(data, "Kalniškiai", "Imbarės")
    # Kadagynai of Darbėnų sen. and Kadagynas of Imbarės sen.
    assert route(data, place(data, "Kadagynai")["schedule"]["household"]["area"]) == 9
    assert route(data, place(data, "Kadagynas")["schedule"]["household"]["area"]) == 10
    # Named in two routes: the app asks.
    assert place(data, "Mažieji Žalimai")["schedule"]["household"]["candidates"]


def test_names_written_otherwise(part):
    data, _ = part
    for name, number in (
        ("Naujoji Įpiltis", 2),  # "N. Įpiltis" (packaging), "Naujoji Įpiltis"
        ("Senoji Įpiltis", 2),  # "S. Įpiltis", "Senoji Įpiltis"
        ("Vaineikių Medsėdžiai", 7),  # "Vaineikiai-Medsėdžiai"
        ("Genčų Medsėdžiai", 7),
        ("Klausgalvų Medsėdžiai", 10),  # "Klausgalvai-Medsėdžiai, Klausgalvų Medsėdžiai"
        ("Akmenalės", 4),  # "Akmenaliai"
        ("Auksūdys", 2),  # "Auksūdis"
        ("Drumulis", 2),  # "Drumuliai"
        ("Gaivališkė", 1),  # "Gaivališkės"
        ("Laumalės", 8),  # "Laumaliai"
    ):
        assert route(data, place(data, name)["schedule"]["household"]["area"]) == number, name
    for name in ("Naujoji Įpiltis", "Senoji Įpiltis"):
        assert route(data, place(data, name)["schedule"]["packaging"]["area"]) == 12


def test_villages_split_by_street(part):
    data, _ = part
    # "Padvariai (be Darbėnų pl., Palaukės, Grafų Tiškevičių, Pamario, Švyturio, Sodininkų,
    # Vienkiemio g. tik 22-68)" in route 7, the streets left out in routes 5, 6 and 9.
    padvariai = place(data, "Padvariai")["schedule"]["household"]
    assert route(data, padvariai["area"]) == 7
    assert routes_of(data, "Padvariai", "household", "Darbėnų pl.") == [9]
    assert routes_of(data, "Padvariai", "household", "Švyturio g.") == [6]
    assert routes_of(data, "Padvariai", "household", "Sodininkų g.") == [5]
    assert routes_of(data, "Padvariai", "household", "Vienkiemio g.") == [7, 9]
    schedule, key = street(data, place(data, "Padvariai"), "Sodų g.")
    assert key not in padvariai["streets"]  # the rest of the village: route 7
    # Packaging: "Darbėnų pl. 20-44" (route 5) and "Darbėnų pl 1-19" (15).
    assert routes_of(data, "Padvariai", "packaging", "Darbėnų pl.") == [5, 15]
    assert routes_of(data, "Padvariai", "packaging", "Vienkiemio g.") == [8, 15]
    # "Kluonaliai (tik Giminių, Svainių, ...)": streets without their type.
    kluonaliai = place(data, "Kluonaliai")["schedule"]["household"]
    assert set(kluonaliai) == {"streets"}
    assert routes_of(data, "Kluonaliai", "household", "Giminių g.") == [3]
    assert routes_of(data, "Kluonaliai", "household", "Jauryklos aklg.") == [3]
    assert routes_of(data, "Kluonaliai", "household", "Tolių g.") == [2]
    assert routes_of(data, "Kluonaliai", "household", "Metalo g.") == [6]
    # "Kluonaliai (be Jablonskio, Metalo, Kaimynų, Meistrų, Aitvarų g.)" in packaging route 7.
    assert route(data, place(data, "Kluonaliai")["schedule"]["packaging"]["area"]) == 7
    assert routes_of(data, "Kluonaliai", "packaging", "Metalo g.") == [6]
    assert routes_of(data, "Žygai", "household", "Bliūdsakių g.") == [6]
    assert route(data, place(data, "Žygai")["schedule"]["household"]["area"]) == 8


def test_garden_communities(part):
    data, warnings = part
    # SB „Rubuliai“: one more choice in the street list of Rubuliai.
    rubuliai = place(data, "Rubuliai")
    key = variant_key("SB „Rubuliai“")
    assert [key, "SB „Rubuliai“"] in rubuliai["streets"]
    packaging = rubuliai["schedule"]["packaging"]
    assert route(data, packaging["area"]) == 13
    assert [route(data, i) for i in packaging["streets"][key]] == [14]
    # The others: the register doesn't say where they are.
    assert "not a settlement or a street: household: Kretingos r.: SB „Medvalakis“" in warnings
    assert "not a settlement or a street: green: Kretingos r.: SB „Draugystė“" in warnings


def test_warnings(part):
    _, warnings = part
    gardens = [w for w in warnings if ": SB " in w]
    assert len(gardens) == 32
    assert [w for w in warnings if w not in gardens] == [
        "not a settlement or a street: packaging: Kretingos m.: Alksnio",
        "not a settlement or a street: glass: Kretingos m.: Alksnio",
        "not a settlement or a street: green: Kretingos m.: Alksnio",
        "not a settlement or a street: green: Kretingos m.: Kvecių",
    ]


def test_settlements_without_mixed_waste(part):
    data, _ = part
    missing = {
        loc["name"] for loc in data["locations"] if "household" not in loc.get("schedule", {})
    }
    # A garden community's streets, and villages no file names (most without addresses).
    assert {"Kumponai", "Greičiai", "Kalniškiai", "Būdviečiai", "Naujukai"} <= missing
    assert len(missing) == 25


def test_a_street_left_out_that_no_route_names_isnt_no_pickup():
    reader = kretinga.Routes(kretinga.Index(REGISTRY), kretinga.PROVIDER, defaultdict(dict))
    areas = [
        Area("household", f"{n} MARŠRUTAS. Kaimai: {places}", "Kretingos r.")
        for n, places in (
            (1, "Padvariai (be Sodininkų g.)."),
            (2, "Padvariai (be Salantų g.), Klibiai."),
            (3, "Padvariai (tik Sodininkų g.)."),
        )
    ]
    reader.prepare(areas)
    (_, clause), *_ = reader.clauses(areas[0])[0]
    assert clause.excluded  # Sodininkų g. is route 3's
    (_, clause), *_ = reader.clauses(areas[1])[0]
    assert not clause.excluded
    assert reader.unknown == ["Padvarių k.: Salantų g (left out, but no route names it)"]


# --- the half years ------------------------------------------------------------


def moved(day, days, years):
    day += timedelta(days=days)
    return day.replace(year=day.year + years)


def shifted(result, days=0, years=0):
    """The routes of a file, their dates moved: another period's file."""
    return ParseResult(
        [
            Area(
                a.kind,
                a.name,
                a.district,
                provider=a.provider,
                dates={moved(d, days, years) for d in a.dates},
            )
            for a in result.areas
        ]
    )


def test_the_next_half_year_continues_the_routes_of_the_same_places():
    # 20 June 2026: the second half of the year is linked next to the first.
    first, second = parsed(H1), parsed(H2)
    warnings = kretinga.combine([(H1, first), (H2, second)], REGISTRY, date(2026, 6, 20))
    # Routes 1, 3, 4, 6 and 9 name the same places in both: their rows get July's dates.
    continued = [a for a in first.areas if max(a.dates) > date(2026, 7, 1)]
    assert [a.name.split()[0] for a in continued] == ["1", "3", "4", "6", "9"]
    assert second.areas == []
    assert warnings[0] == (
        "Kretingos r. household: the 2026-07-01 place '2 MARŠRUTAS. Kretingos m gatvės: Aisčių "
        "g., Algirdo aklg., A' doesn't match one 2026-01-01 place; its dates are left out until "
        "2026-07-01"
    )
    assert len(warnings) == 10
    # In July the second half takes over.
    first, second = parsed(H1), parsed(H2)
    assert kretinga.combine([(H1, first), (H2, second)], REGISTRY, date(2026, 7, 2)) == []
    assert first.areas == [] and len(second.areas) == 10


def test_a_half_year_that_ends_without_the_next():
    files = [(f, content(f)) for f in (H2, PACKAGING)]
    data, warnings = build_dataset(files, REGISTRY, date(2027, 2, 15), 31, kretinga.SOURCE)
    assert warnings[:2] == [
        "the mixed waste schedule ended on 2026-12-31; no newer one is read",
        "the packaging schedule ended on 2026-12-31; no newer one is read",
    ]
    # The routes keep their last dates, 31 days on.
    kretingsodis = row(data, place(data, "Kretingsodis")["schedule"]["household"]["area"])
    assert kretingsodis["dates"] == ["2026-12-28"]
    darbenai = row(data, place(data, "Darbėnai")["schedule"]["household"]["area"])
    assert darbenai["dates"] == ["2026-12-24"]


def test_the_next_half_year_in_place_of_the_last():
    # Linked in place of the last before it starts: the last one's December dates are lost.
    next_half = shifted(parsed(H1), years=1)
    warnings = kretinga.combine([(H1, next_half)], REGISTRY, date(2026, 12, 20))
    assert warnings == ["no mixed waste schedule for today; the next starts on 2027-01-01"]


def test_overlapping_files_fail():
    with pytest.raises(ValueError, match="overlap"):
        kretinga.combine([(H2, parsed(H2)), (H2, shifted(parsed(H1), days=150))], REGISTRY, TODAY)


# --- the published folder --------------------------------------------------------


def test_published_folder_and_its_metrics(part, tmp_path):
    data, warnings = part
    built = [(kretinga.PROVIDER, {**data, "warnings": len(warnings)})]
    dataset = merge_parts(built, kretinga.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == ["kretinga"]
    assert all(a["provider"] == "kretinga" for a in dataset["areas"])
    folder = tmp_path / "kretingos-r"
    folder.mkdir()
    (folder / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    (folder / "addresses.json").write_text("{}", encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="kretinga"} 170' in text
    assert 'siuksliaveze_data_areas{source="kretinga",kind="green"} 3' in text
    assert 'siuksliaveze_data_warnings{source="kretinga"} 36' in text
    # regions.json lists the folder, so installed apps download it.
    assert regions.collect(tmp_path)["regions"] == [
        {
            "path": "kretingos-r/",
            "kind": "settlements",
            "files": ["schedule.json", "addresses.json"],
            "providers": ["kretinga"],
        }
    ]


def test_main_writes_the_folder(tmp_path, monkeypatch):
    by_url = {f.url: COPIES[f.file_name] for f in (H1, H2, PACKAGING, FOOD, GREEN)}

    def serve(url, timeout=0):
        if url == kretinga.PAGE_URL:
            return fixture("kretinga/page.html")
        if url in by_url:
            return fixture(f"kretinga/{by_url[url]}")
        raise OSError(f"HTTP Error 404: {url}")

    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kretinga.http, "get", serve)
    monkeypatch.setattr(kretinga.address_register, "fetch", blocked)
    monkeypatch.setattr(kretinga.address_points, "fetch", blocked)
    assert kretinga.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["kretinga"]
    addresses = json.loads((tmp_path / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > kretinga.MIN_ADDRESS_POINTS


def test_a_page_without_the_files_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(kretinga.http, "get", lambda url, timeout=0: b"<html></html>")
    monkeypatch.setattr(build, "live_or_snapshot", lambda name, live, snap: (snap()[0], None))
    assert kretinga.main(["--out", str(tmp_path)]) == 1
    assert not (tmp_path / "schedule.json").exists()

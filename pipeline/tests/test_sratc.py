"""Šiaulių RATC: the municipalities' pages, the five yearly PDFs, their places and next year;
Radviliškio r.'s quarterly mixed waste and yearly packaging files."""

import json
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from functools import cache

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, sratc, status
from schedule_pipeline.build import (
    ValidationError,
    build_dataset,
    current_rows,
    merge_parts,
    published_part,
)
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "sratc" / "registry-sratc-2026-11-21.json")
TODAY = date(2026, 11, 21)
FILES = {
    "Šiaulių r.": "siauliu-r-2026.pdf",
    "Akmenės r.": "akmenes-r-2026.pdf",
    "Joniškio r.": "joniskio-r-2026.pdf",
    "Kelmės r.": "kelmes-r-2026.pdf",
    "Pakruojo r.": "pakruojo-r-2026.pdf",
}
SOURCES = {
    name: SourceFile("household", f"https://www.sratc.lt/uploads/{file}", file, name)
    for name, file in FILES.items()
}
# Drąsučiai's mixed waste, as the Šiaulių r. file lists it: every other Thursday, Wednesday 23
# December for Christmas Eve.
DRASUCIAI = [
    (1, 8),
    (1, 22),
    (2, 5),
    (2, 19),
    (3, 5),
    (3, 19),
    (4, 2),
    (4, 16),
    (4, 30),
    (5, 14),
    (5, 28),
    (6, 11),
    (6, 25),
    (7, 9),
    (7, 23),
    (8, 6),
    (8, 20),
    (9, 3),
    (9, 17),
    (10, 1),
    (10, 15),
    (10, 29),
    (11, 12),
    (11, 26),
    (12, 10),
    (12, 23),
]


def files(names=FILES):
    return [(SOURCES[name], fixture(f"sratc/{FILES[name]}")) for name in names]


@cache
def parsed(name):
    """A file's rows; read only, shared by the tests."""
    return sratc.parse_file(SOURCES[name], fixture(f"sratc/{FILES[name]}"))


@pytest.fixture(scope="module")
def part():
    return build_dataset(files(), REGISTRY, TODAY, 31, sratc.SOURCE)


@pytest.fixture(scope="module")
def whole_year():
    """The data with every date of 2026 kept."""
    data, _ = build_dataset(files(), REGISTRY, TODAY, 366, sratc.SOURCE)
    return data


def place(data, name, district=None, kind=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and district in (None, loc["district"])
        and kind in (None, loc["type"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def rows(data, ids):
    return sorted(row(data, i)["name"] for i in ids)


def area_of(data, location, kind="household"):
    return row(data, location["schedule"][kind]["area"])


def streets(location):
    return {label: key for key, label in location["streets"]}


# --- the pages ----------------------------------------------------------------


def test_finds_the_file_of_private_houses():
    # Under "Atliekų surinkimo grafikai individualioms valdoms", not the apartment buildings'
    # files of the same text ("Visų rūšių atliekų surinkimas 2026 m."); the page's <base>.
    html = fixture("sratc/siauliu-rajonas.html").decode("utf-8")
    found = sratc.find_files(html, sratc.SIAULIU_R)
    assert found == [
        (
            SourceFile(
                "household",
                "https://www.sratc.lt/uploads/2026%20m-%20individuali%C5%B3%20vald%C5%B3%20"
                "grafikas%20%C5%A0iauli%C5%B3%20rajonas%20260831.pdf",
                "2026 m- individualių valdų grafikas Šiaulių rajonas 260831.pdf",
                "Šiaulių r.",
            ),
            2026,
        )
    ]


def test_an_old_file_still_linked_is_left_out():
    # Akmenės r. still links the 2023 file, by an image without text.
    html = fixture("sratc/akmenes-rajonas.html").decode("utf-8")
    found = sratc.find_files(html, sratc.AKMENES_R)
    assert [(f.file_name, year) for f, year in found] == [
        ("2023 m- individualios valdos.pdf", 2023),
        ("2026 m- individualių valdų grafikas Akmenės r-.pdf", 2026),
    ]
    chosen, warnings = sratc.select_files(found, sratc.AKMENES_R, TODAY)
    assert [f.file_name for f in chosen] == ["2026 m- individualių valdų grafikas Akmenės r-.pdf"]
    assert warnings == []


def test_reads_this_year_and_later():
    def link(name, year):
        return (SourceFile("household", f"https://x/{name}", name, "Kelmės r."), year)

    this, later, again = link("2026.pdf", 2026), link("2027.pdf", 2027), link("2026-b.pdf", 2026)
    chosen, warnings = sratc.select_files([this, later], sratc.KELMES_R, TODAY)
    assert chosen == [this[0], later[0]] and warnings == []
    # A correction linked after the original replaces it.
    chosen, warnings = sratc.select_files([this, again], sratc.KELMES_R, TODAY)
    assert chosen == [again[0]]
    assert warnings == ["Kelmės r.: 2026.pdf: not read, 2026-b.pdf is a newer schedule for 2026"]
    # In January, before the new file is posted: the newest one, with a warning.
    chosen, warnings = sratc.select_files([this], sratc.KELMES_R, date(2027, 1, 5))
    assert chosen == [this[0]]
    assert warnings == ["Kelmės r.: no schedule for 2027 on the page"]


# --- the files ---------------------------------------------------------------------


def test_places_of_each_file():
    counts = {}
    for name in FILES:
        result = parsed(name)
        assert result.warnings == []
        assert all(d.year == 2026 for a in result.areas for d in a.dates)
        counts[name] = dict(Counter(a.kind for a in result.areas))
    assert counts == {
        "Šiaulių r.": {"household": 109, "packaging": 109, "glass": 109, "green": 26},
        "Akmenės r.": {"household": 14, "packaging": 14, "glass": 14},
        "Joniškio r.": {"household": 14, "packaging": 14, "glass": 14, "food": 5},
        "Kelmės r.": {"household": 48, "packaging": 48, "glass": 48, "green": 10},
        "Pakruojo r.": {"household": 49, "packaging": 49, "glass": 49, "green": 15},
    }


def test_a_place_and_its_dates():
    areas = {a.kind: a for a in parsed("Šiaulių r.").areas if a.name == "Drąsučių k."}
    assert areas["household"].district == "Kuršėnų kaimiškoji seniūnija"
    assert sorted(areas["household"].dates) == [date(2026, m, d) for m, d in DRASUCIAI]
    assert len(areas["packaging"].dates) == 12 and len(areas["glass"].dates) == 4
    assert min(areas["green"].dates) == date(2026, 4, 1)


def test_headings_above_and_inside_the_tables():
    headings = {a.district for name in FILES for a in parsed(name).areas}
    # Above the table, upper case in sentence case; in its first row, after a note ("* Mišrių
    # komunalinių atliekų surinkimas I ir III mėnesio Antradienį. Kelmės miestas 2"); none above
    # (the one before).
    assert {
        "Kuršėnų miesto seniūnija",
        "Klovainių sen.",
        "Kelmės miestas 2",
        "Saugėlaukio-Kepalių seniūnijos",
        "Kruopių ir Naujosios Akmenės kaimiškoji/miesto seniūnijos",
        "Žagarė",
    } <= headings
    assert not any(h is None or "grafik" in h.lower() for h in headings)


def test_first_column_on_several_rows():
    names = [a.name for a in parsed("Akmenės r.").areas]
    # "Naujosios Akmenės m." in one cell, its streets in the next, a village further down.
    assert any(
        n.startswith("Naujosios Akmenės m., Algirdo g.") and n.endswith("Ramučių k.") for n in names
    )
    # A first line that describes the list: a colon.
    kursenai = [a.name for a in parsed("Šiaulių r.").areas][0]
    assert kursenai.startswith("Kuršėnų miesto dalis, išskyrus Daugėlius, Pavenčius: Aido g.")


def test_days_as_written():
    assert sratc._days("13, 27", 2026, 1, "x") == {date(2026, 1, 13), date(2026, 1, 27)}
    assert sratc._days("1; 15;29", 2026, 9, "x") == {date(2026, 9, d) for d in (1, 15, 29)}
    # Kelmė's moved days, a stray dot, digits spaced out to fill the cell (Pakruojo r.).
    assert sratc._days("6 (perkelta iš 01\nd.);15", 2026, 1, "x") == {
        date(2026, 1, 6),
        date(2026, 1, 15),
    }
    assert sratc._days("11,.25", 2026, 3, "x") == {date(2026, 3, 11), date(2026, 3, 25)}
    assert sratc._days("1 0 ; 2 5", 2026, 6, "x") == {date(2026, 6, 10), date(2026, 6, 25)}


def test_unreadable_days_fail_loudly():
    with pytest.raises(ValueError, match="not a list of days in month 1: '6, 2O'"):
        sratc._days("6, 2O", 2026, 1, "x")
    with pytest.raises(ValueError, match="31 of month 2"):
        sratc._days("3; 31", 2026, 2, "x")


def test_the_year_in_the_title_and_the_name_must_agree():
    renamed = SourceFile("household", "https://x/2027.pdf", "individualios 2027.pdf", "Kelmės r.")
    with pytest.raises(ValueError, match="the title says 2026, the name 2027"):
        sratc.parse_file(renamed, fixture("sratc/kelmes-r-2026.pdf"))


def test_a_file_of_another_municipality_fails():
    # Joniškio r.'s headings name no eldership of Akmenės r.
    wrong = SourceFile("household", "https://x/j.pdf", "joniskio-r-2026.pdf", "Akmenės r.")
    with pytest.raises(ValueError, match="'Joniškio miestas' isn't an eldership of Akmenės r."):
        sratc.parse_file(wrong, fixture("sratc/joniskio-r-2026.pdf"))
    # Too few places: the format changed.
    with pytest.raises(ValueError, match="only 14 places"):
        sratc.parse_file(
            SourceFile("household", "https://x/a.pdf", "a.pdf", "Kelmės r."),
            fixture("sratc/akmenes-r-2026.pdf"),
        )


def test_elderships_of_headings():
    assert sratc.elderships_of("KURŠĖNŲ MIESTO SENIŪNIJA") == ["Kuršėnų miesto"]
    assert sratc.elderships_of("Kelmės apylinkių seniūnija") == ["Kelmės apylinkių"]
    assert sratc.elderships_of("Kelmės miestas 1") == ["Kelmės"]
    assert sratc.elderships_of("Žagarė") == ["Žagarės"]
    assert sratc.elderships_of("Gaižaičių-Rudiškių-Gataučių seniūnijos") == [
        "Gaižaičių",
        "Rudiškių",
        "Gataučių",
    ]
    assert sratc.elderships_of("Kruopių ir Naujosios Akmenės kaimiškoji/miesto seniūnijos") == [
        "Kruopių",
        "Naujosios Akmenės kaimiškoji",
        "Naujosios Akmenės miesto",
    ]
    assert sratc.elderships_of("Naujosios Akmenės kaimiškoji ir Akmenės seniūnijos") == [
        "Naujosios Akmenės kaimiškoji",
        "Akmenės",
    ]
    assert sratc.elderships_of("Grafikas 2026 m.") == []


# --- matching ------------------------------------------------------------------------


def test_counts(part):
    data, _ = part
    stats = data["matching"]
    assert stats["locations"] == len(REGISTRY.settlements) == 2075
    assert stats["unmatchedRows"] == 0
    assert all(loc["provider"] == "siauliai" for loc in data["locations"])
    with_kind: Counter = Counter()
    for loc in data["locations"]:
        municipality = sratc.municipality_of(loc["district"]).name
        for kind in loc.get("schedule", {}):
            with_kind[(municipality, kind)] += 1
    assert {k: v for k, v in with_kind.items() if k[1] == "household"} == {
        ("Šiaulių r.", "household"): 434,
        ("Akmenės r.", "household"): 124,
        ("Joniškio r.", "household"): 214,
        ("Kelmės r.", "household"): 592,
        ("Pakruojo r.", "household"): 284,
    }
    assert sum(v for k, v in with_kind.items() if k[1] == "green") == 62
    assert sum(v for k, v in with_kind.items() if k[1] == "food") == 9
    sratc.check_municipalities(data)


@pytest.mark.parametrize(
    "name, district, weekday, count, first, last",
    [
        ("Drąsučiai", "Kuršėnų kaimiškoji", None, 26, "2026-01-08", "2026-12-23"),
        ("Žerkščiai", "Ventos", "Pirmadienis", 12, "2026-01-12", "2026-12-14"),
        ("Kepaliai", "Kepalių", "Trečiadienis", 13, "2026-01-07", "2026-12-09"),
        ("Verpena", "Kelmės apylinkių", "Trečiadienis", 24, "2026-01-07", "2026-12-16"),
        ("Guostagalis", "Guostagalio", None, 26, "2026-01-14", "2026-12-30"),
    ],
)
def test_a_village_of_each_municipality(whole_year, name, district, weekday, count, first, last):
    household = area_of(whole_year, place(whole_year, name, district))
    assert household.get("weekday") == weekday
    assert len(household["dates"]) == count
    assert (household["dates"][0], household["dates"][-1]) == (first, last)


def test_drasuciai_every_date(whole_year):
    household = area_of(whole_year, place(whole_year, "Drąsučiai"))
    assert household["dates"] == [date(2026, m, d).isoformat() for m, d in DRASUCIAI]


def test_towns_by_street(part):
    data, _ = part
    kursenai = place(data, "Kuršėnai")
    keys = streets(kursenai)
    household = kursenai["schedule"]["household"]
    assert set(household) == {"streets"}
    # Two places, of the town's streets: before any settlement, in Kuršėnų miesto seniūnija.
    (aido,) = rows(data, household["streets"][keys["Aido g."]])
    assert aido.startswith("Kuršėnų miesto dalis, išskyrus Daugėlius, Pavenčius:")
    (daugeliu,) = rows(data, household["streets"][keys["Daugėlių g."]])
    assert daugeliu.startswith("Kuršėnų miesto dalis Daugėliai, Pavenčiai:")
    # "Ventos g. Nr. 2, 2A, 6, 8, 10" in one place, "Ventos g." in the other: both offered.
    assert len(household["streets"][keys["Ventos g."]]) == 2
    # Streets no place names (apartment buildings, new streets) are left to the app.
    assert keys["J. Ruzgio g."] not in household["streets"]
    # Kelmė: "Kooperacijos g. (2-44, 1-39)" and the like in each of its three places.
    kelme = place(data, "Kelmė")
    assert len(kelme["schedule"]["household"]["streets"][streets(kelme)["Kooperacijos g."]]) == 3


def test_streets_of_a_village(part):
    data, _ = part
    # "Paitaičių k. išskyrus Guobų ir Liepų g." and "Paitaičių k. Guobų ir Liepų g."
    village = place(data, "Paitaičiai")
    household = village["schedule"]["household"]
    assert row(data, household["area"])["name"] == "Paitaičių k. išskyrus Guobų ir Liepų g."
    for street in ("Guobų g.", "Liepų g."):
        assert rows(data, household["streets"][streets(village)[street]]) == [
            "Paitaičių k. Guobų ir Liepų g."
        ]
    # "Uosių g. lyginiai namo numeriai" (even numbers) in one place, odd in another.
    naudvaris = place(data, "Naudvaris")
    uosiu = naudvaris["schedule"]["household"]["streets"][streets(naudvaris)["Uosių g."]]
    assert len(uosiu) == 2
    # "Linksmučių k. (be Užupio g.)" and "Jovarų k., (tik Užupio g., Linksmučių k.)".
    linksmuciai = place(data, "Linksmučiai")
    household = linksmuciai["schedule"]["household"]
    assert row(data, household["area"])["name"].startswith("Mažeikonių k.")
    assert rows(data, household["streets"][streets(linksmuciai)["Užupio g."]])[0].startswith(
        "Pakruojo m. (centras)"
    )


def test_some_houses_of_a_village(part):
    data, _ = part
    # "Ilgviečių k. Nr. 1;5;7;10;11;13" next to "Ilgviečių k.": the app asks.
    candidates = place(data, "Ilgviečiai")["schedule"]["household"]["candidates"]
    assert len(candidates) == 2
    # "Kareiviškio k. (Nr. 3, Nr. 4)" and "(Nr. 1, Nr. 2, Nr. 5, Nr. 6)".
    assert len(place(data, "Kareiviškis")["schedule"]["household"]["candidates"]) == 2


def test_gardens(part):
    data, _ = part
    # A garden community is one more choice in its village's street list.
    noreikiai = place(data, "Noreikiai", "Kužių")
    household = noreikiai["schedule"]["household"]
    garden = streets(noreikiai)["SB „Švendrelis“"]
    assert rows(data, household["streets"][garden]) == ["SB ,,Švendrelis“ (Noreikių k.)"]
    kelme = place(data, "Kelmė")
    assert {"SB „Vingis“", "SB „Kražantė“"} <= set(streets(kelme))
    # SB "Stipirkiai" in the Naujoji Akmenė list is the village Stipirkiai (353 addresses).
    stipirkiai = place(data, "Stipirkiai")
    assert area_of(data, stipirkiai)["name"].startswith("Naujosios Akmenės m., Aukštųjų g.")


def test_villages_under_another_eldership(part):
    data, warnings = part
    # The Žeimelio sen. list names villages of Pašvitinio sen., which no place lists there.
    binenai = place(data, "Binėnai")
    assert binenai["district"] == "Pašvitinio"
    assert area_of(data, binenai)["district"] == "Žeimelio sen."
    # "Rimšonių k." too: Klovainių sen.'s Rimšoniai has a place of its own.
    assert area_of(data, place(data, "Rimšoniai", "Pašvitinio"))["district"] == "Žeimelio sen."
    # "Akmenės ir Ventos seniūnijos: ... Dumbrių k.": Dumbriai of Papilės sen. is listed there.
    assert "not a settlement or a street: household: Akmenės ir Ventos seniūnijos: Dumbrių k." in (
        warnings
    )


def test_towns_and_villages_of_one_name(part):
    data, warnings = part
    assert area_of(data, place(data, "Venta", kind="m."))["name"] == "Ventos m."
    assert area_of(data, place(data, "Venta", kind="k."))["name"].startswith("Ventos k.")
    # "Karklėnų k." is the town Karklėnai mstl., which no place names as a town; "Gruzdžių vs."
    # isn't Gruzdžiai mstl., which has a place of its own.
    assert area_of(data, place(data, "Karklėnai"))["name"].startswith("Albinavos k.")
    assert area_of(data, place(data, "Gruzdžiai"))["name"] == "Gruzdžių mstl."
    assert "not a settlement or a street: household: Gruzdžių seniūnija: Gruzdžių vs." in warnings
    # "Akmenės I ir III k.", "Kinkių k." for Kinkiai I and II.
    assert area_of(data, place(data, "Akmenė III"))["name"].startswith("Ventos k.")
    kinkiai = {area_of(data, place(data, f"Kinkiai {n}"))["id"] for n in ("I", "II")}
    assert len(kinkiai) == 1


def test_parts_of_a_town_named_in_words(part):
    data, _ = part
    # "Pakruojo m. (naujamiestis)" and "Pakruojo m. (centras)": the app asks.
    assert rows(data, place(data, "Pakruojis", kind="m.")["schedule"]["household"]["candidates"])[
        0
    ].startswith("Pakruojo m. (centras)")


def test_names_that_match_nothing_are_reported(part):
    _, warnings = part
    distinct = sorted({w.split(": ", 2)[2] for w in warnings if w.startswith("not ")})
    assert distinct == [
        "Akmenės ir Ventos seniūnijos: Dumbrių k.",
        "Bubių seniūnija: Spitkiškės k.",
        "Ginkūnų seniūnija: Pakrantės g.",
        "Ginkūnų seniūnija: Slėnio g.",
        "Ginkūnų seniūnija: Spindulio g.",
        "Ginkūnų seniūnija: Stukų vs.",
        "Gruzdžių seniūnija: Gruzdžių vs.",
        "Joniškio miestas: Satkūnų k.",
        "Kelmės miestas 1: P. Cvirkos g.",
        "Kelmės miestas 3: S. Nėries g.",
        "Kražių seniūnija: Palėpšių k.",
        "Kukečių seniūnija: Kryžbarko k.",
        "Kukečių seniūnija: Mateikių k.",
        "Kukečių seniūnija: Užburkio k.",
        "Kuršėnų miesto seniūnija: Draugystės g.",
        "Kuršėnų miesto seniūnija: J. Gagarino g.",
        "Kuršėnų miesto seniūnija: V. Montvilos g.",
        "Naujosios Akmenės miesto seniūnija: Sodų g.",
        "Pakražančio seniūnija: Kalniškių k.",
        "Pakražančio seniūnija: Raudgirio k.",
        "Pakražančio seniūnija: Šaukiškės k.",
        "Papilės seniūnija: Padarbių k.",
        "Papilės seniūnija: Šaltiškių k.",
        "Raudėnų seniūnija: Vileišių k.",
        "Raudėnų seniūnija: Šilėnų k.",
        "Saugėlaukio-Kepalių seniūnijos: Podžiūnų k.",
        "Tytuvėnų apylinkių seniūnija: Tytuvėnų geležinkelio stotis",
        "Vaiguvos seniūnija: Pagiriškio k.",
        "Vaiguvos seniūnija: Šiliškių k.",
        "Žagarė: Butlerių g.",
        "Žagarė: Raudondvario g.",
        "Žagarė: Rengių g.",
        "Žeimelio sen.: Dausiškių k.",
    ]


# --- this year and the next ------------------------------------------------------


def year_rows(year, *names, district="Kuršėnų kaimiškoji seniūnija"):
    return ParseResult(
        [
            Area("household", name, district, dates={date(year, 12, 1)}, provider="siauliai")
            for name in names
        ]
    )


def test_next_year_continues_places_of_the_same_villages():
    this_year = year_rows(2026, "Drąsučių k.", "Micaičių k.")
    next_year = year_rows(2027, "Drąsučių kaimas", "Micaičių k., Varputėnų k.")
    source = SOURCES["Šiaulių r."]
    warnings = sratc.combine([(source, this_year), (source, next_year)], REGISTRY, TODAY)
    assert this_year.areas[0].dates == {date(2026, 12, 1), date(2027, 12, 1)}
    assert this_year.areas[1].dates == {date(2026, 12, 1)}
    assert next_year.areas == []
    assert warnings == [
        "Šiaulių r. household: the 2027 place 'Micaičių k., Varputėnų k.' doesn't match one "
        "2026 place; its dates are left out until 2027",
        "Šiaulių r. household: the 2026 place 'Micaičių k.' has no dates for 2027",
    ]


def test_a_municipality_without_next_years_file_keeps_this_years():
    # January: Šiaulių r. has posted 2027, Kelmės r. hasn't.
    siauliai = (SOURCES["Šiaulių r."], year_rows(2027, "Drąsučių k."))
    kelme = (SOURCES["Kelmės r."], year_rows(2026, "Verpenos k.", district="Kelmės miestas 1"))
    january = date(2027, 1, 10)
    assert sratc.combine([siauliai, kelme], REGISTRY, january) == []
    assert len(kelme[1].areas) == 1
    # Both stay the schedules in force: each municipality's files run out on their own.
    assert current_rows([siauliai, kelme], january) == {
        siauliai[1].areas[0].id,
        kelme[1].areas[0].id,
    }


def test_missing_kind_fails():
    with pytest.raises(ValidationError, match="no green schedule|only .* green areas"):
        build_dataset(files(["Akmenės r."]), REGISTRY, TODAY, 31, sratc.SOURCE)


def test_one_municipality_matching_nothing_fails(part):
    data, _ = part
    broken = {
        **data,
        "locations": [loc for loc in data["locations"] if loc["district"] != "Kepalių"]
        + [
            {k: v for k, v in loc.items() if k != "schedule"}
            for loc in data["locations"]
            if loc["district"] == "Kepalių"
        ],
    }
    sratc.check_municipalities(broken)  # one eldership less is still enough
    joniskis = sratc.JONISKIO_R.elderships
    broken["locations"] = [loc for loc in data["locations"] if loc["district"] not in joniskis]
    with pytest.raises(ValidationError, match="Joniškio r.: only 0 settlements"):
        sratc.check_municipalities(broken)


# --- the published file ------------------------------------------------------------


def test_published_file_and_its_metrics(part, tmp_path):
    data, warnings = part
    data = {**data, "warnings": len(warnings)}
    dataset = merge_parts([(sratc.PROVIDER, data)], sratc.PAGE_URL)
    assert dataset["source"] == sratc.PAGE_URL
    assert [p["id"] for p in dataset["providers"]] == ["siauliai"]
    assert all(a["provider"] == "siauliai" for a in dataset["areas"])
    assert dataset["coverage"]["household"]["to"] == "2026-12-31"
    assert {f["name"] for f in dataset["files"]} == set(FILES.values())

    (tmp_path / "sratc").mkdir()
    (tmp_path / "sratc" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_areas{source="siauliai",kind="food"} 5' in text
    places = sum(1 for loc in dataset["locations"] if loc.get("schedule"))
    assert f'siuksliaveze_data_places{{source="siauliai"}} {places}' in text
    last = int((date(2026, 12, 31) - date(1970, 1, 1)) / timedelta(seconds=1))
    assert (
        f'siuksliaveze_data_last_date_timestamp_seconds{{source="siauliai",kind="household"}} '
        f"{last}" in text
    )


# --- Radviliškio r. ------------------------------------------------------------------

RADVILISKIO_REGISTRY = Registry.load(FIXTURES / "sratc" / "registry-radviliskio-r-2026-11-21.json")
MIXED = SourceFile(
    "household",
    "https://www.sratc.lt/uploads/2026%20m%20indiv-%20vald%C5%B3%20MKA%20ir%20BSA%20"
    "surinkimas_sv.pdf",
    "2026 m indiv- valdų MKA ir BSA surinkimas_sv.pdf",
    "Radviliškio r.",
)
PACKAGING = SourceFile(
    "packaging",
    "https://www.sratc.lt/uploads/2026%20m%20grafikai/2026%20m%20radviliskio%20indiv-%20valdu"
    "%20POP%20ir%20stiklo%20surinkimas.pdf",
    "2026 m radviliskio indiv- valdu POP ir stiklo surinkimas.pdf",
    "Radviliškio r.",
)
RADVILISKIO_FILES = {
    MIXED.url: "radviliskio-r-mka-2026-q4.pdf",
    PACKAGING.url: "radviliskio-r-pop-2026.pdf",
}
# Aukštelkai's mixed waste in the October-December 2026 file: every other Friday, Christmas Day
# too.
AUKSTELKAI = ["2026-10-02", "2026-10-16", "2026-10-30", "2026-11-13", "2026-11-27"]
AUKSTELKAI += ["2026-12-11", "2026-12-25"]


def radviliskio_files():
    return [(f, fixture(f"sratc/{RADVILISKIO_FILES[f.url]}")) for f in (MIXED, PACKAGING)]


@cache
def radviliskio_parsed(kind):
    """A file's rows; read only, shared by the tests."""
    source = MIXED if kind == "household" else PACKAGING
    return sratc.parse_radviliskio_file(source, fixture(f"sratc/{RADVILISKIO_FILES[source.url]}"))


@pytest.fixture(scope="module")
def radviliskis():
    return build_dataset(
        radviliskio_files(), RADVILISKIO_REGISTRY, TODAY, 31, sratc.RADVILISKIO_SOURCE
    )


@pytest.fixture(scope="module")
def radviliskis_year():
    data, _ = build_dataset(
        radviliskio_files(), RADVILISKIO_REGISTRY, TODAY, 366, sratc.RADVILISKIO_SOURCE
    )
    return data


def street_rows(data, location, kind, label):
    """The rows of a street of a settlement; None if it's left to the app."""
    key = streets(location).get(label)
    return location["schedule"][kind]["streets"].get(key)


def test_radviliskio_files_on_its_page():
    # By the link's text, or the name of a file linked by an image ("2024 m indiv- AŽ.pdf",
    # packaging of 2024); bulky waste isn't read, nor are the apartment buildings' files.
    html = fixture("sratc/radviliskio-rajonas.html").decode("utf-8")
    found, warnings = sratc.find_radviliskio_files(html)
    assert [(f.kind, f.file_name, year) for f, year in found] == [
        ("household", MIXED.file_name, 2026),
        ("packaging", "2024 m indiv- AŽ.pdf", 2024),
        ("packaging", PACKAGING.file_name, 2026),
    ]
    assert warnings == []
    assert [f for f, _ in found if f.kind == "household"] == [MIXED]
    chosen, warnings = sratc.select_radviliskio_files(found, TODAY)
    assert chosen == [MIXED, PACKAGING] and warnings == []


def test_radviliskio_reads_every_quarter_of_this_year_and_later():
    def link(name, year, kind="household"):
        return (SourceFile(kind, f"https://x/{name}", name, "Radviliškio r."), year)

    q4, q1, q2 = link("2026 q4.pdf", 2026), link("2027 q1.pdf", 2027), link("2027 q2.pdf", 2027)
    packaging = link("2026 POP.pdf", 2026, "packaging")
    # December: the next quarter's file is read as soon as it's linked, next to this one.
    chosen, warnings = sratc.select_radviliskio_files([q4, q1, packaging], TODAY)
    assert chosen == [q4[0], q1[0], packaging[0]] and warnings == []
    # Two quarters of one year: both (each has its own months).
    chosen, _ = sratc.select_radviliskio_files([q1, q2, packaging], date(2027, 3, 25))
    assert chosen[:2] == [q1[0], q2[0]]
    # January, before the next quarter's file: the last one, with a warning.
    chosen, warnings = sratc.select_radviliskio_files([q4, packaging], date(2027, 1, 5))
    assert chosen == [q4[0], packaging[0]]
    assert warnings == [
        "Radviliškio r.: no mixed waste schedule for 2027 on the page",
        "Radviliškio r.: no packaging schedule for 2027 on the page",
    ]
    with pytest.raises(ValueError, match="no mixed waste schedule of private houses"):
        sratc.select_radviliskio_files([packaging], TODAY)


def test_radviliskio_mixed_waste_of_a_quarter():
    result = radviliskio_parsed("household")
    assert result.warnings == []
    assert Counter(a.kind for a in result.areas) == {"household": 21, "green": 9}
    dates = sorted(d for a in result.areas for d in a.dates)
    assert (dates[0], dates[-1]) == (date(2026, 10, 1), date(2026, 12, 31))
    assert {a.district for a in result.areas} == {"Radviliškio r."}
    (aukstelkai,) = [a for a in result.areas if a.kind == "household" and "Aukštelkų k." in a.name]
    assert [d.isoformat() for d in sorted(aukstelkai.dates)] == AUKSTELKAI
    assert aukstelkai.weekday == "Penktadienis"
    # The town's green waste, with its own weekday: none in December.
    green = [a for a in result.areas if a.kind == "green"]
    assert all(a.name.startswith("Radviliškio miesto sen.: Radviliškio m.") for a in green)
    assert max(d for a in green for d in a.dates) == date(2026, 11, 30)


def test_radviliskio_packaging_and_glass_of_a_year():
    result = radviliskio_parsed("packaging")
    assert Counter(a.kind for a in result.areas) == {"packaging": 15, "glass": 15}
    # Each place's list starts with its town or eldership, inside the table.
    names = [a.name for a in result.areas if a.kind == "packaging"]
    assert names[0].startswith("Radviliškio miestas (Individualios valdos) : Aušros a.")
    assert any(n.startswith("Šeduvos miestas: Baukų g.") for n in names)
    (aukstelkai,) = [
        a for a in result.areas if a.kind == "glass" and a.name.startswith("Aukštelkų sen.: Aukš")
    ]
    assert [d.isoformat()[5:] for d in sorted(aukstelkai.dates)] == [
        "01-21",
        "04-15",
        "07-08",
        "09-30",
        "12-23",
    ]


def test_radviliskio_files_are_read_strictly(monkeypatch):
    content = fixture("sratc/radviliskio-r-mka-2026-q4.pdf")
    # A quarter isn't a year.
    with pytest.raises(ValueError, match="a table starting with month 10"):
        sratc.parse_blocks(MIXED, content)
    # The year in the name must be the title's.
    renamed = replace(MIXED, file_name="2027 m indiv- valdų MKA.pdf")
    with pytest.raises(ValueError, match="the title says 2026, the name 2027"):
        sratc.parse_radviliskio_file(renamed, content)
    # The packaging file as the mixed waste one: no mixed waste in it.
    swapped = replace(PACKAGING, kind="household")
    with pytest.raises(ValueError, match="no household dates"):
        sratc.parse_radviliskio_file(swapped, fixture("sratc/radviliskio-r-pop-2026.pdf"))
    # Dates of another year miss the weekdays the titles name.
    monkeypatch.setattr(sratc, "_year", lambda pdf, source: 2025)
    with pytest.raises(ValueError, match="aren't on Pirmadienis as titled"):
        sratc.parse_radviliskio_file(MIXED, content)


def test_radviliskio_counts(radviliskis):
    data, warnings = radviliskis
    stats = data["matching"]
    assert stats["locations"] == len(RADVILISKIO_REGISTRY.settlements) == 407
    assert stats["unmatchedRows"] == 0
    assert all(loc["provider"] == "radviliskis" for loc in data["locations"])
    with_kind = Counter(kind for loc in data["locations"] for kind in loc.get("schedule", {}))
    assert with_kind == {"household": 295, "packaging": 349, "glass": 349, "green": 2}
    # Nobody is asked to choose between places: one each, or one per street.
    assert not any(k.endswith(".ambiguous") and v for k, v in stats.items())
    assert sorted({w.split(": ", 2)[2] for w in warnings}) == [
        "Pakalniškių sen.: Miškadvario k.",
        "Radviliškio sen.: Jasnagurkos k.",
        "Sidabravo sen.: Jasnagurkos vs.",
        "Sidabravo sen.: Palabės k.",
        "Šeduvos miesto sen.: Saulėtekio g.",
        "Šeduvos miesto sen.: Sausio 13-osios g.",
    ]


def test_radviliskio_a_village_and_its_dates(radviliskis_year):
    aukstelkai = place(radviliskis_year, "Aukštelkai")
    household = area_of(radviliskis_year, aukstelkai)
    assert household["dates"] == AUKSTELKAI
    assert household["name"].startswith("Aukštelkų sen.: Aukštelkų k., Birjočių k.")
    packaging = area_of(radviliskis_year, aukstelkai, "packaging")
    assert len(packaging["dates"]) == 13 and packaging["dates"][0] == "2026-01-02"


def test_radviliskio_town_streets(radviliskis):
    data, _ = radviliskis
    town = place(data, "Radviliškis", kind="m.")
    assert {kind: set(r) for kind, r in town["schedule"].items()} == {
        kind: {"streets"} for kind in ("household", "packaging", "glass", "green")
    }
    alyvu = street_rows(data, town, "household", "Alyvų g.")
    assert rows(data, alyvu)[0].startswith("Radviliškio miesto sen.: Radviliškio m. - Alyvų g.")
    # "Laisvės al. (iki 15; iki 32)" in one place, "(nuo 17; nuo 34)" in another: those two.
    laisves = rows(data, street_rows(data, town, "household", "Laisvės al."))
    assert len(laisves) == 2 and "Aušros a., Laisvės al. (nuo 17; nuo 34)" in laisves[1]
    assert len(street_rows(data, town, "packaging", "Dariaus ir Girėno g.")) == 2
    # Streets of private houses no place names (Paplentės 1-oji g., 110 addresses) aren't "no
    # pickup": they're left to the app, which offers the town's places.
    assert street_rows(data, town, "household", "Paplentės 1-oji g.") is None
    assert all(town["schedule"]["household"]["streets"].values())
    # Šeduva: one place for mixed waste, two by street for packaging.
    seduva = place(data, "Šeduva", kind="m.")
    assert set(seduva["schedule"]["household"]) == {"area"}
    assert street_rows(data, seduva, "packaging", "Baukų g.")
    assert street_rows(data, seduva, "packaging", "Užuovėjos g.") is None
    # Baisogala: all of it in one place.
    assert set(place(data, "Baisogala")["schedule"]["household"]) == {"area"}


def test_radviliskio_streets_of_a_village(radviliskis):
    data, _ = radviliskis
    # "Linkaičių k. - Kaštonų g., Miško g., Pervažos g." and "Linkaičių k. - Arsenalo g., ...".
    linkaiciai = place(data, "Linkaičiai")
    kastonu = street_rows(data, linkaiciai, "household", "Kaštonų g.")
    arsenalo = street_rows(data, linkaiciai, "household", "Arsenalo g.")
    assert len(kastonu) == len(arsenalo) == 1 and kastonu != arsenalo
    assert street_rows(data, linkaiciai, "household", "Sodų g.") is None
    # Karčemos, next to "Linkaičių glž. st." in a packaging list: all of it.
    assert set(place(data, "Karčemos")["schedule"]["packaging"]) == {"area"}


def test_radviliskio_unclosed_bracket():
    assert sratc._close_brackets("M. Mažvydo g.(nuo 1 iki 49, Miško a., Miško g.") == (
        "M. Mažvydo g.(nuo 1 iki 49), Miško a., Miško g."
    )
    text = "Laisvės al. (iki 15; iki 32) Ligoninės g., M. Mažvydo g. (iki 49), M. Valančiaus g."
    assert sratc._close_brackets(text) == text


def quarter(start, *names):
    """Mixed waste rows of a file of three months from `start`."""
    return ParseResult(
        [
            Area("household", name, "Radviliškio r.", dates={start, start + timedelta(days=80)})
            for name in names
        ]
    )


NEXT_QUARTER = replace(MIXED, url="https://x/2027.pdf", file_name="2027.pdf")


def test_radviliskio_next_quarter_continues_places_of_the_same_villages():
    q4 = quarter(
        date(2026, 10, 7),
        "Aukštelkų sen.: Aukštelkų k., Birjočių k.",
        "Aukštelkų sen.: Kaulinių k.",
    )
    q1 = quarter(
        date(2027, 1, 6),
        "Aukštelkų sen.: Birjočių k., Aukštelkų kaimas",
        "Aukštelkų sen.: Kaulinių k., Rupliškio vs.",
    )
    warnings = sratc.combine_radviliskio(
        [(MIXED, q4), (NEXT_QUARTER, q1)], RADVILISKIO_REGISTRY, date(2026, 12, 20)
    )
    assert q4.areas[0].dates == {
        date(2026, 10, 7),
        date(2026, 12, 26),
        date(2027, 1, 6),
        date(2027, 3, 27),
    }
    assert q1.areas == [] and len(q4.areas) == 2
    assert warnings == [
        "Radviliškio r. household: the 2027-01-01 place 'Aukštelkų sen.: Kaulinių k., Rupliškio "
        "vs.' doesn't match one 2026-10-01 place; its dates are left out until 2027-01-01",
        "Radviliškio r. household: the 2026-10-01 place 'Aukštelkų sen.: Kaulinių k.' has no "
        "dates for 2027-01-01",
    ]


def test_radviliskio_the_quarter_in_force():
    q4 = quarter(date(2026, 10, 7), "Aukštelkų sen.: Kaulinių k.")
    q1 = quarter(date(2027, 1, 6), "Aukštelkų sen.: Kaulinių k., Rupliškio vs.")
    # Once the next quarter has started, its places are the schedule; the last ones are dropped.
    files = [(MIXED, q4), (NEXT_QUARTER, q1)]
    assert sratc.combine_radviliskio(files, RADVILISKIO_REGISTRY, date(2027, 1, 2)) == []
    assert q4.areas == [] and len(q1.areas) == 1
    # A quarter that has ended without a successor keeps its places, with their last dates.
    q4 = quarter(date(2026, 10, 7), "Aukštelkų sen.: Kaulinių k.")
    january = date(2027, 1, 5)
    assert sratc.combine_radviliskio([(MIXED, q4)], RADVILISKIO_REGISTRY, january) == [
        "Radviliškio r.: the mixed waste schedule ended on 2026-12-31; no newer one is read"
    ]
    assert current_rows([(MIXED, q4)], january) == {q4.areas[0].id}
    # The last quarter's file replaced by the next before it starts: its last dates are lost.
    q1 = quarter(date(2027, 1, 6), "Aukštelkų sen.: Kaulinių k.")
    assert sratc.combine_radviliskio([(NEXT_QUARTER, q1)], RADVILISKIO_REGISTRY, TODAY) == [
        "Radviliškio r.: no mixed waste schedule for today; the next starts on 2027-01-01"
    ]


def test_radviliskio_files_of_the_same_months():
    first = quarter(date(2026, 10, 7), "Aukštelkų sen.: Kaulinių k.")
    again = quarter(date(2026, 10, 7), "Aukštelkų sen.: Kaulinių k., Sedūnų k.")
    fixed = replace(MIXED, url="https://x/fixed.pdf", file_name="fixed.pdf")
    warnings = sratc.combine_radviliskio(
        [(MIXED, first), (fixed, again)], RADVILISKIO_REGISTRY, TODAY
    )
    # A correction linked after the original replaces it.
    assert warnings == [
        f"Radviliškio r.: {MIXED.file_name}: not read, fixed.pdf is a newer schedule for "
        "2026-10-01 - 2026-12-31"
    ]
    assert first.areas == [] and len(again.areas) == 1
    # Months that overlap otherwise: not something we can read.
    overlapping = quarter(date(2026, 11, 4), "Aukštelkų sen.: Kaulinių k.")
    with pytest.raises(ValueError, match="overlap"):
        sratc.combine_radviliskio(
            [(MIXED, quarter(date(2026, 10, 7), "x")), (fixed, overlapping)],
            RADVILISKIO_REGISTRY,
            TODAY,
        )


def test_radviliskio_is_a_part_of_its_own(part, radviliskis, tmp_path):
    five, five_warnings = part
    data, warnings = radviliskis
    built = [
        (sratc.PROVIDER, {**five, "warnings": len(five_warnings)}),
        (sratc.RADVILISKIO, {**data, "warnings": len(warnings)}),
    ]
    dataset = merge_parts(built, sratc.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == ["siauliai", "radviliskis"]
    assert dataset["providers"][1]["url"] == "https://www.sratc.lt/grafikai-radviliskio-rajonas/"
    # The five's part is as it is published on its own.
    alone = merge_parts(built[:1], sratc.PAGE_URL)
    assert published_part(dataset, sratc.PROVIDER) == published_part(alone, sratc.PROVIDER)
    (tmp_path / "sratc").mkdir()
    (tmp_path / "sratc" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    places = sum(1 for loc in data["locations"] if loc.get("schedule"))
    assert f'siuksliaveze_data_places{{source="radviliskis"}} {places}' in text
    assert 'siuksliaveze_data_areas{source="radviliskis",kind="green"} 9' in text
    last = int((date(2026, 12, 31) - date(1970, 1, 1)) / timedelta(seconds=1))
    assert (
        f'siuksliaveze_data_last_date_timestamp_seconds{{source="radviliskis",kind="household"}} '
        f"{last}" in text
    )


class _Today(date):
    @classmethod
    def today(cls):
        return TODAY


def test_a_part_whose_build_fails_keeps_its_published_part(
    monkeypatch, part, radviliskis, tmp_path
):
    five, _ = part
    data, _ = radviliskis
    yesterday = merge_parts(
        [
            (sratc.PROVIDER, {**five, "generatedAt": "2026-11-20T04:30:00+00:00"}),
            (sratc.RADVILISKIO, {**data, "generatedAt": "2026-11-20T04:31:00+00:00"}),
        ],
        sratc.PAGE_URL,
    )

    def new_layout(today, keep_days):
        raise ValueError("a table starting with month 1")

    monkeypatch.setattr(sratc, "date", _Today)
    monkeypatch.setattr(sratc, "SOURCE", replace(sratc.SOURCE, download=lambda t, k: (files(), [])))
    monkeypatch.setattr(
        sratc, "RADVILISKIO_SOURCE", replace(sratc.RADVILISKIO_SOURCE, download=new_layout)
    )
    monkeypatch.setattr(sratc, "fetch_registries", lambda: (REGISTRY, RADVILISKIO_REGISTRY))
    monkeypatch.setattr(sratc, "fetch_points", lambda *municipalities: [])
    monkeypatch.setattr(sratc, "MIN_ADDRESS_POINTS", 0)
    monkeypatch.setattr(sratc, "RADVILISKIO_MIN_ADDRESS_POINTS", 0)
    monkeypatch.setattr(build, "load_published", lambda url: lambda: yesterday)
    assert sratc.main(["--out", str(tmp_path)]) == 0
    written = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in written["providers"]] == ["siauliai", "radviliskis"]
    assert written["providers"][0]["generatedAt"] != "2026-11-20T04:30:00+00:00"
    assert written["providers"][1]["generatedAt"] == "2026-11-20T04:31:00+00:00"
    assert published_part(written, sratc.RADVILISKIO)["areas"] == data["areas"]
    # --strict (the live check on pull requests) fails instead.
    assert sratc.main(["--out", str(tmp_path), "--strict"]) == 1

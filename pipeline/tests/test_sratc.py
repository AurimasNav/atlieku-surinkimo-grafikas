"""Šiaulių RATC: the municipalities' pages, the five yearly PDFs, their places and next year."""

import json
from collections import Counter
from datetime import date, timedelta
from functools import cache

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import sratc, status
from schedule_pipeline.build import ValidationError, build_dataset, current_rows, merge_parts
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

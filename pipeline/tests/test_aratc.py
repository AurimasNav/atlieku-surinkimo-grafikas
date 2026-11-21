"""Alytaus RATC: the page, the PDFs of six municipalities, their routes and the next contract
year."""

import json
from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import aratc, status, svara
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.locations import Index
from schedule_pipeline.model import Area, ParseResult
from schedule_pipeline.registry import Registry

REGISTRY = aratc.town_elderships(
    Registry.load(FIXTURES / "aratc" / "registry-alytaus-ratc-2026-11-21.json")
)
TODAY = date(2026, 11, 21)
UPLOADS = "https://www.aratc.lt/uploads/Grafikai/"
# The files of the page, as they are linked, and their copies in fixtures/aratc.
COPIES = {
    "Alytaus r 2026-2027 MA MKA gyventojai.pdf": "alytaus-r-mka.pdf",
    "Alytaus r 2026-2028 PA STKL individualūs.pdf": "alytaus-r-pa.pdf",
    "Prienu r MA MKA 2026-2027 gyventojai.pdf": "prienu-r-mka.pdf",
    "Prienu r 2026 12-2028 03  PA STKL individualus.pdf": "prienu-r-pa.pdf",
    "Lazdiju r 2026-2027 MKA individualūs.pdf": "lazdiju-mka.pdf",
    "Lazdiju r 2026-2027 MA individualus 2026-06-30.pdf": "lazdiju-ma.pdf",
    "Lazdiju r 2026 08 - 2027 02 PA STKL individualus namai.pdf": "lazdiju-pa.pdf",
    "Varenos r 2026-2027 MKA individualūs.pdf": "varenos-mka.pdf",
    "Varėnos rajono savivaldybės maisto atliekų konteinerių aptarnavimo grafikas 2026 - 2027 "
    "metams.pdf": "varenos-ma.pdf",
    "Varenos r 2026-2027 PA STKL individualūs.pdf": "varenos-pa.pdf",
    "Druskininku sav 2026 04-2027 - 02 MA MKA gyventojai individualus.pdf": "druskininku-mka.pdf",
    "SODŲ, VIENKIEMIŲ IR SUNKIAI PRIVAŽIUOJAMŲ INDIVIDUALIŲ VALDŲ MIŠRIŲ KOMUNALINIŲ ATLIEKŲ "
    "SURINKIMO DRUSKININKŲ SAVIVALDYBĖS TERITORIJOJE GRAFIKAS 2026 - 2027 M.pdf": (
        "druskininku-sodai.pdf"
    ),
    "Druskininku sav PA STKL 2026-2027 Individualus namai 2026.06.30.pdf": "druskininku-pa.pdf",
    "Birstono sav 2026-2027 MA MKA gyventojai.pdf": "birstono-mka.pdf",
    "Birstono sav 2026-2027 PA STKL gyventojai.pdf": "birstono-pa.pdf",
}


def page_files():
    return aratc.find_files(fixture("aratc/page.html").decode("utf-8"))


def files(today=TODAY):
    chosen, _ = aratc.select_files(page_files(), today)
    return [(f, fixture(f"aratc/{COPIES[f.file_name]}")) for f in chosen]


def parsed(copy, **source):
    file = aratc.ScheduleFile("household", f"{UPLOADS}{copy}", copy, **source)
    return aratc.parse_file(file, fixture(f"aratc/{copy}")).areas


@pytest.fixture(scope="module")
def part():
    return build_dataset(files(), REGISTRY, TODAY, 31, aratc.SOURCE)


@pytest.fixture(scope="module")
def whole_year():
    """The data with every date of the contract year kept."""
    data, _ = build_dataset(files(), REGISTRY, TODAY, 366, aratc.SOURCE)
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


def area_of(data, location, kind):
    return row(data, location["schedule"][kind]["area"])


def by_street(data, location, kind):
    """{street label: [row names]} of a place's schedule of a kind."""
    labels = dict(location["streets"])
    return {
        labels[key]: sorted(row(data, i)["name"] for i in ids)
        for key, ids in location["schedule"][kind]["streets"].items()
    }


# --- the page ----------------------------------------------------------------


def test_finds_the_files_of_individual_houses():
    found = page_files()
    names = {f.file_name for f in found}
    # The two packaging files that end on 30 November are linked too.
    assert names == set(COPIES) | {
        "Alytaus r 2026-2027 PA STKL.pdf",
        "Prienu r 2026-2027 PA STKL gyventojai.pdf",
    }
    # Not those of shared containers, companies, public places, garden communities, nor
    # Alytus city.
    assert not any("bendro" in n or "mon" in n or "Alytaus m" in n for n in names)
    by_name = {f.file_name: f for f in found}
    # The links are relative to the page's <base>, with the letters percent-encoded.
    alytaus = by_name["Alytaus r 2026-2028 PA STKL individualūs.pdf"]
    assert alytaus.url == UPLOADS + "Alytaus%20r%202026-2028%20PA%20STKL%20individual%C5%ABs.pdf"
    assert (alytaus.municipality, alytaus.kind, alytaus.valid_from) == (
        "Alytaus r.",
        "packaging",
        date(2026, 12, 1),
    )
    old = by_name["Prienu r 2026-2027 PA STKL gyventojai.pdf"]
    assert (old.municipality, old.valid_until) == ("Prienų r.", date(2026, 11, 30))
    remote = next(f for f in found if f.file_name.startswith("SODŲ"))
    assert (remote.municipality, remote.kind, remote.group) == (
        "Druskininkų sav.",
        "household",
        aratc.REMOTE_GROUP,
    )
    lazdiju = {f.kind for f in found if f.municipality == "Lazdijų r."}
    assert lazdiju == {"household", "food", "packaging"}


def test_files_a_newer_one_replaces_are_left_out():
    chosen, warnings = aratc.select_files(page_files(), TODAY)
    assert {f.file_name for f in chosen} == set(COPIES)
    assert warnings == [
        "Alytaus r 2026-2027 PA STKL.pdf: not read, Alytaus r 2026-2028 PA STKL individualūs.pdf "
        "replaces it after 2026-11-30",
        "Prienu r 2026-2027 PA STKL gyventojai.pdf: not read, Prienu r 2026 12-2028 03  PA STKL "
        "individualus.pdf replaces it after 2026-11-30",
    ]
    chosen, warnings = aratc.select_files(page_files(), date(2026, 12, 1))
    assert {f.file_name for f in chosen} == set(COPIES)
    assert warnings[0] == "Alytaus r 2026-2027 PA STKL.pdf: not read, it ended on 2026-11-30"


def test_each_municipality_needs_its_files():
    without = [f for f in page_files() if f.municipality != "Varėnos r." or f.kind != "household"]
    with pytest.raises(ValidationError, match="no schedule found on the page for Varėnos r. hou"):
        aratc.select_files(without, TODAY)


# --- the tables ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("copy", "counts", "first", "last"),
    [
        ("alytaus-r-mka.pdf", {"household": 16, "food": 3}, "2026-03-02", "2027-02-26"),
        ("alytaus-r-pa.pdf", {"packaging": 15, "glass": 15}, "2026-12-01", "2028-03-31"),
        ("prienu-r-mka.pdf", {"household": 14, "food": 2}, "2026-03-01", "2027-02-27"),
        ("prienu-r-pa.pdf", {"packaging": 14, "glass": 14}, "2026-12-01", "2028-03-31"),
        ("lazdiju-mka.pdf", {"household": 17}, "2026-03-02", "2027-02-25"),
        ("lazdiju-ma.pdf", {"food": 3}, "2026-03-02", "2027-02-08"),
        ("lazdiju-pa.pdf", {"packaging": 12, "glass": 12}, "2026-08-01", "2027-02-28"),
        ("varenos-mka.pdf", {"household": 19}, "2026-03-02", "2027-02-26"),
        ("varenos-ma.pdf", {"food": 2}, "2026-03-03", "2027-02-09"),
        ("varenos-pa.pdf", {"packaging": 12, "glass": 12}, "2026-03-03", "2027-02-26"),
        ("druskininku-mka.pdf", {"household": 8, "food": 4}, "2026-03-02", "2027-02-23"),
        ("druskininku-sodai.pdf", {"household": 1}, "2026-04-11", "2027-02-13"),
        ("druskininku-pa.pdf", {"packaging": 6, "glass": 6}, "2026-07-02", "2027-02-27"),
        ("birstono-mka.pdf", {"household": 1, "food": 1}, "2026-03-10", "2027-02-17"),
        ("birstono-pa.pdf", {"packaging": 1, "glass": 1}, "2026-03-10", "2027-02-09"),
    ],
)
def test_reads_every_file(copy, counts, first, last):
    areas = parsed(copy)
    found: dict[str, int] = {}
    for area in areas:
        found[area.kind] = found.get(area.kind, 0) + 1
    assert found == counts
    dates = [d for a in areas for d in a.dates]
    assert (min(dates).isoformat(), max(dates).isoformat()) == (first, last)


def test_mixed_waste_once_a_month():
    first = parsed("alytaus-r-mka.pdf")[0]
    assert first.name.startswith("SIMNO SEN. Simnas, Kaimynai. KROKIALAUKIO SEN. Dapkiškės,")
    assert sorted(first.dates) == [
        date(2026, 3, 2),
        date(2026, 4, 8),
        date(2026, 5, 4),
        date(2026, 6, 1),
        date(2026, 7, 6),
        date(2026, 8, 3),
        date(2026, 9, 7),
        date(2026, 10, 5),
        date(2026, 11, 2),
        date(2026, 12, 7),
        date(2027, 1, 4),
        date(2027, 2, 1),
    ]


def test_a_cell_of_dates_for_several_rows_of_places():
    # Prienų r.: one cell of dates for the rows of three elderships, each with its "Seniūnija".
    first = parsed("prienu-r-mka.pdf")[0]
    assert first.name == (
        "Visoje N. Ūtos sen. Dalyje Šilavoto sen.: Jasenava, Jiestrakis, Kuišiai, Meškinė, "
        "Mieleiškampis, Paskrynupys, Pašlavantys, Skrynupis, Naujasis Skrynupis, Stuomenai, "
        "Varnakė Dalyje Balbieriškio sen.: Vartai, Kunigiškiai (Kunigiškių g. nuo 1 iki 36)"
    )
    assert min(first.dates) == date(2026, 3, 17) and len(first.dates) == 12


def test_a_row_of_dates_without_its_borders():
    # Lazdijų r., page 2: the packaging cells of the first row have no borders (pdfplumber's
    # table finder leaves them empty).
    areas = parsed("lazdiju-pa.pdf")
    route = [a for a in areas if a.name.startswith("Lazdijų miesto sen.: Lazdijų m. - Ateities")]
    dates = {a.kind: sorted(d.isoformat() for d in a.dates) for a in route}
    assert dates == {
        "packaging": [
            "2026-08-12",
            "2026-09-11",
            "2026-10-12",
            "2026-11-18",
            "2026-12-11",
            "2027-01-13",
            "2027-02-15",
        ],
        "glass": ["2026-10-19", "2027-01-26"],
    }


def test_months_written_bottom_to_top():
    # Varėnos r. packaging: the months' titles are rotated, and August is "Rupjūtis".
    first = parsed("varenos-pa.pdf")[0]
    assert first.kind == "packaging"
    assert first.name.startswith("Varėnos m., Senosios Varėnos k. tik Antakalnio g.,")
    assert date(2026, 8, 4) in first.dates and len(first.dates) == 12


def test_waste_types_in_letters_set_apart():
    # Prienų r.: "S T I K L A S" in the column of waste types.
    areas = parsed("prienu-r-pa.pdf")
    assert sum(a.kind == "glass" for a in areas) == 14


def test_the_whole_municipality():
    # Birštonas: one row, "Individualūs konteineriai".
    areas = parsed("birstono-mka.pdf", municipality="Birštono sav.")
    assert {(a.kind, a.name, a.district) for a in areas} == {
        ("household", "Visa savivaldybė", "Birštono sav."),
        ("food", "Visa savivaldybė", "Birštono sav."),
    }


def test_validity_on_the_page_limits_the_dates():
    areas = parsed("lazdiju-pa.pdf", valid_until=date(2026, 9, 30))
    assert max(d for a in areas for d in a.dates) == date(2026, 9, 27)
    areas = parsed("lazdiju-pa.pdf", valid_from=date(2026, 12, 1))
    assert min(d for a in areas for d in a.dates) == date(2026, 12, 1)


def record(places="Simno sen.: Simnas", dates=(), other=()):
    return aratc._Record([places], list(dates), list(other))


def test_strict():
    source = aratc.ScheduleFile("household", f"{UPLOADS}x.pdf", "x.pdf", "Alytaus r.")
    february = date(2027, 2, 1)
    with pytest.raises(ValueError, match="day 30 of 2027-02"):
        aratc.schedules(source, [(record(dates=[("household", [(february, 30)])]), "x")])
    with pytest.raises(ValueError, match="not days: '2O'"):
        aratc.schedules(
            source, [(record(dates=[("household", [(february, 3)])], other=["2O"]), "x")]
        )
    with pytest.raises(ValueError, match="places without dates"):
        aratc.schedules(source, [(record(), "x")])
    with pytest.raises(ValueError, match="dates of no waste type"):
        aratc.schedules(source, [(record(dates=[(None, [(february, 3)])]), "x")])
    with pytest.raises(ValueError, match="dates without places"):
        aratc.schedules(source, [(record("", dates=[("household", [(february, 3)])]), "x")])
    # Notices in the table are skipped: "DĖL ATLIEKŲ IŠVEŽIMO ... KREIPTIS ... 0 315 72842".
    notice = record("DĖL ATLIEKŲ IŠVEŽIMO KREIPTIS", other=["tel.", "0", "315"])
    result = aratc.schedules(
        source, [(notice, "x"), (record(dates=[("household", [(february, 3)])]), "x")]
    )
    assert [(a.kind, a.district, sorted(a.dates)) for a in result.areas] == [
        ("household", "Alytaus r.", [date(2027, 2, 3)])
    ]


def test_months_out_of_order_fail():
    names = "Kovas Balandis Gegužė Liepa Birželis Rugpjūtis Rugsėjis".split()
    words = [
        {"text": name, "x0": 100.0 + 40 * i, "x1": 120.0 + 40 * i, "top": 10.0, "bottom": 18.0}
        for i, name in enumerate(names)
    ]
    with pytest.raises(ValueError, match="months out of order"):
        aratc._rows_of_months(words, "x")


# --- the places ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "read"),
    [
        (
            "Juozapavo k., Lazdijų k. - visas išskyrus Kauno g., Ramybės g., Padumblių k.",
            "Juozapavo k., Lazdijų k. (išskyrus Kauno g., Ramybės g.), Padumblių k.",
        ),
        (
            "Lazdijų miesto sen.: Lazdijų m. - Dariaus ir Girėno g., Ežero g.",
            "Lazdijų miesto sen.: Lazdijų m., Dariaus ir Girėno g., Ežero g.",
        ),
        (
            "VARĖNOS M.: (A. Smetonos g.). MERKINĖS MSTL.",
            "VARĖNOS m. (A. Smetonos g.), MERKINĖS mstl.",
        ),
        (
            "Druskininkų miestas: M. K. Čiurlionio g., Ratnyčiosg., Tylos.g.",
            "Druskininkų m., M. K. Čiurlionio g., Ratnyčios g., Tylos g.",
        ),
        ("Byliškės, Byliškių sodų bendrijos", "Byliškės, Byliškių k."),
        ("Alytaus km.: Takniškių g.(Nuo Alytaus m. iki viaduko)", "Alytaus k., Takniškių g. 0"),
        (
            "Navickai (Navickų g. 2, 15); Gintaro g., Rasos g), Rutka",
            "Navickai (Navickų g. 2, 15); Gintaro g., Rasos g, Rutka",
        ),
        (
            "Visoje N.Ūtos sen. Bagrėnas ( tik Jurginų g.), Kalviai (be Lauko g.)",
            "Visoje Naujosios Ūtos sen. Bagrėnas (Jurginų g.), Kalviai (išskyrus Lauko g.)",
        ),
        (
            "Miklusėnai: Ūdrijos g., Padirmiškis- Plenta",
            "Miklusėnai, Ūdrijos g., Padirmiškis, Plenta",
        ),
    ],
)
def test_spellings(written, read):
    assert aratc.normalize(written) == read


def test_town_elderships():
    towns = {s.name: s.district for s in REGISTRY.settlements if s.abbr == "m."}
    assert towns["Druskininkai"] == "Druskininkų miesto"
    assert towns["Birštonas"] == "Birštono miesto"
    assert towns["Prienai"] == "Prienų"


def test_counts(part):
    data, warnings = part
    stats = data["matching"]
    assert stats["locations"] == 1558
    assert stats["household.single"] + stats["household.byStreet"] == 1379
    assert stats["household.ambiguous"] == 42
    assert stats["household.none"] == 137
    assert len(warnings) == 47
    with_mixed = {}
    for loc in data["locations"]:
        if "household" in loc.get("schedule", {}):
            label = next(m.label for m in aratc.MUNICIPALITIES if loc["district"] in m.elderships)
            with_mixed[label] = with_mixed.get(label, 0) + 1
    assert with_mixed == {
        "Alytaus r.": 393,
        "Prienų r.": 353,
        "Lazdijų r.": 324,
        "Varėnos r.": 243,
        "Druskininkų sav.": 58,
        "Birštono sav.": 50,
    }


@pytest.mark.parametrize(
    ("name", "district", "first", "last"),
    [
        ("Kaimynai", "Simno", "2026-03-02", "2027-02-01"),  # Alytaus r.
        ("Išlaužas", "Išlaužo", "2026-03-21", "2027-02-20"),  # Prienų r., a whole eldership
        ("Kučiūnai", "Kučiūnų", "2026-03-16", "2027-02-15"),  # Lazdijų r.
        ("Valkininkai", "Valkininkų", "2026-03-10", "2027-02-09"),  # Varėnos r.
        ("Grūtas", "Viečiūnų", "2026-03-09", "2027-02-22"),  # Druskininkai
        ("Nemajūnai", "Birštono", "2026-03-10", "2027-02-09"),  # Birštonas, the whole of it
    ],
)
def test_one_village_of_each_municipality(whole_year, name, district, first, last):
    dates = area_of(whole_year, place(whole_year, name, district), "household")["dates"]
    assert (dates[0], dates[-1]) == (first, last)


def test_a_whole_eldership(part):
    data, _ = part
    # "BUTRIMONIŲ SEN., PUNIOS SEN. Adamonys, ...": every settlement of Butrimonių sen.
    butrimonys = area_of(data, place(data, "Butrimonys", "Butrimonių"), "household")
    assert butrimonys["name"].startswith("BUTRIMONIŲ SEN., PUNIOS SEN.")
    # "Dalyje Jiezno sen.: tik Jiezno sen. esantys kaimai (be Jiezno, Strazdiškių, Jiezno
    # Kolonijų)", and the town and those two villages in another route.
    villages = "Dalyje Jiezno sen.: tik Jiezno sen. esantys kaimai"
    town = "Dalyje Jiezno sen.: tik Jieznas, Strazdiškės, Jiezno Kolonijos"
    assert area_of(data, place(data, "Jieznas"), "household")["name"] == town
    assert area_of(data, place(data, "Strazdiškės", "Jiezno"), "household")["name"] == town
    jiezno = [loc for loc in data["locations"] if loc["district"] == "Jiezno"]
    others = {area_of(data, loc, "household")["name"] for loc in jiezno} - {town}
    assert len(others) == 1 and others.pop().startswith(villages)
    reader = aratc.Routes(Index(REGISTRY), aratc.PROVIDER, defaultdict(dict))
    row_of_villages = Area("household", f"{villages} (be Jiezno, Strazdiškių, Jiezno Kolonijų )")
    names = {s.name for s, _ in reader.clauses(replace(row_of_villages, district="Prienų r."))[0]}
    assert len(names) == 61 - 3 and not names & {"Jieznas", "Strazdiškės", "Jiezno Kolonijos"}


def test_streets_of_the_towns(part):
    data, _ = part
    druskininkai = place(data, "Druskininkai", "Druskininkų miesto")
    mixed = by_street(data, druskininkai, "household")
    assert mixed["Vytauto g."] == [area_of_name(data, "household", "Druskininkų miestas: Vytauto")]
    # A street no route names: apartment buildings with shared containers.
    assert mixed["Taikos g."] == []
    # The farmsteads' file names Bijūnų g.: its own group.
    bijunu = mixed["Bijūnų g."]
    assert len(bijunu) == 1 and bijunu[0].startswith("Druskininkų miestas: Bijūnų g.")
    # Prienai: one mixed waste route, packaging by street.
    prienai = place(data, "Prienai")
    assert area_of(data, prienai, "household")["name"].startswith("Dalyje Prienų sen.: Prienai")
    packaging = by_street(data, prienai, "packaging")
    assert packaging["Algirdo g."][0].startswith("Dalyje Prienų miesto.: Algirdo g.")
    assert packaging["Vilniaus g."][0].startswith("Dalyje Prienų miesto.: Aušros g.")


def area_of_name(data, kind, prefix):
    return next(
        a["name"] for a in data["areas"] if a["kind"] == kind and a["name"].startswith(prefix)
    )


def test_villages_by_street(part):
    data, _ = part
    # "Lazdijų k. - tik Kauno g., Ramybės g." and "Lazdijų k. - visas išskyrus Kauno g.,
    # Ramybės g.".
    lazdijai = place(data, "Lazdijai", "Lazdijų")
    assert area_of(data, lazdijai, "packaging")["name"].startswith("Būdviečio sen.: Bielėnų k.")
    assert by_street(data, lazdijai, "packaging")["Kauno g."][0].startswith(
        "Būdviečio sen.: Aštriosios Kirsnos k."
    )
    # "Miklusėnai (išskyrus Ūdrijos g.)" and "Miklusėnai: Ūdrijos g.".
    miklusenai = place(data, "Miklusėnai")
    assert area_of(data, miklusenai, "household")["name"].startswith("ALYTAUS SEN. Aniškis")
    assert by_street(data, miklusenai, "household")["Ūdrijos g."][0].startswith(
        "ALYTAUS SEN. Bakšiai"
    )
    # Bagrėnas of Prienų sen., put in the Pakuonio section with its street: "Bagrėnas (be
    # Jurginų g.)", "Bagrėnas ( tik Jurginų g.)", "Prienai, Bagrėnas (tik Paupio g.)".
    bagrenas = place(data, "Bagrėnas")
    streets = by_street(data, bagrenas, "household")
    assert streets["Jurginų g."][0].startswith("Dalyje Pakuonio sen.: Antakalnis")
    assert streets["Paupio g."][0].startswith("Dalyje Prienų sen.: Prienai")
    # Some houses of a street: one more choice next to the route of the rest.
    assert len(by_street(data, place(data, "Kriauniai"), "household")["Nemuno g."]) == 2


def test_the_farmsteads_of_druskininkai(part):
    data, _ = part
    # Neravai of Viečiūnų sen.: its village route, or the one of farmsteads and places hard to
    # reach.
    choices = place(data, "Neravai", "Viečiūnų")["schedule"]["household"]["candidates"]
    groups = sorted(str(row(data, i).get("group")) for i in choices)
    assert groups == ["None", aratc.REMOTE_GROUP]


def test_names_that_match_nothing_are_reported(part):
    _, warnings = part
    for warning in (
        "not a settlement or a street: household: Miroslavo sen.: Dainava",
        "not a settlement or a street: packaging: Jakėnų sen.: Aleksandravos k.",
        "not a settlement or a street: household: Čiurlių k.: Alyvų g.",
        "not a settlement or a street: household: Senosios Varėnos k.: Liepų g.",
        "not a settlement or a street: household: Veisiejų sen.: Čivonių II k.",
    ):
        assert warning in warnings


# --- the next contract year ------------------------------------------------------


def routes(year, *names, kind="household", label="Alytaus r."):
    first = date(year, 3, 2)
    return ParseResult(
        [
            Area(kind, name, district=label, provider="alytus", dates={first.replace(day=2 + i)})
            for i, name in enumerate(names)
        ]
    )


def test_next_year_continues_routes_of_the_same_places():
    this_year = routes(2026, "SIMNO SEN. Simnas, Kaimynai.", "KROKIALAUKIO SEN. Varda.")
    next_year = routes(2027, "SIMNO SEN.: Simnas, Kaimynai", "KROKIALAUKIO SEN.: Varda, Dirvonai")
    file = aratc.ScheduleFile("household", f"{UPLOADS}x.pdf", "x.pdf", "Alytaus r.")
    warnings = aratc.combine(
        [(file, this_year), (file, next_year)], REGISTRY, date(2027, 2, 10), check=False
    )
    assert this_year.areas[0].dates == {date(2026, 3, 2), date(2027, 3, 2)}
    assert this_year.areas[1].dates == {date(2026, 3, 3)}
    assert next_year.areas == []
    assert warnings == [
        "Alytaus r. household: the route 'KROKIALAUKIO SEN.: Varda, Dirvonai' from 2027-03-02 "
        "doesn't match one in force; its dates are left out until then",
        "Alytaus r. household: the route 'KROKIALAUKIO SEN. Varda.' has no dates from 2027-03-02",
    ]
    # In March the new year's routes take over.
    this_year = routes(2026, "SIMNO SEN. Simnas, Kaimynai.")
    next_year = routes(2027, "SIMNO SEN. Simnas, Kaimynai.", "KROKIALAUKIO SEN. Varda.")
    aratc.combine([(file, this_year), (file, next_year)], REGISTRY, date(2027, 3, 3), check=False)
    assert this_year.areas == [] and len(next_year.areas) == 2


def test_too_few_routes_fail():
    file = aratc.ScheduleFile("household", f"{UPLOADS}x.pdf", "x.pdf", "Alytaus r.")
    with pytest.raises(ValidationError, match="Alytaus r.: only 1 household routes in the file"):
        aratc.combine(
            [(file, routes(2026, "SIMNO SEN. Simnas")), (file, routes(2027, "PIVAŠIŪNŲ SEN."))],
            REGISTRY,
            TODAY,
        )
    with pytest.raises(ValidationError, match="1 household routes of Alytaus r."):
        aratc.combine([(file, routes(2026, "SIMNO SEN. Simnas"))], REGISTRY, TODAY)


def test_march_without_the_new_files():
    data, warnings = build_dataset(files(), REGISTRY, date(2027, 3, 10), 31, aratc.SOURCE)
    # The places stay linked to last year's routes, which keep their last dates, also where
    # another municipality's file of the kind runs on (Alytaus r. packaging, to March 2028).
    kaimynai = area_of(data, place(data, "Kaimynai"), "household")
    assert kaimynai["dates"] == ["2027-02-01"]
    kucunai = area_of(data, place(data, "Kučiūnai", "Kučiūnų"), "glass")
    assert kucunai["dates"] == ["2027-01-24"]
    assert "Lazdijų r. household: the schedule ended on 2027-02-25, no newer one is read" in (
        warnings
    )


# --- Kauno švara and the published file ----------------------------------------------


def test_kauno_svara_leaves_these_municipalities_to_the_centre():
    # Its open-data file lists containers of Prienų r., Birštonas, Druskininkai (and Alytaus r.
    # packaging until December): schedules of the same places, only once.
    read = {name for m in svara.MUNICIPALITIES for name in m.spellings}
    assert not read & set(aratc.KAUNO_SVARA_NAMES)
    assert svara.FROM_ALYTAUS_RATC <= set(aratc.KAUNO_SVARA_NAMES)


def test_published_file_and_its_metrics(part, tmp_path):
    data, warnings = part
    data = {**data, "warnings": len(warnings)}
    dataset = merge_parts([(aratc.PROVIDER, data)], aratc.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == ["alytus"]
    assert all(a["provider"] == "alytus" for a in dataset["areas"])
    assert {a["district"] for a in dataset["areas"]} == {m.label for m in aratc.MUNICIPALITIES}
    aratc.check_places(dataset)

    (tmp_path / "alytaus-ratc").mkdir()
    (tmp_path / "alytaus-ratc" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    places = sum(1 for loc in dataset["locations"] if loc.get("schedule"))
    assert f'siuksliaveze_data_places{{source="alytus"}} {places}' in text
    last = int((date(2027, 2, 27) - date(1970, 1, 1)) / timedelta(seconds=1))
    assert (
        f'siuksliaveze_data_last_date_timestamp_seconds{{source="alytus",kind="household"}} '
        f"{last}" in text
    )


def test_a_municipality_without_its_routes_fails(part):
    # Three elderships of Varėnos r. without mixed waste: the totals of six would hide it.
    data, _ = part
    broken = [
        {**loc, "schedule": {}} if loc["district"] in {"Jakėnų", "Merkinės", "Varėnos"} else loc
        for loc in data["locations"]
    ]
    with pytest.raises(ValidationError, match="Varėnos r.: only 113 of 326 settlements"):
        aratc.check_places({"locations": broken})

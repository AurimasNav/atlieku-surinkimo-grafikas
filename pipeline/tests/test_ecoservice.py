"""Ecoservice: the pages of Šilutės r., Trakų r. and Šalčininkų r., their PDFs in three
layouts, the routes' places, and the two folders."""

import dataclasses
import json
from datetime import date
from urllib.parse import unquote

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, ecoservice, regions, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
# The files the pages link, by the name in their link, and their copies in fixtures/ecoservice.
COPIES = {
    "isvezimai_valdos_2026silute.pdf": "silute-household.pdf",
    "Traku-r.-atlieku-surinkimo-grafikas-2026.pdf": "trakai-household.pdf",
    "Individualiu-valdu-misriu-komunaliniu-atlieku-surinkimo-grafikas-Salcininku-r.-2026-m.pdf": (
        "salcininkai-household.pdf"
    ),
    "Individualiu-valdu-antriniu-zaliavu-isvezimo-grafikas-Salcininku-r.-2026-m.pdf": (
        "salcininkai-packaging.pdf"
    ),
}
REGISTRIES = {
    "silute": "registry-silutes-r-2026-11-21.json",
    "trakai": "registry-traku-r-2026-11-21.json",
    "salcininkai": "registry-salcininku-r-2026-11-21.json",
}


def serve(url, timeout=0):
    """The saved pages and files, as ecoservice.http.get."""
    for municipality in ecoservice.MUNICIPALITIES:
        if url == municipality.provider.url:
            return fixture(f"ecoservice/page-{municipality.provider.id}.html")
    return fixture(f"ecoservice/{COPIES[unquote(url.rsplit('/', 1)[-1])]}")


def registry(key):
    return Registry.load(FIXTURES / "ecoservice" / REGISTRIES[key])


def parsed(copy, kind, municipality, name=None):
    file = SourceFile(kind, f"https://ecoservice.lt/wp-content/uploads/{copy}", name or copy)
    return ecoservice.parse_file(file, fixture(f"ecoservice/{copy}"), municipality)


@pytest.fixture(scope="module")
def parts():
    """Each municipality's part as the daily job builds it from its page, with every date of
    the year kept."""
    built = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ecoservice.http, "get", serve)
        for municipality in ecoservice.MUNICIPALITIES:
            key = municipality.provider.id
            files, warnings = ecoservice.download(municipality, TODAY, 366)
            data, more = build_dataset(
                files, registry(key), TODAY, 366, ecoservice.source(municipality)
            )
            built[key] = (files, data, warnings + more)
    return built


def place(data, name, kind=None, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and kind in (None, loc["type"])
        and district in (None, loc["district"])
    )


def schedule_of(data, name, waste="household", kind=None, district=None):
    return place(data, name, kind, district)["schedule"][waste]


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def street_rows(data, settlement, waste, label, kind=None, district=None):
    """The rows of a street; None if it's left to the app."""
    location = place(data, settlement, kind, district)
    key = next(key for key, text in location["streets"] if text == label)
    return location["schedule"][waste]["streets"].get(key)


def named(data, ids):
    return sorted(row(data, i)["name"] for i in ids)


# --- the pages ---------------------------------------------------------------


def test_finds_the_schedules_on_each_page():
    found = {}
    for municipality in ecoservice.MUNICIPALITIES:
        page = fixture(f"ecoservice/page-{municipality.provider.id}.html").decode("utf-8")
        files = ecoservice.find_files(page, municipality.provider.url)
        found[municipality.provider.id] = sorted((f.kind, f.file_name) for f in files)
    assert found == {
        "silute": [("household", "isvezimai_valdos_2026silute.pdf")],
        # "Peržiūrėti grafiką" under "2026 m. Trakų r. mišrių komunalinių atliekų, pakuočių bei
        # stiklo atliekų surinkimo grafikas".
        "trakai": [("household", "Traku-r.-atlieku-surinkimo-grafikas-2026.pdf")],
        "salcininkai": [
            ("household", next(name for name in COPIES if "misriu" in name)),
            ("packaging", next(name for name in COPIES if "antriniu" in name)),
        ],
    }


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (
            "Šilutės rajono savivaldybės teritorijoje esančių buitinių atliekų ir antrinių "
            "žaliavų (iš individualių namų valdų) konteinerių išvežimo grafikas 2026 m.",
            "household",
        ),
        ("Individualių valdų antrinių žaliavių išvežimo grafikas", "packaging"),
        ("Individualių valdų mišrių komunalinių atliekų išvežimo grafikas", "household"),
        ("Stiklo pakuočių surinkimo grafikas", "glass"),
        ("Peržiūrėti grafiką", None),
    ],
)
def test_the_kind_of_a_file_by_its_text(text, kind):
    assert ecoservice.file_kind(text) == kind


def test_other_files_are_not_read():
    html = (
        '<p>2026 m. Trakų r. mišrių komunalinių atliekų surinkimo grafikas</p><script>"a"</script>'
        '<a href="/wp-content/uploads/2026/01/a-2026.pdf">Peržiūrėti grafiką</a>'
        '<a href="/data/public/uploads/b.pdf">Buitinių atliekų pusiau požeminių konteinerių '
        "aikštelių grafikas</a>"
        '<a href="/wp-content/uploads/c.pdf">Bendro naudojimo konteinerių grafikas</a>'
        '<a href="https://teisineinformacija.lt/d">Buitinių atliekų išvežimo grafikas</a>'
    )
    files = ecoservice.find_files(html, ecoservice.TRAKAI_PAGE)
    assert [(f.kind, f.url) for f in files] == [
        ("household", "https://ecoservice.lt/wp-content/uploads/2026/01/a-2026.pdf")
    ]


# --- the tables ------------------------------------------------------------------


def test_silute_blocks_of_mixed_waste_packaging_and_glass():
    result = parsed("silute-household.pdf", "household", ecoservice.SILUTE, "x-2026.pdf")
    assert len(result.areas) == 81  # 27 routes, each with three waste types
    assert not result.warnings
    route = {
        a.kind: a for a in result.areas if a.name == "ŠILUTĖS SENIŪNIJA: Pagrynių k., Šlažų k."
    }
    # Mixed waste every four weeks, every two from April to August; packaging and glass every
    # four weeks.
    assert sorted(route["household"].dates)[:5] == [
        date(2026, 1, 5),
        date(2026, 2, 2),
        date(2026, 3, 2),
        date(2026, 3, 30),
        date(2026, 4, 13),
    ]
    assert len(route["household"].dates) == 19 and route["household"].weekday == "Pirmadienis"
    assert route["packaging"].dates == route["glass"].dates and len(route["glass"].dates) == 13
    # The towns' streets and the gardens' are in the places.
    town = next(
        a for a in result.areas if a.name.startswith("ŠILUTĖS MIESTO GATVĖS: SB„Voveraitė“")
    )
    assert "Baldininkų 13-asis tak." in town.name
    assert {a.district for a in result.areas} == {"Šilutės r."}
    assert {a.provider for a in result.areas} == {"silute"}


def test_trakai_rows_of_every_kind_and_of_mixed_waste_only():
    result = parsed("trakai-household.pdf", "household", ecoservice.TRAKAI)
    assert len(result.areas) == 72  # 24 routes
    lentvaris = {a.kind: a for a in result.areas if a.name.startswith("Lentvario m.: Alyvų g.")}
    # "VISŲ RŪŠIŲ KONTEINERIAI Buitinių atliekų ir popierius, plastikas, stiklas" on 26
    # January, "TIK buitinių atliekų konteineriai" on 12 January: mixed waste every two weeks.
    assert sorted(lentvaris["household"].dates)[:3] == [
        date(2026, 1, 12),
        date(2026, 1, 26),
        date(2026, 2, 9),
    ]
    assert len(lentvaris["household"].dates) == 26
    assert lentvaris["packaging"].dates == lentvaris["glass"].dates
    assert (
        min(lentvaris["glass"].dates) == date(2026, 1, 26) and len(lentvaris["glass"].dates) == 13
    )
    # Routes on Saturdays and Sundays too (VI and VII).
    sunday = next(a for a in result.areas if a.name.startswith("Lentvario sen.: Kariotiškių k."))
    assert sunday.weekday == "Sekmadienis"


def test_trakai_a_weekday_in_the_cell_of_the_places():
    # The cell of the weekday "III" is one with the places: "... Naujosios\nIII Sodybos g.".
    result = parsed("trakai-household.pdf", "household", ecoservice.TRAKAI)
    route = next(a for a in result.areas if a.name.startswith("Trakų m.: Aukštadvario g."))
    assert "Naujosios Sodybos g., P. Cvirkos g." in route.name and " III " not in route.name
    assert route.weekday == "Trečiadienis"


def test_dates_off_a_routes_weekday_are_warnings():
    trakai = parsed("trakai-household.pdf", "household", ecoservice.TRAKAI).warnings
    assert len(trakai) == 2
    assert "household of 'Trakų m.: Bernardinų g., Birutės g., Birutės skg." in trakai[1]
    assert "on 2026-08-18, not on its weekday (Trečiadienis)" in trakai[1]
    # Without a column of weekdays, the weekday of the other dates.
    packaging = parsed("salcininkai-packaging.pdf", "packaging", ecoservice.SALCININKAI)
    assert [w.split(": ", 1)[1] for w in packaging.warnings] == [
        "packaging of 'Jašiūnų sen.: Buikų k., Deguškių k., Gojaus k., Jašiūnų mstl' on "
        "2026-11-17, not on its weekday (Penktadienis)",
        "packaging of 'Dainavos sen.' on 2026-12-28, not on its weekday (Penktadienis)",
    ]


def test_salcininkai_mixed_waste_under_cells_of_elderships():
    result = parsed("salcininkai-household.pdf", "household", ecoservice.SALCININKAI)
    assert len(result.areas) == 34 and {a.kind for a in result.areas} == {"household"}
    names = [a.name for a in result.areas]
    # An eldership's cell spans its routes, over the page break too.
    assert "AKMENYNĖS SEN.: ABOLŲ K. - Didžioji g., Mažoji g., MIŠTAUTONIŲ K., SMAGURIŲ K. - " in (
        next(n for n in names if "ABOLŲ" in n)
    )
    assert next(n for n in names if "BUIKŲ k." in n).startswith("JAŠIŪNŲ SEN.: BUIKŲ k.")
    # "VĖŽIONIŲ" + "K - Jazminų g", which ran over into the next route's cell.
    dainava = next(n for n in names if n.startswith("DAINAVOS SEN."))
    assert dainava.endswith("UŽUKLONIŲ K., VĖŽIONIŲ K - Jazminų g")
    assert next(n for n in names if "ALBERTINOS" in n).startswith("DIEVENIŠKIŲ SEN.: ALBERTINOS")
    town = next(
        a for a in result.areas if a.name.startswith("JAŠIŪNŲ SEN.: JAŠIŪNŲ MSTL. - Stoties")
    )
    assert len(town.dates) == 26  # "10,24", "2,16,30"


def test_salcininkai_packaging_and_glass_of_whole_elderships():
    result = parsed("salcininkai-packaging.pdf", "packaging", ecoservice.SALCININKAI)
    by_name = {(a.name, a.kind): a for a in result.areas}
    assert len(result.areas) == 38  # 19 routes, packaging ("POP") and glass ("STIK")
    akmenyne = by_name[("Akmenynės sen.", "packaging")]
    assert sorted(akmenyne.dates)[:2] == [date(2026, 1, 12), date(2026, 3, 9)]
    assert sorted(by_name[("Turgelių sen.", "glass")].dates) == [
        date(2026, 3, 13),
        date(2026, 6, 5),
        date(2026, 8, 28),
        date(2026, 11, 20),
    ]
    assert ("Baltosios Vokės sen.: Rūdninkų k., Vakariškių k., Plytinės k.", "glass") in by_name


def test_the_title_must_agree_with_the_file_name_and_the_link():
    with pytest.raises(ValueError, match="the title says 2026, the file name 2027"):
        parsed("trakai-household.pdf", "household", ecoservice.TRAKAI, "Traku-2027.pdf")
    with pytest.raises(ValueError, match="a household schedule, its link says packaging"):
        parsed("salcininkai-household.pdf", "packaging", ecoservice.SALCININKAI)


def test_a_waste_type_the_municipalitys_files_dont_have_fails():
    # Šalčininkų r.: packaging and glass are a file of their own.
    with pytest.raises(ValueError, match="glass dates in a household file"):
        parsed("trakai-household.pdf", "household", ecoservice.SALCININKAI)


def test_months_by_name_or_number():
    roman = ecoservice._header(
        ["", "", "", *"I II III IV V VI VII VIII IX X XI XII".split()],
        [
            "SAVAITĖS DIENOS",
            "VIETOVĖ",
            "ATLIEKŲ RŪŠIS",
            "MĖNUO",
            *[""] * 11,
        ],
        2026,
        "x",
    )
    assert roman.roles == {0: "weekday", 1: "places", 2: "kind"}
    assert roman.months[3] == date(2026, 1, 1) and roman.months[14] == date(2026, 12, 1)
    # A misspelt month is still one ("gėgužė", "rūgpjūtis").
    named = "sausis vasaris kovas balandis gėgužė birželis liepa rūgpjūtis".split()
    assert (
        len(ecoservice._header(["Savaitės diena", "", "Vietovės", *named], None, 2026, "x").months)
        == 8
    )
    with pytest.raises(ValueError, match="months out of order"):
        ecoservice._header(["", *"I II IV III V VI VII".split()], None, 2026, "x")
    with pytest.raises(ValueError, match="a column 'Adresas' before the months"):
        ecoservice._header(["Adresas", *named], None, 2026, "x")


# --- the places ----------------------------------------------------------------


def test_counts(parts):
    counts = {}
    for key, (_, data, warnings) in parts.items():
        stats = data["matching"]
        counts[key] = (
            stats["locations"],
            stats["household.single"] + stats["household.byStreet"],
            stats.get("household.ambiguous", 0),
            stats["household.none"],
            stats["packaging.single"] + stats["packaging.byStreet"],
            len(warnings),
        )
    assert counts == {
        "silute": (297, 271, 0, 26, 271, 6),
        "trakai": (437, 324, 0, 113, 324, 8),
        "salcininkai": (444, 381, 3, 60, 315, 3),
    }


@pytest.mark.parametrize(
    ("key", "name", "kind", "count", "first", "last"),
    [
        # "KINTŲ SENIŪNIJA: Blymacių k., Kintų mstl., ...": "1, 29" in January ... "3, 31".
        ("silute", "Kintai", "mstl.", 20, "2026-01-01", "2026-12-31"),
        # "Aukštadvario sen.: Aukštadvario mstl., ...": 8 January ... 24 December.
        ("trakai", "Aukštadvaris", "mstl.", 26, "2026-01-08", "2026-12-24"),
        # "AKMENYNĖS SEN.: AKMENYNĖS K. - Bažnyčios g., ...": 28 January ... "2,30".
        ("salcininkai", "Akmenynė", "k.", 13, "2026-01-28", "2026-12-30"),
    ],
)
def test_a_village_of_each_municipality(parts, key, name, kind, count, first, last):
    _, data, _ = parts[key]
    dates = row(data, schedule_of(data, name, kind=kind)["area"])["dates"]
    assert (len(dates), dates[0], dates[-1]) == (count, first, last)


@pytest.mark.parametrize(
    ("key", "town", "kind", "street"),
    [
        ("silute", "Šilutė", "m.", "Alyvų g."),
        ("silute", "Švėkšna", "mstl.", "Saulės g."),
        ("trakai", "Trakai", "m.", "Alyvų g."),
        ("trakai", "Lentvaris", "m.", "Aušros g."),
        ("salcininkai", "Šalčininkai", "m.", "Laimės g."),
        ("salcininkai", "Eišiškės", "m.", "Kaštonų g."),
    ],
)
def test_a_town_street_no_route_names_is_left_to_the_app(parts, key, town, kind, street):
    _, data, _ = parts[key]
    location = place(data, town, kind)
    assert street_rows(data, town, "household", street, kind) is None
    assert "area" not in location["schedule"]["household"]
    # No street is "no pickup": nothing in the files says a street has none.
    for waste, schedule in location["schedule"].items():
        assert all(schedule.get("streets", {}).values()), waste


@pytest.mark.parametrize(
    ("key", "town", "street"),
    [
        # "Gilijos g. (1, 3, ..., 18)" and "Gilijos g., ( 25, 27, ..., 32)".
        ("silute", "Šilutė", "Gilijos g."),
        # "Gėlių g. (nelyginiai numeriai iki 25 ...)" and "(nelyginiai numeriai nuo 29 ...)".
        ("trakai", "Lentvaris", "Gėlių g."),
        # "Vilniaus g.(nuo 1 namo iki 58,70 namo ...)" and "Vilniaus g.,(nuo posukio ...)".
        ("salcininkai", "Šalčininkai", "Vilniaus g."),
    ],
)
def test_a_street_split_by_house_numbers_asks_between_its_routes(parts, key, town, street):
    _, data, _ = parts[key]
    assert len(street_rows(data, town, "household", street, "m.")) == 2


def test_silute(parts):
    _, data, warnings = parts["silute"]
    # "ŠILUTĖS MIESTO GATVĖS:" and "ŠVĖKŠNOS MIESTELIO GATVĖS:": the towns' streets.
    tilzes = street_rows(data, "Šilutė", "household", "Tilžės g.")
    assert named(data, tilzes)[0].startswith("ŠILUTĖS MIESTO GATVĖS: Šiaurės g.")
    gintaro = street_rows(data, "Švėkšna", "household", "Gintaro g.")
    assert named(data, gintaro)[0].startswith("ŠVĖKŠNOS SENIŪNIJA: Alseikų k.")
    # The gardens' streets, "3-asis" for the register's "3-iasis" and as it is.
    for street in ("Baldininkų 3-iasis tak.", "Aušros 3-asis tak.", "Voveraičių tak."):
        assert street_rows(data, "Šilutė", "household", street), street
    # "Vilkėnų I, II, III k.": the register's Vilkėnas I, II and III.
    for name in ("Vilkėnas I", "Vilkėnas II", "Vilkėnas III"):
        assert schedule_of(data, name)["area"]
    # "Aviečių g." in the town's list is Pagryniai's street, its village another route's.
    pagryniai = schedule_of(data, "Pagryniai")
    assert row(data, pagryniai["area"])["name"] == "ŠILUTĖS SENIŪNIJA: Pagrynių k., Šlažų k."
    aviečių = street_rows(data, "Pagryniai", "household", "Aviečių g.")
    assert named(data, aviečių)[0].startswith("ŠILUTĖS MIESTO GATVĖS: Aušros g.")
    # "Žemaičių Naumiesčio mstl., Pergalės a.": the square, the town another route's.
    naumiestis = schedule_of(data, "Žemaičių Naumiestis")
    assert row(data, naumiestis["area"])["name"].endswith(": Žemaičių Naumiesčio mstl.")
    assert sorted(warnings) == sorted(
        f"not a settlement or a street: {kind}: {place}"
        for kind in ("household", "packaging", "glass")
        for place in ("Kintų sen.: Košių k.", "Šilutės m.: Svarstyklių g.")
    )


def test_trakai(parts):
    _, data, warnings = parts["trakai"]
    # "Trakų sen., Trakų m. Užpelkių k., Veličkavos k., Žaizdrių k. – prie Trakų miesto
    # prijungtos teritorijos": the villages, not the town.
    joined = schedule_of(data, "Veličkava")["area"]
    assert schedule_of(data, "Žaizdriai")["area"] == joined
    trakai = schedule_of(data, "Trakai")
    assert joined not in {r for rows in trakai["streets"].values() for r in rows}
    # "Trakų m. – buvusi Babriškių k. teritorija": a choice of its own in the town's list.
    babriskes = street_rows(data, "Trakai", "household", "Buvusi Babriškių k. teritorija")
    assert named(data, babriskes)[0].startswith("Rūdiškių sen.: Bajambalių k.")
    assert schedule_of(data, "Babriškės")["area"] == babriskes[0]
    # "Senųjų Trakų sen.: ... Varnikų k. (be Pakrantės g. ir Kraštinė g.)": the Varnikai of
    # Trakų sen. that has these streets, which another route names.
    location = next(
        loc for loc in data["locations"] if loc["name"] == "Varnikai" and loc.get("streets")
    )
    schedule = location["schedule"]["household"]
    assert row(data, schedule["area"])["name"].startswith("Trakų m.: Aukštadvario g.")
    pakrantes = next(key for key, label in location["streets"] if label == "Pakrantės g.")
    assert named(data, schedule["streets"][pakrantes])[0].startswith("Senųjų Trakų sen.: Padumblės")
    # "Rūdiškių sen., Rūdiškių m.": the whole town.
    assert row(data, schedule_of(data, "Rūdiškės", kind="m.")["area"])["name"] == (
        "Rūdiškių sen., Rūdiškių m."
    )
    assert not any("Varnikų k." in w or "Gabijos" in w for w in warnings)
    assert "not a settlement or a street: household: Trakų sen.: Užpelkių k." in warnings


def test_salcininkai(parts):
    _, data, warnings = parts["salcininkai"]
    # "TARTOKO K (be gatviu)": the village's route for any street another route doesn't name.
    tartokas = schedule_of(data, "Tartokas")
    assert row(data, tartokas["area"])["name"].startswith("ŠALČININKŲ SEN.: ČIAUKŠLIŲ K.")
    bruknynes = street_rows(data, "Tartokas", "household", "Bruknynės g.")
    assert len(bruknynes) == 2
    # "Rudnios k.,(10,14namas)" next to "RUDNIOS K.(be gatviu)": the app asks.
    assert len(schedule_of(data, "Rudnia", district="Gerviškių")["candidates"]) == 2
    # "NEBIGĖNŲ K. - Negibėnų g." and "S GIRIOS K.": Negibėnai and Giria.
    assert schedule_of(data, "Negibėnai")["area"] and schedule_of(data, "Giria")["area"]
    # "RŪDNINKŲ K. - ..., Poligonas; Ryto g., ...": the streets after the military range.
    assert schedule_of(data, "Rūdninkai")["area"]
    assert not any("Vilkpėdės" in w or "Poligonas" in w for w in warnings)
    # Packaging and glass of whole elderships.
    assert row(data, schedule_of(data, "Akmenynė", "packaging")["area"])["name"] == (
        "Akmenynės sen."
    )
    assert "glass" in place(data, "Turgeliai")["schedule"]
    # "Jašiūnų mstl.(Azalijų g., ..., Žalioji g., Keidžių k., ... Marazų k., ...": the bracket
    # of the town's streets isn't closed; the villages after it are the route's.
    marazai = row(data, schedule_of(data, "Marazai", "packaging")["area"])
    assert marazai["name"].startswith("Jašiūnų sen.: Buikų k., Deguškių k.")
    # "Krantinės g.,(nuo 27 namo nr. Lauko g., ...": nor is this one.
    lauko = street_rows(data, "Šalčininkai", "packaging", "Lauko g.", "m.")
    assert named(data, lauko)[0].startswith("Šalčininkų sen.: Milvydų k., Šalčininkų m.")
    assert "not a settlement or a street: household: Karmoniškių k.: Gėlių g." in warnings


def test_brackets_left_open_are_closed_before_the_next_place():
    assert ecoservice._close_brackets(
        "Jašiūnų mstl.(Azalijų g., Beržų g., Keidžių k., Gojaus k."
    ) == ("Jašiūnų mstl.(Azalijų g., Beržų g.), Keidžių k., Gojaus k.")
    assert ecoservice._close_brackets("Lentvario m. (Gabijos g., Gėlių g.") == (
        "Lentvario m. (Gabijos g., Gėlių g.)"
    )
    assert ecoservice._close_brackets("Varnikų k. (Pakrantės g.), Žydiškių k.") == (
        "Varnikų k. (Pakrantės g.), Žydiškių k."
    )


# --- next year and the folders ---------------------------------------------------


def routes(year, *names):
    return ParseResult(
        [
            Area(
                "household",
                name,
                district="Trakų r.",
                dates={date(year, 1, 14 + i)},
                provider="trakai",
            )
            for i, name in enumerate(names)
        ]
    )


def test_next_year_continues_routes_of_the_same_places():
    municipality = dataclasses.replace(ecoservice.TRAKAI, min_areas={})
    this_year = routes(2026, "Rūdiškių sen., Rūdiškių m.", "Paluknio sen.: Paluknio k.")
    next_year = routes(2027, "Rūdiškių sen.: Rūdiškių m.", "Paluknio sen.: Liepynų k.")
    file = SourceFile("household", "https://ecoservice.lt/x.pdf", "x.pdf")
    warnings = ecoservice.tratc.combine(
        [(file, this_year), (file, next_year)], registry("trakai"), date(2026, 12, 20), municipality
    )
    assert this_year.areas[0].dates == {date(2026, 1, 14), date(2027, 1, 14)}
    assert next_year.areas == []
    assert any("the 2027 route 'Paluknio sen.: Liepynų k.'" in w for w in warnings)


def test_two_folders(parts, tmp_path):
    for folder, region in ecoservice.REGIONS.items():
        built = [
            (m.provider, {**parts[m.provider.id][1], "warnings": len(parts[m.provider.id][2])})
            for m in region.municipalities
        ]
        dataset = merge_parts(built, region.source)
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
        (tmp_path / folder / "addresses.json").write_text("{}", encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # A source each, by its provider; the places with a schedule.
    assert 'siuksliaveze_data_places{source="trakai"} 324' in text
    for key in REGISTRIES:
        assert f'siuksliaveze_data_areas{{source="{key}",kind="glass"}}' in text
    index = regions.collect(tmp_path)["regions"]
    assert [(r["path"], r["providers"]) for r in index] == [
        ("ecoservice/", ["trakai", "salcininkai"]),
        ("silutes-r/", ["silute"]),
    ]


def test_a_municipality_that_fails_keeps_its_published_part(parts, tmp_path, monkeypatch):
    published = merge_parts(
        [
            (m.provider, {**parts[m.provider.id][1], "warnings": 0, "generatedAt": "2026-11-20"})
            for m in (ecoservice.TRAKAI, ecoservice.SALCININKAI)
        ],
        ecoservice.ECOSERVICE_PAGES,
    )

    def get(url, timeout=0):
        if url == ecoservice.SALCININKAI.provider.url:
            raise OSError("HTTP Error 503: Service Unavailable")
        return serve(url)

    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(ecoservice.http, "get", get)
    monkeypatch.setattr(ecoservice.address_register, "fetch", blocked)
    monkeypatch.setattr(ecoservice.address_points, "fetch", blocked)
    monkeypatch.setattr(build, "load_published", lambda url: lambda: published)
    assert ecoservice.main(["--region", "ecoservice", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    providers = {p["id"]: p["generatedAt"] for p in data["providers"]}
    assert providers["salcininkai"] == "2026-11-20" and providers["trakai"] > "2026-11-21"
    assert {a["provider"] for a in data["areas"]} == {"trakai", "salcininkai"}
    assert data["source"] == ecoservice.ECOSERVICE_PAGES
    assert (tmp_path / "addresses.json").exists()

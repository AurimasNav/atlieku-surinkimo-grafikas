"""Jurbarko r.: the Tauragės RATC page, the two yearly PDFs, their routes and the joined years."""

import json
from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import status, taurage
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.locations import _section_parts
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "taurage" / "registry-jurbarko-r-2026-11-21.json")
TODAY = date(2026, 11, 21)
UPLOADS = "https://www.uabtratc.lt/wp-content/uploads/2025/12/"
MIXED = SourceFile(
    "household",
    UPLOADS + "Jurbarko-grafikas_MKA_ZA_2026_suderintas.pdf",
    "Jurbarko-grafikas_MKA_ZA_2026_suderintas.pdf",
)
PACKAGING = SourceFile(
    "packaging",
    UPLOADS + "Jurbarko-pakuotes_2026_suderintas.pdf",
    "Jurbarko-pakuotes_2026_suderintas.pdf",
)
# Skirsnemunė's mixed waste, as the 2026 file lists it: every other Tuesday.
SKIRSNEMUNE = [
    (1, 6),
    (1, 20),
    (2, 3),
    (2, 17),
    (3, 3),
    (3, 17),
    (3, 31),
    (4, 14),
    (4, 28),
    (5, 12),
    (5, 26),
    (6, 9),
    (6, 23),
    (7, 7),
    (7, 21),
    (8, 4),
    (8, 18),
    (9, 1),
    (9, 15),
    (9, 29),
    (10, 13),
    (10, 27),
    (11, 10),
    (11, 24),
    (12, 8),
    (12, 22),
]


def files():
    return [(f, fixture(f"taurage/{f.file_name}")) for f in (MIXED, PACKAGING)]


def parsed(file):
    return taurage.parse_file(file, fixture(f"taurage/{file.file_name}"))


@pytest.fixture(scope="module")
def part():
    return build_dataset(files(), REGISTRY, TODAY, 31, taurage.SOURCE)


@pytest.fixture(scope="module")
def whole_year():
    """The data with every date of 2026 kept."""
    data, _ = build_dataset(files(), REGISTRY, TODAY, 366, taurage.SOURCE)
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


def area_of(data, location, kind):
    return row(data, location["schedule"][kind]["area"])


def streets(location):
    return {label: key for key, label in location["streets"]}


# --- the page ----------------------------------------------------------------


def test_finds_the_files_of_jurbarko_r_on_the_page():
    # By the texts of the links: not the other municipalities, nor bulky waste ("Jurbarko rajono
    # savivaldybės didelių gabaritų ... grafikas 2026"). The year is the one in the file's name,
    # not the upload folder's.
    found = taurage.find_files(fixture("taurage/page.html").decode("utf-8"))
    assert found == [(PACKAGING, 2026), (MIXED, 2026)]


def test_year_of_a_link_from_its_text_or_heading():
    html = (
        "<h5>2027 metų atliekų išvežimo grafikai</h5>"
        '<a href="/uploads/2026/12/Jurbarko-grafikas.pdf">Jurbarko miesto ir rajono mišrių atliekų'
        " grafikas</a>"
        '<a href="/uploads/2026/12/Jurbarko-pak.pdf">Jurbarko pakuočių grafikas 2028</a>'
    )
    found = taurage.find_files(html)
    assert [(f.kind, year) for f, year in found] == [("household", 2027), ("packaging", 2028)]


def test_reads_this_year_and_later():
    next_year = SourceFile("household", "https://x/uploads/2026/12/MKA_2027.pdf", "MKA_2027.pdf")
    old = SourceFile("household", "https://x/uploads/2024/12/MKA_2025.pdf", "MKA_2025.pdf")
    chosen, warnings = taurage.select_files(
        [(old, 2025), (MIXED, 2026), (next_year, 2027), (PACKAGING, 2026)], TODAY
    )
    assert chosen == [MIXED, next_year, PACKAGING] and warnings == []
    # In January, before the new files are posted: the newest ones, with a warning.
    chosen, warnings = taurage.select_files([(MIXED, 2026), (PACKAGING, 2026)], date(2027, 1, 5))
    assert chosen == [MIXED, PACKAGING]
    assert warnings == [
        "no household schedule for 2027 on the page",
        "no packaging schedule for 2027 on the page",
    ]


def test_a_correction_uploaded_later_is_read():
    fixed = SourceFile("packaging", "https://x/uploads/2026/03/pakuotes_2026.pdf", "pakuotes.pdf")
    chosen, warnings = taurage.select_files([(fixed, 2026), (PACKAGING, 2026)], TODAY)
    assert chosen == [fixed]
    assert warnings == [
        "Jurbarko-pakuotes_2026_suderintas.pdf: not read, pakuotes.pdf is a newer packaging "
        "schedule for 2026"
    ]


def test_a_file_without_a_year_is_reported():
    plain = SourceFile("household", "https://x/uploads/grafikas.pdf", "grafikas.pdf")
    chosen, warnings = taurage.select_files([(plain, None), (MIXED, 2026)], TODAY)
    assert chosen == [MIXED]
    assert warnings == ["grafikas.pdf: no year in its name, link or heading; not read"]


# --- the files ---------------------------------------------------------------------


def test_mixed_and_green_waste_file():
    result = parsed(MIXED)
    assert result.warnings == []
    kinds = [a.kind for a in result.areas]
    assert kinds.count("household") == 12 and kinds.count("green") == 2
    for area in result.areas:
        assert all(d.year == 2026 for d in area.dates)
        if area.kind == "household":
            # Every other week, the same weekday.
            assert len(area.dates) in (26, 27) and area.weekday
    route = next(a for a in result.areas if "Skirsnemunės mstl." in a.name)
    assert route.kind == "household" and route.weekday == "Antradienis"
    assert sorted(route.dates) == [date(2026, m, d) for m, d in SKIRSNEMUNE]
    assert route.name.startswith("Šimkaičių sen.: Jovališkės k., Akmeniškės k.")
    assert route.name.endswith(
        "Raudonės sen.: Stakių mstl., Stakių k., Pasnietalio k., Ambručių k., Dangutiškės k., "
        "Miškų k., Naujininkų k., Pamituvio I ir II k., Šambaravos k., Vaičiuškų k., Birbilų k., "
        "Čerbų k."
    )


def test_tables_that_run_on_to_the_next_page():
    names = [a.name for a in parsed(MIXED).areas]
    # The second green waste table ends at the top of page 2, a mixed waste table on each of
    # pages 3, 4 and 5; a line break inside "Bišpilio Sodo 1-oji g." is joined.
    assert any(n.endswith("Pušaitės g., Šaltinėlio g. Jurbarkų sen.: Jurbarkų k.") for n in names)
    assert any(
        "Tilžės g., Kauno g., Kranto g., Nemuno g., Tėviškės g. Jurbarkų" in n for n in names
    )
    assert any(n.endswith("Dainių k. (Eržvilko g. 3A, 5, 18, 20, 22, 24)") for n in names)
    assert any("Pjaunių k. Skirsnemunės sen.: Naukaimio k. (Vytėnų)" in n for n in names)
    assert any("Bišpilio Sodo 1-oji g., Bišpilio Sodo 2-oji g., Gedimino g." in n for n in names)


def test_last_column_of_green_waste():
    # pdfplumber's table finder loses December ("16"), whose text runs past the table's border.
    green = [a for a in parsed(MIXED).areas if a.kind == "green"]
    assert all(
        max(a.dates) == date(2026, 12, 16) and min(a.dates) == date(2026, 1, 7) for a in green
    )
    assert sorted(len(a.dates) for a in green) == [22, 23]


def test_hidden_text_is_not_read():
    # Page 1 clips away a table of another municipality's template under its notice, with
    # months, dates and villages of its own.
    names = " ".join(a.name for a in parsed(MIXED).areas)
    assert "Adomiškių" not in names and "MARIJAMPOL" not in names


def test_packaging_and_glass_file():
    result = parsed(PACKAGING)
    assert result.warnings == []
    kinds = [a.kind for a in result.areas]
    assert kinds.count("packaging") == 9 and kinds.count("glass") == 9
    first = {a.kind: a for a in result.areas if a.name.startswith("JURBARKO MIESTO SENIŪNIJA:")}
    assert first["packaging"].name == first["glass"].name
    assert len(first["packaging"].dates) == 13
    assert {date(2026, 7, 3), date(2026, 7, 31), date(2026, 12, 17)} <= first["packaging"].dates
    assert first["glass"].dates == {
        date(2026, 1, 22),
        date(2026, 4, 20),
        date(2026, 7, 13),
        date(2026, 10, 8),
    }


def test_the_year_in_the_title_and_the_name_must_agree():
    renamed = SourceFile("household", UPLOADS + "Jurbarko_MKA_2027.pdf", "Jurbarko_MKA_2027.pdf")
    with pytest.raises(ValueError, match="the title says 2026, the name 2027"):
        taurage.parse_file(renamed, fixture(f"taurage/{MIXED.file_name}"))


def word(text, x0, top=100.0):
    return {"text": text, "x0": x0, "x1": x0 + 6 * len(text), "top": top, "bottom": top + 12}


def test_unreadable_dates_fail_loudly():
    table = taurage._Table("household", [(150.0, 1), (200.0, 2)], 120.0, 1)
    with pytest.raises(ValueError, match="text before the dates: '6, 2O'"):
        taurage._read_line(table, [word("6,", 140), word("2O", 155)], 2026, "x")
    taurage._read_line(table, [word("6,", 140), word("20", 155), word("3;17", 195)], 2026, "x")
    days = {(d.month, d.day) for d in table.dates["household"]}
    assert days == {(1, 6), (1, 20), (2, 3), (2, 17)}
    with pytest.raises(ValueError, match="31 of month 2"):
        taurage._read_line(table, [word("31", 195)], 2026, "x")


def test_dates_of_no_waste_type_fail():
    table = taurage._Table(None, [(150.0, 1)], 120.0, 1)
    with pytest.raises(ValueError, match="dates of no waste type"):
        taurage._read_line(table, [word("14", 145)], 2026, "x")
    # The label of the row, left of the columns, gives it.
    taurage._read_line(table, [word("STIKLAS", 40), word("14", 145)], 2026, "x")
    assert table.dates == {"glass": {date(2026, 1, 14)}}


def test_parts_of_a_list():
    assert _section_parts("Skirsnemunės mstl., Skirsnemuniškių I, II ir III k., Molynės k.") == [
        "Skirsnemunės mstl.",
        "Skirsnemuniškių I, II ir III k.",
        "Molynės k.",
    ]
    # Commas inside brackets, and missing ones before a capital.
    assert _section_parts(
        "Motiškių k. Eimučių k., Klišių k. (Beržų g. 1, Vėjų g. 55) Naujasodžių k. Kauno g. "
        "Lauko g 2B Jurbarkų k.; Pušų 14"
    ) == [
        "Motiškių k.",
        "Eimučių k.",
        "Klišių k. (Beržų g. 1, Vėjų g. 55)",
        "Naujasodžių k.",
        "Kauno g.",
        "Lauko g 2B",
        "Jurbarkų k.",
        "Pušų 14",
    ]


# --- matching ------------------------------------------------------------------------


def test_counts(part):
    data, warnings = part
    stats = data["matching"]
    assert stats["locations"] == len(REGISTRY.settlements) == 374
    assert stats["unmatchedRows"] == 0
    assert all(loc["provider"] == "jurbarkas" for loc in data["locations"])
    with_kind = {
        kind: sum(1 for loc in data["locations"] if kind in loc.get("schedule", {}))
        for kind in ("household", "packaging", "glass", "green")
    }
    assert with_kind == {"household": 349, "packaging": 125, "glass": 125, "green": 2}


def test_skirsnemune(whole_year):
    # The village of Skirsnemunės sen. ("Skirsnemunės mstl." in the file, a village in the
    # register) has one row of each kind it is listed for.
    village = place(whole_year, "Skirsnemunė", "Skirsnemunės")
    household = area_of(whole_year, village, "household")
    assert household["weekday"] == "Antradienis"
    assert household["dates"] == [date(2026, m, d).isoformat() for m, d in SKIRSNEMUNE]
    # "Skirsnemunės mst." in the packaging file.
    assert area_of(whole_year, village, "packaging")["name"].startswith(
        "SKIRSNEMUNĖS SENIŪNIJA: Skirsnemunės mst."
    )
    assert "green" not in village["schedule"]


def test_the_town_by_street(part):
    data, _ = part
    town = place(data, "Jurbarkas")
    keys = streets(town)
    household = town["schedule"]["household"]
    assert set(household) == {"streets"}
    assert rows(data, household["streets"][keys["Dainių g."]])[0].startswith(
        "Jurbarko m., privačių namų konteineriai gatvėse: Dainių g., Eglių g."
    )
    # "Putinų g." in the file.
    assert len(household["streets"][keys["Putino g."]]) == 1
    # No route of any kind names Savanorių g. (apartment buildings): no pickup.
    assert household["streets"][keys["Savanorių g."]] == []
    # Bočių g. has green waste, so private houses, but no mixed waste route lists it: the app
    # offers the town's routes.
    assert keys["Bočių g."] not in household["streets"]
    assert len(town["schedule"]["green"]["streets"][keys["Bočių g."]]) == 1
    assert sum(1 for ids in household["streets"].values() if ids) == 111


def test_the_town_packaging(part):
    data, _ = part
    town = place(data, "Jurbarkas")
    keys = streets(town)
    packaging = town["schedule"]["packaging"]
    assert area_of(data, town, "packaging")["name"].startswith(
        "JURBARKO MIESTO SENIŪNIJA: Jurbarko miestas"
    )
    # Some houses of a street on another route: one more choice for that street.
    ryto = rows(data, packaging["streets"][keys["Ryto g."]])
    assert len(ryto) == 2 and ryto[0].startswith("GIRDŽIŲ SENIŪNIJA")
    pusu = rows(data, packaging["streets"][keys["Pušų g."]])
    assert pusu[1].startswith("JURBARKŲ SENIŪNIJA: Naujasodžių k.")


def test_villages_of_one_name(part):
    data, _ = part

    def household(name, district):
        return area_of(data, place(data, name, district), "household")["name"]

    assert household("Kalniškiai", "Jurbarkų").startswith("Eržvilko sen.: Eržvilko mstl.")
    assert household("Kalniškiai", "Šimkaičių").startswith("Šimkaičių sen.: Jovališkės k.")
    assert household("Pamituvys", "Veliuonos").startswith("Veliuonos sen.: Gricių k.")
    # "Pamituvio I ir II k." of Raudonės sen.
    assert household("Pamituvys I", "Raudonės") == household("Pamituvys", "Šimkaičių")
    assert household("Pamituvys II", "Raudonės") == household("Pamituvys", "Šimkaičių")
    # A town and a village of one name: by the type. "Smalininkų mstl." is the town (m.);
    # "Vadžgirio mstl." the town, so the village Vadžgirys has no mixed waste route.
    for kind in ("mstl.", "k."):
        stakiai = area_of(data, place(data, "Stakiai", kind=kind), "household")
        assert stakiai["name"].startswith("Šimkaičių sen.: Jovališkės k.")
    town = place(data, "Smalininkai", kind="m.")
    assert area_of(data, town, "packaging")["name"].startswith("SMALININKŲ SENIŪNIJA")
    assert "household" in place(data, "Vadžgirys", kind="mstl.")["schedule"]
    assert "household" not in place(data, "Vadžgirys", kind="k.").get("schedule", {})


def test_naukaimis_by_the_place_named_with_it(part):
    data, _ = part

    def household(name, district):
        return area_of(data, place(data, name, district), "household")["name"]

    # "Naukaimio k. (Skirsnemunė)" and "Naukaimio k. (Vytėnų)": Provider.aliases.
    assert "Naukaimio k. (Skirsnemunė)" in household("Naukaimis I", "Skirsnemunės")
    assert "Naukaimio k. (Vytėnų)" in household("Naukaimis II", "Skirsnemunės")
    # "Naukaimio k. (Vadžgirys)": the only one of Šimkaičių sen.
    assert "Naukaimio k. (Vadžgirys)" in household("Naukaimis", "Šimkaičių")


def test_numbered_villages(part):
    data, _ = part
    route = area_of(data, place(data, "Skirsnemunė"), "household")["id"]
    for name in ("Skirsnemuniškiai I", "Skirsnemuniškiai II", "Skirsnemuniškiai III"):
        assert place(data, name)["schedule"]["household"] == {"area": route}
    # "Balnių I ir II k.": the register's Balniai and Balniai II.
    assert (
        place(data, "Balniai")["schedule"]["household"]
        == (place(data, "Balniai II")["schedule"]["household"])
    )
    # "Pabebirvio k. (Šimkaičių), Pabebirvio k. (Vadžgirio)": both in the same route.
    assert place(data, "Pabebirvys I")["schedule"]["household"] == {"area": route}
    assert place(data, "Pabebirvys II")["schedule"]["household"] == {"area": route}


def test_streets_and_houses_in_brackets(part):
    data, _ = part
    village = place(data, "Naujasodžiai")
    keys = streets(village)
    household = village["schedule"]["household"]
    # "Naujasodžių k. (išskyrus Kauno g. 99, ...; Obelų g., Dariaus ir Girėno g.)": the rest
    # of the village; the streets left out go to the route that names them.
    assert row(data, household["area"])["name"].startswith("Eržvilko sen.: Būkintlaukio k.")
    assert rows(data, household["streets"][keys["Obelų g."]])[0].startswith(
        "Raudonės sen.: Raudonės mstl."
    )
    # "(Kauno g. 99; 101; 103; 107)": some houses, one more choice next to the rest.
    assert len(household["streets"][keys["Kauno g."]]) == 2
    klisiai = place(data, "Klišiai")
    household = klisiai["schedule"]["household"]
    assert len(household["streets"][streets(klisiai)["Eržvilko g."]]) == 2
    # Packaging: "Dainių k.(išskyrus Eržvilko g.)" and "Dainių k. (Eržvilko g., Vėjų g. 7; 1)".
    dainiai = place(data, "Dainiai")
    packaging = dainiai["schedule"]["packaging"]
    assert rows(data, packaging["streets"][streets(dainiai)["Eržvilko g."]])[0].startswith(
        "ERŽVILKO SENIŪNIJA"
    )
    assert len(packaging["streets"][streets(dainiai)["Vėjų g."]]) == 2


def test_spellings_and_typos(part):
    data, _ = part
    # "Raudonėnų g." for the village, "Batraitiškės k." for Baltraitiškė, "Seredžius mstl."
    # (nominative), "Juodaičių mstl." for the village Juodaičiai, "Jokūbaičių k. I (...)".
    assert "household" in place(data, "Raudonėnai")["schedule"]
    assert "packaging" in place(data, "Baltraitiškė")["schedule"]
    assert "packaging" in place(data, "Seredžius")["schedule"]
    assert "packaging" in place(data, "Juodaičiai")["schedule"]
    jokubaiciai = place(data, "Jokūbaičiai I")
    assert area_of(data, jokubaiciai, "packaging")["name"].startswith("ŠIMKAIČIŲ SENIŪNIJA")


def test_a_village_put_in_another_eldership(part):
    data, warnings = part
    # "VIEŠVILĖS SENIŪNIJA: ..., Kazikėnų k." is Kazikėnai of Smalininkų sen., which no
    # packaging route lists in its own eldership.
    kazikenai = place(data, "Kazikėnai")
    assert area_of(data, kazikenai, "packaging")["name"].startswith("SMALININKŲ SENIŪNIJA")
    # "Girdžių sen.: Liudvinavos k." isn't Liudvinava of Šimkaičių sen., which a route lists
    # there: reported.
    liudvinava = place(data, "Liudvinava")
    assert area_of(data, liudvinava, "household")["name"].startswith("Šimkaičių sen.: Jovališkės")
    assert "not a settlement or a street: household: Girdžių sen.: Liudvinavos k." in warnings


def test_names_that_match_nothing_are_reported(part):
    _, warnings = part
    assert sorted(set(warnings)) == [
        "not a settlement or a street: glass: Jurbarko miesto sen.: Smukučiai",
        "not a settlement or a street: glass: Skirsnemunės sen.: Skirsnemunės II k.",
        "not a settlement or a street: household: Girdžių sen.: Liudvinavos k.",
        "not a settlement or a street: household: Girdžių sen.: Paalsio k.",
        "not a settlement or a street: household: Jurbarkų sen.: Naujininkų k.",
        "not a settlement or a street: household: Naujasodžių k.: Linų g. 2",
        "not a settlement or a street: household: Skirsnemunės sen.: Kalniškių k.",
        "not a settlement or a street: household: Veliuonos sen.: Užringio k.",
        "not a settlement or a street: packaging: Jurbarko miesto sen.: Smukučiai",
        "not a settlement or a street: packaging: Skirsnemunės sen.: Skirsnemunės II k.",
    ]


# --- this year and the next ------------------------------------------------------


def year_rows(year, *names, kind="household"):
    return ParseResult(
        [Area(kind, name, dates={date(year, 12, 1)}, provider="jurbarkas") for name in names]
    )


NO_MINIMUM = replace(taurage.JURBARKAS, min_areas={})


def test_next_year_continues_routes_of_the_same_places():
    this_year = year_rows(2026, "Girdžių sen.: Girdžių mstl.", "Juodaičių sen.: Juodaičių k.")
    next_year = year_rows(
        2027,
        "GIRDŽIŲ SENIŪNIJA: Girdžių k.",  # the same village, worded differently
        "Juodaičių sen.: Juodaičių k., Mišiūnų k.",
    )
    warnings = taurage.combine(
        [(MIXED, this_year), (MIXED, next_year)], REGISTRY, TODAY, NO_MINIMUM
    )
    assert this_year.areas[0].dates == {date(2026, 12, 1), date(2027, 12, 1)}
    assert this_year.areas[1].dates == {date(2026, 12, 1)}
    assert next_year.areas == []
    assert warnings == [
        "household: the 2027 route 'Juodaičių sen.: Juodaičių k., Mišiūnų k.' doesn't match one "
        "2026 route; its dates are left out until 2027",
        "household: the 2026 route 'Juodaičių sen.: Juodaičių k.' has no dates for 2027",
    ]
    # In January the new year's routes take over.
    this_year = year_rows(2026, "Girdžių sen.: Girdžių mstl.")
    next_year = year_rows(2027, "Girdžių sen.: Girdžių mstl.", "Juodaičių sen.: Juodaičių k.")
    taurage.combine(
        [(MIXED, this_year), (MIXED, next_year)], REGISTRY, date(2027, 1, 2), NO_MINIMUM
    )
    assert this_year.areas == [] and len(next_year.areas) == 2


def test_next_year_is_checked_when_it_appears():
    this_year = year_rows(2026, "Girdžių sen.: Girdžių mstl.")
    next_year = year_rows(2027, "Girdžių sen.: Girdžių mstl.")
    with pytest.raises(ValueError, match="only 1 household routes in the 2027 file"):
        taurage.combine([(MIXED, this_year), (MIXED, next_year)], REGISTRY, TODAY)


def test_january_without_the_new_files():
    data, _ = build_dataset(files(), REGISTRY, date(2027, 2, 1), 31, taurage.SOURCE)
    # The places stay linked to last year's routes, which keep their last dates.
    village = place(data, "Skirsnemunė")["schedule"]
    assert row(data, village["household"]["area"])["dates"] == ["2026-12-22"]


def test_missing_file_fails():
    with pytest.raises(ValidationError, match="no packaging schedule file found"):
        build_dataset(files()[:1], REGISTRY, TODAY, 31, taurage.SOURCE)


# --- the published file ------------------------------------------------------------


def test_published_file_and_its_metrics(part, tmp_path):
    data, warnings = part
    data = {**data, "warnings": len(warnings)}
    dataset = merge_parts([(taurage.JURBARKAS.provider, data)], taurage.PAGE_URL)
    assert dataset["source"] == taurage.PAGE_URL
    assert [p["id"] for p in dataset["providers"]] == ["jurbarkas"]
    assert all(a["provider"] == "jurbarkas" for a in dataset["areas"])
    assert dataset["coverage"]["household"]["to"] == "2026-12-31"
    assert dataset["coverage"]["green"]["to"] == "2026-12-16"

    (tmp_path / "jurbarko-r").mkdir()
    (tmp_path / "jurbarko-r" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_areas{source="jurbarkas",kind="green"} 2' in text
    places = sum(1 for loc in dataset["locations"] if loc.get("schedule"))
    assert f'siuksliaveze_data_places{{source="jurbarkas"}} {places}' in text
    last = int((date(2026, 12, 31) - date(1970, 1, 1)) / timedelta(seconds=1))
    assert (
        f'siuksliaveze_data_last_date_timestamp_seconds{{source="jurbarkas",kind="household"}} '
        f"{last}" in text
    )

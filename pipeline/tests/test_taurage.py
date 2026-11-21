"""Tauragės RATC: the page, the yearly PDFs of Jurbarko r., Tauragės r., Šilalės r. and Pagėgių
sav., their routes and the joined years."""

import json
from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta
from functools import cache

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import status, taurage
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.locations import Index, _section_parts
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


# --- Tauragės r., Šilalės r. and Pagėgių sav. ---------------------------------------

OTHERS = {m.provider.id: m for m in taurage.MUNICIPALITIES if m is not taurage.JURBARKAS}
OTHER_REGISTRIES = {
    "taurage": "registry-taurages-r-2026-11-21.json",
    "silale": "registry-silales-r-2026-11-21.json",
    "pagegiai": "registry-pagegiu-sav-2026-11-21.json",
}
TAURAGES = {
    "district": "Taurages-rajonas_MKA_2026_suderintas-naujas-1.pdf",
    "town": "Taurages-miestas_MKA_2026_suderintas.pdf",
    "food": "Taurages-miestas_ZA_2026_suderintas.pdf",
    "packaging": "Taurages-miestas-ir-rajonas_pakuotes_2026_suderintas-03-10.pdf",
}
SILALES = {
    "household": "Silales_MKA_grafikas_2026_suderintas.pdf",
    "packaging": "Silale_pakuotes_2026_suderintas.pdf",
}
PAGEGIAI = "Pagegiai_bendras_2026_suderintas.pdf"


def serve(url, timeout=0):
    """The saved page and files, as taurage.http.get."""
    if url == taurage.PAGE_URL:
        return fixture("taurage/page.html")
    return fixture(f"taurage/{taurage.file_name(url)}")


@cache
def parsed_other(key, name, kind):
    file = SourceFile(kind, f"https://x/{name}", name)
    return taurage.parse_file(file, fixture(f"taurage/{name}"), OTHERS[key])


def of_kind(result, kind):
    return [a for a in result.areas if a.kind == kind]


@pytest.fixture(scope="module")
def others():
    """Each municipality's part, built as the daily job does from the page, with every date of
    2026 kept."""
    built = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(taurage.http, "get", serve)
        for key, municipality in OTHERS.items():
            files, warnings = taurage.download(municipality, TODAY, 31)
            registry = Registry.load(FIXTURES / "taurage" / OTHER_REGISTRIES[key])
            data, more = build_dataset(files, registry, TODAY, 366, taurage.source(municipality))
            built[key] = (files, data, warnings + more)
    return built


def other_place(data, name, kind=None):
    return place(data, name, kind=kind)


def street_rows(data, location, kind, label):
    """The rows of a street; None if it's left to the app."""
    key = streets(location)[label]
    return location["schedule"][kind]["streets"].get(key)


def test_finds_the_files_of_the_other_municipalities():
    html = fixture("taurage/page.html").decode("utf-8")

    def found(key):
        return {(f.kind, f.group, f.file_name) for f, _ in taurage.find_files(html, OTHERS[key])}

    # The town of Tauragė and its villages have mixed waste files of their own; the town's food
    # waste ("maisto ir žaliųjų") has one; bulky waste ("apvažiavimo būdu") isn't read.
    assert found("taurage") == {
        ("household", "district", TAURAGES["district"]),
        ("household", "town", TAURAGES["town"]),
        ("food", "town", TAURAGES["food"]),
        ("packaging", "", TAURAGES["packaging"]),
    }
    assert found("silale") == {
        ("household", "district", SILALES["household"]),
        ("packaging", "district", SILALES["packaging"]),
    }
    # One file, "mišrių/biologinių/pakuočių", of every kind.
    assert found("pagegiai") == {("household", "", PAGEGIAI)}


def test_the_town_and_the_villages_files_are_chosen_apart():
    uploads = "https://x/uploads/2026"
    town = SourceFile("household", f"{uploads}/01/m.pdf", "m.pdf", group="town")
    villages = SourceFile("household", f"{uploads}/01/r.pdf", "r.pdf", group="district")
    later = SourceFile("household", f"{uploads}/03/r2.pdf", "r2.pdf", group="district")
    chosen, warnings = taurage.select_files([(town, 2026), (villages, 2026), (later, 2026)], TODAY)
    # Not one of the town's and one of the villages' for the same year: a newer one each.
    assert chosen == [later, town]
    assert warnings == [
        "r.pdf: not read, r2.pdf is a newer household schedule of the district for 2026"
    ]


def test_the_villages_of_taurages_r():
    result = parsed_other("taurage", TAURAGES["district"], "household")
    assert result.warnings == []
    routes = of_kind(result, "household")
    assert len(routes) == 12 and all(len(a.dates) in (26, 27) and a.weekday for a in routes)
    first = routes[0]
    assert first.name.startswith("1.Maršrutas. Žygaičių seniūnija. Aukštupių k.")
    # The months in two rows of six: January to June, then July to December.
    assert min(first.dates) == date(2026, 1, 14) and max(first.dates) == date(2026, 12, 30)
    assert date(2026, 7, 29) in first.dates
    # A table that lists two routes with the same dates: a row each.
    two = [a for a in routes if a.name.startswith(("2.Maršrutas.", "3. Maršrutas."))]
    assert len(two) == 2 and two[0].dates == two[1].dates
    assert two[0].name.endswith("Žygaičių seniūnija. Kęsčių k., Leikiškių k.")
    assert any(a.name == "8. Maršrutas. Skaudvilės miestas, Nosaičių k." for a in routes)
    assert any(a.name.startswith("11 Maršrutas. Gaurės seniūnija.") for a in routes)


def test_the_town_of_taurage():
    household = of_kind(parsed_other("taurage", TAURAGES["town"], "household"), "household")
    # A table per weekday heading ("PIRMADIENIS I"), each with several parts of the town.
    assert len(household) == 5
    assert household[0].name.startswith("Pramonė. Pramonės g.,")
    assert "Senamiestis II. Bažnyčių g." in household[0].name
    assert household[0].weekday == "Pirmadienis" and len(household[0].dates) == 26
    # Food and green waste in one container, its label around the dates ("Žaliosios/maisto/"
    # above, "virtuvės atliekos" below).
    food = parsed_other("taurage", TAURAGES["food"], "food")
    assert [a.kind for a in food.areas] == ["food"] * 5
    pramone = food.areas[0]
    assert pramone.name.startswith("Pramonė.") and pramone.weekday == "Penktadienis"
    assert min(pramone.dates) == date(2026, 1, 2) and max(pramone.dates) == date(2026, 12, 18)
    assert len(pramone.dates) == 23


def test_taurages_packaging_and_glass():
    result = parsed_other("taurage", TAURAGES["packaging"], "packaging")
    assert result.warnings == []
    packaging, glass = of_kind(result, "packaging"), of_kind(result, "glass")
    assert len(packaging) == len(glass) == 18
    assert all(len(a.dates) == 12 for a in packaging)
    first = next(a for a in glass if a.name.startswith("(1) Tauragės m. Islandijos g."))
    assert first.dates == {
        date(2026, 2, 23),
        date(2026, 5, 26),
        date(2026, 8, 26),
        date(2026, 11, 25),
    }
    # A table whose months and dates are on the next page.
    route = next(a for a in packaging if a.name.startswith("(10) MAŽONŲ SENIŪNIJA"))
    assert route.name.endswith("Šaukėnų k., Tuščių k.") and len(route.dates) == 12


def test_silales_r_files():
    mixed = parsed_other("silale", SILALES["household"], "household")
    assert mixed.warnings == []
    assert len(of_kind(mixed, "household")) == 10
    # The weekday written letter by letter left of the labels isn't part of the places, nor is
    # the notice above the first table.
    assert all(" sen:" in a.name.split(",")[0] for a in mixed.areas)
    assert not any("informuoja" in a.name or a.name.startswith("P ") for a in mixed.areas)
    # Green waste of the town: its label below a row of weekdays ("Penktadienis").
    (green,) = of_kind(mixed, "green")
    assert green.name.startswith("Šilalės miesto sen: Šilalės m. privačių namų konteineriai.")
    assert len(green.dates) == 22 and {date(2026, 11, 6), date(2026, 11, 20)} <= green.dates
    packaging = parsed_other("silale", SILALES["packaging"], "packaging")
    assert len(of_kind(packaging, "packaging")) == len(of_kind(packaging, "glass")) == 11


def test_pagegiu_sav_file():
    result = parsed_other("pagegiai", PAGEGIAI, "household")
    assert result.warnings == []
    kinds = [a.kind for a in result.areas]
    assert {k: kinds.count(k) for k in set(kinds)} == {
        "household": 7,
        "green": 1,
        "packaging": 3,
        "glass": 3,
    }
    # Weekly in the town: a month's dates take two or three lines of its cell.
    town = next(a for a in result.areas if a.name == "Pagėgių sen.: Benininkų k., Pagėgių m.")
    assert town.kind == "household" and len(town.dates) == 52
    assert {d.day for d in town.dates if d.month == 3} == {2, 9, 16, 23, 30}
    # "M i šr io s": a label typed with spaces between its letters.
    route = next(a for a in result.areas if a.name.startswith("Pagėgių sen.: Būbliškės k.;"))
    assert route.kind == "household" and len(route.dates) == 26


@pytest.mark.parametrize(
    ("words", "kind"),
    [
        (["M", "i", "šr", "io", "s"], "household"),
        (["Žaliosios/maisto/"], "food"),
        (["komunalinės", "Žaliosios", "atliekos"], "green"),
        (["Popierius,", "plastikas,"], "packaging"),
        (["metalas", "Stiklas"], "glass"),
        (["Mėnuo"], None),
    ],
)
def test_the_kind_of_a_row_of_dates(words, kind):
    assert taurage._label_kind(words) == kind


def test_dates_of_no_waste_type_fail_below_the_places():
    table = taurage._Table(None, [(150.0, 1), (200.0, 2)], 120.0, 1, lines=["Laukuvos sen:"])
    with pytest.raises(ValueError, match="dates of no waste type"):
        taurage._row(table, [word("14", 145)], 2026, "x")
    # The label's words above the row give it, and the next line of the same cell has it too.
    assert taurage._row(table, [word("Mišrios", 40)], 2026, "x")
    assert taurage._row(table, [word("14,", 140), word("28", 160)], 2026, "x")
    assert taurage._row(table, [word("3", 195)], 2026, "x")
    assert table.dates == {"household": {date(2026, 1, 14), date(2026, 1, 28), date(2026, 2, 3)}}
    # Anything else ends the table.
    assert not taurage._row(table, [word("UAB", 40), word("Ecoservice", 150)], 2026, "x")


def reader(key):
    registry = Registry.load(FIXTURES / "taurage" / OTHER_REGISTRIES[key])
    provider = OTHERS[key].provider
    return provider.reader(Index(registry), provider, defaultdict(dict))


@pytest.mark.parametrize(
    ("text", "written"),
    [
        # A part of the town, a village written so, the brackets of which houses (also one
        # left unclosed), a full stop after a bracket.
        (
            "Senamiestis I. Aušros g., D. Poškos g. (lyginiai 24-44, nelyginiai 23-51 (nuo "
            "Vytauto g. iki Gedimino g.)), J. Tumo-Vaižganto g. (lyginiai 72-110, nelyginiai "
            "77-101 (nuo Vytauto g. iki Gedimino g.), K. Donelaičio g. Taurai. Alėjos g. "
            "Tauragės m. (Tarailiai). Akacijų g.",
            "Tauragės m., Aušros g., D. Poškos g. , J. Tumo-Vaižganto g. , K. Donelaičio g. Taurų "
            "k., Alėjos g. Tauragės m. (Tarailiai) Akacijų g.",
        ),
        # The packaging file: the route's number, houses from one to another, "sk.", "takas".
        (
            "(1) Tauragės m. T. Ivanausko sk., T. Ivanausko g. 52-95 (nuo Šilalės g. iki "
            "Veterinarijos g.), V. Kudirkos g. 37 (46)-64, Šilalės g. 61A,B,C,D, 63 A,B,C, 85; "
            "Mitaujos takas, Kundročių k. (tik 5, 5A, 6, 7). fPožerūnų k.",
            "Tauragės m. T. Ivanausko skg., T. Ivanausko g., V. Kudirkos g., Šilalės g. 61A, "
            "63A, 85; Mitaujos tak., Kundročių k. Požerūnų k.",
        ),
        (
            "1.Maršrutas. Žygaičių seniūnija. Padrūtupių k Drūtaviškių k., Joniškės kolektyviniai "
            "sodai",
            "Žygaičių seniūnija. Padrūtupių k. Drūtaviškių k., Joniškės k.",
        ),
    ],
)
def test_spellings_of_taurages_r(text, written):
    assert reader("taurage").written(text) == written


def test_spellings_of_silales_r_and_pagegiai():
    assert reader("silale").written(
        "(1)Šilalės miesto gatvės: A. Rubšio g., Dyvyčio g. Šilalės miesto sen: Šilalės m. "
        "privačių namų konteineriai. Kaltinėnų sen: Gedminiškės k. 11. Laukuvos sen: "
        "Norvainių k. (tik 1,2)."
    ) == (
        "Šilalės m., A. Rubšio g., Dievyčio g. Šilalės miesto sen: Šilalės m. Kaltinėnų sen: "
        "Gedminiškės k. 11 Laukuvos sen: Norvainių k."
    )
    assert (
        reader("pagegiai").written("Vilkyškių sen.: Kalvaičių k.(0). Dinkių k.,(0) Tutlių k.")
        == "Vilkyškių sen.: Kalvaičių k. Dinkių k., Tutlių k."
    )


def test_taurages_r_counts_and_villages(others):
    _, data, _ = others["taurage"]
    stats = data["matching"]
    assert stats["locations"] == 299 and stats["unmatchedRows"] == 0
    with_kind = {
        kind: sum(1 for loc in data["locations"] if kind in loc.get("schedule", {}))
        for kind in ("household", "packaging", "glass", "food")
    }
    assert with_kind == {"household": 277, "packaging": 275, "glass": 275, "food": 4}
    town = other_place(data, "Žygaičiai", "mstl.")
    route = area_of(data, town, "household")
    assert route["name"].startswith("1.Maršrutas. Žygaičių seniūnija.")
    assert route["dates"][0] == "2026-01-14" and route["dates"][-1] == "2026-12-30"
    assert len(route["dates"]) == 26
    # "8. Maršrutas. Skaudvilės miestas": the town, whole.
    skaudvile = area_of(data, other_place(data, "Skaudvilė"), "household")
    assert skaudvile["name"] == "8. Maršrutas. Skaudvilės miestas, Nosaičių k."
    # "Kundročių k. (tik 5, 5A, 6, 7)" in one route, "(tik 1, 2, 3, 4)" in another: the app asks.
    assert len(other_place(data, "Kundročiai")["schedule"]["packaging"]["candidates"]) == 2


def test_taurage_by_street(others):
    _, data, _ = others["taurage"]
    town = other_place(data, "Tauragė")
    assert set(town["schedule"]["household"]) == {"streets"}
    pramone = street_rows(data, town, "household", "Pramonės g.")
    assert rows(data, pramone)[0].startswith("Pramonė. Pramonės g.")
    # Houses of one street in two routes ("Vytauto g. (nelyginiai 1-77 ...)", "(lyginiai
    # 74-146 ...)"): the app asks.
    assert len(street_rows(data, town, "household", "Vytauto g.")) == 2
    # No route names Upokšnio g.: left to the app, which offers the town's routes. No street
    # of the town is "no pickup".
    assert street_rows(data, town, "household", "Upokšnio g.") is None
    for schedule in town["schedule"].values():
        assert all(schedule["streets"].values())
    # Food waste of the town, by street too.
    assert rows(data, street_rows(data, town, "food", "Pramonės g."))[0].startswith("Pramonė.")
    # A village named before its streets ("Taurai. Alėjos g., ..."), and streets of Tauragės
    # Dvaras among them ("Smilgų g., Tauragės Dvaro g.").
    taurai = area_of(data, other_place(data, "Taurai"), "household")
    assert taurai["name"].startswith("Taurai. Alėjos g.")
    assert area_of(data, other_place(data, "Tauragės Dvaras"), "household") == taurai
    # Norkaičiai: its village route, and streets in a route of the town.
    norkaiciai = other_place(data, "Norkaičiai")
    household = norkaiciai["schedule"]["household"]
    assert row(data, household["area"])["name"].startswith("9. Maršrutas. Mažonų seniūnija.")
    brolių = rows(data, street_rows(data, norkaiciai, "household", "Brolių g."))
    assert brolių[0].startswith("Papušynė I.")


def test_silales_r_town_and_villages(others):
    _, data, _ = others["silale"]
    assert data["matching"]["unmatchedRows"] == 0
    assert sum(1 for loc in data["locations"] if "household" in loc.get("schedule", {})) == 357
    # "Šilalės m. privačių namų konteineriai": the town, whole, for mixed and green waste; its
    # streets in one packaging route.
    town = other_place(data, "Šilalė")
    for kind in ("household", "green"):
        assert area_of(data, town, kind)["name"].startswith("Šilalės miesto sen: Šilalės m.")
    assert area_of(data, town, "packaging")["name"].startswith("(1)Šilalės miesto gatvės:")
    # "Dirkintų k. (tik Birutės g. ir Paupio g.)" in the town's route; the rest of the village
    # in another.
    dirkintai = other_place(data, "Dirkintai")
    packaging = dirkintai["schedule"]["packaging"]
    assert rows(data, street_rows(data, dirkintai, "packaging", "Paupio g."))[0].startswith("(1)")
    assert row(data, packaging["area"])["name"].startswith("(8)Šilalės kaimiškoji sen:")
    # "Dirkintų k. Birutės g. 1A, 9, ...": some houses, one more choice for that street.
    assert len(street_rows(data, dirkintai, "household", "Birutės g.")) == 2
    # "Katyčių k. 7, 11" in one route, Katyčiai in another: the app asks.
    assert len(other_place(data, "Katyčiai")["schedule"]["household"]["candidates"]) == 2
    village = area_of(data, other_place(data, "Laukuva"), "household")
    assert village["dates"][0] == "2026-01-07" and village["dates"][-1] == "2026-12-23"


def test_pagegiu_sav_towns_and_villages(others):
    _, data, _ = others["pagegiai"]
    assert data["matching"]["unmatchedRows"] == 0
    town = other_place(data, "Pagėgiai", "m.")
    household = area_of(data, town, "household")
    assert household["weekday"] == "Pirmadienis" and len(household["dates"]) == 52
    assert area_of(data, town, "green")["name"] == household["name"]
    # The village of the same name, by its type.
    village = area_of(data, other_place(data, "Pagėgiai", "k."), "household")
    assert village["name"] == "Pagėgių sen.: Būbliškės k.; Pagėgių k., Plaušvarių k."
    assert area_of(data, other_place(data, "Panemunė"), "household")["weekday"] == "Ketvirtadienis"
    # "Kalvaičių k.(0)" in the packaging file: still the village's route.
    assert "packaging" in other_place(data, "Kalvaičiai")["schedule"]
    route = area_of(data, other_place(data, "Vilkyškiai"), "household")
    assert route["dates"][0] == "2026-01-06" and route["dates"][-1] == "2026-12-22"


def test_names_the_other_municipalities_dont_match_are_reported(others):
    def warned(key):
        return sorted({w.split(": ", 2)[2] for w in others[key][2] if w.startswith("not a")})

    assert warned("taurage") == [
        "Batakių sen.: Batakių gel. Stotis",
        "Batakių sen.: Batakių glž. St.",
        "Lauksargių sen.: Žilučių k.",
        "Mažonų sen.: Ringių girininkija",
        "Tauragės m.: Brolių g.",
        "Tauragės m.: Miltaujos g.",
        "Tauragės m.: Naujoji g.",
        "Tauragės m.: Užuovėjos g.",
        "Tauragės m.: Vakarų g.",
        "Taurų k.: Geležinkelio g.",
        "Žygaičių sen.: Pašikšnių k.",
    ]
    assert warned("silale") == [
        "Upynos sen.: Brokštėnų k.",
        "Šilalės kaimiškoji sen.: Pajėrubynio k.",
        "Šilalės kaimiškoji sen.: Pajėrubynio k. 3",
    ]
    assert others["pagegiai"][2] == []


def test_the_town_and_the_villages_run_out_apart():
    municipality = replace(taurage.TAURAGE, min_areas={}, min_group_areas={})
    file = SourceFile("household", "https://x/MKA_2026.pdf", "MKA_2026.pdf")
    town, villages = replace(file, group="town"), replace(file, group="district")

    def rows_of(year, *names):
        return ParseResult(
            [Area("household", n, dates={date(year, 12, 1)}, provider="taurage") for n in names]
        )

    registry = Registry.load(FIXTURES / "taurage" / OTHER_REGISTRIES["taurage"])
    this_town = rows_of(2026, "Tauragės m.: Aušros g.")
    this_villages = rows_of(2026, "Žygaičių seniūnija. Žygaičių mstl.")
    next_villages = rows_of(2027, "ŽYGAIČIŲ SENIŪNIJA: Žygaičių mstl.")
    parsed = [(town, this_town), (villages, this_villages), (villages, next_villages)]
    assert taurage.combine(parsed, registry, TODAY, municipality) == []
    assert this_villages.areas[0].dates == {date(2026, 12, 1), date(2027, 12, 1)}
    # In January the villages' new routes take over; the town keeps its routes until its own
    # file of the new year is read.
    this_villages = rows_of(2026, "Žygaičių seniūnija. Žygaičių mstl.")
    next_villages = rows_of(2027, "ŽYGAIČIŲ SENIŪNIJA: Žygaičių mstl.")
    parsed = [(town, this_town), (villages, this_villages), (villages, next_villages)]
    taurage.combine(parsed, registry, date(2027, 1, 2), municipality)
    assert this_villages.areas == [] and len(next_villages.areas) == 1
    assert len(this_town.areas) == 1
    # Next year's file of the villages has its own minimum.
    strict = replace(municipality, min_group_areas={("household", "district"): 2})
    village = "Žygaičių seniūnija. Žygaičių mstl."
    parsed = [(villages, rows_of(2026, village)), (villages, rows_of(2027, village))]
    with pytest.raises(ValueError, match="only 1 household of the district routes in the 2027"):
        taurage.combine(parsed, registry, TODAY, strict)


def test_one_file_for_the_four_municipalities(part, others, tmp_path):
    jurbarkas, warnings = part
    built = [(taurage.JURBARKAS.provider, {**jurbarkas, "warnings": len(warnings)})]
    built += [
        (OTHERS[key].provider, {**data, "warnings": len(more)})
        for key, (_, data, more) in others.items()
    ]
    dataset = merge_parts(built, taurage.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == ["jurbarkas", "taurage", "silale", "pagegiai"]
    # Jurbarko r.'s part is as it was published on its own.
    alone = merge_parts(built[:1], taurage.PAGE_URL)
    for key in ("areas", "locations", "files"):
        mine = [x for x in dataset[key] if x.get("provider") == "jurbarkas"]
        assert mine == alone[key]
    assert dataset["providers"][0] == {**alone["providers"][0]}
    (tmp_path / "jurbarko-r").mkdir()
    (tmp_path / "jurbarko-r" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # A source each, by its provider; `jurbarkas` still means Jurbarko r. alone.
    assert 'siuksliaveze_data_areas{source="jurbarkas",kind="household"} 12' in text
    assert 'siuksliaveze_data_areas{source="taurage",kind="food"} 5' in text
    assert 'siuksliaveze_data_areas{source="silale",kind="green"} 1' in text
    assert 'siuksliaveze_data_places{source="pagegiai"} 105' in text

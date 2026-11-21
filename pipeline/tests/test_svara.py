# ruff: noqa: E501 (rows of the source file are long)
from dataclasses import replace
from datetime import date

import pytest

from schedule_pipeline import svara
from schedule_pipeline.svara import Rule, parse_rule

TODAY = date(2026, 11, 16)  # a Monday

CSV = """\
Kauno r. sav.;Ringaudų sen.;Karkiškių k.;Ganyklų g.;2;52-MK-1;2026-11-25;kas 14 dienų;Mišrios komunalinės
Kauno r. sav.;Ringaudų sen.;Karkiškių k.;Ganyklų g.;10;52-MK-2;2026-11-11;kas 14 dienų;Mišrios komunalinės
Kauno r. sav.;Ringaudų sen.;Karkiškių k.;Ganyklų g.;2A;52-MK-3;2026-11-18;kas 14 dienų;Mišrios komunalinės
Kauno r. sav.;Ringaudų sen.;Karkiškių k.;Ganyklų g.;2;52-MA-1;2026-11-20;kas 7 dienas;Maistinės atliekos
Kauno r. sav.;;Karkiškių k.;Parko g. ;;52-MK-4;2026-11-25;kas 14 dienų;Mišrios komunalinės
Kauno r. sav.;Užliedžių sen.;Sausinės k.;Vanagynės g.;1;52-ZA-1;2027-04-20;kas 28 dienas, balandį, gegužę, birželį, liepą, rugpjūtį, rugsėjį, spalį, lapkritį;Žaliosios atliekos
Kauno r. sav.;Užliedžių sen.;Sausinės k.;Vanagynės g.;1;52-MA-2;2025-04-22;kas 14 dienų;Maistinės atliekos
Kauno r. sav.;Užliedžių sen.;Sausinės k.;Vanagynės g.;3;52-AT-1;2026-11-20;kas 7 dienas;Atliekų tvarkymas
Kauno r. sav.;Užliedžių sen.;Sausinės k.;Vanagynės g.;5;52-AZ-1;2026-11-20;kiekvieną mėnesio dieną, kiekvieną mėnesį, penktadienį;Antrinės žaliavos
Kauno m. sav.;Šančių sen.;Kauno m.;Švenčionių g.;16;MK-000002;2026-11-18;kas 14 dienų;Mišrios komunalinės
"""


def relax(monkeypatch, max_skipped=0.05):
    """Small test files are enough data."""
    monkeypatch.setattr(
        svara,
        "MUNICIPALITIES",
        tuple(replace(m, min_rows=1, min_addresses=1) for m in svara.MUNICIPALITIES),
    )
    monkeypatch.setattr(svara, "MAX_SKIPPED", max_skipped)


@pytest.fixture
def built(monkeypatch):
    relax(monkeypatch, max_skipped=0.5)
    return svara.build(("﻿" + CSV).encode("utf-8"), TODAY)


def test_parse_rule():
    assert parse_rule("kas 14 dienų") == Rule(14)
    assert parse_rule("kas 21 dieną") == Rule(21)
    assert parse_rule("kas 7 dienas") == Rule(7)
    assert parse_rule("kas 28 dienas, balandį, gegužę, lapkritį") == Rule(28, (4, 5, 11))
    assert parse_rule("kiekvieną mėnesio dieną, kiekvieną mėnesį, penktadienį") == Rule(7)
    # Several days a week, and one day a month (Kaišiadorių r.).
    assert parse_rule(
        "kiekvieną mėnesio dieną, kiekvieną mėnesį, pirmadienį, trečiadienį, penktadienį"
    ) == Rule(7, weekdays=(0, 2, 4))
    assert parse_rule(
        "kiekvieną mėnesio dieną, kiekvieną mėnesį, trečiąjį mėnesyje trečiadienį"
    ) == Rule(0, weekdays=(2,), nth=3)
    assert parse_rule("kas 14 dienų, kartais") is None
    assert parse_rule("kiekvieną mėnesio dieną, kiekvieną mėnesį, pirmadienį, kartais") is None
    assert parse_rule("30 mėnesio dieną, spalį") is None
    assert parse_rule("") is None


def test_only_the_district_and_understood_rows(built):
    dataset, files, warnings = built
    assert dataset["municipality"] == "Kauno r. sav."
    assert set(files) == {"ringaudu", "uzliedziu"}
    assert "Kauno m." not in str(files)
    assert any("Atliekų tvarkymas" in w for w in warnings)


def test_containers_on_the_same_days_share_a_schedule(built):
    dataset, files, _ = built
    areas = dataset["areas"]
    street = files["ringaudu"]["towns"]["Karkiškių k."]["Ganyklų g."]
    # Houses in the order people expect.
    assert list(street) == ["2", "2A", "10"]
    household = {
        house: [areas[i] for i in ids if areas[i]["kind"] == "household"]
        for house, ids in street.items()
    }
    # 11 and 25 November are two weeks apart: one schedule. 18 November is the other week.
    assert household["2"][0]["id"] == household["10"][0]["id"]
    assert household["2"][0]["id"] != household["2A"][0]["id"]
    assert household["2"][0]["dates"][:3] == ["2026-10-28", "2026-11-11", "2026-11-25"]
    # The same address has mixed and food waste.
    assert sorted(areas[i]["kind"] for i in street["2"]) == ["food", "household"]


def test_a_missing_eldership_comes_from_the_town(built):
    _, files, _ = built
    # No eldership, a trailing space in the street and no house number in the source row.
    assert list(files["ringaudu"]["towns"]["Karkiškių k."]["Parko g."]) == [""]


def test_paused_schedules_resume_on_their_next_date(built):
    dataset, _, _ = built
    green = next(a for a in dataset["areas"] if a["kind"] == "green")
    assert green["resumes"] == "2027-04-20"
    assert green["months"] == [4, 5, 6, 7, 8, 9, 10, 11]
    # Nothing in winter, although November is one of its months.
    assert green["dates"][0] == "2027-04-20"


def test_containers_without_an_upcoming_pickup_are_left_out(built):
    dataset, files, warnings = built
    house = files["uzliedziu"]["towns"]["Sausinės k."]["Vanagynės g."]["1"]
    assert [dataset["areas"][i]["kind"] for i in house] == ["green"]
    assert "1 food containers without an upcoming pickup left out" in warnings


def test_every_weekday_rule_is_weekly(built):
    dataset, _, _ = built
    packaging = next(a for a in dataset["areas"] if a["kind"] == "packaging")
    assert packaging["every"] == 7
    assert "2026-11-20" in packaging["dates"]


def test_ids_stay_the_same_the_next_day(monkeypatch):
    relax(monkeypatch, max_skipped=0.5)
    content = CSV.encode("utf-8")

    def ids(day):
        areas = svara.build(content, day)[0]["areas"]
        return {a["id"] for a in areas if a["kind"] == "household"}

    assert ids(TODAY) == ids(date(2026, 11, 17))


def test_too_little_data_fails():
    with pytest.raises(svara.ValidationError, match="only 9 rows"):
        svara.build(CSV.encode("utf-8"), TODAY)


def test_addresses_get_coordinates_from_the_register(built):
    from schedule_pipeline.addresses import AddressPoint
    from schedule_pipeline.registry import Registry, Settlement, Street

    _, files, _ = built
    registry = Registry(
        [
            Settlement(
                1, "Karkiškės", "Karkiškių", "k.", "Ringaudų", [Street(10, "Ganyklų", "g.")]
            ),
            Settlement(
                2, "Sausinė", "Sausinės", "k.", "Užliedžių", [Street(20, "Vanagynės", "g.")]
            ),
        ]
    )
    points = [
        AddressPoint(1, 10, "2", 54.85, 23.75),
        AddressPoint(1, 10, "2A", 54.851, 23.751),
        AddressPoint(2, 20, "1", 54.95, 23.85),
    ]
    table, missing = svara.locate_table(files, registry, points, "now")
    assert table["places"] == [
        ["ringaudu", "Ringaudų sen.", "Karkiškių k.", "Ganyklų g."],
        ["uzliedziu", "Užliedžių sen.", "Sausinės k.", "Vanagynės g."],
    ]
    assert table["points"] == [
        [5485000, 2375000, 0, "2"],
        [5485100, 2375100, 0, "2A"],
        [5495000, 2385000, 1, "1"],
    ]
    # Ganyklų g. 10, Parko g. (no number) and Vanagynės g. 5 aren't in this register.
    assert missing == 3


# Spellings of one place, as Kauno švara's file has them (2026-11). Each row: eldership, town,
# street, house, waste type.
SPELLINGS = [
    ("Akademijos sen.", "Akademijos mstl.", "Forto g.", "8", "Maistinės atliekos"),
    ("Akademijos sen.", "Akademijos mstl.", "Forto g.", "8-1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Forto g.", "8-2", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Vynuogyno g.", "9", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Vynuogyno g.", "11", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Vynuogyno", "13", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademija", "Vynuogyno g.", "9", "Žaliosios atliekos"),
    ("Akademijos sen.", "Akademijos mstl.", "S. Žukausko g.", "1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "S. Žukausko g.", "3", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Silvestro Žukausko g.", "5", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Darbininkų g.", "1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Darbininkų skg.", "1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Kadagių g.", "3A", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Kadagių g.", "3a", "Maistinės atliekos"),
    # Not in the register: merged only by name.
    ("Akademijos sen.", "Akademijos mstl.", "Kaštonų g.", "1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Kaštonų g.", "2", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Kaštonų g", "4", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Beržų g.", "1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Beržų al.", "1", "Mišrios komunalinės"),
    ("Akademijos sen.", "Akademijos mstl.", "Beržų", "2", "Mišrios komunalinės"),
    # Under the wrong eldership: Domeikavos k. is in Domeikavos sen.
    ("Vandžiogalos sen.", "Domeikavos k.", "Rugio g.", "1", "Mišrios komunalinės"),
    ("Domeikavos sen.", "Domeikavos k.", "Rugio g.", "2", "Mišrios komunalinės"),
    # Two settlements of that name: stays where it is.
    ("Domeikavos sen.", "Jonučių k.", "Bičiulių g.", "1", "Mišrios komunalinės"),
]
REGISTRY_FOR_SPELLINGS = [
    (1, "Akademija", "Akademijos", "mstl.", "Akademijos", [
        (11, "Forto", "g."),
        (12, "Vynuogyno", "g."),
        (13, "Silvestro Žukausko", "g."),
        (14, "Darbininkų", "g."),
        (15, "Darbininkų", "skg."),
        (16, "Kadagių", "g."),
    ]),
    (2, "Domeikava", "Domeikavos", "k.", "Domeikavos", [(21, "Rugio", "g.")]),
    (3, "Jonučiai", "Jonučių", "k.", "Alšėnų", [(31, "Bičiulių", "g.")]),
    (4, "Jonučiai", "Jonučių", "k.", "Garliavos apylinkių", [(41, "Bičiulių", "g.")]),
]  # fmt: skip


def build_spellings(monkeypatch, registry=True):
    from schedule_pipeline.registry import Registry, Settlement, Street

    relax(monkeypatch)
    frequency = {"Maistinės atliekos": "kas 7 dienas"}
    rows = [
        f"Kauno r. sav.;{e};{t};{s};{h};C-{n};2026-11-20;{frequency.get(w, 'kas 14 dienų')};{w}"
        for n, (e, t, s, h, w) in enumerate(SPELLINGS)
    ]
    settlements = [
        Settlement(code, name, genitive, abbr, district, [Street(*s) for s in streets])
        for code, name, genitive, abbr, district, streets in REGISTRY_FOR_SPELLINGS
    ]
    return svara.build(
        "\n".join(rows).encode("utf-8"), TODAY, {"kauno": Registry(settlements)} if registry else {}
    )


def kinds(dataset, ids):
    return sorted(dataset["areas"][i]["kind"] for i in ids)


def test_a_town_written_two_ways_is_listed_once(monkeypatch):
    dataset, files, _ = build_spellings(monkeypatch)
    akademija = next(e for e in dataset["elderships"] if e["name"] == "Akademijos sen.")
    assert akademija["towns"] == ["Akademijos mstl."]
    # The one "Akademija" row had only a green waste bin of Vynuogyno g. 9; now it is one
    # address with everything the town has there.
    town = files["akademijos"]["towns"]["Akademijos mstl."]
    assert kinds(dataset, town["Vynuogyno g."]["9"]) == ["green", "household"]
    assert "Forto g." in town
    # Phones that saved "Akademija" find their address again.
    aliases = files["akademijos"]["aliases"]
    assert aliases["Akademija"]["Vynuogyno g."]["9"] == [
        "akademijos",
        "Akademijos mstl.",
        "Vynuogyno g.",
        "9",
    ]
    assert dataset["stats"]["merged"]["towns"] == 1


def test_street_spellings_with_one_register_code_are_merged(monkeypatch):
    dataset, files, _ = build_spellings(monkeypatch)
    town = files["akademijos"]["towns"]["Akademijos mstl."]
    # The spelling with the most addresses stays, not the register's full name.
    assert list(town["S. Žukausko g."]) == ["1", "3", "5"]
    assert "Silvestro Žukausko g." not in town
    assert list(town["Vynuogyno g."]) == ["9", "11", "13"]
    assert "Vynuogyno" not in town
    aliases = files["akademijos"]["aliases"]["Akademijos mstl."]
    assert aliases["Silvestro Žukausko g."]["5"][2:] == ["S. Žukausko g.", "5"]
    assert aliases["Vynuogyno"]["13"][2:] == ["Vynuogyno g.", "13"]
    # "3a" and "3A" are one house.
    assert list(town["Kadagių g."]) == ["3A"]
    assert kinds(dataset, town["Kadagių g."]["3A"]) == ["food", "household"]


def test_streets_of_different_types_stay_apart(monkeypatch):
    for registry in (True, False):
        _, files, _ = build_spellings(monkeypatch, registry)
        town = files["akademijos"]["towns"]["Akademijos mstl."]
        assert {"Darbininkų g.", "Darbininkų skg."} <= set(town)
        # Not in the register: "Beržų" could be either of them, so it stays as it is.
        assert {"Beržų g.", "Beržų al.", "Beržų"} <= set(town)


def test_streets_not_in_the_register_merge_by_name(monkeypatch):
    for registry in (True, False):
        _, files, _ = build_spellings(monkeypatch, registry)
        town = files["akademijos"]["towns"]["Akademijos mstl."]
        assert list(town["Kaštonų g."]) == ["1", "2", "4"]
        assert "Kaštonų g" not in town


def test_without_the_register_only_names_are_merged(monkeypatch):
    dataset, files, _ = build_spellings(monkeypatch, registry=False)
    akademija = next(e for e in dataset["elderships"] if e["name"] == "Akademijos sen.")
    assert akademija["towns"] == ["Akademija", "Akademijos mstl."]
    town = files["akademijos"]["towns"]["Akademijos mstl."]
    assert {"S. Žukausko g.", "Silvestro Žukausko g."} <= set(town)
    assert list(town["Vynuogyno g."]) == ["9", "11", "13"]


def test_a_town_moves_to_its_eldership_only_if_certain(monkeypatch):
    dataset, files, _ = build_spellings(monkeypatch)
    assert list(files["domeikavos"]["towns"]["Domeikavos k."]["Rugio g."]) == ["1", "2"]
    # Its old place keeps the alias, though no town is listed there any more.
    assert files["vandziogalos"]["towns"] == {}
    assert files["vandziogalos"]["aliases"]["Domeikavos k."]["Rugio g."]["1"] == [
        "domeikavos",
        "Domeikavos k.",
        "Rugio g.",
        "1",
    ]
    vandziogala = next(e for e in dataset["elderships"] if e["name"] == "Vandžiogalos sen.")
    assert vandziogala["towns"] == []
    # Two Jonučiai elsewhere, none in Domeikavos sen.: left where it is, and counted.
    assert "Jonučių k." in files["domeikavos"]["towns"]
    merged = dataset["stats"]["merged"]
    assert (merged["townsMovedToTheirEldership"], merged["townsInAnotherEldership"]) == (1, 1)


def test_every_house_number_gets_the_waste_types_of_its_building(monkeypatch):
    dataset, files, warnings = build_spellings(monkeypatch)
    forto = files["akademijos"]["towns"]["Akademijos mstl."]["Forto g."]
    # The food bin was listed under 8, the mixed waste bins under 8-1 and 8-2.
    for house in ("8", "8-1", "8-2"):
        assert kinds(dataset, forto[house]) == ["food", "household"]
    assert dataset["stats"]["merged"]["filledFromBuilding"] == 3
    # Counted in the stats, not as warnings.
    assert not any("merged" in w for w in warnings)


def test_fill_buildings_keeps_what_a_house_number_has():
    index = {
        "E": {
            "T": {
                "S": {
                    "8": {"food-a"},
                    "8-1": {"mixed-a"},
                    "8-2": {"mixed-a"},
                    "8-3": {"mixed-b", "food-b"},
                    "10-1": {"mixed-a"},
                    "10-2": {"mixed-b"},
                    "12": {"mixed-a"},
                }
            }
        }
    }
    kind_of = {"food-a": "food", "food-b": "food", "mixed-a": "household", "mixed-b": "household"}
    assert svara.fill_buildings(index, kind_of) == 3
    houses = index["E"]["T"]["S"]
    # 8 has no mixed waste of its own: it gets what most of its flats have.
    assert houses["8"] == {"food-a", "mixed-a"}
    # Food comes from the house; a flat that has its own keeps it.
    assert houses["8-1"] == houses["8-2"] == {"food-a", "mixed-a"}
    assert houses["8-3"] == {"mixed-b", "food-b"}
    # Without the house and without a majority, nothing is added to what they have.
    assert houses["10-1"] == {"mixed-a"}
    assert houses["10-2"] == {"mixed-b"}
    assert houses["12"] == {"mixed-a"}


def test_towns_get_their_register_name_for_the_search(monkeypatch):
    dataset, _, _ = build_spellings(monkeypatch)
    names = {e["name"]: e.get("registerNames") for e in dataset["elderships"]}
    # People type "Akademija"; the file writes the genitive and the type.
    assert names["Akademijos sen."] == {"Akademijos mstl.": "Akademija"}
    # Jonučiai isn't in Domeikavos sen.: both Jonučiai of the district have that name.
    assert names["Domeikavos sen."] == {"Domeikavos k.": "Domeikava", "Jonučių k.": "Jonučiai"}
    # No towns, no names; the list of towns stays as it was.
    assert names["Vandžiogalos sen."] is None
    assert next(e for e in dataset["elderships"] if e["name"] == "Akademijos sen.")["towns"] == [
        "Akademijos mstl."
    ]


def test_register_names_only_where_they_are_certain_and_differ():
    from schedule_pipeline.registry import Registry, Settlement

    registry = Registry(
        [
            Settlement(1, "Akademija", "Akademijos", "mstl.", "Akademijos"),
            Settlement(2, "Babtai", "Babtų", "mstl.", "Babtų"),
            Settlement(3, "Babtai", "Babtų", "k.", "Babtų"),
            # Two names with one genitive, both outside the town's eldership.
            Settlement(4, "Pagiriai", "Pagirių", "k.", "Kulautuvos"),
            Settlement(5, "Pagirys", "Pagirių", "k.", "Zapyškio"),
            Settlement(6, "Pagiriai", "Pagirių", "k.", "Babtų"),
        ]
    )
    index = {
        "Akademijos sen.": {"Akademija": {}, "Kauno raj.": {}},
        "Babtų sen.": {"Babtų mstl.": {}, "Babtų k.": {}, "Pagirių k.": {}},
        "Lapių sen.": {"Pagirių k.": {}},
    }
    assert svara.register_names(index, registry) == {
        # "Akademija" is the register's name already; "Kauno raj." is no settlement.
        "Babtų sen.": {"Babtų mstl.": "Babtai", "Babtų k.": "Babtai", "Pagirių k.": "Pagiriai"},
        # Not in Lapių sen., and the district has a Pagiriai and a Pagirys: no name.
    }
    assert svara.register_names(index, None) == {}


def test_without_the_register_no_names_are_published(monkeypatch):
    dataset, _, _ = build_spellings(monkeypatch, registry=False)
    assert not any("registerNames" in e for e in dataset["elderships"])


# Rows of the other municipalities, as the file has them (2026-11-21; Kauno švara's container
# numbers). Kaišiadorių r. is written two ways, and a few rows have it as their eldership.
KAISIADORYS = """\
Kaišiadorių r. sav.;Kaišiadorių miesto sen.;Kaišiadorių m.;Beržyno g.;23;49-MK-000002;2026-12-03;kas 14 dienų;Mišrios komunalinės
Kaišiadorių r. sav.;Kaišiadorių miesto sen.;Kaišiadorių m.;Laisvės g.;6;49-MK-000003;2026-12-03;kas 14 dienų;Mišrios komunalinės
Kaišiadorių rajono sav.;Kaišiadorių rajono sav.;Kaišiadorių m.;Dobilų g.;5;49-MK-009927;2026-12-03;kas 14 dienų;Mišrios komunalinės
Kaišiadorių rajono sav.;Paparčių sen.;Neravų k.;Ąžuolo g.;8;49-MK-000288;2026-12-01;kas 28 dienas;Mišrios komunalinės
Kaišiadorių r. sav.;Žiežmarių apylinkės sen.;Stasiūnų k.;Ateities g.;6;MK-000986;2026-12-01;kiekvieną mėnesio dieną, kiekvieną mėnesį, pirmąjį mėnesyje antradienį;Mišrios komunalinės
Kaišiadorių r. sav.;Žiežmarių apylinkės sen.;Stasiūnų k.;Ateities g.;6;MK-000986;2026-12-18;kiekvieną mėnesio dieną, kiekvieną mėnesį, trečiąjį mėnesyje penktadienį;Mišrios komunalinės
Kaišiadorių r. sav.;Rumšiškių sen.;Rusonių k.;Topolių g.;26;49-MK-000101;2026-12-02;kiekvieną mėnesio dieną, kiekvieną mėnesį, pirmąjį mėnesyje trečiadienį;Mišrios komunalinės
Kaišiadorių r. sav.;Kaišiadorių miesto sen.;Kaišiadorių m.;Gedimino g.;92;49-MK-003602;2026-11-23;kiekvieną mėnesio dieną, kiekvieną mėnesį, pirmadienį, trečiadienį, penktadienį;Mišrios komunalinės
"""
ALYTAUS_RATC = """\
Prienų r. sav.;Jiezno sen.;Jiezno m.;Vytauto g.;1;PR-1;2026-11-26;kas 14 dienų;Mišrios komunalinės
Birštono sav.;Birštono sen.;Birštono m.;Jaunimo g.;2;BI-1;2026-11-26;kas 14 dienų;Mišrios komunalinės
Druskininkų sav.;Leipalingio sen.;Leipalingio mstl.;Ežero g.;3;DR-1;2026-11-26;kas 14 dienų;Mišrios komunalinės
"""
NOVEMBER_21 = date(2026, 11, 21)


def build_all(monkeypatch, csv=CSV + KAISIADORYS + ALYTAUS_RATC, registries=None):
    relax(monkeypatch, max_skipped=0.5)
    return svara.build(csv.encode("utf-8"), NOVEMBER_21, registries)


def dates_of(dataset, ids):
    return sorted({d for i in ids for d in dataset["areas"][i]["dates"]})


def test_kaisiadorys_is_published_with_kauno_r(monkeypatch):
    dataset, files, warnings = build_all(monkeypatch)
    kaisiadorys = [e for e in dataset["elderships"] if e.get("municipality") == "Kaišiadorių r."]
    assert [e["name"] for e in kaisiadorys] == [
        "Kaišiadorių miesto sen.",
        "Paparčių sen.",
        "Rumšiškių sen.",
        "Žiežmarių apylinkės sen.",
    ]
    # Kauno r. elderships say nothing: apps that don't know the field take them as they are.
    assert {e["name"] for e in dataset["elderships"] if "municipality" not in e} == {
        "Ringaudų sen.",
        "Užliedžių sen.",
    }
    street = files["kaisiadoriu-miesto"]["towns"]["Kaišiadorių m."]["Beržyno g."]
    assert dates_of(dataset, street["23"])[2:5] == ["2026-11-19", "2026-12-03", "2026-12-17"]
    # A row with the municipality as its eldership: the eldership of its town.
    assert "Dobilų g." in files["kaisiadoriu-miesto"]["towns"]["Kaišiadorių m."]
    # Monitoring counts it apart (status.py); Kauno r.'s own numbers stay at the top.
    assert dataset["otherMunicipalities"] == [
        {
            "id": "kaisiadorys",
            "name": "Kaišiadorių r.",
            "stats": {
                "rows": 8,
                "addresses": 7,
                "towns": 4,
                "areas": {"household": 8},
                "merged": dict.fromkeys(
                    [
                        "towns",
                        "streets",
                        "houses",
                        "townsMovedToTheirEldership",
                        "townsInAnotherEldership",
                        "aliases",
                        "filledFromBuilding",
                    ],
                    0,
                ),
            },
            "warnings": 0,
        }
    ]
    assert dataset["stats"]["rows"] == 9
    assert not [w for w in warnings if w.startswith("Kaišiadorių r.")]


def test_kauno_r_stays_as_it_was_alone(monkeypatch):
    alone, alone_files, _ = build_all(monkeypatch, csv=CSV)
    both, both_files, _ = build_all(monkeypatch)
    assert "otherMunicipalities" not in alone
    # Same file names and contents, schedules at the same positions, the same numbers.
    for name, data in alone_files.items():
        assert both_files[name] == data
    assert both["areas"][: len(alone["areas"])] == alone["areas"]
    assert [e for e in both["elderships"] if "municipality" not in e] == alone["elderships"]
    for key in ("municipality", "stats", "warnings"):
        assert both[key] == alone[key]


def test_alytaus_ratc_municipalities_are_never_read(monkeypatch):
    # Their schedules come from Alytaus RATC; reading them here too would give their addresses
    # two sources.
    read = {name for m in svara.MUNICIPALITIES for name in m.spellings}
    assert not read & svara.FROM_ALYTAUS_RATC
    dataset, files, _ = build_all(monkeypatch)
    text = str(dataset) + str(files)
    for place in ("Jiezno", "Birštono", "Leipalingio"):
        assert place not in text


def test_a_municipality_that_cant_be_read_is_left_out(monkeypatch):
    relax(monkeypatch, max_skipped=0.5)
    kauno, kaisiadorys = svara.MUNICIPALITIES
    monkeypatch.setattr(svara, "MUNICIPALITIES", (kauno, replace(kaisiadorys, min_rows=100)))
    dataset, files, warnings = svara.build((CSV + KAISIADORYS).encode("utf-8"), NOVEMBER_21)
    # Kauno r. is published without it.
    assert "otherMunicipalities" not in dataset
    assert set(files) == {"ringaudu", "uzliedziu"}
    assert "Kaišiadorių r. left out: only 8 rows for Kaišiadorių r." in warnings


def test_one_day_of_the_month(monkeypatch):
    dataset, files, _ = build_all(monkeypatch)
    house = files["rumsiskiu"]["towns"]["Rusonių k."]["Topolių g."]["26"]
    (area,) = (dataset["areas"][i] for i in house)
    # The first Wednesday of every month.
    assert area["dates"][:4] == ["2026-11-04", "2026-12-02", "2027-01-06", "2027-02-03"]
    assert (area["nth"], area["weekday"]) == (1, 2)
    assert "every" not in area
    # One container emptied on the first Tuesday and the third Friday: both are pickups.
    stasiunai = files["ziezmariu-apylinkes"]["towns"]["Stasiūnų k."]["Ateities g."]["6"]
    assert dates_of(dataset, stasiunai)[2:6] == [
        "2026-12-01",
        "2026-12-18",
        "2027-01-05",
        "2027-01-15",
    ]


def test_several_days_a_week(monkeypatch):
    dataset, files, _ = build_all(monkeypatch)
    house = files["kaisiadoriu-miesto"]["towns"]["Kaišiadorių m."]["Gedimino g."]["92"]
    # Monday, Wednesday and Friday: a weekly schedule each, shared with other containers.
    assert len(house) == 3
    assert all(dataset["areas"][i]["every"] == 7 for i in house)
    assert [d for d in dates_of(dataset, house) if "2026-11-23" <= d <= "2026-11-29"] == [
        "2026-11-23",
        "2026-11-25",
        "2026-11-27",
    ]


def test_a_next_date_the_rule_doesnt_have_is_not_used(monkeypatch):
    # 9 December is the second Wednesday.
    row = "Kaišiadorių r. sav.;Rumšiškių sen.;Rusonių k.;Topolių g.;28;C-1;2026-12-09;kiekvieną mėnesio dieną, kiekvieną mėnesį, pirmąjį mėnesyje trečiadienį;Mišrios komunalinės\n"
    _, files, warnings = build_all(monkeypatch, csv=CSV + KAISIADORYS + row)
    assert "28" not in files["rumsiskiu"]["towns"]["Rusonių k."]["Topolių g."]
    assert any(w.startswith("Kaišiadorių r.: 1 rows skipped: frequency") for w in warnings)


def test_a_town_written_with_its_former_type(monkeypatch):
    from schedule_pipeline.registry import Registry, Settlement, Street

    # The register has the town Žiežmariai (its own eldership), and a village and a homestead
    # of that name in Žiežmarių apylinkės sen.
    registry = Registry(
        [
            Settlement(1, "Žiežmariai", "Žiežmarių", "m.", "Žiežmarių", [
                Street(11, "Vytauto", "g."),
                Street(12, "Kauno", "g."),
                Street(13, "Tvenkinių", "aklg."),
            ]),
            Settlement(2, "Žiežmariai", "Žiežmarių", "k.", "Žiežmarių apylinkės", [
                Street(21, "Linų", "g."),
            ]),
            Settlement(3, "Žiežmariai", "Žiežmarių", "vs.", "Žiežmarių apylinkės"),
        ]
    )  # fmt: skip

    def row(eldership, town, street, house):
        return f"Kaišiadorių r. sav.;{eldership};{town};{street};{house};C;2026-12-03;kas 14 dienų;Mišrios komunalinės\n"

    # Most of the town is "Žiežmarių mstl." under the eldership around it, with one house of
    # a street the town doesn't have.
    rows = [
        row("Žiežmarių apylinkės sen.", "Žiežmarių mstl.", "Vytauto g.", n) for n in range(1, 10)
    ]
    rows.append(row("Žiežmarių apylinkės sen.", "Žiežmarių mstl.", "Tvenkinių akl. g.", 1))
    rows.append(row("Žiežmarių apylinkės sen.", "Žiežmarių mstl.", "Linų g.", 1))
    rows.append(row("Žiežmarių sen.", "Žiežmarių m.", "Kauno g.", 2))
    dataset, files, _ = build_all(
        monkeypatch, csv=CSV + "".join(rows), registries={"kaisiadorys": registry}
    )
    # One town, in its own eldership, found by its name in the register.
    entry = next(e for e in dataset["elderships"] if e["name"] == "Žiežmarių sen.")
    assert entry["towns"] == ["Žiežmarių mstl."]
    assert entry["registerNames"] == {"Žiežmarių mstl.": "Žiežmariai"}
    town = files["ziezmariu"]["towns"]["Žiežmarių mstl."]
    assert list(town) == ["Kauno g.", "Linų g.", "Tvenkinių akl. g.", "Vytauto g."]
    assert files["ziezmariu"]["aliases"]["Žiežmarių m."]["Kauno g."]["2"][1] == "Žiežmarių mstl."
    stats = dataset["otherMunicipalities"][0]["stats"]["merged"]
    assert (stats["towns"], stats["townsMovedToTheirEldership"]) == (1, 1)


def test_streets_with_two_types():
    from schedule_pipeline.registry import Settlement, Street

    assert svara.split_type("Liepų al. g.", svara.STREET_TYPES) == ("liepu", "al.")
    assert svara.split_type("Tvenkinių aklg.", svara.STREET_TYPES) == ("tvenkiniu", "aklg.")
    pakertai = Settlement(1, "Pakertai", "Pakertų", "k.", "Žiežmarių apylinkės", [
        Street(11, "Liepų", "al."),
        Street(12, "Liepų", "g."),
    ])  # fmt: skip
    assert svara.find_street(pakertai, "Liepų al. g.") == 11


def test_the_location_tables_of_several_municipalities_are_joined():
    kauno = {
        "generatedAt": "now",
        "source": "AR",
        "places": [["ringaudu", "Ringaudų sen.", "Karkiškių k.", "Ganyklų g."]],
        "points": [[5485000, 2375000, 0, "2"]],
    }
    kaisiadorys = {
        "generatedAt": "now",
        "source": "AR",
        "places": [["ziezmariu", "Žiežmarių sen.", "Žiežmarių mstl.", "Vytauto g."]],
        "points": [[5480000, 2445000, 0, "1"]],
    }
    table = svara.join_tables([kauno, kaisiadorys])
    # Kauno r.'s places keep their index; the points stay sorted by latitude.
    assert table["places"] == kauno["places"] + kaisiadorys["places"]
    assert table["points"] == [[5480000, 2445000, 1, "1"], [5485000, 2375000, 0, "2"]]

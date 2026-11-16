# ruff: noqa: E501 (rows of the source file are long)
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


@pytest.fixture
def built(monkeypatch):
    monkeypatch.setattr(svara, "MIN_ROWS", 1)
    monkeypatch.setattr(svara, "MIN_ADDRESSES", 1)
    monkeypatch.setattr(svara, "MAX_SKIPPED", 0.5)
    return svara.build(("﻿" + CSV).encode("utf-8"), TODAY)


def test_parse_rule():
    assert parse_rule("kas 14 dienų") == Rule(14)
    assert parse_rule("kas 21 dieną") == Rule(21)
    assert parse_rule("kas 7 dienas") == Rule(7)
    assert parse_rule("kas 28 dienas, balandį, gegužę, lapkritį") == Rule(28, (4, 5, 11))
    assert parse_rule("kiekvieną mėnesio dieną, kiekvieną mėnesį, penktadienį") == Rule(7)
    assert (
        parse_rule("kiekvieną mėnesio dieną, kiekvieną mėnesį, trečiąjį mėnesyje trečiadienį")
        is None
    )
    assert parse_rule("kas 14 dienų, kartais") is None
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
    monkeypatch.setattr(svara, "MIN_ROWS", 1)
    monkeypatch.setattr(svara, "MIN_ADDRESSES", 1)
    monkeypatch.setattr(svara, "MAX_SKIPPED", 0.5)
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

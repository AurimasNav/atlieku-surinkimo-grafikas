"""Checks the location matching against hand-verified cases from the real schedules."""

from datetime import date

import pytest
from test_parsers import REGISTRY, all_sources

from schedule_pipeline.build import build_dataset
from schedule_pipeline.locations import Index, _near
from schedule_pipeline.registry import fold


@pytest.fixture(scope="module")
def dataset():
    data, _ = build_dataset(all_sources(), REGISTRY, today=date(2026, 10, 11), keep_days=31)
    return data


@pytest.fixture(scope="module")
def find(dataset):
    areas = {a["id"]: a for a in dataset["areas"]}
    locations = {(loc["name"], loc["district"]): loc for loc in dataset["locations"]}

    def lookup(name, district):
        loc = locations[(name, district)]
        rows = {
            kind: areas[r["area"]]["name"] if "area" in r else r
            for kind, r in loc.get("schedule", {}).items()
        }
        return loc, rows

    return lookup


def test_simple_village_links_all_three_schedules(find):
    loc, rows = find("Aleksandravas", "Avižienių")
    assert rows["household"] == "Aleksandravas"
    assert "Aleksandravo k." in rows["packaging"]
    assert "Aleksandravo k." in rows["glass"]
    assert "streets" not in loc  # no street question needed


def test_town_split_by_street(find):
    loc, rows = find("Avižieniai", "Avižienių")
    streets = dict(loc["streets"])
    akacijos = next(k for k, label in streets.items() if label.startswith("Akacijų"))
    durpiu = next(k for k, label in streets.items() if label.startswith("Durpių"))
    household = loc["schedule"]["household"]["streets"]
    # The two household rows for Avižieniai list Akacijų and Durpių streets separately.
    assert household[akacijos] != household[durpiu]
    assert len(household[akacijos]) == 1


def test_whole_district_rule_with_exceptions(find):
    # "Sužionių sen. kaimai iškyrus Pakryžės k., Veriškių k." covers other Sužionių villages
    # and not Pakryžė, which another row lists explicitly.
    _, sužionys = find("Sužionys", "Sužionių")
    _, pakryze = find("Pakryžė", "Sužionių")
    assert "iškyrus Pakryžės" in sužionys["glass"]
    assert "Sužionių sen. kaimai: Pakryžės k." in pakryze["glass"]


def test_numbered_settlements_share_a_row(find):
    # The schedule says "Akmena (k.)"; the register has "Akmena I" and "Akmena II".
    _, first = find("Akmena I", "Paberžės")
    _, second = find("Akmena II", "Paberžės")
    assert first["household"] == second["household"] == "Akmena (k.)"


def test_village_missing_from_a_schedule_is_not_guessed(find):
    _, rows = find("Ažunerė", "Bezdonių")
    assert "household" in rows
    assert "packaging" not in rows and "glass" not in rows


def test_house_or_apartment_is_left_to_the_user(dataset, find):
    loc, _ = find("Maišiagala", "Maišiagalos")
    candidates = loc["schedule"]["household"]["candidates"]
    groups = {a["group"] for a in dataset["areas"] if a["id"] in candidates}
    assert groups == {"Individualūs namai", "Daugiabučiai namai"}


def test_only_served_districts_are_listed(dataset):
    districts = {loc["district"] for loc in dataset["locations"]}
    assert "Avižienių" in districts
    assert "Rudaminos" not in districts  # not served by this operator


def test_district_spellings():
    index = Index(REGISTRY)
    assert index.district("Sužionys") == "Sužionių"
    assert index.district("Nemenčinės mst.") == "Nemenčinės miesto"
    assert index.district("Bezdonių.") == "Bezdonių"


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("Kalikstiškiai", "Kalikstiškės", True),
        ("Mėlenai", "Mėleniai", True),
        ("Akmena", "Akmenėlė", False),
        ("Bajorai", "Bendoriai", False),
    ],
)
def test_near_names(a, b, expected):
    assert _near(fold(a), fold(b)) is expected

"""Kaišiadorių r.: the schedules of SĮ „Kaišiadorių paslaugos“, the JSON its page's plugin asks
for, and the places."""

import json
from datetime import date

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, kaisiadorys, regions, status
from schedule_pipeline.build import build_dataset
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 27)
PAGE = fixture("kaisiadorys/page.html")
DATA = fixture("kaisiadorys/data-2026.json")
REGISTRY = "kaisiadorys/registry-kaisiadoriu-r-2026-11-21.json"
AJAX = "https://www.kaisiadoriupaslaugos.lt/wp-admin/admin-ajax.php"


def empty(year):
    """The site's answer for a year without schedules (2027 on 27 November 2026)."""
    data = {"year": year, "wasteTypes": [], "locations": [], "schedules": []}
    return json.dumps({"success": True, "data": data}).encode()


def get(url):
    assert url == kaisiadorys.PAGE_URL
    return PAGE


def post(url, form):
    assert url == AJAX
    assert (form["action"], form["nonce"]) == ("tobalt_waste_get_data", "a83410b836")
    return DATA if form["year"] == "2026" else empty(int(form["year"]))


@pytest.fixture(scope="module")
def built():
    waits = []
    files, warnings = kaisiadorys.download(TODAY, 31, get, post, waits.append)
    registry = Registry.load(FIXTURES / REGISTRY)
    data, more = build_dataset(files, registry, TODAY, 31, kaisiadorys.SOURCE)
    return files, waits, data, warnings + more


def place(data, name, kind=None, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and kind in (None, loc["type"])
        and district in (None, loc["district"])
    )


def rows(data, location, waste="household"):
    schedule = location["schedule"][waste]
    ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    by_id = {a["id"]: a for a in data["areas"]}
    return [by_id[i]["name"] for i in ids]


# --- the site ----------------------------------------------------------------------


def test_the_pages_settings():
    tag = kaisiadorys.read_tag(PAGE.decode("utf-8"))
    assert (tag.ajax_url, tag.nonce) == (AJAX, "a83410b836")
    with pytest.raises(ValueError, match="no tobaltWaste settings"):
        kaisiadorys.read_tag("<html></html>")


def test_this_year_and_the_next_are_read(built):
    files, waits, _, _ = built
    # 2027 has no schedules yet: left out. One request every 10 seconds (robots.txt).
    assert [f.year for f, _ in files] == [2026]
    assert waits == [10, 10]
    assert kaisiadorys.years(TODAY, 31) == [2026, 2027]
    # In January, last year too, while its dates are kept.
    assert kaisiadorys.years(date(2027, 1, 20), 31) == [2026, 2027, 2028]
    with pytest.raises(build.ValidationError, match="no schedules for 2026, 2027"):
        kaisiadorys.download(TODAY, 31, get, lambda url, form: empty(int(form["year"])), print)


def test_answers_that_are_not_the_years_data_fail():
    year = kaisiadorys.Year(2026, kaisiadorys.PAGE_URL)
    with pytest.raises(ValueError, match="not a successful answer"):
        kaisiadorys.parse_file(year, b'{"success": false, "data": "Invalid nonce"}')
    with pytest.raises(ValueError, match="the answer is of 2027"):
        kaisiadorys.parse_file(year, empty(2027))
    data = json.loads(DATA)
    data["data"]["schedules"]["1125"]["1"]["2"] = [30]
    with pytest.raises(ValueError, match="Navasodų k.: day 30 of 2026-2"):
        kaisiadorys.parse_file(year, json.dumps(data).encode())


def test_the_rows():
    result = kaisiadorys.parse_file(kaisiadorys.Year(2026, kaisiadorys.PAGE_URL), DATA)
    kinds = {}
    for area in result.areas:
        kinds[area.kind] = kinds.get(area.kind, 0) + 1
    # 392 locations with a schedule, 5 of them cemeteries and the shared containers.
    assert kinds == {"household": 387, "packaging": 385, "glass": 385, "green": 195}
    assert result.warnings == [
        "rows that aren't homes left out: Nemaitonių kapinės (Nemaitonių sen.); Palomenės "
        "kapinės (Palomenės sen.); Paparčių kapinės (Paparčių sen.); Pusiau požeminiai mišrių "
        "atliekų konteineriai; Žaslių kapinės (Žaslių sen.)"
    ]
    navasodai = [a for a in result.areas if a.name == "Navasodų k."]
    assert {a.kind for a in navasodai} == {"household", "packaging", "glass", "green"}
    household = next(a for a in navasodai if a.kind == "household")
    assert household.district == "Kaišiadorių apylinkės"
    assert household.provider == "kaisiadorys"
    assert max(household.dates) == date(2026, 12, 24)
    # A waste type of another name is left out, with a warning.
    data = json.loads(DATA)
    data["data"]["wasteTypes"].append({"id": 9, "name": "Didžiosios atliekos"})
    data["data"]["schedules"]["1125"]["9"] = {"12": [1]}
    result = kaisiadorys.parse_file(
        kaisiadorys.Year(2026, kaisiadorys.PAGE_URL), json.dumps(data).encode()
    )
    assert result.warnings[0] == "waste type „Didžiosios atliekos“ isn't read"


# --- the places --------------------------------------------------------------------


def test_counts(built):
    _, _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 391
    assert (stats["household.single"], stats["household.ambiguous"]) == (275, 1)
    assert (stats["household.byStreet"], stats["household.none"]) == (1, 114)
    assert stats["unmatchedRows"] == 37
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 380, "packaging": 378, "glass": 378, "green": 188}
    assert data["coverage"]["household"] == {"from": "2026-10-27", "to": "2026-12-31"}
    assert data["coverage"]["green"] == {"from": "2026-12-16", "to": "2026-12-24"}
    unlinked = sorted({w.split(": ", 2)[2] for w in warnings if w.startswith("not linked")})
    assert unlinked == [
        "Benkūnų k.",
        "Dumsių k.",
        "Mičiūnų k.",
        "Paramotės Krušonys",
        "Prozariškių k.",
        "S. Gegužinės k.",
        'S/B „BALTASIS BERŽELIS"',
        'S/B „GIRELĖ"',
        'S/B „SODŽIUS"',
        "SB „Marios“",
        "SB „Šilas“.",
        "Vladiškių g.",
    ]


def test_villages_towns_and_typos(built):
    _, _, data, _ = built
    navasodai = place(data, "Navasodai")
    assert (navasodai["district"], navasodai["provider"]) == (
        "Kaišiadorių apylinkės",
        "kaisiadorys",
    )
    for kind in ("household", "packaging", "glass", "green"):
        assert rows(data, navasodai, kind) == ["Navasodų k."]
    assert rows(data, place(data, "Žiežmariai", "m.")) == ["Žiežmarių miestas"]
    assert rows(data, place(data, "Rumšiškės", "mstl.")) == ["Rumšiškių miestelis"]
    # Typos and the nominative: one village of the eldership that close. "Vaidžionys" and
    # "Vadžionių k." have the same dates: one of them.
    assert rows(data, place(data, "Vaidžionys")) == ["Vadžionių k."]
    assert rows(data, place(data, "Anuprava"), "packaging") == ["Anupravos k"]
    assert rows(data, place(data, "Anglininkai")) == ["Anglininkų k."]
    # "Mankuviškių k.": both numbered villages; Mankuviškės I also has a row of its own.
    assert rows(data, place(data, "Mankuviškės II")) == ["Mankuviškių k."]
    assert sorted(rows(data, place(data, "Mankuviškės I"))) == [
        "Mankuviškių I k.",
        "Mankuviškių k.",
    ]
    # Užtakai: Nedėjos g. has a row of its own.
    uztakai = place(data, "Užtakai")["schedule"]["household"]
    assert len(uztakai["streets"]) == 1 and len(uztakai["candidates"]) == 2


def test_the_streets_of_kaisiadorys(built):
    _, _, data, _ = built
    town = place(data, "Kaišiadorys", "m.")
    assert town["district"] == "Kaišiadorių miesto"
    # Every street's mixed and green waste have the town's dates: no street to ask for.
    for kind in ("household", "green"):
        assert town["schedule"][kind] == {"area": town["schedule"][kind]["area"]}
        assert rows(data, town, kind) == ["Kaišiadorių miestas"]
    # Packaging: 18 streets have other dates; glass: 74.
    assert len(town["schedule"]["packaging"]["streets"]) == 18
    assert len(town["schedule"]["glass"]["streets"]) == 74
    names = dict(town["streets"])
    by_id = {a["id"]: a for a in data["areas"]}
    zvejy = next(k for k, v in names.items() if v == "Žvejų g.")
    assert [by_id[i]["name"] for i in town["schedule"]["packaging"]["streets"][zvejy]] == [
        "Žvejų g."
    ]


def test_a_place_named_by_two_rows_is_reported(built):
    _, _, _, warnings = built
    assert (
        "Anglininkai k. (Kruonio sen.) is named by 2 glass rows: Anglinikų k.; Anglininkų k."
        in (warnings)
    )
    assert sum(1 for w in warnings if " is named by " in w) == 11


# --- the folder --------------------------------------------------------------------


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kaisiadorys, "_get", get)
    monkeypatch.setattr(kaisiadorys, "_post", post)
    monkeypatch.setattr(kaisiadorys, "_wait", lambda seconds: None)
    monkeypatch.setattr(kaisiadorys.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(kaisiadorys.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "kaisiadoriu-r"
    assert kaisiadorys.main(["--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    (provider,) = data["providers"]
    assert {key: provider[key] for key in ("id", "name", "url")} == {
        "id": "kaisiadorys",
        "name": "SĮ „Kaišiadorių paslaugos“",
        "url": "https://www.kaisiadoriupaslaugos.lt/kaisiadoriu-atlieku-isvezimo-grafikai/",
    }
    assert regions.region(tmp_path, out) == {
        "path": "kaisiadoriu-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["kaisiadorys"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="kaisiadorys"}' in text

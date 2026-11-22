"""Ukmergės r.: the municipality's page, the PDFs of Ukmergės autobusų parkas, their routes, the
two periods a year and the published folder."""

import json
from collections import Counter
from datetime import date

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, regions, snapshot, status, ukmerge
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "ukmerge" / "registry-ukmerges-r-2026-11-21.json")
TODAY = date(2026, 11, 21)
UPLOADS = "https://www.ukmerge.lt/uploads/Documents/"
# The page's files, newest first as it links them, and their copies in fixtures/ukmerge/.
COPIES = {
    "2026_m._birelio-gruodio_mn._Ukmergs_miesto_gyventoj_komunalini_ir_pakuoi_atliek_surinkimo"
    "_grafikas.pdf": "miestas-2026-h2.pdf",
    "2026_m._birelio-gruodio_mn._Ukmergs_rajono_gyvnetoj_komunalini_ir_pakuoi_atliek_surinkimo"
    "_grafikas.pdf": "rajonas-2026-h2.pdf",
    "2026_m._sausio-gegus_mn._Ukmerges_miesto_komunalini_ir_pakuoi_atliek_surinkimo_grafikas"
    "_(002).pdf": "miestas-2026-h1.pdf",
    "2026_m._sausio-gegus_mn._Ukmergs_rajono_gyventoj_komunalini_ir_pakuoi_atliek_surinkimo"
    "_grafikas.pdf": "rajonas-2026-h1.pdf",
}


def page_files():
    return ukmerge.find_files(fixture("ukmerge/page.html").decode("utf-8"))


TOWN_H2, DISTRICT_H2, TOWN_H1, DISTRICT_H1 = page_files()[0]


def content(file):
    return fixture(f"ukmerge/{COPIES[file.file_name]}")


def parsed(file):
    return ukmerge.parse_file(file, content(file))


@pytest.fixture(scope="module")
def part():
    files = [(f, content(f)) for f in (TOWN_H2, DISTRICT_H2)]
    return build_dataset(files, REGISTRY, TODAY, 31, ukmerge.SOURCE)


def place(data, name, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name and district in (None, loc["district"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def route(data, area_id):
    """The route's name: "Želvos maršrutas: ..." is Želvos."""
    return row(data, area_id)["name"].split(" maršrutas:")[0]


def routes_of(data, name, kind, street=None, district=None):
    """The routes of a place, or of one of its streets."""
    schedule = place(data, name, district)["schedule"][kind]
    if street is None:
        ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    else:
        location = place(data, name, district)
        key = next(k for k, label in location["streets"] if label == street)
        ids = schedule["streets"][key]
    return sorted(route(data, i) for i in ids)


def by_route(result, name, kind="household"):
    return next(
        a for a in result.areas if a.kind == kind and a.name.startswith(f"{name} maršrutas:")
    )


# --- the page ----------------------------------------------------------------


def test_finds_the_files_by_their_links():
    files, warnings = page_files()
    found = [(f.group, f.kind, f.year, f.months, COPIES[f.file_name]) for f in files]
    assert found == [
        ("town", "household", 2026, (6, 12), "miestas-2026-h2.pdf"),
        ("district", "household", 2026, (6, 12), "rajonas-2026-h2.pdf"),
        ("town", "household", 2026, (1, 5), "miestas-2026-h1.pdf"),
        ("district", "household", 2026, (1, 5), "rajonas-2026-h1.pdf"),
    ]
    assert warnings == []
    assert TOWN_H2.url == f"{UPLOADS}document_740/{TOWN_H2.file_name}"
    assert (TOWN_H1.start, TOWN_H1.end) == (date(2026, 1, 1), date(2026, 5, 31))
    assert (TOWN_H2.start, TOWN_H2.end) == (date(2026, 6, 1), date(2026, 12, 31))


def file(group, year, months, name=None):
    name = name or f"{group}-{year}-{months[0]}-{months[1]}.pdf"
    return ukmerge.ScheduleFile(
        "household", f"{UPLOADS}{name}", name, group=group, year=year, months=months
    )


def periods(files):
    return [(f.group, f.year, f.months) for f in files]


def test_reads_the_files_with_dates_still_to_publish():
    files, _ = page_files()
    selected, warnings = ukmerge.select_files(files, TODAY)
    assert periods(selected) == [("town", 2026, (6, 12)), ("district", 2026, (6, 12))]
    assert warnings == []
    # In June, May's dates are still published: both periods are read.
    selected, _ = ukmerge.select_files(files, date(2026, 6, 20))
    assert periods(selected) == [
        ("town", 2026, (1, 5)),
        ("town", 2026, (6, 12)),
        ("district", 2026, (1, 5)),
        ("district", 2026, (6, 12)),
    ]


def test_the_next_period_is_read_when_it_is_linked():
    files = [
        file("town", 2027, (1, 5)),
        file("district", 2027, (1, 5)),
        file("town", 2026, (6, 12)),
        file("district", 2026, (6, 12)),
    ]
    selected, _ = ukmerge.select_files(files, date(2026, 12, 18))
    assert periods(selected) == [
        ("town", 2026, (6, 12)),
        ("town", 2027, (1, 5)),
        ("district", 2026, (6, 12)),
        ("district", 2027, (1, 5)),
    ]
    # Once December's dates are older than a month, only the new period.
    selected, _ = ukmerge.select_files(files, date(2027, 2, 2))
    assert periods(selected) == [("town", 2027, (1, 5)), ("district", 2027, (1, 5))]


def test_a_late_period_keeps_the_last_one():
    files, _ = page_files()
    selected, _ = ukmerge.select_files(files, date(2027, 2, 15))
    assert periods(selected) == [("town", 2026, (6, 12)), ("district", 2026, (6, 12))]


def test_of_two_files_for_one_period_the_newest_on_top_is_read():
    newer = file("town", 2026, (6, 12), "patikslintas.pdf")
    files, _ = page_files()
    selected, warnings = ukmerge.select_files([newer, *files], TODAY)
    assert [f.file_name for f in selected][0] == "patikslintas.pdf"
    assert warnings == [
        f"{TOWN_H2.file_name}: not read, patikslintas.pdf is a newer schedule of the town for "
        "2026-06-01 - 2026-12-31"
    ]


def test_a_page_without_the_district_fails():
    files, _ = page_files()
    with pytest.raises(ValidationError, match="no schedule of the district"):
        ukmerge.select_files([f for f in files if f.group == "town"], TODAY)


def test_links_of_other_schedules_are_reported():
    html = (
        '<a href="/a.pdf">2026 m. didelių gabaritų atliekų surinkimo grafikas</a>'
        '<a href="/b.pdf">Ukmergės miesto komunalinių atliekų surinkimo grafikas</a>'
        '<a href="/c.pdf">Rūšiavimo taisyklės</a>'
    )
    files, warnings = ukmerge.find_files(html)
    assert files == []
    assert warnings == [
        "a.pdf ('2026 m. didelių gabaritų atliekų surinkimo grafikas'): a schedule of no kind "
        "we read",
        "b.pdf ('Ukmergės miesto komunalinių atliekų surinkimo grafikas'): no year in its link "
        "or name; not read",
    ]


# --- the tables ------------------------------------------------------------------


DISTRICT_ROUTES = [
    "Želvos",
    "Tulpiakiemio",
    "Lyduokių",
    "Pabaisko",
    "Deltuvos",
    "Veprių",
    "Šešuolių",
    "Šaukavos",
    "Kazliškių-Labeikių",
    "Taujėnų",
    "Žemaitkiemio",
    "Vidiškių",
    "Pivonijos",
    "Siesikų",
]
TOWN_ROUTES = ["Gėlyno", "Užupio", "Krekšlių", "Šlapių", "Dukstynos"]


def names(result, kind="household"):
    return [a.name.split(" maršrutas:")[0] for a in result.areas if a.kind == kind]


def test_the_district_june_to_december():
    result = parsed(DISTRICT_H2)
    for kind in ("household", "packaging", "glass"):
        assert names(result, kind) == DISTRICT_ROUTES
    zelva = by_route(result, "Želvos")
    assert zelva.district == "Ukmergės r." and zelva.provider == "ukmerge"
    assert zelva.name.startswith(
        "Želvos maršrutas: Šešuolių sen.: Dvareliškių k. Želvos sen.: Adomiškio k., Bajorų k.,"
    )
    assert zelva.name.endswith("Želvos mstl., Žvynėnų k.")
    assert (min(zelva.dates), max(zelva.dates), len(zelva.dates)) == (
        date(2026, 6, 9),
        date(2026, 12, 22),
        15,
    )
    assert zelva.weekday == "Antradienis"
    assert sorted(by_route(result, "Želvos", "packaging").dates) == [
        date(2026, 6, 30),
        date(2026, 8, 11),
        date(2026, 9, 22),
        date(2026, 11, 3),
        date(2026, 12, 15),
    ]
    assert sorted(by_route(result, "Želvos", "glass").dates) == [
        date(2026, 7, 21),
        date(2026, 11, 24),
    ]
    # Christmas Eve's pickup is on 29 December: no single weekday.
    lyduokiai = by_route(result, "Lyduokių")
    assert max(lyduokiai.dates) == date(2026, 12, 29) and lyduokiai.weekday is None
    # The name written on two lines.
    assert by_route(result, "Kazliškių-Labeikių").name.startswith(
        "Kazliškių-Labeikių maršrutas: Šešuolių sen.: Bratnavos k., Butkūnų k., Jonelių k., "
        "Labeikių., "
    )
    # "Žalgirių k." doesn't fit the Deltuvos route's cell: the PDF writes it over the first line
    # of the next one's.
    assert by_route(result, "Deltuvos").name.endswith("Statikų k., Žalgirių k.")
    assert by_route(result, "Veprių").name.startswith(
        "Veprių maršrutas: Deltuvos sen.: Bernotiškių k., "
    )


def test_the_district_january_to_may():
    result = parsed(DISTRICT_H1)
    assert names(result) == DISTRICT_ROUTES
    zelva = by_route(result, "Želvos")
    assert sorted(zelva.dates)[:3] == [date(2026, 1, 6), date(2026, 1, 20), date(2026, 2, 3)]
    assert max(zelva.dates) == date(2026, 5, 26)
    assert by_route(result, "Želvos", "glass").dates == {date(2026, 3, 17)}
    # The Šešuolių route's last line, hidden over the Šaukavos route's: the same places as in
    # June-December.
    assert by_route(result, "Šešuolių").name.endswith(
        "Užupėnų k. Pivonijos sen.: Dastainiškio k., Stanislavuvkos k."
    )
    assert by_route(result, "Šaukavos").name.startswith(
        "Šaukavos maršrutas: Vidiškių sen.: Bimūnų k., "
    )
    assert (
        by_route(result, "Šešuolių").name.split(":", 1)[1]
        == (by_route(parsed(DISTRICT_H2), "Šešuolių").name.split(":", 1)[1])
    )


def test_the_town_june_to_december():
    result = parsed(TOWN_H2)
    for kind in ("household", "packaging", "glass"):
        assert names(result, kind) == TOWN_ROUTES
    gelynas = by_route(result, "Gėlyno")
    assert gelynas.name.startswith(
        "Gėlyno maršrutas: UKMERGĖS MIESTO SEN.: Aguonų g., Akloji g., Alytaus g.,"
    )
    assert gelynas.name.endswith(
        "Žilvičių g. PABAISKO SEN. Varinės k.: Daigyno g., Girininkų g., Kosmonautų g., "
        "Medžiotojų g., Šaltinių g., Varinės g."
    )
    assert (min(gelynas.dates), max(gelynas.dates), len(gelynas.dates)) == (
        date(2026, 6, 8),
        date(2026, 12, 21),
        15,
    )
    assert gelynas.weekday == "Pirmadienis"
    assert sorted(by_route(result, "Gėlyno", "glass").dates) == [
        date(2026, 8, 31),
        date(2026, 11, 30),
    ]
    assert by_route(result, "Dukstynos", "packaging").dates >= {
        date(2026, 6, 5),
        date(2026, 6, 26),
        date(2026, 12, 11),
    }


def test_the_town_january_to_may():
    result = parsed(TOWN_H1)
    assert names(result) == TOWN_ROUTES
    # Glass once: 27 April to 1 May, a route a day.
    assert [min(by_route(result, r, "glass").dates) for r in TOWN_ROUTES] == [
        date(2026, 4, 27),
        date(2026, 4, 28),
        date(2026, 4, 29),
        date(2026, 4, 30),
        date(2026, 5, 1),
    ]
    assert sorted(by_route(result, "Šlapių").dates)[6:9] == [
        date(2026, 4, 1),
        date(2026, 4, 15),
        date(2026, 4, 29),
    ]


def test_a_link_for_other_months_fails():
    other = file("district", 2026, (1, 5), DISTRICT_H2.file_name)
    with pytest.raises(ValueError, match=r"months \[6, 7, 8, 9, 10, 11, 12\], the link says 1-5"):
        ukmerge.parse_file(other, content(DISTRICT_H2))


def test_a_title_of_another_year_fails():
    other = file("district", 2027, (6, 12), DISTRICT_H2.file_name)
    with pytest.raises(ValueError, match="isn't of the district in 2027"):
        ukmerge.parse_file(other, content(DISTRICT_H2))


def test_the_town_s_file_linked_as_the_district_s_fails():
    other = file("district", 2026, (6, 12), TOWN_H2.file_name)
    with pytest.raises(ValueError):
        ukmerge.parse_file(other, content(TOWN_H2))


def test_dates_off_their_weekday_fail(monkeypatch):
    monkeypatch.setattr(ukmerge, "SAME_WEEKDAY", 1.01)
    with pytest.raises(ValueError, match="aren't on one working day"):
        parsed(DISTRICT_H2)


def test_too_few_routes_fail(monkeypatch):
    monkeypatch.setitem(ukmerge.MIN_ROUTES, "town", 6)
    with pytest.raises(ValueError, match=r"only 5 routes \(expected 6\)"):
        parsed(TOWN_H2)


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("Mišrios komunalinės", "household"),
        ("Mišrių komunalinių atliekų", "household"),
        ("Popieriaus, plastiko", "packaging"),
        ("Plastiko, popieriaus pakuotės", "packaging"),
        ("Stiklo", "glass"),
        ("Stiklo pakuotės", "glass"),
    ],
)
def test_the_rows_waste_types(label, kind):
    assert ukmerge._row_kind(label, "here") == kind


@pytest.mark.parametrize("label", ["Maisto atliekos", "Didelių gabaritų atliekos"])
def test_rows_of_other_waste_types_fail(label):
    with pytest.raises(ValueError, match="no waste type"):
        ukmerge._row_kind(label, "here")


# --- the places ------------------------------------------------------------------


def test_counts(part):
    data, warnings = part
    assert len(data["areas"]) == 57
    stats = data["matching"]
    for kind in ("household", "packaging", "glass"):
        assert [stats[f"{kind}.{s}"] for s in ("single", "byStreet", "ambiguous", "none")] == [
            362,
            1,
            1,
            192,
        ]
    assert len(data["locations"]) == 556


def test_settlements_without_mixed_waste(part):
    data, _ = part
    points, _ = snapshot.load_points(snapshot.UKMERGE_ADDRESSES_FILE)
    addresses = Counter(f"g{p.settlement}" for p in points)
    without = Counter(
        {
            (loc["name"], loc["district"]): addresses[loc["id"]]
            for loc in data["locations"]
            if "household" not in loc.get("schedule", {})
        }
    )
    # Villages no file names, most without addresses: 406 of 17,603 addresses in November 2026.
    assert len(without) == 192
    assert sum(without.values()) == 406
    assert without.most_common(3) == [
        (("Algirdai", "Deltuvos"), 15),
        (("Slabada", "Veprių"), 15),
        (("Diržiai", "Deltuvos"), 14),
    ]
    # "Veprių mstl.": the town, not the village of its name.
    assert without[("Vepriai", "Veprių")] == 13


def test_acceptance_examples(part):
    data, _ = part
    # Adomiškis (Želvos sen.), "Želvos sen.: Adomiškio k., ...": the Želvos route, every other
    # Tuesday, 9 June -> 22 December 2026 in the file.
    assert routes_of(data, "Adomiškis", "household") == ["Želvos"]
    zelva = by_route(parsed(DISTRICT_H2), "Želvos")
    assert (min(zelva.dates), max(zelva.dates)) == (date(2026, 6, 9), date(2026, 12, 22))
    # Taujėnai (mstl.): the Taujėnų route, 4 June -> 17 December 2026 on Thursdays.
    assert routes_of(data, "Taujėnai", "household", district="Taujėnų") == ["Taujėnų"]
    taujenai = by_route(parsed(DISTRICT_H2), "Taujėnų")
    assert (min(taujenai.dates), max(taujenai.dates)) == (date(2026, 6, 4), date(2026, 12, 17))


def test_the_streets_of_the_town(part):
    data, _ = part
    for street, expected in (
        ("Aguonų g.", ["Gėlyno"]),
        ("Antakalnio g.", ["Užupio"]),
        ("Krekšlių g.", ["Krekšlių"]),
        ("Kauno g.", ["Šlapių"]),
        ("Vytauto g.", ["Dukstynos"]),
        ("A. Vienuolio-Žukausko g.", ["Krekšlių"]),
        ("Koklių Fabriko g.", ["Užupio"]),
        ("Anykščių skg.", ["Dukstynos"]),
        # "Ramybės skg.": the register has only Ramybės g.
        ("Ramybės g.", ["Dukstynos"]),
    ):
        for kind in ("household", "packaging", "glass"):
            assert routes_of(data, "Ukmergė", kind, street) == expected, street
    # Streets split by house numbers ("Vilniaus g. (nelyginiai nuo 35 iki 113)"): no route has
    # the whole street, so the app offers the routes of its parts and the town's others.
    for street in ("Vilniaus g.", "Nuotekų g.", "Šlaitų g."):
        assert routes_of(data, "Ukmergė", "household", street) == sorted(TOWN_ROUTES)


def test_streets_no_route_names_are_left_to_the_app(part):
    data, _ = part
    town = place(data, "Ukmergė")
    named = town["schedule"]["household"]["streets"]
    assert len(named) == 166
    unnamed = [label for key, label in town["streets"] if key not in named]
    assert len(unnamed) == 86
    # Apartment buildings' streets and new streets of houses: the files say nothing of them.
    assert {"Dariaus ir Girėno g.", "Serbentų g.", "Kęstučio a.", "Anykščių g."} <= set(unnamed)
    assert "none" not in town["schedule"]["household"]


def test_villages_with_some_streets(part):
    data, _ = part
    # "PABAISKO SEN. Varinės k.: Daigyno g., ...": the town's Gėlyno route, the only one that
    # names Varinė, so for its other streets too.
    assert routes_of(data, "Varinė", "household") == ["Gėlyno"]
    # "Vaitkūnų k. (Sodžiaus g.)": no other route names Vaitkūnai.
    assert routes_of(data, "Vaitkūnai", "household") == ["Pabaisko"]


def test_villages_of_one_name(part):
    data, _ = part
    for district, expected in (
        ("Šešuolių", ["Kazliškių-Labeikių"]),
        ("Lyduokių", ["Lyduokių"]),
        ("Pabaisko", ["Pabaisko"]),
    ):
        assert routes_of(data, "Slabada", "household", district=district) == expected
    assert routes_of(data, "Bernotiškiai", "household", district="Deltuvos") == ["Veprių"]
    assert routes_of(data, "Bernotiškiai", "household", district="Vidiškių") == ["Vidiškių"]
    assert routes_of(data, "Kopūstėliai", "glass", district="Žemaitkiemio") == ["Žemaitkiemio"]
    # "Lelikonių k.": the village, not the farmstead (vs.) of its name.
    lelikoniai = {loc["type"]: loc for loc in data["locations"] if loc["name"] == "Lelikoniai"}
    assert route(data, lelikoniai["k."]["schedule"]["household"]["area"]) == "Želvos"
    assert "schedule" not in lelikoniai["vs."]
    # Rasališkiai is in two routes: the app asks.
    assert routes_of(data, "Rasališkiai", "household") == ["Kazliškių-Labeikių", "Želvos"]


def test_names_written_otherwise(part):
    data, _ = part
    for name, district, expected in (
        ("Labeikiai", "Šešuolių", "Kazliškių-Labeikių"),  # "Labeikių."
        ("Šlapių Priemiestis", "Vidiškių", "Šaukavos"),
        ("Vaisgėliškis", "Pivonijos", "Pivonijos"),  # "Vaizgėliškio vs."
        ("Dainiškis", "Želvos", "Želvos"),  # "Dainiškio k.", a farmstead (vs.)
        ("Kryžiauka", "Deltuvos", "Siesikų"),
        ("Antakalnis III", "Pivonijos", "Pivonijos"),
        ("Urnėžiai I", "Pivonijos", "Pivonijos"),
        ("Sarapai", "Deltuvos", "Deltuvos"),  # 'SB "Vienybė" Sarapų k.'
    ):
        assert routes_of(data, name, "household", district=district) == [expected], name


def test_warnings(part):
    _, warnings = part
    unknown = [
        "Želvos sen.: Deferencijos k.",
        "Siesikų sen.: Dirvonų k.",
        "Lyduokių sen.: SB „Pušelė“",
        "Lyduokių sen.: SB „Šilas“",
        'Deltuvos sen.: SB "Armona"',
        'Deltuvos sen.: SB "Vienybė"',
        "Deltuvos sen.: Tabalos k.",
    ]
    expected = [
        f"not a settlement or a street: {kind}: {place}"
        for place in unknown
        for kind in ("household", "packaging", "glass")
    ]
    assert sorted(warnings) == sorted(expected)


# --- the periods -----------------------------------------------------------------


def shifted(result, years):
    """The routes of a file, a year later: another period's file."""
    return ParseResult(
        [
            Area(
                a.kind,
                a.name,
                a.district,
                provider=a.provider,
                dates={d.replace(year=d.year + years) for d in a.dates},
            )
            for a in result.areas
        ]
    )


def test_the_next_period_continues_the_routes_of_the_same_places():
    # 20 May 2026: June-December is linked next to January-May.
    files = [(f, parsed(f)) for f in (TOWN_H1, TOWN_H2, DISTRICT_H1, DISTRICT_H2)]
    warnings = ukmerge.combine(files, REGISTRY, date(2026, 5, 20))
    town_h1, town_h2, district_h1, district_h2 = (result for _, result in files)
    # Every route of the district names the same places in both: their rows get June's dates.
    assert district_h2.areas == []
    assert all(max(a.dates) > date(2026, 6, 1) for a in district_h1.areas)
    # The town's Užupio, Krekšlių and Šlapių routes have new streets in June: they wait.
    assert town_h2.areas == []
    assert [max(a.dates) > date(2026, 6, 1) for a in town_h1.areas if a.kind == "household"] == [
        True,
        False,
        False,
        False,
        True,
    ]
    assert warnings[0] == (
        "Ukmergės r. (town) household: the 2026-06-01 place 'Užupio maršrutas: UKMERGĖS MIESTO "
        "SEN.: Antakalnio g., Gruod' doesn't match one 2026-01-01 place; its dates are left out "
        "until 2026-06-01"
    )
    assert len(warnings) == 18
    # In June the new period takes over.
    files = [(f, parsed(f)) for f in (TOWN_H1, TOWN_H2, DISTRICT_H1, DISTRICT_H2)]
    assert ukmerge.combine(files, REGISTRY, date(2026, 6, 2)) == []
    assert [len(result.areas) for _, result in files] == [0, 15, 0, 42]


def test_a_period_that_ends_without_the_next():
    files = [(f, content(f)) for f in (TOWN_H2, DISTRICT_H2)]
    data, warnings = build_dataset(files, REGISTRY, date(2027, 1, 20), 31, ukmerge.SOURCE)
    assert warnings[:2] == [
        "the schedule of the town ended on 2026-12-31; no newer one is read",
        "the schedule of the district ended on 2026-12-31; no newer one is read",
    ]
    # The routes keep their last dates, 31 days on.
    assert row(data, place(data, "Adomiškis")["schedule"]["household"]["area"])["dates"] == [
        "2026-12-22"
    ]
    assert row(data, place(data, "Adomiškis")["schedule"]["glass"]["area"])["dates"] == [
        "2026-11-24"
    ]


def test_the_next_period_in_place_of_the_last():
    # Linked in place of the last before it starts: the last one's December dates are lost.
    next_period = shifted(parsed(TOWN_H1), years=1)
    linked = file("town", 2027, (1, 5))
    warnings = ukmerge.combine([(linked, next_period)], REGISTRY, date(2026, 12, 20))
    assert warnings == ["no schedule of the town for today; the next starts on 2027-01-01"]


def test_overlapping_files_fail():
    whole_year = file("town", 2026, (1, 12), TOWN_H2.file_name)
    with pytest.raises(ValueError, match="overlap"):
        ukmerge.combine(
            [(TOWN_H2, parsed(TOWN_H2)), (whole_year, parsed(TOWN_H2))], REGISTRY, TODAY
        )


# --- the published folder --------------------------------------------------------


def test_published_folder_and_its_metrics(part, tmp_path):
    data, warnings = part
    built = [(ukmerge.PROVIDER, {**data, "warnings": len(warnings)})]
    dataset = merge_parts(built, ukmerge.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == ["ukmerge"]
    assert all(a["provider"] == "ukmerge" for a in dataset["areas"])
    folder = tmp_path / "ukmerges-r"
    folder.mkdir()
    (folder / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    (folder / "addresses.json").write_text("{}", encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="ukmerge"} 364' in text
    assert 'siuksliaveze_data_areas{source="ukmerge",kind="glass"} 19' in text
    assert 'siuksliaveze_data_warnings{source="ukmerge"} 21' in text
    # regions.json lists the folder, so installed apps download it.
    assert regions.collect(tmp_path)["regions"] == [
        {
            "path": "ukmerges-r/",
            "kind": "settlements",
            "files": ["schedule.json", "addresses.json"],
            "providers": ["ukmerge"],
        }
    ]


def test_main_writes_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(ukmerge.http, "get", serve)
    monkeypatch.setattr(ukmerge.raseiniai.address_register, "fetch", refused)
    monkeypatch.setattr(ukmerge.raseiniai.address_points, "fetch", refused)
    assert ukmerge.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["ukmerge"]
    addresses = json.loads((tmp_path / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > ukmerge.MUNICIPALITY.min_address_points


def serve(url, timeout=0):
    """The page and its files, from the fixtures."""
    by_url = {f.url: COPIES[f.file_name] for f in (TOWN_H2, DISTRICT_H2, TOWN_H1, DISTRICT_H1)}
    if url == ukmerge.PAGE_URL:
        return fixture("ukmerge/page.html")
    if url in by_url:
        return fixture(f"ukmerge/{by_url[url]}")
    raise OSError(f"HTTP Error 404: {url}")


def refused(url, timeout=0):
    raise OSError("HTTP Error 403: Forbidden")


def test_the_copy_when_the_site_refuses_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(ukmerge.http, "get", serve)
    copy = tmp_path / "copy"
    ukmerge.save_copy(copy, TODAY)
    # As Kėdainių r.'s: the page, the files read today named after their URLs, and copy.json.
    index = json.loads((copy / "copy.json").read_text(encoding="utf-8"))
    assert index["takenAt"] == "2026-11-21" and index["page"] == ukmerge.PAGE_URL
    assert index["files"] == [TOWN_H2.file_name, DISTRICT_H2.file_name]
    assert sorted(p.name for p in copy.iterdir()) == sorted(
        [TOWN_H2.file_name, DISTRICT_H2.file_name, "copy.json", "page.html"]
    )

    monkeypatch.setattr(ukmerge.http, "get", refused)
    monkeypatch.setattr(ukmerge, "COPY_DIR", copy)
    files, warnings = ukmerge.download(TODAY, 31)
    assert [(f.group, f.months) for f, _ in files] == [("town", (6, 12)), ("district", (6, 12))]
    assert files[1][1] == content(DISTRICT_H2)
    assert warnings == [
        f"{ukmerge.PAGE_URL}: unavailable (HTTP Error 403: Forbidden); used the copy from "
        "2026-11-21 (0 days old)"
    ]
    # Months later it gives its age but asks for no refresh (snapshot.site_copy_note); the
    # routes keep their last dates meanwhile.
    _, warnings = ukmerge.download(date(2027, 1, 25), 31)
    assert warnings[0].endswith("used the copy from 2026-11-21 (65 days old)")
    # Without a copy, the error.
    monkeypatch.setattr(ukmerge, "COPY_DIR", tmp_path / "none")
    with pytest.raises(OSError, match="403"):
        ukmerge.download(TODAY, 31)


def test_the_committed_copy_can_be_built(monkeypatch):
    """The copy in pipeline/data, as the daily job reads it on GitHub's runners (it is
    refreshed, so only that it builds: build_dataset checks the counts)."""
    monkeypatch.setattr(ukmerge.http, "get", refused)
    # The files the daily job reads (31 days back): the copy has those of the day it was taken.
    files, warnings = ukmerge.download(date.today(), 31)
    assert "used the copy from" in warnings[0]
    assert {f.group for f, _ in files} == {"town", "district"}
    build_dataset(files, REGISTRY, date.today(), 31, ukmerge.SOURCE)


def test_a_page_without_the_files_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(ukmerge.http, "get", lambda url, timeout=0: b"<html></html>")
    monkeypatch.setattr(build, "live_or_snapshot", lambda name, live, snap: (snap()[0], None))
    assert ukmerge.main(["--out", str(tmp_path)]) == 1
    assert not (tmp_path / "schedule.json").exists()

"""Marijampolės AATC: the pages of five municipalities, the PDFs of Ecoservice and Ekonovus,
their routes, and the one folder for the five."""

import dataclasses
import json
from datetime import date
from urllib.parse import unquote

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, maatc, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
UPLOADS = "https://maatc.lt/wp-content/uploads/"
# The files the pages link, by the name in their link, and their copies in fixtures/maatc.
COPIES = {
    "2026-m.-Marijampoles-sav.-individualiu-valdu-misriu-komunaliniu-atlieku-pakuociu-ir-"
    "antriniu-zaliavu-konteineriu-aptarnavimo-grafikas.pdf": "marijampole-household.pdf",
    "2026-m.-Marijampoles-sav.-individualiu-maisto-surinkimo-grafikas.pdf": (
        "marijampole-food.pdf"
    ),
    "2026-m.-Vilkaviskio-raj.-sav.-individualiu-valdu-misriu-komunaliniu-atlieku-"
    "konteineriu-aptarnavimo-grafikas-.pdf": "vilkaviskis-household.pdf",
    "2026-m.-Vilkaviskio-raj.-sav.-individualiu-valdu-antriniu-zaliavu-ir-pakuociu-"
    "konteineriu-aptarnavimo-grafikas.pdf": "vilkaviskis-packaging.pdf",
    "2026-m.-Vilkaviskio-raj.sav_.-individualiu-maisto-surinkimo-grafikas.pdf": (
        "vilkaviskis-food.pdf"
    ),
    "2026-m.-Kalvarijos-sav.-individualiu-valdu-misriu-komunaliniu-atlieku-pakuociu-ir-"
    "antriniu-zaliavu-konteineriu-aptarnavimo-grafikas-.pdf": "kalvarija-household.pdf",
    "2026-m.-Kalvarijos-sav.-individualiu-maisto-surinkimo-grafikas.pdf": "kalvarija-food.pdf",
    "2026-m.-Kazlu-Rudos-sav.-individualiu-valdu-misriu-komunaliniu-atlieku-pakuociu-ir-"
    "antriniu-zaliavu-konteineriu-aptarnavimo-grafikas.pdf": "kazluruda-household.pdf",
    "2026-m.-Kazlu-Rudos-sav.-individualiu-maisto-surinkimo-grafikas.pdf": "kazluruda-food.pdf",
    "2026-m.-Sakiu-rajono-sav.-individualiu-valdu-misriu-komunaliniu-atlieku-konteineriu-"
    "aptarnavimo-grafikas-.pdf": "sakiai-household.pdf",
    "2026-m.-Sakiu-rajono-sav.-misriu-pakuociu-atlieku-surinkimo-is-individualiu-"
    "konteineriu-grafikas-.pdf": "sakiai-packaging.pdf",
    "2026-m.-Sakiu-rajono-sav.-stiklo-pakuociu-atlieku-surinkimo-is-individualiu-"
    "konteineriu-grafikas-.pdf": "sakiai-glass.pdf",
    "2026-m.-Sakiu-raj.sav_.-individualiu-maisto-surinkimo-grafikas.pdf": "sakiai-food.pdf",
}
REGISTRIES = {
    "marijampole": "registry-marijampoles-sav-2026-11-21.json",
    "vilkaviskis": "registry-vilkaviskio-r-2026-11-21.json",
    "kalvarija": "registry-kalvarijos-sav-2026-11-21.json",
    "kazluruda": "registry-kazlu-rudos-sav-2026-11-21.json",
    "sakiai": "registry-sakiu-r-2026-11-21.json",
}


def serve(url, timeout=0):
    """The saved pages and files, as maatc.http.get."""
    for municipality in maatc.MUNICIPALITIES:
        if url == municipality.provider.url:
            return fixture(f"maatc/page-{municipality.provider.id}.html")
    return fixture(f"maatc/{COPIES[unquote(url.rsplit('/', 1)[-1])]}")


def registry(key):
    return Registry.load(FIXTURES / "maatc" / REGISTRIES[key])


def parsed(copy, kind, municipality, name=None):
    file = SourceFile(kind, f"{UPLOADS}2025/12/{copy}", name or f"2026-m.-{copy}")
    return maatc.parse_file(file, fixture(f"maatc/{copy}"), municipality).areas


@pytest.fixture(scope="module")
def parts():
    """Each municipality's part as the daily job builds it from its page, with every date of
    the year kept."""
    built = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(maatc.http, "get", serve)
        for municipality in maatc.MUNICIPALITIES:
            key = municipality.provider.id
            files, warnings = maatc.download(municipality, TODAY, 366)
            data, more = build_dataset(files, registry(key), TODAY, 366, maatc.source(municipality))
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


# --- the pages ---------------------------------------------------------------


def test_finds_the_files_of_individual_houses_on_each_page():
    found = {}
    for municipality in maatc.MUNICIPALITIES:
        page = fixture(f"maatc/page-{municipality.provider.id}.html").decode("utf-8")
        files = maatc.find_files(page, municipality.provider.url)
        found[municipality.provider.id] = sorted(f.kind for f in files)
        for file in files:
            assert file.file_name in COPIES
            assert file.url.startswith(UPLOADS)
    assert found == {
        "marijampole": ["food", "household"],
        "vilkaviskis": ["food", "household", "packaging"],
        "kalvarija": ["food", "household"],
        "kazluruda": ["food", "household"],
        "sakiai": ["food", "glass", "household", "packaging"],
    }


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (
            "2026 m. Marijampolės sav. individualių valdų mišrių komunalinių atliekų, pakuočių "
            "ir antrinių žaliavų konteinerių aptarnavimo grafikas",
            "household",
        ),
        (
            "2026 m. Vilkaviškio raj. sav. individualių valdų antrinių žaliavų ir pakuočių "
            "konteinerių aptarnavimo grafikas",
            "packaging",
        ),
        (
            "2026 m. Šakių rajono sav. mišrių pakuočių atliekų surinkimo iš individualių "
            "konteinerių grafikas",
            "packaging",
        ),
        (
            "2026 m. Šakių rajono sav. stiklo pakuočių atliekų surinkimo iš individualių "
            "konteinerių grafikas",
            "glass",
        ),
        ("2026 m. Kalvarijos sav. maisto atliekų iš individualių konteinerių", "food"),
        ("Stambiagabaričių atliekų surinkimo grafikas", None),
    ],
)
def test_the_kind_of_a_file_by_its_text(text, kind):
    assert maatc.file_kind(text) == kind


def page(*links):
    return "".join(f'<a href="{UPLOADS}{href}">{text}</a>' for href, text in links)


def test_shared_containers_washing_and_bulky_waste_are_not_read():
    html = page(
        ("2025/12/a.pdf", "2026 m. Kazlų Rūdos sav. bendro naudojimo konteinerių grafikas"),
        ("2025/12/b.pdf", "2026 m. Kazlų Rūdos sav. 1,1 m3 bendro naudojimo ... plovimo grafikas"),
        (
            "2025/12/c.pdf",
            "2026 m. Kazlų Rūdos sav. gyventojų daugiabučiuose bei individualiuose valdose "
            "susidariusių didelių gabaritų atliekų ... surinkimo grafikas",
        ),
        ("2025/12/d.pdf", "2026 m. Kazlų Rūdos sav. juridinių antrinių žaliavų grafikas"),
        ("2026/06/e.pdf", "2026 m. Bendro naudojimo maisto atliekų konteinerių plovimo grafikas"),
        ("2026/06/f.pdf", "2026 m. Kazlų Rūdos sav. maisto atliekų iš individualių konteinerių"),
    )
    assert [f.url for f in maatc.find_files(html, maatc.KAZLU_RUDA.provider.url)] == [
        f"{UPLOADS}2026/06/f.pdf"
    ]


def test_next_years_files_are_read_next_to_this_years():
    html = page(
        ("2025/12/2026-m.-misriu.pdf", "2026 m. individualių valdų mišrių komunalinių grafikas"),
        ("2026/12/2027-m.-misriu.pdf", "2027 m. individualių valdų mišrių komunalinių grafikas"),
        ("2024/12/2025-m.-misriu.pdf", "2025 m. individualių valdų mišrių komunalinių grafikas"),
    )
    files = maatc.find_files(html, maatc.SAKIAI.provider.url)
    chosen, _ = maatc.tratc.select_files(files, TODAY)
    assert [f.file_name for f in chosen] == ["2026-m.-misriu.pdf", "2027-m.-misriu.pdf"]


# --- the tables ------------------------------------------------------------------


def test_ecoservice_blocks_with_mixed_waste_packaging_and_glass():
    areas = parsed("kazluruda-household.pdf", "household", maatc.KAZLU_RUDA)
    assert len(areas) == 39  # 13 routes, each with three waste types
    town = [a for a in areas if a.name.startswith("KAZLŲ RŪDOS M.: Alyvų g., Gedimino g.")]
    by_kind = {a.kind: sorted(a.dates) for a in town}
    # "Mišrios komunalinės atliekos/Pakuočių (mėlynas) konteineris/Stiklo konteineris" and
    # "Mišrios komunalinės atliekos/Pakuočių (mėlynas) konteineris": every two weeks, glass
    # every four.
    assert len(by_kind["household"]) == len(by_kind["packaging"]) == 26
    assert by_kind["household"][:3] == [date(2026, 1, 5), date(2026, 1, 19), date(2026, 2, 2)]
    assert by_kind["glass"][:4] == [
        date(2026, 1, 5),
        date(2026, 2, 2),
        date(2026, 3, 2),
        date(2026, 3, 30),
    ]
    assert by_kind["glass"][-1] == date(2026, 12, 7) and len(by_kind["glass"]) == 13
    # A village: mixed waste every two weeks, packaging and glass every four.
    village = {a.kind: a for a in areas if a.name.startswith("KAZLŲ RŪDOS SEN.: Kazlų I k.")}
    assert len(village["household"].dates) == 26 and len(village["packaging"].dates) == 13
    assert village["glass"].dates == village["packaging"].dates
    # The elderships written bottom to top on the left aren't in the places.
    assert all("seniūnija" not in a.name for a in areas)
    assert {a.district for a in areas} == {"Kazlų Rūdos sav."}
    assert {a.provider for a in areas} == {"kazluruda"}


def test_rows_without_a_waste_type_are_the_titles():
    areas = parsed("vilkaviskis-household.pdf", "household", maatc.VILKAVISKIS)
    assert len(areas) == 29 and {a.kind for a in areas} == {"household"}
    town = next(a for a in areas if a.name.startswith("VILKAVIŠKIO M.: Akmenų g."))
    assert len(town.dates) == 26 and town.weekday == "Pirmadienis"


def test_packaging_and_glass_with_weekdays_and_dashes():
    areas = parsed("vilkaviskis-packaging.pdf", "packaging", maatc.VILKAVISKIS)
    assert len(areas) == 36
    pilviskiai = {a.kind: a for a in areas if a.name == "PILVIŠKIŲ SEN.: Pilviškių mstl."}
    assert len(pilviskiai["packaging"].dates) == 26
    # "Stiklas | Pirmadienis I | - | 23 | - | 20 | ...".
    assert sorted(pilviskiai["glass"].dates) == [
        date(2026, 2, 23),
        date(2026, 4, 20),
        date(2026, 6, 15),
        date(2026, 8, 10),
        date(2026, 10, 5),
        date(2026, 11, 30),
    ]


def test_ekonovus_tables():
    areas = parsed("sakiai-packaging.pdf", "packaging", maatc.SAKIAI)
    assert len(areas) == 13 and {a.kind for a in areas} == {"packaging"}
    town = next(a for a in areas if a.name == "Šakių sen.: Šakių m.")
    # "2; 16; 30" in June, "08,22" in September.
    assert {date(2026, 6, 2), date(2026, 6, 16), date(2026, 6, 30)} <= town.dates
    assert {date(2026, 9, 8), date(2026, 9, 22)} <= town.dates
    assert len(town.dates) == 26 and town.weekday == "Antradienis"
    # Food waste from July: the months before are empty.
    food = parsed("marijampole-food.pdf", "food", maatc.MARIJAMPOLE)
    assert len(food) == 8 and min(d for a in food for d in a.dates) == date(2026, 7, 1)
    assert food[0].name.startswith("Marijampolės m. (A. Civinsko g., Alytaus g.")


def test_the_title_must_agree_with_the_file_name_and_the_link():
    with pytest.raises(ValueError, match="the title says 2026, the file name 2027"):
        parsed("kalvarija-food.pdf", "food", maatc.KALVARIJA, name="2027-m.-maisto.pdf")
    with pytest.raises(ValueError, match="a glass schedule, its link says packaging"):
        parsed("sakiai-glass.pdf", "packaging", maatc.SAKIAI)


def test_a_waste_type_the_municipalitys_files_dont_have_fails():
    # Šakių r.: packaging and glass are Ekonovus' files of their own.
    with pytest.raises(ValueError, match="glass dates in a household file"):
        parsed("kazluruda-household.pdf", "household", maatc.SAKIAI)


@pytest.mark.parametrize(
    ("text", "days"),
    [("5", [5]), ("2, 30", [2, 30]), ("2; 16; 30", [2, 16, 30]), ("08,22", [8, 22]), ("-", [])],
)
def test_days_of_a_month(text, days):
    assert maatc._days(text, "x") == days


@pytest.mark.parametrize("text", ["2, a", "Pirmadienis", "1.15"])
def test_anything_else_in_a_months_cell_fails(text):
    with pytest.raises(ValueError, match="not days"):
        maatc._days(text, "x")


def test_months_out_of_order_fail():
    months = "sausis vasaris balandis kovas gegužė birželis liepa".split()
    with pytest.raises(ValueError, match="months out of order"):
        maatc._header(["", "", *months], 2026, "x")
    in_order = "sausis vasaris kovas balandis gegužė birželis liepa".split()
    with pytest.raises(ValueError, match="columns"):
        maatc._header(["Grafikas", "Adresas", *in_order], 2026, "x")


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
            len(warnings),
        )
    assert counts == {
        "marijampole": (279, 265, 4, 10, 12),
        "vilkaviskis": (360, 357, 0, 3, 17),
        "kalvarija": (160, 133, 0, 27, 0),
        "kazluruda": (183, 144, 1, 38, 0),
        "sakiai": (507, 450, 9, 48, 7),
    }
    kinds = {key: sorted({a["kind"] for a in data["areas"]}) for key, (_, data, _) in parts.items()}
    assert set(map(tuple, kinds.values())) == {("food", "glass", "household", "packaging")}


@pytest.mark.parametrize(
    ("key", "name", "kind", "count", "first", "last"),
    [
        ("marijampole", "Šunskai", "mstl.", 27, "2026-01-01", "2026-12-31"),
        ("vilkaviskis", "Keturvalakiai", "mstl.", 26, "2026-01-14", "2026-12-30"),
        ("kalvarija", "Liubavas", "k.", 27, "2026-01-01", "2026-12-31"),
        ("kazluruda", "Jankai", "k.", 26, "2026-01-08", "2026-12-24"),
        ("sakiai", "Lekėčiai", "mstl.", 27, "2026-01-01", "2026-12-31"),
    ],
)
def test_a_village_of_each_municipality(parts, key, name, kind, count, first, last):
    _, data, _ = parts[key]
    dates = row(data, schedule_of(data, name, kind=kind)["area"])["dates"]
    assert (len(dates), dates[0], dates[-1]) == (count, first, last)


@pytest.mark.parametrize(
    ("key", "town", "street"),
    [
        ("marijampole", "Marijampolė", "R. Juknevičiaus g."),
        ("vilkaviskis", "Vilkaviškis", "Šaltinio g."),
        ("vilkaviskis", "Kybartai", "Putinų g."),
        ("kalvarija", "Kalvarija", "Artojų g."),
        ("kazluruda", "Kazlų Rūda", "Atžalyno g."),
        ("sakiai", "Šakiai", "Jaunystės 2-oji g."),
        ("sakiai", "Gelgaudiškis", "Obelų 2-oji g."),
    ],
)
def test_a_town_street_no_route_names_is_left_to_the_app(parts, key, town, street):
    _, data, _ = parts[key]
    assert street_rows(data, town, "household", street, kind="m.") is None
    # No street is "no pickup": nothing in the files says a street has none.
    for waste, schedule in place(data, town, "m.")["schedule"].items():
        assert all(schedule.get("streets", {}).values()), waste


def test_marijampole(parts):
    _, data, warnings = parts["marijampole"]
    # The town in another eldership's section: "MOKOLŲ SEN.: ... MARIJAMPOLĖS M.: Vytauto g.
    # (nuo Geležinkelio g. iki Vingio g.)", one more choice for that street.
    vytauto = street_rows(data, "Marijampolė", "household", "Vytauto g.")
    assert any(row(data, r)["name"].startswith("MOKOLŲ SEN.: Kumelionių k.") for r in vytauto)
    # "Panoramos g. (Liepynų k.)" in the town's list is Liepynai's street.
    liepynai = street_rows(data, "Liepynai", "household", "Panoramos g.")
    assert row(data, liepynai[0])["name"].startswith("MARIJAMPOLĖS M.: Fabriko g.")
    # Numbered streets of the gardens: "Šakališkių (nuo 1-oji iki 18-oji) g.", "Tylioji 1, 3,
    # 5, 7-oji g.".
    for street in ("Šakališkių 18-oji g.", "Tylioji 7-oji g."):
        rows = street_rows(data, "Marijampolė", "household", street)
        assert row(data, rows[0])["name"].startswith("MARIJAMPOLĖS M.(Šakališkių sodai)")
    # "Liudvinavo k. (tik Paparčio sodai)": the streets named after the gardens.
    gardens = street_rows(data, "Liudvinavas", "household", "Paparčio 23-oji g.")
    assert row(data, gardens[0])["name"].startswith("MARIJAMPOLĖS M.: Fabriko g.")
    assert row(data, schedule_of(data, "Liudvinavas", kind="k.")["area"])["name"].startswith(
        "LIUDVINAVO SEN.: Liudvinavo mstl."
    )
    # "Putriškių k." in Liudvinavo sen.'s section is Putriškiai of Patašinės sen., not
    # Petriškiai.
    putriskiai = row(data, schedule_of(data, "Putriškiai")["area"])
    assert putriskiai["name"].startswith("LIUDVINAVO SEN.: Narto k.")
    # Some houses of a village in another route: the app asks.
    assert len(schedule_of(data, "Balaikai")["candidates"]) == 2
    # Food waste of Triobiškiai of Patašinės sen., which has the streets, not of Liudvinavo sen.
    food = street_rows(data, "Triobiškiai", "food", "Krėvos g.", district="Patašinės")
    assert row(data, food[0])["name"].startswith("Marijampolės m. (Algirdo g.")
    assert "food" not in place(data, "Triobiškiai", district="Liudvinavo").get("schedule", {})
    assert "not a settlement or a street: household: Igliaukos sen.: Popojų k." in warnings


def test_vilkaviskis(parts):
    _, data, warnings = parts["vilkaviskis"]
    # "visa Klausučių seniūnija", "Pilviškių seniūnijos kaimai išskyrus ...": a fallback.
    whole = row(data, schedule_of(data, "Rumokai")["area"])
    assert whole["name"] == "KLAUSUČIŲ SEN.: visa Klausučių seniūnija"
    villages = row(data, schedule_of(data, "Alksnėnai", district="Pilviškių")["area"])
    assert villages["name"].startswith("PILVIŠKIŲ SEN.: Pilviškių seniūnijos kaimai")
    gabriske = row(data, schedule_of(data, "Gabriškė")["area"])
    assert gabriske["name"].startswith("PILVIŠKIŲ SEN.: Pilviškių mstl.")
    # Antupiai, of Gižų sen. ("visa Gižų seniūnija"), named in Keturvalakių sen.'s section.
    antupiai = row(data, schedule_of(data, "Antupiai")["area"])
    assert antupiai["name"].startswith("KETURVALAKIŲ SEN.: Antupių k.")
    # "PAVEJONIO SEN.:" is Pajevonio sen.
    pajevonys = row(data, schedule_of(data, "Ančlaukys")["area"])
    assert pajevonys["name"].startswith("PAVEJONIO SEN.: Ančlaukio k.")
    assert not any("PAVEJONIO" in w or "PAVEVONIO" in w for w in warnings)


def test_kalvarija_and_kazlu_ruda(parts):
    _, kalvarija, _ = parts["kalvarija"]
    # "Skersabalių II k.": the register has one Skersabaliai.
    assert schedule_of(kalvarija, "Skersabaliai")["area"]
    _, kazluruda, _ = parts["kazluruda"]
    # "KAZLŲ RŪDOS SEN.:", an eldership of two words.
    jure = row(kazluruda, schedule_of(kazluruda, "Jūrė", kind="mstl.")["area"])
    assert jure["name"] == "KAZLŲ RŪDOS SEN.: Jūrės mstl., Čečetų k."
    # "Limarkų k. (tik 4 ir 5)" and "(išskyrus 4 ir 5)": the app asks.
    assert len(schedule_of(kazluruda, "Limarkai")["candidates"]) == 2


def test_sakiai(parts):
    _, data, warnings = parts["sakiai"]
    # "Kudirkos Naumiesčio sen.:", an eldership of two words; Ekonovus' packaging and glass.
    for waste in ("household", "packaging", "glass"):
        assert schedule_of(data, "Kudirkos Naumiestis", waste)
    town = row(data, schedule_of(data, "Kudirkos Naumiestis", "packaging")["area"])
    assert town["name"].startswith("Kudirkos Naumiesčio sen.: Kudirkos Naumiesčio m.")
    # "Bridžių VS." is the homestead.
    assert schedule_of(data, "Bridžiai", "packaging", kind="vs.")
    assert "not a settlement or a street: household: Šakių m.: Ramybės g." in warnings


# --- next year and the one folder ------------------------------------------------


def routes(year, *names):
    return ParseResult(
        [
            Area(
                "household",
                name,
                district="Kazlų Rūdos sav.",
                dates={date(year, 1, 14 + i)},
                provider="kazluruda",
            )
            for i, name in enumerate(names)
        ]
    )


def test_next_year_continues_routes_of_the_same_places():
    municipality = dataclasses.replace(maatc.KAZLU_RUDA, min_areas={})
    this_year = routes(2026, "KAZLŲ RŪDOS SEN.: Jūrės mstl., Čečetų k.", "JANKŲ SEN.: Jankų k.")
    next_year = routes(2027, "KAZLŲ RŪDOS SEN.: Čečetų k., Jūrės mstl.", "JANKŲ SEN.: Būdos k.")
    file = SourceFile("household", f"{UPLOADS}x.pdf", "x.pdf")
    warnings = maatc.tratc.combine(
        [(file, this_year), (file, next_year)],
        registry("kazluruda"),
        date(2026, 12, 20),
        municipality,
    )
    assert this_year.areas[0].dates == {date(2026, 1, 14), date(2027, 1, 14)}
    assert next_year.areas == []
    assert any("the 2027 route 'JANKŲ SEN.: Būdos k.'" in w for w in warnings)
    # Too few routes in next year's file fail now, not on 1 January.
    with pytest.raises(ValueError, match="only 1 household routes in the 2027 file"):
        maatc.tratc.combine(
            [(file, routes(2026, "JANKŲ SEN.: Jankų k.")), (file, routes(2027, "JANKŲ SEN."))],
            registry("kazluruda"),
            date(2026, 12, 20),
            maatc.KAZLU_RUDA,
        )


def test_one_folder_for_the_five(parts, tmp_path):
    built = [
        (maatc.BY_PROVIDER[key].provider, {**data, "warnings": len(warnings)})
        for key, (_, data, warnings) in parts.items()
    ]
    dataset = merge_parts(built, maatc.PAGES)
    assert [p["id"] for p in dataset["providers"]] == list(REGISTRIES)
    (tmp_path / "maatc").mkdir()
    (tmp_path / "maatc" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # A source each, by its provider; the places with a schedule.
    assert 'siuksliaveze_data_places{source="kalvarija"} 133' in text
    for key in REGISTRIES:
        assert f'siuksliaveze_data_areas{{source="{key}",kind="food"}}' in text


def test_a_municipality_that_fails_keeps_its_published_part(parts, tmp_path, monkeypatch):
    two = (maatc.KALVARIJA, maatc.KAZLU_RUDA)
    published = merge_parts(
        [
            (m.provider, {**parts[m.provider.id][1], "warnings": 0, "generatedAt": "2026-11-20"})
            for m in two
        ],
        maatc.PAGES,
    )

    def get(url, timeout=0):
        if url == maatc.KAZLU_RUDA.provider.url:
            raise OSError("HTTP Error 503: Service Unavailable")
        return serve(url)

    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(maatc, "MUNICIPALITIES", two)
    monkeypatch.setattr(maatc.http, "get", get)
    monkeypatch.setattr(maatc.address_register, "fetch", blocked)
    monkeypatch.setattr(maatc.address_points, "fetch", blocked)
    monkeypatch.setattr(build, "load_published", lambda url: lambda: published)
    assert maatc.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    providers = {p["id"]: p["generatedAt"] for p in data["providers"]}
    assert providers["kazluruda"] == "2026-11-20" and providers["kalvarija"] > "2026-11-21"
    assert {a["provider"] for a in data["areas"]} == {"kalvarija", "kazluruda"}
    assert (tmp_path / "addresses.json").exists()

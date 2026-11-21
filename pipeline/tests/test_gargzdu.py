"""Klaipėdos r.: the Gargždų švara page, the yearly spreadsheet, its rows and the joined years."""

import io
import json
from datetime import date

import openpyxl
import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import gargzdu, status
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.locations import variant_key
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "gargzdu" / "registry-klaipedos-r-2026-11-21.json")
TODAY = date(2026, 11, 21)
URL_2026 = "https://www.gargzdusvara.eu/uploads/Grafikai%202026/grafikas%202026.xlsx"
URL_2025 = "https://www.gargzdusvara.eu/uploads/GRAFIKAI%202025/2025%20MKA%2BAZ%20(1).xlsx"
FILE_2026 = SourceFile("household", URL_2026, "grafikas 2026.xlsx")
FILE_2025 = SourceFile("household", URL_2025, "2025 MKA+AZ (1).xlsx")


def page_files():
    return gargzdu.find_files(fixture("gargzdu/page.html").decode("utf-8"))


def parsed(file=FILE_2026):
    return gargzdu.parse_file(file, fixture(f"gargzdu/{file.file_name}"))


@pytest.fixture(scope="module")
def part():
    return build_dataset(
        [(FILE_2026, fixture("gargzdu/grafikas 2026.xlsx"))], REGISTRY, TODAY, 31, gargzdu.SOURCE
    )


def place(data, name, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name and district in (None, loc["district"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def rows(data, ids):
    return sorted(row(data, i)["name"] for i in ids)


def streets(location):
    return {label: key for key, label in location["streets"]}


# --- the page ----------------------------------------------------------------


def test_finds_the_spreadsheet_on_the_page():
    # The page links "uploads/..." relative to its <base href>, the site's root.
    assert page_files() == [FILE_2026]


def test_year_from_the_address():
    assert gargzdu.file_year(URL_2026) == 2026
    assert gargzdu.file_year(URL_2025) == 2025
    assert gargzdu.file_year("https://x/uploads/grafikas.xlsx") is None
    assert gargzdu.file_year("https://x/uploads/Grafikai 2026/grafikas 2027.xlsx") is None


def test_reads_this_year_and_later():
    next_year = SourceFile("household", "https://x/uploads/Grafikai%202027/g.xlsx", "g.xlsx")
    files, warnings = gargzdu.select_files([FILE_2025, FILE_2026, next_year], TODAY)
    assert files == [FILE_2026, next_year] and warnings == []
    # In January, before the new file is posted: the newest one, with a warning.
    files, warnings = gargzdu.select_files([FILE_2026], date(2027, 1, 5))
    assert files == [FILE_2026]
    assert warnings == ["no schedule for 2027 on the page"]


def test_a_correction_linked_after_the_original_is_read():
    fixed = SourceFile("household", "https://x/uploads/Grafikai%202026/naujas.xlsx", "naujas.xlsx")
    files, warnings = gargzdu.select_files([FILE_2026, fixed], TODAY)
    assert files == [fixed]
    assert warnings == ["grafikas 2026.xlsx: not read, naujas.xlsx is linked after it for 2026"]


def test_a_file_without_a_year_is_reported():
    plain = SourceFile("household", "https://x/uploads/grafikas.xlsx", "grafikas.xlsx")
    files, warnings = gargzdu.select_files([plain, FILE_2026], TODAY)
    assert files == [FILE_2026]
    assert warnings == ["grafikas.xlsx: no year in its address; not read"]


# --- the spreadsheet -------------------------------------------------------------


def test_parse_dates():
    assert gargzdu.parse_dates("01-02,01-16,12-31", 2026) == {
        date(2026, 1, 2),
        date(2026, 1, 16),
        date(2026, 12, 31),
    }
    # 2025: spaces after some commas.
    assert gargzdu.parse_dates("08-22, 09-19,", 2025) == {date(2025, 8, 22), date(2025, 9, 19)}
    assert gargzdu.parse_dates(None, 2026) == set()
    assert gargzdu.parse_dates("  ", 2026) == set()


@pytest.mark.parametrize("value", ["kas savaitę", "01.02", "02-30", 45658, date(2026, 1, 2)])
def test_parse_dates_rejects_anything_else(value):
    with pytest.raises(ValueError):
        gargzdu.parse_dates(value, 2026)


def test_file_of_2026():
    result = parsed()
    kinds = [a.kind for a in result.areas]
    assert {k: kinds.count(k) for k in set(kinds)} == {
        "household": 319,
        "packaging": 312,
        "glass": 311,
        "green": 298,
    }
    assert result.warnings == []
    village = {a.kind: a for a in result.areas if a.name == "Ablingos k."}
    assert len(village["household"].dates) == 26
    assert {date(2026, 1, 2), date(2026, 12, 18)} <= village["household"].dates
    assert village["glass"].dates == {
        date(2026, 1, 25),
        date(2026, 2, 25),
        date(2026, 5, 20),
        date(2026, 8, 12),
        date(2026, 11, 4),
    }
    # Green waste from April to November.
    assert min(village["green"].dates) == date(2026, 4, 10)
    assert max(village["green"].dates) == date(2026, 11, 27)
    # A row with dates for only some kinds.
    first = "Aukštkiemių k. - tik Airių g., Anglų g."
    assert {a.kind for a in result.areas if a.name.startswith(first)} == {"household"}


def test_file_of_2025():
    # Other column titles ("Gyvenvietės", "Komunalinės"), spaces in the lists, and a second
    # sheet with a row of the first one.
    result = parsed(FILE_2025)
    kinds = {a.kind for a in result.areas}
    assert kinds == {"household", "packaging", "glass", "green"}
    assert all(d.year == 2025 for a in result.areas for d in a.dates)
    assert len(result.warnings) == 4
    assert all(
        "Normantų k. (tik Karklų g., Rugiagėlių g.)' is listed twice" in w for w in result.warnings
    )


def workbook(*rows):
    book = openpyxl.Workbook()
    sheet = book.active
    for cells in rows:
        sheet.append(cells)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


HEADER = [
    "Gyvenvietė",
    "Mišrios komunalinės",
    "Plastikas - popierius",
    "Stiklas",
    "Žaliosios atliekos",
]


def test_unknown_column_fails_loudly():
    content = workbook([*HEADER, "Maisto atliekos"], ["Ablingos k.", "01-02"])
    with pytest.raises(ValueError, match="unknown column 'Maisto atliekos'"):
        gargzdu.parse_file(FILE_2026, content)


def test_unreadable_cell_fails_loudly():
    content = workbook(HEADER, ["Ablingos k.", "kas antrą penktadienį"])
    with pytest.raises(ValueError, match="row 2: unrecognised list of days"):
        gargzdu.parse_file(FILE_2026, content)


def test_dates_without_a_place_fail():
    content = workbook(HEADER, ["Ablingos k.", "01-02"], [None, "01-03"])
    with pytest.raises(ValueError, match="row 3: dates without a place"):
        gargzdu.parse_file(FILE_2026, content)


def test_file_without_a_table_fails():
    with pytest.raises(ValueError, match="no schedule table"):
        gargzdu.parse_file(FILE_2026, workbook(["Grafikas"]))


def test_hidden_rows_are_not_read():
    book = openpyxl.Workbook()
    sheet = book.active
    for cells in (HEADER, ["Ablingos k.", "01-02"], ["Agluonėnų k.", "01-07"]):
        sheet.append(cells)
    sheet.row_dimensions[3].hidden = True
    buffer = io.BytesIO()
    book.save(buffer)
    result = gargzdu.parse_file(FILE_2026, buffer.getvalue())
    assert [a.name for a in result.areas] == ["Ablingos k."]


# --- matching ------------------------------------------------------------------------


def test_counts(part):
    data, warnings = part
    stats = data["matching"]
    assert stats["locations"] == len(REGISTRY.settlements) == 294
    assert stats["household.single"] >= 250
    assert sum(1 for loc in data["locations"] if "household" in loc.get("schedule", {})) == 280
    assert all(loc["provider"] == "klaipedos" for loc in data["locations"])
    # Laugaliai is in the file, not in the register (Laugalių g. is a street of Gargždai).
    assert stats["unmatchedRows"] == 4
    assert all(w.endswith(": Laugalių k.") for w in warnings if w.startswith("not linked"))
    # Businesses, a military area and a filling station aren't homes: in the data, but no place
    # is linked to them.
    linked = {
        i
        for loc in data["locations"]
        for s in loc.get("schedule", {}).values()
        for i in [s.get("area"), *s.get("candidates", []), *sum(s.get("streets", {}).values(), [])]
    }
    businesses = [a for a in data["areas"] if "įmon" in a["name"] or "poligon" in a["name"]]
    assert businesses and not {a["id"] for a in businesses} & linked


def test_a_village_has_one_row_of_each_kind(part):
    data, _ = part
    village = place(data, "Ablinga")
    assert "streets" not in village
    for kind in ("household", "packaging", "glass", "green"):
        assert row(data, village["schedule"][kind]["area"])["name"] == "Ablingos k."


def test_rows_for_the_rest_of_a_village(part):
    data, _ = part
    village = place(data, "Dituva")
    keys = streets(village)
    packaging = village["schedule"]["packaging"]
    # "Dituvos k. (išskyrus Žiemos g., Kuršaičių g., ...)" for the rest of the village...
    assert row(data, packaging["area"])["name"].startswith("Dituvos k. (išskyrus Žiemos g.")
    # ...and the left-out streets by the rows that name them.
    assert rows(data, packaging["streets"][keys["Žiemos g."]]) == ["Dituvos k. (tik Žiemos g.)"]
    assert rows(data, packaging["streets"][keys["Kuršaičių g."]])[0].startswith(
        "Dituvos k. (tik Kuršaičių g."
    )
    assert keys["Vingio g."] not in packaging["streets"]


def test_rows_that_list_streets(part):
    data, _ = part
    village = place(data, "Aukštkiemiai")
    keys = streets(village)
    household = village["schedule"]["household"]["streets"]
    assert rows(data, household[keys["Airių g."]])[0].startswith("Aukštkiemių k. - tik Airių g.")
    assert rows(data, household[keys["Vėjų g."]]) == ["Aukštkiemių k. - Pagairės g., Vėjų g."]
    # A new street no row lists ("Auros g.", 63 addresses) isn't left without a pickup: the app
    # offers the village's rows.
    assert keys["Auros g."] not in household


def test_villages_of_the_same_name(part):
    data, _ = part
    judrenai = place(data, "Girininkai", "Judrėnų")["schedule"]["household"]
    vezaiciai = place(data, "Girininkai", "Vėžaičių")["schedule"]["household"]
    assert row(data, judrenai["area"])["name"] == "Girininkų k. - Judrėnų sen."
    assert row(data, vezaiciai["area"])["name"] == "Girininkų k. - Vėžaičių sen."


def test_parts_named_in_words_are_candidates(part):
    data, _ = part
    kalote = place(data, "Kalotė")["schedule"]["household"]
    assert rows(data, kalote["candidates"]) == [
        "Kalotės k. - naujoji Kalotė",
        "Kalotės k. - senoji Kalotė",
    ]
    # "nuo ... iki Pervalkos g.": a part of the village, not Pervalkos g.
    dercekliai = place(data, "Dercekliai")["schedule"]["household"]
    assert len(dercekliai["candidates"]) == 2


def test_shared_containers_are_one_more_choice(part):
    data, _ = part
    town = place(data, "Dovilai")["schedule"]["household"]
    assert rows(data, town["candidates"]) == ["Dovilų mstl.", "Dovilų mstl. - tik bendro naudojimo"]


def test_garden_communities(part):
    data, _ = part
    village = place(data, "Kiškėnai")
    garden = variant_key("SB „Tolupis“")
    assert [garden, "SB „Tolupis“"] in village["streets"]
    household = village["schedule"]["household"]
    assert row(data, household["area"])["name"] == 'Kiškėnų k. - (išskyrus SB "Tolupis")'
    assert rows(data, household["streets"][garden]) == [
        'Kiškėnų k. (SB "Tolupis", bendro naudojimo konteineriai)',
        'Kiškėnų k. - (tik SB "Tolupis")',
    ]
    # A garden's shared containers, in a row of their own.
    vaiteliai = place(data, "Vaiteliai")
    key = variant_key("SB „Vaiteliai“")
    assert rows(data, vaiteliai["schedule"]["household"]["streets"][key]) == [
        'SB "Vaiteliai" (Bendro naudojimo konteineriai)',
        "Vaitelių k.",
    ]
    # Gardens a list of streets names: a choice of the town with that row.
    town = place(data, "Gargždai")
    packaging = town["schedule"]["packaging"]["streets"][variant_key("SB „Minija“")]
    assert rows(data, packaging)[0].startswith("Gargždų m. - (pietinė miesto dalis")


def test_typos_in_the_names(part):
    data, _ = part
    # "Klipčšių k." is Klipščiai, "Gargdždų m." Gargždai, "Moctaičių g." Mostaičių g.
    assert "green" in place(data, "Klipščiai")["schedule"]
    town = place(data, "Gargždai")
    green = town["schedule"]["green"]["streets"]
    assert rows(data, green[streets(town)["Gargždės g."]])[0].startswith(
        "Gargdždų m. - Asiūklių g."
    )
    lelia = place(data, "Leliai")
    packaging = lelia["schedule"]["packaging"]["streets"]
    assert rows(data, packaging[streets(lelia)["Mostaičių g."]])[0].startswith(
        "Lelių k. (tik Moctaičių g."
    )


def test_a_street_and_a_lane_of_the_same_name(part):
    data, _ = part
    town = place(data, "Gargždai")
    keys = streets(town)
    green = town["schedule"]["green"]["streets"]
    # Only "Smilgų g." is in the green waste row, not "Smilgų skg.".
    assert rows(data, green[keys["Smilgų g."]]) == [
        "Gargždų m. Beržyno g., Inkilų g., Rūtenių g., Saulės g., Skaidrioji g., Smilgų g."
    ]
    assert keys["Smilgų skg."] not in green


def test_names_that_match_nothing_are_reported(part):
    _, warnings = part
    unknown = [w for w in warnings if w.startswith("not a settlement or a street")]
    # Streets the register doesn't have (yet), or spelled differently ("Vėjų g." is Vėjo g.).
    assert "not a settlement or a street: glass: Slengių k.: Deimenos g" in unknown
    assert "not a settlement or a street: packaging: Saulažolių k.: Vėjų g" in unknown
    assert len(unknown) <= 10


# --- this year and the next ------------------------------------------------------


def year_rows(year, *names):
    return ParseResult(
        [Area("household", name, dates={date(year, 12, 1)}, provider="klaipedos") for name in names]
    )


def test_next_year_continues_rows_of_the_same_text(monkeypatch):
    monkeypatch.setattr(gargzdu, "MIN_AREAS", {})
    this_year = year_rows(2026, "Ablingos k.", "Agluonėnų k.")
    next_year = year_rows(2027, "Ablingos k.", "Agluonėnų k. - tik Ąžuolų g.")
    warnings = gargzdu.combine([(FILE_2026, this_year), (FILE_2026, next_year)], REGISTRY, TODAY)
    assert this_year.areas[0].dates == {date(2026, 12, 1), date(2027, 12, 1)}
    assert this_year.areas[1].dates == {date(2026, 12, 1)}
    assert next_year.areas == []
    assert warnings == [
        "household: the 2027 row 'Agluonėnų k. - tik Ąžuolų g.' isn't in the 2026 file; its dates "
        "are left out until 2027",
        "household: the 2026 row 'Agluonėnų k.' has no dates for 2027",
    ]
    # In January the new year's rows take over.
    this_year = year_rows(2026, "Ablingos k.")
    next_year = year_rows(2027, "Ablingos k.", "Agluonėnų k. - tik Ąžuolų g.")
    gargzdu.combine([(FILE_2026, this_year), (FILE_2026, next_year)], REGISTRY, date(2027, 1, 2))
    assert this_year.areas == [] and len(next_year.areas) == 2


def test_next_year_is_checked_when_it_appears():
    this_year = year_rows(2026, "Ablingos k.")
    next_year = year_rows(2027, "Ablingos k.")
    with pytest.raises(ValueError, match="only 1 household rows in the 2027 file"):
        gargzdu.combine([(FILE_2026, this_year), (FILE_2026, next_year)], REGISTRY, TODAY)


def test_january_without_the_new_file():
    today = date(2027, 1, 5)
    data, _ = build_dataset(
        [(FILE_2026, fixture("gargzdu/grafikas 2026.xlsx"))], REGISTRY, today, 31, gargzdu.SOURCE
    )
    # The places stay linked to last year's rows, which keep their last dates.
    village = place(data, "Ablinga")["schedule"]
    assert row(data, village["household"]["area"])["dates"] == ["2026-12-18"]


def test_missing_kind_fails():
    content = workbook(HEADER[:2], *[[f"Ablingos k. {i}", "01-02"] for i in range(300)])
    with pytest.raises(ValidationError, match="only 0 packaging areas"):
        build_dataset([(FILE_2026, content)], REGISTRY, TODAY, 31, gargzdu.SOURCE)


# --- the published file ------------------------------------------------------------


def test_published_file_and_its_metrics(part, tmp_path):
    data, warnings = part
    data = {**data, "warnings": len(warnings)}
    dataset = merge_parts([(gargzdu.PROVIDER, data)], gargzdu.PAGE_URL)
    assert dataset["source"] == gargzdu.PAGE_URL
    assert [p["id"] for p in dataset["providers"]] == ["klaipedos"]
    assert all(a["provider"] == "klaipedos" for a in dataset["areas"])
    assert dataset["coverage"]["green"] == {"from": "2026-10-21", "to": "2026-11-29"}

    (tmp_path / "klaipedos-r").mkdir()
    (tmp_path / "klaipedos-r" / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_areas{source="klaipedos",kind="green"}' in text
    places = sum(1 for loc in dataset["locations"] if loc.get("schedule"))
    assert f'siuksliaveze_data_places{{source="klaipedos"}} {places}' in text

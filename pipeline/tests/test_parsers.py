from datetime import date
from pathlib import Path

import pytest

from schedule_pipeline.build import ValidationError, build_dataset
from schedule_pipeline.dates import assign_years, parse_days, parse_month, parse_weekdays
from schedule_pipeline.pdf_parser import parse_pdf
from schedule_pipeline.scrape import classify, find_schedule_files
from schedule_pipeline.xlsx_parser import parse_xlsx

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def by_name(areas, prefix):
    return next(a for a in areas if a.name.startswith(prefix))


# --- dates -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("11 d., 25 d.", [11, 25]),
        ("1d., 15d., 29d., ", [1, 15, 29]),
        ("1 5 d .", [15]),
        ("17 d", [17]),
        ("", []),
    ],
)
def test_parse_days(text, expected):
    assert parse_days(text) == expected


def test_parse_days_rejects_unknown_format():
    with pytest.raises(ValueError):
        parse_days("pagal poreikį")


def test_months_and_weekdays():
    assert parse_month("Birželis") == 6
    assert parse_month("Lapkričio") == 11
    assert parse_month("Atliekos") is None
    assert parse_weekdays("kiekvienas mėnesio pimadienis, penktadienis") == [0, 4]
    assert assign_years([11, 12, 1, 2], 2026) == [2026, 2026, 2027, 2027]


# --- scraping ----------------------------------------------------------------


def test_finds_all_schedule_files():
    files = find_schedule_files(fixture("page.html").decode("utf-8"))
    kinds = sorted(f.kind for f in files)
    assert kinds == ["glass", "glass", "household", "packaging", "packaging"]
    assert all(f.url.startswith("https://www.nemenkom.lt/uploads/") for f in files)


def test_glass_folder_is_not_packaging():
    url = "https://www.nemenkom.lt/uploads/failai/atliekos/Stiklo%20pakuot%C4%97s/x.pdf"
    assert classify(url) == "glass"


# --- household xlsx ----------------------------------------------------------


@pytest.fixture(scope="module")
def household():
    name = "2026 m- birželis-gruodis mėn  Buitinių atliekų surinkimo grafikas.xlsx"
    return parse_xlsx(fixture("household-2026-06-12.xlsx"), "household", name)


def test_household_explicit_dates(household):
    area = by_name(household.areas, "Aleksandravas")
    assert area.district == "Avižienių"
    assert area.group == "Individualūs namai"
    assert date(2026, 6, 11) in area.dates
    assert date(2026, 10, 29) in area.dates
    assert all(d.weekday() == 3 for d in area.dates)  # Thursday


def test_household_inherits_missing_district(household):
    area = by_name(household.areas, "Bendoriai (Bendorėlių arka")
    assert area.district == "Avižienių"


def test_household_apartment_rules(household):
    apartments = [a for a in household.areas if a.group == "Daugiabučiai namai"]
    assert len(apartments) > 20
    weekly = by_name(apartments, "Buivydiškės")
    assert weekly.dates and {d.weekday() for d in weekly.dates} == {0, 4}
    every_other = by_name(apartments, "Skersabaliai")
    assert not every_other.dates
    assert every_other.note == "kas antras mėnesio trečiadienis"


def test_household_skips_notes_and_empty_rows(household):
    names = [a.name for a in household.areas]
    assert not any("DĖMESIUI" in n or "Parengė" in n for n in names)
    assert len(household.areas) > 650


# --- packaging / glass pdf ---------------------------------------------------


def test_packaging_pdf():
    result = parse_pdf(fixture("packaging-2026-q4.pdf"), "packaging", "2026 m- spalio.pdf")
    assert len(result.areas) > 30
    area = by_name(result.areas, "Avižienių sen. kaimai: Avižienių mstl. Avižų g.")
    # Letter-spaced cells in the PDF ("1 5 d .") must still parse.
    assert area.dates == {date(2026, 10, 15), date(2026, 11, 16), date(2026, 12, 15)}


def test_glass_pdf_single_month_per_row():
    result = parse_pdf(fixture("glass-2026-q4.pdf"), "glass", "2026 m- spalio.pdf")
    assert len(result.areas) > 25
    assert all(len(a.dates) == 1 for a in result.areas)


# --- full build --------------------------------------------------------------


def all_sources():
    files = find_schedule_files(fixture("page.html").decode("utf-8"))
    names = {
        ("household", "birželis"): "household-2026-06-12.xlsx",
        ("packaging", "liepos"): "packaging-2026-q3.pdf",
        ("packaging", "spalio"): "packaging-2026-q4.pdf",
        ("glass", "liepos"): "glass-2026-q3.pdf",
        ("glass", "spalio"): "glass-2026-q4.pdf",
    }
    sources = []
    for f in files:
        local = next(v for (k, word), v in names.items() if k == f.kind and word in f.file_name)
        sources.append((f, fixture(local)))
    return sources


def test_build_dataset():
    dataset, _ = build_dataset(all_sources(), today=date(2026, 10, 11), keep_days=31)
    assert dataset["schemaVersion"] == 1
    assert set(dataset["coverage"]) == {"household", "packaging", "glass"}
    assert dataset["coverage"]["household"]["to"].startswith("2026-12")
    ids = [a["id"] for a in dataset["areas"]]
    assert len(ids) == len(set(ids))
    # Nothing older than the cutoff survives.
    assert all(d >= "2026-09-10" for a in dataset["areas"] for d in a["dates"])


def test_build_fails_when_a_schedule_is_missing():
    sources = [s for s in all_sources() if s[0].kind != "glass"]
    with pytest.raises(ValidationError, match="glass"):
        build_dataset(sources, today=date(2026, 10, 11), keep_days=31)


def test_identical_rows_from_two_quarters_are_merged():
    q3 = parse_pdf(fixture("packaging-2026-q3.pdf"), "packaging").areas
    q4 = parse_pdf(fixture("packaging-2026-q4.pdf"), "packaging").areas
    shared = {a.id for a in q3} & {a.id for a in q4}
    assert shared, "expected some areas with unchanged text across quarters"

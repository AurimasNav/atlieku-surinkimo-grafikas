"""Švenčionių r.: the municipality's page, its mixed waste rules turned into a rolling window of
dates, its packaging file (dates for nine elderships, rules for Pabradė's two), the places, and
yesterday's rows for a file that can't be read."""

import json
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, regions, status, svencionys
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 22)
UPLOADS = "https://svencionys.lt/wp-content/uploads/"
# The files the page links, and their copies in fixtures/svencionys.
COPIES = {
    f"{UPLOADS}2025/01/Misriuju-komunliniu-atlieku-isvezimo-grafikai_20250120.pdf": (
        "misrios-2025.pdf"
    ),
    f"{UPLOADS}2025/12/Pakuociu-atlieku-isvezimo-grafikai_2026.pdf": "pakuotes-2026.pdf",
}
REGISTRY = "svencionys/registry-svencioniu-r-2026-11-22.json"
NORTH_MIXED = [
    "Švenčionių seniūnija (išskyrus Milkuškų, Kukiškės, Medišionių kaimus)",
    "Adutiškio, Svirkų seniūnijos ir Milkuškų, Kukiškės, Medišionių kaimai",
    "Sarių, Cirkliškio, Strūnaičio seniūnijos",
    "Švenčionių miestas",
    "Švenčionėlių ir Kaltanėnų seniūnijos (išskyrus Berniūnų, Žvirbliškės, Kūrinių kaimus)",
    "Švenčionėlių miestas",
    "Labanoro seniūnija ir Berniūnų, Žvirbliškės, Kūrinių kaimai",
]


def serve(url, timeout=0):
    """The saved page and files, as svencionys.http.get."""
    if url == svencionys.PAGE_URL:
        return fixture("svencionys/page.html")
    return fixture(f"svencionys/{COPIES[url]}")


def parsed(kind, keep_days=31, today=TODAY):
    url = next(u for u, copy in COPIES.items() if (kind == "household") == ("Misri" in u))
    file = svencionys.ScheduleFile(kind, url, url.rsplit("/", 1)[-1])
    if kind == "household":
        file.start, file.end = svencionys.window(today, keep_days)
    else:
        file.year = 2026
    return svencionys.parse_file(file, fixture(f"svencionys/{COPIES[url]}"))


def by_name(result, kind, start):
    """The row of a kind whose name starts so."""
    (area,) = [a for a in result.areas if a.kind == kind and a.name.startswith(start)]
    return area


def days(area, month=None):
    return [d for d in sorted(area.dates) if month is None or (d.year, d.month) == month]


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, with a year of dates kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(svencionys.http, "get", serve)
        files, warnings = svencionys.download(TODAY, 366)
        registry = Registry.load(FIXTURES / REGISTRY)
        data, more = build_dataset(files, registry, TODAY, 366, svencionys.source())
    return files, data, warnings + more


def place(data, name, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name and district in (None, loc["district"])
    )


def rows(data, name, waste="household", district=None):
    """A place's rows of a kind."""
    schedule = place(data, name, district)["schedule"][waste]
    ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    by_id = {a["id"]: a for a in data["areas"]}
    return [by_id[i] for i in ids]


# --- the page ----------------------------------------------------------------


def test_finds_the_mixed_waste_and_packaging_files_by_their_links():
    files, warnings = svencionys.find_files(fixture("svencionys/page.html").decode("utf-8"))
    assert [(f.kind, f.url, f.year) for f in files] == [
        ("household", next(iter(COPIES)), None),
        ("packaging", list(COPIES)[1], 2026),
    ]
    # The shared containers' file ("Bendro naudojimo ...") isn't read, without a warning.
    assert warnings == []


def test_other_links():
    def page(*links):
        return "".join(f'<a href="{UPLOADS}{name}">{text}</a>' for text, name in links)

    files, warnings = svencionys.find_files(
        page(
            ("Didžiųjų atliekų surinkimo grafikas", "didziosios.pdf"),
            ("Pakuočių atliekų konteinerių tuštinimo grafikai", "Pakuociu-grafikai_2027.pdf"),
            ("Atliekų tvarkymo taisyklės", "taisykles.pdf"),
        )
    )
    assert [(f.kind, f.year) for f in files] == [("packaging", 2027)]
    assert warnings == [
        "didziosios.pdf ('Didžiųjų atliekų surinkimo grafikas'): a schedule of no kind we read"
    ]


def test_next_years_packaging_is_read_next_to_this_years():
    def file(kind, year, name):
        return svencionys.ScheduleFile(kind, f"{UPLOADS}{name}", name, year=year)

    mixed = file("household", None, "a.pdf")
    files = [mixed, file("packaging", 2025, "p25.pdf"), file("packaging", 2026, "p26.pdf")]
    chosen, warnings = svencionys.select_files([*files, file("packaging", 2027, "p27.pdf")], TODAY)
    assert [f.file_name for f in chosen] == ["a.pdf", "p26.pdf", "p27.pdf"]
    assert warnings == []
    # A second mixed waste file isn't read; last year's packaging only: read, with a warning.
    chosen, warnings = svencionys.select_files(
        [*files, file("household", None, "b.pdf")], date(2027, 1, 5)
    )
    assert [f.file_name for f in chosen] == ["a.pdf", "p26.pdf"]
    assert warnings == [
        "b.pdf: not read, a.pdf is linked first",
        "no packaging schedule for 2027 on the page",
    ]
    with pytest.raises(build.ValidationError, match="no mixed waste schedule"):
        svencionys.select_files(files[1:], TODAY)


# --- the rules -------------------------------------------------------------------


def test_rules_of_weeks_of_the_month():
    assert svencionys.parse_rule("I III PIRMADIENIS") == svencionys.Rule(0, (1, 3))
    assert svencionys.parse_rule("I-III antradienis") == svencionys.Rule(1, (1, 3))
    assert svencionys.parse_rule("II - IV Trečiadienis") == svencionys.Rule(2, (2, 4))
    assert svencionys.parse_rule("IV penktadienis") == svencionys.Rule(4, (4,))
    assert svencionys.parse_rule("II mėnesio trečiadienis") == svencionys.Rule(2, (2,))
    assert svencionys.parse_rule("I-III mėn. ketvirtadienis") == svencionys.Rule(3, (1, 3))
    for unknown in (
        "I-II pirmadienis",
        "I II III pirmadienis",
        "V pirmadienis",
        "I pirmadienį",
        "kas antrą pirmadienį",
        "III mėnesio",
    ):
        assert svencionys.parse_rule(unknown) is None, unknown


def test_a_rules_dates():
    start, end = date(2026, 11, 1), date(2027, 1, 31)
    # The first and the third Monday: days 1-7 and 15-21; three weeks from the third to the next
    # month's first.
    assert sorted(svencionys.Rule(0, (1, 3)).dates(start, end)) == [
        date(2026, 11, 2),
        date(2026, 11, 16),
        date(2026, 12, 7),
        date(2026, 12, 21),
        date(2027, 1, 4),
        date(2027, 1, 18),
    ]
    # The fourth Friday, on Christmas Day: not moved.
    assert date(2026, 12, 25) in svencionys.Rule(4, (2, 4)).dates(start, end)
    # In some months only.
    rule = svencionys.Rule(0, (2,), (1, 3, 5, 7, 9, 11))
    assert sorted(rule.dates(date(2026, 1, 1), date(2026, 12, 31)))[:2] == [
        date(2026, 1, 12),
        date(2026, 3, 9),
    ]


def test_the_window_of_the_rules_dates():
    assert svencionys.window(TODAY, 31) == (date(2026, 10, 22), date(2027, 12, 31))
    assert svencionys.window(date(2027, 1, 5), 31) == (date(2026, 12, 5), date(2028, 2, 29))


# --- the mixed waste file --------------------------------------------------------


def test_the_mixed_waste_rules():
    result = parsed("household")
    assert result.warnings == []
    names = [a.name for a in result.areas]
    assert len(names) == 16
    assert names[9:] == NORTH_MIXED
    # Pabradė's table: a row per column, its sections and places as the file writes them.
    monday = by_name(result, "household", "Pabradės sen.: Baltadvario k., Meškerinės II k.,")
    assert monday.name.endswith("Purviniškių k., Voverės vs., Pažeimenės k.")
    assert monday.weekday == "Pirmadienis"
    assert days(monday, (2026, 11)) == [date(2026, 11, 2), date(2026, 11, 16)]
    # "A.Mickevičiaus" "g." on two lines is one street.
    town = by_name(result, "household", "Pabradės m.: Keisūnų g., A.Mickevičiaus g., Strazdų g.")
    assert days(town, (2026, 11)) == [date(2026, 11, 9), date(2026, 11, 23)]
    # Two sections, "Magūnu sen." as the register writes it, and the apartment buildings'
    # containers ("Pabradės m. daugiabučiai namai") not read.
    tuesday = by_name(result, "household", "Pabradės sen.: Žvėrinės g., Skirlėnų k.,")
    assert "; Magūnų sen.: Dalininkų k., Vėblių k.," in tuesday.name
    assert tuesday.name.endswith("Molių k., Bendrovės k.")
    assert "daugiab" not in " ".join(names)
    wednesday = by_name(result, "household", "Pabradės sen.: Mečankos k.,")
    assert "; Magūnų sen.: Družilių k.," in wednesday.name
    # The window: from 31 days back to the end of December 2027.
    town = by_name(result, "household", "Švenčionių miestas")
    assert (min(town.dates), max(town.dates)) == (date(2026, 10, 28), date(2027, 12, 22))
    assert town.weekday == "Trečiadienis"
    # A holiday isn't moved: New Year's Day 2027 is the first Friday.
    labanoras = by_name(result, "household", "Labanoro seniūnija")
    assert date(2027, 1, 1) in labanoras.dates
    assert {a.district for a in result.areas} == {"Švenčionių r."}


def test_the_mixed_waste_file_needs_a_window():
    file = svencionys.ScheduleFile("household", next(iter(COPIES)), "m.pdf")
    with pytest.raises(ValueError, match="no window"):
        svencionys.parse_file(file, fixture("svencionys/misrios-2025.pdf"))


# --- the packaging file ----------------------------------------------------------


def test_the_nine_elderships_dates_and_pabrades_rules():
    result = parsed("packaging")
    assert result.warnings == []
    kinds = sorted(a.kind for a in result.areas)
    assert kinds == ["glass"] * 13 + ["packaging"] * 13
    # The nine elderships: the header's rule ("II mėnesio trečiadienis") is not in the name.
    town = by_name(result, "packaging", "Švenčionių miestas")
    assert town.name == "Švenčionių miestas"
    assert len(town.dates) == 12
    assert (min(town.dates), max(town.dates)) == (date(2026, 1, 14), date(2026, 12, 9))
    # The second Wednesday, on the holiday of 11 March too.
    assert date(2026, 3, 11) in town.dates
    glass = by_name(result, "glass", "Švenčionių seniūnija")
    assert days(glass) == [date(2026, 3, 2), date(2026, 6, 1), date(2026, 9, 7), date(2026, 12, 7)]
    # Pabradė's rules: the fourth Monday of every month, and glass the second Monday of every
    # other month, of the file's year.
    monday = by_name(result, "packaging", "Pabradės m.: Keisūnų g., Mickevičiaus g.,")
    assert monday.name.endswith("Mokyklos g., Ažubalio g.")
    assert len(monday.dates) == 12
    assert (min(monday.dates), max(monday.dates)) == (date(2026, 1, 26), date(2026, 12, 28))
    glass = by_name(result, "glass", "Pabradės m.: Keisūnų g.,")
    assert days(glass) == [
        date(2026, 1, 12),
        date(2026, 3, 9),
        date(2026, 5, 11),
        date(2026, 7, 13),
        date(2026, 9, 14),
        date(2026, 11, 9),
    ]
    # The column that goes on over a page, a garden community, and a village of the eldership.
    thursday = by_name(result, "packaging", "Pabradės m.: Perėjimo g.,")
    assert "Bajorėlių g., Pušaitės sodų bendrija, Taikos g., Šlaito g." in thursday.name
    assert thursday.name.endswith("Didlaukio g.; Pabradės sen.: Pušalotos k.")
    villages = by_name(result, "glass", "Magūnų sen.: Bendrovės k.,")
    assert villages.name.endswith("; Pabradės sen.: Karkažiškės k., Navasiolkų k., Maleikėnų k.")
    # The first Thursday of January is New Year's Day.
    assert min(by_name(result, "glass", "Pabradės sen.: Naujadvario k.").dates) == date(2026, 1, 1)


def test_a_title_of_another_year_fails():
    file = svencionys.ScheduleFile("packaging", list(COPIES)[1], "p.pdf", year=2027)
    with pytest.raises(ValueError, match="the tables are of 2026, the link says 2027"):
        svencionys.parse_file(file, fixture("svencionys/pakuotes-2026.pdf"))
    file = svencionys.ScheduleFile("packaging", list(COPIES)[1], "p.pdf")
    with pytest.raises(ValueError, match="isn't of the packaging"):
        svencionys.parse_file(file, fixture("svencionys/misrios-2025.pdf"))


def test_dates_off_their_rule_are_a_warning(monkeypatch):
    read = svencionys._dated

    def moved(rows, kind, year, where):
        """The second Wednesday of March on the Thursday after it."""
        columns = read(rows, kind, year, where)
        text, rule, dates = columns[0]
        columns[0] = (text, rule, dates - {date(2026, 3, 11)} | {date(2026, 3, 12)})
        return columns

    monkeypatch.setattr(svencionys, "_dated", moved)
    result = parsed("packaging")
    assert result.warnings == [
        "Pakuociu-atlieku-isvezimo-grafikai_2026.pdf: packaging of 'Švenčionių miestas' on "
        "2026-03-12, not its rule's"
    ]
    # Glass has no rule in its header.
    assert len(result.areas) == 26


def test_dated_tables_are_strict():
    header = ["Švenčionių miestas II mėnesio trečiadienis", "Švenčionėlių miestas"]
    rows = [header] + [[f"{m:02}.14", f"{m:02}.15"] for m in range(1, 13)]
    (text, rule, dates), (other, none, _) = svencionys._dated(rows, "packaging", 2026, "x")
    assert (text, rule, other, none) == (
        "Švenčionių miestas",
        svencionys.Rule(2, (2,)),
        "Švenčionėlių miestas",
        None,
    )
    assert len(dates) == 12
    with pytest.raises(ValueError, match="not a date: '1.14'"):
        svencionys._dated([header, ["1.14", "01.15"]], "glass", 2026, "x")
    with pytest.raises(ValueError, match="2026 has no day '02.30'"):
        svencionys._dated([header, ["02.30", "01.15"]], "glass", 2026, "x")
    with pytest.raises(ValueError, match="not in every month"):
        svencionys._dated(rows[:12], "packaging", 2026, "x")


# --- the strict reading ----------------------------------------------------------

SOUTH = ["PIRMADIENIS", "ANTRADIENIS"]
NINE = (
    "Adutiškio, Cirkliškio, Kaltanėnų, Labanoro, Sarių, Strūnaičio, Svirkų, Švenčionėlių, "
    "Švenčionių"
)


def mixed_blocks(south_weeks=("I III", "II IV"), extra=()):
    return [
        "Mišriosios komunalinės atliekos:",
        "Pabradės ir Magūnų seniūnijos:",
        [SOUTH, list(south_weeks), ["Pabradės sen.\nBaltadvario k.", "Pabradės m.\nKeisūnų g."]],
        *extra,
        f"{NINE} seniūnijos:",
        [["PIRMADIENIS"], ["I-III"], ["Labanoro seniūnija"]],
    ]


def test_the_files_blocks_are_strict():
    tables, months = svencionys._read(mixed_blocks(), "household", "x")
    assert [(t.part == svencionys.SOUTH, t.kind) for t in tables] == [
        (True, "household"),
        (False, "household"),
    ]
    assert months == {}
    with pytest.raises(ValueError, match="text we don't read next to the tables: 'Švenčių"):
        svencionys._read(
            mixed_blocks(extra=["Švenčių dienomis atliekos vežamos kitą dieną."]), "household", "x"
        )
    with pytest.raises(ValueError, match="isn't of the mixed waste"):
        svencionys._read(["Mišrios atliekos:", *mixed_blocks()[1:]], "household", "x")
    with pytest.raises(ValueError, match="an eldership the register doesn't have: 'Vilniaus'"):
        svencionys._read(
            [*mixed_blocks()[:1], "Pabradės ir Vilniaus seniūnijos:"], "household", "x"
        )
    with pytest.raises(ValueError, match="tables of"):
        svencionys._read(mixed_blocks()[:3], "household", "x")
    # A table that goes on over a page: its cells join the last row's.
    blocks = mixed_blocks()
    blocks.insert(3, [["Meškerinės k.", "Vytauto g."]])
    tables, _ = svencionys._read(blocks, "household", "x")
    assert tables[0].rows[2] == [
        "Pabradės sen.\nBaltadvario k.\nMeškerinės k.",
        "Pabradės m.\nKeisūnų g.\nVytauto g.",
    ]


def test_the_notes_of_the_months():
    blocks = [
        "INDIVIDUALIŲ PAKUOČIŲ ATLIEKŲ KONTEINERIŲ TUŠTINIMO GRAFIKAI:",
        "Magūnų ir Pabradės seniūnijos:",
        "2026 M. STIKLO PAKUOČIŲ ATLIEKŲ KONTEINERIŲ TUŠTINIMO GRAFIKAS",
        [SOUTH, ["II", "II"], ["Pabradės m.: Keisūnų g.", "Pabradės m.: Vilniaus g."]],
        "Stiklo pakuočių atliekų konteineriai Pabradės ir Magūnų seniūnijose tuštinami kas antrą "
        "mėnesį (02, 04, 06, 08, 10, 12).",
    ]
    # The months are right, but the file has one of its four tables.
    with pytest.raises(ValueError, match="tables of"):
        svencionys._read(blocks, "packaging", "x")
    for wrong in ("(01, 02, 03)", "(01, 05, 09)", "(03, 05, 07, 09, 11)"):
        note = blocks[-1].replace("(02, 04, 06, 08, 10, 12)", wrong)
        with pytest.raises(ValueError, match="the months of a note"):
            svencionys._read([*blocks[:-1], note], "packaging", "x")


def test_weekday_tables_are_strict():
    columns = svencionys._columns(
        [["PIRMADIENIS", None, None, None], ["I", "III", "II", "IV"], ["a", None, "b", None]], "x"
    )
    assert columns == [(svencionys.Rule(0, (1, 3)), "a"), (svencionys.Rule(0, (2, 4)), "b")]
    with pytest.raises(ValueError, match="weeks of the month we don't read: 'I II'"):
        svencionys._columns([["PIRMADIENIS", None], ["I", "II"], ["a", None]], "x")
    with pytest.raises(ValueError, match="across two weekdays"):
        svencionys._columns([["PIRMADIENIS", "ANTRADIENIS"], ["I", "III"], ["a", None]], "x")
    with pytest.raises(ValueError, match="'SEKMADIENIAI' for a weekday"):
        svencionys._columns([["SEKMADIENIAI"], ["I"], ["a"]], "x")
    with pytest.raises(ValueError, match="no places on IV Pirmadienis"):
        svencionys._columns([["PIRMADIENIS"], ["IV"], [""]], "x")


def test_pabrades_places_are_strict():
    # As the packaging file writes them, a place or a section over two lines.
    text = "Pabradės m.:\nKeisūnų g.,\nPušaitės sodų\nbendrija,\nPabradės\nseniūnija:\nPušalotos k."
    assert svencionys.south_places(text, "x") == (
        "Pabradės m.: Keisūnų g., Pušaitės sodų bendrija; Pabradės sen.: Pušalotos k."
    )
    for text, error in (
        ("Baltadvario k.", "under no eldership or town"),
        ("Pabradės sen.\nBaltadvario", "places of no known kind: 'Baltadvario'"),
        ("Pabradės sen.\nBaltadvario km.", "places of no known kind"),
        ("Vilniaus sen.\nBaltadvario k.", "an eldership of no Pabradė table"),
        ("Švenčionių m.\nVilniaus g.", "a town of no eldership of Pabradė's tables"),
        ("Pabradės sen.\nA k.\nPabradės sen.\nB k.", "Pabradės sen. twice"),
        ("Pabradės sen.\nPabradės m.\nVilniaus g.", "a section without places"),
    ):
        with pytest.raises(ValueError, match=error):
            svencionys.south_places(text, "x")


def test_the_nine_elderships_places_are_strict():
    parts = svencionys.north_parts(NORTH_MIXED[1])
    assert parts == [
        svencionys.Part("elderships", ("Adutiškio", "Svirkų")),
        svencionys.Part("villages", ("Milkuškų", "Kukiškės", "Medišionių")),
    ]
    assert svencionys.north_parts(
        "Švenčionių seniūnija (išskyrus Švenčionių miestą, Milkuškų, Kukiškės kaimus)"
    ) == [svencionys.Part("elderships", ("Švenčionių",), ("Milkuškų", "Kukiškės"), "Švenčionių")]
    svencionys.check_north(NORTH_MIXED, "x")
    for texts, error in (
        (NORTH_MIXED[1:], r"named whole are \['Adutiškio'"),
        ([*NORTH_MIXED, "Sarių seniūnija"], "named whole are"),
        ([NORTH_MIXED[0].replace("Kukiškės, ", ""), *NORTH_MIXED[1:]], "villages left out"),
        # The town left out of its eldership, and no column of its own.
        (
            [NORTH_MIXED[0].replace("(išskyrus", "(išskyrus Švenčionių miestą,"), *NORTH_MIXED[1:3]]
            + NORTH_MIXED[4:],
            r"no column of \['Švenčionių'\]",
        ),
    ):
        with pytest.raises(ValueError, match=error):
            svencionys.check_north(texts, "x")
    for text, error in (
        ("Pabradės seniūnija", "an eldership read place by place"),
        ("Vilniaus seniūnija", "an eldership the register doesn't have"),
        ("Pabradės miestas", "a town we don't know"),
        ("Labanoro seniūnija, Berniūnų kaimas", "places we don't read"),
        ("Labanoro seniūnija (be Berniūnų kaimo)", "places we don't read"),
        ("Labanoro seniūnija (išskyrus Berniūnų kaimą)", "places left out we don't read"),
    ):
        with pytest.raises(ValueError, match=error):
            svencionys.north_parts(text, "x")


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 565
    # Every settlement of the nine elderships, and the villages Pabradė's table names: 43 small
    # villages of Pabradės and Magūnų sen. aren't in it. Pažeimenė is in two columns.
    assert (
        stats["household.single"],
        stats["household.byStreet"],
        stats["household.ambiguous"],
        stats["household.none"],
    ) == (520, 1, 1, 43)
    # Pabradė's and Magūnai's packaging: the town's streets and ten villages.
    for kind in ("packaging", "glass"):
        assert (stats[f"{kind}.single"], stats[f"{kind}.byStreet"], stats[f"{kind}.none"]) == (
            449,
            1,
            115,
        ), kind
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 16, "packaging": 13, "glass": 13}
    assert warnings == []


def test_the_nine_elderships(built):
    _, data, _ = built
    # A village of Švenčionių sen. left out of its row is the Tuesday row's.
    (row,) = rows(data, "Milkuškos")
    assert row["name"] == NORTH_MIXED[1]
    (row,) = rows(data, "Šventa")
    assert row["name"] == NORTH_MIXED[0]
    # Two Žvirbliškės: Kaltanėnų sen.'s is left out of its row and named by Labanoro's; Švenčionių
    # sen.'s is in its eldership's row.
    (row,) = rows(data, "Žvirbliškė", district="Kaltanėnų")
    assert row["name"] == NORTH_MIXED[6]
    (row,) = rows(data, "Žvirbliškė", district="Švenčionių")
    assert row["name"] == NORTH_MIXED[0]
    (row,) = rows(data, "Žvirbliškė", "packaging", district="Kaltanėnų")
    assert row["name"].startswith("Labanoro seniūnija")
    # The towns are named whole; Platumai with Švenčionėliai for packaging.
    (row,) = rows(data, "Švenčionys")
    assert row["name"] == "Švenčionių miestas"
    (row,) = rows(data, "Platumai", "packaging")
    assert row["name"] == "Švenčionėlių miestas ir Platumų kaimas"
    (row,) = rows(data, "Platumai")
    assert row["name"].startswith("Švenčionėlių ir Kaltanėnų seniūnijos")
    # Cirkliškis: the first and the third Wednesday, 4 November 2026 to 15 December 2027.
    (row,) = rows(data, "Cirkliškis")
    assert row["name"] == "Sarių, Cirkliškio, Strūnaičio seniūnijos"
    assert (row["dates"][0], row["dates"][-1]) == ("2025-12-03", "2027-12-15")


def test_pabrade_and_magunai(built):
    _, data, _ = built
    (row,) = rows(data, "Pavoverė")
    assert row["name"].startswith("Pabradės sen.: Naujadvario k.,")
    (row,) = rows(data, "Prienai")
    assert row["weekday"] == "Antradienis" and "Magūnų sen.:" in row["name"]
    # "Burbiškių I k." (an alias) and "Burbiškės II k." (one letter off).
    (row,) = rows(data, "Burbliškė I")
    assert row["weekday"] == "Penktadienis"
    (row,) = rows(data, "Burbliškė II")
    assert row["weekday"] == "Ketvirtadienis"
    # "Silniškų vs." and "Pušalotos k." are in the town's columns.
    (row,) = rows(data, "Silniškiai")
    assert row["name"].startswith("Pabradės m.: Vilniaus g.,")
    # Pažeimenė is in two columns: the app asks.
    assert sorted(r["weekday"] for r in rows(data, "Pažeimenė")) == [
        "Ketvirtadienis",
        "Pirmadienis",
    ]
    # Villages no row names have none.
    assert "household" not in place(data, "Brižiai").get("schedule", {})


def test_the_towns_streets(built):
    _, data, _ = built
    town = place(data, "Pabradė")
    assert (town["type"], town["district"]) == ("m.", "Pabradės")
    streets = {label: key for key, label in town["streets"]}
    by_id = {a["id"]: a for a in data["areas"]}

    def route(street, kind="household"):
        (one,) = town["schedule"][kind]["streets"][streets[street]]
        return by_id[one]["name"].split(",")[0], by_id[one]["weekday"]

    assert route("Keisūnų g.") == ("Pabradės m.: Keisūnų g.", "Pirmadienis")
    # "Ažubalio g." is Ažubalių g.; "Mickevičiaus g." A. Mickevičiaus g.
    assert route("Ažubalių g.") == ("Pabradės m.: Keisūnų g.", "Pirmadienis")
    assert route("A. Mickevičiaus g.", "packaging") == ("Pabradės m.: Keisūnų g.", "Pirmadienis")
    # Žvėrinės g. is in the Pabradės sen. column on Tuesdays, and the town's on Fridays for
    # packaging.
    assert route("Žvėrinės g.") == ("Pabradės sen.: Žvėrinės g.", "Antradienis")
    assert route("Žvėrinės g.", "glass") == ("Pabradės m.: Vasaros g.", "Penktadienis")
    # The garden community "Pušaitės SB" is the town's Pušaitės 1-oji g. to 12-oji g.
    for number in (1, 7, 12):
        assert route(f"Pušaitės {number}-oji g.") == ("Pabradės m.: Perėjimo g.", "Ketvirtadienis")
    # Streets no row names are left to the app.
    by_street = town["schedule"]["household"]["streets"]
    for street in ("Architektų g.", "Gamyklos g.", "Pušų skg."):
        assert streets[street] not in by_street
    assert len(by_street) == 66


# --- a file that can't be read, next year, and the folder -------------------------


def test_a_file_that_cant_be_read_keeps_yesterdays_rows(built):
    files, data, _ = built
    published = merge_parts(
        [(svencionys.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-21"})],
        svencionys.PAGE_URL,
    )
    mixed, packaging = (f for f, _ in files)
    result = svencionys.parse_or_keep(mixed, b"", lambda: published)
    assert len(result.areas) == 16
    assert {a.kind for a in result.areas} == {"household"}
    assert "yesterday's 16 mixed waste rows are kept" in result.warnings[0]
    result = svencionys.parse_or_keep(packaging, b"", lambda: published)
    assert sorted({a.kind for a in result.areas}) == ["glass", "packaging"]
    assert len(result.areas) == 26
    with pytest.raises(ValueError, match="not downloaded"):
        svencionys.parse_or_keep(mixed, b"", None)


def test_next_years_packaging_continues_this_years(built):
    files, _, _ = built
    _, packaging = (f for f, _ in files)
    this = parsed("packaging")
    following = parsed("packaging")
    # The same rows a year (53 weeks) later.
    for area in following.areas:
        area.dates = {d + timedelta(weeks=53) for d in area.dates}
    registry = Registry.load(FIXTURES / REGISTRY)
    mixed = parsed("household")
    pairs = [(files[0][0], mixed), (packaging, this), (packaging, following)]
    assert svencionys.combine(pairs, registry, TODAY) == []
    town = by_name(this, "packaging", "Švenčionių miestas")
    assert len(town.dates) == 24 and max(town.dates).year == 2027
    assert following.areas == []
    # Mixed waste's rows aren't joined, whatever the year of their first date.
    assert len(mixed.areas) == 16


def refused(url, timeout=0):
    raise OSError("HTTP Error 403: Forbidden")


def test_the_copy_when_the_site_refuses_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(svencionys.http, "get", serve)
    copy = tmp_path / "copy"
    assert svencionys.save_copy(copy, TODAY)
    # As Ukmergės r.'s: the page, the files read today named after their URLs, and copy.json.
    index = json.loads((copy / "copy.json").read_text(encoding="utf-8"))
    names = [url.rsplit("/", 1)[-1] for url in COPIES]
    assert index == {"takenAt": "2026-11-22", "page": svencionys.PAGE_URL, "files": names}
    assert sorted(p.name for p in copy.iterdir()) == sorted([*names, "copy.json", "page.html"])
    # Saved again with the same files: no change.
    assert not svencionys.save_copy(copy, TODAY)

    monkeypatch.setattr(svencionys.http, "get", refused)
    monkeypatch.setattr(svencionys, "COPY_DIR", copy)
    files, warnings = svencionys.download(TODAY, 31)
    assert [(f.kind, content) for f, content in files] == [
        ("household", fixture("svencionys/misrios-2025.pdf")),
        ("packaging", fixture("svencionys/pakuotes-2026.pdf")),
    ]
    assert files[0][0].start == date(2026, 10, 22)
    assert warnings == [
        f"{svencionys.PAGE_URL}: unavailable (HTTP Error 403: Forbidden); used the copy from "
        "2026-11-22 (0 days old)"
    ]
    # Without a copy, the error.
    monkeypatch.setattr(svencionys, "COPY_DIR", tmp_path / "none")
    with pytest.raises(OSError, match="403"):
        svencionys.download(TODAY, 31)


def test_the_committed_copy_can_be_built(monkeypatch):
    """The copy in pipeline/data, as the daily job reads it on GitHub's runners (it is
    refreshed, so only that it builds: build_dataset checks the counts)."""
    monkeypatch.setattr(svencionys.http, "get", refused)
    files, warnings = svencionys.download(date.today(), 31)
    assert "used the copy from" in warnings[0]
    assert [f.kind for f, _ in files][0] == "household"
    registry = Registry.load(FIXTURES / REGISTRY)
    build_dataset(files, registry, date.today(), 31, svencionys.source())


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(svencionys.http, "get", serve)
    monkeypatch.setattr(svencionys.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(svencionys.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "svencioniu-r"
    assert svencionys.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["svencionys"]
    assert regions.region(tmp_path, out) == {
        "path": "svencioniu-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["svencionys"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="svencionys"} 522' in text

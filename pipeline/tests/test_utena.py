"""Utenos r.: the page of UAB „Utenos komunalininkas“, its two PDFs (the town's and the
elderships'), the elderships' mixed waste rules turned into dates, the town's streets, and
yesterday's rows for a file that can't be read."""

import json
from datetime import date
from urllib.parse import unquote

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, regions, status, utena
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 22)
CDN = "https://cdn.prod.website-files.com/6143098e1d46fa87629020db/"
# The files the page links, by their names, and their copies in fixtures/utena.
COPIES = {
    "694a59ac55201e09edb72731_Grafikas antrinių ir mišrių 2026 m. Utenos mieste.pdf": (
        "miestas-2026.pdf"
    ),
    "694a59b71aaf2605fe65b84c_Grafikas antrinių ir mišrių 2026 m. Utenos rajono seniūnijose.pdf": (
        "seniunijos-2026.pdf"
    ),
}
REGISTRY = "utena/registry-utenos-r-2026-11-22.json"
# The page's rules of the elderships' mixed waste.
RULES = (
    "Užpalių sen. – kiekvieno mėnesio pirmą dieną.",
    "Vyžuonų sen. – Sudeikių sen. – kiekvieno mėnesio ketvirtą dieną.",
    "Leliūnų sen. – kiekvieno mėnesio septintą dieną.",
    "Tauragnų sen. – Daugailių sen., Utenos sen. (Vaikutėnai) – kiekvieno mėnesio dešimtą dieną.",
    "Saldutiškio sen. – Kuktiškių sen. Utenos sen. ( visi kaimai) – kiekvieno mėnesio tryliktą "
    "dieną.",
)
VAIKUTENAI = "Tauragnų sen., Daugailių sen. ir Vaikutėnų k. (Utenos sen.)"
VILLAGES = "Saldutiškio sen., Kuktiškių sen. ir Utenos sen. (visi kaimai, išskyrus Vaikutėnų k.)"


def serve(url, timeout=0):
    """The saved page and files, as utena.http.get."""
    if url == utena.PAGE_URL:
        return fixture("utena/page.html")
    return fixture(f"utena/{COPIES[unquote(url.rsplit('/', 1)[-1])]}")


def parsed(copy, group, year=2026, rules=RULES):
    file = utena.ScheduleFile(
        "household", f"{CDN}{copy}", copy, group=group, year=year, rules=rules
    )
    return utena.parse_file(file, fixture(f"utena/{copy}"))


def days(dates):
    return sorted(dates)


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(utena.http, "get", serve)
        files, warnings = utena.download(TODAY, 366)
        registry = Registry.load(FIXTURES / REGISTRY)
        data, more = build_dataset(files, registry, TODAY, 366, utena.source())
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


def test_finds_the_towns_file_and_the_elderships_by_their_headings():
    files, warnings = utena.find_files(fixture("utena/page.html").decode("utf-8"))
    assert sorted(f.file_name for f in files) == sorted(COPIES)
    assert {f.group: f.year for f in files} == {"town": 2026, "district": 2026}
    assert all(f.url.startswith(CDN) and f.kind == "household" for f in files)
    # The page's rules go with the elderships' file.
    assert {f.group: f.rules for f in files} == {"town": (), "district": RULES}
    assert warnings == []


def test_next_years_file_is_read_next_to_this_years():
    def file(group, year, name="x.pdf"):
        url = f"{CDN}{group}{year}{name}"
        return utena.ScheduleFile("household", url, name, group=group, year=year)

    files = [file("town", 2026), file("district", 2026), file("town", 2027), file("town", 2025)]
    chosen, warnings = utena.select_files(files, TODAY)
    assert sorted((f.group, f.year) for f in chosen) == [
        ("district", 2026),
        ("town", 2026),
        ("town", 2027),
    ]
    assert warnings == []
    # Of two for one year, the one linked first.
    chosen, warnings = utena.select_files([*files, file("district", 2026, "y.pdf")], TODAY)
    assert warnings == ["y.pdf: not read, x.pdf is the district's schedule for 2026"]
    with pytest.raises(build.ValidationError, match="no schedule of the district"):
        utena.select_files([f for f in files if f.group == "town"], TODAY)
    # Last year's only: read, with a warning.
    chosen, warnings = utena.select_files(files[:2], date(2027, 1, 5))
    assert len(chosen) == 2
    assert warnings == [
        "no schedule of the town for 2027 on the page",
        "no schedule of the district for 2027 on the page",
    ]


def test_links_of_other_years_or_areas():
    def page(heading, name):
        return (
            f'<div class="blogs__download__item"><h6 class="headline-6">{heading}</h6>'
            f'<a href="{CDN}{name}" class="download-button">Atidaryti →</a></div>'
        )

    town = "Atliekų surinkimo apvažiavimo būdu Utenos mieste grafikai 2026 m."
    with pytest.raises(ValueError, match="a file of 2027, its heading says 2026"):
        utena.find_files(page(town, "694a59ac2026_Grafikas 2027 m. Utenos mieste.pdf"))
    files, warnings = utena.find_files(page(town, "694a59ac55201e09edb72731_Grafikas.pdf"))
    assert [(f.group, f.year) for f in files] == [("town", 2026)]
    other = "Atliekų surinkimo apvažiavimo būdu Utenos rajono kaimuose grafikai 2026 m."
    assert utena.find_files(page(other, "a.pdf")) == (
        [],
        [f"a.pdf: not read, a schedule of no area or year we read: {other!r}"],
    )
    # Other PDFs (the contract, the prices) aren't schedules.
    assert utena.find_files(page("Paslaugos teikimo sutartis", "b.pdf")) == ([], [])


# --- the rules -------------------------------------------------------------------


def test_rules_of_a_day_of_every_month():
    assert utena.parse_rule("kiekvieno mėnesio pirmą dieną") == utena.Rule(1)
    assert utena.parse_rule("Kiekvieno  mėnesio tryliktą dieną.") == utena.Rule(13)
    assert utena.parse_rule("kiekvieno mėnesio dvidešimt pirmą dieną") == utena.Rule(21)
    assert utena.parse_rule("kiekvieno mėnesio dvidešimtą dieną") == utena.Rule(20)
    for unknown in (
        "kiekvieno mėnesio pirmą savaitę",
        "kas 14 dienų",
        "kiekvieno mėnesio 1 dieną",
        "kiekvieno mėnesio dvidešimt dešimtą dieną",
        "kiekvieno mėnesio trisdešimt antrą dieną",
        "kiekvieno mėnesio pirmą ir penkioliktą dieną",
    ):
        assert utena.parse_rule(unknown) is None, unknown
    with pytest.raises(ValueError, match="2026-02 hasn't one"):
        utena.parse_rule("kiekvieno mėnesio trisdešimtą dieną").dates(2026)


def test_holidays_and_sundays_move_to_the_next_day():
    assert [utena.easter(y) for y in (2025, 2026, 2027)] == [
        date(2025, 4, 20),
        date(2026, 4, 5),
        date(2027, 3, 28),
    ]
    assert {date(2026, 4, 6), date(2026, 11, 2), date(2026, 12, 24)} <= utena.holidays(2026)
    first = days(utena.Rule(1).dates(2026))
    # 1 January (a holiday) is a Thursday, 1 February and 1 March are Sundays, 1 May (a holiday)
    # is a Friday: collected on Saturday the 2nd. 1 November is a Sunday and 2 November a
    # holiday. 1 August is a Saturday: not moved.
    assert first == [
        date(2026, 1, 2),
        date(2026, 2, 2),
        date(2026, 3, 2),
        date(2026, 4, 1),
        date(2026, 5, 2),
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 1),
        date(2026, 9, 1),
        date(2026, 10, 1),
        date(2026, 11, 3),
        date(2026, 12, 1),
    ]
    thirteenth = days(utena.Rule(13).dates(2026))
    assert [d for d in thirteenth if d.day != 13] == [date(2026, 9, 14), date(2026, 12, 14)]


def test_the_places_of_the_rules():
    assert utena.rule_places("Vyžuonų sen., Sudeikių sen.") == [
        utena.Part("Vyžuonų"),
        utena.Part("Sudeikių"),
    ]
    assert utena.rule_places(VAIKUTENAI) == [
        utena.Part("Tauragnų"),
        utena.Part("Daugailių"),
        utena.Part("Utenos", village="Vaikutėnų k."),
    ]
    assert utena.rule_places(VILLAGES)[2] == utena.Part("Utenos", but=("Vaikutėnų k.",))
    with pytest.raises(ValueError, match="places of no known kind: 'Vaikutėnų k.'"):
        utena.rule_places("Tauragnų sen. ir Vaikutėnų k.")
    with pytest.raises(ValueError, match="an eldership the register doesn't have"):
        utena.rule_places("Utenio sen.")


def test_rules_in_other_words_fail():
    text = (
        "Pastaba: neišvežus atliekų nustatytą dieną, jos vežamos artimiausią darbo dieną.\n"
        "Mišrių komunalinių atliekų išvežimas Utenos rajono seniūnijose 2026 m.\n"
        "Užpalių sen., Vyžuonų sen., Sudeikių sen., Leliūnų sen. - kiekvieno mėnesio pirmą\n"
        "dieną.\n"
        f"{VAIKUTENAI} - kiekvieno mėnesio dešimtą dieną.\n"
        f"{VILLAGES} - kiekvieno mėnesio tryliktą dieną.\n"
        "Pastaba: atliekų išvežimo dienai sutapus su šventine diena ar sekmadieniu, atliekos bus "
        "vežamos artimiausią darbo dieną."
    )
    # A rule on two lines.
    rules = utena._rules(text, 2026, "x")
    assert [(r.rule.day, len(r.parts)) for r in rules] == [(1, 4), (10, 3), (13, 3)]
    with pytest.raises(ValueError, match="rules of .* in a file of 2027"):
        utena._rules(text, 2027, "x")
    with pytest.raises(ValueError, match="unrecognised mixed waste rule: 'Užpalių sen., .*"):
        utena._rules(text.replace("pirmą\n", "pirmą savaitės\n"), 2026, "x")
    with pytest.raises(ValueError, match="a note under the mixed waste rules"):
        utena._rules(text.replace("artimiausią darbo dieną.", "ankstesnę darbo dieną."), 2026, "x")
    with pytest.raises(ValueError, match="mixed waste rules for all villages of"):
        utena._rules(text.replace(", Leliūnų sen.", ""), 2026, "x")
    with pytest.raises(ValueError, match="mixed waste rules for all villages of"):
        utena._rules(text.replace("Tauragnų sen.,", "Užpalių sen.,"), 2026, "x")
    with pytest.raises(ValueError, match=r"no mixed waste rule for \['Vaikutėnų k.'\]"):
        utena._rules(text.replace(" ir Vaikutėnų k. (Utenos sen.)", ""), 2026, "x")
    with pytest.raises(ValueError, match="0 headings"):
        utena._rules(text.replace("2026 m.", "2026 metais"), 2026, "x")


# --- the files -------------------------------------------------------------------


def test_the_towns_routes():
    result = parsed("miestas-2026.pdf", "town")
    kinds = sorted(a.kind for a in result.areas)
    assert kinds == ["glass"] * 3 + ["green"] * 3 + ["household"] * 3 + ["packaging"] * 3
    first, second, third = (a for a in result.areas if a.kind == "household")
    assert first.name.startswith("Utenos m.: Algirdo g., Ąžuolijos g., Bažnyčios g.,")
    assert second.name.startswith("Utenos m.: A. Baranausko, Alyvų g.,")
    assert third.name.endswith("Žemdirbių g., Žirgapievio g., Žirgų g.")
    # "12; 26 | 9; 23 | ... | 3; 16;\n30 | 14; 28": every other Monday; Tuesday 3 November after
    # the holiday on Monday.
    assert days(first.dates)[:3] == [date(2026, 1, 12), date(2026, 1, 26), date(2026, 2, 9)]
    assert [d for d in days(first.dates) if d.month == 11] == [
        date(2026, 11, 3),
        date(2026, 11, 16),
        date(2026, 11, 30),
    ]
    assert len(first.dates) == 26 and first.weekday is None
    green = next(a for a in result.areas if a.kind == "green" and a.name == first.name)
    # "5; 12;\n19; 26" in May: every week in summer.
    assert [d.day for d in days(green.dates) if d.month == 5] == [5, 12, 19, 26]
    glass = next(a for a in result.areas if a.kind == "glass" and a.name == first.name)
    assert days(glass.dates) == [
        date(2026, 1, 19),
        date(2026, 4, 27),
        date(2026, 7, 20),
        date(2026, 10, 26),
    ]
    assert glass.weekday == "Pirmadienis"
    # Bulky and hazardous waste ("Pavojingos, didelių gabaritų") isn't read.
    assert result.warnings == []
    assert {a.district for a in result.areas} == {"Utenos r."}


def test_the_elderships_packaging_glass_and_mixed_waste():
    result = parsed("seniunijos-2026.pdf", "district")
    by_kind = {}
    for area in result.areas:
        by_kind.setdefault(area.kind, []).append(area)
    assert sorted(a.name for a in by_kind["packaging"]) == sorted(
        f"{e} sen." for e in utena.ELDERSHIPS
    )
    assert len(by_kind["glass"]) == 9
    assert [a.name for a in by_kind["household"]] == [
        "Užpalių sen.",
        "Vyžuonų sen., Sudeikių sen.",
        "Leliūnų sen.",
        VAIKUTENAI,
        VILLAGES,
    ]
    leliunai = next(a for a in by_kind["packaging"] if a.name == "Leliūnų sen.")
    # "22 | 20 | 19 | ... | 21".
    assert days(leliunai.dates)[:3] == [date(2026, 1, 22), date(2026, 2, 20), date(2026, 3, 19)]
    assert len(leliunai.dates) == 12
    vaikutenai = next(a for a in by_kind["household"] if a.name == VAIKUTENAI)
    # The tenth of every month; 10 May is a Sunday.
    assert len(vaikutenai.dates) == 12
    assert [d for d in days(vaikutenai.dates) if d.day != 10] == [date(2026, 5, 11)]
    # The page's rules say the same.
    assert result.warnings == []


def test_the_pages_rules_are_checked_against_the_files():
    moved = (*RULES[:2], RULES[2].replace("septintą", "aštuntą"), *RULES[3:])
    result = parsed("seniunijos-2026.pdf", "district", rules=moved)
    assert len(result.warnings) == 1
    assert "the page's mixed waste rules aren't the file's: Užpalių sen. –" in result.warnings[0]
    result = parsed("seniunijos-2026.pdf", "district", rules=())
    assert result.warnings == [
        "seniunijos-2026.pdf: the page has no mixed waste rules to check the file's"
    ]


def test_a_title_of_the_other_file_or_another_year_fails():
    with pytest.raises(ValueError, match="isn't of the district"):
        parsed("miestas-2026.pdf", "district")
    with pytest.raises(ValueError, match="the title says 2026, the link 2027"):
        parsed("seniunijos-2026.pdf", "district", year=2027)


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 585
    # Every settlement has mixed waste, packaging and glass; the town by street.
    for kind in ("household", "packaging", "glass"):
        assert (stats[f"{kind}.single"], stats[f"{kind}.byStreet"]) == (584, 1), kind
        assert stats.get(f"{kind}.ambiguous", 0) == stats.get(f"{kind}.none", 0) == 0
    assert (stats["green.byStreet"], stats["green.none"]) == (1, 584)
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 8, "packaging": 12, "glass": 12, "green": 3}
    # "Draugystės g." of the second route: the register has Draugystės a. (the first route's)
    # and Draugystės 1-oji g. to 18-oji g., no Draugystės g.
    assert warnings == [
        f"not a settlement or a street: {kind}: Utenos m.: Draugystės g."
        for kind in ("household", "green", "packaging", "glass")
    ]


def test_villages_of_utenos_sen(built):
    _, data, _ = built
    # Vaikutėnai is named by the rule of the tenth, the other villages of Utenos sen. have the
    # rule of the thirteenth.
    (row,) = rows(data, "Vaikutėnai")
    assert row["name"] == VAIKUTENAI
    assert (len(row["dates"]), row["dates"][0], row["dates"][-1]) == (
        12,
        "2026-01-10",
        "2026-12-10",
    )
    (row,) = rows(data, "Nemeikščiai", district="Utenos")
    assert row["name"] == VILLAGES
    assert (len(row["dates"]), row["dates"][0], row["dates"][-1]) == (
        12,
        "2026-01-13",
        "2026-12-14",
    )
    (row,) = rows(data, "Vaikutėnai", "packaging")
    assert row["name"] == "Utenos sen."
    # A village of Užpalių sen.: the first of every month.
    (row,) = rows(data, "Užpaliai")
    assert row["name"] == "Užpalių sen."
    assert (row["dates"][0], row["dates"][-1]) == ("2026-01-02", "2026-12-01")


def test_the_towns_streets(built):
    _, data, _ = built
    town = place(data, "Utena")
    assert (town["type"], town["district"]) == ("m.", "Utenos miesto")
    streets = {label: key for key, label in town["streets"]}
    by_id = {a["id"]: a for a in data["areas"]}

    def route(street, kind="household"):
        (one,) = town["schedule"][kind]["streets"][streets[street]]
        return by_id[one]["name"].split(",")[0]

    assert route("Kalno g.") == "Utenos m.: Aukštaičių g."
    assert route("A. Baranausko g.") == "Utenos m.: A. Baranausko"
    # "Draugystės a." of the first route, not "Draugystės g." of the second.
    assert route("Draugystės a.") == "Utenos m.: Algirdo g."
    # "Lanko g..", and "Papievių g. Pienių g." without a comma.
    assert route("Lanko g.") == "Utenos m.: A. Baranausko"
    assert route("Pienių g.", "packaging") == "Utenos m.: Aukštaičių g."
    # Streets no route names are left to the app.
    by_street = town["schedule"]["household"]["streets"]
    for street in ("Pramonės g.", "Draugystės 13-oji g.", "Alyvų aklg."):
        assert streets[street] not in by_street
    assert len(by_street) == 141


# --- a file that can't be read, and the folder -----------------------------------


def test_a_file_that_cant_be_read_keeps_yesterdays_rows(built):
    files, data, _ = built
    published = merge_parts(
        [(utena.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-21"})],
        utena.PAGE_URL,
    )
    town, district = sorted((f for f, _ in files), key=lambda f: f.group != "town")
    result = utena.parse_or_keep(town, b"", lambda: published)
    assert len(result.areas) == 12
    assert all(a.name.startswith("Utenos m.:") for a in result.areas)
    assert "yesterday's 12 rows of the town are kept" in result.warnings[0]
    result = utena.parse_or_keep(district, b"", lambda: published)
    assert len(result.areas) == 23
    with pytest.raises(ValueError, match="not downloaded"):
        utena.parse_or_keep(town, b"", None)


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(utena.http, "get", serve)
    monkeypatch.setattr(utena.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(utena.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "utenos-r"
    assert utena.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["utena"]
    assert regions.region(tmp_path, out) == {
        "path": "utenos-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["utena"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="utena"} 585' in text

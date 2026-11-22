"""Kupiškio r.: the page of UAB „Kupiškio komunalininkas“, its mixed waste rules turned into
dates, the town's dated schedule they are checked against, the half year's packaging and glass
file, the food waste file, and the places."""

import json
import re
from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import aratc, build, kupiskis, regions, status, svara
from schedule_pipeline.build import build_dataset
from schedule_pipeline.kretinga import ScheduleFile
from schedule_pipeline.model import ParseResult
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 22)
UPLOADS = "http://www.kupkom.lt/wp-content/uploads/2026/"
# The files the page links, and their copies in fixtures/kupiskis.
COPIES = {
    f"{UPLOADS}07/RUSIUOJAMUJU-ATLIEKU-SURINKIMO-GRAFIKAS-2026-1.pdf": "rusiuojamos-2026-2.pdf",
    f"{UPLOADS}01/2026-m.-Maisto-atlieku-surinkimo-grafikas.pdf": "maisto-2026.pdf",
    f"{UPLOADS}01/2026-m.-Misriu-atlieku-surinkimo-grafikas.pdf": "misrios-miestas-2026.pdf",
}
TOWN = f"{UPLOADS}01/2026-m.-Misriu-atlieku-surinkimo-grafikas.pdf"
REGISTRY = "kupiskis/registry-kupiskio-r-2026-11-22.json"
PAGE = fixture("kupiskis/page.html").decode("utf-8")
YEAR = (date(2026, 1, 1), date(2026, 12, 31))


def serve(url):
    """The saved page and files, as kupiskis.download gets them."""
    if url == kupiskis.PAGE_URL:
        return PAGE.encode("utf-8")
    return fixture(f"kupiskis/{COPIES[url]}")


def page(html=PAGE, start=YEAR[0], end=YEAR[1], check="misrios-miestas-2026.pdf"):
    """The page's mixed waste rows of 2026, the town's rule checked against `check`."""
    source = kupiskis.RulePage(
        "household",
        kupiskis.PAGE_URL,
        "atlieku-isvezimas",
        start=start,
        end=end,
        check=(check, fixture(f"kupiskis/{check}")) if check else None,
    )
    return kupiskis.parse_file(source, html.encode("utf-8"))


def row(result, name):
    return next(a for a in result.areas if a.name == name)


def nth(weekday, *ns, year=2026):
    """The nth `weekday`s (0 = Monday) of every month of `year`."""
    days = [date(year, 1, 1) + timedelta(days=n) for n in range(366)]
    return {
        d for d in days if d.year == year and d.weekday() == weekday and (d.day - 1) // 7 + 1 in ns
    }


SORTED = ScheduleFile(
    "packaging",
    f"{UPLOADS}07/RUSIUOJAMUJU-ATLIEKU-SURINKIMO-GRAFIKAS-2026-1.pdf",
    "RUSIUOJAMUJU-ATLIEKU-SURINKIMO-GRAFIKAS-2026-1.pdf",
    year=2026,
    months=(7, 12),
)
FOOD = ScheduleFile(
    "food",
    f"{UPLOADS}01/2026-m.-Maisto-atlieku-surinkimo-grafikas.pdf",
    "2026-m.-Maisto-atlieku-surinkimo-grafikas.pdf",
    year=2026,
)


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, its rules' dates from 31 days ago."""
    files, warnings = kupiskis.download(TODAY, 31, serve)
    registry = aratc.town_elderships(Registry.load(FIXTURES / REGISTRY))
    data, more = build_dataset(files, registry, TODAY, 31, kupiskis.SOURCE)
    return files, data, warnings + more


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


# --- the rules -------------------------------------------------------------------


def test_rules_of_a_weekday_of_the_month():
    assert kupiskis.parse_rule("1-as mėnesio pirmadienis") == svara.Rule(0, weekdays=(0,), nth=1)
    assert kupiskis.parse_rule(" 4-as mėnesio sekmadienis ") == svara.Rule(0, weekdays=(6,), nth=4)
    for text in (
        "5-as mėnesio pirmadienis",  # not in every month
        "Kiekvienas mėnesio trečiadienis",  # the town's rule until 2024
        "kiekvieno mėnesio pirmą dieną",  # Utenos r.'s
        "1-as mėnesio",
        "1-as mėnesio pirmadienį",
        "2-as mėnesio antradienis ir ketvirtadienis",
    ):
        assert kupiskis.parse_rule(text) is None, text
    second_tuesday = kupiskis.parse_rule("2-as mėnesio antradienis")
    dates = kupiskis.rule_dates([second_tuesday], *YEAR)
    assert sorted(dates)[:3] == [date(2026, 1, 13), date(2026, 2, 10), date(2026, 3, 10)]
    assert dates == nth(1, 2)


def test_the_rules_dates_reach_13_months_ahead():
    assert kupiskis.horizon(TODAY) == date(2027, 12, 31)
    assert kupiskis.horizon(date(2026, 12, 1)) == date(2028, 1, 31)
    assert kupiskis.horizon(date(2026, 1, 31)) == date(2027, 2, 28)


# --- the page ----------------------------------------------------------------


def test_finds_the_files_by_their_sections():
    files, warnings = kupiskis.find_files(PAGE)
    assert [(f.kind, f.url, f.year, f.months) for f in files] == [
        ("household", TOWN, 2026, None),
        ("packaging", SORTED.url, 2026, (7, 12)),
        ("food", FOOD.url, 2026, None),
    ]
    # Not the food waste table linked in the mixed waste section, nor the textile section.
    assert warnings == []


def test_the_files_in_force():
    files, _ = kupiskis.find_files(PAGE)
    chosen, warnings = kupiskis.select_files(files, TODAY)
    assert chosen == files[1:]
    assert warnings == []
    assert kupiskis.town_file(files, TODAY) == files[0]
    # The next half year is read as soon as it is linked, the last one for a month after it.
    first = replace(SORTED, url="x.pdf", file_name="x.pdf", year=2027, months=(1, 6))
    assert kupiskis.select_files([SORTED, first], date(2026, 12, 28))[0] == [SORTED, first]
    assert kupiskis.select_files([SORTED, first], date(2027, 2, 2))[0] == [first]
    # A half year that ended without the next: its blocks keep their last dates.
    chosen, warnings = kupiskis.select_files([SORTED], date(2027, 3, 1))
    assert chosen == [SORTED]
    assert warnings == ["no food waste schedule on the page"]
    # Of two for one half year, the one linked last.
    chosen, warnings = kupiskis.select_files([SORTED, replace(SORTED, file_name="y.pdf")], TODAY)
    assert [f.file_name for f in chosen] == ["y.pdf"]
    assert warnings[0].startswith(f"{SORTED.file_name}: not read, y.pdf is a newer packaging")
    with pytest.raises(build.ValidationError, match="no packaging schedule on the page"):
        kupiskis.select_files([FOOD], TODAY)


def test_sections_of_no_waste_type_and_files_without_a_year():
    html = PAGE.replace("3. Tekstilės atliekų", "3. Žaliųjų atliekų").replace(
        "2.1. 2026 M. II PUSMETIS", "2.1. II PUSMETIS"
    )
    html = html.replace("RUSIUOJAMUJU-ATLIEKU-SURINKIMO-GRAFIKAS-2026", "RUSIUOJAMUJU")
    files, warnings = kupiskis.find_files(html)
    assert [f.kind for f in files] == ["household", "food"]
    assert warnings == [
        "a section of no waste type we read: '3. Žaliųjų atliekų surinkimo grafikas'",
        "RUSIUOJAMUJU-1.pdf ('RUSIUOJAMUJU'): no year in its heading, link or name",
    ]


def test_the_rules_of_the_page():
    result = page()
    assert result.warnings == []
    names = [a.name for a in result.areas]
    assert len(names) == 23
    # The town: the first and third Wednesday, as its file has them.
    town = row(result, "Kupiškio m.")
    assert town.dates == nth(2, 1, 3)
    assert (len(town.dates), town.weekday) == (24, "Trečiadienis")
    # A village after two rules has the dates of both: Pyragiai and Vėžionys the second and
    # fourth Tuesday, the other villages of those rules one of them.
    assert row(result, "Kupiškio sen.: Vėžionys, Pyragiai").dates == nth(1, 2, 4)
    virbaliskiai = "Kupiškio sen.: Virbališkiai, Jutkonys, Bagdonys, Iciūnai, Gindviliai, "
    assert row(result, f"{virbaliskiai}Laukminiškiai, Plundakai").dates == nth(1, 2)
    assert row(result, "Kupiškio sen.: Slavinčiškis, Dvaramiškis, Čiovydžiai").dates == nth(1, 4)
    # "Stačniai" of the third Tuesday is the first Tuesday's Stračniai.
    subacius = "Subačiaus sen.: Subačius, Skverbai, Stirniškiai, Valakai, Paviešinčiai, Čečeliai"
    assert row(result, f"{subacius}, Stračniai").dates == nth(1, 1, 3)
    assert row(result, "Subačiaus sen.: Kunčiai, Šaukliškiai").dates == nth(1, 3)
    # The first Friday of January 2027 is New Year's Day: kept, as the town's 2025 file kept 1
    # January.
    friday = page(start=date(2027, 1, 1), end=date(2027, 1, 31))
    siauriai = row(friday, "Noriūnų sen.: Siauriai, Karaliūnai, Maskvyčiai, Paprūdžiai")
    assert siauriai.dates == {date(2027, 1, 1)}
    assert all(a.district == "Kupiškio r." and a.provider == "kupiskis" for a in result.areas)


def test_rules_in_other_words_fail():
    edits = {
        "<strong>1-as mėnesio pirmadienis </strong> Kuosenai": (
            "<strong>Kiekvienas mėnesio pirmadienis </strong> Kuosenai",
            "an unrecognised mixed waste rule: 'Kiekvienas mėnesio pirmadienis Kuosenai, ",
        ),
        "<strong>2-as mėnesio pirmadienis</strong> Skodiniai,": (
            "<strong>2-ą mėnesio pirmadienį</strong> Skodiniai,",
            "an unrecognised mixed waste rule: '2-ą mėnesio pirmadienį Skodiniai, ",
        ),
        "Paprūdžiai.</p>": (
            "Paprūdžiai <strong>kas savaitę</strong>.</p>",
            "bold words after the places: 'Siauriai, Karaliūnai, Maskvyčiai, Paprūdžiai'",
        ),
        "Kuosenai, Mirabelis.": ("Kuosenai (Kuosėnų k.), Mirabelis.", "places of no known kind"),
        "1.7 Šimonių seniūnijoje": ("1.7 Šimonių apylinkėse", "a rule of no place we know"),
        "<p><strong>3-as mėnesio trečiadienis</strong></p>\n<p><a": (
            "<p><strong>3-as mėnesio trečiadienis</strong> Vilniaus g.</p>\n<p><a",
            "a rule of no place we know: '1.1. Kupiškio mieste'",
        ),
        "<strong>1-as mėnesio trečiadienis</strong></p>": (
            "1-as mėnesio trečiadienis</p>",
            "an unrecognised mixed waste rule: '1-as mėnesio trečiadienis'",
        ),
    }
    for old, (new, message) in edits.items():
        assert PAGE.count(old) == 1, old
        with pytest.raises(ValueError, match=message.replace("(", r"\(")):
            page(PAGE.replace(old, new))
    without = PAGE.replace("<p><strong>1-as mėnesio trečiadienis</strong></p>", "").replace(
        "<p><strong>3-as mėnesio trečiadienis</strong></p>", ""
    )
    with pytest.raises(ValueError, match="no mixed waste rule of the town"):
        page(without)
    skapiskis = re.compile(r"<p><strong> 1-as mėnesio pirmadienis</strong> Skapiškis.*?</p>")
    assert len(skapiskis.findall(PAGE)) == 1
    with pytest.raises(ValueError, match="no mixed waste rules of Skapiškio sen."):
        page(skapiskis.sub("", PAGE))


def test_the_towns_rule_is_checked_against_its_file():
    # The 2025 file has the same rule's days, 1 January (a holiday) among them.
    assert page(check="misrios-miestas-2025.pdf").warnings == []
    other = PAGE.replace(
        "<p><strong>3-as mėnesio trečiadienis</strong></p>",
        "<p><strong>4-as mėnesio trečiadienis</strong></p>",
    )
    (warning,) = page(other).warnings
    assert warning == (
        "misrios-miestas-2026.pdf: the town's dates of 2026 aren't its rule's (1-as mėnesio "
        "trečiadienis ir 4-as mėnesio trečiadienis): not in the file 2026-01-28, 2026-02-25, "
        "2026-03-25, 2026-04-22; not the rule's 2026-01-21, 2026-02-18, 2026-03-18, 2026-04-15"
    )
    assert page(check=None).warnings == [
        "no dated schedule of the town on the page to check its rule (1-as mėnesio trečiadienis "
        "ir 3-as mėnesio trečiadienis)"
    ]
    (warning,) = page(check="maisto-2026.pdf").warnings
    assert warning.startswith("maisto-2026.pdf: can't be read to check the town's rule")


# --- the files -------------------------------------------------------------------


def test_the_half_years_packaging_and_glass():
    result = kupiskis.parse_file(SORTED, fixture("kupiskis/rusiuojamos-2026-2.pdf"))
    by_name = {(a.kind, a.name): a for a in result.areas}
    assert sorted({name for _, name in by_name}) == [
        "Alizavos sen.",
        "Kupiškio m.",
        "Kupiškio sen.",
        "Noriūnų sen.",
        "Skapiškio sen.",
        "Subačiaus sen.",
        "Šimonių sen., Skodinių k., Kinderių k.",
    ]
    assert len(result.areas) == 14
    town = by_name[("packaging", "Kupiškio m.")]
    assert sorted(town.dates) == [
        date(2026, 7, 30),
        date(2026, 8, 31),
        date(2026, 9, 30),
        date(2026, 10, 30),
        date(2026, 11, 30),
        date(2026, 12, 30),
    ]
    glass = by_name[("glass", "Šimonių sen., Skodinių k., Kinderių k.")]
    assert sorted(glass.dates) == [date(2026, 7, 22), date(2026, 10, 15)]
    # The link's period must be the title's.
    with pytest.raises(ValueError, match="isn't of 2026 \\(1, 6\\)"):
        kupiskis.parse_file(
            replace(SORTED, months=(1, 6)), fixture("kupiskis/rusiuojamos-2026-2.pdf")
        )
    with pytest.raises(ValueError, match="isn't of 2026 \\(7, 12\\)"):
        kupiskis.parse_file(SORTED, fixture("kupiskis/maisto-2026.pdf"))


def test_the_blocks_places():
    assert kupiskis.block_name("Kupiškio miestas", "x") == ("Kupiškio m.", ["Kupiškio miesto"])
    assert kupiskis.block_name("Šimonių sen.(Skodinių,Kinderių k.)", "x") == (
        "Šimonių sen., Skodinių k., Kinderių k.",
        ["Šimonių"],
    )
    # As the page wrote them in 2024.
    assert kupiskis.block_name("Šimonių sen., Kinderių k., Skodinių k.", "x") == (
        "Šimonių sen., Kinderių k., Skodinių k.",
        ["Šimonių"],
    )
    assert kupiskis.block_name("Kupiškio miestas, Noriūnų sen.", "x") == (
        "Kupiškio m., Noriūnų sen.",
        ["Kupiškio miesto", "Noriūnų"],
    )
    for label in ("Panevėžio sen.", "Subačiaus m.", "Visi kaimai"):
        with pytest.raises(ValueError, match="a block of"):
            kupiskis.block_name(label, "x")


def test_the_food_waste():
    (food,) = kupiskis.parse_file(FOOD, fixture("kupiskis/maisto-2026.pdf")).areas
    assert food.name == "Kupiškis, Subačius, Noriūnai, Šepeta, Aukštupėnai"
    # The second and fourth Wednesday.
    assert food.dates == nth(2, 2, 4)
    assert (food.kind, food.weekday) == ("food", "Trečiadienis")
    with pytest.raises(ValueError, match="the title says 2026, the link 2027"):
        kupiskis.parse_file(replace(FOOD, year=2027), fixture("kupiskis/maisto-2026.pdf"))
    with pytest.raises(ValueError, match="a title of"):
        kupiskis.parse_file(FOOD, fixture("kupiskis/misrios-miestas-2026.pdf"))


def test_the_next_half_year_continues_the_blocks_of_the_same_places():
    def half(file, result, days):
        return file, ParseResult(
            [replace(a, dates={d + timedelta(days=days) for d in a.dates}) for a in result.areas]
        )

    content = fixture("kupiskis/rusiuojamos-2026-2.pdf")
    registry = aratc.town_elderships(Registry.load(FIXTURES / REGISTRY))
    nxt = replace(SORTED, file_name="next.pdf", year=2027, months=(1, 6))
    parsed = [(SORTED, kupiskis.parse_file(SORTED, content)), half(nxt, parsed_again(), 184)]
    assert kupiskis.combine(parsed, registry, date(2026, 12, 28)) == []
    (this, now), (_, later) = parsed
    assert later.areas == []
    town = next(a for a in now.areas if a.kind == "packaging" and a.name == "Kupiškio m.")
    assert max(town.dates) == date(2027, 7, 2)
    # Ended without the next.
    parsed = [(SORTED, kupiskis.parse_file(SORTED, content))]
    assert kupiskis.combine(parsed, registry, date(2027, 1, 5)) == [
        "the packaging schedule ended on 2026-12-31; no newer one is read"
    ]
    with pytest.raises(ValueError, match="overlap"):
        kupiskis.combine(
            [(SORTED, parsed_again()), (replace(nxt, year=2026, months=(12, 12)), parsed_again())],
            registry,
            TODAY,
        )


def parsed_again():
    return kupiskis.parse_file(SORTED, fixture("kupiskis/rusiuojamos-2026-2.pdf"))


# --- the places ----------------------------------------------------------------


def test_counts(built):
    files, data, warnings = built
    assert [f.file_name for f, _ in files] == [
        "atlieku-isvezimas",
        SORTED.file_name,
        FOOD.file_name,
    ]
    assert warnings == []
    stats = data["matching"]
    assert stats["locations"] == 396
    # 125 settlements the rules name and the town; the villages of Skapiškio, Alizavos and
    # Šimonių sen. they don't name have the eldership's one rule; elsewhere the app asks.
    assert (stats["household.single"], stats["household.ambiguous"]) == (298, 98)
    for kind in ("packaging", "glass"):
        assert stats[f"{kind}.single"] == 396, kind
    assert (stats["food.single"], stats["food.none"]) == (5, 391)
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 23, "packaging": 7, "glass": 7, "food": 1}
    # The rules' dates from 31 days ago to the end of 2027; the files' from 31 days ago.
    assert data["coverage"]["household"] == {"from": "2026-10-27", "to": "2027-12-28"}
    assert data["coverage"]["packaging"] == {"from": "2026-10-22", "to": "2026-12-30"}


def test_the_town_and_the_villages(built):
    _, data, _ = built
    town = place(data, "Kupiškis")
    assert (town["type"], town["district"]) == ("m.", "Kupiškio miesto")
    assert "streets" not in town
    for kind in ("household", "packaging", "glass"):
        assert rows(data, town, kind) == ["Kupiškio m."]
    assert rows(data, town, "food") == ["Kupiškis, Subačius, Noriūnai, Šepeta, Aukštupėnai"]
    # Skodiniai and Kinderiai: their eldership's mixed waste, Šimonių sen.'s packaging.
    skodiniai = place(data, "Skodiniai")
    assert rows(data, skodiniai) == ["Kupiškio sen.: Skodiniai, Papiliai, Bukėnai, Kinderiai"]
    assert rows(data, skodiniai, "packaging") == ["Šimonių sen., Skodinių k., Kinderių k."]
    # "Subačius" is the town; the old town has a rule of its own.
    subacius = "Subačiaus sen.: Subačius, Skverbai, Stirniškiai, Valakai, Paviešinčiai, Čečeliai"
    assert rows(data, place(data, "Subačius", "m.")) == [f"{subacius}, Stračniai"]
    (old,) = rows(data, place(data, "Subačius", "mstl."))
    assert old.startswith("Subačiaus sen.: Lukonys, Miliūnai, Subačiaus mstl.")
    # "Skapiškio gel. st.": the station.
    (station,) = rows(data, place(data, "Skapiškis", "glž. st."))
    assert station.startswith("Skapiškio sen.: Skapiškis, Skapiškio gel. st.")
    # "Puponys-2" of Šimonių sen. is Puponys II, "Miliūnai-2" Alizavos sen.'s Miliūnai.
    assert rows(data, place(data, "Puponys II"))[0].startswith("Šimonių sen.: Šimonys")
    assert rows(data, place(data, "Miliūnai", district="Alizavos"))[0].startswith("Alizavos")
    # Typos: Maskvyčiai, Paviešinčiai, Kunigiškiai, Viežtai.
    for name in ("Maksvyčiai", "Paviešintys", "Kunigiškis", "Viežgai"):
        assert len(rows(data, place(data, name))) == 1, name
    # A village no rule names: its eldership's only rule, or the app asks which.
    assert rows(data, place(data, "Bugailiškiai"))[0].startswith("Šimonių sen.: Šimonys")
    assert len(rows(data, place(data, "Pajuodupė"))) == 10


def test_a_village_named_by_two_rows_is_reported(built):
    files, _, _ = built
    registry = aratc.town_elderships(Registry.load(FIXTURES / REGISTRY))
    html = PAGE.replace(
        "Noriūnai, Rudiliai, Puponys, Palėvenė, Aukštaičiai",
        "Noriūnai, Rudiliai, Puponiai, Palėvenė, Aukštaičiai",
    )
    source = files[0][0]
    parsed = [(source, kupiskis.parse_file(source, html.encode("utf-8")))]
    assert kupiskis.combine(parsed, registry, TODAY) == [
        "Puponys k. (Noriūnų sen.) is named by 2 mixed waste rows: Noriūnų sen.: Puponys, "
        "Blizgė, Morkūniškis, Račiupėnai, Buivėnai; Noriūnų sen.: Puponiai, Aukštaičiai, Žvėriai"
    ]


# --- the folder ------------------------------------------------------------------


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kupiskis, "_get", serve)
    monkeypatch.setattr(kupiskis.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(kupiskis.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "kupiskio-r"
    assert kupiskis.main(["--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["kupiskis"]
    assert regions.region(tmp_path, out) == {
        "path": "kupiskio-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["kupiskis"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="kupiskis"} 396' in text

"""Zarasų r.: the municipality's page, the transcription of its mixed waste scan and the hash
that guards it, the rules turned into dates, the packaging PDF, the places and the folder."""

import hashlib
import json
import re
from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, regions, status, svara, zarasai
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "zarasai" / "registry-zarasu-r-2026-11-22.json")
TODAY = date(2026, 11, 22)
UPLOADS = "https://www.zarasai.lt/data/public/uploads/"
SCAN_URL = f"{UPLOADS}2026/03/misriu.pdf"
PACKAGING_URL = (
    f"{UPLOADS}2025/12/pakuociu-ir-antriniu-zaliavu-isvezimo-is-ind.-valdu-grafikas_2026.pdf"
)
# The scan isn't kept here: the tests read the committed transcription with the hash of these
# bytes in place of the scan's (`scan`).
SCAN = b"%PDF-1.4 the scan"


@pytest.fixture
def scan(tmp_path, monkeypatch):
    """The committed transcription, guarding SCAN."""
    data = json.loads(zarasai.RULES_FILE.read_text(encoding="utf-8"))
    data["sha256"] = hashlib.sha256(SCAN).hexdigest()
    path = tmp_path / "rules-zarasu-r.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(zarasai, "RULES_FILE", path)
    return path


def serve(url, timeout=0):
    """The saved page and packaging file, and SCAN, as zarasai.http.get."""
    files = {
        zarasai.PAGE_URL: fixture("zarasai/page.html"),
        SCAN_URL: SCAN,
        PACKAGING_URL: fixture("zarasai/pakuotes-2026.pdf"),
    }
    return files[url]


def page_files():
    return zarasai.find_files(fixture("zarasai/page.html").decode("utf-8"))


@pytest.fixture
def part(scan, monkeypatch):
    monkeypatch.setattr(zarasai.http, "get", serve)
    files, warnings = zarasai.download(TODAY, 31)
    data, more = build_dataset(files, REGISTRY, TODAY, 31, zarasai.SOURCE)
    return data, warnings + more


def place(data, name, district=None, kind_of_place=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and district in (None, loc["district"])
        and kind_of_place in (None, loc["type"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def rows_of(data, name, kind="household", street=None, district=None, kind_of_place=None):
    """The rows of a place (or of one of its streets)."""
    location = place(data, name, district, kind_of_place)
    schedule = location["schedule"][kind]
    if street is None:
        ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    else:
        key = next(k for k, label in location["streets"] if label == street)
        ids = schedule["streets"][key]
    return [row(data, i) for i in ids]


def starting(rows, *beginnings):
    """Whether the rows are those whose names start so, one each."""
    names = [r["name"] for r in rows]
    return len(names) == len(beginnings) and all(
        sum(n.startswith(b) for n in names) == 1 for b in beginnings
    )


def dates_of(data, name, kind="household", **where):
    """The dates of a place's only row."""
    (only,) = rows_of(data, name, kind, **where)
    return only["dates"]


# The beginnings of the rules' rows, as rows_of gives them.
MONDAY_TOWN = "Zarasų sen. Šaltupės g. nuo 66 nr. iki 70"
TUESDAY_TOWN = "Zarasų sen. Aušros skg. 1,3,5,7, Aušros g"
THURSDAY_TOWN_1 = "Zarasų sen. Jauneikių g., Petro Cvirkos g"
THURSDAY_TOWN_2 = "Zarasų sen. Palaukės g., Juozo Gruodžio g"
FRIDAY_TOWN = "Zarasų sen. Bajorų g., Smėlynės g., Aukšt"
FIRST_WEDNESDAY = "Dusetų sen. Dusetų vs., Padustėlio k. Vyt"
SECOND_WEDNESDAY = "Dusetų sen. Pakniškių k., Brogiškės k., P"
THIRD_WEDNESDAY = "Dusetų sen. Padustėlio k. Alyvų g., Beržų"
LAST_WEDNESDAY = "Dusetų sen. Užtiltės k. Vasaknų g. 12, 14"
DUSETOS = "Dusetų sen. Dusetų m."


# --- the page ----------------------------------------------------------------


def test_finds_the_files_by_the_rows_of_their_kinds():
    files = page_files()
    assert [(f.kind, f.url, f.since) for f in files] == [
        ("household", SCAN_URL, date(2026, 1, 1)),
        ("packaging", PACKAGING_URL, date(2026, 1, 1)),
    ]
    assert files[0].file_name == "misriu.pdf"


def test_rows_of_the_kinds_read_must_link_their_schedule():
    def page(cell):
        return f"<table><tr><td>Komunalinės atliekos</td><td>{cell}</td></tr></table>"

    with pytest.raises(ValueError, match="links no schedule"):
        zarasai.find_files(page("Žiūrėti savitarnoje"))
    with pytest.raises(ValueError, match="links 'Grafikas'"):
        zarasai.find_files(page('<a href="/data/public/uploads/2027/01/m.pdf">Grafikas</a>'))
    with pytest.raises(ValueError, match="links 'Nuo 2027-01-01'"):
        zarasai.find_files(page('<a href="/data/public/uploads/2027/01/m.docx">Nuo 2027-01-01</a>'))
    # Food waste and the other rows aren't read.
    food = '<table><tr><td>Maisto atliekos</td><td><a href="x.pdf">Kada?</a></td></tr></table>'
    assert zarasai.find_files(food) == []


def test_the_rules_dates_run_from_a_month_ago_to_13_months_ahead():
    scan, packaging = zarasai.select_files(page_files(), TODAY, 31)
    assert (scan.start, scan.end) == (date(2026, 10, 22), date(2027, 12, 27))
    assert packaging.kind == "packaging" and packaging.start is None
    # Not before the day the link names.
    scan, _ = zarasai.select_files(page_files(), date(2026, 1, 10), 31)
    assert scan.start == date(2026, 1, 1)


def test_a_page_without_the_scan_or_the_packaging_file_fails():
    scan, packaging = page_files()
    with pytest.raises(ValidationError, match="0 mixed waste schedules on the page"):
        zarasai.select_files([packaging], TODAY, 31)
    with pytest.raises(ValidationError, match="2 mixed waste schedules on the page"):
        zarasai.select_files([scan, scan, packaging], TODAY, 31)
    with pytest.raises(ValidationError, match="no packaging schedule"):
        zarasai.select_files([scan], TODAY, 31)


# --- the rules -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "weekday", "weeks"),
    [
        ("2-ą ir paskutinį mėnesio pirmadienį", 0, (2, -1)),
        ("1-ą mėnesio pirmadienį", 0, (1,)),
        ("1-ą ir 3-ą mėnesio antradienį", 1, (1, 3)),
        ("1-ą i 3-ą mėnesio ketvirtadienį", 3, (1, 3)),
        ("4-ą mėnesio trečiadienį", 2, (4,)),
        ("Paskutinį mėn. trečiadienį", 2, (-1,)),
        ("PIRMAS MĖN. PIRMADIENIS", 0, (1,)),
        ("TREČIAS MĖN. KETVIRTADIENIS", 3, (3,)),
    ],
)
def test_rules(text, weekday, weeks):
    assert zarasai.parse_rule(text) == zarasai.Rule(weekday, weeks)


@pytest.mark.parametrize(
    "text",
    [
        "kiekvieno mėnesio pirmą dieną",
        "kas antrą pirmadienį",
        "6-ą mėnesio pirmadienį",
        "1-ą ir 1-ą mėnesio pirmadienį",
        "PIRMAS MĖN. PIRMADIENĮ",
        "pirmą mėnesio pirmadienį",
    ],
)
def test_rules_in_other_words(text):
    assert zarasai.parse_rule(text) is None


def test_the_nth_and_the_last_weekday_of_the_month():
    rule = zarasai.parse_rule("2-ą ir paskutinį mėnesio pirmadienį")
    assert sorted(rule.dates(date(2026, 11, 1), date(2027, 1, 31))) == [
        date(2026, 11, 9),
        date(2026, 11, 30),
        date(2026, 12, 14),
        date(2026, 12, 28),
        date(2027, 1, 11),
        date(2027, 1, 25),
    ]
    # December 2026 has five Wednesdays: the 4th is the 23rd, the last the 30th.
    december = (date(2026, 12, 1), date(2026, 12, 31))
    assert zarasai.parse_rule("4-ą mėnesio trečiadienį").dates(*december) == {date(2026, 12, 23)}
    assert zarasai.parse_rule("Paskutinį mėn. trečiadienį").dates(*december) == {date(2026, 12, 30)}
    # svara.Rule's nth -1, the engine underneath.
    assert svara.Rule(0, weekdays=(2,), nth=-1).allows(date(2026, 12, 30))
    assert not svara.Rule(0, weekdays=(2,), nth=-1).allows(date(2026, 12, 23))


def test_the_transcription():
    rules = zarasai.load_rules()
    assert rules.url == SCAN_URL
    assert len(rules.rules) == 26
    first = rules.rules[0]
    assert first.text == "2-ą ir paskutinį mėnesio pirmadienį"
    assert first.rule == zarasai.Rule(0, (2, -1))
    assert first.name == (
        "Zarasų sen. Šaltupės g. nuo 66 nr. iki 70 nr., Magutiškių vs., Statybininkų g., "
        "Valstiečių g., Igno Pašilio g., Kauno g. nuo 44 nr. iki 90 nr."
    )
    # A rule of three elderships' places.
    assert any(
        r.name.startswith("Salako sen. Murliškių k.") and " Dusetų sen. Pažemio k." in r.name
        for r in rules.rules
    )


def edited(tmp_path, change):
    data = json.loads(zarasai.RULES_FILE.read_text(encoding="utf-8"))
    change(data["rules"][0])
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda r: r.update(weeks=[2]), "not pirmadienis of weeks"),
        (lambda r: r.update(weekday="antradienis"), "not antradienis"),
        (lambda r: r.update(rule="kas antrą pirmadienį"), "not pirmadienis"),
        (lambda r: r["places"][0].update(eldership="Antazavės"), "a section of"),
        (lambda r: r["places"].append(r["places"][0]), "Zarasų sen. twice"),
        (lambda r: r["places"][0]["places"].append("Prie ežero"), "places of no known kind"),
        (lambda r: r["places"][0]["places"].append("Kauno g. prie turgaus"), "no known kind"),
        (lambda r: r["places"][0]["places"].append("Salos k., Gėlių k."), "read as two places"),
        (lambda r: r.update(note="?"), "keys"),
    ],
)
def test_a_transcription_of_other_words_or_places_fails(tmp_path, change, error):
    with pytest.raises(ValueError, match=error):
        zarasai.load_rules(edited(tmp_path, change))


@pytest.mark.parametrize(
    ("place", "found"),
    [
        ("Magutiškių vs.", [("place", "Magutiškių vs.", False, False)]),
        ("Veselavos k", [("place", "Veselavos k.", False, False)]),
        ("Apkartų I k.", [("place", "Apkartų I k.", False, False)]),
        ("Likančių k. 1, 2", [("place", "Likančių k.", False, False)]),
        (
            "Padustėlio k. Vytauto Striogos g. 1, 2, 3, 4, 5, 7, 9, 11 ir 15 nr.",
            [
                ("place", "Padustėlio k.", False, False),
                ("street", "Vytauto Striogos g.", True, True),
            ],
        ),
        (
            "Kartašovkos vs. Suvieko k.",
            [("place", "Kartašovkos vs.", False, False), ("place", "Suvieko k.", False, False)],
        ),
        (
            "Kiviškių k. Suvieko kel. 21, 22",
            [("place", "Kiviškių k.", False, False), ("street", "Suvieko kel.", True, True)],
        ),
        ("Šaltupės g. nuo 66 nr. iki 70 nr.", [("street", "Šaltupės g.", True, False)]),
        (
            "Vytauto Striogos g. 6, 8, 10, 12 nr. ir nuo 17 nr. iki 47 nr.",
            [("street", "Vytauto Striogos g.", True, False)],
        ),
        (
            "Vilniaus g. nuo Salos g. iki Vytauto g. sankryžos",
            [("street", "Vilniaus g.", True, False)],
        ),
        (
            "Kauno g. išskyrus nurodytus ketvirtadienį ir pirmadienį",
            [("street", "Kauno g.", False, False)],
        ),
        ("Dariaus ir Girėno g.", [("street", "Dariaus ir Girėno g.", False, False)]),
    ],
)
def test_the_places_of_a_rule(place, found):
    assert [tuple(t) for t in zarasai.tokens(place)] == found


# --- the hash ------------------------------------------------------------------


def test_the_rules_while_the_scan_is_the_one_transcribed(scan):
    file = zarasai.ScheduleFile(
        "household", SCAN_URL, "misriu.pdf", start=date(2026, 10, 22), end=date(2027, 12, 27)
    )
    result = zarasai.parse_file(file, SCAN)
    assert len(result.areas) == 26 and result.warnings == []
    assert {a.kind for a in result.areas} == {"household"}
    for area in result.areas:
        assert date(2026, 10, 22) <= min(area.dates) and max(area.dates) <= date(2027, 12, 27)
        assert {d.weekday() for d in area.dates} == {zarasai.WEEKDAY_NAMES.index(area.weekday)}
    # The scan at another address, with the same bytes: read, with a warning.
    moved = replace(file, url=f"{UPLOADS}2027/01/misriu.pdf")
    assert zarasai.parse_file(moved, SCAN).warnings == [
        f"misriu.pdf: the scan transcribed from {SCAN_URL}, now here"
    ]


def test_a_changed_scan_fails_with_its_new_hash(scan):
    file = zarasai.ScheduleFile(
        "household", SCAN_URL, "misriu.pdf", start=date(2026, 10, 22), end=date(2027, 12, 27)
    )
    other = SCAN + b" corrected"
    digest = hashlib.sha256(other).hexdigest()
    message = (
        f"the published scan changed (new hash {digest}); "
        "re-transcribe pipeline/data/rules-zarasu-r.json"
    )
    with pytest.raises(ValidationError) as error:
        zarasai.parse_file(file, other)
    assert str(error.value) == message


def test_the_committed_transcription_has_the_hash_of_the_published_scan():
    """The scan of 2 March 2026 (3 pages, 1,379,501 bytes), as the page linked it on 22
    November 2026."""
    assert zarasai.load_rules().sha256 == (
        "c62a6642851ca1074b7d0edefe30230b0677bfc5be98da71cb3ed916d1722575"
    )


# --- packaging -------------------------------------------------------------------


def packaging_file():
    return page_files()[1]


def test_packaging_and_glass():
    result = zarasai.parse_file(packaging_file(), fixture("zarasai/pakuotes-2026.pdf"))
    assert result.warnings == []
    packaging = [a for a in result.areas if a.kind == "packaging"]
    glass = [a for a in result.areas if a.kind == "glass"]
    assert len(packaging) == len(glass) == 6
    first = packaging[0]
    assert first.name.startswith("Zarasų miestas: Aukštaičių g., Bajorų g.")
    assert first.name.endswith("Kaimai: Dimitriškių k., Štadvilių k., Sniegiškių k., Gružtų k.")
    assert sorted(first.dates)[:3] == [date(2026, 1, 19), date(2026, 2, 20), date(2026, 3, 20)]
    assert len(first.dates) == 12
    # Glass four times a year ("-" the other months), on packaging days.
    assert sorted(glass[0].dates) == [
        date(2026, 3, 20),
        date(2026, 6, 19),
        date(2026, 9, 18),
        date(2026, 12, 18),
    ]
    assert all(g.dates <= p.dates for p, g in zip(packaging, glass, strict=True))
    assert packaging[5].name.startswith("Kaimai ir miesteliai: Julijanavos k.")
    assert max(packaging[5].dates) == date(2026, 12, 30)


def test_a_packaging_file_of_another_year_than_its_link_fails():
    file = replace(packaging_file(), since=date(2027, 1, 1))
    with pytest.raises(ValueError, match="a schedule of 2026, its link says from 2027-01-01"):
        zarasai.parse_file(file, fixture("zarasai/pakuotes-2026.pdf"))


def test_packaging_rows_out_of_order_fail():
    def rows(*cells):
        return [list(c) + [None] * (13 - len(c)) for c in cells]

    months = ["mėnuo", *"sausis vasaris kovas balandis gegužė birželis liepa".split()]
    months += "rugpjūtis rugsėjis spalis lapkritis gruodis".split()
    days = ["diena", *[str(n) for n in range(10, 22)]]
    blue = ["1 grafikas", "Mėlynas konteineris pakuočių (popieriaus, plastiko ir metalo) atliekoms"]
    green = ["Žalias konteineris stiklo atliekoms"]
    good = rows(blue, months, days, green, months, ["diena", *["-"] * 12], ["adresas", "Kaimai: x"])
    assert len(zarasai._schedules(good, 2026, "x.pdf")) == 1
    with pytest.raises(ValueError, match="expected kind"):
        zarasai._schedules(rows(blue, months, days, blue[1:], months, days), 2026, "x.pdf")
    with pytest.raises(ValueError, match="not a day of 2026-02"):
        zarasai._schedules(rows(blue, months, ["diena", "1", "30", *days[3:]]), 2026, "x.pdf")
    with pytest.raises(ValueError, match="not a day of 2026-01: '-'"):
        zarasai._schedules(rows(blue, months, ["diena", "-", *days[2:]]), 2026, "x.pdf")
    with pytest.raises(ValueError, match="the last without its addresses"):
        zarasai._schedules(good[:-1], 2026, "x.pdf")
    with pytest.raises(ValueError, match="'2 grafikas' after 0 schedules"):
        zarasai._schedules(rows(["2 grafikas", blue[1]]), 2026, "x.pdf")


# --- the places ------------------------------------------------------------------


def test_counts(part):
    data, _ = part
    stats = data["matching"]
    assert stats["locations"] == 762
    assert stats["household.single"] + stats["household.byStreet"] == 291
    assert stats["household.ambiguous"] == 6
    assert stats["packaging.single"] + stats["packaging.byStreet"] == 64
    assert {k: sum(a["kind"] == k for a in data["areas"]) for k in zarasai.PROVIDER.kinds} == {
        "household": 26,
        "packaging": 6,
        "glass": 6,
    }


def test_acceptance_examples(part):
    data, _ = part
    # Salakas: the first Wednesday of the month ("PIRMAS MĖN. TREČIADIENIS").
    salakas = dates_of(data, "Salakas")
    assert (salakas[0], salakas[-1], len(salakas)) == ("2026-11-04", "2027-12-01", 14)
    # Dusetos: the first and third Wednesdays, the whole town.
    dusetos = dates_of(data, "Dusetos", kind_of_place="m.")
    assert dusetos[:4] == ["2026-11-04", "2026-11-18", "2026-12-02", "2026-12-16"]
    assert dusetos[-1] == "2027-12-15"
    assert starting(rows_of(data, "Dusetos", kind_of_place="m."), DUSETOS)
    # Its packaging and glass.
    glass = rows_of(data, "Dusetos", "glass", kind_of_place="m.")
    assert starting(glass, "Kaimai ir miesteliai: Rokėnų k., Dusetų m.")
    assert glass[0]["dates"] == ["2026-12-22"]


def test_the_streets_of_zarasai(part):
    data, _ = part
    assert starting(rows_of(data, "Zarasai", street="Statybininkų g."), MONDAY_TOWN)
    # Some houses of a street are that street: Aušros g. 7, 8, 10, ... on Tuesdays.
    assert starting(rows_of(data, "Zarasai", street="Aušros g."), TUESDAY_TOWN)
    # A street of several routes asks.
    kauno = rows_of(data, "Zarasai", street="Kauno g.")
    assert starting(kauno, MONDAY_TOWN, THURSDAY_TOWN_2, FRIDAY_TOWN)
    vilniaus = rows_of(data, "Zarasai", street="Vilniaus g.")
    assert starting(vilniaus, THURSDAY_TOWN_1, FRIDAY_TOWN)
    # "Žaliosios g." is Žalioji g.
    assert starting(rows_of(data, "Zarasai", street="Žalioji g."), THURSDAY_TOWN_2)
    # A street no route names is left to the app: not "no pickup".
    streets = place(data, "Zarasai")["schedule"]["household"]["streets"]
    labels = dict(place(data, "Zarasai")["streets"])
    unnamed = sorted(label for key, label in labels.items() if key not in streets)
    assert unnamed == [
        "Bijūnų g.",
        "Dariaus ir Girėno skg.",
        "Draugystės g.",
        "E. Pliaterytės skg.",
        "Gėlių g.",
        "Jauneikių skg.",
        "Kalno g.",
        "Naujakurių g.",
        "P. Širvio g.",
        "Rožių g.",
        "S. Nėries g.",
        "Salos g.",
        "Savanorių skg.",
        "Sėlių a.",
        "Vytauto skg.",
        "Šilo g.",
    ]
    assert all(streets.values())
    # Packaging names Zarasai's streets too.
    packaging = rows_of(data, "Zarasai", "packaging", street="S. Nėries g.")
    assert starting(packaging, "Zarasų miestas: Aukštaičių g., Bajorų g.")


def test_the_streets_of_villages(part):
    data, _ = part
    # "Užtiltės k. Vasaknų g. 12, 14, 24, 26, 30": one more choice for that street.
    assert starting(rows_of(data, "Užtiltė"), FIRST_WEDNESDAY)
    vasaknu = rows_of(data, "Užtiltė", street="Vasaknų g.")
    assert starting(vasaknu, FIRST_WEDNESDAY, LAST_WEDNESDAY)
    # "Padustėlio k. Alyvų g., Beržų g., ...": those streets, whatever the town has.
    assert starting(rows_of(data, "Padustėlis", street="Beržų g."), THIRD_WEDNESDAY)
    striogos = rows_of(data, "Padustėlis", street="Vytauto Striogos g.")
    assert starting(striogos, FIRST_WEDNESDAY, THIRD_WEDNESDAY)
    # A street after a comma, of the village before it: Pasartės g. 1, 3, 5 of Didžiadvaris.
    assert starting(rows_of(data, "Didžiadvaris"), FIRST_WEDNESDAY)
    pasartes = rows_of(data, "Didžiadvaris", street="Pasartės g.")
    assert starting(pasartes, FIRST_WEDNESDAY, SECOND_WEDNESDAY)
    # Or of the village after it: "Kloviškių k., Senųjų Baibių g., Baibių k.".
    assert starting(rows_of(data, "Baibiai"), "Salako sen. Murliškių k.")
    baibiu = rows_of(data, "Baibiai", street="Senųjų Baibių g.")
    assert starting(baibiu, "Turmanto sen. Ilgiškės k. 2,")
    # "Magutiškių vs., Statybininkų g.": the farmstead, and a street of the town.
    assert starting(rows_of(data, "Magutiškės"), MONDAY_TOWN)


def test_houses_of_a_village_without_streets_ask(part):
    data, _ = part
    # "Jakunčių k. 1, 2, 3, 4, 6, 7" and "Jakunčių k. 8, 9, 10": the register has no streets.
    jakunciai = rows_of(data, "Jakunčiai")
    assert starting(jakunciai, "Dusetų sen. Antalieptės mstl.", THIRD_WEDNESDAY)


def test_names_written_otherwise(part):
    data, _ = part
    turmantas = "Turmanto sen. Turmanto mstl., Kimbartiškių k."
    # Aliases: "Bartkiškių k." for Bartkiškė I, "Boleslavovos k." for Boleslovava.
    assert starting(rows_of(data, "Bartkiškė I"), turmantas)
    assert starting(rows_of(data, "Boleslovava"), "Imbrado sen. Zablatiškių k.")
    # "Galiniškių II k." under Turmanto sen.: Zarasų sen.'s, the only one of that name.
    assert starting(rows_of(data, "Galiniškės II"), turmantas)
    # "Antazavės mstl.": Antazavė is a village in the register.
    assert starting(rows_of(data, "Antazavė"), "Imbrado sen. Avilių mstl.")
    # "Avilių.mstl." in the packaging file.
    aviliai = rows_of(data, "Aviliai", "packaging", kind_of_place="mstl.")
    assert starting(aviliai, "Kaimai ir miesteliai: Julijanavos k.")


def test_a_packaging_village_of_a_name_several_elderships_have(part):
    """The packaging file names no elderships: its "Sniegiškių k.", with Dimitriškės, Štadviliai
    and Gružtai, is Zarasų sen.'s, not Dusetų sen.'s or Salako sen.'s."""
    data, _ = part
    town = "Zarasų miestas: Aukštaičių g., Bajorų g."
    assert starting(rows_of(data, "Sniegiškės", "packaging", district="Zarasų"), town)
    for other in ("Dusetų", "Salako"):
        assert "packaging" not in place(data, "Sniegiškės", other).get("schedule", {})


def test_warnings(part):
    _, warnings = part
    assert warnings == [
        "not a settlement or a street: household: Zarasų sen.: Sarokiškio k.",
        "not a settlement or a street: household: Padustėlio k.: Alyvų g.",
        "not a settlement or a street: household: Padustėlio k.: Pušų g.",
        "not a settlement or a street: household: Padustėlio k.: Šilo g.",
        "not a settlement or a street: household: Dusetų sen.: Piliakalnio k.",
        "not a settlement or a street: household: Zarasų sen.: Liepkalnio k.",
    ]


def test_mixed_waste_never_runs_out(part):
    data, _ = part
    coverage = data["coverage"]
    assert coverage["household"]["to"] == "2027-12-27"
    assert coverage["packaging"]["to"] == "2026-12-30"


# --- the published folder --------------------------------------------------------


def test_published_folder_and_its_metrics(part, tmp_path):
    data, warnings = part
    dataset = merge_parts(
        [(zarasai.PROVIDER, {**data, "warnings": len(warnings)})], zarasai.PAGE_URL
    )
    assert [p["id"] for p in dataset["providers"]] == ["zarasai"]
    assert all(a["provider"] == "zarasai" for a in dataset["areas"])
    folder = tmp_path / "zarasu-r"
    folder.mkdir()
    (folder / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    (folder / "addresses.json").write_text("{}", encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # 297 with mixed waste, and Kukuliškiai and Suvėnai with packaging only.
    assert 'siuksliaveze_data_places{source="zarasai"} 299' in text
    assert 'siuksliaveze_data_areas{source="zarasai",kind="household"} 26' in text
    assert 'siuksliaveze_data_warnings{source="zarasai"} 6' in text
    last = 'siuksliaveze_data_last_date_timestamp_seconds{source="zarasai",kind="household"} '
    assert f"{last}1829865600" in text  # 2027-12-27
    assert regions.collect(tmp_path)["regions"] == [
        {
            "path": "zarasu-r/",
            "kind": "settlements",
            "files": ["schedule.json", "addresses.json"],
            "providers": ["zarasai"],
        }
    ]


def no_register(url, timeout=0):
    raise OSError("HTTP Error 403: Forbidden")


def test_main_writes_the_folder(scan, tmp_path, monkeypatch):
    monkeypatch.setattr(zarasai.http, "get", serve)
    monkeypatch.setattr(zarasai.raseiniai.address_register, "fetch", no_register)
    monkeypatch.setattr(zarasai.raseiniai.address_points, "fetch", no_register)
    assert zarasai.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["zarasai"]
    assert data["source"] == zarasai.PAGE_URL
    addresses = json.loads((tmp_path / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > zarasai.MUNICIPALITY.min_address_points


def test_a_changed_scan_writes_nothing(scan, tmp_path, monkeypatch, capsys):
    """The workflow then keeps yesterday's folder, so ScheduleDataStale fires."""

    def corrected(url, timeout=0):
        return SCAN + b" corrected" if url == SCAN_URL else serve(url)

    monkeypatch.setattr(zarasai.http, "get", corrected)
    monkeypatch.setattr(build, "live_or_snapshot", lambda name, live, snap: (snap()[0], None))
    assert zarasai.main(["--out", str(tmp_path)]) == 1
    assert not (tmp_path / "schedule.json").exists()
    assert "re-transcribe pipeline/data/rules-zarasu-r.json" in capsys.readouterr().err


def test_pages_without_the_files_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(zarasai.http, "get", lambda url, timeout=0: b"<html></html>")
    monkeypatch.setattr(build, "live_or_snapshot", lambda name, live, snap: (snap()[0], None))
    assert zarasai.main(["--out", str(tmp_path)]) == 1
    assert not (tmp_path / "schedule.json").exists()


def test_the_window_moves_with_the_day(scan, monkeypatch):
    monkeypatch.setattr(zarasai.http, "get", serve)
    later = TODAY + timedelta(days=60)
    files, _ = zarasai.download(later, 31)
    result = zarasai.parse_file(*files[0])
    assert max(d for a in result.areas for d in a.dates) <= later + timedelta(days=400)
    assert min(d for a in result.areas for d in a.dates) >= later - timedelta(days=31)


# --- the copy --------------------------------------------------------------------

# Made up here, so this file has none: a Google API key and a reCAPTCHA site key.
KEY = "AIza" + "x" * 35
RECAPTCHA = "6L" + "y" * 38


def refused(url, timeout=0):
    raise OSError("HTTP Error 403: Forbidden")


def test_the_copy_when_the_site_refuses_the_job(scan, tmp_path, monkeypatch):
    def with_a_key(url, timeout=0):
        page = serve(url)
        keys = f'<script src="x.js?key={KEY}&render={RECAPTCHA}"></script></head>'
        return page.replace(b"</head>", keys.encode())

    monkeypatch.setattr(zarasai.http, "get", with_a_key)
    copy = tmp_path / "copy"
    assert zarasai.save_copy(copy, TODAY)
    # The page, the scan and the packaging file, and copy.json; the page's keys left out.
    index = json.loads((copy / "copy.json").read_text(encoding="utf-8"))
    assert index["takenAt"] == "2026-11-22" and index["page"] == zarasai.PAGE_URL
    assert index["files"] == ["misriu.pdf", PACKAGING_URL.rsplit("/", 1)[1]]
    page = (copy / "page.html").read_bytes()
    assert KEY.encode() not in page and b"AIza_REDACTED" in page
    assert RECAPTCHA.encode() not in page and b"render=6L_REDACTED" in page
    # The same files again: no change, even with new markup.
    assert not zarasai.save_copy(copy, date(2026, 11, 23))

    monkeypatch.setattr(zarasai.http, "get", refused)
    monkeypatch.setattr(zarasai, "COPY_DIR", copy)
    files, warnings = zarasai.download(TODAY, 31)
    assert [f.file_name for f, _ in files] == index["files"]
    assert files[0][1] == SCAN
    assert warnings == [
        f"{zarasai.PAGE_URL}: unavailable (HTTP Error 403: Forbidden); used the copy from "
        "2026-11-22 (0 days old)"
    ]
    # The hash check reads the copy's scan.
    assert len(zarasai.parse_file(*files[0]).areas) == 26
    # Without a copy, the error.
    monkeypatch.setattr(zarasai, "COPY_DIR", tmp_path / "none")
    with pytest.raises(OSError, match="403"):
        zarasai.download(TODAY, 31)


def test_a_new_scan_in_the_copy_stops_the_build(scan, tmp_path, monkeypatch):
    """The daily refresh takes a new scan into the copy; the build that reads it fails."""
    monkeypatch.setattr(zarasai.http, "get", serve)
    copy = tmp_path / "copy"
    zarasai.save_copy(copy, TODAY)
    monkeypatch.setattr(
        zarasai.http, "get", lambda url, timeout=0: SCAN + b"!" if url == SCAN_URL else serve(url)
    )
    assert zarasai.save_copy(copy, date(2026, 11, 23))
    monkeypatch.setattr(zarasai.http, "get", refused)
    monkeypatch.setattr(zarasai, "COPY_DIR", copy)
    files, _ = zarasai.download(date(2026, 11, 23), 31)
    with pytest.raises(ValidationError, match="the published scan changed"):
        zarasai.parse_file(*files[0])


def test_the_committed_copy_can_be_read(monkeypatch):
    """The copy in pipeline/data, as the daily job reads it on GitHub's runners. It is
    refreshed daily, so only that it is read: a new scan in it is the build's to report."""
    monkeypatch.setattr(zarasai.http, "get", refused)
    files, warnings = zarasai.download(date.today(), 31)
    assert "used the copy from" in warnings[0]
    assert [f.kind for f, _ in files][0] == "household"
    assert {f.kind for f, _ in files} == {"household", "packaging"}
    for file, content in files[1:]:
        assert zarasai.parse_file(file, content).areas
    page = (zarasai.COPY_DIR / "page.html").read_bytes()
    assert not re.search(rb"AIza[0-9A-Za-z_-]{35}", page)

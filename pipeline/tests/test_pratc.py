"""Panevėžio RATC: the page, the three layouts of its spreadsheets, the places of Pasvalio r.,
Rokiškio r., Biržų r. and Panevėžio r., next year and the published file."""

import copy
import dataclasses
import hashlib
import io
import json
from collections import defaultdict
from datetime import date
from functools import cache
from urllib.parse import unquote, urlsplit

import openpyxl
import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import pratc, pratc_word, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
PAGE = fixture("pratc/page.html").decode("utf-8")
# The files the page links, as saved in fixtures/pratc/.
FILES = {
    "Bendro ir individualaus naudojimo mišrių kom- atliekų kont- aptarnavimo grafikas.xlsx": (
        "pasvalio-r-mka.xlsx"
    ),
    "Individualaus naudojimo pakuočių konteinerių aptarnavimo grafikas.xlsx": (
        "pasvalio-r-pakuotes.xlsx"
    ),
    "Maisto atliekų konteinerių aptarnavimo grafikas_Pasvalio r-.xlsx": "pasvalio-r-maistas.xlsx",
    "Mišrių komunalinių atliekų surinkimo grafikas.xlsx": "rokiskio-r-mka.xlsx",
    "Pakuočių konteinerių (individualių valdų) aptarnavimo grafikas.xlsx": (
        "rokiskio-r-pakuotes.xlsx"
    ),
    "Maisto atliekų surinkimo grafikas_Rokiškio r-.xlsx": "rokiskio-r-maistas.xlsx",
    "INDIVIDUALIŲ VALDŲ mišrių kom- ir pakuočių atliekų kont- aptarnavimo grafikas.xlsx": (
        "birzu-r-individualios.xlsx"
    ),
    "NAUJAS Maisto atliekų konteinerių aptranavimo grafikas_Biržų r-.xlsx": "birzu-r-maistas.xlsx",
    "Pakuočių konteinerių (individualių valdų) aptarnavimo grafikas1.xlsx": (
        "panevezio-r-pakuotes.xlsx"
    ),
    "Pakuočių stiklo konteinerių (individualių valdų) aptarnavimo grafikas.xlsx": (
        "panevezio-r-stiklas.xlsx"
    ),
    "Mišrių komunalinių grafikas1.doc": "panevezio-r-mka.doc",
}
REGISTRIES = {
    "pasvalys": "registry-pasvalio-r-2026-11-21.json",
    "rokiskis": "registry-rokiskio-r-2026-11-21.json",
    "birzai": "registry-birzu-r-2026-11-21.json",
    "panevezio-r": "registry-panevezio-r-2026-11-21.json",
}


def serve(url, timeout=0):
    """The saved files, as pratc.http.get."""
    return fixture(f"pratc/{FILES[unquote(urlsplit(url).path).rsplit('/', 1)[-1]]}")


def saved(municipality, name):
    """A saved file as the page links it."""
    files, _ = pratc.find_files(PAGE)
    source = next(f for m, f, _ in files if m is municipality and FILES[f.file_name] == name)
    return source, fixture(f"pratc/{name}")


def parsed(municipality, name):
    """A file's rows; read only, shared by the tests."""
    return _parsed(municipality.provider.id, name)


@cache
def _parsed(key, name):
    municipality = pratc.BY_ID[key]
    return pratc.parse_file(*saved(municipality, name), municipality)


def registry(municipality):
    return Registry.load(FIXTURES / "pratc" / REGISTRIES[municipality.provider.id])


def build(municipality, today=TODAY, keep_days=31):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pratc.http, "get", serve)
        source = pratc.source(municipality, lambda: PAGE)
        files, warnings = source.download(today, keep_days)
        data, more = build_dataset(files, registry(municipality), today, keep_days, source)
    return files, data, warnings + more


@pytest.fixture(scope="module")
def parts():
    return {m.provider.id: build(m) for m in pratc.MUNICIPALITIES}


@pytest.fixture(scope="module")
def whole_year():
    """Every date of 2026 kept."""
    return {m.provider.id: build(m, keep_days=366)[1] for m in pratc.MUNICIPALITIES}


def place(data, name, kind=None, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and kind in (None, loc["type"])
        and district in (None, loc["district"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def area_of(data, location, kind="household"):
    return row(data, location["schedule"][kind]["area"])


def street_rows(data, town, kind, label):
    """The rows of a street of a town; None if the app is left to offer the town's rows."""
    location = place(data, town, "m.")
    key = next(key for key, text in location["streets"] if text == label)
    return location["schedule"][kind]["streets"].get(key)


# --- the page ----------------------------------------------------------------------------


def test_finds_the_files_of_individual_houses():
    files, warnings = pratc.find_files(PAGE)
    found = {(m.label, f.kind, FILES[f.file_name], year) for m, f, year in files}
    assert found == {
        ("Pasvalio r.", "household", "pasvalio-r-mka.xlsx", 2026),
        ("Pasvalio r.", "packaging", "pasvalio-r-pakuotes.xlsx", 2026),
        ("Pasvalio r.", "food", "pasvalio-r-maistas.xlsx", 2026),
        ("Rokiškio r.", "household", "rokiskio-r-mka.xlsx", 2026),
        ("Rokiškio r.", "packaging", "rokiskio-r-pakuotes.xlsx", 2026),
        ("Rokiškio r.", "food", "rokiskio-r-maistas.xlsx", 2026),
        ("Biržų r.", "household", "birzu-r-individualios.xlsx", 2026),
        # Linked from /uploads/ without a year: read from its title.
        ("Biržų r.", "food", "birzu-r-maistas.xlsx", None),
        # Panevėžio r.: its mixed waste is a Word document; its food waste isn't read.
        ("Panevėžio r.", "household", "panevezio-r-mka.doc", 2026),
        ("Panevėžio r.", "packaging", "panevezio-r-pakuotes.xlsx", 2026),
        ("Panevėžio r.", "glass", "panevezio-r-stiklas.xlsx", 2026),
    }
    assert warnings == []
    assert all(f.url.startswith("https://www.pratc.lt/uploads/") for _, f, _ in files)
    # Not the link without text next to Biržų r.'s food waste file (an old file, which
    # answers 403), nor shared containers, businesses, textiles, cemeteries or bulky waste.
    assert not any("atnaujintas" in f.file_name for _, f, _ in files)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Mišrių komunalinių atliekų surinkimo grafikas", "household"),
        ("Pakuočių (individualių valdų) konteinerių aptarnavimo grafikas", "packaging"),
        ("Pakuočių (stiklo) atliekų konteinerių aptarnavimo grafikas", "glass"),
        ("Pakuočių ir stiklo atliekų iš INDIVIDUALIŲ VALDŲ išvežimo grafikas", "packaging"),
        ("Mišrių komunalinių ir pakuočių atliekų konteinerių grafikas", "household"),
        ("Maisto atliekų surinkimo grafikas", "food"),
        ("Didelių gabaritų atliekų surinkimo grafikas apvažiavimo būdu", None),
    ],
)
def test_the_kind_of_a_file_by_its_item(text, kind):
    assert pratc.file_kind(text) == kind


def test_a_word_document_of_a_kind_that_is_read_is_reported():
    html = PAGE.replace("Pasvalio%20r-.xlsx", "Pasvalio%20r-.docx")  # Pasvalio r.'s food waste file
    _, warnings = pratc.find_files(html)
    assert warnings == [
        "Pasvalio r.: Maisto atliekų konteinerių aptarnavimo grafikas_Pasvalio r-.docx: "
        "not a spreadsheet; not read"
    ]
    # Panevėžio r.'s mixed waste in another format than the Word 97-2003 one it reads.
    html = PAGE.replace("grafikas1.doc", "grafikas1.docx")
    files, warnings = pratc.find_files(html)
    assert warnings == [
        "Panevėžio r.: Mišrių komunalinių grafikas1.docx: not a Word 97-2003 document; not read"
    ]
    assert not any(f.kind == "household" for m, f, _ in files if m is pratc.PANEVEZIO_R)


def test_the_year_of_a_file_without_one_in_its_link():
    assert pratc.content_year(fixture("pratc/birzu-r-maistas.xlsx")) == 2026
    assert pratc.content_year(fixture("pratc/birzu-r-individualios.xlsx")) == 2026
    assert pratc.content_year(fixture("pratc/panevezio-r-mka.doc")) == 2026
    assert pratc.content_year(b"<html>Not found</html>") is None


def test_reads_this_year_and_later():
    def file(kind, name):
        return SourceFile(kind, f"https://www.pratc.lt/uploads/{name}", name)

    files = [
        (file("household", "a.xlsx"), 2025),
        (file("household", "b.xlsx"), 2026),
        (file("household", "c.xlsx"), 2027),
        (file("packaging", "d.xlsx"), 2026),
        (file("packaging", "e.xlsx"), 2026),  # a correction linked after the first
        (file("food", "f.xlsx"), None),
    ]
    selected, warnings = pratc.select_files(files, pratc.PASVALYS, TODAY)
    assert [f.file_name for f in selected] == ["b.xlsx", "c.xlsx", "e.xlsx"]
    assert warnings == [
        "Pasvalio r.: f.xlsx: no year in its link or titles; not read",
        "Pasvalio r.: d.xlsx: not read, e.xlsx is a newer packaging schedule for 2026",
    ]
    # In January, before next year's files: the newest, with a warning.
    selected, warnings = pratc.select_files(files[:2], pratc.PASVALYS, date(2027, 1, 5))
    assert [f.file_name for f in selected] == ["b.xlsx"]
    assert warnings == ["Pasvalio r.: no household schedule for 2027 on the page"]


# --- the spreadsheets --------------------------------------------------------------------


def test_routes_of_a_whole_year():
    result = parsed(pratc.PASVALYS, "pasvalio-r-mka.xlsx")
    assert len(result.areas) == 31
    assert {a.kind for a in result.areas} == {"household"}
    first = result.areas[0]
    assert first.name == "Pasvalio apylinkių sen.: Diliauskų k., Kiemelių k., Papyvesių k."
    assert min(first.dates) == date(2026, 1, 5) and max(first.dates) == date(2026, 12, 21)
    assert len(first.dates) == 26 and first.weekday == "Pirmadienis"
    # The last row, "BENDRO NAUDOJIMO KONTEINERIAI: ..." with weekdays for dates.
    assert result.warnings == [
        "Bendro ir individualaus naudojimo mišrių kom- atliekų kont- aptarnavimo grafikas.xlsx "
        "[Pasvalio raj. MKA 2026] row 34: shared containers; not read"
    ]


def test_a_sheet_per_waste_type_named_by_its_title():
    result = parsed(pratc.PASVALYS, "pasvalio-r-pakuotes.xlsx")
    kinds = [a.kind for a in result.areas]
    # The sheets are "... AŽ ind. mišri pak" (mixed packaging) and "... AŽ ind. stiklas".
    assert kinds.count("packaging") == 10 and kinds.count("glass") == 30
    result = parsed(pratc.ROKISKIS, "rokiskio-r-pakuotes.xlsx")
    kinds = [a.kind for a in result.areas]
    assert kinds.count("packaging") == 14 and kinds.count("glass") == 42
    # The notes under the tables ("Taip pat ... galite rasti ...") are no routes.
    assert result.warnings == []
    result = parsed(pratc.PANEVEZIO_R, "panevezio-r-stiklas.xlsx")
    assert {a.kind for a in result.areas} == {"glass"} and len(result.areas) == 48
    # Nor the waste code under the table ("KODAS | 20 01 02 02").
    assert result.warnings == []


def test_a_rule_and_a_row_of_days_per_route():
    result = parsed(pratc.ROKISKIS, "rokiskio-r-mka.xlsx")
    assert len(result.areas) == 18
    first = result.areas[0]
    assert first.name.startswith("Degenių k., Rumpiškėnų, Rimgaudiškio k.")
    # "Pirmą mėnesio ketvirtadienį": the first Thursday of each month.
    assert sorted(first.dates)[:3] == [date(2026, 1, 1), date(2026, 2, 5), date(2026, 3, 5)]
    assert len(first.dates) == 12 and first.weekday == "Ketvirtadienis"
    # The routes of shared containers have a rule ("Kiekvieną mėnesio pirmadienį") and no days.
    assert [w.rsplit(": ", 1)[-1] for w in result.warnings] == ["shared containers; not read"] * 4


def test_a_day_the_rule_does_not_allow_is_reported():
    workbook = openpyxl.load_workbook(io.BytesIO(fixture("pratc/rokiskio-r-mka.xlsx")))
    workbook.active["C10"] = 2  # 2 January 2026 is a Friday, the rule says Thursday
    content = io.BytesIO()
    workbook.save(content)
    source, _ = saved(pratc.ROKISKIS, "rokiskio-r-mka.xlsx")
    result = pratc.parse_file(source, content.getvalue(), pratc.ROKISKIS)
    assert any(
        w.endswith("row 10: 2026-01-02 isn't a day of the rule 'Pirmą mėnesio ketvirtadienį'")
        for w in result.warnings
    )


def test_a_block_of_twelve_months_per_place():
    result = parsed(pratc.BIRZAI, "birzu-r-individualios.xlsx")
    assert len(result.areas) == 46 * 3
    papilys = [a for a in result.areas if a.name.startswith("Papilys, Valkiškiai")]
    assert {a.kind: len(a.dates) for a in papilys} == {"household": 13, "packaging": 13, "glass": 5}
    household = next(a for a in papilys if a.kind == "household")
    assert min(household.dates) == date(2026, 1, 14) and max(household.dates) == date(2026, 12, 16)
    # A town's route: twice a month for mixed waste, once for packaging.
    town = [a for a in result.areas if a.name.startswith("Biržų miestas: Alyvų g.")]
    assert {a.kind: len(a.dates) for a in town} == {"household": 26, "packaging": 13, "glass": 4}


def test_the_individual_part_of_a_cell_with_shared_containers():
    result = parsed(pratc.ROKISKIS, "rokiskio-r-maistas.xlsx")
    names = [a.name for a in result.areas]
    # "Individualūs: ... Bendro naudojimo: ...": only the first part; a row of shared
    # containers only isn't read.
    assert len(names) == 2
    assert names[0].startswith("Kavoliškio k., Parokiškės k., Serapiniškio k. Rokiškio m. - ")
    assert not any("Bendro" in name or "Individual" in name for name in names)
    assert result.warnings[-1].endswith("row 5: shared containers; not read")
    result = parsed(pratc.PASVALYS, "pasvalio-r-maistas.xlsx")
    assert [a.name for a in result.areas] == [
        "Ąžuolynės kaimas, Aukštikalnių kaimas, Pasvalio miestas"
    ]
    # Biržų r.: its shared containers' rows have days that aren't days ("1, 8, 22 29").
    assert len(parsed(pratc.BIRZAI, "birzu-r-maistas.xlsx").areas) == 3


def edited(name, cell, value):
    workbook = openpyxl.load_workbook(io.BytesIO(fixture(f"pratc/{name}")))
    workbook.active[cell] = value
    content = io.BytesIO()
    workbook.save(content)
    return content.getvalue()


@pytest.mark.parametrize(
    ("municipality", "name", "cell"),
    [
        (pratc.PASVALYS, "pasvalio-r-mka.xlsx", "D3"),
        (pratc.ROKISKIS, "rokiskio-r-mka.xlsx", "D10"),
        (pratc.BIRZAI, "birzu-r-individualios.xlsx", "C16"),
    ],
)
def test_unreadable_days_fail_loudly(municipality, name, cell):
    source, _ = saved(municipality, name)
    with pytest.raises(ValueError):
        pratc.parse_file(source, edited(name, cell, "kas antrą savaitę"), municipality)


def test_the_year_of_the_link_must_be_the_year_of_the_dates():
    source, content = saved(pratc.PASVALYS, "pasvalio-r-mka.xlsx")
    source = SourceFile(source.kind, source.url.replace("2026%20grafikai", "2027%20grafikai"), "x")
    with pytest.raises(ValueError, match="the link says 2027"):
        pratc.parse_file(source, content, pratc.PASVALYS)


def test_a_waste_type_the_file_does_not_have_fails():
    source, content = saved(pratc.PANEVEZIO_R, "panevezio-r-stiklas.xlsx")
    source = SourceFile("packaging", source.url, source.file_name)
    with pytest.raises(ValueError, match="glass in a packaging file"):
        pratc.parse_file(source, content, pratc.PANEVEZIO_R)


# --- Panevėžio r.'s mixed waste: a Word document ------------------------------------------

DOC = "panevezio-r-mka.doc"
DOC_TEXT = pratc_word.worddoc.text(fixture(f"pratc/{DOC}"))


def document_text(*replacements):
    """The document's text with `replacements` ((old, new), each found once), for
    pratc_word.worddoc.text."""
    text = DOC_TEXT
    for old, new in replacements:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return lambda content: text


def test_the_routes_of_the_document():
    document = pratc_word.read(fixture(f"pratc/{DOC}"))
    assert document.year == 2026
    numbers = [r.number for r in document.routes]
    # Routes 8 and 9 share a cell; 3* is a part of route 3's village with a route of its own.
    assert numbers == ["1", "2", "3", "3*", *map(str, range(4, 26))]
    first = document.routes[0]
    assert first.places == (
        "Geležių, Karsakiškio, Sodelių, Prūselių, Tiltagalių ir kitų Karsakiškio seniūnijos "
        "gyvenviečių"
    )
    assert first.rule == "ketvirtadieniai" and first.plain
    assert sorted(first.dates(2026))[:4] == [
        date(2026, 1, 8),
        date(2026, 2, 5),
        *[date(2026, 3, 5), date(2026, 4, 2)],
    ]
    # A list of streets over two lines without a comma between them.
    assert "Birutės, Ievų, Laisvės, Liaudies" in document.routes[6].places
    # Days without "d.", or with a stray full stop: "Kovas 13 27d", "Spalis . 16 d.".
    assert {d for d in document.routes[4].dates(2026) if d.month == 3} == {
        date(2026, 3, 13),
        date(2026, 3, 27),
    }
    assert document.routes[24].rule == "pirmadieniai-antradieniai"
    # Notes under four routes; marks in the days of three.
    assert [r.number for r in document.routes if not r.plain] == ["3", "4", "13", "14"]
    assert document.routes[2].first_note().startswith("*Vietoje 2026m. sausio 1d. Šeškų")
    assert document.routes[2].days[1] == [("*", 2, 3), ("", 15, 15), ("", 29, 29)]
    assert document.texts == [
        "Nurodytomis dienomis, prašome gyventojų, konteinerius išstumti prie gatvės nuo 7 val. "
        "ryto. Dėl iškilusių klausimų skambinti į UAB „Švaros komanda“ tel. : 0 652 75772 ."
    ]


def test_routes_with_notes_are_read_from_their_transcription():
    result = parsed(pratc.PANEVEZIO_R, DOC)
    rows = {a.name: a for a in result.areas}
    assert len(rows) == 29 and {a.kind for a in result.areas} == {"household"}
    # Route 3: 1 January moved to the 2nd for some villages, to the 3rd for others; one house
    # every four weeks.
    seskai = rows["Šeškų, Tičkūnų, Ūtos, Senamiesčio, Maksvytiškių gyvenviečių"]
    dembava = rows["Dembavos, Oželių, Vyčių, Keravos, Vaivadų, Velželio gyvenviečių"]
    assert min(seskai.dates) == date(2026, 1, 2) and min(dembava.dates) == date(2026, 1, 3)
    assert seskai.dates - {date(2026, 1, 2)} == dembava.dates - {date(2026, 1, 3)}
    house = rows["Šeškų k. (Panevėžio aplinkl. 201)"]
    assert len(house.dates) == 13 and house.dates < seskai.dates
    assert house.weekday == "Ketvirtadienis" and seskai.weekday is None
    # Route 4: "Vietoje 2027m. sausio 1d. aptarnausime sausio 2d.".
    piniava = rows["Piniavos, Staniūnų, Velžio, Liūdynės, Skynimų gyvenviečių"]
    assert max(piniava.dates) == date(2027, 1, 2)
    # A route without notes, from its days: 2026-09-27 (a Sunday) is reported, and kept.
    assert result.warnings == [
        "Mišrių komunalinių grafikas1.doc route 3*: 2026-09-27 isn't a day of the rule "
        "'ketvirtadieniai'"
    ]
    assert date(2026, 9, 27) in rows["Paežerio I k. (Miglės, Kedrų ir Medeinos gatvės)"].dates


def test_the_transcription_agrees_with_the_days_of_its_routes():
    """The committed transcription is of this file, and differs from the routes' days only as
    their notes say."""
    document = pratc_word.read(fixture(f"pratc/{DOC}"))
    transcription = pratc_word.load_transcription()
    routes = {r.text: r for r in document.routes}
    assert all(entry["text"] in routes for entry in transcription["routes"])
    for entry in transcription["routes"]:
        days = {d.isoformat() for d in routes[entry["text"]].dates(2026)}
        dates = [set(row["dates"]) for row in entry["rows"]]
        if entry["number"] == "3":
            assert set.union(*dates) == days and dates[3] < days
        elif entry["number"] == "4":
            assert dates == [days | {"2027-01-02"}]
        else:
            assert dates == [days]
    assert transcription["files"] == [
        {
            "url": saved(pratc.PANEVEZIO_R, DOC)[0].url,
            "sha256": hashlib.sha256(fixture(f"pratc/{DOC}")).hexdigest(),
        }
    ]
    # As the draft command writes it.
    assert pratc_word.TRANSCRIPTION.read_text(encoding="utf-8") == pratc_word.dump(transcription)


def test_a_changed_route_with_notes_must_be_transcribed_again(monkeypatch):
    source, content = saved(pratc.PANEVEZIO_R, DOC)
    monkeypatch.setattr(
        pratc_word.worddoc, "text", document_text(("Gruodis            *26 d.", "Gruodis  *28 d."))
    )
    with pytest.raises(
        ValueError,
        match=r"notes that schedule-panevezio-r-mixed.json doesn't "
        r"have: route 13 \('\*Vietoje 2026m\. gruodžio 25d",
    ):
        pratc.parse_file(source, content, pratc.PANEVEZIO_R)
    # A route without notes is read from the file: no transcription needed.
    monkeypatch.setattr(
        pratc_word.worddoc,
        "text",
        document_text(("Gruodis           07 d.\x07", "Gruodis 14 d.\x07")),
    )
    rows = {a.name: a for a in pratc.parse_file(source, content, pratc.PANEVEZIO_R).areas}
    raguva = next(a for name, a in rows.items() if name.startswith("Raguvos, Nevėžio"))
    assert max(raguva.dates) == date(2026, 12, 14)


def test_a_route_with_new_notes_or_a_new_text_after_the_table_fails():
    source, content = saved(pratc.PANEVEZIO_R, DOC)
    transcription = pratc_word.load_transcription()
    without = {**transcription, "routes": transcription["routes"][1:]}  # not route 3
    with pytest.raises(ValueError, match=r"route 3 \('\*Vietoje 2026m\. sausio 1d\."):
        pratc_word.parse(source, content, "panevezio-r", without)
    without = {**transcription, "texts": []}
    with pytest.raises(ValueError, match="text after the table that .* doesn't have"):
        pratc_word.parse(source, content, "panevezio-r", without)


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        ("Sausis              08 d.", "Sausis   kas antrą savaitę", "not days of Sausis"),
        ("Vasaris            05 d.", "Vasaris            30 d.", "day 30 of Vasaris"),
        ("Vasaris            05 d.                   Rugpjūtis", "Rugpjūtis", "no days of vasaris"),
        ("Vasaris            05 d.", "               05 d.", "'05 d.' before the months"),
        ("Gegužė            28 d.", "Kovas  28 d.", "Kovas twice"),
        ("(ketvirtadieniai)\rSausis", "\rSausis", "route 1: no weekdays in brackets"),
        ("grafikai 2026 m.", "grafikai", "no title with the year"),
    ],
)
def test_unreadable_routes_fail_loudly(monkeypatch, old, new, error):
    source, content = saved(pratc.PANEVEZIO_R, DOC)
    monkeypatch.setattr(pratc_word.worddoc, "text", document_text((old, new)))
    with pytest.raises(ValueError, match=error):
        pratc.parse_file(source, content, pratc.PANEVEZIO_R)


def test_the_year_of_the_link_must_be_the_year_of_the_document():
    source, content = saved(pratc.PANEVEZIO_R, DOC)
    source = SourceFile(source.kind, source.url.replace("2026%20grafikai", "2027%20grafikai"), "x")
    with pytest.raises(ValueError, match=r"a schedule of 2026, the link says \[2027\]"):
        pratc.parse_file(source, content, pratc.PANEVEZIO_R)


def test_a_document_that_cannot_be_read_keeps_yesterdays_mixed_waste(parts):
    _, data, _ = parts["panevezio-r"]
    published = merge_parts([(pratc.PANEVEZIO_R.provider, {**data, "warnings": 0})])
    source, content = saved(pratc.PANEVEZIO_R, DOC)
    damaged = content[:4096]
    result = pratc.parse_file(source, damaged, pratc.PANEVEZIO_R, lambda: published)
    household = [a for a in data["areas"] if a["kind"] == "household"]
    assert sorted(a.id for a in result.areas) == sorted(a["id"] for a in household)
    assert result.warnings == [
        f"Mišrių komunalinių grafikas1.doc: can't be read ({result.warnings[0].split('(', 1)[1]}"
    ]
    assert result.warnings[0].endswith("yesterday's 29 household rows of Panevėžio r. are kept")
    # The spreadsheets are still read; without published data the build fails.
    with pytest.raises(ValueError):
        pratc.parse_file(source, damaged, pratc.PANEVEZIO_R)


def test_a_draft_of_the_transcription():
    url = saved(pratc.PANEVEZIO_R, DOC)[0].url
    content = fixture(f"pratc/{DOC}")
    committed = pratc_word.load_transcription()
    # Nothing to add: the committed entries are kept as they are.
    data, todo = pratc_word.draft([(url, content)], committed)
    assert data == committed and todo == []
    # From nothing: a draft of each route with notes, its dates its days.
    data, todo = pratc_word.draft([(url, content)], {})
    assert [e["number"] for e in data["routes"]] == ["3", "4", "13", "14"]
    route3 = data["routes"][0]["rows"]
    assert len(route3) == 1 and route3[0]["dates"][:3] == ["2026-01-02", "2026-01-03", "2026-01-15"]
    assert len(todo) == 5 and todo[-1].startswith("a text after the table")


@pytest.mark.parametrize(
    ("name", "text", "rest"),
    [
        (
            "Geležių, Karsakiškio, Sodelių, Prūselių, Tiltagalių ir kitų Karsakiškio seniūnijos "
            "gyvenviečių",
            "Geležių, Karsakiškio, Sodelių, Prūselių, Tiltagalių",
            "Karsakiškio",
        ),
        (
            # "Sodų" is a street here (Sodų g.), not gardens.
            "Naujarodžių gyvenvietės ir Krekenavos gatvių: Akmenės, Antanaičio, Sodų, Žibučių",
            "Naujarodžių, Krekenavos m., Akmenės g., Antanaičio g., Sodų g., Žibučių g.",
            None,
        ),
        (
            "Ramygalos gatvių: Biliūno, Dariaus ir Girėno, Malūno sk., Laisvės a., Vienkiemio "
            "taip pat Daniūnų, Barklainių ir Butkiškio gyvenviečių",
            "Ramygalos m., Biliūno g., Dariaus ir Girėno g., Malūno sk., Laisvės a., Vienkiemio "
            "g., Daniūnų, Barklainių, Butkiškio",
            None,
        ),
        (
            "Vaivadų, Paežerio I (visos išskyrus Miglės, Kedrų ir Medeinos gatvės), Šeškų",
            "Vaivadų, Paežerio I (išskyrus Miglės g., Kedrų g., Medeinos g.), Šeškų",
            None,
        ),
        (
            "Bernatonių ir Bernatonių sodų, Klevečkinės, gyvenviečių",
            "Bernatonių, Bernatonių, Klevečkinės",
            None,
        ),
        ("Plukių sodų gyventojų", "Plukių", None),
        (
            "Ragaudžių km., ir Vaišvilčių km., Tarnagalos km., gyvenviečių",
            "Ragaudžių k., Vaišvilčių k., Tarnagalos k.",
            None,
        ),
        (
            "Naujamiesčio, Berčiūnų, Liberiškio, gyventojams",
            "Naujamiesčio, Berčiūnų, Liberiškio",
            None,
        ),
    ],
)
def test_the_places_of_a_route(name, text, rest):
    assert pratc_word.places(name) == (text, rest)


# --- the places --------------------------------------------------------------------------


def test_counts(parts):
    counts = {}
    for key, (_, data, warnings) in parts.items():
        kinds = {}
        for area in data["areas"]:
            kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
        served = {
            kind: sum(1 for loc in data["locations"] if kind in loc.get("schedule", {}))
            for kind in kinds
        }
        counts[key] = (kinds, served, len(warnings))
    assert counts == {
        "pasvalys": (
            {"household": 31, "packaging": 10, "glass": 30, "food": 1},
            {"household": 259, "packaging": 233, "glass": 230, "food": 3},
            9,
        ),
        "rokiskis": (
            {"household": 18, "packaging": 14, "glass": 42, "food": 2},
            {"household": 249, "packaging": 352, "glass": 350, "food": 6},
            20,
        ),
        "birzai": (
            {"household": 46, "packaging": 46, "glass": 46, "food": 3},
            {"household": 292, "packaging": 292, "glass": 292, "food": 4},
            24,
        ),
        "panevezio-r": (
            {"household": 29, "packaging": 16, "glass": 48},
            {"household": 248, "packaging": 398, "glass": 397},
            6,
        ),
    }


@pytest.mark.parametrize(
    ("key", "name", "district", "kind", "count", "first", "last", "weekday"),
    [
        # As the files have them.
        ("pasvalys", "Diliauskai", "Pasvalio apylinkių", "household", 26, "01-05", "12-21", 0),
        ("rokiskis", "Kazliškis", "Kazliškio", "household", 12, "01-01", "12-03", 3),
        ("birzai", "Papilys", "Papilio", "household", 13, "01-14", "12-16", 2),
        ("panevezio-r", "Raguva", "Raguvos", "glass", 4, "03-03", "11-10", 1),
        ("panevezio-r", "Smilgiai", "Smilgių", "household", 13, "01-20", "12-22", 1),
    ],
)
def test_a_place_of_each_municipality(
    whole_year, key, name, district, kind, count, first, last, weekday
):
    data = whole_year[key]
    dates = area_of(data, place(data, name, district=district), kind)["dates"]
    assert (len(dates), dates[0], dates[-1]) == (count, f"2026-{first}", f"2026-{last}")
    assert {date.fromisoformat(d).weekday() for d in dates} == {weekday}


def test_sections_of_elderships(parts):
    _, data, _ = parts["pasvalys"]
    # "Daujėnų sen.: Vytautų k. Krinčino sen.: Aukštuolių k., ...": each in its eldership.
    assert area_of(data, place(data, "Vytautai", district="Daujėnų"))["name"].startswith(
        "Daujėnų sen.: Vytautų k."
    )
    # "Pasvalio apylinkių sen.: Medinių k., Vytartų k., Vaškų sen., Dovydų k., ...": a comma
    # after an eldership's name.
    assert area_of(data, place(data, "Dovydai", district="Vaškų"))["name"].startswith(
        "Joniškėlio apylinkių sen.: Gailionių k."
    )
    # "Namišių sen.: Kiemėnai. Saločių sen.: ...": nominative, "Pagojis II".
    assert "packaging" in place(data, "Pagojis II")["schedule"]
    _, data, _ = parts["panevezio-r"]
    # "Krekenavos mstl. (išskyrus Beržytės g., ...)" and "(tik Beržytės g., ...)".
    krekenava = place(data, "Krekenava", "mstl.")["schedule"]["glass"]
    assert len(krekenava["streets"]) == 6 and "area" in krekenava


def test_town_streets_after_the_town(parts):
    _, data, _ = parts["pasvalys"]
    # "Pasvalio m. - Atžalyno g., ...", "Pasvalys - Ajerų g., ...",
    # "Pasvalio miesto sen., Pasvalys: Ajerų g., ...".
    assert street_rows(data, "Pasvalys", "household", "Atžalyno g.")
    assert street_rows(data, "Pasvalys", "packaging", "Ajerų g.")
    # A street of two words with a hyphen is one street, not two places.
    assert street_rows(data, "Joniškėlis", "glass", "G. Petkevičaitės-Bitės g.")
    _, data, _ = parts["rokiskis"]
    # "Rokiškio m. (Alyvų g., Aušros g., ...)".
    assert street_rows(data, "Rokiškis", "packaging", "Alyvų g.")


def test_streets_no_route_names_are_left_to_the_app(parts):
    for key, town in (("pasvalys", "Pasvalys"), ("rokiskis", "Rokiškis"), ("birzai", "Biržai")):
        _, data, _ = parts[key]
        for schedule in place(data, town, "m.")["schedule"].values():
            # No street gets an empty list ("no pickup"): the app offers the town's routes.
            assert all(schedule.get("streets", {}).values())
    _, data, _ = parts["pasvalys"]
    assert len(place(data, "Pasvalys", "m.")["schedule"]["household"]["streets"]) == 83


def test_dashed_lists_of_villages_and_streets(parts):
    _, data, _ = parts["rokiskis"]
    # "Miliūnų-Miegonių-Lauciūnų-Vyžūnos-Sodelių-Iciūnų kaimai".
    name = area_of(data, place(data, "Miegonys"))["name"]
    assert name.startswith("Miliūnų-Miegonių-Lauciūnų")
    # "Sinagogų-Mikėno-...-Pirties Respublikos-...-Jūžintų (už geležinkelio) gatvės": streets
    # of Rokiškis, the last some of its houses.
    route = street_rows(data, "Rokiškis", "household", "Sinagogų g.")
    assert route and row(data, route[0])["name"].startswith("Sinagogų-Mikėno")
    assert street_rows(data, "Rokiškis", "household", "Respublikos g.") == route
    # "Jūžintų (už geležinkelio)" and "Jūžintų (iki gel.pervažos)": the street's two routes.
    assert len(street_rows(data, "Rokiškis", "household", "Jūžintų g.")) == 2
    # "Obelių miestas ir priemiestis".
    assert area_of(data, place(data, "Obelių Priemiestis"))["name"].startswith("Antanašės-")


def test_an_eldership_after_a_settlement_tells_which(parts):
    _, data, _ = parts["rokiskis"]
    # "Obeliai- Pandėlio sen.-Buivėnai": the village of Pandėlio sen., not the town.
    village = place(data, "Obeliai", "k.", "Pandėlio")
    assert area_of(data, village)["name"].startswith("Moškėnų-Ilgalaukių")
    assert not area_of(data, place(data, "Obeliai", "m."))["name"].startswith("Moškėnų")
    _, data, _ = parts["birzai"]
    # "Papilys, ..., Parovėja (Papilio sen.)" and "Juodžioniai, Parovėja.": two villages.
    assert area_of(data, place(data, "Parovėja", district="Papilio"))["name"].startswith("Papilys")
    assert area_of(data, place(data, "Parovėja", district="Parovėjos"))["name"].startswith(
        "Juodžioniai"
    )


def test_villages_of_one_name_in_several_elderships(parts):
    _, data, _ = parts["rokiskis"]
    # Food waste "Bajorų k., Rokiškio m. - Aguonų g., ...": the Bajorai around Rokiškis, not
    # the one of Kriaunų sen.
    assert "food" in place(data, "Bajorai", district="Rokiškio kaimiškoji")["schedule"]
    assert "food" not in place(data, "Bajorai", district="Kriaunų")["schedule"]
    # Mixed waste: each in the route of the villages around it.
    kriaunu = area_of(data, place(data, "Bajorai", district="Kriaunų"))["name"]
    assert kriaunu.startswith("Rokiškėlių-Meldučių")
    # A name the list can't tell is reported, not given to both.
    reader = pratc.Places(
        pratc.Index(registry(pratc.ROKISKIS)), pratc.ROKISKIS.provider, defaultdict(dict)
    )
    area = Area("household", "Bajorų k.", provider="rokiskis")
    assert reader.clauses(area)[0] == []
    assert reader.unknown == ["Rokiškio r.: Bajorų k. (in Kriaunų sen., Rokiškio kaimiškoji sen.)"]


def test_gardens_are_streets_of_the_settlements_that_have_them(parts):
    _, data, _ = parts["birzai"]
    route = "Biržų miestas: Agaro g."
    # "Liepų sodai: Rožių takas, ..., Samanų tak., ...": of Biržai and of Ruoliškis.
    assert row(data, street_rows(data, "Biržai", "household", "Rožių tak.")[0])["name"].startswith(
        route
    )
    ruoliskis = place(data, "Ruoliškis")
    assert area_of(data, ruoliskis)["name"].startswith(route)
    # "Rinkuškių sodai: Rožių aklg., ...": Rinkuškiai's, which the route names whole too.
    assert area_of(data, place(data, "Rinkuškiai"))["name"].startswith("Daudžgiriai")


def test_villages_of_one_name(parts):
    _, data, _ = parts["rokiskis"]
    # Named in two routes: the app asks.
    assert len(place(data, "Stanikūnai")["schedule"]["household"]["candidates"]) == 2
    _, data, _ = parts["birzai"]
    # "N. Radviliškis": the small town and the village of that name.
    for kind in ("mstl.", "k."):
        location = place(data, "Nemunėlio Radviliškis", kind)
        assert area_of(data, location)["name"].startswith("N. Radviliškis")


def test_names_that_match_nothing_are_reported(parts):
    _, _, warnings = parts["birzai"]
    unknown = sorted({w.split(": ", 2)[-1] for w in warnings if w.startswith("not a settlement")})
    assert unknown == [
        "Biržų m.: Bokšto g.",
        "Biržų m.: Karklų g.",
        "Biržų m.: S. Nėries g.",
        "Biržų m.: Sodo g.",
        "Biržų m.: Stirnų g.",
        "Biržų r.: Gerultiškis",
        "Biržų r.: Spalviškių girink.",
    ]
    _, _, warnings = parts["rokiskis"]
    assert "not a settlement or a street: household: Rokiškio r.: Klodnikų" in warnings
    _, _, warnings = parts["panevezio-r"]
    unknown = sorted({w.split(": ", 2)[-1] for w in warnings if w.startswith("not a settlement")})
    assert unknown == [
        "Panevėžio r.: Dvareliškių",
        "Panevėžio r.: Pučiakų",
        "Ramygalos m.: Lauko g.",
        "Ramygalos m.: Maironio g.",
        "Ramygalos m.: Šilo g.",
    ]


def mixed_waste(data, location):
    """The names of a place's mixed waste rows: (the row of the whole, {street: rows})."""
    schedule = location["schedule"]["household"]
    labels = dict(location.get("streets", []))
    streets = {
        labels[key]: [row(data, i)["name"] for i in ids]
        for key, ids in schedule.get("streets", {}).items()
    }
    return row(data, schedule["area"])["name"] if "area" in schedule else None, streets


def test_the_mixed_waste_routes_of_panevezio_r(parts):
    _, data, _ = parts["panevezio-r"]
    first = "Geležių, Karsakiškio, Sodelių, Prūselių, Tiltagalių ir kitų Karsakiškio"
    # "... ir kitų Karsakiškio seniūnijos gyvenviečių": every settlement of the eldership that
    # no other route names.
    karsakiskio = [loc for loc in data["locations"] if loc["district"] == "Karsakiškio"]
    assert all("household" in loc["schedule"] for loc in karsakiskio)
    assert mixed_waste(data, place(data, "Akmeniai", district="Karsakiškio"))[0].startswith(first)
    assert mixed_waste(data, place(data, "Paliūniškis"))[0].startswith("Paliūniškio, Klimbalės")
    # "Naujarodžių gyvenvietės ir Krekenavos gatvių: ...", "Krekenavos gatvių: ...": the
    # small town by street; a street no route names is left to the app.
    whole, streets = mixed_waste(data, place(data, "Krekenava", "mstl."))
    assert whole is None and len(streets) == 24
    assert streets["Akmenės g."] == streets["Vytauto g."]
    assert streets["Akmenės g."][0].startswith("Naujarodžių gyvenvietės ir Krekenavos gatvių")
    assert streets["Bažnyčios g."][0].startswith("Krekenavos gatvių: Bažnyčios")
    assert "Maironio g." not in streets
    assert "household" not in place(data, "Krekenava", "vs.").get("schedule", {})
    # Ramygala: "Vienkiemio" in two routes, "Laisvės" and "Laisvės a." (the register's only
    # Laisvės) too.
    _, streets = mixed_waste(data, place(data, "Ramygala", "m."))
    assert len(streets["Vienkiemio g."]) == 2 and len(streets["Laisvės a."]) == 2
    assert streets["Dariaus ir Girėno g."][0].startswith("Ramygalos gatvių: Biliūno")
    # Paežerys I: route 3 but three streets, which have route 3* ("3.* Paežerio I k. ...").
    whole, streets = mixed_waste(data, place(data, "Paežerys I"))
    assert whole.startswith("Paežerio I (visos išskyrus")
    assert set(streets) == {"Miglės g.", "Kedrų g.", "Medeinos g."}
    assert streets["Miglės g."] == ["Paežerio I k. (Miglės, Kedrų ir Medeinos gatvės)"]
    # Šeškai: one house of Panevėžio aplinkl. has a route of its own, one more choice.
    whole, streets = mixed_waste(data, place(data, "Šeškai"))
    assert whole.startswith("Šeškų, Tičkūnų")
    assert sorted(streets["Panevėžio aplinkl."]) == [
        "Šeškų k. (Panevėžio aplinkl. 201)",
        "Šeškų, Tičkūnų, Ūtos, Senamiesčio, Maksvytiškių gyvenviečių",
    ]
    # Oželiai, named only in route 3's note about 1 January.
    assert mixed_waste(data, place(data, "Oželiai"))[0].startswith("Dembavos, Oželių")
    # "Plukių sodų", "Bernatonių ir Bernatonių sodų": the villages, whose streets the gardens'
    # are in the register.
    assert mixed_waste(data, place(data, "Plukiai"))[0] == "Plukių sodų gyventojų"
    assert mixed_waste(data, place(data, "Bernatoniai", "k."))[0].startswith("Bernatonių ir")


# --- next year ---------------------------------------------------------------------------


def next_year(result: ParseResult, rename=None) -> ParseResult:
    """The same routes a year later; `rename`: a route worded otherwise."""
    shifted = copy.deepcopy(result)
    for area in shifted.areas:
        area.dates = {d.replace(year=2027) for d in area.dates if not (d.month, d.day) == (2, 29)}
        if rename and area.name.startswith(rename[0]):
            area.name = rename[1]
    return shifted


def test_next_year_continues_the_same_routes():
    source, _ = saved(pratc.PASVALYS, "pasvalio-r-mka.xlsx")
    this = parsed(pratc.PASVALYS, "pasvalio-r-mka.xlsx")
    later = next_year(this, ("Pušaloto sen.", "Pušaloto sen.: Mikoliškio k."))
    results = [(source, copy.deepcopy(this)), (source, later)]
    warnings = pratc.combine(results, registry(pratc.PASVALYS), TODAY, pratc.PASVALYS)
    joined = results[0][1].areas
    first = next(a for a in joined if a.name.startswith("Pasvalio apylinkių sen.: Diliauskų"))
    assert max(first.dates).year == 2027 and min(first.dates).year == 2026
    assert results[1][1].areas == []
    # Pušalotas' route covers fewer places in 2027: its dates wait for 1 January.
    assert warnings == [
        "household: the 2027 route 'Pušaloto sen.: Mikoliškio k.' doesn't match one 2026 route; "
        "its dates are left out until 2027",
        "household: the 2026 route 'Pušaloto sen.: Mikoliškio k., Pušaloto mstl., Pušaloto vs.' "
        "has no dates for 2027",
    ]
    # On 1 January, 2027 is the schedule in force.
    results = [(source, copy.deepcopy(this)), (source, next_year(this))]
    pratc.combine(results, registry(pratc.PASVALYS), date(2027, 1, 1), pratc.PASVALYS)
    assert results[0][1].areas == [] and len(results[1][1].areas) == 31


def test_next_year_is_checked_when_it_appears():
    source, _ = saved(pratc.PASVALYS, "pasvalio-r-mka.xlsx")
    this = parsed(pratc.PASVALYS, "pasvalio-r-mka.xlsx")
    later = next_year(this)
    later.areas = later.areas[:5]
    with pytest.raises(ValueError, match="only 5 household routes in the 2027 file"):
        pratc.combine(
            [(source, copy.deepcopy(this)), (source, later)],
            registry(pratc.PASVALYS),
            TODAY,
            pratc.PASVALYS,
        )


def test_next_years_document_continues_the_same_routes():
    """Panevėžio r.'s routes are told apart by the places DocumentRoutes reads in their names,
    the house of route 3 and the eldership of route 1 too."""
    source, _ = saved(pratc.PANEVEZIO_R, DOC)
    this = parsed(pratc.PANEVEZIO_R, DOC)
    results = [(source, copy.deepcopy(this)), (source, next_year(this))]
    warnings = pratc.combine(results, registry(pratc.PANEVEZIO_R), TODAY, pratc.PANEVEZIO_R)
    assert warnings == [] and results[1][1].areas == []
    rows = {a.name: a for a in results[0][1].areas}
    for name in ("Šeškų k. (Panevėžio aplinkl. 201)", "Plukių sodų gyventojų"):
        assert {d.year for d in rows[name].dates} == {2026, 2027}


# --- the published file ------------------------------------------------------------------


def test_one_file_for_the_four_municipalities(parts, tmp_path):
    built = [
        (pratc.BY_ID[key].provider, {**data, "warnings": len(warnings)})
        for key, (_, data, warnings) in parts.items()
    ]
    dataset = merge_parts(built, pratc.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == [
        "pasvalys",
        "rokiskis",
        "birzai",
        "panevezio-r",
    ]
    assert {p["name"] for p in dataset["providers"]} == {pratc.COMPANY}
    (tmp_path / "panevezio-ratc").mkdir()
    (tmp_path / "panevezio-ratc" / "schedule.json").write_text(
        json.dumps(dataset), encoding="utf-8"
    )
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    # A source each, counting the settlements with a schedule.
    assert 'siuksliaveze_data_places{source="pasvalys"} 267' in text
    assert 'siuksliaveze_data_places{source="panevezio-r"} 453' in text
    assert 'siuksliaveze_data_areas{source="birzai",kind="food"} 3' in text
    # 2026-12-31: the last mixed waste pickup of Biržų r.
    last = 'siuksliaveze_data_last_date_timestamp_seconds{source="birzai",kind="household"}'
    assert f"{last} 1798675200" in text


class _Today(date):
    @classmethod
    def today(cls):
        return TODAY


def _offline(*args, **kwargs):
    raise OSError("offline")


def test_a_municipality_whose_places_stop_matching_keeps_yesterdays_part(
    parts, monkeypatch, tmp_path
):
    """Panevėžio r. matching too few settlements keeps its part of the published file; the
    other three are built (main, from the saved page and files and the snapshots)."""
    yesterday = "2026-11-20T04:30:00+00:00"
    _, data, _ = parts["panevezio-r"]
    published = merge_parts(
        [(pratc.PANEVEZIO_R.provider, {**data, "generatedAt": yesterday, "warnings": 0})]
    )
    monkeypatch.setattr(pratc.http, "get", serve)
    monkeypatch.setattr(pratc, "fetch_page", lambda: PAGE)
    monkeypatch.setattr(pratc, "date", _Today)
    monkeypatch.setattr(pratc.address_register, "fetch", _offline)
    monkeypatch.setattr(pratc.address_points, "fetch", _offline)
    monkeypatch.setattr(pratc.build, "load_published", lambda url: lambda: published)
    strict = dataclasses.replace(pratc.PANEVEZIO_R, min_places=10_000)
    monkeypatch.setattr(pratc, "MUNICIPALITIES", (*pratc.MUNICIPALITIES[:3], strict))
    assert pratc.main(["--out", str(tmp_path)]) == 0
    dataset = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    built = {p["id"]: p["generatedAt"] for p in dataset["providers"]}
    assert built["panevezio-r"] == yesterday
    assert all(built[key] > yesterday for key in ("pasvalys", "rokiskis", "birzai"))
    ours = [a for a in dataset["areas"] if a["provider"] == "panevezio-r"]
    assert len(ours) == len(data["areas"])
    addresses = json.loads((tmp_path / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > 70_000
    # --strict: the build fails instead.
    assert pratc.main(["--strict", "--out", str(tmp_path / "strict")]) == 1


def test_a_route_to_transcribe_again_keeps_yesterdays_mixed_waste(
    parts, monkeypatch, tmp_path, capsys
):
    """Panevėžio r.'s document with a route the transcription doesn't have: its mixed waste
    rows are yesterday's, its packaging and glass today's, with a warning on the run."""
    yesterday = "2026-11-20T04:30:00+00:00"
    _, data, _ = parts["panevezio-r"]
    old = [dict(a, dates=a["dates"][:1]) if a["kind"] == "household" else a for a in data["areas"]]
    published = merge_parts(
        [(pratc.PANEVEZIO_R.provider, {**data, "areas": old, "generatedAt": yesterday})]
    )
    transcription = pratc_word.load_transcription()
    transcription["routes"] = transcription["routes"][1:]  # not route 3
    monkeypatch.setattr(pratc_word, "load_transcription", lambda: transcription)
    monkeypatch.setattr(pratc.http, "get", serve)
    monkeypatch.setattr(pratc, "fetch_page", lambda: PAGE)
    monkeypatch.setattr(pratc, "date", _Today)
    monkeypatch.setattr(pratc.address_register, "fetch", _offline)
    monkeypatch.setattr(pratc.address_points, "fetch", _offline)
    monkeypatch.setattr(pratc.build, "load_published", lambda url: lambda: published)
    monkeypatch.setattr(pratc, "MUNICIPALITIES", (pratc.PANEVEZIO_R,))
    assert pratc.main(["--out", str(tmp_path)]) == 0
    dataset = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert dataset["providers"][0]["generatedAt"] > yesterday
    rows = {a["id"]: a for a in dataset["areas"]}
    assert all(rows[a["id"]]["dates"] == a["dates"] for a in old)  # yesterday's household rows
    assert {a["kind"] for a in dataset["areas"]} == {"household", "packaging", "glass"}
    out = capsys.readouterr().out
    assert "::warning::Panevėžio r.: Mišrių komunalinių grafikas1.doc: can't be read" in out
    assert "re-transcribe it" in out
    # --strict (the live-build check): the build fails.
    assert pratc.main(["--strict", "--out", str(tmp_path / "strict")]) == 1

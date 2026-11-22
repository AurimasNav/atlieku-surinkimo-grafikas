"""Kėdainių r.: the municipality's page, the elderships' Word and PDF tables with the glass days
in red, the places, and the folder."""

import dataclasses
import io
import json
import zipfile
from datetime import date
from xml.sax.saxutils import escape

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, kedainiai, regions, status
from schedule_pipeline.build import build_dataset
from schedule_pipeline.model import Area, ParseResult, SourceFile
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
DOCLIB = "https://www.kedainiai.lt/lt/doclib/"
# The files the page links, by the id in their URL, and their copies in fixtures/kedainiai.
COPIES = {
    "ojtzogief2tn9wx8wngzc89ck2b6qpkh": "dotnuvos.docx",
    "6skc7sc0rmdmyafyjx86sgpfmvrv5vnp": "gudziunu.docx",
    "e3mqos8yc3qe397rrfrmeapphmv25anf": "josvainiu.pdf",
    "iaru4ocne4tzfxce5xnc759u63kbtxgb": "kedainiu-miesto.docx",
    "ebmzmnokrgy36326d8bq8j27p3a31c3e": "krakiu.docx",
    "e6zy36bw5mo3d9q6183rxytachg17wbk": "pelednagiu.docx",
    "tdsnaoinhgb8pxptau39pt5gr3vhmja1": "pernaravos.docx",
    "avt4wu4x7m1tzh25bz6g4hbzaf1pvb95": "surviliskio.docx",
    "61r4c5bfai3gr45qjqz6tcjpkp33q8wa": "setos.docx",
    "y54athaa6sqerj3ztqf3m3ewrcjjh3gb": "truskavos.docx",
    "qrrbefx5xg32c6svauujeae7rs3aeyk6": "vilainiu.docx",
}
REGISTRY = Registry.load(FIXTURES / "kedainiai" / "registry-kedainiu-r-2026-11-21.json")


def serve(url, timeout=0, user_agent=""):
    """The saved page and files, as kedainiai.http.get."""
    if url == kedainiai.PAGE_URL:
        return fixture("kedainiai/page.html")
    return fixture(f"kedainiai/{COPIES[url.removeprefix(DOCLIB)]}")


def parsed(copy, eldership, year=2026):
    file = SourceFile("household", f"{DOCLIB}x", f"{eldership} seniūnija ({year})", group=eldership)
    return kedainiai.parse_file(file, fixture(f"kedainiai/{copy}"))


def area(result, kind, start):
    """The row of a kind whose places start so."""
    return next(a for a in result.areas if a.kind == kind and a.name.startswith(start))


@pytest.fixture(scope="module")
def built():
    """The data as the daily job builds it from the page, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(kedainiai.http, "get", serve)
        files, warnings = kedainiai.download(TODAY, 366)
        data, more = build_dataset(files, REGISTRY, TODAY, 366, kedainiai.SOURCE)
    return files, data, warnings + more


def place(data, name, kind=None):
    return next(
        loc for loc in data["locations"] if loc["name"] == name and kind in (None, loc["type"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def dates(data, name, waste, kind=None):
    return row(data, place(data, name, kind)["schedule"][waste]["area"])["dates"]


# --- the page ----------------------------------------------------------------


def test_finds_a_file_for_each_eldership_under_the_years_heading():
    files = kedainiai.find_files(fixture("kedainiai/page.html").decode("utf-8"))
    assert {f.group for f, _ in files} == kedainiai.ELDERSHIPS
    assert {year for _, year in files} == {2026}
    for file, _ in files:
        # Not the menus' links to the elderships' own pages, nor the shared containers' files.
        assert file.url.removeprefix(DOCLIB) in COPIES
        assert file.file_name == f"{file.group} seniūnija (2026)"


def page(*sections, between=""):
    """A page with a heading and the links of each (year, elderships), and the site's menu,
    which links every eldership's page, above and below."""
    menu = "".join(
        f'<a href="/seniunijos/{i}">{e} seniūnija</a>'
        for i, e in enumerate(sorted(kedainiai.ELDERSHIPS))
    )
    body = "".join(
        f"<h4><strong>{year} M. ATLIEKŲ SURINKIMO GRAFIKAI:</strong></h4>"
        + "".join(
            f'<h6><a href="/lt/doclib/{year}{i}"><span>{e} seniūnija</span></a></h6>'
            for i, e in enumerate(elderships)
        )
        for year, elderships in sections
    )
    return f"<html><nav>{menu}</nav><main>{body}</main>{between}<footer>{menu}</footer></html>"


@pytest.mark.parametrize("between", ["", '<a href="#">Atgal</a>'])
def test_this_years_files_and_next_years_both(between):
    html = page(
        (2027, ["Dotnuvos", "Krakių"]), (2026, ["Krakių", "Dotnuvos", "Šėtos"]), between=between
    )
    files, warnings = kedainiai.select_files(kedainiai.find_files(html), date(2026, 12, 20))
    assert sorted(f.file_name for f in files) == [
        "Dotnuvos seniūnija (2026)",
        "Dotnuvos seniūnija (2027)",
        "Krakių seniūnija (2026)",
        "Krakių seniūnija (2027)",
        "Šėtos seniūnija (2026)",
    ]
    # An eldership missing from the list isn't taken from the menu below it.
    assert "no file for Vilainių sen. on the page" in warnings
    files, warnings = kedainiai.select_files(kedainiai.find_files(html), date(2027, 1, 5))
    assert sorted(f.file_name for f in files) == [
        "Dotnuvos seniūnija (2027)",
        "Krakių seniūnija (2027)",
        "Šėtos seniūnija (2026)",
    ]
    assert "no 2027 schedule for Šėtos sen. on the page" in warnings


def test_a_file_that_cant_be_downloaded(tmp_path, monkeypatch):
    def get(url, timeout=0, user_agent=""):
        if url.endswith("ojtzogief2tn9wx8wngzc89ck2b6qpkh"):
            raise OSError("HTTP Error 404: Not Found")
        return serve(url)

    monkeypatch.setattr(kedainiai.http, "get", serve)
    copy = tmp_path / "copy"
    kedainiai.save_copy(copy, TODAY)
    monkeypatch.setattr(kedainiai.http, "get", get)
    # The copy, if there is one, as for the page.
    monkeypatch.setattr(kedainiai, "COPY_DIR", copy)
    files, warnings = kedainiai.download(TODAY, 31)
    assert dict((f.group, c) for f, c in files)["Dotnuvos"] == fixture("kedainiai/dotnuvos.docx")
    assert warnings == [
        f"{kedainiai.PAGE_URL}: unavailable (HTTP Error 404: Not Found); used the copy from "
        "2026-11-21 (0 days old)"
    ]
    # Without one, the build fails (and yesterday's part is kept).
    monkeypatch.setattr(kedainiai, "COPY_DIR", tmp_path / "none")
    with pytest.raises(OSError, match="404"):
        kedainiai.download(TODAY, 31)


# --- the tables --------------------------------------------------------------


def test_routes_under_headings_across_the_table():
    result = parsed("dotnuvos.docx", "Dotnuvos")
    assert sorted((a.kind, a.weekday) for a in result.areas) == [
        ("glass", "Ketvirtadienis"),
        ("glass", "Trečiadienis"),
        ("household", "Ketvirtadienis"),
        ("household", "Trečiadienis"),
        ("packaging", "Ketvirtadienis"),
        ("packaging", "Trečiadienis"),
    ]
    mixed = area(result, "household", "Akademija, Aušra")
    # "(PIRMĄ MĖNESIO TREČIADIENĮ)" is taken off the places.
    assert mixed.name.endswith("Valinava, Valučiai, Žemaičių k.")
    assert mixed.district == "Dotnuvos"
    assert min(mixed.dates) == date(2026, 1, 7) and max(mixed.dates) == date(2026, 12, 2)
    assert len(mixed.dates) == 12
    assert result.warnings == []


def test_glass_days_are_the_packaging_days_in_red():
    result = parsed("dotnuvos.docx", "Dotnuvos")
    packaging = area(result, "packaging", "Akademija, Aušra")
    glass = area(result, "glass", "Akademija, Aušra")
    assert len(packaging.dates) == 12
    assert sorted(glass.dates) == [
        date(2026, 1, 14),
        date(2026, 4, 8),
        date(2026, 7, 8),
        date(2026, 10, 14),
    ]
    assert glass.dates < packaging.dates


def test_the_waste_type_in_a_column_and_places_merged_across_both():
    result = parsed("gudziunu.docx", "Gudžiūnų")
    mixed = area(result, "household", "Alksnėnai")
    packaging = area(result, "packaging", "Alksnėnai")
    assert mixed.name == packaging.name
    assert mixed.name.endswith("Vikaičiai, Žilvičiai")
    assert len(mixed.dates) == len(packaging.dates) == 12
    assert sorted(area(result, "glass", "Alksnėnai").dates)[0] == date(2026, 1, 12)


def test_the_town_and_its_villages():
    result = parsed("kedainiu-miesto.docx", "Kėdainių miesto")
    names = sorted(a.name[:16] for a in result.areas if a.kind == "household")
    assert names == [
        "Bartkūniškiai, B",
        "I KĖDAINIŲ M.: A",
        "II KĖDAINIŲ M.: ",
        "III KĖDAINIŲ M.:",
        "IV KĖDAINIŲ M.: ",
    ]
    # Every two weeks: 5, 19 January ... 7, 21 December.
    first = area(result, "household", "I KĖDAINIŲ")
    assert len(first.dates) == 26 and max(first.dates) == date(2026, 12, 21)
    assert first.name.endswith("Žalgirio g., Janušava")
    assert len(area(result, "glass", "Janušava, A. Būdvyčio").dates) == 4


def test_the_pdf_of_josvainiai():
    result = parsed("josvainiu.pdf", "Josvainių")
    sunday = area(result, "household", "Galulaukiai")
    assert sunday.name.startswith("Galulaukiai, Graužiai, Josvainiai, Karūnava")
    assert sunday.weekday == "Sekmadienis"
    assert min(sunday.dates) == date(2026, 1, 4) and max(sunday.dates) == date(2026, 12, 6)
    assert sorted(area(result, "glass", "Galulaukiai").dates) == [
        date(2026, 1, 11),
        date(2026, 4, 12),
        date(2026, 7, 12),
        date(2026, 10, 11),
    ]
    assert len([a for a in result.areas if a.kind == "household"]) == 2


@pytest.mark.parametrize(
    ("copy", "eldership", "routes"),
    [
        ("dotnuvos.docx", "Dotnuvos", (2, 2)),
        ("gudziunu.docx", "Gudžiūnų", (1, 1)),
        ("josvainiu.pdf", "Josvainių", (2, 2)),
        ("kedainiu-miesto.docx", "Kėdainių miesto", (5, 3)),
        ("krakiu.docx", "Krakių", (2, 2)),
        ("pelednagiu.docx", "Pelėdnagių", (3, 1)),
        ("pernaravos.docx", "Pernaravos", (1, 1)),
        ("surviliskio.docx", "Surviliškio", (1, 1)),
        ("setos.docx", "Šėtos", (2, 1)),
        ("truskavos.docx", "Truskavos", (1, 1)),
        ("vilainiu.docx", "Vilainių", (2, 1)),
    ],
)
def test_every_file(copy, eldership, routes):
    result = parsed(copy, eldership)
    count = {k: sum(1 for a in result.areas if a.kind == k) for k in ("household", "packaging")}
    assert (count["household"], count["packaging"]) == routes
    # Glass four times a year, on a packaging day of January, April, July and October.
    for glass in (a for a in result.areas if a.kind == "glass"):
        assert sorted(d.month for d in glass.dates) == [1, 4, 7, 10]
    # Each route says when it is driven ("TREČIĄ MĖNESIO SEKMADIENĮ", "KAS ANTRĄ
    # ANTRADIENĮ"), and its days agree.
    file = SourceFile("household", "x", f"{eldership} seniūnija (2026)", group=eldership)
    assert all(r.rule for r in kedainiai.read_routes(file, fixture(f"kedainiai/{copy}")))
    assert result.warnings == []


def test_the_title_must_be_of_the_links_eldership_and_year():
    with pytest.raises(ValueError, match="the title is of 'dotnuvos', not Krakių"):
        parsed("dotnuvos.docx", "Krakių")
    with pytest.raises(ValueError, match="the title says 2026, the page 2027"):
        parsed("dotnuvos.docx", "Dotnuvos", year=2027)


def run(text, color=None, hidden=False):
    properties = ""
    if color:
        properties += f'<w:color w:val="{color}"/>'
    if hidden:
        properties += "<w:vanish/>"
    return f'<w:r><w:rPr>{properties}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def cell(*runs, span=1):
    content = "".join(r if r.startswith("<w:r>") else run(r) for r in runs)
    grid = f'<w:tcPr><w:gridSpan w:val="{span}"/></w:tcPr>' if span > 1 else ""
    return f"<w:tc>{grid}<w:p>{content}</w:p></w:tc>"


MONTHS = (
    "Sausis Vasaris Kovas Balandis Gegužė Birželis Liepa Rugpjūtis Rugsėjis Spalis Lapkritis "
    "Gruodis"
).split()


def docx(*rows, title="2026 M. DOTNUVOS SENIŪNIJOS ATLIEKŲ SURINKIMO GRAFIKAI"):
    """A Word document with the table of an eldership's file: its title, the months, then
    `rows` (lists of cells)."""
    header = [cell("MARŠRUTAS")] + [cell(m) for m in MONTHS]
    table = [[cell(title, span=13)], header, *rows]
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:tbl>"
        + "".join(f"<w:tr>{''.join(r)}</w:tr>" for r in table)
        + "</w:tbl></w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


MIXED = [cell("SURENKAMOS MIŠRIOS KOMUNALINĖS ATLIEKOS", span=13)]
PACKAGING = [
    cell(
        "SURENKAMOS PAKUOČIŲ ATLIEKOS ",
        run(
            "(* RAUDONAI PAŽYMĖTOMIS DIENOMIS TUŠTINAMI IR STIKLO PAKUOČIŲ ATLIEKŲ KONTEINERIAI)",
            "FF0000",
        ),
        span=13,
    )
]


def route(places, *days):
    return [cell(run("(PIRMĄ MĖNESIO TREČIADIENĮ) ", "FF0000"), places)] + [
        cell(*d) if isinstance(d, tuple) else cell(d) for d in days
    ]


def parse(content):
    return kedainiai.parse_file(
        SourceFile("household", "x", "Dotnuvos seniūnija (2026)", group="Dotnuvos"), content
    )


def test_a_made_up_table():
    result = parse(
        docx(
            MIXED,
            route("Dotnuva, Aušra", "7", "4"),
            PACKAGING,
            route("Dotnuva", run("14", "C00000"), "11", ""),
        )
    )
    by_kind = {a.kind: a for a in result.areas}
    assert by_kind["household"].dates == {date(2026, 1, 7), date(2026, 2, 4)}
    assert by_kind["packaging"].dates == {date(2026, 1, 14), date(2026, 2, 11)}
    assert by_kind["glass"].dates == {date(2026, 1, 14)}
    assert by_kind["glass"].name == "Dotnuva"


def test_hidden_text_isnt_read():
    result = parse(docx(MIXED, route("Dotnuva", ("7", run("8", hidden=True)))))
    assert result.areas[0].dates == {date(2026, 1, 7)}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([MIXED, route("Dotnuva", run("7", "FF0000"))], "red days in a household row"),
        (
            [[cell("SURENKAMOS PAKUOČIŲ ATLIEKOS", span=13)], route("Dotnuva", run("7", "FF0000"))],
            "red days without the note",
        ),
        ([PACKAGING, route("Dotnuva", (run("1", "FF0000"), "4"))], "day 2026-01-14 is partly red"),
        ([MIXED, route("Dotnuva", "7 d.")], "not days: '7 d.'"),
        ([MIXED, route("Dotnuva", "7", "30")], "day 30 of 2026-02"),
        ([MIXED, route("", "7")], "dates without places"),
        ([MIXED, [cell("Dotnuva")]], "places without dates"),
        ([route("Dotnuva", "7")], "dates before the heading of a waste type"),
        ([[cell("SURENKAMOS KAŽKOKIOS ATLIEKOS", span=13)]], "a heading of no waste type"),
    ],
)
def test_anything_unexpected_fails(rows, message):
    with pytest.raises(ValueError, match=message):
        parse(docx(*rows))


def test_bulky_waste_and_the_notes_below_arent_read():
    result = parse(
        docx(
            MIXED,
            route("Dotnuva", "7"),
            [cell("SURENKAMOS DIDELIŲ GABARITŲ ATLIEKOS IŠ INDIVIDUALIŲ VALDŲ", span=13)],
            [cell("Dotnuva; Aušra", span=7), cell("Gegužės 20 d. ir spalio 7 d.", span=6)],
            [cell("1. Konteineriai turi būti pastatyti iki 7 val. ryto.", span=13)],
            # Another waste type's heading after them is read again.
            PACKAGING,
            route("Aušra", "14"),
        )
    )
    assert [(a.kind, a.name) for a in result.areas] == [
        ("household", "Dotnuva"),
        ("packaging", "Aušra"),
    ]


def test_days_other_than_the_heading_says_are_a_warning():
    # The first Wednesday of February 2026 is the 4th, not the 11th.
    result = parse(docx(MIXED, route("Dotnuva", "7", "11")))
    assert result.areas[0].dates == {date(2026, 1, 7), date(2026, 2, 11)}
    assert result.warnings == [
        "Dotnuvos seniūnija (2026) row 4: (PIRMĄ MĖNESIO TREČIADIENĮ), but 2026-02-11"
    ]


def test_neither_word_nor_pdf_fails():
    with pytest.raises(ValueError, match="neither a Word document nor a PDF"):
        parse(b"<html></html>")


# --- the places ----------------------------------------------------------------


def test_counts(built):
    files, data, warnings = built
    assert len(files) == 11
    stats = data["matching"]
    assert stats["locations"] == 478
    assert stats["household.single"] + stats["household.byStreet"] >= 300
    assert stats["household.single"] == 309
    assert stats["household.ambiguous"] == 2  # Akademija, Graužiai of Josvainių sen.
    assert stats["packaging.single"] == stats["glass.single"] == 287
    assert {a["kind"] for a in data["areas"]} == {"household", "packaging", "glass"}
    assert sorted(w.split(": ", 1)[1] for w in warnings if "household" in w) == [
        "household: Kėdainių m.: Pakrantės g.",
        "household: Kėdainių m.: Ryto g.",
        "household: Kėdainių m.: V. Montvilos g.",
        "household: Kėdainių miesto sen.: Klamputė",
        "household: Pernaravos sen.: Sauskojai",
    ]


@pytest.mark.parametrize(
    ("name", "kind", "waste", "count", "first", "last"),
    [
        ("Dotnuva", "mstl.", "household", 12, "2026-01-07", "2026-12-02"),
        ("Dotnuva", "mstl.", "glass", 4, "2026-01-14", "2026-10-14"),
        ("Krakės", "mstl.", "household", 12, "2026-01-21", "2026-12-16"),
        ("Krakės", "mstl.", "glass", 4, "2026-01-28", "2026-10-28"),
        # The PDF.
        ("Josvainiai", "mstl.", "household", 12, "2026-01-04", "2026-12-06"),
        ("Josvainiai", "mstl.", "glass", 4, "2026-01-11", "2026-10-11"),
        # Every second Tuesday.
        ("Vilainiai", "k.", "household", 26, "2026-01-13", "2026-12-29"),
        ("Daumantai", "k.", "household", 12, "2026-01-18", "2026-12-20"),
    ],
)
def test_a_village(built, name, kind, waste, count, first, last):
    _, data, _ = built
    found = dates(data, name, waste, kind)
    assert (len(found), found[0], found[-1]) == (count, first, last)


def test_a_town_and_a_village_of_one_name_both_get_the_route(built):
    _, data, _ = built
    for name in ("Gudžiūnai", "Krakės", "Pagiriai", "Josvainiai", "Surviliškis", "Pernarava"):
        town, village = (place(data, name, kind)["schedule"] for kind in ("mstl.", "k."))
        assert town == village, name


def test_akademijas_station_is_another_route(built):
    _, data, _ = built
    candidates = place(data, "Akademija")["schedule"]["household"]["candidates"]
    names = sorted(row(data, c)["name"][:40] for c in candidates)
    assert names[0].startswith("Akademija, Aušra")
    assert (
        "Akademija (Geležinkelio stotis)"
        in row(data, candidates[1])["name"] + row(data, candidates[0])["name"]
    )


def street(data, settlement, label, waste="household"):
    location = place(data, settlement)
    key = next(key for key, text in location["streets"] if text == label)
    return location["schedule"][waste]["streets"].get(key)


def test_the_towns_streets(built):
    _, data, _ = built
    first = street(data, "Kėdainiai", "Antano Būdvyčio g.")  # "A. Būdvyčio g."
    assert [row(data, i)["name"][:15] for i in first] == ["I KĖDAINIŲ M.: "]
    assert row(data, street(data, "Kėdainiai", "Ąžuolų skg.")[0])["name"].startswith("IV ")
    # "Rožių g." in route III and "Rožių," in IV: the app asks.
    assert len(street(data, "Kėdainiai", "Rožių g.")) == 2
    # Packaging: "Janušava, A. Būdvyčio g., ...": the town's street, not Janušava's.
    assert len(street(data, "Kėdainiai", "Gedimino g.", "packaging")) == 1
    assert "streets" not in place(data, "Janušava")["schedule"]["packaging"]
    # A street no route names is left to the app (apartment buildings, or a house left out).
    assert street(data, "Kėdainiai", "Chemikų g.") is None
    named = place(data, "Kėdainiai")["schedule"]["household"]["streets"]
    assert len(named) == 139 and all(named.values())


# --- this year and the next -----------------------------------------------------


def routes(year, *names, eldership="Dotnuvos"):
    return ParseResult(
        [
            Area(
                "household",
                name,
                district=eldership,
                dates={date(year, 1, 7 + i)},
                provider="kedainiai",
            )
            for i, name in enumerate(names)
        ]
    )


def test_next_year_continues_routes_of_the_same_places():
    municipality = dataclasses.replace(kedainiai.MUNICIPALITY, min_areas={})
    this_year = routes(2026, "Dotnuva, Aušra", "Beržai")
    next_year = routes(2027, "Aušra, Dotnuva", "Bokštai")
    file = SourceFile("household", "x", "x", group="Dotnuvos")
    warnings = kedainiai.tratc.combine(
        [(file, this_year), (file, next_year)], REGISTRY, date(2026, 12, 20), municipality
    )
    assert this_year.areas[0].dates == {date(2026, 1, 7), date(2027, 1, 7)}
    assert next_year.areas == []
    assert any("the 2027 route 'Bokštai'" in w for w in warnings)


# --- the folder ------------------------------------------------------------------


def test_the_folder_and_its_monitoring(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kedainiai.http, "get", serve)
    monkeypatch.setattr(kedainiai.address_register, "fetch", blocked)
    monkeypatch.setattr(kedainiai.address_points, "fetch", blocked)
    out = tmp_path / "kedainiu-r"
    assert kedainiai.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["kedainiai"]
    assert {a["provider"] for a in data["areas"]} == {"kedainiai"}
    assert (out / "addresses.json").exists()
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="kedainiai"} 317' in text
    assert regions.main(["--site", str(tmp_path)]) == 0
    index = json.loads((tmp_path / "regions.json").read_text(encoding="utf-8"))
    assert index["regions"] == [
        {
            "path": "kedainiu-r/",
            "kind": "settlements",
            "files": ["schedule.json", "addresses.json"],
            "providers": ["kedainiai"],
        }
    ]


def test_a_failed_build_keeps_the_published_part(built, tmp_path, monkeypatch):
    _, data, _ = built
    published = build.merge_parts(
        [(kedainiai.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-20"})],
        kedainiai.PAGE_URL,
    )

    def down(url, timeout=0, user_agent=""):
        raise OSError("HTTP Error 503: Service Unavailable")

    monkeypatch.setattr(kedainiai.http, "get", down)
    monkeypatch.setattr(kedainiai.address_register, "fetch", down)
    monkeypatch.setattr(kedainiai.address_points, "fetch", down)
    monkeypatch.setattr(kedainiai, "COPY_DIR", tmp_path / "no copy")
    monkeypatch.setattr(build, "load_published", lambda url: lambda: published)
    assert kedainiai.main(["--out", str(tmp_path)]) == 0
    kept = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert kept["providers"][0]["generatedAt"] == "2026-11-20"
    # Without published data to keep, the step fails and the workflow keeps yesterday's files.
    monkeypatch.setattr(build, "load_published", lambda url: lambda: {"providers": []})
    assert kedainiai.main(["--out", str(tmp_path / "none")]) == 1


def test_a_file_that_cant_be_read_keeps_its_elderships_rows(built, tmp_path, monkeypatch):
    _, data, _ = built
    published = build.merge_parts(
        [(kedainiai.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-20"})],
        kedainiai.PAGE_URL,
    )

    def get(url, timeout=0, user_agent=""):
        if url.endswith("ojtzogief2tn9wx8wngzc89ck2b6qpkh"):  # Dotnuvos sen.
            return b"<!DOCTYPE html><html></html>"
        return serve(url)

    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kedainiai.http, "get", get)
    monkeypatch.setattr(kedainiai.address_register, "fetch", blocked)
    monkeypatch.setattr(kedainiai.address_points, "fetch", blocked)
    monkeypatch.setattr(build, "load_published", lambda url: lambda: published)
    assert kedainiai.main(["--keep-days", "366", "--out", str(tmp_path)]) == 0
    result = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert result["providers"][0]["generatedAt"] > "2026-11-21"
    # The 9 of the files, and "Dotnuvos seniūnija (2026): can't be read (...); yesterday's 6
    # rows of Dotnuvos sen. are kept".
    assert result["providers"][0]["warnings"] == 10
    dotnuva = sorted(a["id"] for a in result["areas"] if a.get("district") == "Dotnuvos")
    assert dotnuva == sorted(a["id"] for a in data["areas"] if a.get("district") == "Dotnuvos")
    assert len(dotnuva) == 6
    assert place(result, "Dotnuva")["schedule"] == place(data, "Dotnuva")["schedule"]
    # --strict (the live check): the file fails the build.
    assert kedainiai.main(["--strict", "--out", str(tmp_path / "strict")]) == 1


def test_the_copy_when_the_site_refuses_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(kedainiai.http, "get", serve)
    copy = tmp_path / "copy"
    kedainiai.save_copy(copy, TODAY)
    # As ecoservice's: the page, the files named after their URLs, and copy.json.
    index = json.loads((copy / "copy.json").read_text(encoding="utf-8"))
    assert index["takenAt"] == "2026-11-21" and index["page"] == kedainiai.PAGE_URL
    assert sorted(index["files"]) == sorted(COPIES)
    assert sorted(p.name for p in copy.iterdir()) == sorted([*COPIES, "copy.json", "page.html"])

    def refused(url, timeout=0, user_agent=""):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kedainiai.http, "get", refused)
    monkeypatch.setattr(kedainiai, "COPY_DIR", copy)
    files, warnings = kedainiai.download(TODAY, 31)
    assert sorted(f.group for f, _ in files) == sorted(kedainiai.ELDERSHIPS)
    assert dict((f.group, c) for f, c in files)["Josvainių"] == fixture("kedainiai/josvainiu.pdf")
    assert warnings == [
        f"{kedainiai.PAGE_URL}: unavailable (HTTP Error 403: Forbidden); used the copy from "
        "2026-11-21 (0 days old)"
    ]
    # Months later it gives its age but asks for no refresh (snapshot.site_copy_note); in a new
    # year, it asks for its files.
    _, warnings = kedainiai.download(date(2027, 1, 25), 31)
    assert warnings[0].endswith("used the copy from 2026-11-21 (65 days old)")
    assert "no 2027 schedule for Dotnuvos sen. on the page" in warnings
    # Refreshed again with the same files, the copy is left as it is, its date too.
    monkeypatch.setattr(kedainiai.http, "get", serve)
    assert not kedainiai.save_copy(copy, date(2026, 11, 22))
    assert json.loads((copy / "copy.json").read_text(encoding="utf-8")) == index


def test_the_committed_copy_can_be_built(monkeypatch):
    """The copy in pipeline/data, as the daily job reads it on GitHub's runners (it is
    refreshed, so only that it builds: build_dataset checks the counts)."""

    def refused(url, timeout=0, user_agent=""):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(kedainiai.http, "get", refused)
    files, warnings = kedainiai.download(date.today(), 366)
    assert "used the copy from" in warnings[0]
    assert sorted(f.group for f, _ in files) == sorted(kedainiai.ELDERSHIPS)
    build_dataset(files, REGISTRY, date.today(), 366, kedainiai.SOURCE)

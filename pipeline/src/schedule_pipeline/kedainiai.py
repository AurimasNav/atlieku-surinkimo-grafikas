"""Kėdainių rajonas: the schedules of the individual houses of the municipality, published by
Kėdainių rajono savivaldybės administracija on its page of waste schedules. UAB „Ekonovus“
collects mixed waste, packaging and glass (named in the files). Kėdainiai town is mostly
apartment buildings with shared containers, whose schedules aren't read; the streets of its
private houses are in the files.

The page lists, under a heading with the year ("2026 M. ATLIEKŲ SURINKIMO GRAFIKAI:"), a link
per eldership ("Dotnuvos seniūnija", ..., "Kėdainių miesto seniūnija"), found by these texts
and the year of the heading. The links lead to the municipality's document library, whose URLs
say nothing: a Word document each, but the 2026 one of Josvainių sen. is a PDF of the same table
saved from Excel. Both are read. The other links (shared containers, bulky, hazardous and textile
waste, used oil) aren't.

Each file is one table, its title with the year and the eldership ("2026 M. DOTNUVOS SENIŪNIJOS
ATLIEKŲ SURINKIMO GRAFIKAI IŠ INDIVIDUALIŲ VALDŲ"), a row of months and a row per route under
the heading of its waste type:

    MARŠRUTAS                                      | Sausis | Vasaris | ... | Gruodis
    SURENKAMOS MIŠRIOS KOMUNALINĖS ATLIEKOS
    (PIRMĄ MĖNESIO TREČIADIENĮ) Akademija, Aušra,  | 7      | 4       | ... | 2
    SURENKAMOS PAKUOČIŲ ATLIEKOS (* RAUDONAI PAŽYMĖTOMIS DIENOMIS TUŠTINAMI IR STIKLO PAKUOČIŲ
    ATLIEKŲ KONTEINERIAI)
    (ANTRĄ MĖNESIO TREČIADIENĮ) Akademija, Aušra,  | 14     | 11      | ... | 9
    SURENKAMOS DIDELIŲ GABARITŲ ATLIEKOS ...       (bulky waste and notes: not read)

or with the waste type in a column of its own, next to the places ("Gudžiūnų seniūnija", a cell
of places merged across mixed waste and packaging). The glass containers are emptied on the
packaging days printed in red: there is no other mark, so the colour of the text is read (the
runs' colour in the Word files, the characters' fill colour in the PDF). Kėdainių miesto sen.
lists the streets of the town's private houses ("I KĖDAINIŲ M.: A. Būdvyčio g., ...") and its
villages. Strict: a cell of a month that isn't days, a day the month doesn't have, red days in
a mixed waste row or without the note that explains them, a day half red, places without dates
or dates without places, a title whose year or eldership isn't its link's raise ValueError.

The places are read by aratc.Routes, each row in its eldership's section. Streets of Kėdainiai
that no route names are left to the app: the shared containers' files aren't read, so nothing
says a street has none. Next year's files continue the routes of this year that cover the same
places (tratc.combine).

Writes <out>/schedule.json and <out>/addresses.json, in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.kedainiai --out ../site/kedainiu-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import date
from functools import partial
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin
from xml.etree import ElementTree

import pdfplumber

from . import addresses as address_points
from . import aratc, build, http, snapshot, tratc
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import _STREET_TYPE, Clause, Index, _section_parts
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Settlement, fold

PAGE_URL = "https://www.kedainiai.lt/gyventojui/atlieku-tvarkymas/atlieku-isvezimo-grafikai/1538"
# Yesterday's data, for a build that fails today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/kedainiu-r"
PUBLISHER = "Kėdainių rajono savivaldybės administracija"
# Every eldership of the municipality (register names); the page links a file for each.
ELDERSHIPS = frozenset(
    {
        "Dotnuvos",
        "Gudžiūnų",
        "Josvainių",
        "Kėdainių miesto",
        "Krakių",
        "Pelėdnagių",
        "Pernaravos",
        "Surviliškio",
        "Šėtos",
        "Truskavos",
        "Vilainių",
    }
)
# Mixed waste, packaging and glass in each file.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"household": ("household", "packaging", "glass")}


@dataclass(frozen=True)
class Municipality(tratc.Municipality):
    """What tratc.combine needs to know (tratc.Municipality), with the elderships as
    aratc.Routes reads them."""

    @property
    def elderships(self) -> frozenset[str]:
        return self.provider.elderships


# --- the places ------------------------------------------------------------------

# A route's number before the town's name: "I KĖDAINIŲ M.:", "IV KĖDAINIŲ M.:".
_ROUTE_NUMBER = re.compile(r"(?<![\w.])(?:I{1,3}|IV|VI{0,3}|IX|X)\s+(?=[A-ZĄČĘĖĮŠŲŪŽ]+\s+M\.)")
# The town's section in a row ("KĖDAINIŲ M.:", "Kėdainių m.").
_TOWN_MARK = r"\b{}\s+[Mm]\."


class Routes(aratc.Routes):
    """Reads the places of one row, as aratc.Routes does, in the section of the row's eldership
    (its `district`): "Akademija, Aušra, Ąžuolaičiai, Dotnuva, ..., Žemaičių k." in Dotnuvos
    sen. Kėdainių miesto sen. has the town's streets after its name ("I KĖDAINIŲ M.: A.
    Būdvyčio g., ..., Žalgirio g., Janušava") or after a village ("Janušava, A. Būdvyčio g.,
    ..."): those are the town's, which Janušava's streets of the same names (Gedimino g., ...)
    aren't.

    No street of the town gets "no pickup" when no route names it (build_locations): the files
    list the streets of private houses, and those of apartment buildings are in the shared
    containers' files, which aren't read. The app offers the town's routes instead."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()
        mine = self.places[MUNICIPALITY.label]
        # The town of each eldership that has one: Kėdainių miesto sen.'s Kėdainiai.
        self.towns = {s.district: s for s in mine if s.abbr == "m."}

    def spellings(self, text: str) -> str:
        return _ROUTE_NUMBER.sub("", text)

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        """The row read in the section of its eldership; the id stays the row's."""
        text = area.name
        town = self.towns.get(area.district or "")
        if town and not re.search(_TOWN_MARK.format(re.escape(town.genitive)), text, re.I):
            # Streets without the town's name before them are the town's.
            parts = _section_parts(text)
            first = next(
                (i for i, part in enumerate(parts) if _STREET_TYPE.search(f" {fold(part)} ")),
                None,
            )
            if first is not None:
                parts[first] = f"{town.genitive} m.: {parts[first]}"
                text = ", ".join(parts)
        row = SimpleNamespace(
            id=area.id,
            kind=area.kind,
            name=f"{area.district} sen.: {text}",
            district=MUNICIPALITY.label,
        )
        return super().clauses(row)


PROVIDER = Provider(
    id="kedainiai",
    name=PUBLISHER,
    url=PAGE_URL,
    elderships=ELDERSHIPS,
    kinds=("household", "packaging", "glass"),
    reader=Routes,
)
MUNICIPALITY = Municipality(
    PROVIDER,
    snapshot.KEDAINIAI_MUNICIPALITY,
    snapshot.KEDAINIAI_REGISTRY_FILE,
    snapshot.KEDAINIAI_ADDRESSES_FILE,
    # 2026: 22 mixed waste and 16 packaging routes, each with glass, which gave a mixed waste
    # schedule to 312 of the 478 settlements (21,262 of the 21,414 addresses). Far fewer means
    # the format changed and the parser or the matching missed rows.
    min_areas={"household": 17, "packaging": 12, "glass": 12},
    min_household_places=250,
    # About 21,400 addresses in 2026.
    min_address_points=15_000,
    label="Kėdainių r.",
    file_kinds=FILE_KINDS,
)


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    """The links of the page with their texts, and the year of the heading above each ("2026
    M. ATLIEKŲ SURINKIMO GRAFIKAI:")."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, int | None]] = []
        self.open: list[tuple[str | None, list[str]]] = []
        self.year: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.open.append((dict(attrs).get("href"), []))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.open:
            href, text = self.open.pop()
            if href:
                self.links.append((href, clean_text("".join(text)), self.year))

    def handle_data(self, data: str) -> None:
        if self.open:
            self.open[-1][1].append(data)
        elif match := re.search(r"(?<!\d)(20\d{2})\s*m\.?\s+atliek\w*\s+surinkimo", data, re.I):
            self.year = int(match.group(1))


def eldership_of(text: str) -> str | None:
    """The eldership a link's text names: "Dotnuvos seniūnija", "• Kėdainių miesto
    seniūnija"."""
    match = re.fullmatch(r"(?:\W*\s*)?(.+?)\s+seniunija", fold(text))
    if not match:
        return None
    return next((e for e in sorted(ELDERSHIPS) if fold(e) == match.group(1)), None)


def find_files(html: str, page_url: str = PAGE_URL) -> list[tuple[SourceFile, int]]:
    """The elderships' files the page links, by the texts of the links, with the year of the
    heading above each. The site's menus link the elderships' own pages with the same texts,
    above the heading and below the list: a heading's list ends at the first other link after
    it ("Kėdainių rajono gyventojų buityje susidarančių pavojingų atliekų ...") or where an
    eldership comes again."""
    collector = _Links()
    collector.feed(html)
    files: list[tuple[SourceFile, int]] = []
    heading: int | None = None  # the year of the heading above the link
    seen: set[str] = set()  # the elderships of its list
    ended = False  # its list has ended
    for href, text, year in collector.links:
        if year != heading:
            heading, seen, ended = year, set(), False
        if year is None or ended:
            continue  # the menu above the first heading, or below the list
        eldership = eldership_of(text)
        if seen and (eldership in seen or (eldership is None and text)):
            ended = True
            continue
        if eldership is None:
            continue
        seen.add(eldership)
        url = urljoin(page_url, href)
        # The URLs say nothing ("/lt/doclib/ojtzog..."): the link's text and year name the file.
        name = f"{clean_text(text.strip('•'))} ({year})"
        files.append((SourceFile("household", url, name, group=eldership), year))
    return files


def select_files(
    files: list[tuple[SourceFile, int]], today: date
) -> tuple[list[SourceFile], list[str]]:
    """Per eldership, the files of this year and later; if there are none, the newest one."""
    selected: list[SourceFile] = []
    warnings: list[str] = []
    for eldership in sorted(ELDERSHIPS):
        mine = [(f, y) for f, y in files if f.group == eldership]
        if not mine:
            warnings.append(f"no file for {eldership} sen. on the page")
            continue
        running = [f for f, y in mine if y >= today.year]
        if today.year not in {y for _, y in mine}:
            warnings.append(f"no {today.year} schedule for {eldership} sen. on the page")
        if not running:
            newest = max(y for _, y in mine)
            running = [f for f, y in mine if y == newest]
        selected += running
    return selected, warnings


def _get(url: str) -> bytes:
    # With the project's own user agent (http.USER_AGENT). kedainiai.lt answers GitHub's
    # runners 403 whatever the user agent; it serves a machine in Lithuania.
    return http.get(url, timeout=60)


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = _get(PAGE_URL).decode("utf-8", errors="replace")
    files, warnings = select_files(find_files(html), today)
    downloaded: list[tuple[SourceFile, bytes]] = []
    for file in files:
        content = _get(file.url)
        if content.startswith((b"PK", b"%PDF")):
            downloaded.append((file, content))
        else:
            # A page of the site, not a document: the list has changed.
            warnings.append(f"{file.file_name}: {file.url} is neither a Word document nor a PDF")
    return downloaded, warnings


# --- the tables ------------------------------------------------------------------


@dataclass
class _Cell:
    """A cell of a table: the columns it spans ([start, end): grid columns of a Word table,
    points across a PDF page), its text and which of its characters are red."""

    start: float
    end: float
    text: str
    red: list[bool]
    # Merged with the cell above it, whose text it repeats.
    continued: bool = False


def _red_hex(value: str | None) -> bool:
    if not value or not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        return False
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return r >= 0x99 and g <= 0x66 and b <= 0x66


def _red_fill(color: object) -> bool:
    """A PDF fill colour that is red: RGB (1, 0, 0) or CMYK (0, 1, 1, 0), or close."""
    if not isinstance(color, tuple | list):
        return False
    values = [float(v) for v in color]
    if len(values) == 3:
        r, g, b = values
        return r >= 0.6 and g <= 0.4 and b <= 0.4
    if len(values) == 4:
        c, m, y, k = values
        return c <= 0.4 and m >= 0.6 and y >= 0.6 and k <= 0.4
    return False


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _on(element: ElementTree.Element | None) -> bool:
    """A toggle property of a run (<w:vanish/>, <w:vanish w:val="0"/>)."""
    return element is not None and element.get(f"{_W}val") not in ("0", "false", "off")


class _Styles:
    """The colour and hiding of text that the styles of a Word document give."""

    def __init__(self, xml: bytes | None):
        self.styles: dict[str, ElementTree.Element] = {}
        if xml:
            for style in ElementTree.fromstring(xml).iter(f"{_W}style"):
                self.styles[style.get(f"{_W}styleId") or ""] = style

    def property(self, style_id: str | None, name: str) -> ElementTree.Element | None:
        seen: set[str] = set()
        while style_id and style_id not in seen:
            seen.add(style_id)
            style = self.styles.get(style_id)
            if style is None:
                return None
            found = style.find(f"{_W}rPr/{_W}{name}")
            if found is not None:
                return found
            based = style.find(f"{_W}basedOn")
            style_id = based.get(f"{_W}val") if based is not None else None
        return None


def _run_property(
    run: ElementTree.Element, paragraph_style: str | None, styles: _Styles, name: str
) -> ElementTree.Element | None:
    """A property of a run: its own, its style's, or its paragraph style's."""
    properties = run.find(f"{_W}rPr")
    if properties is not None:
        own = properties.find(f"{_W}{name}")
        if own is not None:
            return own
        style = properties.find(f"{_W}rStyle")
        if style is not None and (found := styles.property(style.get(f"{_W}val"), name)):
            return found
    return styles.property(paragraph_style, name)


def _docx_cell_text(cell: ElementTree.Element, styles: _Styles) -> tuple[str, list[bool]]:
    """The text of a cell of a Word table and which characters are red. Hidden text isn't
    read; paragraphs are joined with spaces."""
    text: list[str] = []
    red: list[bool] = []
    for paragraph in cell.iter(f"{_W}p"):
        if text:
            text.append(" ")
            red.append(False)
        style = paragraph.find(f"{_W}pPr/{_W}pStyle")
        paragraph_style = style.get(f"{_W}val") if style is not None else None
        for run in paragraph.iter(f"{_W}r"):
            if _on(_run_property(run, paragraph_style, styles, "vanish")):
                continue
            color = _run_property(run, paragraph_style, styles, "color")
            is_red = _red_hex(color.get(f"{_W}val") if color is not None else None)
            for part in run:
                if part.tag == f"{_W}t":
                    value = part.text or ""
                elif part.tag in (f"{_W}tab", f"{_W}br", f"{_W}cr"):
                    value = " "
                else:
                    continue
                text.append(value)
                red += [is_red] * len(value)
    return "".join(text), red


def _docx_rows(content: bytes) -> list[list[_Cell]]:
    """The rows of the tables of a Word document, in order. A cell merged with the one above it
    repeats that one's text (`continued`)."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
        names = set(archive.namelist())
        styles = _Styles(archive.read("word/styles.xml") if "word/styles.xml" in names else None)
    rows: list[list[_Cell]] = []
    for table in document.findall(f"{_W}body/{_W}tbl"):
        above: dict[int, _Cell] = {}  # the last cell starting at each column
        for tr in table.findall(f"{_W}tr"):
            before = tr.find(f"{_W}trPr/{_W}gridBefore")
            column = int(before.get(f"{_W}val") or 0) if before is not None else 0
            row: list[_Cell] = []
            for tc in tr.findall(f"{_W}tc"):
                span_element = tc.find(f"{_W}tcPr/{_W}gridSpan")
                span = int(span_element.get(f"{_W}val") or 1) if span_element is not None else 1
                merge = tc.find(f"{_W}tcPr/{_W}vMerge")
                text, red = _docx_cell_text(tc, styles)
                if merge is not None and merge.get(f"{_W}val") in (None, "continue"):
                    top = above.get(column)
                    if top is None:
                        raise ValueError(f"a merged cell at column {column} with nothing above")
                    cell = _Cell(column, column + span, top.text, top.red, continued=True)
                else:
                    cell = _Cell(column, column + span, text, red)
                above[column] = cell
                row.append(cell)
                column += span
            rows.append(row)
    return rows


def _pdf_rows(content: bytes) -> list[list[_Cell]]:
    """The rows of the tables of a PDF, as pdfplumber's table finder sees them. A cell that
    spans several rows is in each of them, `continued` in all but the first."""
    rows: list[list[_Cell]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.find_tables():
                for table_row in table.rows:
                    _, top, _, bottom = table_row.bbox
                    middle = (top + bottom) / 2
                    cells = sorted(
                        (c for c in table.cells if c[1] <= middle <= c[3]), key=lambda c: c[0]
                    )
                    row: list[_Cell] = []
                    for bbox in cells:
                        text, red = _pdf_cell_text(page, bbox)
                        row.append(_Cell(bbox[0], bbox[2], text, red, bbox[1] < top - 1))
                    rows.append(row)
    return rows


def _pdf_cell_text(page, bbox: tuple[float, float, float, float]) -> tuple[str, list[bool]]:
    """The words whose letters are in the cell, with the red ones."""
    x0, top, x1, bottom = bbox

    def inside(obj: dict) -> bool:
        if obj.get("object_type") != "char":
            return False
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return x0 <= x <= x1 and top <= y <= bottom

    words = page.filter(inside).extract_words(extra_attrs=["non_stroking_color"])
    text: list[str] = []
    red: list[bool] = []
    for word in words:
        if text:
            text.append(" ")
            red.append(False)
        text.append(word["text"])
        red += [_red_fill(word["non_stroking_color"])] * len(word["text"])
    return "".join(text), red


_TITLE = re.compile(r"\b(20\d{2}) m (.+?) seniunijos atlieku surinkimo grafik")
# "(PIRMĄ MĖNESIO TREČIADIENĮ)", "(TREČIA MĖNESIO SEKMADIENĮ)", "(KAS ANTRĄ ANTRADIENĮ)",
# folded (without the brackets): when the route is driven.
_RULE = re.compile(
    r"\b(?:(?P<every>kas antra)|(?P<nth>pirma|antra|trecia|ketvirta|penkta) menesio) "
    r"(?P<day>\w+dieni)\b"
)
_ORDINALS = {"pirma": 1, "antra": 2, "trecia": 3, "ketvirta": 4, "penkta": 5}
_WEEKDAYS = {"pirm": 0, "antr": 1, "trec": 2, "ketv": 3, "penk": 4, "sest": 5, "sekm": 6}
# The same in the text as written, to take it off the places.
_RULE_TEXT = re.compile(r"\(\s*(?:kas\s+)?\w+\s+(?:mėnesio\s+)?\w+dienį\s*\)", re.I)
_DAYS = re.compile(r"\d{1,2}(?:\s*[,;]\s*\d{1,2})*")
# The heading of a waste type (folded): "SURENKAMOS MIŠRIOS KOMUNALINĖS ATLIEKOS", "...
# PAKUOČIŲ ATLIEKOS (* RAUDONAI PAŽYMĖTOMIS DIENOMIS TUŠTINAMI IR STIKLO PAKUOČIŲ ...)", "(PIRMĄ
# MĖNESIO PIRMADIENĮ) SURENKAMOS ..."; not the notes ("... bus surenkamos kito aptarnavimo
# metu").
_HEADING = re.compile(r"^(?:(?:kas antra|\w+ menesio) \w+dieni )?surenkamos\b")
BULKY = "bulky"


def _heading_kind(folded: str) -> str | None:
    """The waste type of a heading: mixed waste, packaging (with glass on the red days), or
    bulky waste, whose rows aren't read."""
    if "gabarit" in folded:
        return BULKY
    if "pakuo" in folded:
        return "packaging"
    if "misri" in folded or "komunal" in folded:
        return "household"
    return None


def _glass_note(folded: str) -> bool:
    return "raudonai" in folded and "stikl" in folded


@dataclass
class _Route:
    kind: Kind
    places: str
    # When it is driven, as the row says ("(PIRMĄ MĖNESIO TREČIADIENĮ)"), and read (_RULE).
    written: str
    rule: re.Match[str] | None
    dates: set[date]
    red: set[date]
    where: str


def _months(row: list[_Cell], where: str) -> list[tuple[float, float, int]] | None:
    """The columns of the months, if the row is the months' ("MARŠRUTAS | Sausis | ...")."""
    found = [
        (c.start, c.end, aratc.MONTHS[fold(c.text)]) for c in row if fold(c.text) in aratc.MONTHS
    ]
    if len(found) < 6:
        return None
    if [m for _, _, m in found] != list(range(1, 13)):
        raise ValueError(f"{where}: months {[m for _, _, m in found]}, not January to December")
    return found


def _day_cell(cell: _Cell, month: date, where: str) -> tuple[set[date], set[date]]:
    """The days of a month's cell, and those of them printed in red."""
    text = cell.text.strip()
    if not text:
        return set(), set()
    if not _DAYS.fullmatch(text):
        raise ValueError(f"{where}: not days: {text!r}")
    dates: set[date] = set()
    red: set[date] = set()
    for match in re.finditer(r"\d+", cell.text):
        try:
            day = month.replace(day=int(match.group()))
        except ValueError as error:
            raise ValueError(f"{where}: day {match.group()} of {month:%Y-%m}: {error}") from error
        colours = set(cell.red[match.start() : match.end()])
        if len(colours) > 1:
            raise ValueError(f"{where}: day {day} is partly red")
        dates.add(day)
        if colours == {True}:
            red.add(day)
    return dates, red


def _routes(source: SourceFile, rows: list[list[_Cell]], slack: float = 0) -> list[_Route]:
    """The routes of a file's table. Strict: see the module's docstring. `slack`: how far a
    cell's edge may be from its column's (PDF points; none in a Word table's grid)."""
    year: int | None = None
    months: list[tuple[float, float, int]] | None = None
    section: str | None = None  # the waste type of the rows under the last heading
    note = False  # the note that red days are glass days
    routes: list[_Route] = []
    for number, row in enumerate(rows, start=1):
        where = f"{source.file_name} row {number}"
        cells = [c for c in row if c.text.strip()]
        if not cells or all(c.continued for c in cells):
            continue  # empty, or the rest of cells merged with the row above
        folded = fold(" ".join(c.text for c in cells))
        if year is None:
            title = _TITLE.search(folded)
            if title:
                year = int(title.group(1))
                if title.group(2) != fold(source.group):
                    raise ValueError(
                        f"{where}: the title is of {title.group(2)!r}, not {source.group}"
                    )
                expected = tratc.file_year(source.file_name)
                if expected and year != expected:
                    raise ValueError(f"{where}: the title says {year}, the page {expected}")
            continue
        found = _months(cells, where)
        if found:
            months = found
            continue
        headings = [c for c in cells if _HEADING.search(fold(c.text))]
        for heading in headings:
            kind = _heading_kind(fold(heading.text))
            if kind is None:
                raise ValueError(f"{where}: a heading of no waste type we know: {heading.text!r}")
            section = kind
            note = note or _glass_note(fold(heading.text))
        if section == BULKY:
            continue  # bulky waste and the notes below, until another waste type's heading
        if months is None:
            if headings:
                continue
            raise ValueError(f"{where}: {folded[:60]!r} before the row of months")
        first = months[0][0]
        labels = [c for c in cells if c.end <= first + slack]
        days = [c for c in cells if c.start >= first - slack]
        wide = [c for c in cells if c not in labels and c not in days]
        if wide and not headings:
            raise ValueError(f"{where}: text across the months: {wide[0].text[:60]!r}")
        if not days:
            if [c for c in labels if c not in headings and not c.continued]:
                raise ValueError(f"{where}: places without dates: {labels[0].text[:60]!r}")
            continue
        if section is None:
            raise ValueError(f"{where}: dates before the heading of a waste type")
        text = " ".join(c.text for c in labels if c not in headings)
        # When it is driven: before the places, or in the waste type's cell next to them.
        written = next((m.group() for c in labels if (m := _RULE_TEXT.search(c.text))), "")
        places = clean_text(_RULE_TEXT.sub("", text)).strip(" ,;")
        if not places:
            raise ValueError(f"{where}: dates without places")
        dates: set[date] = set()
        red: set[date] = set()
        for cell in days:
            month = next(
                (
                    m
                    for start, end, m in months
                    if start - slack <= cell.start and cell.end <= end + slack
                ),
                None,
            )
            if month is None or year is None:
                raise ValueError(f"{where}: {cell.text!r} isn't in a month's column")
            more, more_red = _day_cell(cell, date(year, month, 1), where)
            dates |= more
            red |= more_red
        if not dates:
            raise ValueError(f"{where}: places without dates: {places[:60]!r}")
        if red and section != "packaging":
            raise ValueError(f"{where}: red days in a {section} row")
        if red and not note:
            raise ValueError(f"{where}: red days without the note that they are glass days")
        rule = _RULE.search(fold(written))
        routes.append(_Route(section, places, clean_text(written), rule, dates, red, where))
    if year is None:
        raise ValueError(f"{source.file_name}: no title with the year and the eldership")
    if not routes:
        raise ValueError(f"{source.file_name}: no schedule table found")
    return routes


def _rule_warnings(route: _Route) -> list[str]:
    """Days that aren't the ones the route's heading says ("PIRMĄ MĖNESIO TREČIADIENĮ"): the
    table's days are read, but a mistake in either is worth a look."""
    rule = route.rule
    if rule is None:
        return [f"{route.where}: no weekday we know: {route.written!r}"] if route.written else []
    weekday = next((d for word, d in _WEEKDAYS.items() if rule["day"].startswith(word)), None)
    if weekday is None:
        return [f"{route.where}: no weekday we know: {route.written!r}"]
    wrong = sorted(d for d in route.dates if d.weekday() != weekday)
    if rule["nth"]:
        nth = _ORDINALS[rule["nth"]]
        wrong += sorted(d for d in route.dates if (d.day - 1) // 7 + 1 != nth and d not in wrong)
    else:
        ordered = sorted(route.dates)
        pairs = zip(ordered, ordered[1:], strict=False)
        wrong += [b for a, b in pairs if (b - a).days != 14 and b not in wrong]
    if not wrong:
        return []
    days = ", ".join(d.isoformat() for d in wrong[:4])
    return [f"{route.where}: {route.written}, but {days}"]


def read_routes(source: SourceFile, content: bytes) -> list[_Route]:
    """The routes of an eldership's file, a Word document or a PDF."""
    if content.startswith(b"PK"):
        return _routes(source, _docx_rows(content))
    if content.startswith(b"%PDF"):
        return _routes(source, _pdf_rows(content), slack=2.0)
    raise ValueError(f"{source.file_name}: neither a Word document nor a PDF")


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The mixed waste, packaging and glass schedules of an eldership's file."""
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for route in read_routes(source, content):
        warnings += _rule_warnings(route)
        kinds: list[tuple[Kind, set[date]]] = [(route.kind, route.dates)]
        if route.kind == "packaging":
            if not route.red:
                warnings.append(f"{route.where}: no red days, so no glass: {route.places[:60]!r}")
            kinds.append(("glass", route.red))
        for kind, dates in kinds:
            if not dates:
                continue
            area = Area(
                kind=kind,
                name=route.places,
                district=source.group,
                dates=set(dates),
                provider=PROVIDER.id,
            )
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{route.where}: {kind} of {route.places[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    return ParseResult(areas=list(areas.values()), warnings=warnings)


# --- the source and the output ------------------------------------------------------

SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MUNICIPALITY.min_areas,
    MUNICIPALITY.min_household_places,
    FILE_KINDS,
    partial(tratc.combine, municipality=MUNICIPALITY),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    parser.add_argument(
        "--published",
        default=PUBLISHED_URL,
        help="site folder with yesterday's schedule.json, for a build that fails",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if the build fails instead of keeping the published data",
    )
    args = parser.parse_args(argv)

    name, code = MUNICIPALITY.register
    registry, registry_note = build.live_or_snapshot(
        "Address Register",
        partial(address_register.fetch, name),
        partial(snapshot.load_registry, MUNICIPALITY.registry_file),
    )
    points, points_note = build.live_or_snapshot(
        "Address points",
        partial(address_points.fetch, code),
        partial(snapshot.load_points, MUNICIPALITY.addresses_file),
    )
    loader = None if args.strict else build.load_published(args.published)
    try:
        results = build.build_parts((SOURCE,), registry, date.today(), args.keep_days, loader)
        if not results[0].part:
            raise build.ValidationError(f"{results[0].error}; no published data to keep")
        dataset = build.merge_parts([(r.provider, r.part) for r in results if r.part], PAGE_URL)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < MUNICIPALITY.min_address_points:
            raise build.ValidationError(f"only {len(addresses['points'])} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    for r in results:
        if r.error:
            kept = f"the data published on {r.part['generatedAt'][:10]} is kept" if r.part else ""
            # An annotation on the workflow run.
            print(f"::warning::The {MUNICIPALITY.label} build failed; {kept}. {r.error}")

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    notes = [n for n in (registry_note, points_note) if n]
    title = f"{MUNICIPALITY.label} ({PUBLISHER})"
    build.write_summary(dataset, results, notes, title, f"{args.out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

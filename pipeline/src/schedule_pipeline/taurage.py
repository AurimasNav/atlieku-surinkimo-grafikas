"""Tauragė county: schedules published by its regional waste centre, UAB „Tauragės regiono
atliekų tvarkymo centras“, for Jurbarko r., Tauragės r., Šilalės r. and Pagėgių sav. Mixed and
green waste are collected by UAB „Ecoservice“, packaging and glass by UAB „Jurbarko
komunalininkas“ in Jurbarko r. and UAB „Dunokai“ in Tauragės r. and Šilalės r. (named in the
files).

Its page lists the schedules of the four municipalities, PDFs titled by municipality and waste
type, under a heading with the year; the year is also in the files' names and titles ("...
GRAFIKAS 2026 M."). Each municipality is a `Municipality` in MUNICIPALITIES.

Jurbarko r. has two files a year, found by the texts of their links:

    Jurbarko miesto ir rajono mišrių, maisto ir žaliųjų atliekų grafikas   mixed and green waste
    Jurbarko miesto ir rajono pakuočių grafikas                            packaging and glass

The mixed waste file has a table per route, which can run on to the next page:

    ANTRADIENIS | Mišrios komunalinės (likusios po rūšiavimo) atliekos
                | Sausis | Vasaris | Kovas     | ...
                | 6, 20  | 3, 17   | 3, 17, 31 | ...
                | Šimkaičių sen.: Šimkaičių mstl., ... Skirsnemunės sen.: Šilinės k., ...

and the packaging file one with a row of dates per waste type:

    Mėnuo                       | Sausis | Vasaris | ...
    PLASTIKAS POPIERIUS METALAS | 14     | 12      | ...
    STIKLAS (Mėnesio diena)     | 22     |         | ...
    Seniūnijų kaimų ir ...      | JURBARKO MIESTO SENIŪNIJA: Jurbarko miestas JURBARKŲ ...

The tables are read from the positions of the words: pdfplumber's table finder misses a
table's part on the next page and the end of text that runs past a cell's border. Text the
file clips away isn't read: page 1 of the 2026 mixed waste file hides a table of another
municipality ("MARIJAMPOLĖS SENIŪNIJA") under its notice. The shared containers of apartment
buildings have weekdays, not dates, and aren't read.

A route lists elderships' settlements and streets of Jurbarkas; locations.SectionRoutes links
them to the Address Register. Next year's files appear in December: a route of next year that
covers the same places as one of this year continues it (combine).

The other three put a route's places above its dates (parse_places_first):

    Tauragės rajono mišrių atliekų grafikas          mixed waste of the villages: "1.Maršrutas.
                                                     Žygaičių seniūnija. Aukštupių k., ...",
                                                     then the months in two rows of six
    Tauragės miesto mišrių atliekų grafikas          mixed waste of the town, and of villages
                                                     next to it: "Senamiestis I. Aušros g.,
                                                     ... Taurai. Alėjos g., ..."
    Tauragės miesto maisto ir žaliųjų ... grafikas   food and green waste (one container) of
                                                     the town, laid out the same
    Tauragės miesto ir rajono pakuočių grafikas      packaging and glass: "(1) Tauragės m.
                                                     Islandijos g., ...", a row of dates each
    Šilalės rajono mišrių, maisto ir žaliųjų ...     mixed waste, green waste for the town:
                                                     "Laukuvos sen: Baltkalnio k., ..."
    Šilalės rajono pakuočių grafikas                 packaging and glass
    Pagėgių savivaldybės mišrių/biologinių/pakuočių  everything in one file
    atliekų grafikas

Their rows are read by Routes. Streets of the towns that no route names are left to the app,
which offers the town's routes: none of the files lists every street of private houses.

The four municipalities are written to one <out>/schedule.json and <out>/addresses.json, in
the format of the Vilniaus r. files, a part (model.Provider) each, as tratc does: the app
downloads one file for the region, and a municipality whose build fails keeps its part of
yesterday's file.
Run: python -m schedule_pipeline.taurage --out ../site/jurbarko-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import cache, partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTChar
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.utils import apply_matrix_pt

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import (
    _HOUSE,
    _SECTION_ITEM,
    _SETTLEMENT_TYPES,
    _SPELLINGS,
    _STREET_TYPES,
    _UPPER,
    _WORD,
    Clause,
    Index,
    SectionRoutes,
    _one_off,
    _section_parts,
    _Stop,
    _street_type,
    street_key,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold
from .tratc import _once

PAGE_URL = "https://www.uabtratc.lt/atlieku-surinkimo-grafikai/"
# Yesterday's data, for the part of a municipality whose build fails today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/jurbarko-r"
COMPANY = "UAB „Tauragės regiono atliekų tvarkymo centras“"
# The waste types in the texts of the links (folded), and the schedules a file of each has:
# the first word a link's text has gives its kind ("mišrių, maisto ir žaliųjų" is mixed waste).
LINK_KINDS: tuple[tuple[str, Kind], ...] = (("pakuo", "packaging"), ("misri", "household"))
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "green"),
    "packaging": ("packaging", "glass"),
}
# Bulky waste and the like are collected by appointment or once or twice a year: not read.
NOT_SCHEDULES = ("gabarit", "apvaziav", "pavoj")


@dataclass(frozen=True, eq=False)
class Municipality:
    """A municipality on the page: which links are its schedules, and whom they serve."""

    provider: Provider
    link_word: str  # in the texts of its links, folded
    register: tuple[str, int]  # the Address Register's name and code
    registry_file: Path
    addresses_file: Path
    min_areas: dict[Kind, int]
    min_household_places: int
    min_address_points: int
    folder: str  # of the site
    title: str  # of the job summary
    label: str = ""  # of its notes in the job summary
    link_kinds: tuple[tuple[str, Kind], ...] = LINK_KINDS
    file_kinds: dict[Kind, tuple[Kind, ...]] = field(default_factory=lambda: FILE_KINDS)
    # The tables have their places above the dates (parse_places_first), not below.
    places_first: bool = False
    # Routes a next year's file of the town or of the villages (SourceFile.group) must have, of
    # each kind, where the two have files of their own.
    min_group_areas: dict[tuple[Kind, str], int] = field(default_factory=dict)


JURBARKAS = Municipality(
    provider=Provider(
        id="jurbarkas",
        name=COMPANY,
        url=PAGE_URL,
        # Every eldership of the municipality (register names).
        elderships=frozenset(
            {
                "Eržvilko",
                "Girdžių",
                "Juodaičių",
                "Jurbarko miesto",
                "Jurbarkų",
                "Raudonės",
                "Seredžiaus",
                "Skirsnemunės",
                "Smalininkų",
                "Šimkaičių",
                "Veliuonos",
                "Viešvilės",
            }
        ),
        section_town="Jurbarkas",
        # Skirsnemunės sen. has two villages called Naukaimis, I and II; the routes tell them
        # apart by a place nearby. Naukaimis I is 2 km from Skirsnemunė, Naukaimis II 3 km from
        # Pilis I and II, where Vytėnų g. is (centres of their addresses, 2026).
        aliases=(
            ("Naukaimio k. (Skirsnemunė)", "Naukaimio I k."),
            ("Naukaimio k. (Vytėnų)", "Naukaimio II k."),
        ),
        kinds=("household", "packaging", "glass", "green"),
    ),
    link_word="jurbark",
    register=snapshot.JURBARKO_MUNICIPALITY,
    registry_file=snapshot.JURBARKO_REGISTRY_FILE,
    addresses_file=snapshot.JURBARKO_ADDRESSES_FILE,
    # The 2026 files had 12 mixed waste routes, 2 green waste routes (Jurbarkas and Jurbarkai)
    # and 9 packaging routes, each with glass, and gave a mixed waste schedule to 345 of the 374
    # settlements. Far fewer means the format changed and the parser or the matching missed
    # rows.
    min_areas={"household": 10, "packaging": 7, "glass": 7, "green": 1},
    min_household_places=300,
    # Jurbarko r. had about 12,800 addresses in 2026.
    min_address_points=9_000,
    folder="jurbarko-r",
    title="Jurbarko r. (Tauragės RATC)",
    label="Jurbarko r.",
)


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    """The links of the page with their texts, and the year of the heading above each
    ("2026 metų atliekų išvežimo grafikai")."""

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
        elif match := re.search(r"(?<!\d)(20\d{2})\s*m(?:etų|\.)", data):
            self.year = int(match.group(1))


def _year_in(text: str) -> int | None:
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}
    return years.pop() if len(years) == 1 else None


def file_name(url: str) -> str:
    return PurePosixPath(unquote(urlsplit(url).path)).name


def _group(folded: str) -> str:
    """Whom a link's file is for, where the town and the villages have files of their own
    ("Tauragės miesto mišrių ...", "Tauragės rajono mišrių ..."): "town", "district", or ""
    for both ("Jurbarko miesto ir rajono ...")."""
    town, district = "miesto" in folded.split(), "rajono" in folded.split()
    return "town" if town and not district else "district" if district and not town else ""


def find_files(
    html: str, municipality: Municipality = JURBARKAS, page_url: str = PAGE_URL
) -> list[tuple[SourceFile, int | None]]:
    """The municipality's schedules linked from the page, by the texts of the links, with
    their years: in the file's name ("Jurbarko-pakuotes_2026_suderintas.pdf", not the upload
    folder "2025/12"), in the link's text or in the heading above it."""
    collector = _Links()
    collector.feed(html)
    files: list[tuple[SourceFile, int | None]] = []
    for href, text, heading_year in collector.links:
        url = urljoin(page_url, href)
        folded = fold(text)
        if not url.lower().endswith(".pdf") or municipality.link_word not in folded:
            continue
        kind = next((k for word, k in municipality.link_kinds if word in folded), None)
        if kind is None or any(word in folded for word in NOT_SCHEDULES):
            continue
        if all(f.url != url for f, _ in files):
            name = file_name(url)
            year = _year_in(name) or _year_in(text) or heading_year
            source = SourceFile(kind=kind, url=url, file_name=name, group=_group(folded))
            files.append((source, year))
    return files


def _uploaded(file: SourceFile) -> str:
    """ "2025/12" from ".../uploads/2025/12/name.pdf": when the file was put on the site."""
    match = re.search(r"/uploads/(\d{4}/\d{2})/", file.url)
    return match.group(1) if match else ""


def select_files(
    files: list[tuple[SourceFile, int | None]], today: date
) -> tuple[list[SourceFile], list[str]]:
    """Per kind, the files of this year and later; if there are none, the newest one. Of two
    files for the same year (a correction linked next to the original), the one uploaded
    last, or linked last. The town's and the villages' files of a kind (SourceFile.group) are
    chosen apart."""
    selected: list[SourceFile] = []
    warnings = [
        f"{f.file_name}: no year in its name, link or heading; not read" for f, y in files if not y
    ]
    for kind, group in sorted({(f.kind, f.group) for f, _ in files}):
        mine = [(f, y) for f, y in files if (f.kind, f.group) == (kind, group) and y]
        schedule = f"{kind} schedule" + (f" of the {group}" if group else "")
        running = [(f, y) for f, y in mine if y >= today.year]
        if not running and mine:
            newest = max(y for _, y in mine)
            running = [(f, y) for f, y in mine if y == newest]
        if mine and today.year not in {y for _, y in running}:
            warnings.append(f"no {schedule} for {today.year} on the page")
        for year in sorted({y for _, y in running}):
            same = [f for f, y in running if y == year]
            newest = max(enumerate(same), key=lambda item: (_uploaded(item[1]), item[0]))[1]
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer {schedule} for {year}"
                for f in same
                if f is not newest
            ]
            selected.append(newest)
    return selected, warnings


def download(
    municipality: Municipality, today: date, keep_days: int
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, warnings = select_files(find_files(html, municipality), today)
    return [(f, http.get(f.url, timeout=60)) for f in files], warnings


# --- the visible text of a PDF ------------------------------------------------------


class _ClipInterpreter(PDFPageInterpreter):
    """pdfminer's interpreter, also keeping the clipping area, as a box, which pdfminer
    ignores. Office programs clip every piece of text to its box."""

    def init_state(self, ctm) -> None:
        super().init_state(ctm)
        self.clip: tuple[float, float, float, float] | None = None
        self.clips: list[tuple[float, float, float, float] | None] = []
        self.clipping = False

    def do_q(self) -> None:
        self.clips.append(self.clip)
        super().do_q()

    def do_Q(self) -> None:  # noqa: N802 (the PDF operator)
        if self.clips:
            self.clip = self.clips.pop()
        super().do_Q()

    def do_W(self) -> None:  # noqa: N802
        self.clipping = True

    def do_W_a(self) -> None:  # noqa: N802
        self.clipping = True

    def do_n(self) -> None:
        # "re W n": the path just drawn becomes the clipping area.
        points = [apply_matrix_pt(self.ctm, s[-2:]) for s in self.curpath if len(s) >= 3]
        if self.clipping and points:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            box = (min(xs), min(ys), max(xs), max(ys))
            if self.clip is not None:
                box = (
                    max(box[0], self.clip[0]),
                    max(box[1], self.clip[1]),
                    min(box[2], self.clip[2]),
                    min(box[3], self.clip[3]),
                )
            self.clip = box
        self.clipping = False
        super().do_n()


class _HiddenChars(PDFPageAggregator):
    """Collects the characters drawn outside the clipping area."""

    def __init__(self, rsrcmgr: PDFResourceManager) -> None:
        super().__init__(rsrcmgr)
        self.interpreter: _ClipInterpreter | None = None
        self.hidden: set[tuple[float, float, str]] = set()

    def render_char(self, *args, **kwargs) -> float:
        advance = super().render_char(*args, **kwargs)
        clip = self.interpreter.clip if self.interpreter else None
        char = self.cur_item._objs[-1] if self.cur_item._objs else None
        if clip is not None and isinstance(char, LTChar):
            x, y = (char.x0 + char.x1) / 2, (char.y0 + char.y1) / 2
            if not (clip[0] - 1 <= x <= clip[2] + 1 and clip[1] - 1 <= y <= clip[3] + 1):
                self.hidden.add((round(char.x0, 2), round(char.y0, 2), char.get_text()))
        return advance


def _visible(page):
    """The page without the characters it clips away."""
    resources = PDFResourceManager()
    device = _HiddenChars(resources)
    interpreter = _ClipInterpreter(resources, device)
    device.interpreter = interpreter
    interpreter.process_page(page.page_obj)
    if not device.hidden:
        return page
    return page.filter(
        lambda obj: (
            obj.get("object_type") != "char"
            or (round(obj["x0"], 2), round(obj["y0"], 2), obj["text"]) not in device.hidden
        )
    )


def _lines(page) -> list[list[dict]]:
    """The words of a page in lines, top to bottom."""
    lines: list[list[dict]] = []
    for word in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= 2:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _vertical_rules(page) -> list[tuple[float, float, float]]:
    """The vertical borders of the cells: (x, top, bottom)."""
    return [
        ((r["x0"] + r["x1"]) / 2, r["top"], r["bottom"])
        for r in page.rects + page.lines
        if r["x1"] - r["x0"] < 2 and r["bottom"] - r["top"] > 3
    ]


# --- the tables ------------------------------------------------------------------

# Titles above the months of a table, folded. Shared containers of apartment buildings have
# weekdays, no dates.
TITLES: tuple[tuple[str, Kind | None], ...] = (
    ("misrios komunalines", "household"),
    ("zaliosios atliekos", "green"),
    ("maisto atliekos", "food"),
    ("daugiabuciu namu", None),
)
# Labels of the rows of dates, folded.
ROW_KINDS: tuple[tuple[str, Kind], ...] = (
    ("stikl", "glass"),
    ("plastik", "packaging"),
    ("popier", "packaging"),
    ("pakuo", "packaging"),
)
# The label of the row of places: "Seniūnijų kaimų ir gyvenviečių pavadinimai".
PLACES_LABEL = re.compile(r"pavad|seniunij|gyvenviec")
# Lines that end a table: the next route's heading, the contacts, the footer.
TABLE_END = re.compile(r"^\d*\s*marsrut|visais klausimais|su atlieku surinkimo grafiku")
DAYS = re.compile(r"\d{1,2}(?:\s*[,;]\s*\d{1,2})*[,;]?")
# The columns' titles: whole names only, "Liepų g." and "Vasaros g." aren't months.
MONTHS = {
    fold(name): number
    for number, name in enumerate(
        "Sausis Vasaris Kovas Balandis Gegužė Birželis Liepa Rugpjūtis Rugsėjis Spalis Lapkritis "
        "Gruodis".split(),
        start=1,
    )
}


@dataclass
class _Table:
    kind: Kind | None  # of the title above the months; None: in the labels of the rows
    months: list[tuple[float, int]]  # the centre of each month's column
    left: float  # the left border of the columns of dates and places
    page: int
    row_kind: Kind | None = None
    dates: dict[Kind, set[date]] = field(default_factory=lambda: defaultdict(set))
    lines: list[str] = field(default_factory=list)
    # parse_places_first: the words of row labels since the last row of dates, and the months
    # the table has had.
    pending: list[str] = field(default_factory=list)
    seen: set[int] = field(default_factory=set)

    def month(self, x: float) -> int:
        return min(self.months, key=lambda m: abs(m[0] - x))[1]

    @property
    def places(self) -> str:
        text = ""
        for line in self.lines:
            # "Bišpilio Sodo 1-" + "oji g.", "A. Giedraičio-" + "Giedriaus g."
            joined = re.search(r"\w-$", text) is not None
            text += line if joined or not text else f" {line}"
        return clean_text(text)


def _title(words: list[dict]) -> tuple[bool, Kind | None]:
    text = fold(" ".join(w["text"] for w in words))
    for phrase, kind in TITLES:
        if phrase in text and len(words) <= 8:
            return True, kind
    return False, None


def _year(pdf, source: SourceFile) -> int:
    """The year in the file's title ("... GRAFIKAS 2026 M."), which must agree with its name."""
    first = pdf.pages[0].extract_text() or ""
    titled = re.search(r"(?<!\d)(20\d{2})\s*m\b", first[:400], re.I)
    named = _year_in(source.file_name)
    if titled and named and int(titled.group(1)) != named:
        raise ValueError(f"{source.file_name}: the title says {titled.group(1)}, the name {named}")
    year = int(titled.group(1)) if titled else named
    if year is None:
        raise ValueError(f"{source.file_name}: no year in its title or name")
    return year


def parse_file(
    source: SourceFile, content: bytes, municipality: Municipality = JURBARKAS
) -> ParseResult:
    """The routes of one file. Strict: dates that aren't days of the month's column, a table
    without dates, places or a waste type, and a file without tables raise ValueError."""
    if municipality.places_first:
        return parse_places_first(source, content, municipality.provider)
    tables: list[_Table] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        year = _year(pdf, source)
        table: _Table | None = None
        title: Kind | None = None
        for page_no, page in enumerate(pdf.pages, start=1):
            page = _visible(page)
            rules = _vertical_rules(page)
            for line in _lines(page):
                where = f"{source.file_name} page {page_no}"
                is_title, kind = _title(line)
                months = [(w, MONTHS[fold(w["text"])]) for w in line if fold(w["text"]) in MONTHS]
                ends = TABLE_END.search(fold(" ".join(w["text"] for w in line)))
                if (is_title or len(months) >= 6 or ends) and table:
                    tables.append(table)
                    table = None
                if is_title:
                    title = kind
                elif len(months) >= 6:
                    table = _new_table(title, months, rules, page_no, where)
                    title = None
                elif table:
                    _read_line(table, line, year, where)
                # Before the first table: titles, notices, the shared containers' weekdays.
        if table:
            tables.append(table)
    return _result(tables, source, municipality.provider)


def _result(
    tables: list[_Table], source: SourceFile, provider: Provider, split: bool = False
) -> ParseResult:
    """A row per table and kind of its dates. With `split`, a table that lists several routes
    with the same dates ("2.Maršrutas. ... 3. Maršrutas. ...") is a row per route."""
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for table in tables:
        where = f"{source.file_name} page {table.page}"
        if not table.dates:
            raise ValueError(f"{where}: a table without dates")
        name = table.places
        if not name:
            raise ValueError(f"{where}: dates without places")
        names = [name]
        if split and len(starts := [m.start() for m in _ROUTE.finditer(name)]) > 1:
            bounds = zip([0, *starts[1:]], [*starts[1:], None], strict=True)
            names = [name[a:b].strip() for a, b in bounds]
        for kind, dates in table.dates.items():
            for name in names:
                area = Area(kind=kind, name=name, provider=provider.id, dates=set(dates))
                weekdays = {d.weekday() for d in dates}
                if len(weekdays) == 1:
                    area.weekday = WEEKDAY_NAMES[weekdays.pop()]
                existing = areas.setdefault(area.id, area)
                if existing is not area:
                    warnings.append(f"{where}: {kind} of {name[:60]!r} is listed twice")
                    existing.dates |= area.dates
    if not areas:
        raise ValueError(f"{source.file_name}: no schedule table found")
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def _new_table(
    title: Kind | None, months: list[tuple[dict, int]], rules: list, page_no: int, where: str
) -> _Table:
    """A table from the line of its months' titles."""
    numbers = [m for _, m in months]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError(f"{where}: unexpected months {numbers}")
    first = months[0][0]
    middle = (first["top"] + first["bottom"]) / 2
    # The border of the cells left of the first month; left of it are the rows' labels.
    borders = [x for x, top, bottom in rules if x < first["x0"] and top - 1 <= middle <= bottom + 1]
    left = max(borders) if borders else first["x0"] - 4
    centres = [((w["x0"] + w["x1"]) / 2, m) for w, m in months]
    return _Table(title, centres, left, page_no)


def _read_line(table: _Table, line: list[dict], year: int, where: str) -> None:
    """One line of a table: dates in the months' columns, or a line of its places. The labels
    of the rows are left of the columns."""
    label = fold(" ".join(w["text"] for w in line if w["x0"] < table.left - 1))
    content = [w for w in line if w["x0"] >= table.left - 1]
    if row_kind := next((k for word, k in ROW_KINDS if word in label), None):
        table.row_kind = row_kind
    if PLACES_LABEL.search(label) and not table.lines:
        table.lines.append("")  # the places start
    if not content:
        return
    if not table.lines and all(DAYS.fullmatch(w["text"]) for w in content):
        kind = table.row_kind or table.kind
        if kind is None:
            raise ValueError(f"{where}: dates of no waste type: {[w['text'] for w in content]}")
        for word in content:
            month = table.month((word["x0"] + word["x1"]) / 2)
            for day in re.findall(r"\d+", word["text"]):
                try:
                    table.dates[kind].add(date(year, month, int(day)))
                except ValueError as error:
                    raise ValueError(f"{where}: {day} of month {month}: {error}") from error
        return
    if not table.dates:
        raise ValueError(
            f"{where}: text before the dates: {' '.join(w['text'] for w in content)!r}"
        )
    table.lines.append(" ".join(w["text"] for w in content))


# --- tables with their places above the dates --------------------------------------

# The waste type of a row of dates, by the words of its label, folded and without spaces
# ("M i šr io s"): the label may be on the row's line, above it or around it ("Žaliosios/
# maisto/" above, "virtuvės atliekos" below). Food and green waste in one container is food
# waste, as for Mažeikių r.
LABEL_KINDS: tuple[tuple[str, Kind], ...] = (
    ("maist", "food"),
    ("virtuv", "food"),
    ("zali", "green"),
    ("stikl", "glass"),
    ("pakuo", "packaging"),
    ("popier", "packaging"),
    ("plastik", "packaging"),
    ("metal", "packaging"),
    ("misri", "household"),
    ("komunalin", "household"),
)
WEEKDAYS = {fold(name) for name in WEEKDAY_NAMES}
# "PIRMADIENIS I", "TREČIADIENIS": the heading above a table (Tauragė's files).
_WEEKDAY_HEADING = re.compile(rf"(?:{'|'.join(sorted(WEEKDAYS))})(?: i{{1,3}})?")
# The first line of a table's places: "(1)Šilalės miesto gatvės:", "1.Maršrutas.", "Laukuvos
# sen:", "Šilalės kaimiškoji sen:", "Pagėgių sen.:".
_PLACES_START = re.compile(
    rf"\(\d+\)|\d{{1,2}}\s*\.?\s*Maršrut|{_WORD}(?:\s+(?i:miesto|kaimiškoji))?\s+"
    r"(?i:sen\b|sen[iū]*nij)"
)
# A route of a table that lists several: "2.Maršrutas.", "3. Maršrutas.", "11 Maršrutas.".
_ROUTE = re.compile(r"(?<![\w.])\d{1,2}\s*\.?\s*Maršrutas\b")


def _label_kind(words: list[str]) -> Kind | None:
    text = fold(" ".join(words)).replace(" ", "")
    return next((kind for word, kind in LABEL_KINDS if word in text), None)


def _margin(lines: list[list[dict]], rules: list, before: float) -> float:
    """The right border of the column left of the rows' labels: the weekday is written there
    letter by letter, top to bottom (Šilalės r., Pagėgių sav.). From the border left of
    "Mėnuo"; on a page without it, the page's before."""
    for line in lines:
        for word in line:
            if fold(word["text"]) == "menuo":
                middle = (word["top"] + word["bottom"]) / 2
                borders = [
                    x
                    for x, top, bottom in rules
                    if x <= word["x0"] + 0.5 and top - 1 <= middle <= bottom + 1
                ]
                return max(borders, default=0.0)
    return before


def parse_places_first(source: SourceFile, content: bytes, provider: Provider) -> ParseResult:
    """The routes of a file whose tables have their places first, then the months (in one row
    or in two of six) and a row of dates per waste type, its label left of the months:

        PIRMADIENIS I
        Senamiestis I. Aušros g., Aušros tak., D. Poškos g. (lyginiai 24-44, ...), ...
        Mėnuo                        | Sausis | Vasaris | ... | Birželis
        Mišrios komunalinės atliekos | 12, 26 | 9, 23   | ... | 1, 15, 29
        Mėnuo                        | Liepa  | ...

    A table starts after a weekday heading or at a line that starts a list of places ("(1)",
    "1.Maršrutas.", "Laukuvos sen:"), and ends at the next one; text between tables (titles,
    notices, contacts) isn't read. Strict as parse_file: dates that aren't days of the month's
    column, of no waste type, before the months, or months without places raise ValueError."""
    tables: list[_Table] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        year = _year(pdf, source)
        table: _Table | None = None
        reading = ""  # "places" or "dates" of `table`, or "" between tables
        margin = 0.0
        for page_no, page in enumerate(pdf.pages, start=1):
            page = _visible(page)
            rules = _vertical_rules(page)
            lines = _lines(page)
            margin = _margin(lines, rules, margin)
            where = f"{source.file_name} page {page_no}"
            for line in lines:
                line = [w for w in line if w["x1"] > margin + 1]
                text = " ".join(w["text"] for w in line)
                folded = fold(text)
                if not folded or folded == "menuo":
                    continue
                months = [(w, MONTHS[fold(w["text"])]) for w in line if fold(w["text"]) in MONTHS]
                if len(months) >= 6:
                    if table is None or not table.lines:
                        raise ValueError(f"{where}: months of a table without places")
                    _months(table, months, rules, where)
                    reading = "dates"
                elif _WEEKDAY_HEADING.fullmatch(folded):
                    if reading == "places" and table and table.lines:
                        raise ValueError(f"{where}: places without dates: {table.places[:60]!r}")
                    if table and reading == "dates":
                        tables.append(table)
                    table, reading = _Table(None, [], 0.0, page_no), "places"
                elif reading == "places" and table:
                    if all(DAYS.fullmatch(w["text"]) for w in line):
                        raise ValueError(f"{where}: dates before the months: {text!r}")
                    table.lines.append(text)
                elif reading == "dates" and table and _row(table, line, year, where):
                    pass
                else:
                    if table and reading == "dates":
                        tables.append(table)
                    table, reading = None, ""
                    if _PLACES_START.match(text):
                        table, reading = _Table(None, [], 0.0, page_no, lines=[text]), "places"
        if table and reading == "dates":
            tables.append(table)
        elif table and table.lines:
            raise ValueError(f"{source.file_name}: places without dates: {table.places[:60]!r}")
    return _result(tables, source, provider, split=True)


def _months(table: _Table, months: list[tuple[dict, int]], rules: list, where: str) -> None:
    """A row of months' names: the columns of the dates below it."""
    new = _new_table(None, months, rules, table.page, where)
    numbers = {m for _, m in months}
    if numbers & table.seen:
        raise ValueError(f"{where}: months {sorted(numbers & table.seen)} twice in a table")
    table.seen |= numbers
    table.months, table.left = new.months, new.left
    table.pending, table.row_kind = [], None


def _row(table: _Table, line: list[dict], year: int, where: str) -> bool:
    """One line under the months: dates, a weekday per month ("Penktadienis"), or words of a
    row's label. False for anything else, which ends the table."""
    label = [w["text"] for w in line if w["x0"] < table.left - 1]
    content = [w for w in line if w["x0"] >= table.left - 1]
    if not content:
        table.pending += label
        table.row_kind = None
        return True
    if all(fold(w["text"]) in WEEKDAYS for w in content):
        table.pending += label
        table.row_kind = None
        return True
    if not all(DAYS.fullmatch(w["text"]) for w in content):
        return False
    # Its own label, the label's words since the row above, or the row above's kind: the
    # cell of a month with many dates takes several lines (Pagėgiai's weekly mixed waste).
    kind = _label_kind(label) or _label_kind(table.pending) or table.row_kind
    if kind is None:
        raise ValueError(f"{where}: dates of no waste type: {[w['text'] for w in content]}")
    for word in content:
        month = table.month((word["x0"] + word["x1"]) / 2)
        for day in re.findall(r"\d+", word["text"]):
            try:
                table.dates[kind].add(date(year, month, int(day)))
            except ValueError as error:
                raise ValueError(f"{where}: {day} of month {month}: {error}") from error
    table.pending, table.row_kind = [], kind
    return True


# --- the routes of Tauragės r., Šilalės r. and Pagėgių sav. ------------------------------

# An eldership's section: "Žygaičių seniūnija.", "SKAUDVILĖS SENIŪNIJA:", "MAŽONŲ SENŪNIJA:",
# "Laukuvos sen:", "Šilalės kaimiškoji sen:", "Upynos sen.,", "Pagėgių sen.:".
_ELDERSHIP = re.compile(
    rf"(?<![\w-])(?P<name>{_WORD}(?:\s+(?i:miesto|kaimiškoji))?)\s+"
    r"(?i:sen\b\.?|sen[iū]*nij\w*)\s*[:.,]?"
)
# A part of Tauragė before its streets, or a village written so: "Senamiestis I.", "Taurai.".
_LABEL = re.compile(
    rf"(?:^|(?<=[.,;)]\s))(?P<label>[{_UPPER}][a-ząčęėįšųūž]+(?:\s+I{{1,3}})?)\.\s+(?=[{_UPPER}])"
)
# The publishers' spellings, as SectionRoutes reads them.
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # The route's number: "1.Maršrutas.", "11 Maršrutas." ("(1)" is a bracket of _RANGE).
    (re.compile(r"(?<![\w.])\d{1,2}\s*\.?\s*Maršrutas\b\.?"), " "),
    # "Šilalės m. privačių namų konteineriai.": the containers of private houses, the town.
    (re.compile(r",?\s*privači\w*\s+nam\w*\s+konteiner\w*\.?", re.I), ""),
    # "Šilalės miesto gatvės:": streets of the town.
    (re.compile(rf"\b({_WORD})\s+miesto\s+gatvės\s*:"), r"\1 m.,"),
    # "Joniškės kolektyviniai sodai": the gardens of the village, its streets.
    (re.compile(rf"\b({_WORD})\s+kolektyvin\w*\s+sod\w*"), r"\1 k."),
    # "Šiurpiškės km.", "Puntuko sk." (a skersgatvis), "Aušros takas".
    (re.compile(r"\bkm\."), "k."),
    (re.compile(r"\bsk\."), "skg."),
    (re.compile(r"\btakas\b"), "tak."),
    # "fPožerūnų k.": a letter typed before a name.
    (re.compile(rf"(?<![\w-])[a-ząčęėįšųūž](?=[{_UPPER}][a-ząčęėįšųūž])"), ""),
    # Houses of a street from one to another: "T. Ivanausko g. 52-95", "V. Kudirkos g. 37
    # (46)-64", "Prezidento g. 41(76) – 79(90)", "Tremtinių kelias 1-15A" (the brackets are
    # gone, _RANGE). The street is in each route that has a part of it, and the user picks; the
    # route's text says which part.
    (
        re.compile(
            r"(\b(?:g|pl|al|skg|tak|kel)\.|\bkelias)\s*\d+\s*[A-Za-z]?\s*[-–]\s*\d+\s*[A-Za-z]?"
        ),
        r"\1",
    ),
    # "Šilalės g. 61A,B,C,D, 63 A,B,C": the houses 61A to 61D and 63A to 63C.
    (re.compile(r"(\d+)\s*([A-Z])(?:\s*,\s*[A-Z](?![\w.]))+"), r"\1\2"),
    # Houses of a village by their numbers: "Kundročių k. (tik 5, 5A, 6, 7)" (or "Antegluonio
    # k.(5,4,11,12,13)", a bracket of _RANGE). The village is in each route that has some, and
    # the user picks.
    (re.compile(r"\(\s*tik\s+\d+\s*[A-Za-z]?(?:\s*[,;]\s*\d+\s*[A-Za-z]?)*\s*[.,]?\s*\)"), ""),
    # The full stop after a house number ("Gedminiškės k. 11. Laukuvos sen:", "34 ."), after a
    # type or a bracket ("Kalvaičių k.(0).", "Norvainių k. (tik 1,2).", "Tauragės m.
    # (Tarailiai). Akacijų g."), and a missing one ("Padrūtupių k Drūtaviškių k.").
    (re.compile(r"(?<=\d)\s*\.(?=[\s,;]|$)"), ""),
    (re.compile(r"(?<=[.)])\s*\.(?![\w.])"), ""),
    (re.compile(rf"\b(k|vs|mstl)\s+(?=[{_UPPER}])"), r"\1. "),
)
# A bracket with which houses of a street or a village: "(lyginiai 24-44, nelyginiai 23-51
# (nuo Vytauto g. iki Gedimino g.))", "(8-10, 17-19)", "(nuo Ramovės g. iki Miltaujos g.)",
# "(5,4,11,12,13)"; the route's number, "(1)"; and "(0)" after some villages (Pagėgiai's
# packaging), which says nothing we can read.
_RANGE = re.compile(r"\(\s*(?:lyginiai|nelyginiai|nuo|\d)", re.I)
# What follows a bracket that should have been closed: "(lyginiai 72-110, nelyginiai 77-101
# (nuo Vytauto g. iki Gedimino g.), K. Donelaičio g. ...".
_NEXT_PART = re.compile(rf"\s*,\s*[{_UPPER}]")


def _without_ranges(text: str) -> str:
    """The text without the brackets that say which houses of a street a route has (the street
    is in each route that has some), also when the file leaves one unclosed, and without
    brackets closed that were never opened."""
    kept: list[str] = []
    i = 0
    while i < len(text):
        if not _RANGE.match(text, i):
            kept.append(text[i])
            i += 1
            continue
        depth, i = 1, i + 1
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
            if text[i - 1] == ")" and depth and _NEXT_PART.match(text, i):
                break
    depth, result = 0, []
    for ch in kept:
        if ch == ")" and depth == 0:
            continue
        depth += {"(": 1, ")": -1}.get(ch, 0)
        result.append(ch)
    return "".join(result)


class Routes(SectionRoutes):
    """Reads one row of the schedules of Tauragės r., Šilalės r. and Pagėgių sav.:

        2.Maršrutas. Lauksargių seniūnija. Aukštvilkių k., ... Tauragės seniūnija. Beigeriškių k.
        Senamiestis I. Aušros g., ... Taurai. Alėjos g., ... Tauragės m. (Tarailiai). Akacijų g.
        (1) Tauragės m. Islandijos g., T. Ivanausko g. 52-95 (nuo ...), ... Norkaičių k. Brolių g.
        Šilalės miesto sen: Šilalės m. privačių namų konteineriai. Traksėdžio sen: Dirkintų k.
            Birutės g. 1A, 9, 15, 25, 29
        (1)Šilalės miesto gatvės: A. Rubšio g., ... Traksėdžio sen: Dirkintų k. (tik Birutės g.)
        Pagėgių sen.: Benininkų k., Pagėgių m.

    The publishers' spellings are first written as SectionRoutes reads them (_FIXES), without
    the brackets that say which houses of a street (_without_ranges): a street split between
    routes is in each, and the app asks. A part of Tauragė named before its streets
    ("Senamiestis I.", "Jovarai.") is the town; a village named so ("Taurai.", "Butkeliai.") is
    that village. A settlement is looked up in the eldership its section names, as SectionRoutes
    does, and outside sections in the whole municipality. Streets named before any settlement
    are the town's (`town`). A street the settlement before it doesn't have is the street of the
    only other settlement of its eldership that has it (neighbour), or reported; either way the
    streets after it stay that settlement's. A village with house numbers ("Katyčių k. 7, 11")
    is the whole village, as for SectionRoutes: the app asks between its routes.

    None of the files names every street of private houses (the town files of Tauragė leave out
    some streets the packaging file has), and none names the apartment buildings' streets, whose
    shared containers have schedules of their own: a street of a town that no route names is
    left to the app, which offers the town's routes (`towns_by_street` is empty)."""

    def __init__(
        self,
        index: Index,
        provider: Provider,
        variants: dict[int, dict[str, str]],
        town: str = "",
    ):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.unknown: list[str] = []
        self.named: dict[str, set[int]] | None = None
        self.kind = ""
        self.mine = [s for s in index.registry.settlements if s.district in provider.elderships]
        self.town = next(s for s in self.mine if s.name == town and s.abbr == "m.")
        self.towns_by_street: set[int] = set()

    def written(self, name: str) -> str:
        """The row's text as SectionRoutes reads it: "Senamiestis I. Aušros g., D. Poškos g.
        (lyginiai 24-44, ...)" is "Tauragės m., Aušros g., D. Poškos g."."""
        text = clean_text(name)
        for written, registered in self.provider.aliases:
            text = text.replace(written, registered)
        text = clean_text(_without_ranges(text))
        for pattern, replacement in (*_FIXES, *_SPELLINGS):
            text = pattern.sub(replacement, text)
        return clean_text(_LABEL.sub(self._label, clean_text(text)))

    def _label(self, match: re.Match[str]) -> str:
        key = fold(match["label"])
        named = [s for s in self.mine if fold(s.name) == key and s.abbr != "m."]
        place = named[0] if len(named) == 1 else self.town
        return f"{place.genitive} {place.abbr}, "

    def district(self, name: str) -> str | None:
        """The eldership a section names ("SKAUDVILĖS", "Šilalės kaimiškoji")."""
        key = fold(name)
        exact = [d for d in self.provider.elderships if fold(d) == key]
        return exact[0] if exact else self.index.district(name)

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        if district:
            return super().settlements(name, numerals, kind, district)
        # Outside sections: in the whole municipality, by the name as it is or with a typo.
        names = [f"{name} {n}" for n in re.findall(r"I{1,3}", numerals)] if numerals else [name]
        hits: list[Settlement] = []
        for one in names:
            key = fold(one)
            found = [s for s in self.mine if key in (fold(s.name), fold(s.genitive))]
            if not found:
                close = [s for s in self.mine if _one_off(key, fold(s.genitive))]
                found = close if len(close) == 1 else []
            abbr = _SETTLEMENT_TYPES.get(kind or "")
            wanted = {"m.": ("m.", "mstl."), "mstl.": ("mstl.", "m.")}.get(abbr or "", (abbr,))
            typed = next((t for a in wanted if (t := [s for s in found if s.abbr == a])), [])
            hits += typed or found
        return list({s.code: s for s in hits}.values())

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        self.kind = area.kind
        text = self.written(area.name)
        marks = list(_ELDERSHIP.finditer(text))
        lead = text[: marks[0].start()] if marks else text
        stops = self.section("", lead) if lead.strip(" .,;:") else []
        for i, mark in enumerate(marks):
            until = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            district = self.district(mark["name"])
            if district in self.provider.elderships:
                stops += self.section(district, text[mark.end() : until])
            else:
                self.unknown.append(mark.group(0).strip())
        return [(s.settlement, c) for s in stops for c in s.clauses(area.id)], False

    def section(self, district: str, text: str) -> list[_Stop]:
        """The settlements of an eldership's section, or of none (""), and their streets, as
        SectionRoutes reads them, but a street the settlement before it doesn't have leaves the
        streets after it to that settlement."""
        stops: list[_Stop] = []
        current: list[_Stop] = []  # the settlement the streets after it belong to
        last: list[tuple[_Stop, set[str]]] = []  # the last street, for house numbers after it
        where = f"{district} sen." if district else self.town.name
        for part in _section_parts(text):
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0] if rest else None
            head = head.strip(" ,;:")
            if _HOUSE.fullmatch(head):
                # "Birutės g. 1A, 9, 15": more houses of that street.
                for stop, keys in last:
                    stop.add(keys, houses=True)
                continue
            match = _SECTION_ITEM.fullmatch(head)
            name, numerals, kind = match.group("name", "numerals", "type") if match else ("",) * 3
            houses = bool(match and match.group("houses"))
            places: list[Settlement] = []
            if match and (kind in _SETTLEMENT_TYPES or numerals or not (kind or houses)):
                places = self.settlements(name, numerals, kind, district)
            if match and not places and kind not in _SETTLEMENT_TYPES:
                # A street of the settlement before it, or of the town before any settlement.
                targets = current
                if not targets and district in ("", self.town.district):
                    town = next((s for s in stops if s.settlement is self.town), None)
                    targets = [town or _Stop(self.town)]
                loose = bool(kind or houses)
                found = [(t, self.streets(t.settlement, head, name, kind, loose)) for t in targets]
                if not any(keys for _, keys in found) and (kind or houses):
                    found = self.neighbour(targets, stops, head, name, kind)
                if any(keys for _, keys in found):
                    last = [(t, keys) for t, keys in found if keys]
                    for target, keys in last:
                        target.add(keys, houses)
                        if target not in stops:
                            stops.append(target)
                    continue
                if (kind or houses) and targets:
                    self.unknown += [
                        f"{t.settlement.genitive} {t.settlement.abbr}: {head[:60]}" for t in targets
                    ]
                    last = []
                    continue
            if not places:
                self.unknown.append(f"{where}: {head[:60]}")
                current, last = [], []
                continue
            current, last = [_Stop(s) for s in places], []
            stops += current
            if spec is not None:
                self.spec(current, spec)
        return stops

    def neighbour(
        self, targets: list[_Stop], stops: list[_Stop], part: str, name: str, kind: str | None
    ) -> list[tuple[_Stop, set[str]]]:
        """A street the settlement before it doesn't have, of the only other settlement of its
        eldership that has it, by its whole name and type: "Taurai. ..., Smilgų g., Tauragės
        Dvaro g., Tilžės pl." names streets of Tauragės Dvaras among those of Taurai. Not one
        already in the route whole."""
        elderships = {t.settlement.district for t in targets}
        others = [
            (s, keys)
            for s in self.mine
            if s.district in elderships
            and all(s is not t.settlement for t in targets)
            and (
                keys := {
                    street_key(t)
                    for t in s.streets
                    if fold(t.name) == fold(name) and _street_type(t) == _STREET_TYPES.get(kind)
                }
            )
        ]
        if len(others) != 1:
            return []
        place, keys = others[0]
        stop = next((s for s in stops if s.settlement is place), None) or _Stop(place)
        return [] if stop in stops and stop.streets is None else [(stop, keys)]


TAURAGE = Municipality(
    provider=Provider(
        id="taurage",
        name=COMPANY,
        url=PAGE_URL,
        elderships=frozenset(
            {
                "Batakių",
                "Gaurės",
                "Lauksargių",
                "Mažonų",
                "Skaudvilės",
                "Tauragės",
                "Tauragės miesto",
                "Žygaičių",
            }
        ),
        reader=partial(Routes, town="Tauragė"),
        # The packaging file's spelling of Leono Laurinsko g.
        aliases=(("L. Laurinskio g.", "L. Laurinsko g."),),
        kinds=("household", "packaging", "glass", "food"),
    ),
    link_word="taurag",
    register=snapshot.TAURAGES_MUNICIPALITY,
    registry_file=snapshot.TAURAGES_REGISTRY_FILE,
    addresses_file=snapshot.TAURAGES_ADDRESSES_FILE,
    # The 2026 files had 12 mixed waste routes of the villages and 5 of the town, 5 food waste
    # routes (the town), and 18 packaging routes, each with glass, and gave a mixed waste
    # schedule to 277 of the 299 settlements.
    min_areas={"household": 13, "packaging": 14, "glass": 14, "food": 4},
    min_household_places=230,
    # About 16,100 addresses in 2026.
    min_address_points=11_000,
    folder="jurbarko-r",
    title="Tauragės r. (Tauragės RATC)",
    label="Tauragės r.",
    # The town's mixed waste and its food waste ("maisto ir žaliųjų") have files of their own,
    # apart from the villages' mixed waste; packaging and glass are in one file for both.
    link_kinds=(("pakuo", "packaging"), ("misri", "household"), ("maisto", "food")),
    file_kinds={
        "household": ("household",),
        "food": ("food",),
        "packaging": ("packaging", "glass"),
    },
    places_first=True,
    min_group_areas={("household", "district"): 9, ("household", "town"): 4},
)
SILALE = Municipality(
    provider=Provider(
        id="silale",
        name=COMPANY,
        url=PAGE_URL,
        elderships=frozenset(
            {
                "Bijotų",
                "Bilionių",
                "Didkiemio",
                "Kaltinėnų",
                "Kvėdarnos",
                "Laukuvos",
                "Pajūrio",
                "Palentinio",
                "Tenenių",
                "Traksėdžio",
                "Upynos",
                "Šilalės kaimiškoji",
                "Šilalės miesto",
                "Žadeikių",
            }
        ),
        reader=partial(Routes, town="Šilalė"),
        # The packaging file's spelling of Dievyčio g. (after the lake Dievytis).
        aliases=(("Dyvyčio g.", "Dievyčio g."),),
        kinds=("household", "packaging", "glass", "green"),
    ),
    link_word="silal",
    register=snapshot.SILALES_MUNICIPALITY,
    registry_file=snapshot.SILALES_REGISTRY_FILE,
    addresses_file=snapshot.SILALES_ADDRESSES_FILE,
    # 2026: 10 mixed waste routes, one with green waste (Šilalė), and 11 packaging routes,
    # each with glass, which gave a mixed waste schedule to 357 of the 430 settlements.
    min_areas={"household": 8, "packaging": 8, "glass": 8, "green": 1},
    min_household_places=300,
    # About 10,600 addresses in 2026.
    min_address_points=7_000,
    folder="jurbarko-r",
    title="Šilalės r. (Tauragės RATC)",
    label="Šilalės r.",
    places_first=True,
)
PAGEGIAI = Municipality(
    provider=Provider(
        id="pagegiai",
        name=COMPANY,
        url=PAGE_URL,
        elderships=frozenset({"Lumpėnų", "Natkiškių", "Pagėgių", "Stoniškių", "Vilkyškių"}),
        reader=partial(Routes, town="Pagėgiai"),
        kinds=("household", "packaging", "glass", "green"),
    ),
    link_word="pageg",
    register=snapshot.PAGEGIAI_MUNICIPALITY,
    registry_file=snapshot.PAGEGIAI_REGISTRY_FILE,
    addresses_file=snapshot.PAGEGIAI_ADDRESSES_FILE,
    # 2026: 7 mixed waste routes, one with green waste (Pagėgiai), and 3 packaging routes,
    # each with glass, which gave a mixed waste schedule to 105 of the 106 settlements.
    min_areas={"household": 5, "packaging": 2, "glass": 2, "green": 1},
    min_household_places=85,
    # About 3,300 addresses in 2026.
    min_address_points=2_200,
    folder="jurbarko-r",
    title="Pagėgių sav. (Tauragės RATC)",
    label="Pagėgių sav.",
    # One file, "mišrių/biologinių/pakuočių", has every kind.
    link_kinds=(("misri", "household"), ("pakuo", "packaging")),
    file_kinds={
        "household": ("household", "green", "packaging", "glass"),
        "packaging": ("packaging", "glass"),
    },
    places_first=True,
)
MUNICIPALITIES = (JURBARKAS, TAURAGE, SILALE, PAGEGIAI)


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]],
    registry: Registry,
    today: date,
    municipality: Municipality = JURBARKAS,
) -> list[str]:
    """Joins next year's routes to this year's, in place.

    A place has one row per waste type, with all its dates. Next year's files may word the
    routes differently, so a route of next year that covers exactly the same streets and
    settlements as one route of this year gives that route its dates. The rest is left out,
    with a warning, until its year starts and it becomes the schedule in force; routes of
    earlier years are dropped.

    Next year's files are checked now, not on 1 January when they take over: too few routes
    in them raise ValueError.

    The town's and the villages' files of a kind (SourceFile.group, Tauragės r.) are joined
    apart: each runs out on its own."""
    provider = municipality.provider
    reader = (provider.reader or SectionRoutes)(Index(registry), provider, defaultdict(dict))
    warnings: list[str] = []
    by_kind: dict[tuple[Kind, str], dict[int, list[tuple[ParseResult, Area]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for file, result in parsed:
        for area in result.areas:
            by_kind[area.kind, file.group][min(area.dates).year].append((result, area))
    for (kind, group), years in by_kind.items():
        started = [year for year in years if year <= today.year]
        base = max(started) if started else min(years)
        current: dict[frozenset, list[Area]] = defaultdict(list)
        for _, area in years[base]:
            current[reader.signature(area)].append(area)
        label = f"{kind} of the {group}" if group else kind
        for year in sorted(years):
            if year == base:
                continue
            minimum = municipality.min_group_areas.get(
                (kind, group), municipality.min_areas.get(kind, 0)
            )
            if year > base and len(years[year]) < minimum:
                raise ValueError(
                    f"only {len(years[year])} {label} routes in the {year} file "
                    f"(expected at least {minimum})"
                )
            signatures = {id(area): reader.signature(area) for _, area in years[year]}
            times = Counter(signatures.values())
            continued: set[int] = set()
            for result, area in years[year]:
                signature = signatures[id(area)]
                same = current.get(signature, [])
                # One route of each year, and places we recognise: anything else could give
                # a place the dates of another route.
                if year > base and signature and len(same) == 1 and times[signature] == 1:
                    same[0].dates |= area.dates
                    continued.add(id(same[0]))
                elif year > base:
                    warnings.append(
                        f"{label}: the {year} route {area.name[:60]!r} doesn't match one "
                        f"{base} route; its dates are left out until {year}"
                    )
                result.areas.remove(area)
            if year > base:
                warnings += [
                    f"{label}: the {base} route {area.name[:60]!r} has no dates for {year}"
                    for _, area in years[base]
                    if id(area) not in continued
                ]
    return warnings


def source(municipality: Municipality) -> build.Source:
    return build.Source(
        municipality.provider,
        partial(download, municipality),
        partial(parse_file, municipality=municipality),
        municipality.min_areas,
        municipality.min_household_places,
        municipality.file_kinds,
        partial(combine, municipality=municipality),
    )


SOURCE = source(JURBARKAS)


# --- the output ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    parser.add_argument(
        "--published",
        default=PUBLISHED_URL,
        help="site folder with yesterday's schedule.json, for a municipality whose build fails",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any municipality's build fails instead of keeping its published part",
    )
    args = parser.parse_args(argv)

    loader = None if args.strict else cache(build.load_published(args.published))
    results: list[build.PartResult] = []
    registries: list[tuple[Municipality, Registry]] = []
    points: list[address_points.AddressPoint] = []
    notes: list[str] = []
    down: set[str] = set()  # live sources that failed
    try:
        for municipality in MUNICIPALITIES:
            name, code = municipality.register
            registry, registry_note = build.live_or_snapshot(
                f"Address Register ({municipality.label})",
                _once(partial(address_register.fetch, name), "register", down),
                partial(snapshot.load_registry, municipality.registry_file),
            )
            found, points_note = build.live_or_snapshot(
                f"Address points ({municipality.label})",
                _once(partial(address_points.fetch, code), "points", down),
                partial(snapshot.load_points, municipality.addresses_file),
            )
            notes += [n for n in (registry_note, points_note) if n]
            registries.append((municipality, registry))
            points += found
            results += build.build_parts(
                (source(municipality),), registry, date.today(), args.keep_days, loader
            )
        dataset = build.merge_parts([(r.provider, r.part) for r in results if r.part], PAGE_URL)
        served = {loc["id"] for loc in dataset["locations"]}
        everything = Registry([s for _, registry in registries for s in registry.settlements])
        addresses = address_points.build_addresses(
            points, everything, served, dataset["generatedAt"]
        )
        places = Counter(addresses["places"][point[2]][0] for point in addresses["points"])
        for municipality, registry in registries:
            count = sum(places[f"g{s.code}"] for s in registry.settlements)
            if any(r.part for r in results if r.provider is municipality.provider) and (
                count < municipality.min_address_points
            ):
                raise build.ValidationError(f"{municipality.label}: only {count} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
        if r.error:
            if r.part:
                kept = f"the data published on {r.part['generatedAt'][:10]} is kept"
            else:
                kept = "there is no published data to keep, so it is left out"
            # An annotation on the workflow run.
            print(f"::warning::The {municipality.label} build failed; {kept}. {r.error}")

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name_, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name_).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    # A section per municipality: the company's name is the same in each.
    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
        part = r.part or {"locations": [], "areas": []}
        file_name_ = f"{municipality.label} in {args.out.name}/schedule.json"
        build.write_summary(part, [r], [], municipality.title, file_name_)
    build.write_summary(dataset, [], notes, "Tauragės RATC", f"{args.out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Raseinių rajonas: the schedules of UAB „Raseinių komunalinės paslaugos“ (rkp.lt), which
empties the containers of the individual houses of the whole municipality: mixed waste,
packaging and glass, and green waste in the towns and some villages.

Its page lists a PDF per eldership and kind under a heading of the kind ("Mišrių komunalinių
atliekų surinkimas Raseinių rajono seniūnijose:", "Pakuočių atliekų surinkimas ..."), each
linked by the eldership's name ("Betygalos seniūnija", "Raseinių miesto seniūnija"), and one
green waste file for the municipality ("Biologiškai skaidžių atliekų surinkimo grafikas 2026
metams"). The files are found by these texts. The PDFs say no year: a file's year is the one of
its folder ("2026 metų atliekų surinkimo grafikai/") or, for a file put elsewhere ("Raseinių m.
MKA.pdf"), of the workbook Excel printed it from, which is the PDF's title ("2026 metų UAB RKP
atliekų surinkimo grafikas.xlsx"). Bulky and hazardous waste, collected by registration, isn't
read. A new year's files are expected in December.

A file is a block per route, printed from a spreadsheet:

    BETYGALOS SENIŪNIJA
    Armonų k., Berteškių k., Betygalos mstl., ...                  the places
    Mėnuo        | Sausis | Vasaris | Kovas | ... | Gruodis
    Mišrios      |        |         |       |     |
    komunalinės  | 14     | 11      | 12    | ... | 09             mixed waste: once a month
    atliekos     |        |         |       |     |               in the villages

(packaging: a row "Plastiko, kartono, metalo pakuotės" and one "Stiklo pakuotė" with four dates a
year). The green waste file has the blocks of several elderships, each under its heading
("RASEINIŲ M. SENIŪNIJA"). The blocks are read from the positions of the words, not with
pdfplumber's table finder, which loses the dates of a block at the foot of a page and the label of
another. The towns' files (Raseiniai, Ariogala) list the streets of their private houses, some in
part ("Bažnyčios g. (nuo Kosmonautų g. iki Vilniaus g.)", "Taurupio g. Nr. 1-14": one more choice
for that street). A town street no route names is left to the app: the shared containers of the
apartment buildings have no file here, and no file says a street has none.

The places are read by aratc.Routes, a route's being those of the eldership of its file or
heading ("Betygalos sen.: Armonų k., ..."). Next year's file of an eldership continues the routes
of this year that cover the same places (tratc.combine).

A file that can't be downloaded or read keeps its rows of yesterday's data, with a warning, and
the other files are still updated: the municipality is 25 files, and one broken file shouldn't
hold back the other 24. A page without a file of every eldership fails the build (yesterday's
data is kept), as that means the page changed.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.raseiniai --out ../site/raseiniu-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cache, partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import pdfplumber

from . import addresses as address_points
from . import aratc, build, http, maatc, snapshot, tratc
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import Index, _Stop
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold

PAGE_URL = "https://www.rkp.lt/atlieku-tvarkymas/"
# Yesterday's data, for the files that can't be read today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/raseiniu-r"
COMPANY = "UAB „Raseinių komunalinės paslaugos“"
LABEL = "Raseinių r."
# The elderships of the municipality (register names), each with a mixed waste and a packaging
# file.
ELDERSHIPS = frozenset(
    {
        "Ariogalos",
        "Ariogalos miesto",
        "Betygalos",
        "Girkalnio",
        "Kalnujų",
        "Nemakščių",
        "Pagojukų",
        "Paliepių",
        "Raseinių",
        "Raseinių miesto",
        "Viduklės",
        "Šiluvos",
    }
)
# The kinds of schedule in a file of each kind.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household",),
    "packaging": ("packaging", "glass"),
    "green": ("green",),
}


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_STREET_TYPES = "g|skg|al|pl|tak|a"
_STREET = rf"(?:{_STREET_TYPES})"
_HOUSE_RANGE = r"\d+[A-Za-z]?(?![A-Za-z])(?:\s*-\s*\d+[A-Za-z]?(?![A-Za-z]))?"
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Some houses of a street: "Taurupio g. Nr. 1-14", "Vytauto g. nuo Nr. 36", "Pašlaitės g.
    # Nr. 1-21 ir 2-14": one more choice for that street, as a house number tells aratc.Routes.
    (
        re.compile(
            rf"\b({_STREET})\.\s+(?:nuo\s+)?Nr\.\s*{_HOUSE_RANGE}(?:\s*(?:,|ir)\s*{_HOUSE_RANGE})*"
        ),
        r"\1. 0",
    ),
    # A part of a street: "Savanorių g. (atkarpa nuo Vilniaus g. iki Spindulio g. sankryžos)",
    # read as aratc reads "(nuo ... iki ...)".
    (re.compile(r"\(\s*atkarpa\s+nuo\b"), "(nuo"),
    # A garden community: 'sodų bendrija "Prabauda"', 'Sodų bendrijos „Dubysa“ ir „Reizgupis“',
    # 'sodų bedrija "Rakava"'. The register has no place of their names: they are reported, not
    # read as the village's or the town's Sodų g.
    (re.compile(r"\bsod(?:ų|ininkų)\s+be(?:n)?drij\w*", re.I), "SB"),
)


class Routes(aratc.Routes):
    """Reads the places of the routes, as aratc.Routes reads those of Alytus county: the
    settlements of the section of an eldership ("Betygalos sen.: Armonų k., Betygalos mstl.,
    ..."), and the streets of a town in the section of its eldership ("Raseinių miesto sen.:
    Aguonų g., Bažnyčios g. (nuo Kosmonautų g. iki Vilniaus g.), ...").

    No town gets "no pickup" for a street no route names (build_locations): the files list the
    streets of private houses, the shared containers of apartment buildings have no file, and
    nothing says a street has none. The app offers the town's routes instead."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return text

    def section(self, district: str, text: str) -> list[_Stop]:
        """aratc.Routes' section, with the streets of the town of a town's eldership ("Raseinių
        miesto sen.: Aguonų g., ...") read as the town's."""
        if self.town is aratc._NO_TOWN and district.endswith(" miesto"):
            towns = [
                s
                for s in self.places[self.municipality.label]
                if s.district == district and s.abbr == "m."
            ]
            self.town = towns[0] if len(towns) == 1 else aratc._NO_TOWN
        return super().section(district, text)


PROVIDER = Provider(
    id="raseiniai",
    name=COMPANY,
    url=PAGE_URL,
    elderships=ELDERSHIPS,
    kinds=("household", "packaging", "glass", "green"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.RASEINIAI_MUNICIPALITY,
    snapshot.RASEINIAI_REGISTRY_FILE,
    snapshot.RASEINIAI_ADDRESSES_FILE,
    # 2026: 43 mixed waste routes, 25 packaging and glass routes and 20 green waste routes (the
    # towns and a few villages), which gave a mixed waste schedule to all 554 settlements.
    min_areas={"household": 30, "packaging": 18, "glass": 18, "green": 12},
    min_household_places=450,
    # About 15,900 addresses in 2026.
    min_address_points=11_000,
    label=LABEL,
    file_kinds={"packaging": ("packaging", "glass")},
)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page; `group` is its eldership (register name), "" for the green waste file
    of the municipality, so each eldership's files run out on their own (build.current_rows)."""

    year: int | None = None


class _Links(HTMLParser):
    """The page's links, with their texts and the heading above them: the text of the last
    paragraph without a link ("<p><strong>Pakuočių atliekų surinkimas ...:</strong></p>")."""

    def __init__(self) -> None:
        super().__init__()
        self.base: str | None = None
        self.links: list[tuple[str, str, str]] = []  # (heading, text, href)
        self.heading = ""
        self.paragraph: list[str] | None = None
        self.linked = False  # the paragraph being read has a link
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "base" and attributes.get("href"):
            self.base = attributes["href"]
        elif tag == "p":
            self.paragraph, self.linked = [], False
        elif tag == "a":
            self.href, self.text = attributes.get("href") or "", []
            self.linked = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            self.links.append((self.heading, clean_text("".join(self.text)), self.href))
            self.href = None
        elif tag == "p" and self.paragraph is not None:
            text = clean_text("".join(self.paragraph))
            if text and not self.linked:
                self.heading = text
            self.paragraph = None

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)
        if self.paragraph is not None:
            self.paragraph.append(data)


def _years(text: str) -> set[int]:
    return {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}


def _eldership(text: str) -> str | None:
    """The register's eldership a link or a heading names: "Betygalos seniūnija", "Raseinių
    miesto seniūnija", "ARIOGALOS M. SENIŪNIJA", "RASEINIŲ MIESTO SENIŪNIJA:"."""
    match = re.fullmatch(
        r"(?P<name>\w+)\s+(?:(?P<town>m\.|miesto)\s+)?seniūnija\s*:?", clean_text(text), re.I
    )
    if not match:
        return None
    key = fold(match["name"]) + (" miesto" if match["town"] else "")
    return next((e for e in ELDERSHIPS if fold(e) == key), None)


def _file_kind(heading: str, text: str) -> Kind | None:
    """By the link's text ("Biologiškai skaidžių atliekų surinkimo grafikas ..."), or the
    heading of its list ("Mišrių komunalinių atliekų surinkimas ...", "Pakuočių atliekų
    surinkimas ..."). Bulky and hazardous waste ("Specifinių atliekų ...") isn't read."""
    own = fold(text)
    if "specifin" in own or "gabarit" in own or "taisykl" in own:
        return None
    if "biolog" in own or "skaidz" in own or "zaliuj" in own:
        return "green"
    if _eldership(text) is None:
        return None
    above = fold(heading)
    if "misri" in above or "komunalin" in above:
        return "household"
    if "pakuo" in above:
        return "packaging"
    return None


def find_files(html: str, page_url: str = PAGE_URL) -> list[ScheduleFile]:
    """The PDFs of the page by the texts of their links and headings. The links are relative to
    the page's <base> (https://www.rkp.lt/), and written with spaces and letters as they are."""
    collector = _Links()
    collector.feed(html)
    base = urljoin(page_url, collector.base) if collector.base else page_url
    files: list[ScheduleFile] = []
    for heading, text, href in collector.links:
        url = urljoin(base, href)
        parts = urlsplit(url)
        path = unquote(parts.path)
        kind = _file_kind(heading, text)
        if not path.lower().endswith(".pdf") or kind is None:
            continue
        url = urlunsplit(parts._replace(path=quote(path, safe="/")))
        if any(f.url == url for f in files):
            continue
        years = _years(f"{path} {text}")
        files.append(
            ScheduleFile(
                kind=kind,
                url=url,
                file_name=PurePosixPath(path).name,
                group="" if kind == "green" else _eldership(text) or "",
                year=years.pop() if len(years) == 1 else None,
            )
        )
    return files


def _title_year(pdf) -> int | None:
    """The year of the workbook a PDF was printed from, in its title ("Kopija 2026 metų UAB RKP
    atliekų surinkimo grafikas.xlsx")."""
    title = pdf.metadata.get("Title") or ""
    years = _years(title.decode("latin-1") if isinstance(title, bytes) else str(title))
    return years.pop() if len(years) == 1 else None


def pdf_year(content: bytes) -> int | None:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return _title_year(pdf)


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Per eldership and kind, the files of this year and later; if there are none, the newest
    one. Of two for one year, the one linked last. Every eldership must have its mixed waste and
    packaging files, and the municipality its green waste file."""
    selected: list[ScheduleFile] = []
    warnings = [
        f"{f.file_name}: no year in its folder or title; not read" for f in files if not f.year
    ]
    groups: dict[tuple[Kind, str], list[ScheduleFile]] = defaultdict(list)
    for file in files:
        if file.year:
            groups[(file.kind, file.group)].append(file)
    for (kind, group), mine in sorted(groups.items()):
        running = [f for f in mine if f.year >= today.year] or [
            f for f in mine if f.year == max(g.year for g in mine)
        ]
        if today.year not in {f.year for f in running}:
            warnings.append(f"{group or LABEL} {kind}: no schedule for {today.year} on the page")
        for year in sorted({f.year for f in running}):
            *older, newest = [f for f in running if f.year == year]
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer {kind} schedule for {year}"
                for f in older
            ]
            selected.append(newest)
    missing = [
        f"{eldership} {kind}"
        for eldership in sorted(ELDERSHIPS)
        for kind in ("household", "packaging")
        if not any(f.group == eldership and f.kind == kind for f in selected)
    ]
    if not any(f.kind == "green" for f in selected):
        missing.append(f"{LABEL} green")
    if missing:
        raise build.ValidationError(f"no schedule found on the page for {', '.join(missing)}")
    return selected, warnings


def download(
    today: date, keep_days: int, tolerant: bool = False
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files in force. `tolerant`: a file that can't be downloaded is passed on empty, and
    keeps its rows of yesterday's data (parse_or_keep)."""
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files = find_files(html)
    fetched: dict[str, bytes] = {}
    warnings: list[str] = []

    def get(file: ScheduleFile) -> bytes:
        if file.url not in fetched:
            try:
                fetched[file.url] = http.get(file.url, timeout=60)
            except OSError as error:
                if not tolerant:
                    raise
                warnings.append(f"{file.file_name}: couldn't be downloaded ({error})")
                fetched[file.url] = b""
        return fetched[file.url]

    for file in files:
        if file.year is None and (content := get(file)):
            # A file put outside the folder of its year: the year of its workbook.
            file.year = pdf_year(content)
    selected, select_warnings = select_files(files, today)
    return [(f, get(f)) for f in selected], warnings + select_warnings


# --- the blocks ------------------------------------------------------------------

# The days of a month's cell: "14", "08", "14;28", "2; 16".
_DAYS = re.compile(r"\d{1,2}(?:[;,]\d{1,2})*[;,]?")
# A place or a street with its type ("Armonų k.,", "Dvarviečių vs.", "Aguonų g.,"), or a garden
# community: a line of places, never a label of a row of dates.
_PLACE_WORD = re.compile(rf"\b(?:k|vs|mstl|m|{_STREET_TYPES})\.|bendrij", re.I)
# Titles above the blocks (folded): "Biologiškai skaidžių atliekų surinkimo grafikas".
_TITLE = re.compile(r"\bgrafikas\b")
# A row's waste type by the words of its label (folded).
_ROW_WORDS: tuple[tuple[Kind, tuple[str, ...]], ...] = (
    ("glass", ("stikl",)),
    ("packaging", ("plastik", "kartono", "metalo", "popier")),
    ("household", ("misri", "komunalin")),
    ("green", ("biolog", "skaidz")),
)


@dataclass
class _Line:
    top: float
    bottom: float
    words: list[dict]

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2


def _lines(page) -> list[_Line]:
    """The page's words in lines, top to bottom. The dates of a row aren't all at one height
    (282.8 and 283.2 next to a label at 281.2), the lines of a label and the dates next to it
    are 5 points apart or more."""
    lines: list[_Line] = []
    last = -1e9  # the top of the last word
    for word in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if lines and word["top"] - last <= 2.5 and word["top"] - lines[-1].top <= 4:
            lines[-1].words.append(word)
            lines[-1].bottom = max(lines[-1].bottom, word["bottom"])
        else:
            lines.append(_Line(word["top"], word["bottom"], [word]))
        last = word["top"]
    for line in lines:
        line.words.sort(key=lambda w: w["x0"])
    return lines


@dataclass
class _Columns:
    """A row of months ("Mėnuo Sausis ... Gruodis"): where each month's column is."""

    left: float  # where the first month's column starts; the labels are left of it
    edges: list[float]  # the borders between the months' columns, and the last one's end

    def month(self, x: float) -> int | None:
        """The month of the column at `x`; None left of the months."""
        if x < self.left:
            return None
        for month, edge in enumerate(self.edges, start=1):
            if x < edge:
                return month
        raise ValueError(f"a word right of December, at {x:.0f}")


def _columns(line: _Line, where: str) -> _Columns | None:
    found = [
        (w, aratc.MONTHS[fold(w["text"])]) for w in line.words if fold(w["text"]) in aratc.MONTHS
    ]
    if len(found) < 6:
        return None
    months = [month for _, month in found]
    if months != list(range(1, 13)):
        raise ValueError(f"{where}: months {months}")
    others = [fold(w["text"]) for w in line.words if fold(w["text"]) not in aratc.MONTHS]
    if others != ["menuo"]:
        raise ValueError(f"{where}: {others} next to the months")
    centres = [(w["x0"] + w["x1"]) / 2 for w, _ in found]
    width = (centres[-1] - centres[0]) / 11
    edges = [(a + b) / 2 for a, b in zip(centres, centres[1:], strict=False)]
    return _Columns(found[0][0]["x0"] - 2, [*edges, centres[-1] + width / 2])


@dataclass
class _Block:
    """A route: its places, and its rows of dates with the words of their labels."""

    eldership: str | None  # of the heading above it
    places: str
    where: str
    columns: _Columns
    rows: list[tuple[float, dict[int, list[int]], list[str]]] = field(default_factory=list)
    labels: list[tuple[float, str]] = field(default_factory=list)  # lines of labels only

    def add(self, line: _Line) -> bool:
        """Reads a line of the block: False if it isn't one (the next route's places)."""
        if _PLACE_WORD.search(line.text):
            return False
        labels: list[str] = []
        cells: dict[int, list[str]] = defaultdict(list)
        for word in line.words:
            month = self.columns.month((word["x0"] + word["x1"]) / 2)
            if month is None:
                labels.append(word["text"])
            elif re.fullmatch(r"[\d;,]+", word["text"]):
                cells[month].append(word["text"])
            else:
                return False
        if not cells:
            self.labels.append((line.middle, " ".join(labels)))
            return True
        days: dict[int, list[int]] = {}
        for month, texts in cells.items():
            text = "".join(texts)
            if not _DAYS.fullmatch(text):
                raise ValueError(f"{self.where}: not days: {text!r}")
            days[month] = [int(d) for d in re.findall(r"\d+", text)]
        self.rows.append((line.middle, days, labels))
        return True

    def dates(self, year: int, allowed: tuple[Kind, ...]) -> dict[Kind, set[date]]:
        """The dates of each waste type: a row's is the one its label names, the label on its
        line and the lines of labels nearest to it ("Plastiko, kartono," above the dates,
        "metalo pakuotės" below)."""
        if not self.rows:
            raise ValueError(f"{self.where}: places without dates: {self.places[:80]!r}")
        words = [list(labels) for _, _, labels in self.rows]
        for middle, text in self.labels:
            nearest = min(range(len(self.rows)), key=lambda i: abs(self.rows[i][0] - middle))
            words[nearest].append(text)
        result: dict[Kind, set[date]] = defaultdict(set)
        for (_, days, _), label in zip(self.rows, words, strict=True):
            folded = fold(" ".join(label))
            kinds = {kind for kind, stems in _ROW_WORDS if any(s in folded for s in stems)}
            if not kinds and len(allowed) == 1:
                kinds = set(allowed)  # a row without a label: the file's waste type
            if len(kinds) != 1 or not kinds <= set(allowed):
                raise ValueError(f"{self.where}: a row of {sorted(kinds)}: {' '.join(label)!r}")
            kind = kinds.pop()
            for month, numbers in days.items():
                for day in numbers:
                    try:
                        result[kind].add(date(year, month, day))
                    except ValueError as error:
                        raise ValueError(f"{self.where}: day {day} of {year}-{month:02}") from error
        return result


def _blocks(pdf, name: str) -> list[_Block]:
    """The routes of a file. Strict: months out of order, a cell of a month that isn't days,
    places without dates, dates without places and a file without a block raise ValueError."""
    blocks: list[_Block] = []
    block: _Block | None = None
    eldership: str | None = None  # of the last heading
    pending: list[str] = []  # lines of places, until the months under them
    for page in pdf.pages:
        where = f"{name} page {page.page_number}"
        for line in _lines(page):
            if block and block.add(line):
                continue
            block = None
            text = clean_text(line.text)
            if (found := _eldership(text)) or re.search(r"seniūnija\s*:?$", text, re.I):
                if not found:
                    raise ValueError(f"{where}: an eldership the register doesn't have: {text!r}")
                if pending:
                    raise ValueError(f"{where}: places without dates: {pending[0][:80]!r}")
                eldership = found
                continue
            columns = _columns(line, where)
            if columns:
                if not pending:
                    raise ValueError(f"{where}: months without places above them")
                block = _Block(eldership, clean_text(" ".join(pending)), where, columns)
                blocks.append(block)
                pending = []
            elif not _TITLE.search(fold(text)):
                pending.append(text)
    if pending:
        raise ValueError(f"{name}: places without dates: {pending[0][:80]!r}")
    if not blocks:
        raise ValueError(f"{name}: no schedule found")
    return blocks


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The schedules of a file's routes: one per waste type of a route, named after the route's
    eldership and places ("Betygalos sen.: Armonų k., ..."). The year is the file's (its folder),
    which the title of the PDF, if it has one, must agree with. A heading of another eldership
    than the link's, or a waste type the file's kind doesn't have, raises ValueError."""
    if not content:
        raise ValueError(f"{source.file_name}: not downloaded")
    allowed = FILE_KINDS[source.kind]
    year = getattr(source, "year", None)
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        title = _title_year(pdf)
        if year and title and title != year:
            raise ValueError(
                f"{source.file_name}: a file of {year} printed from a {title} workbook"
            )
        year = year or title
        if not year:
            raise ValueError(f"{source.file_name}: no year")
        blocks = _blocks(pdf, source.file_name)
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for block in blocks:
        eldership = block.eldership or source.group
        if source.group and block.eldership and block.eldership != source.group:
            raise ValueError(f"{block.where}: {block.eldership} sen. in the file of {source.group}")
        if not eldership:
            raise ValueError(f"{block.where}: no eldership above {block.places[:60]!r}")
        name = f"{eldership} sen.: {block.places}"
        for kind, dates in sorted(block.dates(year, allowed).items()):
            area = Area(kind=kind, name=name, district=LABEL, dates=dates, provider=PROVIDER.id)
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{block.where}: {kind} of {name[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_or_keep(
    source: SourceFile, content: bytes, published: Callable[[], dict] | None = None
) -> ParseResult:
    """parse_file, or for a file that can't be read, its rows of yesterday's data (`published`;
    None: raise instead): those of its kinds and its eldership, or the green waste rows."""
    try:
        return parse_file(source, content)
    except Exception as error:  # any failure of one file must not stop the others
        if published is None:
            raise
        prefix = f"{source.group} sen.:"

        def mine(row: dict) -> bool:
            return row["kind"] in FILE_KINDS[source.kind] and row["name"].startswith(prefix)

        kept = build.published_rows(published(), PROVIDER, mine)
        if not kept:
            raise
        where = f"{source.group} sen." if source.group else LABEL
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} {source.kind} rows of {where} are kept"
            ],
        )


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]],
    registry: Registry,
    today: date,
    municipality: tratc.Municipality = MUNICIPALITY,
) -> list[str]:
    """tratc.combine for each eldership's files on their own (`SourceFile.group`; here also the
    green waste file, jonava.py the town's): next year's files may be posted one eldership at a
    time. Next year's routes of an eldership aren't counted against the municipality's minimum."""
    groups: dict[str, list[tuple[SourceFile, ParseResult]]] = defaultdict(list)
    for file, result in parsed:
        groups[file.group].append((file, result))
    municipality = replace(municipality, min_areas={})
    warnings: list[str] = []
    for files in groups.values():
        warnings += tratc.combine(files, registry, today, municipality)
    return warnings


def source(published: Callable[[], dict] | None = None) -> build.Source:
    """`published`: yesterday's data, for the files that can't be read (None: fail instead)."""
    return build.Source(
        PROVIDER,
        partial(download, tolerant=published is not None),
        partial(parse_or_keep, published=published),
        MUNICIPALITY.min_areas,
        MUNICIPALITY.min_household_places,
        MUNICIPALITY.file_kinds,
        combine,
    )


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
        help="site folder with yesterday's schedule.json, for the files that can't be read",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any file can't be read instead of keeping its published rows",
    )
    args = parser.parse_args(argv)
    published = None if args.strict else args.published
    return run(args.out, args.keep_days, published, MUNICIPALITY, source)


def run(
    out: Path,
    keep_days: int,
    published_url: str | None,
    municipality: tratc.Municipality,
    make_source: Callable[[Callable[[], dict] | None], build.Source],
) -> int:
    """Builds one provider's folder (raseiniai, jonava): schedule.json and addresses.json. With
    `published_url`, files that can't be read keep their rows of the data published there, and
    a build that fails keeps its whole part; without, any failure raises. Returns 1 when the
    build fails without data to keep."""
    loader = cache(build.load_published(published_url)) if published_url else None
    name, code = municipality.register
    registry, registry_note = build.live_or_snapshot(
        f"Address Register ({municipality.label})",
        partial(address_register.fetch, name),
        partial(snapshot.load_registry, municipality.registry_file),
    )
    points, points_note = build.live_or_snapshot(
        f"Address points ({municipality.label})",
        partial(address_points.fetch, code),
        partial(snapshot.load_points, municipality.addresses_file),
    )
    try:
        results = build.build_parts(
            (make_source(loader),), registry, date.today(), keep_days, loader
        )
        parts = [(r.provider, r.part) for r in results if r.part]
        if not parts:
            raise build.ValidationError(f"{municipality.label}: no data to publish")
        dataset = build.merge_parts(parts, municipality.provider.url)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < municipality.min_address_points:
            raise build.ValidationError(
                f"{municipality.label}: only {len(addresses['points'])} address points"
            )
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    for r in results:
        if r.error:
            # An annotation on the workflow run.
            print(
                f"::warning::The {municipality.label} build failed; the data published on "
                f"{r.part['generatedAt'][:10]} is kept. {r.error}"
            )
    out.mkdir(parents=True, exist_ok=True)
    for file_name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (out / file_name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    notes = [n for n in (registry_note, points_note) if n]
    build.write_summary(dataset, results, notes, municipality.label, f"{out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Jurbarko rajonas: schedules published by the regional waste centre of Tauragė county, UAB
„Tauragės regiono atliekų tvarkymo centras“. Mixed and green waste are collected by UAB
„Ecoservice“, packaging and glass by UAB „Jurbarko komunalininkas“ (named in the files).

Its page lists the schedules of four municipalities (Tauragės r., Jurbarko r., Šilalės r. and
Pagėgių sav.), PDFs titled by municipality and waste type, under a heading with the year; the
year is also in the files' names and titles ("... GRAFIKAS 2026 M."). Each municipality lays its
tables out in its own way. Only Jurbarko r. is read so far; another one is a `Municipality`
in MUNICIPALITIES, and a parser if its tables differ.

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

Writes <out>/schedule.json and <out>/addresses.json, in the format of the Vilniaus r. files.
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
from functools import partial
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
from .locations import Index, SectionRoutes
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold

PAGE_URL = "https://www.uabtratc.lt/atlieku-surinkimo-grafikai/"
# The waste types in the texts of the links (folded), and the schedules a file of each has.
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


JURBARKAS = Municipality(
    provider=Provider(
        id="jurbarkas",
        name="UAB „Tauragės regiono atliekų tvarkymo centras“",
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
)
MUNICIPALITIES = {"jurbarkas": JURBARKAS}


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
        kind = next((k for word, k in LINK_KINDS if word in folded), None)
        if kind is None or any(word in folded for word in NOT_SCHEDULES):
            continue
        if all(f.url != url for f, _ in files):
            name = file_name(url)
            year = _year_in(name) or _year_in(text) or heading_year
            files.append((SourceFile(kind=kind, url=url, file_name=name), year))
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
    last, or linked last."""
    selected: list[SourceFile] = []
    warnings = [
        f"{f.file_name}: no year in its name, link or heading; not read" for f, y in files if not y
    ]
    for kind in sorted({f.kind for f, _ in files}):
        mine = [(f, y) for f, y in files if f.kind == kind and y]
        running = [(f, y) for f, y in mine if y >= today.year]
        if not running and mine:
            newest = max(y for _, y in mine)
            running = [(f, y) for f, y in mine if y == newest]
        if mine and today.year not in {y for _, y in running}:
            warnings.append(f"no {kind} schedule for {today.year} on the page")
        for year in sorted({y for _, y in running}):
            same = [f for f, y in running if y == year]
            newest = max(enumerate(same), key=lambda item: (_uploaded(item[1]), item[0]))[1]
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer {kind} schedule for {year}"
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

    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for table in tables:
        where = f"{source.file_name} page {table.page}"
        if not table.dates:
            raise ValueError(f"{where}: a table without dates")
        name = table.places
        if not name:
            raise ValueError(f"{where}: dates without places")
        for kind, dates in table.dates.items():
            area = Area(kind=kind, name=name, provider=municipality.provider.id, dates=set(dates))
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
    in them raise ValueError."""
    reader = SectionRoutes(Index(registry), municipality.provider, defaultdict(dict))
    warnings: list[str] = []
    by_kind: dict[Kind, dict[int, list[tuple[ParseResult, Area]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for _, result in parsed:
        for area in result.areas:
            by_kind[area.kind][min(area.dates).year].append((result, area))
    for kind, years in by_kind.items():
        started = [year for year in years if year <= today.year]
        base = max(started) if started else min(years)
        current: dict[frozenset, list[Area]] = defaultdict(list)
        for _, area in years[base]:
            current[reader.signature(area)].append(area)
        for year in sorted(years):
            if year == base:
                continue
            minimum = municipality.min_areas.get(kind, 0)
            if year > base and len(years[year]) < minimum:
                raise ValueError(
                    f"only {len(years[year])} {kind} routes in the {year} file "
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
                        f"{kind}: the {year} route {area.name[:60]!r} doesn't match one "
                        f"{base} route; its dates are left out until {year}"
                    )
                result.areas.remove(area)
            if year > base:
                warnings += [
                    f"{kind}: the {base} route {area.name[:60]!r} has no dates for {year}"
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
        FILE_KINDS,
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
        "--municipality", choices=sorted(MUNICIPALITIES), default="jurbarkas", help="which one"
    )
    args = parser.parse_args(argv)
    municipality = MUNICIPALITIES[args.municipality]

    name, code = municipality.register
    registry, registry_note = build.live_or_snapshot(
        "Address Register",
        partial(address_register.fetch, name),
        partial(snapshot.load_registry, municipality.registry_file),
    )
    points, points_note = build.live_or_snapshot(
        "Address points",
        partial(address_points.fetch, code),
        partial(snapshot.load_points, municipality.addresses_file),
    )
    try:
        results = build.build_parts(
            (source(municipality),), registry, date.today(), args.keep_days, None
        )
        dataset = build.merge_parts([(r.provider, r.part) for r in results], PAGE_URL)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < municipality.min_address_points:
            raise build.ValidationError(f"only {len(addresses['points'])} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name_, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name_).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    notes = [n for n in (registry_note, points_note) if n]
    title, file_name_ = municipality.title, f"{municipality.folder}/schedule.json"
    build.write_summary(dataset, results, notes, title, file_name_)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

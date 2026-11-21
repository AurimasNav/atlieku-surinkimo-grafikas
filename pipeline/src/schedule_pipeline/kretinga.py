"""Kretingos rajonas: the schedules of SĮ „Kretingos komunalininkas“, the municipal company that
collects the waste of the whole municipality (kretkom.lt).

Its page links a PDF per waste type and period, made in Word, described by the link's text (or
its title), with the period in it or in the file's name:

    2026 m. Mišrių komunalinių atliekų išvežimo grafikas (01-06 mėn.)    mixed waste, and
    2026 m. Mišrių komunalinių atliekų išvežimo grafikas (07-12 mėn.)    the next half year
    2026 m. Stiklo pakuočių ir visų pakuočių, išskyrus stiklo, ...       packaging and glass
    2026 m. Maisto atliekų išvežimo grafikas (01-12 mėn.)                Kretinga's food waste
    2026 m. Žaliųjų–biriųjų atliekų išvežimo grafikas                    and green waste ("...
                                                                         2026 m- 04-11 mėn_.pdf")

Bulky waste, branches, and where the textile and cooking oil containers stand aren't read.

The mixed and packaging files have a table per route: its places, a row of months, and a row
of days per waste type ("Mišrios komunalinės atliekos"; "Visų pakuočių, išskyrus stiklo,
atliekos" and "Stiklo pakuočių atliekos"):

    1 MARŠRUTAS. Kretingos m gatvės: J. Basanavičiaus g., ..., Palangos g. 1–16, ...
    Kaimai: Kretingsodis, Ankštakiai, ..., Kretingos miesto daugiabučiai.
                                    | Liepa  | Rugpjūtis | Rugsėjis | ...
    Mišrios komunalinės atliekos    | 13, 27 | 10, 24    | 7, 21    | ...

The food and green waste files have a row per route, its days under months written top to
bottom or bottom to top. The tables are read with pdfplumber's table finder, without the
2-point letters of an empty line some routes have. Strict: a cell of days that isn't a list of
days, a day the month doesn't have, months other than the title's, a waste type the file
shouldn't have, routes out of order and mixed waste dates that mostly miss one working day (the
wrong year or months) raise.

Mixed waste comes half a year at a time, the other kinds a year (green waste a season). Every
file that still has dates to publish is read, so the next half year's file is read as soon as
the page links it; until it starts, its routes continue those in force that cover the same
places (combine). When a period ends and nothing newer is linked, its routes keep their last
dates (build.current_rows), with a warning.

The places are read by Routes. Writes <out>/schedule.json and <out>/addresses.json, in the
format of the Vilniaus r. files.
Run: python -m schedule_pipeline.kretinga --out ../site/kretingos-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .dates import WEEKDAY_NAMES, month_end
from .locations import (
    _UPPER,
    _WORD,
    Clause,
    Index,
    SectionRoutes,
    _common_prefix,
    _near,
    _one_off,
    _Stop,
    _typo,
    split_places,
    variant_key,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold
from .sratc import _continue

PAGE_URL = "https://www.kretkom.lt/atlieku-isvezimo-grafikai/"
NAME = "SĮ „Kretingos komunalininkas“"
MUNICIPALITY = "Kretingos r."  # every row's `district`
TOWN = "Kretinga"


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page, with the period its link's text or name gives: a year, and months
    if it names them."""

    year: int = 0
    months: tuple[int, int] | None = None

    @property
    def start(self) -> date:
        return date(self.year, (self.months or (1, 12))[0], 1)

    @property
    def end(self) -> date:
        return month_end(self.year, (self.months or (1, 12))[1])


class _Links(HTMLParser):
    """The page's links: (href, text, title)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []
        self._open: tuple[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self._open = (attributes["href"] or "", attributes.get("title") or "")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._open:
            href, title = self._open
            self.links.append((href, clean_text("".join(self._text)), clean_text(title)))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open:
            self._text.append(data)


# The waste type of a file, by its link's text, then its name (folded). Bulky waste ("Didžiųjų
# atliekų"), branches ("Šakų") and the places of containers ("Tekstilės", "kepimo aliejaus")
# aren't schedules of a container at the house: not read.
FILES: tuple[tuple[re.Pattern[str], Kind | None], ...] = (
    (re.compile(r"\bdidz|\bdidel|\bsaku\b|\btekstil|\baliej|\bvietos\b|\bvietu\b"), None),
    (re.compile(r"\bmisri"), "household"),
    (re.compile(r"\bpakuoc|\bstikl"), "packaging"),
    (re.compile(r"\bmaist"), "food"),
    (re.compile(r"\bzali"), "green"),
)
LABELS: dict[Kind, str] = {
    "household": "mixed waste",
    "packaging": "packaging",
    "food": "food waste",
    "green": "green waste",
}
# The kinds the page must have: without them the build fails, and yesterday's data is kept.
REQUIRED: tuple[Kind, ...] = ("household", "packaging")
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}


def file_name(url: str) -> str:
    return PurePosixPath(unquote(urlsplit(url).path)).name


# The months' names as their stems, folded: "balandžio", "lapkričio", "Gegužė".
_MONTH_STEMS = {
    stem: number
    for number, stem in enumerate(
        "saus vasar kov baland geguz birz liep rugpj rugs spal lapkr gruod".split(), start=1
    )
}


def _month_word(word: str) -> int | None:
    return next((n for stem, n in _MONTH_STEMS.items() if word.startswith(stem)), None)


def period(text: str) -> tuple[int | None, tuple[int, int] | None]:
    """The year and months a link's text, a file's name or a title gives: "2026 m. ... (07-12
    mėn.)", "... II pusmetis", "2026 m. balandžio–lapkričio mėn."; None for what it doesn't
    name."""
    folded = fold(text.replace("_", " "))  # "... 04-11 mėn_.pdf"
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", folded)}
    year = years.pop() if len(years) == 1 else None
    if match := re.search(r"\b(\d{1,2}) (\d{1,2}) men\b", folded):
        return year, (int(match[1]), int(match[2]))
    if (match := re.search(r"\b([a-z]+) ([a-z]+) men\b", folded)) and (
        (first := _month_word(match[1])) and (last := _month_word(match[2]))
    ):
        return year, (first, last)
    if re.search(r"\bii pusmetis\b", folded):
        return year, (7, 12)
    if re.search(r"\bi pusmetis\b", folded):
        return year, (1, 6)
    return year, None


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The schedules the page links, in the order of the page, with the periods of their links
    (else their names); and warnings about PDFs of no kind we know or without a year."""
    collector = _Links()
    collector.feed(html)
    files: list[ScheduleFile] = []
    warnings: list[str] = []
    for href, text, title in collector.links:
        url = urljoin(page_url, href)
        name = file_name(url)
        if not name.lower().endswith(".pdf") or any(f.url == url for f in files):
            continue
        described = text or title
        kind, known = None, False
        for words in (fold(described), fold(name)):
            for pattern, found in FILES:
                if pattern.search(words):
                    kind, known = found, True
                    break
            if known:
                break
        if not known:
            if "grafik" in fold(f"{described} {name}"):
                warnings.append(f"{name} ({described!r}): a schedule of no kind we read")
            continue
        if kind is None:
            continue
        (year, months), (name_year, name_months) = period(described), period(name)
        year, months = year or name_year, months or name_months
        if year is None:
            warnings.append(f"{name} ({described!r}): no year in its link or name; not read")
            continue
        files.append(ScheduleFile(kind, url, name, year=year, months=months))
    return files, warnings


def select_files(
    files: list[ScheduleFile], today: date, keep_days: int = 31
) -> tuple[list[ScheduleFile], list[str]]:
    """Of each kind, the files with dates still to publish (their period ends at most
    `keep_days` before today), so the next period's file is read as soon as it's linked; if
    none runs to today, also the latest one, whose routes keep their last dates. Of two files
    for the same period (a correction), the one linked last."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    cutoff = today - timedelta(days=keep_days)
    for kind, label in LABELS.items():
        mine: dict[tuple[date, date], ScheduleFile] = {}
        for file in (f for f in files if f.kind == kind):
            if (older := mine.get((file.start, file.end))) is not None:
                warnings.append(
                    f"{older.file_name}: not read, {file.file_name} is a newer {label} schedule "
                    f"for {file.start} - {file.end}"
                )
            mine[(file.start, file.end)] = file
        if not mine:
            if kind in REQUIRED:
                raise build.ValidationError(f"no {label} schedule on the page")
            warnings.append(f"no {label} schedule on the page")
            continue
        running = [f for f in mine.values() if f.end >= cutoff]
        latest = max(mine.values(), key=lambda f: f.end)
        if not any(f.end >= today for f in running) and latest not in running:
            running.append(latest)
        selected += sorted(running, key=lambda f: f.start)
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    found, warnings = find_files(html)
    chosen, notes = select_files(found, today, keep_days)
    return [(f, http.get(f.url, timeout=120)) for f in chosen], warnings + notes


# --- the tables ------------------------------------------------------------------

MONTHS = {
    fold(name): number
    for number, name in enumerate(
        "Sausis Vasaris Kovas Balandis Gegužė Birželis Liepa Rugpjūtis Rugsėjis Spalis Lapkritis "
        "Gruodis".split(),
        start=1,
    )
}
# A route's first cell: "1 MARŠRUTAS. Kretingos m gatvės: ...".
_ROUTE = re.compile(r"^\s*(\d+)\s*MARŠRUTAS\b", re.I)
# The number of a route in a column of its own: "2.".
_NUMBER = re.compile(r"^\s*(\d+)\s*\.?\s*$")
# The waste type of a row of days.
ROW_KINDS: tuple[tuple[re.Pattern[str], Kind], ...] = (
    (re.compile(r"^misrios komunalines atliekos$"), "household"),
    (re.compile(r"^visu pakuociu isskyrus stiklo atliekos$"), "packaging"),
    (re.compile(r"^stiklo pakuociu atliekos$"), "glass"),
)
# Shared containers ("bendro naudojimo konteineriai", emptied "Pagal poreikį"): not read.
_SHARED = re.compile(r"bendro naudojimo|pagal poreik")
_DAYS = re.compile(r"\d{1,2}(?:\s*,\s*\d{1,2})*\s*,?")
# Routes in a file of each kind, at least: the 2026 files had 10 mixed waste routes, 15 of
# packaging and glass, one of food waste (and one of shared containers) and 3 of green waste.
MIN_ROUTES: dict[Kind, int] = {"household": 8, "packaging": 10, "food": 1, "green": 2}
# Of a route's mixed waste dates, at least this share on one working day (holidays move a
# few): days in the wrong months fall on other weekdays, and those of the wrong year on the next
# or the last weekday, a Saturday or a Sunday for some route.
SAME_WEEKDAY = 0.75


def _month(cell: str) -> int | None:
    """A month's name in a column title, written across or top to bottom ("S/a/u/s/i/s"), or
    bottom to top ("s/i/d/n/a/l/a/B")."""
    letters = re.sub(r"\s+", "", cell)
    return MONTHS.get(fold(letters)) or MONTHS.get(fold(letters[::-1]))


@dataclass
class _Route:
    number: int
    text: str
    dates: dict[Kind, set[date]] = field(default_factory=dict)


def _tables(content: bytes) -> tuple[str, list[list[str]]]:
    """The text above the first table (its title) and the rows of every table, page by page.
    Letters written across that are smaller than 4 points (an empty line under some routes)
    aren't read; the size of a letter written top to bottom is its width (and pdfplumber calls
    it `upright` too: told apart by its matrix)."""
    title, rows = "", []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for number, page in enumerate(pdf.pages):
            page = page.filter(
                lambda obj: (
                    obj.get("object_type") != "char"
                    or obj.get("size", 0) >= 4
                    or abs(obj["matrix"][1]) + abs(obj["matrix"][2]) > 0.01
                )
            )
            tables = page.find_tables()
            if number == 0:
                top = min((t.bbox[1] for t in tables), default=page.height)
                title = clean_text(page.crop((0, 0, page.width, top)).extract_text())
            for table in tables:
                rows += [[clean_text(cell) for cell in row] for row in table.extract()]
    return title, rows


def _days(cell: str, year: int, month: int, where: str) -> set[date]:
    if not cell:
        return set()
    if not _DAYS.fullmatch(cell):
        raise ValueError(f"{where}: unrecognised days {cell!r}")
    try:
        return {date(year, month, int(day)) for day in re.findall(r"\d+", cell)}
    except ValueError as error:
        raise ValueError(f"{where}: {error} ({cell!r} in month {month})") from error


def parse_routes(
    source: SourceFile, content: bytes
) -> tuple[int, tuple[int, int] | None, list[_Route]]:
    """The year and months of the file's title (None if it names none) and its routes."""
    where = source.file_name
    title, rows = _tables(content)
    year, titled = period(title)
    if year is None:
        raise ValueError(f"{where}: no year in the title {title[:80]!r}")
    routes: list[_Route] = []
    columns: dict[int, int] | None = None
    current: _Route | None = None
    for line, cells in enumerate(rows, start=1):
        at = f"{where} row {line}"
        months = {i: m for i, cell in enumerate(cells) if cell and (m := _month(cell))}
        if len(months) >= 2:
            found = list(months.values())
            first, last = titled or (found[0], found[-1])
            if found != list(range(first, last + 1)):
                raise ValueError(f"{at}: months {found}, the title says {first}-{last}")
            columns = months
            continue
        filled = [cell for cell in cells if cell]
        if not filled:
            continue
        if len(filled) == 1 and cells[0]:
            # A route's places across the table, or their rest on the next page.
            if match := _ROUTE.match(cells[0]):
                current = _Route(int(match[1]), cells[0])
                routes.append(current)
            elif current is not None and not current.dates:
                current.text = f"{current.text} {cells[0]}"
            else:
                raise ValueError(f"{at}: text outside a route {cells[0][:60]!r}")
            continue
        if columns is None:
            continue  # the titles over the months ("Eil. Nr.", "MARŠRUTAS", "2026 m.")
        label = " ".join(c for i, c in enumerate(cells) if c and i not in columns)
        days = {month: cells[i] if i < len(cells) else "" for i, month in columns.items()}
        if _SHARED.search(fold(" ".join(filled))):
            current = None
            continue
        kind = next((k for pattern, k in ROW_KINDS if pattern.match(fold(label))), None)
        if kind is None:
            # Food and green waste: a row per route, its number, places and days.
            number, _, text = label.partition(" ")
            if not (match := _NUMBER.match(number)) or not text:
                raise ValueError(f"{at}: unknown row {label[:60]!r}")
            current = _Route(int(match[1]), text)
            routes.append(current)
            kind = source.kind
        elif current is None:
            raise ValueError(f"{at}: days before the first route")
        dates: set[date] = set()
        for month, cell in days.items():
            dates |= _days(cell, year, month, at)
        if kind in current.dates:
            raise ValueError(f"{at}: route {current.number} has two rows of {kind}")
        current.dates[kind] = dates
    return year, titled, routes


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of one file: a row per route and waste type. Strict (see parse_routes): also a
    route without the file's main waste type or with another file's, routes out of order, too
    few routes, a title whose year or months aren't the link's, and mixed waste dates that
    mostly miss one working day raise ValueError."""
    where = source.file_name
    year, titled, routes = parse_routes(source, content)
    linked_year, linked = getattr(source, "year", 0), getattr(source, "months", None)
    if (linked_year and linked_year != year) or (linked and titled and linked != titled):
        raise ValueError(
            f"{where}: the title is for {year} {titled}, the link for {linked_year} {linked}"
        )
    kinds = FILE_KINDS.get(source.kind, (source.kind,))
    numbers = [route.number for route in routes]
    if not numbers or numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError(f"{where}: routes {numbers}")
    readable = [route for route in routes if route.dates]
    if len(readable) < MIN_ROUTES[source.kind]:
        raise ValueError(
            f"{where}: only {len(readable)} routes (expected at least {MIN_ROUTES[source.kind]})"
        )
    areas: list[Area] = []
    for route in readable:
        if not route.dates.get(kinds[0]):
            raise ValueError(f"{where}: no {kinds[0]} dates for route {route.number}")
        if other := sorted(set(route.dates) - set(kinds)):
            raise ValueError(f"{where}: {', '.join(other)} in the {source.kind} file")
        for kind, dates in route.dates.items():
            if not dates:
                continue
            weekdays = Counter(d.weekday() for d in dates)
            weekday, times = weekdays.most_common(1)[0]
            if kind == "household" and (times < SAME_WEEKDAY * len(dates) or weekday > 4):
                raise ValueError(
                    f"{where}: the dates of route {route.number} aren't on one working day: "
                    "the wrong year or months?"
                )
            area = Area(kind, route.text, MUNICIPALITY, provider=PROVIDER_ID, dates=dates)
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekday]
            areas.append(area)
    return ParseResult(areas=areas)


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as Routes reads them.
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "1 MARŠRUTAS.": the route's number.
    (re.compile(r"^\s*\d+\s*MARŠRUTAS\s*\.?\s*", re.I), ""),
    # 'SB ,,Rubuliai“': two commas for an opening quote.
    (re.compile(r",,(?=\w)"), "„"),
    (re.compile(r";"), ","),
    # "SB „Paupys Tarvydai": a quote left open before the next place.
    (re.compile(rf"(\bSB\s*[„“”\"',]*\s*\w[\w-]*)(?![\w“”\"-])\s+(?=[{_UPPER}])"), r"\1“, "),
    # "Kluonaliai (tik ...). Kretingos miesto ...", "Senkai. SB „Paupys“. Darbėnų mstl.": the
    # end of a sentence between two places (not an initial: "S. Įpiltis").
    (re.compile(rf"(?<=[a-ząčęėįšųūž)“”\"]{{2}})\.\s+(?=[{_UPPER}])"), ", "),
)
# "Kaimai:" before the villages.
_VILLAGES = re.compile(r"\bKaimai\s*:", re.I)
# A street, its type and some of its houses: "Palangos g. 1–16", "Palangos g nuo 18", "Taikos
# (tik iki 101)" (the bracket taken off), "Vienkiemio g. t ik 22-68", "Malūno takas", "Kalno".
_STREET = re.compile(
    r"(?P<name>.+?)(?:\s+(?P<type>g|gatvė|al|aklg|akl|skg|sk|tak|takas|pl|a)\b\.?)?"
    r"(?P<houses>\s+(?:t\s?ik\b|nuo\b|iki\b|Nr\.|\s)*\d.*)?"
)
# A settlement and its type: "Darbėnų mstl.", "Salantų miestas", "Kretingsodis".
_PLACE = re.compile(r"(?P<name>.+?)(?:\s+(?P<type>k|km|vs|mstl|mst|m|miestas)\b\.?)?")
_TYPES = {
    "k": ("k.",),
    "km": ("k.",),
    "vs": ("vs.",),
    "mstl": ("mstl.", "m."),
    "mst": ("mstl.", "m."),
    "m": ("m.", "mstl."),
    "miestas": ("m.", "mstl."),
}
# "(Darbėnų sen.)": which of two villages of one name.
_ELDERSHIP = re.compile(rf"({_WORD})\s+sen\b\.?", re.U)
# A garden community: 'SB „Rasa“', 'SB “Draugystė” (tik Gandrų g.)', 'SB ,,Rubuliai“'.
_GARDEN = re.compile(r"^S\s*/?\s*B\b\s*[„“”\"',]*\s*(?P<name>\w[\w-]*)")
_EXCLUDING = re.compile(r"^\s*(?:be|i[sš]+kyrus)\b", re.I)


def _ending(a: str, b: str) -> bool:
    """One word with another ending: "vaineikiai" ~ "vaineikiu", "gencai" ~ "gencu"."""
    n = len(_common_prefix(a, b))
    return n >= 4 and all(len(e) <= 3 and set(e) <= set("aeiouy") for e in (a[n:], b[n:]))


def _same_words(a: str, b: str) -> bool:
    """A name of several words with other endings: "Vaineikiai-Medsėdžiai" and "Genčai
    Medsėdžiai" for the register's Vaineikių and Genčų Medsėdžiai."""
    x, y = a.split(), b.split()
    if len(x) != len(y) or len(x) < 2 or x == y:
        return False
    return all(p == q or _ending(p, q) for p, q in zip(x, y, strict=True))


@dataclass(eq=False)
class _Place(_Stop):
    """What a route says about a settlement. Its streets of which it has some houses are
    shared by the routes that name them (`streets`), and so are those a list of streets left
    out of the rest of a village names with houses ("Padvariai (be Darbėnų pl., ..., Vienkiemio
    g. tik 22-68)": `also`)."""

    also: set[str] = field(default_factory=set)
    # Of villages of one name in two elderships, both, the row not telling which.
    fallback: bool = False

    def clauses(self, area_id: str) -> list[Clause]:
        result = super().clauses(area_id)
        if self.streets is None and self.also:
            result.append(Clause(area_id, set(self.also)))
        for clause in result:
            clause.fallback = self.fallback
        return result


class Routes(SectionRoutes):
    """Reads one route of Kretingos r.: the streets of Kretinga, then the villages:

        Kretingos m gatvės: J. Basanavičiaus g., ..., Palangos g. 1–16, Taikos g. (tik nuo 102)
        Kretingos m.: Užuovėjos, Jablonskio (tik nuo 7 1) g., SB „Žemaitija“.
        Kaimai: Kretingsodis, Ankštakiai, ..., Kadagynai (Darbėnų sen.), Darbėnų mstl., ...
        Kluonaliai (tik Giminių, Svainių, ...), Padvariai (be Darbėnų pl., Palaukės, ...,
        Vienkiemio g. tik 22-68), Vaineikiai-Medsėdžiai, N. Įpiltis, Salantų miestas,
        SB „Minija“, Kretingos, Kartenos ir Salantų miestų daugiabučiai.
        KRETINGOS MIESTO individualios valdos                    the town's private houses

    The villages are nominative (some genitive, with their type), looked up in the whole
    municipality: of two of one name, the one of the eldership in brackets, else the one of the
    eldership most of the row's others are in. "(tik ...)" lists the only streets of a village
    the route serves, "(be ...)" those it doesn't, which go to the routes that name them; some
    houses of a street ("Palangos g. 1–16", "Darbėnų pl. 20-44"): the routes that name it
    share it, and the app asks. A garden community (SB) with a village's name is one more
    choice in that village's street list; the others' places are unknown, and reported. The
    shared containers of apartment buildings ("... daugiabučiai") aren't read.

    No street gets "no pickup": the files list private houses but leave out many streets of
    Kretinga (Genių g., Kalvos g., ...), and say nothing of them. A street of a town or a village
    that no route names is left to the app, which offers the place's routes. A street a route
    leaves out of a village ("be ...") that no route names stays in it, with a warning."""

    towns_by_street: set[int] = set()

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.unknown: list[str] = []
        self.named = None
        self.kind = ""
        self.places = [s for s in index.registry.settlements if s.district in provider.elderships]
        self.town = next(s for s in self.places if s.name == TOWN and s.abbr == "m.")
        self.towns_by_street = set()
        town = re.escape(self.town.genitive)
        # "Kretingos m gatvės:", "Kretingos m.:", "Kretingos miesto gatvės:".
        self.town_mark = re.compile(rf"\b{town}\s+(?:m\b\.?|miesto\b)\s*(?:gatvės\s*)?:", re.I)
        self.whole_town = re.compile(rf"{town}\s+miesto\s+individualios\s+valdos", re.I)
        # "Kretingos, Kartenos ir Salantų miestų daugiabučiai": the towns before such a part.
        self.towns = {fold(s.genitive) for s in self.places if s.abbr in ("m.", "mstl.")}
        # Streets of each kind some route names, per settlement; None before prepare.
        self.listed: dict[str, set[tuple[int, str]]] | None = None

    def prepare(self, areas: list[Area]) -> None:
        """First pass: the streets the routes of each kind name."""
        listed: dict[str, set[tuple[int, str]]] = defaultdict(set)
        for area in areas:
            for settlement, clause in self.clauses(area)[0]:
                listed[area.kind] |= {(settlement.code, key) for key in clause.streets or ()}
        self.listed = listed

    def normalise(self, text: str) -> str:
        text = clean_text(text)
        for written, registered in self.provider.aliases:
            text = text.replace(written, registered)
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return text

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        self.kind = area.kind
        text = self.normalise(area.name)
        if self.whole_town.fullmatch(text.strip(" .")):
            return [(self.town, Clause(area.id, None))], False
        marks = [(m.start(), m.end(), True) for m in self.town_mark.finditer(text)]
        marks += [(m.start(), m.end(), False) for m in _VILLAGES.finditer(text)]
        marks.sort()
        parts = [(text[: marks[0][0]] if marks else text, False)]
        parts += [
            (text[end : marks[i + 1][0] if i + 1 < len(marks) else len(text)], town)
            for i, (_, end, town) in enumerate(marks)
        ]
        stops: list[_Place] = []
        for part, town in parts:
            if part.strip(" ,.;:"):
                stops += self.streets_of_town(part) if town else self.villages(part)
        self.unknown = list(dict.fromkeys(self.unknown))  # "SB „Rasa“, SB „Rasa“"
        return [(s.settlement, c) for s in stops for c in s.clauses(area.id)], False

    def streets_of_town(self, text: str) -> list[_Place]:
        """Streets of Kretinga, with or without their type, some with house numbers."""
        stop = _Place(self.town, streets=set())
        found: list[_Place] = [stop]
        for part in split_places(text):
            if _GARDEN.match(part):
                found += self.garden(part)
                continue
            keys = self.street(self.town, re.sub(r"\([^()]*\)", " ", part))
            if keys:
                stop.streets |= keys
            else:
                self.unknown.append(f"{self.town.genitive} m.: {part[:60]}")
        return [s for s in found if s.streets is None or s.streets]

    def street(self, settlement: Settlement, part: str) -> set[str]:
        match = _STREET.fullmatch(clean_text(part).strip(" ,.;:"))
        if not match:
            return set()
        name, kind = match["name"], match["type"]
        return self.streets(settlement, f"{name} {kind}." if kind else name, name, kind)

    def villages(self, text: str) -> list[_Place]:
        parts: list[str] = []
        for part in split_places(text):
            if "daugiabuc" in fold(part):
                # "Kretingos, Kartenos ir Salantų miestų daugiabučiai": shared containers.
                while parts and fold(parts[-1]) in self.towns:
                    parts.pop()
                continue
            parts.append(part)
        found: list[tuple[list[Settlement], str | None]] = []
        gardens: list[_Place] = []
        for part in parts:
            if _GARDEN.match(part):
                gardens += self.garden(part)
                continue
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0].strip() if rest else None
            eldership = None
            if spec and (match := _ELDERSHIP.fullmatch(spec)):
                eldership = next(
                    (d for d in self.provider.elderships if fold(d) == fold(match[1])), None
                )
                spec = None
            match = _PLACE.fullmatch(head.strip(" ,.:"))
            hits = self.settlements(match["name"], match["type"], eldership) if match else []
            if hits:
                found.append((hits, spec))
            else:
                self.unknown.append(f"{MUNICIPALITY}: {part[:60]}")
        # Of villages of one name, the one of the eldership most of the row's others are in.
        sure = Counter(h[0].district for h, _ in found if len({s.district for s in h}) == 1)
        stops: list[_Place] = []
        for hits, spec in found:
            districts = {s.district for s in hits}
            best = next((d for d, _ in sure.most_common() if d in districts), None)
            if len(districts) > 1 and best:
                hits = [s for s in hits if s.district == best]
            for settlement in hits:
                stop = _Place(settlement, fallback=len(districts) > 1 and not best)
                if spec:
                    self.village_streets(stop, spec)
                stops.append(stop)
        return stops + gardens

    def village_streets(self, stop: _Place, spec: str) -> None:
        """A bracket after a village: the only streets of it the route serves ("tik"), or those
        it doesn't ("be"). A street with house numbers is the route's either way."""
        excluding = bool(_EXCLUDING.match(spec))
        text = re.sub(r"^\s*(?:tik|be|i[sš]+kyrus)\b\s*:?", "", spec, flags=re.I)
        if not excluding:
            stop.streets = set()
        where = f"{stop.settlement.genitive} {stop.settlement.abbr}"
        for item in re.split(r"\s*,\s*|\s+ir\s+", text):
            item = re.sub(r"^\s*(?:be|tik)\s+", "", item, flags=re.I).strip(" .:")
            if not item:
                continue
            keys = self.street(stop.settlement, item)
            houses = bool(re.search(r"\d", item))
            if not keys:
                self.unknown.append(f"{where}: {item[:60]}")
            elif not excluding:
                stop.add(keys, houses=False)
            elif houses:
                stop.also |= keys
            elif self.listed is not None and not all(
                (stop.settlement.code, key) in self.listed[self.kind] for key in keys
            ):
                # Left out of the route, but no route names it: not "no pickup".
                self.unknown.append(f"{where}: {item[:60]} (left out, but no route names it)")
            else:
                stop.excluded |= keys

    def settlements(
        self, name: str, kind: str | None = None, eldership: str | None = None
    ) -> list[Settlement]:
        """The settlements called `name` (nominative or genitive) in the municipality, or in
        `eldership`; also "N. Įpiltis" for Naujoji Įpiltis, other endings ("Akmenaliai",
        "Auksūdis", "Vaineikiai-Medsėdžiai") and typos, if only one name is that close."""
        key = fold(name)
        pool = [s for s in self.places if eldership in (None, s.district)]
        found = [s for s in pool if key in (fold(s.name), fold(s.genitive))]
        if not found:
            # "Akmena" for Akmena I and II.
            found = [s for s in pool if re.fullmatch(re.escape(key) + r" i{1,3}", fold(s.name))]
        if not found and (short := re.fullmatch(r"([a-z]) (\w+)", key)):
            pattern = re.compile(rf"{short[1]}\w* {short[2]}")
            found = [s for s in pool if pattern.fullmatch(fold(s.name))]
        if not found:
            found = [s for s in pool if _same_words(key, fold(s.name))]
        for close in (_near, _one_off, _typo):
            if not found:
                near = [s for s in pool if close(key, fold(s.name)) or close(key, fold(s.genitive))]
                found = near if len({s.name for s in near}) == 1 else []
        if kind:
            typed = (t for a in _TYPES[kind] if (t := [s for s in found if s.abbr == a]))
            found = next(typed, found)
        return found

    def garden(self, part: str) -> list[_Place]:
        """A garden community named after a village ("SB „Rubuliai“"): one more choice in its
        street list. Where the others are, the register doesn't say."""
        match = _GARDEN.match(part)
        name = match["name"] if match else ""
        villages = [s for s in self.places if fold(s.name) == fold(name) and s.abbr == "k."]
        if len(villages) != 1:
            self.unknown.append(f"{MUNICIPALITY}: {part[:60]}")
            return []
        label = f"SB „{name}“"
        key = variant_key(label)
        self.variants[villages[0].code].setdefault(key, label)
        return [_Place(villages[0], streets={key})]


PROVIDER_ID = "kretinga"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=NAME,
    url=PAGE_URL,
    elderships=frozenset(
        {
            "Darbėnų",
            "Imbarės",
            "Kartenos",
            "Kretingos",
            "Kretingos miesto",
            "Kūlupėnų",
            "Salantų miesto",
            "Vydmantų",
            "Žalgirio",
        }
    ),
    reader=Routes,
    kinds=("household", "packaging", "glass", "food", "green"),
)
# Rows of each kind, at least (see MIN_ROUTES). Food and green waste aren't required: the page
# may stop linking a season's file.
MIN_AREAS: dict[Kind, int] = {"household": 8, "packaging": 10, "glass": 10}
# Settlements that must get a mixed waste schedule: 170 of the 194 in November 2026.
MIN_HOUSEHOLD_PLACES = 130
# 22,195 addresses in the Address Register in November 2026.
MIN_ADDRESS_POINTS = 15_000


# --- this period and the next ------------------------------------------------------


def _period(result: ParseResult) -> tuple[date, date]:
    """The months a file's dates fall in, from the first day of the first to the last day of
    the last."""
    dates = [d for a in result.areas for d in a.dates]
    first, last = min(dates), max(dates)
    return first.replace(day=1), month_end(last.year, last.month)


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins the routes of the files of later periods to those of the period in force, in place
    (sratc._continue, as for Radviliškio r.'s quarters): a route of the next half year that
    covers the same places as one in force gives it its dates; the rest wait, with a warning,
    until their period starts. Routes of earlier periods are dropped.

    Files of one kind whose months overlap raise ValueError (select_files reads one file per
    period). A kind whose files have all ended keeps its routes, with their last dates
    (build.current_rows), and a warning; so does a kind with no file for today, whose next one
    has started early. Not green waste, collected from April to November."""
    warnings: list[str] = []
    periods = {id(result): _period(result) for _, result in parsed if result.areas}
    for i, (source, result) in enumerate(parsed):
        for other, later in parsed[i + 1 :]:
            if other.kind != source.kind or not result.areas or not later.areas:
                continue
            (start, end), (other_start, other_end) = periods[id(result)], periods[id(later)]
            if other_start <= end and start <= other_end:
                raise ValueError(
                    f"{source.file_name} ({start} - {end}) and {other.file_name} "
                    f"({other_start} - {other_end}) overlap"
                )
    for kind, label in LABELS.items():
        spans = [periods[id(r)] for s, r in parsed if s.kind == kind and r.areas]
        if kind == "green" or not spans:
            continue
        if (ended := max(end for _, end in spans)) < today:
            warnings.append(f"the {label} schedule ended on {ended}; no newer one is read")
        elif (first := min(start for start, _ in spans)) > today:
            warnings.append(f"no {label} schedule for today; the next starts on {first}")
    groups: dict = defaultdict(lambda: defaultdict(list))
    for _, result in parsed:
        for area in result.areas:
            groups[(MUNICIPALITY, area.kind)][periods[id(result)][0]].append((result, area))
    reader = Routes(Index(registry), PROVIDER, defaultdict(dict))
    return warnings + _continue(groups, reader, lambda start: start <= today, date.isoformat)


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MIN_AREAS,
    MIN_HOUSEHOLD_PLACES,
    FILE_KINDS,
    combine,
)


# --- the output ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    args = parser.parse_args(argv)

    name, code = snapshot.KRETINGOS_MUNICIPALITY
    registry, registry_note = build.live_or_snapshot(
        "Address Register",
        partial(address_register.fetch, name),
        partial(snapshot.load_registry, snapshot.KRETINGOS_REGISTRY_FILE),
    )
    points, points_note = build.live_or_snapshot(
        "Address points",
        partial(address_points.fetch, code),
        partial(snapshot.load_points, snapshot.KRETINGOS_ADDRESSES_FILE),
    )
    try:
        results = build.build_parts((SOURCE,), registry, date.today(), args.keep_days, None)
        dataset = build.merge_parts([(r.provider, r.part) for r in results], PAGE_URL)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < MIN_ADDRESS_POINTS:
            raise build.ValidationError(f"only {len(addresses['points'])} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for out_name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / out_name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    notes = [n for n in (registry_note, points_note) if n]
    title = "Kretingos r. (Kretingos komunalininkas)"
    build.write_summary(dataset, results, notes, title, "kretingos-r/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

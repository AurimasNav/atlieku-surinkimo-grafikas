"""Širvintų rajonas: the schedules of the individual houses whose containers UAB „Ecoservice“
empties, published by the municipality (sirvintos.lt) as PDFs made in Excel: mixed waste on one
page, packaging and glass on another.

    MIXED_PAGE        "Mišrių komunalinių atliekų surinkimo grafikas iš Širvintų rajono gyventojų"
        "INDIVIDUALIŲ VALDŲ MIŠRIŲ KOMUNALINIŲ ATLIEKŲ SURINKIMO GRAFIKAS ŠIRVINTŲ SAVIVALDYBĖ
        2026 m."                                                   June to December 2026
        "ŠIRVINTŲ RAJONO GYVENTOJŲ MIŠRIŲ KOMUNALINIŲ ATLIEKŲ IŠVEŽIMO 2026 M. 04 - 06 MĖN.
        GRAFIKAS"                                                  April to June 2026
    RECYCLABLES_PAGE  "Antrinių žaliavų išvežimo grafikas"
        "2026 metų antrinių žaliavų surinkimo grafikas"           packaging and glass, 2026

The files are found by the texts of their links. Mixed waste comes for periods of their own: May
to April until 2026 ("... 2025 M. 05 MĖN.–2026 M. 04 MĖN. GRAFIKAS", posted in late April), then
April to June 2026 (made on 16 April) and June to December 2026 (made on 16 June, in place of
the last one's June); the page keeps older files linked. A file's period is the months of its
table, which its link names only sometimes (then they must agree). Packaging and glass come a
year at a time, posted in December (the 2026 file was made on 18 December 2025). sirvintos.lt
refuses GitHub's runners (HTTP 403): the daily job then reads the copy of the pages and their
files in pipeline/data (COPY_DIR, save_copy), with a warning that says how old it is, as for
Ukmergės r.

The mixed waste files are a table of routes, in one of two layouts (both read with pdfplumber's
table finder, the letters of a line within 2 points of each other, not 3: the April-June file
has lines of spaces 3 points above its days, "2 5" for 25):

    GRAFIKAS ŠIRVINTŲ SAVIVALDYBĖ 2026 m.         | birželis | liepa | ... | gruodis
    ZIBALŲ SEN. Aukštadvario k., Degsnių k., ...  | 1        | 6     | ... | 7

    Maršruto pavadinimas | Vietovės                          | Balandis | Gegužė | Birželis
    Šešuolėlių I         | ZIBALŲ SEN. Aukštadvario k., ...   | 11       | 4      | 1

The packaging file is a table of places under the rows of their elderships, a row of packaging
("POP/PLAST/M") and one of glass ("STIKLAS") each, under the months "01" to "12". Its places are
read from the positions of the words, not the table finder's cells: it finds no cell for the
last place of Širvintų sen., whose text is taller than its rows. Strict: a month's
cell that isn't days ("-" is none), a day the month doesn't have, a month of mixed waste or
packaging without days, months out of order, a title of another kind or of other years, a row of
no waste type we read, dates without places, places without dates, too few routes and dates that
mostly miss one weekday raise.

The places are read by Routes (ecoservice.Routes for this municipality): sections of elderships
("ZIBALŲ SEN. Aukštadvario k., ..."), the town's streets ("ŠIRVINTŲ MIESTAS Individualios
valdos: Zibalų g. Nr. 19,21, ...", "ŠIRVINTŲ SENIŪNIJA: Širvintų miestas: Ateities g., ..."), and
a whole eldership ("ALIONIŲ SENIŪNIJA: Visa seniūnija, išskyrus Kvakšių k"). No street gets "no
pickup": the files list the streets of private houses, the shared containers of the apartment
buildings have no file, and nothing says a street has none.

Every file that still has dates to publish is read, so the next period's file is read as soon as
the page links it; until its months start, its routes continue those in force that cover the
same places, and from its first month it replaces the last file (combine). When a period ends and
nothing newer is linked, its routes keep their last dates (build.current_rows), with a warning.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.sirvintos --out ../site/sirvintu-r
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber

from . import aratc, build, ecoservice, http, maatc, raseiniai, snapshot
from .dates import WEEKDAY_NAMES, month_end
from .kretinga import _Links, file_name, period
from .locations import _SECTION_ITEM, _WORD, Index, _section_parts, _Stop
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold
from .sratc import _continue
from .tratc import _uploaded

MIXED_PAGE = (
    "https://www.sirvintos.lt/lt/atlieku-tvarkymas/"
    "misriu-komunaliniu-atlieku-surinkimo-grafikas-is-sirvintu-rajono-gyventoju/2998"
)
RECYCLABLES_PAGE = (
    "https://www.sirvintos.lt/lt/viesoji-tvarka-ir-aplinkosauga/atlieku-tvarkymas/"
    "antriniu-zaliavu-isvezimo-grafikas/2332"
)
PAGES = (MIXED_PAGE, RECYCLABLES_PAGE)
NAME = "Širvintų rajono savivaldybė"
LABEL = "Širvintų r."  # every row's `district`
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}
LABELS: dict[Kind, str] = {"household": "mixed waste", "packaging": "packaging"}


# --- the pages ---------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the pages: its link's text, and the first and the last day of the months of its
    table (read after the download: the link names them only sometimes)."""

    text: str = ""
    start: date = date.min
    end: date = date.min


# Files that aren't schedules of the houses' containers, by their links' texts (folded): bulky
# waste, the shared containers of apartment buildings, the semi-underground ones and their
# washing, the cemeteries', textiles, and the local fee.
OTHERS = ("gabarit", "daugiabuc", "pusiau pozemin", "plovim", "kapin", "tekstil", "rinkliav")


def file_kind(text: str) -> Kind | None:
    """ "... MIŠRIŲ KOMUNALINIŲ ATLIEKŲ ... GRAFIKAS" is mixed waste, "... antrinių žaliavų
    surinkimo grafikas" packaging (with glass)."""
    folded = fold(text)
    if "komunalin" in folded or "misri" in folded:
        return "household"
    if "antrin" in folded or "pakuo" in folded or "stikl" in folded:
        return "packaging"
    return None


def find_files(html: str, page_url: str) -> tuple[list[ScheduleFile], list[str]]:
    """The schedules a page links, in its order, by the texts of their links; and warnings about
    schedules of no kind we read."""
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
        if "grafik" not in fold(f"{described} {name}"):
            continue
        kind = file_kind(described)
        if kind is None or any(word in fold(described) for word in OTHERS):
            warnings.append(f"{name} ({described!r}): a schedule of no kind we read")
            continue
        files.append(ScheduleFile(kind, url, name, text=described))
    return files, warnings


def _years(text: str) -> set[int]:
    return {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}


# "2025 M. 05 MĖN.–2026 M. 04 MĖN.": a period across a new year (folded).
_ACROSS = re.compile(r"\b(20\d{2}) m (\d{1,2}) men (20\d{2}) m (\d{1,2}) men\b")


def link_period(text: str) -> tuple[date, date] | None:
    """The months a link's text names: "2026 M. 04 - 06 MĖN.", "2025 M. 05 MĖN.–2026 M. 04
    MĖN."; None if it names none."""
    if match := _ACROSS.search(fold(text)):
        first, last = (int(match[1]), int(match[2])), (int(match[3]), int(match[4]))
        return date(*first, 1), month_end(*last)
    year, months = period(text)
    if year is None or months is None:
        return None
    return date(year, months[0], 1), month_end(year, months[1])


def select_files(
    files: list[ScheduleFile], today: date, keep_days: int = 31
) -> tuple[list[ScheduleFile], list[str]]:
    """Of each kind, the files with dates still to publish (their months end at most
    `keep_days` before today), so the next period's file is read as soon as a page links it; if
    none runs to today, also the latest, whose routes keep their last dates. Of two files for
    the same months, the one uploaded last (the folder of its URL), else the one linked first. No
    file of a kind raises ValidationError."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    cutoff = today - timedelta(days=keep_days)
    for kind, label in LABELS.items():
        mine: dict[tuple[date, date], ScheduleFile] = {}
        for file in (f for f in files if f.kind == kind):
            months = (file.start, file.end)
            if (kept := mine.get(months)) is None:
                mine[months] = file
                continue
            newer, older = (file, kept) if _uploaded(file) > _uploaded(kept) else (kept, file)
            mine[months] = newer
            warnings.append(
                f"{older.file_name}: not read, {newer.file_name} is a newer {label} schedule for "
                f"{months[0]} - {months[1]}"
            )
        if not mine:
            raise build.ValidationError(f"no {label} schedule on the pages")
        running = [f for f in mine.values() if f.end >= cutoff]
        latest = max(mine.values(), key=lambda f: (f.end, f.start))
        if not any(f.end >= today for f in running) and latest not in running:
            running.append(latest)
        selected += sorted(running, key=lambda f: f.start)
    return selected, warnings


def _get(url: str) -> bytes:
    # With the project's own user agent (http.USER_AGENT). sirvintos.lt answers GitHub's runners
    # 403; it serves a machine in Lithuania.
    return http.get(url, timeout=120)


# A copy of the two pages and the files the daily job reads from them, taken from a machine in
# Lithuania (save_copy, run daily by snapshot.py --copies): sirvintos.lt
# answers GitHub's runners 403, as silute.lt, kedainiai.lt and ukmerge.lt do. The mixed waste page
# is the copy's page; the packaging page is kept as one of its files, under the last part of its
# URL ("2332").
COPY_DIR = snapshot.SIRVINTOS_COPY_DIR


def _fetch(
    today: date, keep_days: int, get: Callable[[str], bytes]
) -> tuple[dict[str, bytes], list[ScheduleFile], dict[str, bytes], list[str]]:
    """The pages, the schedules they link of the last two years with the months of their tables
    (each one is downloaded for them), the files' contents by URL, and warnings."""
    pages = {page: get(page) for page in PAGES}
    found: list[ScheduleFile] = []
    warnings: list[str] = []
    for page, html in pages.items():
        files, notes = find_files(html.decode("utf-8", errors="replace"), page)
        found += [f for f in files if all(f.url != g.url for g in found)]
        warnings += [note for note in notes if note not in warnings]
    cutoff = today - timedelta(days=keep_days)
    contents: dict[str, bytes] = {}
    for file in found:
        years = _years(f"{file.text} {file.file_name}")
        if years and max(years) < cutoff.year - 1:
            continue  # two years old: nothing to publish
        contents[file.url] = get(file.url)
        file.start, file.end = read_period(file, contents[file.url])
    return pages, [f for f in found if f.url in contents], contents, warnings


def _download(
    today: date, keep_days: int, get: Callable[[str], bytes]
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    _, found, contents, warnings = _fetch(today, keep_days, get)
    chosen, notes = select_files(found, today, keep_days)
    return [(f, contents[f.url]) for f in chosen], warnings + notes


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files with dates still to publish, from the pages (each linked file of the last two
    years is downloaded: its period is in its table), or where the site doesn't answer and there
    is a copy (COPY_DIR), the copy's, with a warning that says how old it is, as
    ukmerge.download does."""
    try:
        return _download(today, keep_days, _get)
    except OSError as error:
        if not (COPY_DIR / snapshot.SITE_COPY_INDEX).exists():
            raise
        files, warnings = _download(today, keep_days, partial(snapshot.site_copy, COPY_DIR))
        note = snapshot.site_copy_note(MIXED_PAGE, error, COPY_DIR, today)
        print(note, file=sys.stderr)
        return files, [note, *warnings]


def save_copy(folder: Path | None = None, today: date | None = None) -> bool:
    """Saves the pages and every file the daily job would download from them in `folder`
    (COPY_DIR), for download when the site doesn't answer: python -m schedule_pipeline.snapshot
    --copies, daily, so the next period's or year's file comes within a day. False if the files
    were those of the copy already there, which is then left as it is: the packaging page, kept
    as a file, counts as a page, so its markup alone is no change."""
    today = today or snapshot.utc_today()
    pages, found, contents, warnings = _fetch(today, 31, _get)
    _, notes = select_files(found, today)
    for warning in warnings + notes:
        print(f"Širvintų r.: {warning}", file=sys.stderr)
    files = [(RECYCLABLES_PAGE, pages[RECYCLABLES_PAGE])] + [
        (f.url, contents[f.url]) for f in found
    ]
    return snapshot.save_site_copy(
        folder or COPY_DIR, MIXED_PAGE, pages[MIXED_PAGE], files, today, [RECYCLABLES_PAGE]
    )


# --- the tables ------------------------------------------------------------------

# The letters of a line within 2 points of each other (see above).
TABLE_SETTINGS = {"text_y_tolerance": 2}
# The months' numbers of the packaging file's header.
_MONTH_NUMBER = re.compile(r"(0[1-9]|1[0-2])")
# Rows under the mixed waste routes: the shared containers ("Mišrių komunalinių atliekų
# konteineriai prie kapinių ...", "... prie daugiabučių ...", "... iš juridinių asmenų ...") and
# when to put the containers out ("Pastaba: ...") (folded).
_NOTES = re.compile(r"\bkonteineriai (?:prie|is)\b|^pastaba\b")
# The column titles before the months of the mixed waste files (folded).
_COLUMNS = {"marsruto pavadinimas": "route", "vietoves": "places"}
# The waste type of a row of the packaging file (folded).
ROW_KINDS: dict[str, Kind] = {"pop plast m": "packaging", "stiklas": "glass"}
# The row of an eldership in the packaging file: "ALIONIŲ SENIŪNIJA".
_ELDERSHIP_ROW = re.compile(rf"{_WORD}\s+SENIŪNIJA", re.I)
# Routes or places in a file of each kind, at least: the mixed waste files of 2025-2026 had 20
# routes, the 2026 packaging file 20 places.
MIN_ROUTES: dict[Kind, int] = {"household": 15, "packaging": 14}
# The kinds whose rows must have days in every month (glass is collected every few months).
EVERY_MONTH: tuple[Kind, ...] = ("household", "packaging")


@dataclass
class _Route:
    """A route's (or a packaging place's) places and its dates per waste type."""

    name: str
    where: str
    dates: dict[Kind, set[date]] = field(default_factory=dict)


@dataclass
class _Table:
    title: str
    months: list[date]  # the first day of each month of the table
    routes: list[_Route]

    @property
    def period(self) -> tuple[date, date]:
        return self.months[0], month_end(self.months[-1].year, self.months[-1].month)


def _months(numbers: list[int], years: set[int], where: str) -> list[date]:
    """The months of a header, one after another, from the first year of the title on (a
    month before the one to its left is the next year's); the last must be in the title's last
    year."""
    if not years:
        raise ValueError(f"{where}: no year in the title")
    if any((b - a) % 12 != 1 for a, b in zip(numbers, numbers[1:], strict=False)):
        raise ValueError(f"{where}: months out of order: {numbers}")
    year, months = min(years), []
    for number in numbers:
        if months and number < months[-1].month:
            year += 1
        months.append(date(year, number, 1))
    if months[-1].year != max(years):
        raise ValueError(f"{where}: months to {months[-1]:%Y-%m}, the title says {sorted(years)}")
    return months


def _dates(cells: list[str], months: list[date], kind: Kind, where: str) -> set[date]:
    """The dates of a row's cells under the months. "-" or nothing: none that month."""
    dates: set[date] = set()
    for cell, month in zip(cells, months, strict=True):
        days = maatc._days(cell, where)
        if not days and kind in EVERY_MONTH and cell not in ("-", "–"):
            raise ValueError(f"{where}: no {kind} days in {month:%Y-%m}")
        for day in days:
            if not 1 <= day <= month_end(month.year, month.month).day:
                raise ValueError(f"{where}: {month:%Y-%m} has no day {day}")
            dates.add(month.replace(day=day))
    return dates


def _mixed(pdf, where: str) -> _Table:
    """A mixed waste file: the title above a row of months, then a row per route, its places
    (and its name) and its days under the months."""
    title: list[str] = []
    # The months' columns, the columns of the places and of the routes' names, the first month's.
    header: tuple[dict[int, int], int, int | None, int] | None = None
    months: list[date] = []
    routes: list[_Route] = []
    for page in pdf.pages:
        for table in page.extract_tables(TABLE_SETTINGS):
            for row in table:
                cells = [maatc._cell(value) for value in row]
                text = " ".join(c for c in cells if c)
                if not text:
                    continue
                found = {
                    i: aratc.MONTHS[fold(c)] for i, c in enumerate(cells) if fold(c) in aratc.MONTHS
                }
                if len(found) >= 2:
                    columns = sorted(found)
                    if header is not None or columns != list(range(columns[0], columns[-1] + 1)):
                        raise ValueError(f"{where}: another row of months: {text[:80]!r}")
                    roles: dict[str, int] = {}
                    for i, cell in enumerate(cells[: columns[0]]):
                        if role := _COLUMNS.get(fold(cell)):
                            roles[role] = i
                        elif cell:
                            title.append(cell)  # the title's end next to the months
                    places = roles.get("places", 0 if columns[0] == 1 else None)
                    if places is None:
                        raise ValueError(f"{where}: no column of places before the months")
                    header = (found, places, roles.get("route"), columns[0])
                    numbers = [found[i] for i in columns]
                    months = _months(numbers, _years(" ".join(title)), where)
                    continue
                if header is None:
                    title.append(text)
                    continue
                found_months, places, route, first = header
                if _NOTES.search(fold(cells[places] if places < len(cells) else text)):
                    continue
                width = first + len(found_months)
                if len(cells) < width or any(cells[width:]):
                    raise ValueError(f"{where}: a row of other columns: {text[:80]!r}")
                name = cells[places]
                if not name:
                    raise ValueError(f"{where}: dates without places: {text[:80]!r}")
                if any(cells[i] for i in range(first) if i not in (places, route)):
                    raise ValueError(f"{where}: text in no column: {text[:80]!r}")
                days = _dates(cells[first:width], months, "household", f"{where}: {name[:40]!r}")
                routes.append(_Route(name, where, {"household": days}))
    if header is None:
        raise ValueError(f"{where}: no row of months")
    return _Table(clean_text(" ".join(title)), months, routes)


def _line_text(words: list[dict]) -> str:
    """Words in reading order: lines top to bottom (a word within 3 points of a line's top is
    on it), each left to right."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and word["top"] - lines[-1][0]["top"] <= 3:
            lines[-1].append(word)
        else:
            lines.append([word])
    return clean_text(
        " ".join(w["text"] for line in lines for w in sorted(line, key=lambda w: w["x0"]))
    )


def _recyclables(pdf, where: str) -> _Table:
    """The packaging file: the title, the columns' titles and the months' numbers, then the rows
    of elderships and, under each, the places with a row of packaging and one of glass. A place's
    text is the words left of the column of waste types between the top of its first row and the
    bottom of its last."""
    title: list[str] = []
    months: list[date] = []
    routes: list[_Route] = []
    for page in pdf.pages:
        here = f"{where} page {page.page_number}"
        words = page.extract_words()
        for table in page.find_tables():
            texts = table.extract(y_tolerance=2)
            columns: dict[str, int] = {}
            header_bottom: float | None = None
            month_columns: list[int] = []
            eldership = ""
            # (route, its rows' top and bottom); the rows of elderships' top and bottom
            blocks: list[tuple[_Route, float, float]] = []
            others: list[tuple[float, float]] = []
            for row, values in zip(table.rows, texts, strict=True):
                cells = [maatc._cell(value) for value in values]
                text = " ".join(c for c in cells if c)
                top, bottom = row.bbox[1], row.bbox[3]
                if not text:
                    continue
                if header_bottom is None:
                    numbers = [i for i, c in enumerate(cells) if _MONTH_NUMBER.fullmatch(c)]
                    if len(numbers) >= 6 and columns:
                        month_columns = numbers
                        found = [int(cells[i]) for i in numbers]
                        months = _months(found, _years(" ".join(title)), here)
                        header_bottom = bottom
                    elif fold(text).startswith("vietoves pavadinimas"):
                        for i, cell in enumerate(cells):
                            folded = fold(cell)
                            if folded.startswith("vietov"):
                                columns["places"] = i
                            elif "rusis" in folded:
                                columns["kind"] = i
                        if set(columns) != {"places", "kind"}:
                            raise ValueError(f"{here}: columns {cells!r}")
                    else:
                        title.append(text)
                    continue
                places, kind_column = columns["places"], columns["kind"]
                label = fold(cells[kind_column])
                if not label:
                    if _ELDERSHIP_ROW.fullmatch(cells[places]) and text == cells[places]:
                        eldership = cells[places]
                        others.append((top, bottom))
                        continue
                    raise ValueError(f"{here}: a row of no waste type: {text[:80]!r}")
                kind = ROW_KINDS.get(label)
                if kind is None:
                    raise ValueError(f"{here}: a row of {cells[kind_column]!r}")
                row_where = f"{here}: {text[:40]!r}"
                days = _dates([cells[i] for i in month_columns], months, kind, row_where)
                if kind == "packaging":
                    if not eldership:
                        raise ValueError(f"{here}: places of no eldership: {text[:80]!r}")
                    blocks.append((_Route(eldership, here, {kind: days}), top, bottom))
                elif not blocks or kind in blocks[-1][0].dates or cells[places]:
                    raise ValueError(f"{here}: {kind} of no place: {text[:80]!r}")
                else:
                    route, first, _ = blocks[-1]
                    route.dates[kind] = days
                    blocks[-1] = (route, first, bottom)
            if header_bottom is None:
                continue
            # The places, by the words left of the column of waste types.
            left = min(
                cell[0] for row in table.rows if (cell := row.cells[columns["kind"]]) is not None
            )
            texts_of: dict[int, list[dict]] = defaultdict(list)
            x0, _, _, bottom = table.bbox
            for word in words:
                middle = (word["top"] + word["bottom"]) / 2
                if word["x1"] > left + 1 or not x0 - 1 <= word["x0"] or middle > bottom:
                    continue
                if middle <= header_bottom or any(a <= middle <= b for a, b in others):
                    continue
                block = next((i for i, (_, a, b) in enumerate(blocks) if a <= middle <= b), None)
                if block is None:
                    raise ValueError(f"{here}: {word['text']!r} of no place")
                texts_of[block].append(word)
            for i, (route, _, _) in enumerate(blocks):
                text = _line_text(texts_of[i])
                if not text:
                    raise ValueError(f"{here}: dates without places in {route.name}")
                route.name = f"{route.name}: {text}"
                routes.append(route)
    if not months:
        raise ValueError(f"{where}: no row of months")
    return _Table(clean_text(" ".join(title)), months, routes)


# The words of each kind's title (folded).
TITLES: dict[Kind, str] = {"household": "komunalin", "packaging": "antrin"}


def read(source: SourceFile, content: bytes) -> _Table:
    """A file's table. Strict (ValueError): see the module's description."""
    where = source.file_name
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        table = (_mixed if source.kind == "household" else _recyclables)(pdf, where)
    if TITLES[source.kind] not in fold(table.title) or "grafik" not in fold(table.title):
        raise ValueError(f"{where}: the title {table.title[:100]!r} isn't of {source.kind}")
    if len(table.routes) < MIN_ROUTES[source.kind]:
        raise ValueError(
            f"{where}: only {len(table.routes)} routes (expected {MIN_ROUTES[source.kind]})"
        )
    return table


def read_period(source: ScheduleFile, content: bytes) -> tuple[date, date]:
    """The first and the last day of the months of a file's table, which must be those its link
    names, if any, and of the year it names."""
    start, end = read(source, content).period
    named = link_period(source.text)
    if named and named != (start, end):
        raise ValueError(f"{source.file_name}: months {start} - {end}, its link says {named}")
    if (years := _years(source.text)) and not years <= {start.year, end.year}:
        raise ValueError(f"{source.file_name}: months {start} - {end}, its link says {years}")
    return start, end


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of a file: one per route (place) and waste type, named after its places. Dates
    that mostly miss one weekday raise ValueError (the wrong year or months); a few off it are
    warnings (holidays move some)."""
    table = read(source, content)
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for route in table.routes:
        for kind, dates in route.dates.items():
            if not dates:
                continue
            weekday, times = Counter(d.weekday() for d in dates).most_common(1)[0]
            if 2 * times <= len(dates) or weekday > 4:
                raise ValueError(
                    f"{route.where}: the {kind} dates of {route.name[:60]!r} aren't on one working "
                    "day: the wrong year or months?"
                )
            if off := sorted(d for d in dates if d.weekday() != weekday):
                days = ", ".join(d.isoformat() for d in off)
                warnings.append(
                    f"{route.where}: {kind} of {route.name[:60]!r} on {days}, not on its weekday "
                    f"({WEEKDAY_NAMES[weekday]})"
                )
            area = Area(kind, route.name, LABEL, provider=PROVIDER_ID, dates=set(dates))
            if not off:
                area.weekday = WEEKDAY_NAMES[weekday]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{route.where}: {kind} of {route.name[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    return ParseResult(areas=list(areas.values()), warnings=warnings)


# --- the places ------------------------------------------------------------------

_STREET = r"(?:g|skg|al|pl|tak|a)"
_HOUSE = r"\d+\s*[A-Za-z]?(?!\w)"


def _whole(match: re.Match[str]) -> str:
    """A whole eldership but some villages, as aratc.Routes reads it: "Alionių SEN.: tik
    Alionių sen. esantys kaimai (be Kvakšių)"."""
    name, but = match[1], match[2]
    text = f"{name} SEN.: tik {name} sen. esantys kaimai"
    if but:
        text += f" (be {re.sub(r'\s+(?:k|vs)\b\.?', '', but)})"
    return text


# The publisher's spellings, as ecoservice.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], object], ...] = (
    # The town's streets: "ŠIRVINTŲ MIESTAS Individualios valdos: Zibalų g. ...", and in the
    # section of its eldership "ŠIRVINTŲ SENIŪNIJA: Širvintų miestas: Ateities g., ..." (the town
    # is an eldership of its own in the register).
    (
        re.compile(
            rf"(?:\b{_WORD}\s+SENIŪNIJA\s*:\s*)?\b({_WORD})\s+(?i:miestas)\s*"
            r"(?:Individualios\s+valdos\s*)?:"
        ),
        r"\1 miesto.:",
    ),
    # A whole eldership: "ALIONIŲ SENIŪNIJA: Visa seniūnija, išskyrus Kvakšių k", "ČIOBIŠKIO
    # SENIŪNIJA: Visa seniūnija" (the places left out are other rows').
    (
        re.compile(
            rf"\b({_WORD})\s+SENIŪNIJA\s*:\s*Visa\s+seniūnija\s*(?:,?\s*i[sš]+kyrus\s+(.*?))?\s*$",
            re.I,
        ),
        _whole,
    ),
    # Some houses of a street: "Zibalų g. Nr. 19,21", "Totorių g. iki Nr. 12", "Zibalų g. nuo
    # Nr.18", "Plento g. nuo Nr. 58 iki 90.", "Totorių g.12": that street, as ecoservice.Routes
    # reads "Gilijos g. (1, 3, 5, ...)" (the routes that name it are the choices the app gives).
    (
        re.compile(
            rf"\b({_STREET})\.\s*(?:(?:nuo|iki)\s+)?(?:Nr\.\s*)?{_HOUSE}"
            rf"(?:\s*(?:,|ir|iki)\s*(?:Nr\.\s*)?{_HOUSE})*"
        ),
        r"\1.",
    ),
    # "Giminių g,.": the end of the list.
    (re.compile(r"(?<=\w),\.(?=\s|$)"), "."),
    # "Bajorų g. Bajorų k.": that street of the village.
    (re.compile(rf"\b({_WORD})\s+g\.\s+\1\s+k\.(?=\s*[,;]|\s*$)"), r"\1 k. (\1 g.)"),
)


class Routes(ecoservice.Routes):
    """Reads the places of the rows as ecoservice.Routes reads those of Šilutės r., Trakų r. and
    Šalčininkų r. (maatc.Routes, aratc.Routes): the settlements of each eldership's section
    ("ZIBALŲ SEN. Aukštadvario k., ...", "ALIONIŲ SENIŪNIJA: Kvakšių k."), streets of a village
    in a bracket ("Bajorų k. (Pušų g.)", "Širvintų k. (išskyrus Družų g., Zosinos g.)"), a whole
    eldership but some villages, and the town's streets ("ŠIRVINTŲ MIESTAS Individualios valdos:
    Zibalų g. Nr. 19,21, Upelio g., ..."). A street named with some of its houses ("Totorių g.
    iki Nr. 12" in one route, "Totorių g.12" in the other) is that street, as ecoservice.Routes
    reads them: the routes that name it are the choices the app gives. A village in the town's
    list ("..., Tvenkinio g., Kalnalaukio k., Staviškių g., ...") is the municipality's only one
    of that name, and the streets after it are still the town's.

    No street gets "no pickup" (build_locations): the files list the streets of private houses,
    the shared containers of the apartment buildings have no file, and nothing says a street
    has none. A street no route names is left to the app, which offers the town's routes."""

    @staticmethod
    def municipality_of(provider: Provider) -> maatc.Municipality:
        return MUNICIPALITY

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return super().spellings(text)

    def section(self, district: str, text: str) -> list[_Stop]:
        if self.town is aratc._NO_TOWN or district != self.town.district:
            return super().section(district, text)
        streets: list[str] = []
        villages: list[str] = []
        for part in _section_parts(text):
            match = _SECTION_ITEM.fullmatch(part.partition("(")[0].strip(" ,;:"))
            (villages if match and match["type"] in ("k", "vs") else streets).append(part)
        stops = super().section(district, ", ".join(streets))
        return stops + (super().section("", ", ".join(villages)) if villages else [])


PROVIDER_ID = "sirvintos"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=NAME,
    url=MIXED_PAGE,
    # Every eldership of the municipality (register names).
    elderships=frozenset(
        {
            "Alionių",
            "Čiobiškio",
            "Gelvonų",
            "Jauniūnų",
            "Kernavės",
            "Musninkų",
            "Širvintų",
            "Širvintų miesto",
            "Zibalų",
        }
    ),
    # Typos too far from the register's names to be taken for them.
    aliases=(
        ("Ateities.,", "Ateities g.,"),  # Širvintos, mixed waste
        ("Žiūrų k.", "Žiūrių k."),  # Zibalų sen., mixed waste
        ("Peliškiškių vs.", "Peliškių vs."),  # Širvintų sen., mixed waste
        ("Staravygalos k.", "Stavarygalos k."),  # Gelvonų sen., mixed waste
        # Širvintų sen., mixed waste, between "Alekniškio vs." and "Bredėnų k.": the
        # eldership's only Aukšt... place is Aukštosios Viesos (Aukštųjų Viesų k.).
        ("Aukštujų k.", "Aukštųjų Viesų k."),
        ("Stanislavuvkos s.,", "Stanislavuvkos vs.,"),  # Musninkų sen., packaging
    ),
    kinds=("household", "packaging", "glass"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.SIRVINTOS_MUNICIPALITY,
    snapshot.SIRVINTOS_REGISTRY_FILE,
    snapshot.SIRVINTOS_ADDRESSES_FILE,
    # June-December 2026: 20 mixed waste routes, which gave a schedule to 413 of the 470
    # settlements; 2026: 20 places of packaging and glass.
    min_areas={"household": 15, "packaging": 14, "glass": 14},
    min_household_places=330,
    # About 12,000 addresses in 2026.
    min_address_points=8_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- this period and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins the routes of the files of later periods to those of the period in force, in place,
    each kind on its own (sratc._continue, as kretinga.combine joins Kretingos r.'s half years):
    a route of the next period that covers the same places as one in force gives it its dates;
    the rest wait, with a warning, until their period starts. Routes of earlier periods are
    dropped. A file that starts in the months of the one before replaces it from its first month
    (June-December 2026 in place of April-June's June).

    A kind whose files have all ended keeps its routes, with their last dates
    (build.current_rows), and a warning; so does one with no file for today, whose next one has
    started early."""
    warnings: list[str] = []
    groups: dict = defaultdict(lambda: defaultdict(list))
    for kind, label in LABELS.items():
        files = sorted(
            ((s, r) for s, r in parsed if s.kind == kind and r.areas),
            key=lambda p: p[0].start,
        )
        for (source, result), (later, _) in zip(files, files[1:], strict=False):
            if later.start <= source.end:
                for area in result.areas:
                    area.dates = {d for d in area.dates if d < later.start}
                result.areas[:] = [a for a in result.areas if a.dates]
        if not files:
            continue
        if (ended := max(s.end for s, _ in files)) < today:
            warnings.append(f"the {label} schedule ended on {ended}; no newer one is read")
        elif (first := min(s.start for s, _ in files)) > today:
            warnings.append(f"no {label} schedule for today; the next starts on {first}")
        for source, result in files:
            for area in result.areas:
                groups[(LABEL, area.kind)][source.start].append((result, area))
    reader = Routes(Index(registry), PROVIDER, defaultdict(dict))
    return warnings + _continue(groups, reader, lambda start: start <= today, date.isoformat)


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MUNICIPALITY.min_areas,
    MUNICIPALITY.min_household_places,
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
    # The folder of one provider, as raseiniai.py builds its own; a build that fails writes
    # nothing (the daily job keeps yesterday's folder).
    return raseiniai.run(args.out, args.keep_days, None, MUNICIPALITY, lambda _: SOURCE)


if __name__ == "__main__":
    raise SystemExit(main())

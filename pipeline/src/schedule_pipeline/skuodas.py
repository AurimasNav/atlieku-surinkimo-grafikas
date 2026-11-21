"""Skuodo rajonas: the schedules of the individual houses of the whole municipality, published by
Skuodo rajono savivaldybė (skuodas.lt): mixed waste, packaging (paper and plastic) and glass. The
files give the phone number of UAB „Ekonovus“ (+370 700 77046), which collects the waste.

The municipality's page "Atliekų tvarkymas ir surinkimo grafikai 2026 m." (at an address that
still says 2025) has a paragraph per file, each linking it by "čia" ("here"):

    2026 m. Skuodo rajono mišrių komunalinių atliekų surinkimo grafiką 2026 m. rasite čia.
    2026 m. Skuodo rajono pakuočių (išskyrus stiklo) ir popieriaus atliekų surinkimo iš
    individualių namų valdų grafiką rasite čia.
    2026 m. Skuodo rajono stiklo pakuočių atliekų surinkimo iš individualių namų valdų grafiką
    rasite čia.

The files have names that say nothing (cia-1.xls, cia.xlsx, cia-2.xlsx), so they are found by
the texts of their paragraphs, with the year these name. The mixed waste file is a legacy Excel
workbook (.xls, read with xlrd), the others .xlsx (openpyxl). Each is a sheet with a title that
names the waste type and the year, a row of months, and a row per route, its places in one cell:

    SKUODO RAJONO GYVENTOJŲ MIŠRIŲ KOMUNALINIŲ ATLIEKŲ SURINKIMO GRAFIKAS 2026 M.
    Aptarnavimas            | Vietovės pavadinimas               | Sausis | Vasaris | ...
    Pirmadienis, kas 14 d.  | Skuodo sen.: Mažieji Rūšupiai; ... | 5, 19  | 2, 16   | ...
                            | Skuodo miesto senamiestis          | kiekvieną pirmadienį

The packaging file has the day of the week in Roman numerals ("Sav. d.": "II", "VII"), the glass
file none (five pickups a year). Hidden columns and rows aren't read: those of the mixed waste
file hold the dates of 2025. Skuodas town's mixed waste is collected every week, in its old town
("senamiestis") on Mondays and in its new town ("naujamiestis") on Fridays: those rows' dates are
every such day of the year. The shared containers ("bendrojo naudojimo konteineriai") aren't
read. Strict: a cell of days that isn't a list of days, a day the month doesn't have, months out
of order, cells outside the table, a title of another year or waste type than its paragraph's,
and dates mostly off the day of the week their row names (the wrong year) raise.

The places are read by Routes (aratc.Routes). Next year's file of a kind continues the routes of
this year that cover the same places (tratc.combine). Writes <out>/schedule.json and
<out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.skuodas --out ../site/skuodo-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import openpyxl
import xlrd
from openpyxl.utils import column_index_from_string

from . import aratc, build, http, maatc, raseiniai, snapshot, tratc
from .dates import WEEKDAY_NAMES, month_end, parse_weekdays, weekly_dates
from .locations import _WORD, Clause, Index, _Stop
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

PAGE_URL = "https://skuodas.lt/atlieku-tvarkymas-ir-surinkimo-grafikai-2025-m/"
NAME = "Skuodo rajono savivaldybė"
LABEL = "Skuodo r."  # every row's `district`
PROVIDER_ID = "skuodas"
KINDS: tuple[Kind, ...] = ("household", "packaging", "glass")
LABELS: dict[Kind, str] = {"household": "mixed waste", "packaging": "packaging", "glass": "glass"}


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Skuodo raj. sen.: Skuodo priemiestis": Skuodo sen.
    (re.compile(rf"\b({_WORD})\s+raj\.\s+sen\b"), r"\1 sen"),
    # "Skuodo miesto senamiestis", "Skuodo miesto naujamiestis": the town's old and new parts,
    # which the register doesn't have: the whole town, whose two rows the app asks about.
    (
        re.compile(rf"^({_WORD})\s+miesto\s+(?:senamiestis|naujamiestis)\.?$", re.I),
        r"\1 miesto sen.: \1 m.",
    ),
)
# An eldership's mark with nothing after it at the end of a row ("... Virbalų k. Šačių sen.: "):
# no places, not the whole eldership (aratc.Routes reads "Šačių sen., Barstyčių sen." so).
_EMPTY_END = re.compile(rf"\s*\b{_WORD}\s+sen\b\.?\s*:\s*$")


class Routes(aratc.Routes):
    """Reads the places of the routes as aratc.Routes reads those of Alytus county: sections of
    elderships, their villages nominative ("Skuodo sen.: Mažieji Rūšupiai; Puodkaliai") or
    genitive with their type ("Ylakių sen: Augzelių k., ..."), whole elderships ("Aleksandrijos
    sen.", "Šačių sen., Barstyčių sen.") and the streets of Skuodas after its name ("Skuodo
    miesto sen.: Skuodo m. - Apuolės g., ..."). A whole eldership named before the villages of
    another ("Lenkimų sen., Mosėdžio sen.: Plaušiniai; ...", "Mosėdžio sen., Skuodo sen.:
    Būdvietė") is a fallback: a village another row of the kind names gets that row instead.

    Also: "Skuodo raj. sen.:" is Skuodo sen.; the old and new town ("Skuodo miesto senamiestis")
    are the whole town, the app asking which; an eldership's mark at the end of a row with
    nothing after it ("... Šačių sen.: ") is reported, not read as the whole eldership.

    No street of Skuodas gets "no pickup" (build_locations): the glass file names 60 of its 85
    streets, the others say nothing of streets, and nothing says a street has none. The app
    offers the town's routes instead."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return _EMPTY_END.sub("", text)

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        found, skipped = super().clauses(area)
        if match := _EMPTY_END.search(clean_text(area.name)):
            self.unknown.append(f"{match[0].strip()} (no places after it)")
        return found, skipped

    def section(self, district: str, text: str) -> list[_Stop]:
        """aratc.Routes' section, with Skuodas as the town of its eldership's section."""
        if self.town is aratc._NO_TOWN and district.endswith(" miesto"):
            towns = [
                s
                for s in self.places[self.municipality.label]
                if s.district == district and s.abbr == "m."
            ]
            self.town = towns[0] if len(towns) == 1 else aratc._NO_TOWN
        return super().section(district, text)


PROVIDER = Provider(
    id=PROVIDER_ID,
    name=NAME,
    url=PAGE_URL,
    elderships=frozenset(
        {
            "Aleksandrijos",
            "Barstyčių",
            "Lenkimų",
            "Mosėdžio",
            "Notėnų",
            "Skuodo",
            "Skuodo miesto",
            "Šačių",
            "Ylakių",
        }
    ),
    reader=Routes,
    kinds=KINDS,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.SKUODAS_MUNICIPALITY,
    snapshot.SKUODAS_REGISTRY_FILE,
    snapshot.SKUODAS_ADDRESSES_FILE,
    # 2026: 10 mixed waste routes and Skuodas's old and new town, 6 packaging routes and 7 of
    # glass, which gave a mixed waste schedule to 150 of the 174 settlements (the file leaves
    # out 24 villages of Skuodo and Ylakių sen.).
    min_areas={"household": 8, "packaging": 4, "glass": 5},
    min_household_places=120,
    # 8,878 addresses in November 2026.
    min_address_points=6_000,
    label=LABEL,
    # Glass has a file of its own.
    file_kinds={},
)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page, with the year its paragraph names."""

    year: int = 0


# Where a link's paragraph ends: its text describes the file.
_BLOCKS = {"p", "li", "td", "th", "div", "h1", "h2", "h3", "h4", "h5", "h6"}


class _Links(HTMLParser):
    """The page's links with the texts of their paragraphs: (href, text)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._text: list[str] = []
        self._hrefs: list[str] = []  # links of the paragraph being read

    def _flush(self) -> None:
        text = clean_text("".join(self._text))
        self.links += [(href, text) for href in self._hrefs]
        self._text, self._hrefs = [], []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self._flush()
        elif tag == "a" and (href := dict(attrs).get("href")):
            self._hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def file_kind(text: str) -> Kind | None:
    """By the text of a file's paragraph (folded): "pakuočių (išskyrus stiklo) ir popieriaus" is
    packaging, "stiklo pakuočių" glass, "mišrių komunalinių" mixed waste."""
    folded = fold(text)
    if "isskyrus stikl" in folded or "popier" in folded or "plastik" in folded:
        return "packaging"
    if "stikl" in folded:
        return "glass"
    if "pakuoc" in folded:
        return "packaging"
    if "misri" in folded or "komunalin" in folded:
        return "household"
    return None


def _years(text: str) -> set[int]:
    return {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The spreadsheets the page links, in its order, by the texts of their paragraphs; and
    warnings about spreadsheets of no kind we know or without a year."""
    collector = _Links()
    collector.feed(html)
    collector.close()
    files: list[ScheduleFile] = []
    warnings: list[str] = []
    for href, text in collector.links:
        url = urljoin(page_url, href)
        name = PurePosixPath(unquote(urlsplit(url).path)).name
        if not name.lower().endswith((".xls", ".xlsx")) or any(f.url == url for f in files):
            continue
        kind = file_kind(text)
        years = _years(text)
        if kind is None:
            warnings.append(f"{name} ({text[:80]!r}): a spreadsheet of no kind we read")
        elif len(years) != 1:
            warnings.append(f"{name} ({text[:80]!r}): no single year in its paragraph; not read")
        else:
            files.append(ScheduleFile(kind, url, name, year=years.pop()))
    return files, warnings


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Of each kind, the files of this year and later, so next year's file is read as soon as
    it's linked; if there are none, the newest one, whose routes keep their last dates. Of two
    for one year, the one linked last. The page must have a file of each kind."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    for kind, label in LABELS.items():
        mine: dict[int, ScheduleFile] = {}
        for file in (f for f in files if f.kind == kind):
            if (older := mine.get(file.year)) is not None:
                warnings.append(
                    f"{older.file_name}: not read, {file.file_name} is a newer {label} schedule "
                    f"for {file.year}"
                )
            mine[file.year] = file
        if not mine:
            raise build.ValidationError(f"no {label} schedule on the page")
        years = [y for y in mine if y >= today.year] or [max(mine)]
        if today.year not in years:
            warnings.append(f"no {label} schedule for {today.year} on the page")
        selected += [mine[y] for y in sorted(years)]
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    found, warnings = find_files(html)
    chosen, notes = select_files(found, today)
    return [(f, http.get(f.url, timeout=120)) for f in chosen], warnings + notes


# --- the sheets ------------------------------------------------------------------

Sheet = tuple[str, list[tuple[int, list[str]]]]  # its name, and its rows: (number, cells)


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _xls_text(cell: xlrd.sheet.Cell, datemode: int) -> str:
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        return _number(cell.value)
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate.xldate_as_datetime(cell.value, datemode).date().isoformat()
    return clean_text(cell.value)


def _xls_sheets(content: bytes) -> list[Sheet]:
    """The visible cells of the visible sheets of a legacy workbook, as text."""
    book = xlrd.open_workbook(file_contents=content, formatting_info=True)
    sheets: list[Sheet] = []
    for sheet in book.sheets():
        if sheet.visibility:
            continue
        columns = [
            c
            for c in range(sheet.ncols)
            if not (c in sheet.colinfo_map and sheet.colinfo_map[c].hidden)
        ]
        rows = [
            (r + 1, [_xls_text(sheet.cell(r, c), book.datemode) for c in columns])
            for r in range(sheet.nrows)
            if not (r in sheet.rowinfo_map and sheet.rowinfo_map[r].hidden)
        ]
        sheets.append((sheet.name, rows))
    return sheets


def _xlsx_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return _number(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    return clean_text(value)


def _xlsx_sheets(content: bytes) -> list[Sheet]:
    """The visible cells of the visible sheets of a workbook, as text."""
    book = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    sheets: list[Sheet] = []
    for sheet in book.worksheets:
        if sheet.sheet_state != "visible":
            continue
        hidden: set[int] = set()
        for key, dimension in sheet.column_dimensions.items():
            if dimension.hidden:
                first = dimension.min or column_index_from_string(key)
                hidden |= set(range(first, (dimension.max or first) + 1))
        columns = [c for c in range(1, sheet.max_column + 1) if c not in hidden]
        rows = [
            (r, [_xlsx_text(sheet.cell(r, c).value) for c in columns])
            for r in range(1, sheet.max_row + 1)
            if not (r in sheet.row_dimensions and sheet.row_dimensions[r].hidden)
        ]
        sheets.append((sheet.title, rows))
    return sheets


def sheets(source: SourceFile, content: bytes) -> list[Sheet]:
    name = source.file_name.lower()
    if name.endswith(".xls"):
        return _xls_sheets(content)
    if name.endswith(".xlsx"):
        return _xlsx_sheets(content)
    raise ValueError(f"{source.file_name}: not a spreadsheet")


# --- the tables ------------------------------------------------------------------

# The waste type a title names (folded).
_TITLE_KINDS: tuple[tuple[re.Pattern[str], Kind], ...] = (
    (re.compile(r"\bmisri\w* komunalin"), "household"),
    (re.compile(r"\bstiklo pakuoc"), "glass"),
    (re.compile(r"\b(?:popieriaus|plastiko) .*pakuoc"), "packaging"),
)
# The columns' titles (folded) besides the months: the places, and the day of the week.
_PLACES = "vietoves pavadinimas"
_WEEKDAY_TITLES = {"aptarnavimas", "sav d"}
# Text outside the table: the phone number above it, the reminder under it (folded).
_NOTES = re.compile(r"^informacija tel\b|^p s konteineriai\b")
# Shared containers (folded): not read.
_SHARED = re.compile(r"\bbendr\w* naudojim|\bdaugiabuc|\bkolektyvin")
_DAYS = re.compile(r"\d{1,2}(?:\s*,\s*\d{1,2})*")
# "kiekvieną pirmadienį": every week.
_WEEKLY = re.compile(r"^kiekvien\w*\s")
_ROMAN = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}
# Routes in a file of each kind, at least: in 2026, 10 mixed waste routes and the town's two
# parts, 6 of packaging and 7 of glass.
MIN_ROUTES: dict[Kind, int] = {"household": 8, "packaging": 4, "glass": 5}
# Of a route's dates, at least this share on the day of the week its row names (holidays may
# move a few): those of the wrong year fall on another day.
SAME_WEEKDAY = 0.75


@dataclass
class _Header:
    places: int  # the column of the places
    weekday: int | None  # of the day of the week, if the file has one
    months: dict[int, int]  # the months' columns


@dataclass
class _Route:
    where: str
    places: str
    dates: set[date]
    weekday: int | None  # the day of the week its row names


def _header(cells: list[str], where: str) -> _Header | None:
    """A row of months ("Sausis ... Gruodis") and the titles next to them; None if it isn't
    one."""
    months = {i: aratc.MONTHS[fold(c)] for i, c in enumerate(cells) if fold(c) in aratc.MONTHS}
    if len(months) < 6:
        return None
    if list(months.values()) != list(range(1, 13)):
        raise ValueError(f"{where}: months {list(months.values())}")
    places = weekday = None
    for i, cell in enumerate(cells):
        if not cell or i in months:
            continue
        if fold(cell) == _PLACES and places is None:
            places = i
        elif fold(cell) in _WEEKDAY_TITLES and weekday is None:
            weekday = i
        else:
            raise ValueError(f"{where}: an unknown column {cell!r}")
    if places is None:
        raise ValueError(f"{where}: no column of places next to the months")
    return _Header(places, weekday, months)


def _weekday(text: str, where: str) -> int:
    """The day of the week a row names: "Pirmadienis, kas 14 d.", "Kevirtadienis, kas 14 d.",
    "II", "VII"."""
    if text in _ROMAN:
        return _ROMAN[text]
    found = parse_weekdays(re.sub(r"(?i)\bkevirt", "ketvirt", text))
    if len(found) != 1:
        raise ValueError(f"{where}: not a day of the week: {text!r}")
    return found[0]


def _days(cell: str, year: int, month: int, where: str) -> set[date]:
    if not _DAYS.fullmatch(cell):
        raise ValueError(f"{where}: unrecognised days {cell!r}")
    days = [int(day) for day in re.findall(r"\d+", cell)]
    last = month_end(year, month).day
    if wrong := [day for day in days if not 1 <= day <= last]:
        raise ValueError(f"{where}: month {month} of {year} has no day {wrong[0]} ({cell!r})")
    return {date(year, month, day) for day in days}


def _route(cells: list[str], header: _Header, year: int, where: str) -> _Route | None:
    """A route's row: its places, and its days under the months or a weekly rule ("kiekvieną
    pirmadienį", under January). None for shared containers."""
    places = cells[header.places]
    if _SHARED.search(fold(places)):
        return None
    days = {month: cells[i] for i, month in header.months.items() if cells[i]}
    weekday = None
    if header.weekday is not None and cells[header.weekday]:
        weekday = _weekday(cells[header.weekday], where)
    rule = days.get(1, "")
    if len(days) == 1 and _WEEKLY.match(fold(rule)):
        weekdays = parse_weekdays(rule)
        if len(weekdays) != 1 or weekday not in (None, weekdays[0]):
            raise ValueError(f"{where}: not a weekly rule: {rule!r}")
        dates = weekly_dates(weekdays, date(year, 1, 1), date(year, 12, 31))
        return _Route(where, places, dates, weekdays[0])
    if header.weekday is not None and weekday is None:
        raise ValueError(f"{where}: no day of the week for {places[:60]!r}")
    dates: set[date] = set()
    for month, cell in days.items():
        dates |= _days(cell, year, month, where)
    if not dates:
        raise ValueError(f"{where}: places without dates: {places[:60]!r}")
    return _Route(where, places, dates, weekday)


def _table(sheet: Sheet, file_name: str) -> tuple[str, list[_Route]]:
    """A sheet's title and routes. Strict: text above the table that isn't its title or the
    phone number, rows without places, cells outside the table and text under it that isn't
    the reminder raise ValueError."""
    name, rows = sheet
    title = ""
    header: _Header | None = None
    year = 0
    routes: list[_Route] = []
    for number, cells in rows:
        where = f"{file_name} row {number}"
        filled = [(i, c) for i, c in enumerate(cells) if c]
        if not filled:
            continue
        text = " ".join(c for _, c in filled)
        if len(filled) == 1 and _NOTES.search(fold(text)):
            continue
        if header is None:
            if (header := _header(cells, where)) is not None:
                if not title:
                    raise ValueError(f"{where}: months without a title above them")
                continue
            if title or "grafikas" not in fold(text):
                raise ValueError(f"{where}: text above the table: {text[:60]!r}")
            title = text
            years = _years(title)
            if len(years) != 1:
                raise ValueError(f"{where}: no single year in the title {title[:80]!r}")
            year = years.pop()
            continue
        known = {header.places, *header.months, header.weekday}
        if outside := [c for i, c in filled if i not in known]:
            raise ValueError(f"{where}: a cell outside the table: {outside[0][:60]!r}")
        if not cells[header.places]:
            raise ValueError(f"{where}: a row without places: {text[:60]!r}")
        if (route := _route(cells, header, year, where)) is not None:
            routes.append(route)
    if header is None:
        raise ValueError(f"{file_name} ({name}): no table of months")
    return title, routes


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The schedules of a file's routes, one per route. Strict (see _table): also a title of
    another waste type or year than the paragraph's, too few routes, and dates mostly off the
    day of the week their row names raise ValueError; a few off it are warnings."""
    where = source.file_name
    found = [_table(sheet, where) for sheet in sheets(source, content) if sheet[1]]
    if not found:
        raise ValueError(f"{where}: no sheet")
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for title, routes in found:
        kinds = {kind for pattern, kind in _TITLE_KINDS if pattern.search(fold(title))}
        if kinds != {source.kind}:
            raise ValueError(f"{where}: the title {title[:80]!r} isn't of {source.kind}")
        if (linked := getattr(source, "year", 0)) and _years(title) != {linked}:
            raise ValueError(f"{where}: the title {title[:80]!r} isn't of {linked}")
        if len(routes) < MIN_ROUTES[source.kind]:
            raise ValueError(
                f"{where}: only {len(routes)} routes (expected at least {MIN_ROUTES[source.kind]})"
            )
        for route in routes:
            weekdays = Counter(d.weekday() for d in route.dates)
            if route.weekday is not None:
                off = sorted(d for d in route.dates if d.weekday() != route.weekday)
                if len(off) > (1 - SAME_WEEKDAY) * len(route.dates):
                    raise ValueError(
                        f"{route.where}: the dates aren't on {WEEKDAY_NAMES[route.weekday]}: "
                        "the wrong year or months?"
                    )
                warnings += [
                    f"{route.where}: {d} is a {WEEKDAY_NAMES[d.weekday()]}, not "
                    f"{WEEKDAY_NAMES[route.weekday]}"
                    for d in off
                ]
            area = Area(source.kind, route.places, LABEL, dates=route.dates, provider=PROVIDER_ID)
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[next(iter(weekdays))]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{route.where}: {route.places[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    return ParseResult(areas=list(areas.values()), warnings=warnings)


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """tratc.combine: next year's routes continue this year's that cover the same places."""
    return tratc.combine(parsed, registry, today, MUNICIPALITY)


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
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
    args = parser.parse_args(argv)
    # The folder of one provider, as raseiniai.py builds its own; a build that fails writes
    # nothing (the daily job keeps yesterday's folder).
    return raseiniai.run(args.out, args.keep_days, None, MUNICIPALITY, lambda _: SOURCE)


if __name__ == "__main__":
    raise SystemExit(main())

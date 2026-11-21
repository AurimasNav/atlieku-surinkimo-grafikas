"""Ukmergės rajonas: the schedules of UAB „Ukmergės autobusų parkas“, which empties the
containers of the individual houses of the whole municipality: mixed waste, paper and plastic
packaging, and glass.

The municipality's page links a PDF for the town and one for the district per period, made in
Excel; the schedules come in two periods a year, January to May and June to December:

    2026 m. sausio-gegužės mėn. Ukmergės miesto gyventojų komunalinių ir pakuočių atliekų
    surinkimo grafikas.                                              the town, January-May
    2026 m. birželio-gruodžio mėn. Ukmergės rajono gyventojų ...     the district, June-December

The files are found by these texts. The rounds of bulky waste (a page of their own, "DGA
surinkimas 2026 m. lapkritis-gruodis") aren't read, and the shared containers of the town's
apartment buildings have no file.

The district's file is a table of routes, each named after an eldership, with a row of days per
waste type under the months, and a table of the places of each route:

    Maršruto pavadinimas | Surenkamos atliekos  | Birželis | Liepa | ...
                         | Mišrios komunalinės  | 9, 23    | 7, 21 | ...
    Želvos               | Popieriaus, plastiko | 30       |       | ...
                         | Stiklo               |          | 21    | ...

    Maršrutas | Aptarnaujamos gyvenvietės ir kaimai
    Želvos    | Šešuolių sen.: Dvareliškių k.
              | Želvos sen.: Adomiškio k., Bajorų k., ...

The town's file has a table per route ("Gėlyno maršrutas", with the rows "Mišrių komunalinių
atliekų", "Plastiko, popieriaus pakuotės" and "Stiklo pakuotės"), then the streets of each route
("UKMERGĖS MIESTO SEN.: Aguonų g., ..., Vilniaus g. (nelyginiai nuo 35 iki 113), ...", and
"PABAISKO SEN. Varinės k.: Daigyno g., ..." for a village next to the town). The tables are read
from the positions of the words; pdfplumber's table finder splits the town's tables. A cell of
places too small for its text hides its last line, which the PDF still has, over the next cell
("Pivonijos sen.: Dastainiškio k., Stanislavuvkos k." of the Šešuolių route in January-May,
"Žalgirių k." of the Deltuvos route in June-December): a line that overlaps the next cell's first
line is the cell above's. Strict: months other than the link's, a day the month doesn't have, a
row of no waste type we read, routes without places or places without a route, and mixed waste
dates that mostly miss one working day raise.

A route is named "Želvos maršrutas: Šešuolių sen.: Dvareliškių k. Želvos sen.: ...", its places
read by Routes. Every file that still has dates to publish is read, so the next period's files
are read as soon as the page links them; until their months start, their routes continue those
in force that cover the same places (combine). When a period ends and nothing newer is linked,
its routes keep their last dates (build.current_rows), with a warning.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.ukmerge --out ../site/ukmerges-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot
from .dates import WEEKDAY_NAMES, month_end
from .kretinga import ScheduleFile, _Links, file_name, period
from .locations import _UPPER, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold
from .sratc import _continue

PAGE_URL = "https://www.ukmerge.lt/misrios-komunalines-atliekos/"
COMPANY = "UAB „Ukmergės autobusų parkas“"
LABEL = "Ukmergės r."  # every row's `district`
# The files of a period, by the words of their links: the town's and the district's, each
# running out on its own (SourceFile.group, build.current_rows).
GROUPS = {"ukmerges miesto": "town", "ukmerges rajono": "district"}
# The words of each file's title (folded).
TITLES = {"town": "ukmerges mieste", "district": "ukmerges raj"}
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"household": ("household", "packaging", "glass")}


# --- the page ----------------------------------------------------------------


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The schedules the page links, in its order, by the texts of their links: the town's or
    the district's, with the year and months they name ("2026 m. birželio-gruodžio mėn.", else
    the file's name); and warnings about schedules of no kind we read."""
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
        words = fold(described)
        if "grafik" not in fold(f"{described} {name}"):
            continue
        group = next((g for key, g in GROUPS.items() if key in words), None)
        if group is None or "komunalin" not in words:
            warnings.append(f"{name} ({described!r}): a schedule of no kind we read")
            continue
        (year, months), (name_year, name_months) = period(described), period(name)
        year, months = year or name_year, months or name_months
        if year is None:
            warnings.append(f"{name} ({described!r}): no year in its link or name; not read")
            continue
        files.append(ScheduleFile("household", url, name, group=group, year=year, months=months))
    return files, warnings


def select_files(
    files: list[ScheduleFile], today: date, keep_days: int = 31
) -> tuple[list[ScheduleFile], list[str]]:
    """Of the town's files and the district's, those with dates still to publish (their period
    ends at most `keep_days` before today), so the next period's file is read as soon as the
    page links it; if none runs to today, also the latest, whose routes keep their last dates.
    Of two files for one period, the one linked first: the page puts the newest on top. A page
    without a file of the town or of the district raises ValidationError."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    cutoff = today - timedelta(days=keep_days)
    for group in GROUPS.values():
        mine: dict[tuple[date, date], ScheduleFile] = {}
        for file in (f for f in files if f.group == group):
            if (newer := mine.get((file.start, file.end))) is not None:
                warnings.append(
                    f"{file.file_name}: not read, {newer.file_name} is a newer schedule of the "
                    f"{group} for {file.start} - {file.end}"
                )
                continue
            mine[(file.start, file.end)] = file
        if not mine:
            raise build.ValidationError(f"no schedule of the {group} on the page")
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

# A word of days: "9,", "23", "5;".
_DAY = re.compile(r"\d{1,2}[,;]?")
_DAYS = re.compile(r"\d{1,2}(?:\s*[,;]\s*\d{1,2})*\s*[,;]?")
# A route's title in the town's file: "Gėlyno maršrutas".
_TITLE = re.compile(r"(?P<name>\S+(?:\s\S+)?)\s+maršrutas", re.I)
# The district's table of places, its first row.
_PLACES_HEADER = "marsrutas aptarnaujamos gyvenvietes ir kaimai"
# Lines after the tables (folded): where to find new schedules, and when to put the containers
# out ("Pastaba: konteinerius vežimo dieną reikia ištraukti iki 7:00 val., ...").
_END = re.compile(r"^(?:visus naujus|https?|www|pastaba)\b")
# The waste type of a row by the words of its label (folded): "Mišrios komunalinės", "Mišrių
# komunalinių atliekų"; "Popieriaus, plastiko", "Plastiko, popieriaus pakuotės"; "Stiklo",
# "Stiklo pakuotės".
ROW_KINDS: tuple[tuple[str, Kind], ...] = (
    ("misri", "household"),
    ("popier", "packaging"),
    ("plastik", "packaging"),
    ("stikl", "glass"),
)
# Routes in a file, at least: in 2026 the district's had 14, the town's 5.
MIN_ROUTES = {"district": 10, "town": 4}
# Of a route's mixed waste dates, at least this share on one working day (holidays move a few):
# days in the wrong months or year fall on other weekdays.
SAME_WEEKDAY = 0.75


@dataclass
class _Line:
    top: float
    bottom: float
    words: list[dict]

    @property
    def text(self) -> str:
        return clean_text(" ".join(w["text"] for w in self.words))

    @property
    def middle(self) -> float:
        return (self.top + self.bottom) / 2


def _lines(words: list[dict]) -> list[_Line]:
    """Words in lines, top to bottom: a word within 3 points of a line's top is on it (the days
    of a row are a point above its label, a route's name a point below)."""
    lines: list[_Line] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and word["top"] - lines[-1].top <= 3:
            lines[-1].words.append(word)
            lines[-1].bottom = max(lines[-1].bottom, word["bottom"])
        else:
            lines.append(_Line(word["top"], word["bottom"], [word]))
    for line in lines:
        line.words.sort(key=lambda w: w["x0"])
    return lines


def _overlap(upper: _Line, lower: _Line) -> bool:
    """Two lines of a column written over each other (the next line of a cell is 15 points
    down, its letters 12 points high)."""
    return lower.top < upper.bottom - 2


def _name(words: list[dict]) -> str:
    """A route's name written on two lines: "Kazliškių-" and "Labeikių"."""
    text = clean_text(" ".join(w["text"] for w in sorted(words, key=lambda w: (w["top"], w["x0"]))))
    return re.sub(r"(?<=\w)-\s+", "-", text)


@dataclass
class _Months:
    """A row of months: where each month's column is."""

    centres: list[tuple[float, int]]  # (x, month)

    def month(self, x: float, where: str) -> int:
        xs = [c for c, _ in self.centres]
        half = (xs[-1] - xs[0]) / (len(xs) - 1) / 2
        edges = [xs[0] - half, *((a + b) / 2 for a, b in zip(xs, xs[1:], strict=False))]
        edges.append(xs[-1] + half)
        for (_, month), left, right in zip(self.centres, edges, edges[1:], strict=False):
            if left <= x < right:
                return month
        raise ValueError(f"{where}: days outside the months' columns, at {x:.0f}")


def _months(line: _Line, where: str, expected: list[int]) -> _Months | None:
    """The months of a line of their names ("Birželis Liepa ... Gruodis", in the district's
    file after "Surenkamos atliekos"), which must be the link's; None for another line."""
    found = [
        ((w["x0"] + w["x1"]) / 2, aratc.MONTHS[fold(w["text"])])
        for w in line.words
        if fold(w["text"]) in aratc.MONTHS
    ]
    if len(found) < 2:
        return None
    others = {fold(w["text"]) for w in line.words if fold(w["text"]) not in aratc.MONTHS}
    if others - {"surenkamos", "atliekos"}:
        raise ValueError(f"{where}: {sorted(others)} next to the months")
    if (months := [m for _, m in found]) != expected:
        raise ValueError(f"{where}: months {months}, the link says {expected[0]}-{expected[-1]}")
    return _Months(found)


def _row_kind(label: str, where: str) -> Kind:
    folded = fold(label)
    kinds = {kind for stem, kind in ROW_KINDS if stem in folded}
    if len(kinds) != 1:
        raise ValueError(f"{where}: a row of {sorted(kinds) or 'no waste type'}: {label!r}")
    return kinds.pop()


@dataclass
class _Route:
    name: str
    dates: dict[Kind, set[date]] = field(default_factory=dict)
    places: str = ""


@dataclass
class _Row:
    """A row of days: its waste type, its days and the words of routes' names next to it."""

    middle: float
    kind: Kind
    days: list[dict]
    names: list[dict]


def _rows(
    lines: list[_Line], months: _Months, year: int, where: str, boundary: float
) -> list[tuple[_Row, set[date]]]:
    """The rows of days under a row of months: a row per waste type, its label right of
    `boundary` (the routes' names are left of it), its days in the months' columns. Days a
    point or two off their label's line, and names on lines of their own, go to the row
    nearest them. The table's title ("pavadinimas", under "Maršruto") is left out."""
    rows: list[_Row] = []
    loose: list[tuple[_Line, list[dict], list[dict]]] = []
    for line in lines:
        days = [w for w in line.words if _DAY.fullmatch(w["text"])]
        names = [w for w in line.words if w not in days and w["x1"] <= boundary]
        labels = [w for w in line.words if w not in days and w["x1"] > boundary]
        if labels:
            label = clean_text(" ".join(w["text"] for w in labels))
            rows.append(_Row(line.middle, _row_kind(label, where), days, names))
        elif not rows and fold(line.text) == "pavadinimas":
            continue
        elif not rows and not days:
            raise ValueError(f"{where}: {line.text[:60]!r} above the rows of days")
        else:
            loose.append((line, days, names))
    if not rows:
        raise ValueError(f"{where}: months without rows of days")
    for line, days, names in loose:
        nearest = min(rows, key=lambda r: abs(r.middle - line.middle))
        if days and abs(nearest.middle - line.middle) > 6:
            raise ValueError(f"{where}: days of no row: {line.text[:60]!r}")
        nearest.days += days
        nearest.names += names
    result: list[tuple[_Row, set[date]]] = []
    for row in rows:
        cells: dict[int, list[str]] = defaultdict(list)
        for word in sorted(row.days, key=lambda w: w["x0"]):
            cells[months.month((word["x0"] + word["x1"]) / 2, where)].append(word["text"])
        dates: set[date] = set()
        for month, texts in cells.items():
            cell = " ".join(texts)
            if not _DAYS.fullmatch(cell):
                raise ValueError(f"{where}: unrecognised days {cell!r}")
            last = month_end(year, month).day
            for day in (int(d) for d in re.findall(r"\d+", cell)):
                if not 1 <= day <= last:
                    raise ValueError(f"{where}: month {month} of {year} has no day {day}")
                dates.add(date(year, month, day))
        result.append((row, dates))
    return result


def _add(route: _Route, kind: Kind, dates: set[date], where: str) -> None:
    if kind in route.dates:
        raise ValueError(f"{where}: two rows of {kind} for the {route.name} route")
    route.dates[kind] = dates


def _title(lines: list[_Line]) -> str:
    """The text above the first table (the file's title)."""
    return clean_text(" ".join(line.text for line in lines))


def _town(pdf, year: int, months: list[int], where: str) -> tuple[str, list[_Route]]:
    """The town's file: a table of days per route under its title, then the places of each
    route under its title."""
    lines = [line for page in pdf.pages for line in _lines(page.extract_words())]
    title: list[_Line] = []
    tables: list[tuple[_Route, _Months | None, list[_Line]]] = []
    places: list[tuple[str, list[_Line]]] = []
    current: list[_Line] | None = None  # the lines of the table or the places being read
    for i, line in enumerate(lines):
        if match := _TITLE.fullmatch(line.text):
            following = lines[i + 1] if i + 1 < len(lines) else None
            if following and _months(following, where, months):
                tables.append((_Route(match["name"]), None, []))
                current = tables[-1][2]
            else:
                places.append((match["name"], []))
                current = places[-1][1]
        elif found := _months(line, where, months):
            if not tables or tables[-1][1] is not None or tables[-1][2]:
                raise ValueError(f"{where}: months without a route's title above them")
            tables[-1] = (tables[-1][0], found, [])
            current = tables[-1][2]
        elif _END.match(fold(line.text)):
            current = None
        elif current is not None:
            current.append(line)
        elif tables or places:
            raise ValueError(f"{where}: text outside a route: {line.text[:60]!r}")
        else:
            title.append(line)
    routes: list[_Route] = []
    for route, columns, rows in tables:
        if columns is None:
            raise ValueError(f"{where}: no months under the {route.name} route's title")
        for row, dates in _rows(rows, columns, year, where, float("-inf")):
            _add(route, row.kind, dates, where)
        routes.append(route)
    for _, text in places:
        for upper, lower in zip(text, text[1:], strict=False):
            if _overlap(upper, lower):
                raise ValueError(f"{where}: lines written over each other: {lower.text[:60]!r}")
    _join(routes, [(name, " ".join(line.text for line in text)) for name, text in places], where)
    return _title(title), routes


def _district(pdf, year: int, months: list[int], where: str) -> tuple[str, list[_Route]]:
    """The district's file: the table of days of the routes, then the table of their places."""
    title: list[_Line] = []
    routes: list[_Route] = []
    places: list[tuple[str, list[_Line]]] = []
    for page in pdf.pages:
        lines = _lines(page.extract_words())
        if places or any(fold(line.text) == _PLACES_HEADER for line in lines):
            places += _places(page, where, first=not places)
            continue
        found = [(i, m) for i, line in enumerate(lines) if (m := _months(line, where, months))]
        if routes or len(found) != 1:
            many = "another table of days" if routes else f"{len(found)} rows of months"
            raise ValueError(f"{where} page {page.page_number}: {many}")
        (start, columns), *_ = found
        title += lines[:start]
        rows = lines[start + 1 :]
        end = next((i for i, line in enumerate(rows) if _END.match(fold(line.text))), len(rows))
        if not (surenkamos := [w for w in lines[start].words if fold(w["text"]) == "surenkamos"]):
            raise ValueError(f"{where}: no column of waste types")
        # A route is the rows from its mixed waste to the next route's, its name left of them.
        blocks: list[tuple[_Route, list[dict]]] = []
        for row, dates in _rows(rows[:end], columns, year, where, surenkamos[0]["x0"]):
            if row.kind == "household":
                blocks.append((_Route(""), []))
            elif not blocks:
                raise ValueError(f"{where}: {row.kind} before the first route's mixed waste")
            route, names = blocks[-1]
            names += row.names
            _add(route, row.kind, dates, where)
        for route, names in blocks:
            route.name = _name(names)
            if not route.name:
                raise ValueError(f"{where}: a route without a name")
            routes.append(route)
    joined: list[tuple[str, str]] = []
    for name, text in places:
        written = " ".join(line.text for line in text)
        if name:
            joined.append((name, written))
        elif joined:
            # The places of the last route of the page before, continued.
            joined[-1] = (joined[-1][0], f"{joined[-1][1]} {written}")
        else:
            raise ValueError(f"{where}: places of no route: {written[:60]!r}")
    _join(routes, joined, where)
    return _title(title), routes


def _places(page, where: str, first: bool) -> list[tuple[str, list[_Line]]]:
    """The rows of a page of the district's table of places: a route's name and the lines of
    its places. The words go to the cells of pdfplumber's table finder by their middles; a line
    a cell above hides over a row's first line is the cell above's. A row without a name
    continues the route above it, or on top of a page the last route of the page before (""
    for its name)."""
    tables = page.find_tables()
    if len(tables) != 1:
        raise ValueError(f"{where} page {page.page_number}: {len(tables)} tables of places")
    grid = [row.cells for row in tables[0].rows]
    if any(len(cells) != 2 or None in cells for cells in grid):
        raise ValueError(f"{where} page {page.page_number}: a table of places of other columns")
    rows: list[tuple[list[dict], list[dict]]] = [([], []) for _ in grid]
    for word in page.extract_words():
        middle = (word["top"] + word["bottom"]) / 2
        for (name, places), (cell, right) in zip(rows, grid, strict=True):
            if cell[1] <= middle < cell[3]:
                if word["x0"] >= right[0] - 1:
                    places.append(word)
                elif word["x1"] <= cell[2] + 1:
                    name.append(word)
                else:
                    raise ValueError(f"{where}: {word['text']!r} across two columns")
                break
    result = [(_name(name), _lines(places)) for name, places in rows]
    if first:
        header = f"{result[0][0]} {' '.join(line.text for line in result[0][1])}"
        if fold(header) != _PLACES_HEADER:
            raise ValueError(f"{where}: the table of places starts with {header[:60]!r}")
        result = result[1:]
    for i, (_, text) in enumerate(result):
        while len(text) > 1 and _overlap(text[0], text[1]):
            if i == 0:
                raise ValueError(f"{where}: lines written over each other: {text[1].text[:60]!r}")
            result[i - 1][1].append(text.pop(0))
    for _, text in result:
        for upper, lower in zip(text, text[1:], strict=False):
            if _overlap(upper, lower):
                raise ValueError(f"{where}: lines written over each other: {lower.text[:60]!r}")
    merged: list[tuple[str, list[_Line]]] = []
    for name, text in result:
        if not name and merged:
            merged[-1][1].extend(text)
        elif text:
            merged.append((name, text))
        else:
            raise ValueError(f"{where}: the {name} route without places")
    return merged


def _join(routes: list[_Route], places: list[tuple[str, str]], where: str) -> None:
    """The places of each route, by its name: the tables of days and of places must have the
    same routes, in the same order."""
    names = [route.name for route in routes]
    if [fold(name) for name, _ in places] != [fold(name) for name in names]:
        raise ValueError(f"{where}: routes {names}, their places {[name for name, _ in places]}")
    if len(set(names)) != len(names):
        raise ValueError(f"{where}: two routes of one name: {names}")
    for route, (_, text) in zip(routes, places, strict=True):
        route.places = clean_text(text)


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of one file: a row per route and waste type, named after the route and its
    places ("Želvos maršrutas: Šešuolių sen.: Dvareliškių k. Želvos sen.: ..."). Strict (see
    _rows, _places): also a title of another year than the link's or of the other file (the
    town's, "... UKMERGĖS MIESTE ...", or the district's, "... UKMERGĖS RAJ. ..."), too few
    routes, a route without mixed waste and mixed waste dates that mostly miss one working day
    raise ValueError."""
    where = source.file_name
    year = getattr(source, "year", 0)
    first, last = getattr(source, "months", None) or (1, 12)
    group = source.group
    if group not in MIN_ROUTES or not year:
        raise ValueError(f"{where}: a file of no period or area we know")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        read = _town if group == "town" else _district
        title, routes = read(pdf, year, list(range(first, last + 1)), where)
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title)}
    if years != {year} or TITLES[group] not in fold(title):
        raise ValueError(f"{where}: the title {title[:100]!r} isn't of the {group} in {year}")
    if len(routes) < MIN_ROUTES[group]:
        raise ValueError(f"{where}: only {len(routes)} routes (expected {MIN_ROUTES[group]})")
    areas: list[Area] = []
    for route in routes:
        if not route.dates.get("household"):
            raise ValueError(f"{where}: no mixed waste dates for the {route.name} route")
        name = f"{route.name} maršrutas: {route.places}"
        for kind, dates in route.dates.items():
            if not dates:
                continue
            weekdays = Counter(d.weekday() for d in dates)
            weekday, times = weekdays.most_common(1)[0]
            if kind == "household" and (times < SAME_WEEKDAY * len(dates) or weekday > 4):
                raise ValueError(
                    f"{where}: the dates of the {route.name} route aren't on one working day: "
                    "the wrong year or months?"
                )
            area = Area(kind, name, LABEL, provider=PROVIDER_ID, dates=dates)
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekday]
            areas.append(area)
    return ParseResult(areas=areas)


# --- the places ------------------------------------------------------------------

_STREET = r"(?:g|skg|al|pl|tak|a)"
# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Želvos maršrutas: ...": the route's name, not a place.
    (re.compile(r"^[^:]*?\bmaršrutas\s*:\s*"), ""),
    # Some houses of a street: "Vilniaus g. (nelyginiai nuo 35 iki 113)", "Nuotekų g. ( lyginiai
    # nuo 2 iki 46, nelyginiai nuo 1 iki 47)", "Šlaitų g. (nuo 13 iki galo)": one more choice
    # for that street, as a house number tells aratc.Routes.
    (re.compile(rf"\b({_STREET})\.\s*\(\s*(?:(?:ne)?lygin\w*\s+)?nuo\b[^()]*\)"), r"\1. 0"),
    # 'SB "Vienybė" Sarapų k.': a comma left out after a garden community.
    (re.compile(rf"(\bSB\s*[„“\"][^„“”\"]*[“”\"])\s+(?=[{_UPPER}])"), r"\1, "),
)


class Routes(raseiniai.Routes):
    """Reads the places of the routes as raseiniai.Routes reads Raseinių r.'s (aratc.Routes):
    the settlements of each eldership's section ("Želvos sen.: Adomiškio k., ..., Želvos mstl.,
    ..."), the streets of the town in its eldership's ("UKMERGĖS MIESTO SEN.: Aguonų g., ...")
    and those of a village after it ("PABAISKO SEN. Varinės k.: Daigyno g., ..."). Some houses
    of a street ("Vilniaus g. (nelyginiai nuo 35 iki 113)") make the route one more choice for
    the street, so the app asks; "Vaitkūnų k. (Sodžiaus g.)" is that street only. The garden
    communities ('SB „Pušelė“', 'SB "Armona"') aren't places of the register: reported.

    No street gets "no pickup" (build_locations): the town's file lists the streets of its
    private houses, the shared containers of the apartment buildings have no file, and nothing
    says a street has none. A street no route names is left to the app, which offers the
    place's routes."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        # aratc.Routes for this municipality (raseiniai.Routes' own sets Raseinių r.'s).
        self.municipalities = (MUNICIPALITY,)
        aratc.Routes.__init__(self, index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return text


PROVIDER_ID = "ukmerge"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=COMPANY,
    url=PAGE_URL,
    # Every eldership of the municipality (register names).
    elderships=frozenset(
        {
            "Deltuvos",
            "Lyduokių",
            "Pabaisko",
            "Pivonijos",
            "Siesikų",
            "Taujėnų",
            "Ukmergės miesto",
            "Veprių",
            "Vidiškių",
            "Šešuolių",
            "Želvos",
            "Žemaitkiemio",
        }
    ),
    kinds=("household", "packaging", "glass"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.UKMERGE_MUNICIPALITY,
    snapshot.UKMERGE_REGISTRY_FILE,
    snapshot.UKMERGE_ADDRESSES_FILE,
    # 2026: 19 routes (14 of the district, 5 of the town), each with mixed waste, packaging and
    # glass, which gave a schedule to 364 of the 556 settlements: every one with an address.
    min_areas={"household": 14, "packaging": 14, "glass": 14},
    min_household_places=280,
    # About 17,600 addresses in 2026, 5,800 of them in the town.
    min_address_points=12_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- this period and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins the routes of the files of later periods to those of the period in force, in place,
    the town's and the district's each on their own (sratc._continue, as kretinga.combine joins
    Kretingos r.'s half years): a route of the next period that covers the same places as one in
    force gives it its dates; the rest wait, with a warning, until their period starts. Routes
    of earlier periods are dropped.

    Files of one area whose periods overlap raise ValueError (select_files reads one file per
    period). An area whose files have all ended keeps its routes, with their last dates
    (build.current_rows), and a warning; so does one with no file for today, whose next one has
    started early."""
    warnings: list[str] = []
    groups: dict = defaultdict(lambda: defaultdict(list))
    for group in GROUPS.values():
        files = sorted(
            ((s, r) for s, r in parsed if s.group == group and r.areas),
            key=lambda p: p[0].start,
        )
        for (source, _), (other, _) in zip(files, files[1:], strict=False):
            if other.start <= source.end:
                raise ValueError(
                    f"{source.file_name} ({source.start} - {source.end}) and {other.file_name} "
                    f"({other.start} - {other.end}) overlap"
                )
        if not files:
            continue
        if (ended := max(s.end for s, _ in files)) < today:
            warnings.append(f"the schedule of the {group} ended on {ended}; no newer one is read")
        elif (first := min(s.start for s, _ in files)) > today:
            warnings.append(f"no schedule of the {group} for today; the next starts on {first}")
        for source, result in files:
            for area in result.areas:
                groups[(f"{LABEL} ({group})", area.kind)][source.start].append((result, area))
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

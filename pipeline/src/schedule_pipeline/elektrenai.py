"""Elektrėnų savivaldybė: the schedules of UAB „Elektrėnų komunalinis ūkis“ (eku.lt), which
empties the containers of the individual houses of the whole municipality: mixed waste, paper and
plastic packaging, and glass.

The schedules are web pages, not files. The company's page "Atliekų išvežimo grafikai" lists a
page per year ("2025 m.", "2026 m."), and each year's page lists its pages in turn:

    Atliekų išvežimo grafikai                          START_URL
      2026 m.
        Rūšiuoju buitinės atliekas                     households that sort their waste
          Buitinių atliekų išvežimo grafikas           mixed waste
          Antrinių (rūšiuojamų) atliekų ...            paper and plastic packaging, and glass
        Nerūšiuoju buitinių atliekų                    those that don't: not read
        Didelių gabaritų atliekų surinkimo grafikai    bulky waste: not read

The pages are found by the texts of these links. Only the schedules of households that sort are
read: a household that doesn't sort has its mixed waste emptied more often, on the same days and
more, and its page leaves out some villages. The rounds of bulky waste, by registration, aren't
read, and the shared containers of apartment buildings have no page.

A schedule page has a section per route, its places as its title ("Abromiškių k., Geibonių k.,
...", "Vievio seniūnijos Ąžuolinės, Alesninkų, ... kaimai", "Vievio miesto individualūs namai")
and a table of its days, in one of these layouts:

    2026 m. | Dienos       Mėnuo  | Popierius-Plastikas | Stiklas     STIKLAS    | PLASTIKAS IR ...
    Sausis  | 08 | 22      Sausis | 22 d.               | -                      | 2026-01-27
    Vasaris | 05 | 19      Kovas  | 26 d.               | 17 d.       2026-02-04 | 2026-02-24

The tables are read with the standard library's HTML parser. Strict: a column of no waste type,
months out of order, a cell that isn't days or a date of the page's year, a day the month
doesn't have, a page or table of another year, and text next to a table other than the notes
2026 had ("Rūšiuojamų atliekų išvežimas nemokamas.", and that one village's packaging is
collected a day earlier: its own row) raise.

A route is named by its places as the page writes them, read by Routes. The towns' individual
houses ("Elektrėnų individualių namų kvartalo", "Vievio miesto individualūs namai") are the
town; a street of a town in another route ("Marių g. Elektrėnų m.") is that route's. Next year's
page is read as soon as it is listed; its routes continue this year's that cover the same places
(tratc.combine). A year that has ended keeps its routes' last dates until the next is read.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.elektrenai --out ../site/elektrenu-sav
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from . import aratc, build, http, maatc, raseiniai, snapshot, tratc
from .dates import WEEKDAY_NAMES
from .locations import _UPPER, _WORD, Index, _one_off, _typo
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

# The company's list of the years' pages; the years' pages and theirs are found by their links.
START_URL = "https://www.eku.lt/atlieku-ir-teritoriju-tvarkymas/atlieku-isvezimo-grafikai/569"
COMPANY = "UAB „Elektrėnų komunalinis ūkis“"
LABEL = "Elektrėnų sav."  # every row's `district`
# Every eldership of the municipality (register names).
ELDERSHIPS = frozenset(
    {
        "Beižionių",
        "Elektrėnų",
        "Gilučių",
        "Kazokiškių",
        "Kietaviškių",
        "Pastrėvio",
        "Semeliškių",
        "Vievio",
    }
)
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}


# --- the pages ---------------------------------------------------------------


@dataclass
class _Cell:
    parts: list[str] = field(default_factory=list)
    colspan: int = 1

    @property
    def text(self) -> str:
        return clean_text("".join(self.parts))


@dataclass
class _Topic:
    """A section of a schedule page: a route's places and its table."""

    title: str
    tables: list[list[list[_Cell]]] = field(default_factory=list)
    text: list[str] = field(default_factory=list)  # paragraphs next to the table


class _Page(HTMLParser):
    """What the reader needs of a page of eku.lt, all in its <main class="main_content">: the
    title (<h1 class="main_title">), the breadcrumbs, the links of the list of pages under it
    (<div class="childlist_cont">), the sections of a schedule page (<div class="topic-title">
    with the title in an <h4>, then <div class="topic-description"> with the table and notes),
    and any other text of the content (<div class="content_template">)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.crumbs: list[str] = []
        self.children: list[tuple[str, str]] = []  # (href, text)
        self.topics: list[_Topic] = []
        self.loose: list[str] = []  # text of the content outside the lists and sections
        self._main = False
        self._divs: list[set[str]] = []  # the classes of the open <div>s
        self._capture: list[str] | None = None  # the text being read for a title or link
        self._target = ""  # what the captured text is: "h1", "crumb", "child", "topic"
        self._href = ""
        self._table: list[list[_Cell]] | None = None
        self._cell: _Cell | None = None
        self._paragraph: list[str] = []

    @classmethod
    def read(cls, content: bytes | str) -> _Page:
        page = cls()
        page.feed(content.decode("utf-8") if isinstance(content, bytes) else content)
        page.close()
        page._end_paragraph()
        return page

    def _inside(self, name: str) -> bool:
        return any(name in classes for classes in self._divs)

    def _end_paragraph(self) -> None:
        text = clean_text("".join(self._paragraph))
        self._paragraph = []
        if not text:
            return
        if self._inside("topic-description") and self.topics:
            self.topics[-1].text.append(text)
        else:
            self.loose.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "main" and "main_content" in classes:
            self._main = True
        if not self._main:
            return
        if tag == "div":
            if "topic-title-wrapper" in classes:
                self._end_paragraph()
                self.topics.append(_Topic(""))
            self._divs.append(classes)
        elif tag == "h1" and "main_title" in classes:
            self._capture, self._target = [], "h1"
        elif tag == "h4" and self._inside("topic-title"):
            self._capture, self._target = [], "topic"
        elif tag == "a" and self._inside("breadcrumbs"):
            self._capture, self._target = [], "crumb"
        elif tag == "span" and "last_breadcrumb" in classes:
            self._capture, self._target = [], "crumb"
        elif tag == "a" and self._inside("childlist_cont"):
            self._capture, self._target, self._href = [], "child", attributes.get("href") or ""
        elif tag == "table" and self._inside("topic-description"):
            if self._table is not None:
                raise ValueError("a table in a table")
            self._end_paragraph()
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._table.append([])
        elif tag in ("td", "th") and self._table is not None:
            if not self._table:
                raise ValueError("a cell outside a row")
            if int(attributes.get("rowspan") or 1) != 1:
                raise ValueError("a cell of several rows")
            self._cell = _Cell(colspan=int(attributes.get("colspan") or 1))
            self._table[-1].append(self._cell)
        elif tag in ("p", "br", "li") and self._cell is not None:
            self._cell.parts.append(" ")
        elif tag in ("p", "br", "li", "h2", "h3", "h5"):
            self._end_paragraph()

    def handle_endtag(self, tag: str) -> None:
        if not self._main:
            return
        if tag == "main":
            self._end_paragraph()
            self._main = False
        elif tag == "div" and self._divs:
            if self._inside("topic-description") or self._inside("content_template"):
                self._end_paragraph()
            self._divs.pop()
        elif tag in ("h1", "h4", "a", "span") and self._capture is not None:
            if tag == {"h1": "h1", "topic": "h4", "child": "a"}.get(self._target, tag):
                self._captured()
        elif tag in ("td", "th"):
            self._cell = None
        elif tag == "table" and self._table is not None:
            if not self.topics or self.topics[-1].title == "":
                raise ValueError("a table without a title")
            self.topics[-1].tables.append(self._table)
            self._table = None
        elif tag in ("p", "li") and self._cell is None:
            self._end_paragraph()

    def _captured(self) -> None:
        text = clean_text("".join(self._capture or []))
        if self._target == "h1":
            self.title = text
        elif self._target == "crumb":
            self.crumbs.append(text)
        elif self._target == "child":
            self.children.append((self._href, text))
        elif self._target == "topic":
            self.topics[-1].title = text
        self._capture = None

    def handle_data(self, data: str) -> None:
        if not self._main:
            return
        if self._capture is not None:
            self._capture.append(data)
        elif self._cell is not None:
            self._cell.parts.append(data)
        elif self._table is not None:
            if data.strip():
                raise ValueError(f"text in a table outside its cells: {data.strip()[:40]!r}")
        elif self._inside("topic-description") or (
            self._inside("content_template") and not self._inside("childlist_cont")
        ):
            self._paragraph.append(data)


@dataclass
class SchedulePage(SourceFile):
    """A schedule page of a year: `kind` household (mixed waste) or packaging (packaging and
    glass); `title` is its link's text, which must be its title."""

    year: int = 0
    title: str = ""


# "2026 m.": a year's page.
_YEAR = re.compile(r"(20\d{2})\s*m\.?")
# The pages of a year's page (folded): the schedules of households that sort, of those that
# don't, and of bulky waste.
_SORTING = re.compile(r"rusiuoju\b")
_NOT_READ = re.compile(r"nerusiuoju\b|dideliu gabaritu")
# The schedules of households that sort (folded): mixed waste, packaging and glass.
_SCHEDULES: tuple[tuple[re.Pattern[str], Kind], ...] = (
    (re.compile(r"buitiniu atlieku\b"), "household"),
    (re.compile(r"antriniu\b"), "packaging"),
)


class NotListed(build.ValidationError):
    """A year's page without the schedules of households that sort, or without one of them."""


def find_years(page: _Page, url: str = START_URL) -> tuple[list[tuple[int, str]], list[str]]:
    """The years' pages the list links ("2026 m."), with their URLs, and warnings about other
    links."""
    years: list[tuple[int, str]] = []
    warnings: list[str] = []
    for href, text in page.children:
        match = _YEAR.fullmatch(text)
        if match:
            years.append((int(match[1]), urljoin(url, href)))
        else:
            warnings.append(f"{page.title}: a page of no year: {text!r}; not read")
    if not years:
        raise build.ValidationError(f"{url}: no year's page")
    return years, warnings


def select_years(
    years: list[tuple[int, str]], today: date
) -> tuple[list[tuple[int, str]], list[str]]:
    """This year's page and later ones; without, the newest (its routes keep their last dates).
    Two pages of one year raise ValidationError."""
    found = [year for year, _ in years]
    if len(set(found)) != len(found):
        raise build.ValidationError(f"two pages of one year: {sorted(found)}")
    chosen = [(y, u) for y, u in years if y >= today.year] or [max(years)]
    warnings = [] if today.year in {y for y, _ in chosen} else [f"no page of {today.year}"]
    return sorted(chosen), warnings


def _check(page: _Page, text: str, year: int, url: str) -> None:
    """A page must be titled as its link and be under its year's page (its breadcrumbs)."""
    if fold(page.title) != fold(text):
        raise ValueError(f"{url}: the page of {text!r} is titled {page.title!r}")
    if not any(_YEAR.fullmatch(crumb) and int(crumb[:4]) == year for crumb in page.crumbs):
        raise ValueError(f"{url}: {page.title!r} isn't under the page of {year} ({page.crumbs})")


def find_sorting(page: _Page, year: int, url: str) -> tuple[str, list[str]]:
    """The page of the schedules of households that sort, linked by a year's page."""
    found: list[tuple[str, str]] = []
    warnings: list[str] = []
    for href, text in page.children:
        folded = fold(text)
        if _SORTING.match(folded):
            found.append((urljoin(url, href), text))
        elif not _NOT_READ.match(folded):
            warnings.append(f"{year} m.: a page of no kind we read: {text!r}")
    if len(found) != 1:
        raise NotListed(f"{year} m.: {len(found)} pages of the households that sort their waste")
    return found[0][0], warnings


def find_schedules(page: _Page, year: int, url: str) -> tuple[list[SchedulePage], list[str]]:
    """The mixed waste page and the packaging page of households that sort."""
    found: list[SchedulePage] = []
    warnings: list[str] = []
    for href, text in page.children:
        kinds = [kind for pattern, kind in _SCHEDULES if pattern.match(fold(text))]
        if not kinds:
            warnings.append(f"{year} m.: a page of no kind we read: {text!r}")
            continue
        address = urljoin(url, href)
        found.append(SchedulePage(kinds[0], address, f"{year} m. {text}", year=year, title=text))
    if sorted(f.kind for f in found) != ["household", "packaging"]:
        raise NotListed(
            f"{year} m.: schedules of {sorted(f.kind for f in found)}, expected mixed waste "
            "and packaging"
        )
    return found, warnings


def _year_pages(
    year: int, url: str, get: Callable[[str], bytes]
) -> tuple[list[SchedulePage], list[str]]:
    page = _Page.read(get(url))
    _check(page, f"{year} m.", year, url)
    sorting_url, warnings = find_sorting(page, year, url)
    sorting = _Page.read(get(sorting_url))
    text = next(t for h, t in page.children if urljoin(url, h) == sorting_url)
    _check(sorting, text, year, sorting_url)
    schedules, more = find_schedules(sorting, year, sorting_url)
    return schedules, warnings + more


def download(
    today: date, keep_days: int, get: Callable[[str], bytes] | None = None
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The schedule pages of this year and later ones (or the newest year's). A later year's
    page that doesn't list its schedules yet is left out, with a warning."""
    get = get or _get
    years, warnings = find_years(_Page.read(get(START_URL)))
    chosen, notes = select_years(years, today)
    warnings += notes
    sources: list[tuple[SourceFile, bytes]] = []
    for year, url in chosen:
        try:
            pages, more = _year_pages(year, url, get)
        except NotListed as error:
            if year <= today.year or year == chosen[0][0]:
                raise
            warnings.append(f"{error}; the page of {year} isn't read yet")
            continue
        warnings += more
        sources += [(page, get(page.url)) for page in pages]
    return sources, warnings


def _get(url: str) -> bytes:
    # With the project's own user agent (http.USER_AGENT).
    return http.get(url, timeout=60)


# --- the tables ------------------------------------------------------------------

# A column's waste type by the words of its header (folded): "Dienos" (the days of mixed
# waste), "Popierius-Plastikas", "PLASTIKAS IR POPIERIUS", "Stiklas".
_COLUMNS: tuple[tuple[str, Kind], ...] = (
    ("dienos", "household"),
    ("popier", "packaging"),
    ("plastik", "packaging"),
    ("stikl", "glass"),
)
# The first column of a table of months: "2026 m.", "2026" (the non-sorters' page), "Mėnuo".
_MONTHS_COLUMN = re.compile(r"(?:(?P<year>20\d{2})(?: m)?|menuo)")
# A cell of days: "08", "22 d.", "8, 22"; none: "", "-".
_DAYS = re.compile(r"\d{1,2}(?:\s*d\.?)?(?:\s*[,;]\s*\d{1,2}(?:\s*d\.?)?)*")
_NONE = re.compile(r"[-–]?")
# A cell of a table of dates: "2026-01-27".
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# The notes next to a table: what 2026's had.
_NOTES = (
    re.compile(r"Rūšiuojamų atliekų išvežimas nemokamas\.?", re.I),
    re.compile(r"Neteisingai išrūšiuotos atliekos nebus imamos\.?", re.I),
    re.compile(r"Tel\.\s*pasiteirauti\s*\+?[\d\s]+", re.I),
)
# "Pastaba: iš Dumbliko kaimo plastmasė ir popierius bus renkami diena anksčiau, nei nurodyta
# grafike": that village's packaging is collected the day before the route's.
_DAY_EARLIER = re.compile(
    r"Pastaba\s*:\s*iš\s+(?P<village>\w+)\s+kaimo\s+plastmasė\s+ir\s+popierius\s+bus\s+"
    r"renkami\s+diena\s+anksčiau\s*,?\s+nei\s+nurodyta\s+grafike\s*\.?",
    re.I,
)
# "Vievio seniūnijos ...": a route of an eldership's villages.
_OF_ELDERSHIP = re.compile(rf"(?P<eldership>{_WORD})\s+seniūnijos\s")
# Of the dates of a table, at least this share on working days: a table of another year has
# about two in seven on weekends.
WORKING_DAYS = 0.9


def _day(year: int, month: int, day: int, where: str) -> date:
    try:
        return date(year, month, day)
    except ValueError as error:
        raise ValueError(f"{where}: day {day} of {year}-{month:02}") from error


def _table(rows: list[list[_Cell]], year: int, kinds: tuple[Kind, ...], where: str):
    """The dates of each waste type of a table: a row per month under a header of the year or
    "Mėnuo" and the columns' waste types, or rows of dates under a header of waste types."""
    rows = [row for row in rows if any(cell.text for cell in row)]
    if len(rows) < 2:
        raise ValueError(f"{where}: a table without dates")
    header = [cell.text for cell in rows[0] for _ in range(cell.colspan)]
    columns: list[Kind | None] = []  # None: the months
    for i, text in enumerate(header):
        months = _MONTHS_COLUMN.fullmatch(fold(text))
        found = {kind for stem, kind in _COLUMNS if stem in fold(text)}
        if i == 0 and months:
            if months["year"] and int(months["year"]) != year:
                raise ValueError(f"{where}: a table of {months['year']} on the page of {year}")
            columns.append(None)
        elif len(found) == 1:
            columns.append(found.pop())
        else:
            raise ValueError(f"{where}: a column of {text!r}")
    # Mixed waste in one or more columns ("Dienos" over two), the others in one each.
    found_kinds = [kind for kind in columns if kind is not None]
    if set(found_kinds) != set(kinds) or any(
        found_kinds.count(kind) > 1 for kind in found_kinds if kind != "household"
    ):
        raise ValueError(f"{where}: columns {header}, expected {list(kinds)}")
    dates: dict[Kind, set[date]] = defaultdict(set)
    months_read: list[int] = []
    for row in rows[1:]:
        if any(cell.colspan != 1 for cell in row) or len(row) != len(columns):
            raise ValueError(f"{where}: a row of {[c.text for c in row]}, columns {header}")
        cells = [cell.text for cell in row]
        if columns[0] is None:
            month = aratc.MONTHS.get(fold(cells[0]))
            if month is None:
                raise ValueError(f"{where}: a row of {cells[0]!r}, not a month")
            months_read.append(month)
        for kind, cell in zip(columns, cells, strict=True):
            if kind is None or _NONE.fullmatch(cell):
                continue
            if columns[0] is None:
                if not _DAYS.fullmatch(cell):
                    raise ValueError(f"{where}: not days: {cell!r}")
                for day in re.findall(r"\d+", cell):
                    dates[kind].add(_day(year, month, int(day), where))
            elif iso := _ISO.fullmatch(cell):
                when = _day(*(int(part) for part in iso.groups()), where)
                if when.year != year:
                    raise ValueError(f"{where}: {cell} on the page of {year}")
                dates[kind].add(when)
            else:
                raise ValueError(f"{where}: not a date: {cell!r}")
    if columns[0] is None and months_read != list(range(1, 13)):
        raise ValueError(f"{where}: months {months_read}")
    for kind in kinds:
        if not dates[kind]:
            raise ValueError(f"{where}: no {kind} dates")
    every = [d for found in dates.values() for d in found]
    if sum(d.weekday() < 5 for d in every) < WORKING_DAYS * len(every):
        raise ValueError(f"{where}: dates on weekends: the wrong year?")
    return dates


def _earlier(topic: _Topic, where: str) -> str | None:
    """The notes next to a table: the village whose packaging is collected a day earlier, if
    one has; known notes are left out, others raise ValueError."""
    village = None
    for text in topic.text:
        if earlier := _DAY_EARLIER.fullmatch(text):
            if village:
                raise ValueError(f"{where}: two notes of a day earlier")
            village = earlier["village"]
            continue
        rest = text
        for pattern in _NOTES:
            rest = pattern.sub("", rest)
        if rest.strip():
            raise ValueError(f"{where}: a note next to the table: {text[:80]!r}")
    return village


def _without(title: str, village: str, where: str) -> str:
    """A route's title without a village of its list ("Vievio seniūnijos ..., Dumbliko, ...")."""
    found = re.subn(rf"\b{re.escape(village)}\s*,\s*", "", title)
    if found[1] != 1:
        found = re.subn(rf",\s*{re.escape(village)}(?=\s+kaim)", "", title)
    if found[1] != 1:
        raise ValueError(f"{where}: {village} isn't in the list of {title[:60]!r}")
    return found[0]


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of a schedule page: one per route and waste type, named by the route's places
    as the page writes them. A village whose packaging is collected a day earlier gets a row of
    its own ("Vievio seniūnijos Dumbliko kaimas"), and the route's packaging row leaves it out.
    Strict (_table, _earlier): also a page titled otherwise than its link, of another year, with
    text outside its sections, or two sections of one title raise ValueError."""
    year = getattr(source, "year", 0)
    where = source.file_name
    page = _Page.read(content)
    _check(page, getattr(source, "title", ""), year, source.url)
    if page.loose:
        raise ValueError(f"{where}: text outside the schedules: {page.loose[0][:80]!r}")
    if not page.topics:
        raise ValueError(f"{where}: no schedules")
    kinds = FILE_KINDS.get(source.kind, (source.kind,))
    areas: dict[str, Area] = {}
    for topic in page.topics:
        title = topic.title.rstrip(" ,;")
        here = f"{where}: {title[:40]!r}"
        if not title or len(topic.tables) != 1:
            raise ValueError(f"{here}: {len(topic.tables)} tables")
        dates = _table(topic.tables[0], year, kinds, here)
        village = _earlier(topic, here)
        rows = [(kind, title, found) for kind, found in sorted(dates.items())]
        if village:
            if "packaging" not in dates:
                raise ValueError(f"{here}: a note of packaging next to a table without it")
            eldership = _OF_ELDERSHIP.match(title)
            if not eldership:
                raise ValueError(f"{here}: a village of no eldership: {village}")
            rows = [r for r in rows if r[0] != "packaging"] + [
                ("packaging", _without(title, village, here), dates["packaging"]),
                (
                    "packaging",
                    f"{eldership['eldership']} seniūnijos {village} kaimas",
                    {d - timedelta(days=1) for d in dates["packaging"]},
                ),
            ]
        for kind, name, found in rows:
            area = Area(kind, name, LABEL, provider=PROVIDER_ID, dates=set(found))
            weekdays = {d.weekday() for d in found}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            if area.id in areas:
                raise ValueError(f"{here}: two {kind} schedules of one route")
            areas[area.id] = area
    return ParseResult(list(areas.values()))


# --- the places ------------------------------------------------------------------

_STREET = r"(?:g|skg|al|pl|tak|a)"
_PLACE = rf"{_WORD}(?:\s+{_WORD})*\s+(?:k|vs|mstl|m)\."
# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Sen. Kietaviškių k.", "Klon. Mijaugonių k.".
    (re.compile(rf"\bSen\.\s*(?=[{_UPPER}])"), "Senųjų "),
    (re.compile(rf"\bKlon\.\s*(?=[{_UPPER}])"), "Kloninių "),
    # "Antakalnio VS.".
    (re.compile(r"(?<=\w)\s+VS\.(?=\s|[,;:(]|$)"), " vs."),
    # A letter left over: "G Pievaičių VS.", "L Liaukiškių k." (2025).
    (re.compile(rf"(?<![\w.])[{_UPPER}]\s+(?=[{_UPPER}][a-ząčęėįšųūž])"), ""),
    # A town's individual houses: "Elektrėnų individualių namų kvartalo", "Vievio miesto
    # individualūs namai": the town.
    (
        re.compile(rf"\b({_WORD})\s+(?:miesto\s+)?individual\w*\s+nam\w*(?:\s+kvartal\w*)?"),
        r"\1 m.",
    ),
    # A street of a town before it: "Marių g. Elektrėnų m." -> "Elektrėnų m. (Marių g.)".
    (re.compile(rf"\b((?:{_WORD}\s+)+?{_STREET}\.)\s+({_WORD}\s+m\.)"), r"\2 (\1)"),
    # A garden community: 'Sodų "Klevas"', 'sodų „Klevas“:', 'Sodai „Klevas“'. Not a place of
    # the register: reported.
    (re.compile(r"\b[Ss]od(?:ai|ų)\s*([„“\"][^„“”\"]*[“”\"])\s*:?"), r"SB \1,"),
    # A comma left out after a street: "Perkūnkiemio g. Alinkos k.".
    (re.compile(rf"(?<=\bg\.)\s+(?=[{_UPPER}])"), ", "),
    # The streets of a village after a dash: "Abromiškių k. – Orio g., Perkūnkiemio g.": in
    # brackets, closed after the last street (aratc._close).
    (re.compile(r"\b(k|vs|mstl)\.\s*[–—]\s*"), rf"\1. {aratc._OPEN}"),
    # "Vievio seniūnijos Ąžuolinės, ..., Šaltupės kaimai": the eldership's villages.
    (re.compile(r"\s+kaim(?:ai|as)\b\.?"), ""),
)
# A village with its eldership in brackets: "Navasiolkų k., (Semeliškių sen.)", "Navasiolkų
# k.(Beižonių sen.)", "Senųjų Migūčionių k. (Gilučių sen.)".
_IN_ELDERSHIP = re.compile(
    rf"(?P<place>{_PLACE})\s*,?\s*\(\s*(?P<eldership>{_WORD})\s+sen\.?\s*\)\s*,?"
)


class Routes(aratc.Routes):
    """Reads the places of the routes as aratc.Routes reads Alytus county's: settlements in the
    genitive with their type, looked up in the whole municipality ("Abromiškių k., Geibonių k.,
    Pievaičių VS., ..."), or in the eldership a list or a bracket names ("Vievio seniūnijos
    Ąžuolinės, Alesninkų, ... kaimai", "Navasiolkų k. (Semeliškių sen.)"); a town's individual
    houses ("Elektrėnų individualių namų kvartalo") are the town, and "Marių g. Elektrėnų m." and
    "Abromiškių k. – Orio g., Perkūnkiemio g." those streets of the town or village. Two names
    before one type ("Pastrėvio Peliūnų k.") are two settlements, if each is one. The garden
    community ('Sodų "Klevas"') isn't a place of the register: reported.

    No street gets "no pickup" (build_locations): the pages name no street of the towns but
    Marių g. of Elektrėnai, and nothing says a street has none."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        # The villages with their eldership in brackets go to sections of their elderships, at
        # the end: aratc.Routes reads the places before any section in the whole municipality.
        sections: list[str] = []

        def section(match: re.Match[str]) -> str:
            sections.append(f"{match['eldership']} sen.: {match['place']}")
            return ", "

        text = _IN_ELDERSHIP.sub(section, text)
        return "; ".join([text.strip(" ,;"), *sections])

    def district(self, name: str) -> str | None:
        """aratc.Routes' district, or the only one a letter off: "Beižonių", "Smeliškių"."""
        found = super().district(name)
        if found:
            return found
        key = fold(name)
        close = [
            d for d in self.municipality.elderships if _one_off(key, fold(d)) or _typo(key, fold(d))
        ]
        return close[0] if len(close) == 1 else None

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        """aratc.Routes' settlements; two names before one type, with a comma left out
        ("Pastrėvio Peliūnų k."), are two settlements if each is one."""
        found = super().settlements(name, numerals, kind, district)
        words = name.split()
        if found or numerals or len(words) < 2:
            return found
        split = [super(Routes, self).settlements(word, None, kind, district) for word in words]
        return [s for hits in split for s in hits] if all(split) else []


PROVIDER_ID = "elektrenai"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=COMPANY,
    url=START_URL,
    elderships=ELDERSHIPS,
    kinds=("household", "packaging", "glass"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.ELEKTRENAI_MUNICIPALITY,
    snapshot.ELEKTRENAI_REGISTRY_FILE,
    snapshot.ELEKTRENAI_ADDRESSES_FILE,
    # 2026: 13 mixed waste routes and 9 of packaging and glass (and Dumblikas' packaging).
    min_areas={"household": 10, "packaging": 7, "glass": 7},
    min_household_places=150,
    # About 10,900 addresses in 2026.
    min_address_points=7_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- the source ------------------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Next year's routes continue this year's that cover the same places (tratc.combine);
    too few routes in next year's pages raise ValueError."""
    return tratc.combine(parsed, registry, today, MUNICIPALITY)


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MUNICIPALITY.min_areas,
    MUNICIPALITY.min_household_places,
    FILE_KINDS,
    combine,
)


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

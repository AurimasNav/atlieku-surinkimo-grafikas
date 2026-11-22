"""Kupiškio rajonas: the schedules of UAB „Kupiškio komunalininkas“ (kupkom.lt), which empties
the containers of the individual houses of the whole municipality: mixed waste, packaging and
glass, and food waste in the town and four villages.

Its page "ATLIEKŲ IŠVEŽIMAS" is a list of sections, each a heading and its text:

    1. MIŠRIŲ KOMUNALINIŲ ATLIEKŲ SURINKIMO GRAFIKAS
    1.1. Kupiškio mieste                   1-as mėnesio trečiadienis
                                           3-as mėnesio trečiadienis
                                           2026 m. Mišrių atliekų surinkimo grafikas      (PDF)
    1.2 Kupiškio seniūnijoje               1-as mėnesio pirmadienis Kuosenai, Mirabelis.
                                           2-as mėnesio pirmadienis Skodiniai, Papiliai, ...
    ...
    1.7 Šimonių seniūnijoje                2-as mėnesio pirmadienis Šimonys, Adomynė, ...
    2. RŪŠIUOJAMŲJŲ ATLIEKŲ SURINKIMO GRAFIKAS
    2.1. 2026 M. II PUSMETIS RŪŠIUOJAMŲ ATLIEKŲ SURINKIMO GRAFIKAS                         (PDF)
    3. Tekstilės atliekų surinkimo grafikas   Kiekvieno mėnesio ketvirtą ketvirtadienį.
    4. Maisto atliekų surinkimo grafikas      2026 m. Maisto atliekų surinkimo grafikas  (PDF)

**Mixed waste has no dates**: it is written as rules, "1-as mėnesio trečiadienis" (the first
Wednesday of the month) to "4-as", for the town's individual houses and for the villages of
each eldership after their rule. parse_rule reads a rule as svara.Rule (the nth weekday of the
month, as Kauno švara's "pirmąjį mėnesyje trečiadienį"); anything else fails the build. Rules
don't expire, so their dates are calculated for a rolling window, from `keep_days` ago to the
end of the 13th month ahead (horizon), and the build's last mixed waste date is always a year
away: docs/monitoring.md says what notices a broken page instead. The page says nothing about
holidays, and the town's 2025 file kept its pickup on New Year's Day (1 January, a Wednesday):
no day is moved. A village named after two rules ("Pyragiai" after "2-as mėnesio antradienis" and
"4-as mėnesio antradienis") has the dates of both, a row per eldership and set of rules. The
town's own file (a table of the year's days) is read to check its rule: other dates are a
warning.

Packaging and glass are one PDF a half year (made in Excel), linked under a heading with its
period, a block per eldership with the dates of each:

    RŪŠIUOJAMŲJŲ ATLIEKŲ SURINKIMO GRAFIKAS 2026 M. II-PUSMETIS
    Plastiko,popieriaus,metalo atliekos     | Stiklo atliekos
    Kupiškio miestas                        | Kupiškio miestas
    2026-07-30 2026-10-30 2026-08-31 ...    | 2026-08-14 2026-11-13
    ...
    Šimonių sen.(Skodinių,Kinderių k.)      | Šimonių sen.(Skodinių,Kinderių k.)

so an eldership's dates are those of every village of it, and Skodiniai and Kinderiai (of
Kupiškio sen.) have Šimonių sen.'s. Food waste is one PDF a year, a table of days for the places
it names ("Kupiškis, Subačius, Noriūnai, Šepeta, Aukštupėnai"); the same table linked in the
mixed waste section ("Maisto atliekų surinkimo seniūnijose grafikas 2026 m.") isn't read. Textile
waste (a rule without places, a waste type the app has no schedules of) isn't read either. Every
packaging and food file that still has dates to publish is read, so the next half year's is read
as soon as the page links it; until it starts, its blocks continue those in force that cover the
same places (combine). When a period ends and nothing newer is linked, its blocks keep their last
dates (build.current_rows), with a warning.
Strict: a heading, a rule, a block, a title or a cell of no kind we know, a date outside the
file's period, an eldership without rules or without a block, and a page without a packaging
file fail the build; yesterday's folder is then kept.

The places are read by Routes (aratc.Routes). The town's file and the page name no streets: the
town's rows are the whole town, those of apartment buildings too (as for Jonavos r.). A village
the rules don't name gets the rows of its eldership: the only one where it has one rule (Skapiškio,
Alizavos and Šimonių sen.), else the app asks which.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.kupiskis --out ../site/kupiskio-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot, svara, utena
from .dates import WEEKDAY_NAMES, month_end
from .kretinga import ScheduleFile, file_name, period
from .locations import _UPPER, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold
from .sratc import _continue

PAGE_URL = "http://www.kupkom.lt/atlieku-isvezimas/"
COMPANY = "UAB „Kupiškio komunalininkas“"
LABEL = "Kupiškio r."  # every row's `district`
# The town has no eldership in the register: it gets one of its own (aratc.town_elderships).
TOWN = "Kupiškio miesto"
TOWN_ROW = "Kupiškio m."
# The elderships of the municipality (register names), each a section of the page.
ELDERSHIPS = frozenset({"Alizavos", "Kupiškio", "Noriūnų", "Skapiškio", "Subačiaus", "Šimonių"})
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}
# Mixed waste dates are calculated to the end of this month after today's.
AHEAD_MONTHS = 13


# --- the rules -------------------------------------------------------------------

# "1-as mėnesio trečiadienis": the first Wednesday of the month, ..., "4-as".
_RULE = re.compile(r"(?P<nth>[1-4])\s*-\s*as\s+mėnesio\s+(?P<weekday>\w+)")
_WEEKDAYS = {name.casefold(): number for number, name in enumerate(WEEKDAY_NAMES)}


def parse_rule(text: str) -> svara.Rule | None:
    """Understands "1-as mėnesio pirmadienis" (the first Monday of the month) to "4-as mėnesio
    sekmadienis", as svara.Rule's nth weekday. Returns None for anything else."""
    found = _RULE.fullmatch(clean_text(text).casefold())
    if not found or found["weekday"] not in _WEEKDAYS:
        return None
    return svara.Rule(0, weekdays=(_WEEKDAYS[found["weekday"]],), nth=int(found["nth"]))


def rule_dates(rules: Collection[svara.Rule], start: date, end: date) -> set[date]:
    """The days of the rules from `start` to `end`, as svara.Schedule gives them."""
    return {
        day for rule in rules for day in svara.Schedule("household", rule, 0, "").dates(start, end)
    }


def horizon(today: date) -> date:
    """The last day mixed waste dates are calculated for: the end of the 13th month after
    today's (in November 2026, 31 December 2027)."""
    month = today.month + AHEAD_MONTHS
    return month_end(today.year + (month - 1) // 12, (month - 1) % 12 + 1)


# --- the page ----------------------------------------------------------------


@dataclass
class _Section:
    """A section of the page: its heading, the lines of its text (each a list of (bold, text)
    pieces, a line per paragraph or <br>) and its links (href, text)."""

    heading: str
    lines: list[list[tuple[bool, str]]] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)


class _Page(HTMLParser):
    """The sections of the page's accordion: <h4 class="accordion-title"> and the <div
    class="accordion-content"> after it."""

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[_Section] = []
        self.heading: list[str] | None = None
        self.depth = 0  # of the <div>s of a section's content; 0 outside one
        self.line: list[tuple[bool, str]] = []
        self.bold = 0
        self.link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "h4" and "accordion-title" in classes:
            self.heading = []
        elif tag == "div" and self.depth:
            self.depth += 1
        elif tag == "div" and "accordion-content" in classes and self.sections:
            self.depth = 1
        elif not self.depth:
            return
        elif tag in ("p", "br", "li"):
            self._end_line()
        elif tag in ("strong", "b"):
            self.bold += 1
        elif tag == "a":
            self.link = (attributes.get("href") or "", [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "h4" and self.heading is not None:
            self.sections.append(_Section(clean_text("".join(self.heading))))
            self.heading = None
        elif not self.depth:
            return
        elif tag == "div":
            self.depth -= 1
            if not self.depth:
                self._end_line()
        elif tag in ("p", "li"):
            self._end_line()
        elif tag in ("strong", "b"):
            self.bold = max(0, self.bold - 1)
        elif tag == "a" and self.link is not None:
            href, text = self.link
            self.sections[-1].links.append((href, clean_text("".join(text))))
            self.link = None

    def handle_data(self, data: str) -> None:
        if self.heading is not None:
            self.heading.append(data)
        elif self.link is not None:
            self.link[1].append(data)
        elif self.depth:
            self.line.append((self.bold > 0, data))

    def _end_line(self) -> None:
        if clean_text("".join(text for _, text in self.line)):
            self.sections[-1].lines.append(self.line)
        self.line = []


# "1. MIŠRIŲ KOMUNALINIŲ ...", "1.1. Kupiškio mieste", "1.2 Kupiškio seniūnijoje", "2.1. 2026 M.
# II PUSMETIS ...": the number of its section and its own.
_HEADING = re.compile(r"(?P<number>\d+)\.(?:\s*(?P<sub>\d+)\.?)?\s*(?P<text>.*)")
# A section's waste type by the words of its heading (folded); None: textile waste, not read.
_SECTION_KINDS: tuple[tuple[str, Kind | None], ...] = (
    ("misriu komunaliniu atlieku", "household"),
    ("rusiuojam", "packaging"),
    ("tekstil", None),
    ("maisto", "food"),
)
# A subsection of mixed waste: "Kupiškio mieste", "2026 m. Kupiškio mieste", "Noriūnų
# seniūnijoje".
_TOWN_SECTION = re.compile(r"(?:20\d{2}\s*m\.?\s+)?Kupiškio\s+mieste", re.I)
_ELDERSHIP_SECTION = re.compile(r"(?:20\d{2}\s*m\.?\s+)?(?P<name>\w+)\s+seniūnijoje", re.I)
# A place of a rule's list: "Kuosenai", "Subačiaus mstl.", "Skapiškio gel. st.", "Miliūnai-2".
_PLACE = re.compile(rf"[{_UPPER}][\w.\- ]*")
# The publisher's spellings of a village it names in two rules, as the other rule (and the
# register) writes it: Stračniai of Subačiaus sen., the first and third Tuesday.
_SAME = {"Stačniai": "Stračniai"}


@dataclass
class _Subsection:
    """A section of the page with its waste type, or that of the section it is part of."""

    kind: Kind | None
    section: _Section


def read_page(html: str) -> tuple[list[_Subsection], list[str]]:
    """The page's sections, each with its waste type ("1. MIŠRIŲ KOMUNALINIŲ ...": mixed
    waste) or that of the section it is part of ("1.1. Kupiškio mieste"), and warnings about
    sections of no waste type we know. A heading without a number, or of a part of no section,
    raises ValueError."""
    collector = _Page()
    collector.feed(html)
    kinds: dict[str, Kind | None] = {}
    found: list[_Subsection] = []
    warnings: list[str] = []
    for section in collector.sections:
        heading = _HEADING.fullmatch(section.heading)
        if not heading:
            raise ValueError(f"a heading of no section: {section.heading!r}")
        if heading["sub"] is None:
            words = fold(heading["text"])
            known = [kind for stem, kind in _SECTION_KINDS if stem in words]
            if not known:
                warnings.append(f"a section of no waste type we read: {section.heading!r}")
            kinds[heading["number"]] = known[0] if known else None
        elif heading["number"] not in kinds:
            raise ValueError(f"a heading under no section: {section.heading!r}")
        found.append(_Subsection(kinds[heading["number"]], section))
    return found, warnings


def _split(line: list[tuple[bool, str]]) -> tuple[str, str]:
    """A line's bold words, first, and the rest. Bold words after the rest raise ValueError."""
    bold: list[str] = []
    rest: list[str] = []
    for is_bold, text in line:
        if not text.strip():
            (rest if rest else bold).append(text)
        elif is_bold and not rest:
            bold.append(text)
        elif is_bold:
            raise ValueError(f"bold words after the places: {clean_text(''.join(rest))!r}")
        else:
            rest.append(text)
    return clean_text("".join(bold)), clean_text("".join(rest))


def _places(text: str, where: str) -> list[str]:
    """The places of a rule's list: "Kuosenai, Mirabelis." -> ["Kuosenai", "Mirabelis"]. A
    place of no known shape raises ValueError."""
    items = [clean_text(item) for item in text.split(",")]
    if items and re.fullmatch(r"[^\s.]+\.", items[-1]):
        items[-1] = items[-1][:-1]  # the full stop of the list
    if bad := [item for item in items if not _PLACE.fullmatch(item)]:
        raise ValueError(f"{where}: places of no known kind: {bad} in {text!r}")
    return items


@dataclass
class _Rules:
    """The mixed waste rules of the page: the town's, and each eldership's with its places."""

    town: list[tuple[str, svara.Rule]] = field(default_factory=list)
    elderships: dict[str, list[tuple[svara.Rule, list[str]]]] = field(
        default_factory=lambda: defaultdict(list)
    )


def mixed_rules(subsections: list[_Subsection]) -> _Rules:
    """The rules of the mixed waste sections. Strict: a line that isn't a rule we understand
    (and, but in the town's section, its places), a rule in a section of no place we know, and
    a page without the town's rules or an eldership's raise ValueError."""
    rules = _Rules()
    for subsection in subsections:
        if subsection.kind != "household":
            continue
        section = subsection.section
        heading = _HEADING.fullmatch(section.heading)
        text = heading["text"] if heading else section.heading
        town = _TOWN_SECTION.fullmatch(text)
        named = _ELDERSHIP_SECTION.fullmatch(text)
        eldership = next((e for e in ELDERSHIPS if named and fold(e) == fold(named["name"])), None)
        for line in section.lines:
            words, places = _split(line)
            rule = parse_rule(words) if words else None
            if rule is None:
                written = clean_text("".join(t for _, t in line))
                raise ValueError(f"an unrecognised mixed waste rule: {written!r}")
            if town and not places:
                rules.town.append((words, rule))
            elif eldership and places:
                rules.elderships[eldership].append((rule, _places(places, section.heading)))
            else:
                raise ValueError(f"a rule of no place we know: {section.heading!r}: {words!r}")
    if not rules.town:
        raise ValueError("no mixed waste rule of the town on the page")
    if missing := sorted(ELDERSHIPS - set(rules.elderships)):
        raise ValueError(f"no mixed waste rules of {', '.join(missing)} sen. on the page")
    return rules


def _row(kind: Kind, name: str, dates: set[date]) -> Area:
    area = Area(kind, name, LABEL, dates=dates, provider=PROVIDER_ID)
    weekdays = {d.weekday() for d in dates}
    if len(weekdays) == 1:
        area.weekday = WEEKDAY_NAMES[weekdays.pop()]
    return area


@dataclass
class RulePage(SourceFile):
    """The page, read for its mixed waste rules: their dates from `start` to `end`. `check`:
    the town's dated schedule the page links (its name and content), to check the town's rule
    against."""

    start: date = date.min
    end: date = date.min
    check: tuple[str, bytes] | None = field(default=None, repr=False)


def parse_page(source: SourceFile, content: bytes) -> ParseResult:
    """The mixed waste rows of the page's rules: the town's ("Kupiškio m.") and, per eldership,
    a row per set of rules of its villages ("Kupiškio sen.: Pyragiai, Vėžionys": the second and
    fourth Tuesday), with their dates from the page's `start` to `end`. Strict (mixed_rules).
    Sections of no waste type we read are reported by download (find_files)."""
    subsections, _ = read_page(content.decode("utf-8", errors="replace"))
    rules = mixed_rules(subsections)
    start, end = getattr(source, "start", date.min), getattr(source, "end", date.min)
    if start > end:
        raise ValueError(f"{source.file_name}: no dates from {start} to {end}")
    town = [rule for _, rule in rules.town]
    areas = [_row("household", TOWN_ROW, rule_dates(town, start, end))]
    for eldership in sorted(rules.elderships, key=fold):
        of_place: dict[str, set[svara.Rule]] = {}
        for rule, places in rules.elderships[eldership]:
            for place in places:
                of_place.setdefault(_SAME.get(place, place), set()).add(rule)
        groups: dict[frozenset[svara.Rule], list[str]] = {}
        for place, mine in of_place.items():
            groups.setdefault(frozenset(mine), []).append(place)
        for mine, places in groups.items():
            name = f"{eldership} sen.: {', '.join(places)}"
            areas.append(_row("household", name, rule_dates(mine, start, end)))
    return ParseResult(areas, _check_town(getattr(source, "check", None), rules.town))


def _check_town(check: tuple[str, bytes] | None, rules: list[tuple[str, svara.Rule]]) -> list[str]:
    """The town's dated schedule against its rules, for the year of the file: other dates are a
    warning, and so are a file that can't be read and none."""
    written = " ir ".join(words for words, _ in rules)
    if check is None:
        return [f"no dated schedule of the town on the page to check its rule ({written})"]
    name, content = check
    try:
        title, _, days = month_table(content, name)
        year = _title_year(title, "misri", name)
        dates = _dates(days, year, name)
    except ValueError as error:
        return [f"{name}: can't be read to check the town's rule ({error})"]
    expected = rule_dates([rule for _, rule in rules], date(year, 1, 1), date(year, 12, 31))
    if dates == expected:
        return []
    missing = ", ".join(d.isoformat() for d in sorted(expected - dates)[:4])
    extra = ", ".join(d.isoformat() for d in sorted(dates - expected)[:4])
    return [
        f"{name}: the town's dates of {year} aren't its rule's ({written}): "
        f"not in the file {missing or '-'}; not the rule's {extra or '-'}"
    ]


# --- the files -------------------------------------------------------------------


def _get(url: str) -> bytes:
    # With the project's own user agent (http.USER_AGENT); the site has no valid certificate
    # for https.
    return http.get(url, timeout=60)


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The PDFs the page links, by the sections they are in: packaging, with the period of the
    heading above it ("2.1. 2026 M. II PUSMETIS ...", else of its link or name), food waste,
    with its year, and the town's mixed waste schedule ("2026 m. Mišrių atliekų surinkimo
    grafikas", kind household, to check its rule). Warnings: files without a year, and sections
    of no waste type we read."""
    subsections, warnings = read_page(html)
    files: list[ScheduleFile] = []
    for subsection in subsections:
        section = subsection.section
        for href, text in section.links:
            url = urljoin(page_url, href)
            name = file_name(url)
            if not name.lower().endswith(".pdf") or any(f.url == url for f in files):
                continue
            if subsection.kind == "household" and "misri" not in fold(f"{text} {name}"):
                continue  # the food waste table, linked here too; read from its own section
            if subsection.kind not in ("household", "packaging", "food"):
                continue
            year, months = None, None
            for written in (section.heading, text, name):
                found_year, found_months = period(written)
                year, months = year or found_year, months or found_months
            if year is None:
                warnings.append(f"{name} ({text!r}): no year in its heading, link or name")
                continue
            if subsection.kind != "packaging":
                months = None
            files.append(ScheduleFile(subsection.kind, url, name, year=year, months=months))
    return files, warnings


LABELS: dict[Kind, str] = {"packaging": "packaging", "food": "food waste"}


def select_files(
    files: list[ScheduleFile], today: date, keep_days: int = 31
) -> tuple[list[ScheduleFile], list[str]]:
    """Of the packaging and the food waste files, those with dates still to publish (their
    period ends at most `keep_days` before today), so the next period's file is read as soon as
    it's linked; if none runs to today, also the latest one, whose blocks keep their last dates.
    Of two for one period, the one linked last. A page without a packaging file raises
    ValidationError."""
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
            if kind == "packaging":
                raise build.ValidationError("no packaging schedule on the page")
            warnings.append(f"no {label} schedule on the page")
            continue
        running = [f for f in mine.values() if f.end >= cutoff]
        latest = max(mine.values(), key=lambda f: f.end)
        if not any(f.end >= today for f in running) and latest not in running:
            running.append(latest)
        selected += sorted(running, key=lambda f: f.start)
    return selected, warnings


def town_file(files: list[ScheduleFile], today: date) -> ScheduleFile | None:
    """Of the town's dated schedules, this year's, else the newest."""
    mine = [f for f in files if f.kind == "household"]
    return next((f for f in mine if f.year == today.year), None) or max(
        mine, key=lambda f: f.year, default=None
    )


def download(
    today: date, keep_days: int, get: Callable[[str], bytes] | None = None
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The page, for its rules (their dates from `keep_days` ago to horizon(today)), with the
    town's dated schedule to check them; and the packaging and food files in force."""
    get = get or _get
    html = get(PAGE_URL)
    found, warnings = find_files(html.decode("utf-8", errors="replace"))
    chosen, notes = select_files(found, today, keep_days)
    warnings += notes
    check = None
    if town := town_file(found, today):
        try:
            check = (town.file_name, get(town.url))
        except OSError as error:
            warnings.append(f"{town.file_name}: couldn't be downloaded ({error})")
    page = RulePage(
        "household",
        PAGE_URL,
        "atlieku-isvezimas",
        start=today - timedelta(days=keep_days),
        end=horizon(today),
        check=check,
    )
    return [(page, html), *((f, get(f.url)) for f in chosen)], warnings


# --- the tables ------------------------------------------------------------------

# The days of a month's cell: "7 ; 21", "8; 22", "1 ir 15".
_DAYS = re.compile(r"\d{1,2}(?:\s*(?:;|,|ir)\s*\d{1,2})*")
# The first row of the town's and the food waste table (folded), the places column first.
_PLACES_COLUMN = "miesto gyvenvietes pavadinimas"
_MONTH_COLUMNS = ["menuo", "atlieku surinkimo diena"]


def month_table(content: bytes, where: str) -> tuple[str, list[str], dict[int, str]]:
    """The one table of a file of the town's or food waste days: the text above it (its title),
    the places of its first column if it has one ("Kupiškis", "Subačius", ...), and the days of
    each month. Strict: another number of tables, other columns, months out of order and places
    on another row raise ValueError."""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        tables = [(page, table) for page in pdf.pages for table in page.find_tables()]
        if len(tables) != 1:
            raise ValueError(f"{where}: {len(tables)} tables")
        ((page, table),) = tables
        title = clean_text(page.crop((0, 0, page.width, table.bbox[1])).extract_text() or "")
        rows = table.extract()
    header = [fold(cell or "") for cell in rows[0]]
    if header not in (_MONTH_COLUMNS, [_PLACES_COLUMN, *_MONTH_COLUMNS]):
        raise ValueError(f"{where}: a table of {rows[0]}")
    first = len(header) - 2
    months = [aratc.MONTHS.get(fold(row[first] or "")) for row in rows[1:]]
    if months != list(range(1, 13)):
        raise ValueError(f"{where}: the months {[row[first] for row in rows[1:]]}")
    places: list[str] = []
    if first:
        cells = [row[0] for row in rows[1:]]
        if not cells[0] or any(cells[1:]):
            raise ValueError(f"{where}: places {cells}")
        places = [clean_text(p) for p in re.split(r"[\n,]", cells[0]) if clean_text(p)]
        if bad := [p for p in places if not _PLACE.fullmatch(p)]:
            raise ValueError(f"{where}: places of no known kind: {bad}")
    days = {month: clean_text(row[-1]) for month, row in zip(months, rows[1:], strict=True)}
    return title, places, days


def _title_year(title: str, stem: str, where: str) -> int:
    """The one year of a file's title, which must have `stem` (folded)."""
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", title)}
    if stem not in fold(title) or len(years) != 1:
        raise ValueError(f"{where}: a title of {title!r}")
    return years.pop()


def _dates(days: dict[int, str], year: int, where: str) -> set[date]:
    """The dates of a year's cells of days. A cell that isn't days or a day the month doesn't
    have raises ValueError."""
    dates: set[date] = set()
    for month, cell in days.items():
        if not _DAYS.fullmatch(cell):
            raise ValueError(f"{where}: not days: {cell!r}")
        for day in (int(d) for d in re.findall(r"\d+", cell)):
            if not 1 <= day <= month_end(year, month).day:
                raise ValueError(f"{where}: month {month} of {year} has no day {day}")
            dates.add(date(year, month, day))
    return dates


def parse_food(source: SourceFile, content: bytes) -> ParseResult:
    """The food waste row of its places ("Kupiškis, Subačius, Noriūnai, Šepeta, Aukštupėnai").
    Strict (month_table): also a title of another year than the link's or not of food waste,
    and a table without places raise ValueError."""
    where = source.file_name
    title, places, days = month_table(content, where)
    year = _title_year(title, "maisto", where)
    if year != getattr(source, "year", year):
        raise ValueError(f"{where}: the title says {year}, the link {source.year}")
    if not places:
        raise ValueError(f"{where}: no places")
    return ParseResult([_row("food", ", ".join(places), _dates(days, year, where))])


# Each column's waste type by the words of its header (folded): "Plastiko,popieriaus,metalo
# atliekos", "Stiklo atliekos".
_COLUMNS: tuple[tuple[str, Kind], ...] = (
    ("plastik", "packaging"),
    ("popier", "packaging"),
    ("stikl", "glass"),
)
# The dates of a cell: "2026-07-30 2026-10-30 2026-08-31 ...".
_ISO_DATES = re.compile(r"\d{4}-\d{2}-\d{2}(?:\s+\d{4}-\d{2}-\d{2})*")
# A block's places, one by one: "Kupiškio miestas", "Alizavos sen.", "Šimonių
# sen.(Skodinių,Kinderių k.)", "Kinderių k." (in 2024: "Šimonių sen., Kinderių k., Skodinių k.").
_BLOCK_ITEM = re.compile(
    r"(?P<town>Kupiškio\s+(?:miestas|m\.))"
    r"|(?P<eldership>\w+)\s+sen\.\s*(?:\(\s*(?P<villages>[^()]+?)\s+k\.\s*\))?"
    r"|(?P<village>\w+(?:\s+\w+)?)\s+k\.",
    re.I,
)


def block_name(label: str, where: str) -> tuple[str, list[str]]:
    """A block's row name from its label ("Šimonių sen.(Skodinių,Kinderių k.)" -> "Šimonių
    sen., Skodinių k., Kinderių k."; "Kupiškio miestas" -> "Kupiškio m."), and the town and
    elderships it is for (TOWN, register names). Places of no known kind raise ValueError."""
    parts: list[str] = []
    covered: list[str] = []
    for item in utena._items(label):
        found = _BLOCK_ITEM.fullmatch(item)
        eldership = found and found["eldership"]
        name = next((e for e in ELDERSHIPS if eldership and fold(e) == fold(eldership)), None)
        if found and found["town"]:
            parts.append(TOWN_ROW)
            covered.append(TOWN)
        elif name:
            parts.append(f"{name} sen.")
            covered.append(name)
            villages = found["villages"] or ""
            parts += [f"{clean_text(v)} k." for v in villages.split(",") if clean_text(v)]
        elif found and found["village"]:
            parts.append(f"{clean_text(found['village'])} k.")
        else:
            raise ValueError(f"{where}: a block of {label!r}")
    return ", ".join(parts), covered


def parse_sorted(source: SourceFile, content: bytes) -> ParseResult:
    """The packaging and glass rows of a half year's file, a block each ("Alizavos sen.").
    Strict: a title of another period than the link's, another number of tables, columns of
    other waste types, a block whose columns name other places, a cell that isn't dates, a date
    outside the file's period, and a town or eldership without a block or with two raise
    ValueError."""
    where = source.file_name
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        tables = [(page, table) for page in pdf.pages for table in page.find_tables()]
        if len(tables) != 1:
            raise ValueError(f"{where}: {len(tables)} tables")
        ((page, table),) = tables
        title = clean_text(page.crop((0, 0, page.width, table.bbox[1])).extract_text() or "")
        rows = [[clean_text(cell) for cell in row] for row in table.extract()]
    year, months = getattr(source, "year", None), getattr(source, "months", None)
    if "rusiuojam" not in fold(title) or period(title) != (year, months):
        raise ValueError(f"{where}: the title {title!r} isn't of {year} {months or ''}")
    kinds: list[Kind] = []
    for cell in rows[0]:
        found = {kind for stem, kind in _COLUMNS if stem in fold(cell)}
        if len(found) != 1:
            raise ValueError(f"{where}: a column of {cell!r}")
        kinds.append(found.pop())
    if sorted(kinds) != ["glass", "packaging"] or len(rows) % 2 == 0:
        raise ValueError(f"{where}: columns {rows[0]} and {len(rows)} rows")
    start, end = source.start, source.end  # ScheduleFile's period
    areas: list[Area] = []
    covered: list[str] = []
    for labels, cells in zip(rows[1::2], rows[2::2], strict=True):
        if len(set(labels)) != 1 or not labels[0] or _ISO_DATES.search(labels[0]):
            raise ValueError(f"{where}: a block of {labels}")
        name, places = block_name(labels[0], where)
        covered += places
        for kind, cell in zip(kinds, cells, strict=True):
            if not _ISO_DATES.fullmatch(cell):
                raise ValueError(f"{where}: not dates: {cell!r} ({labels[0]})")
            dates = {date.fromisoformat(d) for d in cell.split()}
            if outside := sorted(d for d in dates if not start <= d <= end):
                raise ValueError(f"{where}: {outside[0]} outside {start} - {end} ({labels[0]})")
            areas.append(_row(kind, name, dates))
    expected = sorted(ELDERSHIPS | {TOWN})
    if sorted(covered) != expected:
        raise ValueError(f"{where}: blocks of {sorted(covered)}, not one of each of {expected}")
    return ParseResult(areas)


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    if isinstance(source, RulePage):
        return parse_page(source, content)
    if source.kind == "packaging":
        return parse_sorted(source, content)
    if source.kind == "food":
        return parse_food(source, content)
    raise ValueError(f"{source.file_name}: a file of no kind we read")


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Subačius": the town (Subačius m.); the old town is "Subačiaus mstl." in a rule of its own.
    (re.compile(r"\bSubačius\b(?!\s*(?:m|mstl|vs)\.)"), "Subačiaus m."),
    # "Miliūnai-2" (of Alizavos sen.), "Puponys-2" (Puponys II k., of Šimonių sen.): a village
    # with the name of another eldership's.
    (re.compile(r"(?<=\w)-2\b"), ""),
)
# A row of an eldership's mixed waste rule: "Kupiškio sen.: Kuosenai, Mirabelis".
_RULE_ROW = re.compile(r"(?P<name>\w+) sen\.:\s*")
# A block's places as block_name writes them: "Kupiškio m.", "Alizavos sen.", "Skodinių k.".
_BLOCK = re.compile(
    r"(?P<town>Kupiškio m\.)|(?P<eldership>\w+) sen\.|(?P<village>\w+(?: \w+)?) k\."
)
# "Skapiškio gel. st.": the railway station Skapiškis (glž. st. in the register).
_STATION = re.compile(r"(?P<name>\w+)\s+gel\.\s*st\.?")


class Routes(aratc.Routes):
    """Reads the places of the rows, as aratc.Routes reads those of Alytus county:

        Kupiškio m.                                  the whole town (mixed waste, packaging)
        Kupiškio sen.: Pyragiai, Vėžionys            villages of an eldership's mixed waste
        Alizavos sen.                                an eldership's packaging and glass
        Šimonių sen., Skodinių k., Kinderių k.       and villages of another eldership
        Kupiškis, Subačius, Noriūnai, ...            places of the municipality (food waste)

    The villages of an eldership's mixed waste row are those it names, and every other village
    of the eldership is a fallback, so a village no rule names gets the rows of its eldership
    (the app asks which). "Subačius" is the town; the old town is "Subačiaus mstl.".

    No street gets "no pickup" (build_locations): the page names no streets."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        """The rows' names written as aratc.Routes reads them (self.kind is the row's)."""
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        if self.kind == "household" and (row := _RULE_ROW.match(text)):
            return f"Visoje {row['name']} sen. {text[row.end() :]}"
        items = [_BLOCK.fullmatch(item) for item in text.split(", ")]
        if not all(items):
            return text
        written: list[str] = []
        for item in items:
            if item["town"]:
                written.append(f"Visoje {TOWN} sen.")
            elif item["eldership"]:
                written.append(f"Visoje {item['eldership']} sen.")
            else:
                written.append(self._village(item["village"]))
        return " ".join(written)

    def _village(self, name: str) -> str:
        """A village of a block, in the section of its eldership: "Kupiškio sen.: Skodinių k."
        (unless no village or several of its elderships have the name)."""
        found = {
            s.district
            for s in self.places[LABEL]
            if s.abbr == "k." and fold(s.genitive) == fold(name)
        }
        return f"{found.pop()} sen.: {name} k." if len(found) == 1 else f"{name} k."

    def prepare(self, areas: list[Area]) -> None:
        """The settlements the rows of each kind name, not as a fallback of a whole eldership:
        a village a row puts in another eldership is still found there (as moletai.Routes)."""
        named: dict[str, set[int]] = defaultdict(set)
        for area in areas:
            named[area.kind] |= {s.code for s, c in self.clauses(area)[0] if not c.fallback}
        self.named = named

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        """aratc.Routes' settlements, and railway stations: "Skapiškio gel. st."."""
        if station := _STATION.fullmatch(name):
            return [
                s
                for s in self.places[LABEL]
                if s.abbr == "glž. st."
                and fold(s.genitive) == fold(station["name"])
                and district in ("", s.district)
            ]
        return super().settlements(name, numerals, kind, district)


PROVIDER_ID = "kupiskis"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=COMPANY,
    url=PAGE_URL,
    elderships=ELDERSHIPS | {TOWN},
    kinds=("household", "packaging", "glass", "food"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.KUPISKIS_MUNICIPALITY,
    snapshot.KUPISKIS_REGISTRY_FILE,
    snapshot.KUPISKIS_ADDRESSES_FILE,
    # 2026: the town's rule and 22 rows of the elderships' rules, which name 125 of the 396
    # settlements (the others get their eldership's rows), the packaging and glass of the town
    # and 6 elderships, and one food waste row.
    min_areas={"household": 15, "packaging": 7, "glass": 7},
    min_household_places=300,
    # About 9,400 addresses in 2026, 1,700 of them in the town.
    min_address_points=6_500,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- this period and the next ----------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins the blocks of the packaging and food files of later periods to those of the
    period in force, in place (sratc._continue, as kretinga.combine joins Kretingos r.'s half
    years): a block of the next half year that covers the same places as one in force gives it
    its dates; the rest wait, with a warning, until their period starts. Blocks of earlier
    periods are dropped. Files of one kind whose periods overlap raise ValueError; a kind whose
    files have all ended keeps its blocks, with their last dates, and a warning.

    Also warns about a settlement that two mixed waste rows name (a village in two rules,
    written two ways): the app would ask which."""
    warnings: list[str] = []
    groups: dict = defaultdict(lambda: defaultdict(list))
    for kind, label in LABELS.items():
        files = sorted(
            ((s, r) for s, r in parsed if isinstance(s, ScheduleFile) and s.kind == kind),
            key=lambda pair: pair[0].start,
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
            warnings.append(f"the {label} schedule ended on {ended}; no newer one is read")
        elif (first := min(s.start for s, _ in files)) > today:
            warnings.append(f"no {label} schedule for today; the next starts on {first}")
        for source, result in files:
            for area in result.areas:
                groups[(LABEL, area.kind)][source.start].append((result, area))
    reader = Routes(Index(registry), PROVIDER, defaultdict(dict))
    warnings += _continue(groups, reader, lambda start: start <= today, date.isoformat)
    rows = [a for s, r in parsed if isinstance(s, RulePage) for a in r.areas]
    return warnings + _twice(rows, Routes(Index(registry), PROVIDER, defaultdict(dict)))


def _twice(rows: list[Area], reader: Routes) -> list[str]:
    """Warnings about settlements two mixed waste rows name."""
    reader.prepare(rows)
    names: dict[int, tuple[Settlement, list[str]]] = {}
    for area in rows:
        for settlement, clause in reader.clauses(area)[0]:
            if not clause.fallback:
                names.setdefault(settlement.code, (settlement, []))[1].append(area.name)
    return [
        f"{s.name} {s.abbr} ({s.district} sen.) is named by {len(set(of))} mixed waste rows: "
        + "; ".join(dict.fromkeys(of))
        for s, of in names.values()
        if len(set(of)) > 1
    ]


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
    # nothing (the daily job keeps yesterday's folder). The town gets an eldership of its own.
    return raseiniai.run(
        args.out, args.keep_days, None, MUNICIPALITY, lambda _: SOURCE, aratc.town_elderships
    )


if __name__ == "__main__":
    raise SystemExit(main())

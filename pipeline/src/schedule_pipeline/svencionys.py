"""Švenčionių rajonas: the schedules of the individual houses' containers, published by the
municipality (svencionys.lt) as PDFs: mixed waste as rules, packaging and glass a year at a time.

Its page "Komunalinių atliekų išvežimo grafikai" links three files, found by the texts of their
links (packaging's year from its name, "Pakuociu-atlieku-isvezimo-grafikai_2026.pdf"):

    Mišriųjų komunalinių atliekų išvežimo grafikai                   mixed waste, rules (2025)
    Pakuočių atliekų konteinerių tuštinimo grafikai                  packaging and glass, 2026
    Bendro naudojimo pakuočių atliekų ir antrinių žaliavų ...        the shared containers of
                                                                     the towns: not read

The mixed waste file is one page of rules with no dates and no year (made in January 2025): two
tables, read with pdfplumber's table finder, a column per weekday and weeks of the month, the
places under them. Pabradė, Magūnai and their villages, the town's streets and the villages
listed:

    PIRMADIENIS                       | ...  TREČIADIENIS                      | ...
    I | III        | II | IV          | ...  I | III                           | ...
    Pabradės sen.  | Pabradės m.      | ...  Pabradės sen.                     | ...
    Baltadvario k. | Keisūnų g.       | ...  Mečankos k. ... Magūnu sen. ...   | ...

and the other nine elderships, whole, but some villages and the towns:

    PIRMADIENIS                         | ... | TREČIADIENIS
    I-III                               | ... | I-III                         | II-IV
    Švenčionių seniūnija (išskyrus      | ... | Sarių, Cirkliškio, Strūnaičio | Švenčionių
    Milkuškų, Kukiškės, Medišionių      |     | seniūnijos                    | miestas
    kaimus)                             |     |                               |

"I III" is the first and the third such weekday of the month (the first is on days 1-7, the
third on days 15-21), "II IV" the second and the fourth: every other week, and three weeks
between the third and the next month's first. The second table writes them "I-III" and "II-IV",
the two halves of the month again (not the first three weeks: the columns pair them as the first
table does, and "I-III mėn. trečiadienis" of the shared containers' file alternates with
"II-IV"). The packaging file names its rules "II mėnesio trečiadienis" (the second Wednesday)
next to dates that are exactly those days. Neither file says a day moves for a public holiday,
and the packaging file's 2026 dates keep the rule's days on holidays (Monday 16 February,
Wednesday 11 March): a rule's day isn't moved (Rule).

The rules never end, so their dates are a rolling window, from the days the published data keeps
(31 days back) to the end of the 13th month ahead (window): the daily build moves it on.
The Pabradės m. rows that are apartment buildings' containers ("Pabradės m. daugiabučiai namai")
aren't read.

The packaging file has the nine elderships' packaging and glass as dates (a column per group of
places, "01.14" a row per pickup) and Pabradė's and Magūnai's as rules, in two tables (the first
goes on over a page):

    2026 M. PLASTIKO, POPIERIAUS, METALO PAKUOČIŲ ATLIEKŲ KONTEINERIŲ TUŠTINIMO GRAFIKAS
    PIRMADIENIS          | ... | KETVIRTADIENIS                  | ...
    IV                   | ... | III               | IV          | ...
    Pabradės miestas:    | ... | Pabradės seniūnija: | ...
    Keisūnų g., ...      | ... | Naujadvario k., ... | ...
    Plastiko, popieriaus, metalo pakuočių atliekų konteineriai Pabradės ir Magūnų seniūnijose
    tuštinami kas mėnesį (01, 02, ..., 12).

Those rules are the year's: the file's titles name the year and its notes the months ("kas
antrą mėnesį (01, 03, ..., 11)" for glass), so they become the dates of that year only, and the
file runs out as a yearly file does. Next year's file is read as soon as the page links it, its
rows continuing this year's that cover the same places (tratc.combine).

Strict: a title, a heading or text next to the tables other than these, a weekday or weeks of the
month we don't read, a column across two weekdays, places of no known kind or under no eldership,
an eldership of the nine that no column names whole, or names twice, villages left out of an
eldership that no other column names, a date that isn't one or isn't in the year, packaging
without a date in every month, and a Pabradė rule without its note of months raise. A dated
column whose dates aren't its header's rule is a warning.

The places are read by Routes (aratc.Routes for this municipality): the sections of Pabradės and
Magūnų sen. and the streets of Pabradė (a garden community, "Pušaitės SB", is the town's streets
of its name and a number); the other elderships whole ("Visoje Adutiškio sen."), but the villages
and towns left out of them, which their own rows name. A street of Pabradė no row names is left
to the app (as for Utenos r.): the rows name the streets of individual houses, the apartment
buildings' containers aren't read, and nothing says a street has none. Švenčionys and
Švenčionėliai are named whole ("Švenčionių miestas"). A village in two columns (Pažeimenė, on
Mondays and Thursdays) gets both rows, and the app asks.

svencionys.lt refuses GitHub's runners (HTTP 403): the daily job then reads the copy of the page
and its files in pipeline/data (COPY_DIR, save_copy), with a warning that says how old it is, as
for Ukmergės r. A file that can't be downloaded or read keeps its rows of yesterday's data, and
the other file is still read (as utena.py does).

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.svencionys --out ../site/svencioniu-r
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from urllib.parse import urljoin

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot, svara, tratc
from .dates import WEEKDAY_NAMES, month_end
from .kretinga import _Links, file_name
from .locations import _WORD, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

PAGE_URL = "https://svencionys.lt/aplinkosauga/komunaliniu-atlieku-isvezimo-grafikai/"
# Yesterday's data, for the files that can't be read today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/svencioniu-r"
NAME = "Švenčionių rajono savivaldybė"
LABEL = "Švenčionių r."  # every row's `district`
PROVIDER_ID = "svencionys"
# The elderships (register names): Pabradė's and Magūnai's, read place by place, and the nine
# others, read whole.
SOUTH = frozenset({"Magūnų", "Pabradės"})
NORTH = frozenset(
    {
        "Adutiškio",
        "Cirkliškio",
        "Kaltanėnų",
        "Labanoro",
        "Sarių",
        "Strūnaičio",
        "Svirkų",
        "Švenčionėlių",
        "Švenčionių",
    }
)
ELDERSHIPS = SOUTH | NORTH
# The towns (genitives) and their elderships.
TOWNS = {"Pabradės": "Pabradės", "Švenčionių": "Švenčionių", "Švenčionėlių": "Švenčionėlių"}
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}
LABELS: dict[Kind, str] = {"household": "mixed waste", "packaging": "packaging"}
# The rules' dates run to the end of this month ahead.
WINDOW_MONTHS = 13


# --- the rules -------------------------------------------------------------------

_WEEKS = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
# The weeks a rule may name: one, or every other week ("I III", "I-III": the first and the
# third; "II IV", "II-IV": the second and the fourth).
_PAIRS = {(1,), (2,), (3,), (4,), (1, 3), (2, 4)}
# "I III pirmadienis", "I-III pirmadienis", "IV pirmadienis", "II mėnesio trečiadienis", "I-III
# mėn. trečiadienis" (casefolded).
_RULE = re.compile(r"(?P<weeks>[iv]+(?:\s*[-\s]\s*[iv]+)?)\s+(?:mėn(?:\.|esio)\s+)?(?P<day>\w+)")


@dataclass(frozen=True)
class Rule:
    """The nth `weekday`s of the month (0 = Monday), `weeks` of them ((1, 3): the first and the
    third), in `months` only (every month if empty): svara.Rule's "pirmąjį mėnesyje trečiadienį"
    (the first Wednesday of every month), one for each week. A day that is a public holiday isn't
    moved: neither file says it would be, and the packaging file's dates keep the rules' days on
    holidays."""

    weekday: int
    weeks: tuple[int, ...]
    months: tuple[int, ...] = ()

    def dates(self, start: date, end: date) -> set[date]:
        """The days from `start` to `end`, both included, as svara.Schedule gives them."""
        return {
            day
            for nth in self.weeks
            for day in svara.Schedule(
                "", svara.Rule(0, self.months, (self.weekday,), nth), 0, ""
            ).dates(start, end)
        }


def parse_rule(text: str) -> Rule | None:
    """Understands "I III pirmadienis" (the first and the third Monday of every month), "I-III
    pirmadienis" (the same), "IV pirmadienis" (the fourth), "II mėnesio trečiadienis" (the second
    Wednesday) and "I-III mėn. trečiadienis". Returns None for anything else."""
    found = _RULE.fullmatch(clean_text(text).casefold())
    if not found:
        return None
    weeks = tuple(_WEEKS.get(w, 0) for w in re.split(r"\s*-\s*|\s+", found["weeks"]))
    day = next((n for n, name in enumerate(WEEKDAY_NAMES) if name.casefold() == found["day"]), None)
    if weeks not in _PAIRS or day is None:
        return None
    return Rule(day, weeks)


def window(today: date, keep_days: int) -> tuple[date, date]:
    """The days the rules' dates are published for: from the oldest day the data keeps to the
    end of the WINDOW_MONTHS-th month after today's."""
    months = today.year * 12 + today.month - 1 + WINDOW_MONTHS
    return today - timedelta(days=keep_days), month_end(months // 12, months % 12 + 1)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page. `year`: packaging's, from its link or name; `start` and `end`: the
    days mixed waste's rules are published for (window)."""

    year: int | None = None
    start: date = date.min
    end: date = date.min


# The waste type of a file by its link's text (folded); the shared containers' file isn't read.
FILES: tuple[tuple[re.Pattern[str], Kind | None], ...] = (
    (re.compile(r"\bbendro naudojimo\b"), None),
    (re.compile(r"\bmisri"), "household"),
    (re.compile(r"\bpakuoc"), "packaging"),
)


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The schedules the page links, in its order, by the texts of their links; and warnings
    about schedules of no kind we read."""
    collector = _Links()
    collector.feed(html)
    files: list[ScheduleFile] = []
    warnings: list[str] = []
    for href, text, title in collector.links:
        url = urljoin(page_url, href)
        name = file_name(url)
        described = text or title
        words = fold(f"{described} {name}")
        if not name.lower().endswith(".pdf") or "grafik" not in words:
            continue
        if any(f.url == url for f in files):
            continue
        kinds = [kind for pattern, kind in FILES if pattern.search(fold(described))]
        if not kinds:
            warnings.append(f"{name} ({described!r}): a schedule of no kind we read")
            continue
        if kinds[0] is None:
            continue
        year = tratc.file_year(described) or tratc.file_year(name)
        files.append(ScheduleFile(kinds[0], url, name, year=year))
    return files, warnings


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """The mixed waste file (the one linked first), and the packaging files of this year and
    later or of no year in their link or name (their titles have it); if none, the newest. A page
    without either kind raises ValidationError."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    for kind, label in LABELS.items():
        mine = [f for f in files if f.kind == kind]
        if not mine:
            raise build.ValidationError(f"no {label} schedule on the page")
        if kind == "household":
            first, *others = mine
            warnings += [
                f"{f.file_name}: not read, {first.file_name} is linked first" for f in others
            ]
            selected.append(first)
            continue
        running = [f for f in mine if f.year is None or f.year >= today.year]
        if not running:
            newest = max(f.year or 0 for f in mine)
            running = [f for f in mine if f.year == newest]
            warnings.append(f"no {label} schedule for {today.year} on the page")
        selected += running
    return selected, warnings


def _get(url: str) -> bytes:
    # With the project's own user agent (http.USER_AGENT). svencionys.lt answers GitHub's
    # runners 403; it serves a machine in Lithuania.
    return http.get(url, timeout=60)


# A copy of the page and the files the daily job reads from it, taken from a machine in Lithuania
# (save_copy, run daily by snapshot.py --copies): svencionys.lt answers GitHub's runners 403, as
# silute.lt, kedainiai.lt, ukmerge.lt and sirvintos.lt do.
COPY_DIR = snapshot.SVENCIONYS_COPY_DIR


def _download(
    today: date, keep_days: int, get: Callable[[str], bytes], tolerant: bool
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    files, warnings = find_files(get(PAGE_URL).decode("utf-8", errors="replace"))
    selected, more = select_files(files, today)
    warnings += more
    sources: list[tuple[SourceFile, bytes]] = []
    for file in selected:
        if file.kind == "household":
            file.start, file.end = window(today, keep_days)
        try:
            sources.append((file, get(file.url)))
        except OSError as error:
            if not tolerant:
                raise
            warnings.append(f"{file.file_name}: couldn't be downloaded ({error})")
            sources.append((file, b""))
    return sources, warnings


def download(
    today: date, keep_days: int, tolerant: bool = False
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files in force, mixed waste's with the window of its rules' dates, from the page, or
    where the site doesn't answer and there is a copy (COPY_DIR), the copy's, with a warning
    that says how old it is, as ukmerge.download does. `tolerant`: a file that can't be
    downloaded is passed on empty, and keeps its rows of yesterday's data (parse_or_keep)."""
    try:
        return _download(today, keep_days, _get, tolerant)
    except OSError as error:
        if not (COPY_DIR / snapshot.SITE_COPY_INDEX).exists():
            raise
        get = partial(snapshot.site_copy, COPY_DIR)
        files, warnings = _download(today, keep_days, get, tolerant)
        note = snapshot.site_copy_note(PAGE_URL, error, COPY_DIR, today)
        print(note, file=sys.stderr)
        return files, [note, *warnings]


def save_copy(folder: Path | None = None, today: date | None = None) -> bool:
    """Saves the page and the files the daily job would read from it in `folder` (COPY_DIR),
    for download when the site doesn't answer: python -m schedule_pipeline.snapshot --copies,
    daily, so next year's packaging file (December or January) or a new sheet of rules comes
    within a day. False if the files were those of the copy already there, which is then left
    as it is."""
    today = today or snapshot.utc_today()
    html = _get(PAGE_URL)
    found, warnings = find_files(html.decode("utf-8", errors="replace"))
    chosen, notes = select_files(found, today)
    for warning in warnings + notes:
        print(f"Švenčionių r.: {warning}", file=sys.stderr)
    contents = [(f.url, _get(f.url)) for f in chosen]
    return snapshot.save_site_copy(folder or COPY_DIR, PAGE_URL, html, contents, today)


# --- the files -------------------------------------------------------------------

# Each file's title, its first line (folded).
TITLES: dict[Kind, str] = {
    "household": "misriosios komunalines atliekos",
    "packaging": "individualiu pakuociu atlieku konteineriu tustinimo grafikai",
}
# The heading of a part of the municipality: "Pabradės ir Magūnų seniūnijos:", "Adutiškio,
# Cirkliškio, ..., Švenčionių seniūnijos:".
_HEADING = re.compile(r"(?P<names>.+?)\s+seniūnijos\s*:")
# The packaging file's titles of its tables (folded): "2026 M. PLASTIKO, POPIERIAUS, METALO
# PAKUOČIŲ ATLIEKŲ KONTEINERIŲ TUŠTINIMO GRAFIKAS", "2026 M. STIKLO PAKUOČIŲ ...".
_TABLE_TITLE = re.compile(
    r"(?P<year>20\d{2}) m (?P<what>plastiko popieriaus metalo|stiklo) pakuociu atlieku "
    r"konteineriu tustinimo grafikas"
)
# The notes under Pabradė's and Magūnai's tables (folded): "Plastiko, popieriaus, metalo
# pakuočių atliekų konteineriai Pabradės ir Magūnų seniūnijose tuštinami kas mėnesį (01, 02,
# ..., 12).", "Stiklo ... kas antrą mėnesį (01, 03, ..., 11)."
_NOTE = re.compile(
    r"(?P<what>plastiko popieriaus metalo|stiklo) pakuociu atlieku konteineriai (?P<names>.+?) "
    r"seniunijose tustinami kas (?P<every>antra )?menesi (?P<months>\d{2}(?: \d{2})*)"
)
WHAT: dict[str, Kind] = {"plastiko popieriaus metalo": "packaging", "stiklo": "glass"}
# The tables each file must have: (part of the municipality, waste type).
TABLES: dict[Kind, set[tuple[frozenset[str], Kind]]] = {
    "household": {(SOUTH, "household"), (NORTH, "household")},
    "packaging": {(NORTH, "packaging"), (NORTH, "glass"), (SOUTH, "packaging"), (SOUTH, "glass")},
}
# A date of the nine elderships' tables: "01.14".
_DATE = re.compile(r"(\d{2})\.(\d{2})")
# A rule at the end of a dated column's header: "... II mėnesio trečiadienis".
_HEADER_RULE = re.compile(r"(?P<places>.+?)\s+(?P<rule>(?:I{1,3}|IV)\s+mėnesio\s+\w+)")

Rows = list[list[str | None]]


@dataclass
class _Table:
    """A table of the file, under the heading of its part of the municipality and the title of
    its waste type."""

    part: frozenset[str]
    kind: Kind
    year: int | None
    rows: Rows


def _elderships(text: str, where: str) -> list[str]:
    """The register's elderships a list names: "Pabradės ir Magūnų", "Adutiškio, Cirkliškio"."""
    found: list[str] = []
    for name in re.split(r"\s*,\s*|\s+ir\s+", clean_text(text)):
        eldership = next((e for e in ELDERSHIPS if fold(e) == fold(name)), None)
        if eldership is None:
            raise ValueError(f"{where}: an eldership the register doesn't have: {name!r}")
        found.append(eldership)
    return found


def _part(text: str, where: str) -> frozenset[str]:
    """Pabradė's and Magūnai's elderships, or the nine others, by a heading's list."""
    found = frozenset(_elderships(text, where))
    if found not in (SOUTH, NORTH):
        raise ValueError(f"{where}: a heading of the elderships {sorted(found)}")
    return found


def _blocks(pdf) -> list[str | Rows]:
    """The lines and the tables of the file in their order, page by page; a line with a bracket
    left open goes on in the next one ("... (01, 02, ..., 10," "11, 12).")."""
    blocks: list[str | Rows] = []
    for page in pdf.pages:
        tables = page.find_tables()
        outside = page
        for table in tables:
            outside = outside.outside_bbox(table.bbox)
        found: list[tuple[float, str | Rows]] = [
            (t.bbox[1], [[None if c is None else c.strip() for c in row] for row in t.extract()])
            for t in tables
        ]
        found += [
            (line["top"], text)
            for line in outside.extract_text_lines()
            if (text := clean_text(line["text"]))
        ]
        blocks += [block for _, block in sorted(found, key=lambda f: f[0])]
    joined: list[str | Rows] = []
    for block in blocks:
        last = joined[-1] if joined else None
        if isinstance(block, str) and isinstance(last, str) and last.count("(") > last.count(")"):
            joined[-1] = f"{last} {block}"
        else:
            joined.append(block)
    return joined


_FOLDED_DAYS = {fold(name): n for n, name in enumerate(WEEKDAY_NAMES)}


def _is_weekdays(row: list[str | None]) -> bool:
    """A weekday table's first row: "PIRMADIENIS", None (the cell goes on), "ANTRADIENIS"."""
    return any(row) and all(not c or fold(c) in _FOLDED_DAYS for c in row)


def _months(found: re.Match[str], where: str) -> tuple[int, ...]:
    """The months of a note: every month ("kas mėnesį"), or every other ("kas antrą mėnesį")."""
    months = tuple(int(m) for m in found["months"].split())
    step = 2 if found["every"] else 1
    if not months or months != tuple(range(months[0], 13, step)) or months[0] > step:
        raise ValueError(f"{where}: the months of a note: {found.group()!r}")
    return months


def _read(
    blocks: list[str | Rows], kind: Kind, where: str
) -> tuple[list[_Table], dict[Kind, tuple[int, ...]]]:
    """The tables of a file (its _blocks), and the months of Pabradė's and Magūnai's rules of
    each waste type (the packaging file's notes). Strict: a title of another file, text we don't
    read next to the tables, a table under no heading and title, and tables of another number or
    of other parts and waste types than the file's raise ValueError."""
    first = blocks[0] if blocks else ""
    if not isinstance(first, str) or fold(first) != TITLES[kind]:
        raise ValueError(f"{where}: the title {str(first)[:80]!r} isn't of the {LABELS[kind]}")
    part: frozenset[str] | None = None
    current: Kind | None = "household" if kind == "household" else None
    year: int | None = None
    tables: list[_Table] = []
    months: dict[Kind, tuple[int, ...]] = {}
    previous: str | Rows = first
    for block in blocks[1:]:
        if isinstance(block, str):
            folded = fold(block)
            if found := _HEADING.fullmatch(block):
                part = _part(found["names"], where)
                current = "household" if kind == "household" else None
            elif kind == "packaging" and (found := _TABLE_TITLE.fullmatch(folded)):
                current, year = WHAT[found["what"]], int(found["year"])
            elif kind == "packaging" and (found := _NOTE.fullmatch(folded)):
                note = WHAT[found["what"]]
                if frozenset(_elderships(found["names"], where)) != SOUTH or note in months:
                    raise ValueError(f"{where}: a note of {block[:80]!r}")
                months[note] = _months(found, where)
            else:
                raise ValueError(f"{where}: text we don't read next to the tables: {block[:80]!r}")
            previous = block
            continue
        if part is None or current is None:
            raise ValueError(f"{where}: a table under no heading of its elderships or waste type")
        last = tables[-1] if tables else None
        if (
            last is not None
            and not isinstance(previous, str)
            and (last.part, last.kind) == (part, current)
            and not _is_weekdays(block[0])
        ):
            _continue(last, block, where)  # the table goes on over a page
        else:
            tables.append(_Table(part, current, year, block))
        previous = block
    found_tables = [(t.part, t.kind) for t in tables]
    if len(found_tables) != len(TABLES[kind]) or set(found_tables) != TABLES[kind]:
        names = [("Pabradė" if p == SOUTH else "the nine", k) for p, k in found_tables]
        raise ValueError(f"{where}: tables of {names}")
    return tables, months


def _continue(table: _Table, rows: Rows, where: str) -> None:
    """Joins the rest of a table on the next page to it: a weekday table's places to its last
    row's cells, a dated table's rows to its rows."""
    if not _is_weekdays(table.rows[0]):
        table.rows += rows
        return
    last = table.rows[-1]
    for row in rows:
        if len(row) != len(last):
            raise ValueError(f"{where}: a table goes on with {len(row)} columns, not {len(last)}")
        for i, cell in enumerate(row):
            if cell and last[i] is None:
                raise ValueError(f"{where}: {cell[:40]!r} on the next page in no column")
            if cell:
                last[i] = f"{last[i]}\n{cell}" if last[i] else cell


def _columns(rows: Rows, where: str) -> list[tuple[Rule, str]]:
    """The rule and the places of each column of a weekday table: a row of weekdays, a row of
    the weeks of the month ("I", "III", or "I-III" in one cell), and a row of places, whose
    cells may cover two weeks' cells. Strict: other rows, a weekday or weeks we don't read, a
    column across two weekdays and a column without places raise ValueError."""
    if len(rows) != 3 or len({len(r) for r in rows}) != 1:
        raise ValueError(f"{where}: a weekday table of {len(rows)} rows: {rows[0]}")
    header, weeks, places = rows
    days: list[int] = []
    for cell in header:
        if cell:
            if fold(cell) not in _FOLDED_DAYS:
                raise ValueError(f"{where}: {cell!r} for a weekday")
            days.append(_FOLDED_DAYS[fold(cell)])
        elif days:
            days.append(days[-1])
        else:
            raise ValueError(f"{where}: a weekday table without a weekday in its first column")
    starts = [i for i, cell in enumerate(places) if cell is not None]
    if not starts or starts[0] != 0:
        raise ValueError(f"{where}: places of no column: {places[:2]}")
    columns: list[tuple[Rule, str]] = []
    for n, start in enumerate(starts):
        span = range(start, starts[n + 1] if n + 1 < len(starts) else len(places))
        if len({days[i] for i in span}) != 1:
            raise ValueError(f"{where}: places across two weekdays: {places[start][:40]!r}")
        written = " ".join(weeks[i] or "" for i in span)
        rule = parse_rule(f"{written} {WEEKDAY_NAMES[days[start]]}")
        if rule is None:
            raise ValueError(f"{where}: weeks of the month we don't read: {written!r}")
        if not clean_text(places[start]):
            raise ValueError(f"{where}: no places on {written} {WEEKDAY_NAMES[days[start]]}")
        columns.append((rule, places[start] or ""))
    return columns


# --- the places of Pabradė's and Magūnai's tables -----------------------------------

# A section of a column: "Pabradės sen.", "Magūnu sen." (sic), "Pabradės m.", "Pabradės
# miestas:", "Magūnų seniūnija:".
_SECTION = re.compile(rf"(?P<name>{_WORD})\s+(?P<type>sen\.|seniūnija|m\.|miestas)\s*:?")
# The shared containers of the town's apartment buildings: "Pabradės m. daugiabučiai namai",
# "... daugiabučiai n.", "... daugiab. namai".
_APARTMENTS = re.compile(rf"{_WORD}\s+m\.\s+daugiab\w*\.?\s+(?:namai|n\.)")
# A place: a village, a farmstead, a street, a garden community ("Pušaitės SB", "Pušaitės sodų
# bendrija").
_PLACE = re.compile(r".*\S\s+(?:(?:k|vs|g|skg)\.|SB|sodų\s+bendrija)")


def _label(found: re.Match[str], where: str) -> str:
    """ "Pabradės sen.", "Magūnų sen." or "Pabradės m." for a section of a column."""
    name = found["name"]
    if found["type"] in ("m.", "miestas"):
        if TOWNS.get(name) not in SOUTH:
            raise ValueError(f"{where}: a town of no eldership of Pabradė's tables: {name!r}")
        return f"{name} m."
    eldership = next((e for e in SOUTH if fold(e) == fold(name)), None)
    if eldership is None:
        raise ValueError(f"{where}: an eldership of no Pabradė table: {found.group()!r}")
    return f"{eldership} sen."


def south_places(text: str, where: str) -> str:
    """A column's places as a row's name, a section each: "Pabradės sen.: Baltadvario k., ...;
    Magūnų sen.: Dalininkų k., ...", "Pabradės m.: Keisūnų g., ...". A place written over two
    lines ("A.Mickevičiaus" "g.") is one. The apartment buildings' containers aren't read.
    Strict: places of no known kind or under no section, a section twice and a section without
    places raise ValueError."""
    lines = [line for raw in text.splitlines() if (line := clean_text(raw).rstrip(", "))]
    sections: dict[str, list[str]] = {}
    buffer = ""
    for i, line in enumerate(lines):
        buffer = f"{buffer} {line}".strip().rstrip(", ")
        following = fold(lines[i + 1]) if i + 1 < len(lines) else ""
        if _APARTMENTS.fullmatch(buffer):
            buffer = ""
        elif (found := _SECTION.fullmatch(buffer)) and not following.startswith("daugiab"):
            label = _label(found, where)
            if label in sections:
                raise ValueError(f"{where}: {label} twice in a column")
            sections[label] = []
            buffer = ""
        elif _PLACE.fullmatch(buffer):
            if not sections:
                raise ValueError(f"{where}: {buffer!r} under no eldership or town")
            list(sections.values())[-1].append(buffer)
            buffer = ""
    if buffer:
        raise ValueError(f"{where}: places of no known kind: {buffer[:60]!r}")
    if not sections or not all(sections.values()):
        raise ValueError(f"{where}: a section without places in {text[:60]!r}")
    return "; ".join(f"{label}: {', '.join(places)}" for label, places in sections.items())


# --- the places of the nine elderships' tables --------------------------------------


@dataclass(frozen=True)
class Part:
    """What a column of the nine elderships names: whole elderships but some villages and their
    town ("Švenčionių seniūnija (išskyrus Švenčionių miestą, Milkuškų, ... kaimus)"), a town
    ("Švenčionių miestas") or villages ("Milkuškų, Kukiškės, Medišionių kaimai"), whose
    elderships are those that leave them out."""

    what: str  # "elderships", "town" or "villages"
    names: tuple[str, ...]  # register names of the elderships, else genitives as written
    but: tuple[str, ...] = ()  # villages left out of the elderships
    but_town: str | None = None


_NAMES = rf"{_WORD}(?:\s*,\s*{_WORD}|\s+ir\s+{_WORD})*"
_PART = re.compile(
    rf"(?P<names>{_NAMES})\s+(?P<what>seniūnij(?:a|os)|miestas|kaim(?:as|ai))"
    r"(?:\s*\(\s*išskyrus\s+(?P<but>[^()]*?)\s*\))?"
)
_BUT = re.compile(
    rf"(?:(?P<town>{_WORD})\s+miestą\s*,\s*)?(?P<villages>{_WORD}(?:\s*,\s*{_WORD})*)\s+kaimus"
)
_AND = re.compile(r"\s+ir\s+")


def north_parts(text: str, where: str = "") -> list[Part]:
    """The places a column of the nine elderships names, joined by "ir" (and). Strict: places of
    another kind, an eldership the register doesn't have or not one of the nine, and a town we
    don't know raise ValueError."""
    text = clean_text(text)
    parts: list[Part] = []
    position = 0
    while True:
        found = _PART.match(text, position)
        if not found:
            raise ValueError(f"{where}: places we don't read: {text!r}")
        names = re.split(r"\s*,\s*|\s+ir\s+", found["names"])
        what = found["what"]
        if what.startswith("seniūnij"):
            elderships = _elderships(found["names"], where)
            if not set(elderships) <= NORTH:
                raise ValueError(f"{where}: an eldership read place by place: {text!r}")
            but = _BUT.fullmatch(found["but"]) if found["but"] else None
            if found["but"] and not but:
                raise ValueError(f"{where}: places left out we don't read: {found['but']!r}")
            villages = tuple(re.split(r"\s*,\s*", but["villages"])) if but else ()
            town = but["town"] if but else None
            parts.append(Part("elderships", tuple(elderships), villages, town))
        elif found["but"]:
            raise ValueError(f"{where}: places left out of a town or villages: {text!r}")
        elif what == "miestas":
            if len(names) != 1 or TOWNS.get(names[0]) not in NORTH:
                raise ValueError(f"{where}: a town we don't know: {found.group()!r}")
            parts.append(Part("town", tuple(names)))
        else:
            parts.append(Part("villages", tuple(names)))
        position = found.end()
        if position == len(text):
            return parts
        if not (gap := _AND.match(text, position)):
            raise ValueError(f"{where}: places we don't read: {text!r}")
        position = gap.end()


def check_north(texts: list[str], where: str) -> None:
    """The columns of a table of the nine elderships must name each of them whole once, the
    villages left out of one (with their town) in other columns, and no villages that none
    leaves out (their eldership is the one that does). Else ValueError."""
    parts = [p for text in texts for p in north_parts(text, where)]
    whole = sorted(e for p in parts if p.what == "elderships" for e in p.names)
    if whole != sorted(NORTH):
        raise ValueError(f"{where}: the elderships named whole are {whole}")
    left_out = sorted(fold(v) for p in parts for v in p.but)
    named = sorted(fold(v) for p in parts if p.what == "villages" for v in p.names)
    if left_out != named:
        raise ValueError(
            f"{where}: villages left out of an eldership {left_out}, named on their own {named}"
        )
    towns = {p.names[0] for p in parts if p.what == "town"}
    if missing := sorted({p.but_town for p in parts if p.but_town} - towns):
        raise ValueError(f"{where}: no column of {missing}, left out of an eldership")


# --- the tables into rows ------------------------------------------------------------


def _dated(rows: Rows, kind: Kind, year: int, where: str) -> list[tuple[str, Rule | None, set]]:
    """The places, the header's rule (if any) and the dates of each column of a table of the
    nine elderships: a row of places, then a date per column and row ("01.14"). Strict: a cell
    that isn't a date, a day the year doesn't have, a column without dates, and packaging
    without a date in every month raise ValueError."""
    header, *dates = rows
    if not dates or any(len(r) != len(header) for r in dates):
        raise ValueError(f"{where}: a dated table of {len(dates)} rows")
    columns: list[tuple[str, Rule | None, set]] = []
    for i, cell in enumerate(header):
        text = clean_text(cell)
        rule = None
        if found := _HEADER_RULE.fullmatch(text):
            text, rule = found["places"], parse_rule(found["rule"])
            if rule is None:
                raise ValueError(f"{where}: a rule we don't read: {found['rule']!r}")
        days: set[date] = set()
        for row in dates:
            written = clean_text(row[i])
            if not (day := _DATE.fullmatch(written)):
                raise ValueError(f"{where}: not a date: {written!r} ({text[:40]!r})")
            month, number = int(day[1]), int(day[2])
            if not 1 <= month <= 12 or not 1 <= number <= month_end(year, month).day:
                raise ValueError(f"{where}: {year} has no day {written!r}")
            days.add(date(year, month, number))
        if kind == "packaging" and {d.month for d in days} != set(range(1, 13)):
            raise ValueError(f"{where}: packaging of {text[:40]!r} not in every month")
        columns.append((text, rule, days))
    return columns


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of one file: a row per column and waste type, named after its places as the file
    writes them ("Pabradės sen.: Baltadvario k., ...", "Švenčionių seniūnija (išskyrus Milkuškų,
    Kukiškės, Medišionių kaimus)"). Mixed waste's rules give the dates of the file's window,
    Pabradė's packaging and glass rules those of their year's months. Strict (see _read,
    _columns, south_places, check_north, _dated): also a window or a year missing, and titles of
    another year than the link's raise ValueError."""
    if not content:
        raise ValueError(f"{source.file_name}: not downloaded")
    where = source.file_name
    if source.kind not in TITLES:
        raise ValueError(f"{where}: a file of {source.kind}")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        tables, months = _read(_blocks(pdf), source.kind, where)
    areas: list[Area] = []
    warnings: list[str] = []

    def add(kind: Kind, name: str, dates: set[date]) -> None:
        area = Area(kind, name, LABEL, dates=dates, provider=PROVIDER_ID)
        weekdays = {d.weekday() for d in dates}
        if len(weekdays) == 1:
            area.weekday = WEEKDAY_NAMES[weekdays.pop()]
        if not dates:
            raise ValueError(f"{where}: no {kind} dates for {name[:60]!r}")
        if any(a.id == area.id for a in areas):
            raise ValueError(f"{where}: two {kind} rows of {name[:60]!r}")
        areas.append(area)

    if source.kind == "household":
        start, end = getattr(source, "start", date.min), getattr(source, "end", date.min)
        if start == date.min or end < start:
            raise ValueError(f"{where}: no window for the rules' dates")
        for table in tables:
            columns = _columns(table.rows, where)
            if table.part == NORTH:
                check_north([text for _, text in columns], where)
            for rule, text in columns:
                name = clean_text(text) if table.part == NORTH else south_places(text, where)
                add("household", name, rule.dates(start, end))
        return ParseResult(areas, warnings)
    years = {t.year for t in tables}
    if len(years) != 1 or None in years:
        raise ValueError(f"{where}: tables of the years {sorted(map(str, years))}")
    (year,) = years
    if year != (getattr(source, "year", None) or year):
        raise ValueError(f"{where}: the tables are of {year}, the link says {source.year}")
    for table in tables:
        if table.part == NORTH:
            columns = _dated(table.rows, table.kind, year, where)
            check_north([text for text, _, _ in columns], where)
            for text, rule, dates in columns:
                ruled = rule.dates(min(dates), max(dates)) if rule else dates
                if rule and not dates <= ruled:
                    days = ", ".join(d.isoformat() for d in sorted(dates - ruled))
                    warnings.append(f"{where}: {table.kind} of {text!r} on {days}, not its rule's")
                add(table.kind, text, dates)
            continue
        if table.kind not in months:
            raise ValueError(f"{where}: no note of the months of Pabradė's {table.kind}")
        whole_year = date(year, 1, 1), date(year, 12, 31)
        for rule, text in _columns(table.rows, where):
            ruled = Rule(rule.weekday, rule.weeks, months[table.kind])
            add(table.kind, south_places(text, where), ruled.dates(*whole_year))
    return ParseResult(areas, warnings)


def parse_or_keep(
    source: SourceFile, content: bytes, published: Callable[[], dict] | None = None
) -> ParseResult:
    """parse_file, or for a file that can't be read, its rows of yesterday's data (`published`;
    None: raise instead): the rows of its waste types."""
    try:
        return parse_file(source, content)
    except Exception as error:  # any failure of one file must not stop the other
        if published is None:
            raise
        kinds = FILE_KINDS.get(source.kind, (source.kind,))
        kept = build.published_rows(published(), PROVIDER, lambda r: r["kind"] in kinds)
        if not kept:
            raise
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} {LABELS[source.kind]} rows are kept"
            ],
        )


# --- the places ------------------------------------------------------------------

# A garden community of the rows: "Pušaitės SB", "Pušaitės sodų bendrija".
_GARDEN = re.compile(rf"\b(?P<name>{_WORD})\s+(?:SB|sodų\s+bendrija)\b")
# A section of a town's streets: "Pabradės m.:".
_TOWN_SECTION = re.compile(rf"\b(?P<name>{_WORD})\s+m\.:")


class Routes(raseiniai.Routes):
    """Reads the places of the rows as raseiniai.Routes reads Raseinių r.'s (aratc.Routes):

        Pabradės sen.: Baltadvario k., ...; Magūnų sen.: Dalininkų k., ...   sections
        Pabradės sen.: Žvėrinės g., Skirlėnų k., ...                          a street of the town
        Pabradės m.: Keisūnų g., ..., Pušaitės SB, ..., Silniškų vs.          the town's streets
        Adutiškio, Svirkų seniūnijos ir Milkuškų, Kukiškės, Medišionių kaimai
        Švenčionių seniūnija (išskyrus Milkuškų, Kukiškės, Medišionių kaimus)
        Švenčionių miestas

    A street before any village of an eldership's section is its town's (Pabradė's). A garden
    community is the town's streets of its name and a number ("Pušaitės SB": Pušaitės 1-oji g.
    to 12-oji g.). The nine elderships are whole ("Visoje Adutiškio sen."), but the villages
    and the town a row leaves out; villages named on their own are of the eldership that a row
    of their kind leaves them out of (prepare). No street gets "no pickup" (build_locations):
    Pabradė's rows name the streets of its individual houses, the apartment buildings' shared
    containers aren't read, and nothing says a street has none."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        # aratc.Routes for this municipality (raseiniai.Routes' own sets Raseinių r.'s).
        self.municipalities = (MUNICIPALITY,)
        aratc.Routes.__init__(self, index, provider, variants)
        self.towns_by_street: set[int] = set()
        # The elderships that leave each village out, by the rows of each kind (prepare).
        self.left_out: dict[str, dict[str, set[str]]] = defaultdict(dict)

    def prepare(self, areas: list[Area]) -> None:
        """First the villages the rows leave out of their elderships, so a row naming them
        finds them in those."""
        for area in areas:
            try:
                parts = north_parts(area.name)
            except ValueError:
                continue
            for part in parts:
                for village in part.but:
                    self.left_out[area.kind].setdefault(fold(village), set()).update(part.names)
        super().prepare(areas)

    def section(self, district: str, text: str) -> list:
        """aratc.Routes' section, with a street before any village read as the eldership's
        town's ("Pabradės sen.: Žvėrinės g."), if it has one."""
        if self.town is aratc._NO_TOWN:
            towns = [
                s
                for s in self.places[self.municipality.label]
                if s.district == district and s.abbr == "m."
            ]
            self.town = towns[0] if len(towns) == 1 else aratc._NO_TOWN
        return aratc.Routes.section(self, district, text)

    def spellings(self, text: str) -> str:
        try:
            parts = north_parts(text)
        except ValueError:
            return _GARDEN.sub(self._garden, _TOWN_SECTION.sub(self._town_section, text))
        return " ".join(self._part(part) for part in parts)

    def _town_section(self, found: re.Match[str]) -> str:
        """ "Pabradės m.:" is the section of its eldership: its streets are the town's."""
        eldership = TOWNS.get(found["name"])
        return f"{eldership} sen.:" if eldership else found.group()

    def _garden(self, found: re.Match[str]) -> str:
        """ "Pušaitės SB": the streets of a town named after it with a number, if one town has
        them ("Pušaitės 1-oji g."); else as written (a place we don't know)."""
        pattern = re.compile(re.escape(found["name"]) + r"\s+\d+-(?:oji|asis)")
        towns = [
            (s, streets)
            for s in self.places[self.municipality.label]
            if s.abbr == "m." and (streets := [t for t in s.streets if pattern.fullmatch(t.name)])
        ]
        if len(towns) != 1:
            return found.group()
        return ", ".join(t.label for t in towns[0][1])

    def _villages(self, name: str, elderships: set[str]) -> list[Settlement]:
        key = fold(name)
        return [
            s
            for s in self.places[self.municipality.label]
            if s.district in elderships and key in (fold(s.genitive), fold(s.name))
        ]

    def _part(self, part: Part) -> str:
        """A part as aratc.Routes reads it: "Visoje Adutiškio sen.", "Švenčionių sen.: tik
        Švenčionių sen. esantys kaimai (be Švenčionių, Milkuškų, ...)", "Švenčionių sen.:
        Švenčionių m.", "Švenčionių sen.: Milkuškų k.". A village found in none of its elderships
        or in two is a place we don't know."""
        if part.what == "town":
            (town,) = part.names
            return f"{TOWNS[town]} sen.: {town} m."
        if part.what == "villages":
            texts: list[str] = []
            for village in part.names:
                elderships = self.left_out[self.kind].get(fold(village)) or set(ELDERSHIPS)
                found = self._villages(village, elderships)
                if len(found) == 1:
                    texts.append(f"{found[0].district} sen.: {village} k.")
                else:
                    self.unknown.append(f"{village} k.")
            return " ".join(texts)
        texts = []
        for eldership in part.names:
            but = [v for v in part.but if self._villages(v, {eldership})]
            if part.but_town and TOWNS.get(part.but_town) == eldership:
                but.append(part.but_town)
            if but:
                texts.append(
                    f"{eldership} sen.: tik {eldership} sen. esantys kaimai (be {', '.join(but)})"
                )
            else:
                texts.append(f"Visoje {eldership} sen.")
        self.unknown += [
            f"{v} k." for v in part.but if len(self._villages(v, set(part.names))) != 1
        ]
        return " ".join(texts)


PROVIDER = Provider(
    id=PROVIDER_ID,
    name=NAME,
    url=PAGE_URL,
    elderships=ELDERSHIPS,
    # Names the register writes otherwise (mixed waste, Pabradės sen.).
    aliases=(
        # Thursday's "Burbiškės II k." is Burbliškė II (one letter off, which the reader takes),
        # Friday's "Burbiškių I k." Burbliškė I.
        ("Burbiškių I k.", "Burbliškės I k."),
        # Listed next to "Meškerinės I k." and "Mažalotė I k.", on the same day: the register has
        # one Meškerinė and one Mažalotė.
        ("Meškerinės II k.", "Meškerinės k."),
        ("Mažalotė II k.", "Mažalotės k."),
    ),
    kinds=("household", "packaging", "glass"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.SVENCIONYS_MUNICIPALITY,
    snapshot.SVENCIONYS_REGISTRY_FILE,
    snapshot.SVENCIONYS_ADDRESSES_FILE,
    # 2026: 16 mixed waste rows (9 of Pabradė's table, 7 of the nine elderships'), 13 of
    # packaging and 13 of glass (7 and 6), which gave a mixed waste schedule to 522 of the 565
    # settlements (the other 43 are small villages of Pabradės and Magūnų sen. no row names).
    min_areas={"household": 12, "packaging": 10, "glass": 10},
    min_household_places=400,
    # About 14,000 addresses in 2026.
    min_address_points=10_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Next year's packaging file continues this year's rows that cover the same places
    (tratc.combine). Not mixed waste: its rules' rows are one file's, whatever the year of their
    first date."""
    return tratc.combine(
        [(file, result) for file, result in parsed if file.kind == "packaging"],
        registry,
        today,
        MUNICIPALITY,
    )


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
    # The folder of one provider, as raseiniai.py builds its own.
    return raseiniai.run(args.out, args.keep_days, published, MUNICIPALITY, source)


if __name__ == "__main__":
    raise SystemExit(main())

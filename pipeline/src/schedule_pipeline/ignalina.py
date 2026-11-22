"""Ignalinos rajonas: the schedules of SĮ „Kompata“, the municipal company that empties the
containers of the individual houses of the whole municipality (kompata.lt): mixed waste,
packaging and glass, and food waste in the town and a few villages.

Its pages of schedules ("Grafikai") link a PDF made in Excel for the whole municipality per
waste type and period, then the same tables cut into a file per eldership:

    KOMUNALINIŲ ATLIEKŲ SURINKIMO IŠ INDIVIDUALIŲ KONTEINERIŲ 2026 M. LAPKRIČIO MĖN. - 2027 M.
    BALANDŽIO MĖN. GRAFIKAS                                          mixed waste, half a year
    2026 metų plastiko, popieriaus, metalo, stiklo pakuočių surinkimo iš individualių
    konteinerių grafikas (atsisiųsti PDF)                            packaging and glass, a year
    MAISTO ATLIEKŲ SURINKIMO IŠ INDIVIDUALIŲ KONTEINERIŲ 2026 M. LAPKRIČIO - 2027 M. BALANDŽIO
    MĖN. GRAFIKAS                                                    food waste, half a year
    Ceikinių seniūnija (atsisiųsti PDF)                              an eldership's part

The files of the whole municipality are found by these texts; the elderships' parts (their links
name no schedule) aren't read. Nor is the mixed waste of the garden communities ("... IŠ SODŲ
BENDRIJŲ 2026 M. SPALIO - GRUODŽIO MĖN. ..."): two gardens the register doesn't know, and three
villages with the dates the main file gives them.

A file is a table with a section per eldership ("IGNALINOS SENIŪNIJA", "N. DAUGĖLIŠKIO
SENIŪNIJA") and the town ("IGNALINOS MIESTAS"), each under a row of months, and a row of days per
group of villages:

    VIETOVĖS PAVADINIMAS                   | Mėnuo
    IGNALINOS SENIŪNIJA                    | Lapkritis | Gruodis    | Sausis | ...
    Zuikiškė, Panižiškė                    | 2, 16, 30 | 14, 28     | 11, 25 | ...

(packaging: a column "MĖNUO" with the rows "POP/PLAST/M" and "STIKLAS", under "01 ... 12"). The
tables are read with pdfplumber's table finder. The half years are November to April and May to
October, so a period crosses the new year: a month from the period's first on is of its first
year, the others of the next. Strict: a title of other months or another year than the link's, a
month of another period, a section of no eldership, a cell that isn't days, a day the month
doesn't have, a row of no waste type, villages without days, and dates that mostly miss one
working day (the wrong year) raise. Text outside the tables other than the usual notes (the phone
numbers, putting the containers out by 7 a.m.) is a warning: a change of the schedule may be
written there.

The rows are named after their section and places ("Ignalinos sen.: Zuikiškė, Panižiškė",
"Ignalinos m.: Vilniaus - Budrių - Ažušilės gatvių kvartalas"), read by Routes. Every file that
still has dates to publish is read, so the next period's file is read as soon as the page links
it; until it starts, its rows continue those in force that cover the same places (combine). When
a period ends and nothing newer is linked, its rows keep their last dates (build.current_rows),
with a warning.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.ignalina --out ../site/ignalinos-r
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
from .kretinga import _Links, _month_word, file_name
from .locations import _WORD, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold
from .sratc import _continue

# The pages of schedules: mixed waste, packaging and food waste. The files are found by the
# texts of their links on any of them.
PAGES = (
    "https://www.kompata.lt/grafikai/puslapis/",
    "https://www.kompata.lt/grafikai/pakuociu-surinkimo-grafikas/",
    "https://www.kompata.lt/grafikai/maisto-atlieku-surinkimo-grafikas/",
)
PAGE_URL = PAGES[0]
COMPANY = "SĮ „Kompata“"
LABEL = "Ignalinos r."  # every row's `district`


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of a page, with the period its link's text (else its name) gives: from the first
    day of its first month to the last day of its last, which may be of the next year."""

    start: date = date.min
    end: date = date.min

    @property
    def months(self) -> list[tuple[int, int]]:
        """The period's months in order, (year, month)."""
        months, year, month = [], self.start.year, self.start.month
        while date(year, month, 1) <= self.end:
            months.append((year, month))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return months


# The waste type of a file by its link's text (folded): food waste ("Maisto atliekų ..."),
# packaging ("... pakuočių surinkimo ..."), mixed waste ("Komunalinių atliekų surinkimo iš
# individualių konteinerių ..."). The garden communities' mixed waste ("... iš sodų bendrijų
# ...") isn't read.
FILES: tuple[tuple[re.Pattern[str], Kind | None], ...] = (
    (re.compile(r"\bsodu bendrij"), None),
    (re.compile(r"\bmaist"), "food"),
    (re.compile(r"\bpakuoc"), "packaging"),
    (re.compile(r"\bkomunalin"), "household"),
)
LABELS: dict[Kind, str] = {
    "household": "mixed waste",
    "packaging": "packaging",
    "food": "food waste",
}
# The kinds the pages must have: without them the build fails, and yesterday's data is kept.
REQUIRED: tuple[Kind, ...] = ("household", "packaging")
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}


def period(text: str) -> tuple[date, date] | None:
    """The months a link's text, a file's name or a title names: "2026 M. LAPKRIČIO MĖN. - 2027
    M. BALANDŽIO MĖN.", "2026-2027 METŲ LAPKRIČIO-BALANDŽIO MĖN.", "2026 m. spalio - gruodžio
    mėn.", "..._2026m_-_2027m_11-04men" or "2026 metų" (the year), from the first day of the
    first month to the last day of the last; None for no year, or what isn't one period of at
    most a year."""
    folded = fold(text.replace("_", " "))
    years = sorted({int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", folded)})
    months = [month for word in folded.split() if (month := _month_word(word))]
    if not months and (match := re.search(r"\b(\d{1,2}) (\d{1,2}) ?men\b", folded)):
        months = [int(match[1]), int(match[2])]
    if not years or len(years) > 2 or len(months) not in (0, 2):
        return None
    first, last = months or (1, 12)
    if not (1 <= first <= 12 and 1 <= last <= 12):
        return None
    start_year = years[0]
    end_year = years[1] if len(years) == 2 else start_year + (last < first)
    if (end_year - start_year) * 12 + last - first not in range(12):
        return None
    return date(start_year, first, 1), month_end(end_year, last)


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The schedules of the whole municipality a page links, in its order, by the texts of their
    links: the waste type and the period (else the period of the file's name); and warnings about
    schedules of no kind we read. Links that name no schedule ("Ceikinių seniūnija (atsisiųsti
    PDF)", an eldership's part of a file) aren't read."""
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
        if "grafik" not in words:
            continue
        kinds = [kind for pattern, kind in FILES if pattern.search(words)]
        if not kinds:
            warnings.append(f"{name} ({described!r}): a schedule of no kind we read")
            continue
        if kinds[0] is None:
            continue
        found = period(described) or period(name)
        if found is None:
            warnings.append(f"{name} ({described!r}): no period in its link or name; not read")
            continue
        files.append(ScheduleFile(kinds[0], url, name, start=found[0], end=found[1]))
    return files, warnings


def select_files(
    files: list[ScheduleFile], today: date, keep_days: int = 31
) -> tuple[list[ScheduleFile], list[str]]:
    """Of each kind, the files with dates still to publish (their period ends at most
    `keep_days` before today), so the next period's file is read as soon as it's linked; if none
    runs to today, also the latest, whose rows keep their last dates. Of two files for one
    period, the one linked first. A page without a mixed waste or packaging file raises
    ValidationError; without food waste, a warning."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    cutoff = today - timedelta(days=keep_days)
    for kind, label in LABELS.items():
        mine: dict[tuple[date, date], ScheduleFile] = {}
        for file in (f for f in files if f.kind == kind):
            if (newer := mine.get((file.start, file.end))) is not None:
                warnings.append(
                    f"{file.file_name}: not read, {newer.file_name} is linked first for "
                    f"{file.start} - {file.end}"
                )
                continue
            mine[(file.start, file.end)] = file
        if not mine:
            if kind in REQUIRED:
                raise build.ValidationError(f"no {label} schedule on the pages")
            warnings.append(f"no {label} schedule on the pages")
            continue
        running = [f for f in mine.values() if f.end >= cutoff]
        latest = max(mine.values(), key=lambda f: f.end)
        if not any(f.end >= today for f in running) and latest not in running:
            running.append(latest)
        selected += sorted(running, key=lambda f: f.start)
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    found: list[ScheduleFile] = []
    warnings: list[str] = []
    for page in PAGES:
        html = http.get(page, timeout=60).decode("utf-8", errors="replace")
        files, notes = find_files(html, page)
        found += [f for f in files if all(f.url != other.url for other in found)]
        warnings += [n for n in notes if n not in warnings]
    chosen, notes = select_files(found, today, keep_days)
    return [(f, http.get(f.url, timeout=120)) for f in chosen], warnings + notes


# --- the tables ------------------------------------------------------------------

# The days of a month's cell: "3, 17", "8,22", "30".
_DAYS = re.compile(r"\d{1,2}(?:\s*[,;]\s*\d{1,2})*")
# The rows of the packaging file (folded): paper, plastic and metal, and glass.
ROW_LABELS: dict[str, Kind] = {"pop plast m": "packaging", "stiklas": "glass"}
# The words of each file's title (folded).
TITLES: dict[Kind, str] = {
    "household": "komunaliniu atlieku",
    "packaging": "pakuociu",
    "food": "maisto atlieku",
}
# The municipality's elderships (register names), and the town's section: "IGNALINOS MIESTAS".
ELDERSHIPS = frozenset(
    {
        "Ceikinių",
        "Didžiasalio",
        "Dūkšto",
        "Ignalinos",
        "Kazitiškio",
        "Linkmenų",
        "Mielagėnų",
        "Naujojo Daugėliškio",
        "Rimšės",
        "Tverečiaus",
        "Vidiškių",
    }
)
TOWN = "Ignalinos m."
TOWN_ELDERSHIP = "Ignalinos miesto"
_TOWN_PREFIX = re.compile(r"^Ignalinos\s+miestas\s*[–-]\s*", re.I)
# Rows in a file, at least: in 2026 the mixed waste file had 63, packaging 61, food waste 7.
MIN_ROWS: dict[Kind, int] = {"household": 45, "packaging": 45, "food": 5}
# Of a row's dates, at least this share on one working day (holidays move a few): days of the
# wrong year fall on other weekdays. Not glass, twice a year.
SAME_WEEKDAY = 0.75
# Lines outside the tables every file has (folded starts): the approval ("TVIRTINU", then the
# head's title and name), the phone numbers, the contracts, putting the containers out by 7
# a.m., that the schedule may change, and the rules of sorting.
_NOTES = (
    "klientai konsultuojami",
    "individualus komunaliniu atlieku konteineriai",
    "teikimo sutartis",
    "konteineriai turi buti isstatyti",
    "konteineriai su pakuociu atliekomis turi buti isstatyti",
    "grafikas gali buti koreguojamas",
    "jei rusiavimo konteineryje",
    "jeigu rusiavimo konteineryje",
    "tinkamai isrusiavus",
    "informacija kaip teisingai rusiuoti",
    "primename kad rusiavimo konteineriai",
)


@dataclass
class _Block:
    """A row of the table: its section, its places, and the dates of each waste type."""

    section: str
    places: str
    dates: dict[Kind, set[date]] = field(default_factory=lambda: defaultdict(set))
    label: Kind | None = None  # the packaging file's row being read


def _section(text: str, where: str) -> str:
    """The names of a section's rows start with: "IGNALINOS MIESTAS" is "Ignalinos m.", "N.
    DAUGĖLIŠKIO SENIŪNIJA" and "NAUJOJO DAUGĖLIŠKIO SENIŪNIJA" are "Naujojo Daugėliškio sen."."""
    folded = fold(text)
    if folded == fold(f"{TOWN.split()[0]} miestas"):
        return TOWN
    if match := re.fullmatch(r"(.+) seniunija", folded):
        key = re.sub(r"^n ", "naujojo ", match[1])
        if found := [e for e in ELDERSHIPS if fold(e) == key]:
            return f"{found[0]} sen."
    raise ValueError(f"{where}: a section of no eldership of the municipality: {text!r}")


def _months(cells: list[str | None], kind: Kind, where: str) -> list[int] | None:
    """The months of a section's first row: their names ("Lapkritis ... Balandis"), or for
    packaging their numbers after "MĖNUO" ("01 ... 12"); None for another row."""
    texts = [fold(c or "") for c in cells]
    if kind == "packaging":
        if not texts or texts[0] != "menuo":
            return None
        if not all(re.fullmatch(r"\d{1,2}", t) for t in texts[1:]):
            raise ValueError(f"{where}: months {cells[1:]}")
        return [int(t) for t in texts[1:]]
    if sum(t in aratc.MONTHS for t in texts) < 2:
        return None
    if not all(t in aratc.MONTHS for t in texts):
        raise ValueError(f"{where}: {cells} for the months")
    return [aratc.MONTHS[t] for t in texts]


def _dates(text: str, year: int, month: int, where: str) -> set[date]:
    if not _DAYS.fullmatch(text):
        raise ValueError(f"{where}: unrecognised days {text!r}")
    last = month_end(year, month).day
    days = [int(d) for d in re.findall(r"\d+", text)]
    for day in days:
        if not 1 <= day <= last:
            raise ValueError(f"{where}: month {month} of {year} has no day {day}")
    return {date(year, month, day) for day in days}


def _notes(page, tables, where: str) -> list[str]:
    """Warnings about the lines of a page outside its tables that aren't the usual notes."""
    outside = page
    for table in tables:
        outside = outside.outside_bbox(table.bbox)
    warnings: list[str] = []
    approval = 0  # lines of the approval left: "TVIRTINU", "Vadovė", the head's name
    for line in (outside.extract_text() or "").splitlines():
        text = clean_text(line)
        folded = fold(text)
        if not folded:
            continue
        if folded == "tvirtinu":
            approval = 2
        elif approval:
            approval -= 1
        elif not folded.startswith(_NOTES):
            warnings.append(f"{where} page {page.page_number}: {text[:100]!r} next to the table")
    return warnings


def _read(pdf, source: ScheduleFile) -> tuple[str, list[_Block], list[str]]:
    """The title (the table's first row), the rows and the warnings of a file. A table goes on
    over pages; a row's places and its days may be rows of their own to the table finder."""
    where = source.file_name
    kind = source.kind
    title: str | None = None
    section = ""
    columns: dict[int, tuple[int, int]] = {}  # a cell's index: its (year, month)
    width = 0  # cells of the section's rows
    blocks: list[_Block] = []
    block: _Block | None = None
    notes: list[str] = []
    for page in pdf.pages:
        tables = sorted(page.find_tables(), key=lambda t: t.bbox[1])
        notes += _notes(page, tables, where)
        for table in tables:
            for row in table.extract():
                cells = [None if c is None else clean_text(c) for c in row]
                if not any(cells):
                    continue
                first, rest = cells[0] or "", cells[1:]
                if title is None:
                    if any(rest) or "grafik" not in fold(first):
                        raise ValueError(f"{where}: no title above the table: {first[:60]!r}")
                    title = first
                    continue
                if fold(first) == "vietoves pavadinimas":
                    if {fold(c or "") for c in rest} - {"", "menuo"}:
                        raise ValueError(f"{where}: a header of {cells}")
                    continue
                found = _months(rest, kind, where)
                if found is not None:
                    expected = [month for _, month in source.months]
                    if found != expected:
                        raise ValueError(
                            f"{where}: months {found}, the link says {source.start} - {source.end}"
                        )
                    section = _section(first, where)
                    offset = 1 + len(rest) - len(found)
                    columns = {offset + i: ym for i, ym in enumerate(source.months)}
                    width, block = len(cells), None
                    continue
                if not columns:
                    raise ValueError(f"{where}: {first[:60]!r} above the first section")
                if len(cells) != width:
                    raise ValueError(f"{where}: a row of {len(cells)} cells under {width} columns")
                if first:
                    if block is not None and not block.dates:
                        raise ValueError(f"{where}: places without days: {block.places[:60]!r}")
                    places = re.sub(r"\s*,\s*", ", ", first)
                    if section == TOWN:
                        # "Ignalinos miestas – Vilniaus - Budrių - Ažušilės gatvių kvartalas"
                        # (packaging): the quarter, as the other files name it.
                        places = _TOWN_PREFIX.sub("", places)
                    block = _Block(section, places)
                    blocks.append(block)
                if block is None:
                    raise ValueError(f"{where}: days without places: {cells}")
                if kind == "packaging" and (label := fold(cells[1] or "")):
                    if label not in ROW_LABELS:
                        raise ValueError(f"{where}: a row of no waste type we read: {cells[1]!r}")
                    block.label = ROW_LABELS[label]
                labels = 2 if kind == "packaging" else 1
                if stray := [
                    c for i, c in enumerate(cells[labels:], labels) if c and i not in columns
                ]:
                    raise ValueError(f"{where}: {stray} outside the months' columns")
                days = {i: cells[i] for i in columns if cells[i]}
                if not days:
                    continue
                row_kind = block.label if kind == "packaging" else kind
                if row_kind is None:
                    raise ValueError(f"{where}: days of no waste type: {block.places[:60]!r}")
                for i, text in days.items():
                    year, month = columns[i]
                    block.dates[row_kind] |= _dates(text or "", year, month, where)
    if title is None:
        raise ValueError(f"{where}: no table")
    if block is not None and not block.dates:
        raise ValueError(f"{where}: places without days: {block.places[:60]!r}")
    return title, blocks, notes


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of one file: a row per group of places and waste type, named after its section
    and places ("Ignalinos sen.: Zuikiškė, Panižiškė"). Strict (see _read): also a title of
    another waste type or period than the link's, too few rows, and dates that mostly miss one
    working day raise ValueError."""
    where = source.file_name
    if not isinstance(source, ScheduleFile) or source.start == date.min:
        raise ValueError(f"{where}: a file of no period")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        title, blocks, warnings = _read(pdf, source)
    label = LABELS[source.kind]
    if period(title) != (source.start, source.end) or TITLES[source.kind] not in fold(title):
        raise ValueError(
            f"{where}: the title {title[:100]!r} isn't of the {label} of {source.start} - "
            f"{source.end}"
        )
    if len(blocks) < MIN_ROWS[source.kind]:
        raise ValueError(f"{where}: only {len(blocks)} rows (expected {MIN_ROWS[source.kind]})")
    areas: dict[str, Area] = {}
    for block in blocks:
        name = f"{block.section}: {block.places}"
        if source.kind == "packaging" and not block.dates.get("packaging"):
            raise ValueError(f"{where}: no packaging dates for {name[:60]!r}")
        for kind, dates in block.dates.items():
            weekdays = Counter(d.weekday() for d in dates)
            weekday, times = weekdays.most_common(1)[0]
            if kind != "glass" and (times < SAME_WEEKDAY * len(dates) or weekday > 4):
                raise ValueError(
                    f"{where}: the {kind} dates of {name[:60]!r} aren't on one working day: "
                    "the wrong year or months?"
                )
            area = Area(kind, name, LABEL, provider=PROVIDER_ID, dates=set(dates))
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekday]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{where}: {kind} of {name[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    return ParseResult(list(areas.values()), warnings)


# --- the places ------------------------------------------------------------------

# An eldership's section of a row: "Ignalinos sen.:", "Naujojo Daugėliškio sen.:" (aratc's marks
# have one word).
_ELDERSHIP = re.compile(
    rf"(?:\b(?P<scope>Visoje|Dalyje|Dalis)\s+)?"
    rf"\b(?P<name>(?:Naujojo\s+)?{_WORD}(?:\s+(?i:miesto))?)\s+(?i:sen\b\.?|seniūnij\w*)\s*[:,]?",
    re.U,
)
# The town's quarters: "Vilniaus - Budrių - Ažušilės gatvių kvartalas".
_QUARTER = re.compile(rf"(?P<streets>{_WORD}(?:\s*-\s*{_WORD})+)\s+gatvių\s+kvartal\w*")
# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Azos k. (sezonas)", "Bendoriškė, Pakryžė, Poviliškė (sezonas)": the summer houses of the
    # row's places, collected from May to October; not a part of the last one.
    (re.compile(r"\s*\(\s*sezonas\s*\)", re.I), ""),
    # "Kandrotiškė (I)", "Girutiškė (II)": the register's "Kandrotiškė I".
    (re.compile(r"\s*\(\s*(I{1,3})\s*\)"), r" \1"),
    # "Antagavė (prie Gavaičio ež.)": a part of the village, by the lake (another row names
    # Antagavė, so the app asks).
    (re.compile(r"\s*\(\s*prie\b[^()]*\)"), ""),
    # "Linkmenų sen.: ..., Bajorai, ...": the eldership's Bajorai are Naujieji Bajorai and
    # Senieji Bajorai (Bajorai I-III are Kazitiškio sen.'s).
    (
        re.compile(r"^(Linkmenų sen\.:.*?)\bBajorai\b(?!\s+I)"),
        r"\1Naujieji Bajorai, Senieji Bajorai",
    ),
)


def _streets(match: re.Match[str]) -> str:
    return ", ".join(f"{street.strip()} g." for street in match["streets"].split("-"))


class Routes(raseiniai.Routes):
    """Reads the places of the rows as raseiniai.Routes reads Raseinių r.'s (aratc.Routes): the
    villages of each eldership's section in the nominative ("Ignalinos sen.: Zuikiškė,
    Panižiškė"), and the town's quarters, each the houses of the streets it is named after
    ("Ignalinos m.: Vilniaus - Budrių - Ažušilės gatvių kvartalas": Vilniaus g., Budrių g. and
    Ažušilės g.).

    A name of villages the register numbers ("Bajorai" for Bajorai I, II and III) is those the
    rows of its kind don't name with their numeral ("Bajorai (I)"), else all of them.

    No street gets "no pickup" (build_locations): the town's quarters name three streets each,
    and nothing says the town's other streets have none. A street no row names is left to the
    app, which offers the town's rows."""

    eldership = _ELDERSHIP

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        # aratc.Routes for this municipality (raseiniai.Routes' own sets Raseinių r.'s).
        self.municipalities = (MUNICIPALITY,)
        aratc.Routes.__init__(self, index, provider, variants)
        self.towns_by_street: set[int] = set()
        # The numbered villages the rows of each kind name with their numeral, per eldership.
        self.numbered: dict[tuple[str, str], set[int]] = defaultdict(set)

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return _QUARTER.sub(_streets, text)

    def prepare(self, areas: list[Area]) -> None:
        """First the numbered villages the rows name with their numerals, so a row reads the
        same whatever rows were read before it (also for combine's signatures)."""
        for area in areas:
            self.clauses(area)
        super().prepare(areas)

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        found = super().settlements(name, numerals, kind, district)
        mine = self.numbered[(self.kind, district)]
        if numerals:
            mine |= {s.code for s in found}
        elif len(found) > 1 and all(
            re.fullmatch(re.escape(fold(name)) + r" i{1,3}", fold(s.name)) for s in found
        ):
            found = [s for s in found if s.code not in mine] or found
        return found


PROVIDER_ID = "ignalina"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=COMPANY,
    url=PAGE_URL,
    elderships=ELDERSHIPS | {TOWN_ELDERSHIP},
    # Names the register writes otherwise.
    aliases=(
        ("Senas Daugėliškis", "Senasis Daugėliškis"),
        ("Naujas Daugėliškis", "Naujasis Daugėliškis"),
        ("Kavoliškės", "Kovališkės"),  # Rimšės sen.
    ),
    kinds=("household", "packaging", "glass", "food"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.IGNALINA_MUNICIPALITY,
    snapshot.IGNALINA_REGISTRY_FILE,
    snapshot.IGNALINA_ADDRESSES_FILE,
    # 2026: 63 rows of mixed waste and 61 of packaging and glass, which gave a mixed waste
    # schedule to 264 of the 699 settlements (8,800 of the 10,700 addresses).
    min_areas={"household": 45, "packaging": 45, "glass": 45},
    min_household_places=200,
    # About 10,700 addresses in 2026.
    min_address_points=7_500,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- this period and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins the rows of the files of later periods to those of the period in force, in place,
    each kind on its own (sratc._continue, as kretinga.combine joins Kretingos r.'s half years):
    a row of the next period that covers the same places as one in force gives it its dates; the
    rest wait, with a warning, until their period starts. Rows of earlier periods are dropped.

    Files of one kind whose periods overlap raise ValueError (select_files reads one file per
    period). A kind whose files have all ended keeps its rows, with their last dates
    (build.current_rows), and a warning; so does one with no file for today, whose next one has
    started early."""
    warnings: list[str] = []
    groups: dict = defaultdict(lambda: defaultdict(list))
    for kind, label in LABELS.items():
        files = sorted(
            ((s, r) for s, r in parsed if s.kind == kind and r.areas),
            key=lambda p: getattr(p[0], "start", date.min),
        )
        for (source, _), (other, _) in zip(files, files[1:], strict=False):
            if getattr(other, "start", date.min) <= getattr(source, "end", date.max):
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
    reader.prepare([area for _, result in parsed for area in result.areas])
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

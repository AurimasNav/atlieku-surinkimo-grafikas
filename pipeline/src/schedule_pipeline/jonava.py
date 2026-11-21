"""Jonavos rajonas: the schedules of UAB „Jonavos paslaugos“ (jonavospaslaugos.lt), which
empties the containers of the individual houses of the municipality: mixed waste, packaging and
glass.

Two pages link a one-page PDF per eldership: the elderships' page ("Bukonių sen. 2026 m.", "Rūklos
sen. 2026 m.", ...) and the town's ("Komunalinių (buitinių) ir pakuotės atliekų surinkimo
grafikas iš individualių namų valdų 2026 m."). The files are found by these texts and the year in
them; each file's title names its eldership and year ("... iš individualių namų valdų Bukonių
seniūnijoje 2026 metų sausio - gruodžio mėn."), which must agree. Bulky and hazardous waste,
collected by registration, isn't read. The shared containers of the town's apartment buildings
have a page of their own, which isn't read either. A new year's files are expected in December.

A file is one route, a table read with pdfplumber's table finder:

    Biržuliai, Bukonys, Gaižūnai, ... Šilų s. Vainiai                   the places
    Sausis   | Vasaris | ... | Gruodis | Renkamos atliekos
    2; 16; 30| 13; 27  | ... | 4; 18   | Komunalinės (buitinės) atliekos (pagal sutartį 2 k/mėn.)
    2; 30    | 27      | ... | 4       | Komunalinės (buitinės) atliekos (pagal sutartį 1 k/mėn.)
    19       | 16      | ... | 21      | Popieriaus, plastiko, metalo pakuotės atliekos
    6        |         | ... |         | Stiklo pakuotės atliekos
             | 11      | ... |         | Didelių gabaritų ir pavojingų atliekų surinkimas ...

Mixed waste is emptied twice or once a month, as a household's contract says, and in the town
also every week ("Kiekvieną KETVIRTADIENĮ (DĖMESIO: vietoje sausio 1 d. konteineriai bus
aptarnaujami sausio 3 d.)"): a row each, told apart by `group` ("2 kartus per mėnesį (pagal
sutartį)"), so the app asks which applies. The places are the eldership's villages in the
nominative, then those of others ("Šilų s. Vainiai"); the town's file has "Jonavos miestas",
the whole town: no file lists its streets, so each of them gets the town's rows, those of
apartment buildings too.

The places are read by aratc.Routes ("Bukonių sen.: Biržuliai, ..."). Next year's file of an
eldership continues this year's route if it covers the same places (raseiniai.combine). A file
that can't be downloaded or read keeps its rows of yesterday's data, and the other files are
still updated (raseiniai.py does the same).

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.jonava --out ../site/jonavos-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot, tratc
from .dates import WEEKDAY_NAMES, parse_month, parse_weekdays, weekly_dates
from .locations import _WORD, Clause, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Settlement, fold

SITE = "https://www.jonavospaslaugos.lt"
PAGE_URL = f"{SITE}/straipsniai/atlieku-tvarkymo-grafikas-jonavos-rajono-seniuniju-gyventojams"
TOWN_PAGE_URL = f"{SITE}/straipsniai/atlieku-tvarkymo-grafikas-jonavos-miesto-gyventojams"
# Yesterday's data, for the files that can't be read today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/jonavos-r"
COMPANY = "UAB „Jonavos paslaugos“"
LABEL = "Jonavos r."
# The elderships of the files, as their titles name them: the town's file, and one for each
# eldership of the district. The former Rukla eldership is part of Jonavos sen. now, as the town
# is (Provider.aliases).
SECTIONS = (
    "Jonavos miesto",
    "Bukonių",
    "Kulvos",
    "Ruklos",
    "Šilų",
    "Šveicarijos",
    "Upninkų",
    "Užusalių",
    "Žeimių",
)
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"household": ("household", "packaging", "glass")}


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Villages of another eldership: "Šilų s. Vainiai", "Šilų s. - Liepa, Konciapolis".
    (re.compile(rf"\b({_WORD})\s+s\.\s*-?\s*"), r"\1 sen.: "),
    # "Žeimių miestelis", "Ruklos miestelis".
    (re.compile(r"\bmiestelis\b", re.I), "mstl."),
    # A garden community ("sodininkų bendrija „Pušaitė“"): the register has no place of its
    # name, so it is reported, not read as a street of a village.
    (re.compile(r"\bsod(?:ų|ininkų)\s+be(?:n)?drij\w*", re.I), "SB"),
)


class Routes(aratc.Routes):
    """Reads the places of the routes, as aratc.Routes reads those of Alytus county: the
    villages of the file's eldership in the nominative, then those of others after their
    eldership ("Bukonių sen.: Biržuliai, Bukonys, ... Šilų s. Vainiai"), or the whole town
    ("Jonavos miesto sen.: Jonavos miestas, ...").

    No town gets "no pickup" for a street no route names (build_locations): the town's file is
    for the whole town, and no file lists streets."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()
        # The kinds and texts of the rows read since prepare; None before.
        self.read: set[tuple[str, str]] | None = None

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return text

    def prepare(self, areas: list[Area]) -> None:
        super().prepare(areas)
        self.read = set()

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        """aratc.Routes' clauses; the places it doesn't know are reported once per waste type,
        not again for the route's mixed waste of another frequency (the same text)."""
        found = super().clauses(area)
        if self.read is not None:
            if (area.kind, area.name) in self.read:
                self.unknown = []
            self.read.add((area.kind, area.name))
        return found


PROVIDER = Provider(
    id="jonava",
    name=COMPANY,
    url=PAGE_URL,
    # Every eldership of the municipality (register names).
    elderships=frozenset(
        {
            "Bukonių",
            "Jonavos",
            "Kulvos",
            "Upninkų",
            "Užusalių",
            "Šilų",
            "Šveicarijos",
            "Žeimių",
        }
    ),
    aliases=(
        ("Ruklos sen.:", "Jonavos sen.:"),
        ("Jonavos miesto sen.:", "Jonavos sen.:"),
        # Other names of the only places of these names: Liepos k. (Šilų sen.), Laukagaliai and
        # Bazilioniai (Jonavos sen., which the files put in Šilų sen.).
        ("Šilų s. - Liepa,", "Šilų s. - Liepos,"),
        ("Laukogaliai", "Laukagaliai"),
        ("Bazilionys", "Bazilioniai"),
    ),
    kinds=("household", "packaging", "glass"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.JONAVA_MUNICIPALITY,
    snapshot.JONAVA_REGISTRY_FILE,
    snapshot.JONAVA_ADDRESSES_FILE,
    # 2026: 9 routes, each with mixed waste twice and once a month (the town's also every
    # week), packaging and glass, which gave a mixed waste schedule to 189 of the 266
    # settlements (16,659 of the 16,847 addresses).
    min_areas={"household": 15, "packaging": 7, "glass": 7},
    min_household_places=150,
    # About 16,800 addresses in 2026, 3,600 of them in the town.
    min_address_points=11_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- the pages ---------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of a page; `group` is its eldership as its link and title name it ("Bukonių",
    "Ruklos", "Jonavos miesto"), so each eldership's file runs out on its own."""

    year: int | None = None


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href, self.text = dict(attrs).get("href") or "", []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            self.links.append((self.href, clean_text("".join(self.text))))
            self.href = None

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)


def _section(name: str) -> str | None:
    """SECTIONS' name of an eldership as a link or a title writes it ("Rūklos", "Bukonių")."""
    return next((s for s in SECTIONS if fold(s) == fold(name)), None)


def find_files(html: str, page_url: str) -> list[ScheduleFile]:
    """The PDFs of a page by the texts of their links: "Bukonių sen. 2026 m." on the elderships'
    page; on the town's, the one of individual houses ("... iš individualių namų valdų 2026
    m.")."""
    collector = _Links()
    collector.feed(html)
    files: list[ScheduleFile] = []
    for href, text in collector.links:
        url = urljoin(page_url, href)
        if not urlsplit(url).path.lower().endswith(".pdf"):
            continue
        year = re.search(r"\b(20\d{2})\s*m\b", text)
        if page_url == TOWN_PAGE_URL:
            section = "Jonavos miesto" if "individualiu nam" in fold(text) else None
        else:
            match = re.fullmatch(r"(\w+)\s+sen\.\s+20\d{2}\s*m\.?", text)
            section = _section(match[1]) if match else None
        if section is None or year is None or any(f.url == url for f in files):
            continue
        name = PurePosixPath(unquote(urlsplit(url).path)).name
        if (in_name := tratc.file_year(name)) and in_name != int(year[1]):
            raise ValueError(f"{name}: a file of {in_name}, its link says {year[1]}")
        files.append(
            ScheduleFile(
                kind="household", url=url, file_name=name, group=section, year=int(year[1])
            )
        )
    return files


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Per eldership, the files of this year and later; if there are none, the newest one. Of
    two for one year, the one linked last. Every eldership must have its file."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    groups: dict[str, list[ScheduleFile]] = defaultdict(list)
    for file in files:
        groups[file.group].append(file)
    for group, mine in groups.items():
        running = [f for f in mine if f.year >= today.year] or [
            f for f in mine if f.year == max(g.year for g in mine)
        ]
        if today.year not in {f.year for f in running}:
            warnings.append(f"{group} sen.: no schedule for {today.year} on the page")
        for year in sorted({f.year for f in running}):
            *older, newest = [f for f in running if f.year == year]
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer schedule for {year}"
                for f in older
            ]
            selected.append(newest)
    if missing := [s for s in SECTIONS if s not in groups]:
        raise build.ValidationError(f"no schedule found on the pages for {', '.join(missing)}")
    return selected, warnings


def download(
    today: date, keep_days: int, tolerant: bool = False
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files in force of both pages. `tolerant`: a file that can't be downloaded is passed
    on empty, and keeps its rows of yesterday's data (parse_or_keep)."""
    files: list[ScheduleFile] = []
    for page in (PAGE_URL, TOWN_PAGE_URL):
        files += find_files(http.get(page, timeout=60).decode("utf-8", errors="replace"), page)
    selected, warnings = select_files(files, today)
    sources: list[tuple[SourceFile, bytes]] = []
    for file in selected:
        try:
            sources.append((file, http.get(file.url, timeout=60)))
        except OSError as error:
            if not tolerant:
                raise
            warnings.append(f"{file.file_name}: couldn't be downloaded ({error})")
            sources.append((file, b""))
    return sources, warnings


# --- the tables ------------------------------------------------------------------

# "... iš individualių namų valdų Bukonių seniūnijoje 2026 metų sausio - gruodžio mėn.", "...
# buvusios Ruklos seniūnijos teritorijoje 2026 metų ...", "... Jonavos miesto seniūnijoje ...".
_TITLE = re.compile(
    r"individualių\s+namų\s+valdų\s+(?:buvusios\s+)?(?P<name>\w+(?:\s+miesto)?)\s+seniūnij\w*"
    r"(?:\s+teritorijoje)?\s+(?P<year>20\d{2})\s+metų",
    re.I,
)
# The days of a month's cell: "2; 16; 30", "27", "".
_DAYS = re.compile(r"\d{1,2}(?:\s*;\s*\d{1,2})*")
# "Kiekvieną KETVIRTADIENĮ (DĖMESIO: vietoje sausio 1 d. konteineriai bus aptarnaujami sausio
# 3 d.)": every week, but a day moved.
_WEEKLY = re.compile(r"Kiekvien\w+\s+(?P<weekday>\w+)", re.I)
_MOVED = re.compile(
    r"\(\s*DĖMESIO:\s*vietoje\s+(?P<month>\w+)\s+(?P<day>\d{1,2})\s*d\.\s*konteineriai\s+bus\s+"
    r"aptarnaujami\s+(?P<to_month>\w+)\s+(?P<to_day>\d{1,2})\s*d\.\s*\)",
    re.I,
)
_FREQUENCY = re.compile(r"\(\s*pagal\s+sutartį\s+(?P<times>\d)\s*k\s*/\s*(?P<unit>mėn|sav)\.?\s*\)")
_UNITS = {"mėn": "mėnesį", "sav": "savaitę"}


def frequency(label: str) -> str | None:
    """The group of a row of mixed waste, by its contract's frequency: "(pagal sutartį 2
    k/mėn.)" is "2 kartus per mėnesį (pagal sutartį)"."""
    match = _FREQUENCY.search(label)
    if not match:
        return None
    times = "Kartą" if match["times"] == "1" else f"{match['times']} kartus"
    return f"{times} per {_UNITS[match['unit']]} (pagal sutartį)"


def _row_kind(label: str) -> tuple[Kind | None, str | None]:
    """The waste type of a row by its label, and the group of mixed waste. Bulky and hazardous
    waste: None. Anything else raises ValueError."""
    folded = fold(label)
    if "gabarit" in folded or "pavojing" in folded:
        return None, None
    if "stikl" in folded:
        return "glass", None
    if "pakuot" in folded:
        return "packaging", None
    if "komunalin" in folded:
        group = frequency(label)
        if group is None:
            raise ValueError(f"mixed waste of no frequency: {label!r}")
        return "household", group
    raise ValueError(f"a row of no waste type: {label!r}")


def _weekly(text: str, year: int, where: str) -> set[date]:
    """ "Kiekvieną KETVIRTADIENĮ (DĖMESIO: vietoje sausio 1 d. ... sausio 3 d.)": every such
    weekday of the year, but the day moved."""
    text = clean_text(text)
    weekly = _WEEKLY.match(text)
    weekdays = parse_weekdays(weekly["weekday"]) if weekly else []
    if not weekly or len(weekdays) != 1:
        raise ValueError(f"{where}: not a weekly rule: {text!r}")
    dates = weekly_dates(weekdays, date(year, 1, 1), date(year, 12, 31))
    rest = text[weekly.end() :]
    for moved in _MOVED.finditer(rest):
        months = parse_month(moved["month"]), parse_month(moved["to_month"])
        if None in months:
            raise ValueError(f"{where}: not a month: {moved[0]!r}")
        before = date(year, months[0], int(moved["day"]))
        if before not in dates:
            raise ValueError(f"{where}: {before} isn't a pickup day to move")
        dates = (dates - {before}) | {date(year, months[1], int(moved["to_day"]))}
    if _MOVED.sub("", rest).strip():
        raise ValueError(f"{where}: not a weekly rule: {text!r}")
    return dates


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The schedules of a file's route: mixed waste of each frequency, packaging and glass,
    named after the eldership and the places ("Bukonių sen.: Biržuliai, ..."). Strict: a title
    of another eldership or year than the link's, months out of order, a cell of a month that
    isn't days, a day the month doesn't have, a row of no waste type or a file without a table
    raise ValueError."""
    if not content:
        raise ValueError(f"{source.file_name}: not downloaded")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = clean_text(" ".join(page.extract_text() or "" for page in pdf.pages))
        tables = [table for page in pdf.pages for table in page.extract_tables()]
    title = _TITLE.search(text)
    if not title:
        raise ValueError(f"{source.file_name}: no title with the eldership and year")
    section, year = _section(title["name"]), int(title["year"])
    if section != source.group or year != getattr(source, "year", year):
        raise ValueError(
            f"{source.file_name}: the title says {title['name']} {year}, "
            f"the link {source.group} {getattr(source, 'year', '')}"
        )
    where = source.file_name
    grids = [t for t in tables if any(_months(row) for row in t)]
    if len(grids) != 1:
        raise ValueError(f"{where}: {len(grids)} tables of months")
    rows = [[clean_text(c) if c else "" for c in row] for row in grids[0]]
    header = next(i for i, row in enumerate(rows) if _months(row))
    places = clean_text(" ".join(c for row in rows[:header] for c in row if c))
    if not places:
        raise ValueError(f"{where}: no places above the months")
    name = f"{section} sen.: {places}"
    areas: list[Area] = []
    for row in rows[header + 1 :]:
        if not any(row):
            continue
        if len(row) != 13:
            raise ValueError(f"{where}: a row of {len(row)} columns")
        kind, group = _row_kind(row[12])
        if kind is None:
            continue
        weekday = None
        if row[0] and not any(row[1:12]) and not _DAYS.fullmatch(row[0]):
            dates = _weekly(row[0], year, where)
            # The rule's weekday, though a day is moved to another.
            weekday = Counter(d.weekday() for d in dates).most_common(1)[0][0]
        else:
            dates = set()
            for month, cell in enumerate(row[:12], start=1):
                if cell and not _DAYS.fullmatch(cell):
                    raise ValueError(f"{where}: not days: {cell!r}")
                for day in re.findall(r"\d+", cell):
                    try:
                        dates.add(date(year, month, int(day)))
                    except ValueError as error:
                        raise ValueError(f"{where}: day {day} of {year}-{month:02}") from error
        if not dates:
            raise ValueError(f"{where}: no dates of {row[12]!r}")
        area = Area(kind, name, district=LABEL, group=group, dates=dates, provider=PROVIDER.id)
        weekdays = {d.weekday() for d in dates}
        if weekday is None and len(weekdays) == 1:
            weekday = weekdays.pop()
        if weekday is not None:
            area.weekday = WEEKDAY_NAMES[weekday]
        if any(a.id == area.id for a in areas):
            raise ValueError(f"{where}: two rows of {kind} {group or ''}")
        areas.append(area)
    if not any(a.kind == "household" for a in areas):
        raise ValueError(f"{where}: no mixed waste")
    return ParseResult(areas=areas)


def _months(row: list[str | None]) -> bool:
    """The row of months: "Sausis ... Gruodis | Renkamos atliekos". Raises ValueError for
    months out of order."""
    cells = [fold(c or "") for c in row]
    found = [aratc.MONTHS[c] for c in cells if c in aratc.MONTHS]
    if len(found) < 6:
        return False
    if found != list(range(1, 13)) or cells[:12] != [c for c in cells if c in aratc.MONTHS]:
        raise ValueError(f"months out of order: {row}")
    if cells[12:] != ["renkamos atliekos"]:
        raise ValueError(f"{row[12:]} after the months")
    return True


def parse_or_keep(
    source: SourceFile, content: bytes, published: Callable[[], dict] | None = None
) -> ParseResult:
    """parse_file, or for a file that can't be read, its eldership's rows of yesterday's data
    (`published`; None: raise instead)."""
    try:
        return parse_file(source, content)
    except Exception as error:  # any failure of one file must not stop the others
        if published is None:
            raise
        prefix = f"{source.group} sen.:"
        kept = build.published_rows(published(), PROVIDER, lambda r: r["name"].startswith(prefix))
        if not kept:
            raise
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} rows of {source.group} sen. are kept"
            ],
        )


# --- the source ------------------------------------------------------------------


def source(published: Callable[[], dict] | None = None) -> build.Source:
    """`published`: yesterday's data, for the files that can't be read (None: fail instead).
    Next year's file of an eldership continues this year's route as raseiniai.combine joins
    Raseinių r.'s, an eldership at a time."""
    return build.Source(
        PROVIDER,
        partial(download, tolerant=published is not None),
        partial(parse_or_keep, published=published),
        MUNICIPALITY.min_areas,
        MUNICIPALITY.min_household_places,
        MUNICIPALITY.file_kinds,
        partial(raseiniai.combine, municipality=MUNICIPALITY),
    )


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

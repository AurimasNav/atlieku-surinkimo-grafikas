"""Utenos rajonas: the schedules of UAB „Utenos komunalininkas“ (utenoskom.lt), which empties
the containers of the individual houses of the whole municipality: mixed waste, packaging and
glass, and the town's green waste.

Its page links two PDFs, made in Excel, each under a heading of its own:

    Atliekų surinkimo apvažiavimo būdu Utenos mieste grafikai 2026 m.              the town
    Atliekų surinkimo apvažiavimo būdu Utenos rajono seniūnijose grafikai 2026 m.  the elderships

The files are found by these texts and the year in them, which the files' titles ("BUITYJE
SUSIDARIUSIŲ ATLIEKŲ SURINKIMO APVAŽIAVIMO BŪDU UTENOS MIESTE GRAFIKAS 2026 M.") must agree with.
A new year's files are expected in December (the 2026 ones were uploaded on 23 December 2025).

Each file is one table, read with pdfplumber's table finder: a block per route, its places in the
first column, and a row of days per waste type under the months:

    Gatvės pavadinimas            | Atliekų rūšys                 | Sausis | ... | Gruodis
    Algirdo g., Ąžuolijos g., ... | Mišrios komunalinės           | 12; 26 | ... | 14; 28
                                  | Biologiškai skaidžios         | 13     | ... | 15
                                  | Plastikas, Metalas, Popierius | 5      | ... | 7
                                  | Stiklas                       | 19     | ... |
                                  | Pavojingos, didelių gabaritų  | 13     | ... |

The town's file has three routes of the streets of its individual houses; the elderships' file
("Seniūnijos") a block per eldership ("Leliūnų sen. tel. +370 389 60816") with packaging and glass,
the whole eldership. Bulky and hazardous waste ("Pavojingos, didelių gabaritų"), collected by
registration, isn't read. "Biologiškai skaidžios" (brown containers, every week from May to
October, once a month in winter) is green waste, as for Raseinių r.

The elderships' mixed waste has no dates: it is written under their table in words, a day of
every month:

    Mišrių komunalinių atliekų išvežimas Utenos rajono seniūnijose 2026 m.
    Užpalių sen. - kiekvieno mėnesio pirmą dieną.
    Vyžuonų sen., Sudeikių sen. - kiekvieno mėnesio ketvirtą dieną.
    ...
    Tauragnų sen., Daugailių sen. ir Vaikutėnų k. (Utenos sen.) - kiekvieno mėnesio dešimtą dieną.
    Saldutiškio sen., Kuktiškių sen. ir Utenos sen. (visi kaimai, išskyrus Vaikutėnų k.) - ...
    Pastaba: atliekų išvežimo dienai sutapus su šventine diena ar sekmadieniu, atliekos bus
    vežamos artimiausią darbo dieną.

The rules become the dates of the file's year (parse_rule and Rule, as svara.parse_rule reads
Kauno švara's), and a day that is a Sunday or a public holiday moves to the next day that is
neither, as the note says: the company collects on Saturdays too, its page says ("Atliekos
vežamos ir šeštadieniais (išskyrus sekmadienius ir šventines dienas)"), and its town's dates move
to the day after a holiday. Strict: a rule or a note in other words, places of no known kind, and
an eldership without mixed waste or with two rules raise. The page has the rules too, in other
words ("Tauragnų sen. – Daugailių sen., Utenos sen. (Vaikutėnai) – kiekvieno mėnesio dešimtą
dieną."); the elderships each day has there are checked against the file's, and a difference is
a warning.

The places are read by Routes (aratc.Routes): a town street no route names is left to the app,
since the apartment buildings' shared containers have no file and nothing says a street has none.
Next year's file continues this year's routes if they cover the same places (raseiniai.combine).
A file that can't be downloaded or read keeps its rows of yesterday's data, and the other file is
still read (as raseiniai.py does).

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.utena --out ../site/utenos-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot, tratc
from .dates import WEEKDAY_NAMES, month_end
from .locations import _STREET_TYPES, Index, _street_type, street_key
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Settlement, fold

PAGE_URL = "https://www.utenoskom.lt/paslaugos/atlieku-tvarkymas"
# Yesterday's data, for the files that can't be read today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/utenos-r"
COMPANY = "UAB „Utenos komunalininkas“"
LABEL = "Utenos r."
# The town's eldership in the register; its routes are named "Utenos m.: Algirdo g., ...".
TOWN = "Utenos miesto"
TOWN_PREFIX = "Utenos m.:"
# The other elderships of the municipality (register names), each a block of the elderships'
# file.
ELDERSHIPS = frozenset(
    {
        "Daugailių",
        "Kuktiškių",
        "Leliūnų",
        "Saldutiškio",
        "Sudeikių",
        "Tauragnų",
        "Utenos",
        "Užpalių",
        "Vyžuonų",
    }
)
# The two files, by the words of their headings on the page and of their titles (folded).
GROUPS = {"utenos mieste": "town", "utenos rajono seniunijose": "district"}
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "packaging", "glass", "green")
}


# --- the rules -------------------------------------------------------------------

# "pirmą" (the first), ..., "tryliktą" (the 13th), "dvidešimt pirmą" (the 21st): ordinals in the
# accusative, as "kiekvieno mėnesio ... dieną" has them.
_ORDINALS = {
    "pirmą": 1,
    "antrą": 2,
    "trečią": 3,
    "ketvirtą": 4,
    "penktą": 5,
    "šeštą": 6,
    "septintą": 7,
    "aštuntą": 8,
    "devintą": 9,
    "dešimtą": 10,
    "vienuoliktą": 11,
    "dvyliktą": 12,
    "tryliktą": 13,
    "keturioliktą": 14,
    "penkioliktą": 15,
    "šešioliktą": 16,
    "septynioliktą": 17,
    "aštuonioliktą": 18,
    "devynioliktą": 19,
    "dvidešimtą": 20,
    "trisdešimtą": 30,
}
_TENS = {"dvidešimt": 20, "trisdešimt": 30}
_RULE = re.compile(r"kiekvieno\s+mėnesio\s+(?P<day>\w+(?:\s+\w+)?)\s+dieną")
# Lithuania's public holidays on fixed days (Darbo kodeksas, art. 123), (month, day); Easter
# Sunday and Monday move. Mother's and Father's Days are Sundays.
_HOLIDAYS = (
    (1, 1),
    (2, 16),
    (3, 11),
    (5, 1),
    (6, 24),
    (7, 6),
    (8, 15),
    (11, 1),
    (11, 2),
    (12, 24),
    (12, 25),
    (12, 26),
)


def easter(year: int) -> date:
    """Easter Sunday of the Gregorian calendar (the anonymous algorithm, as Meeus gives it)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday) // 451
    month, day = divmod(h + weekday - 7 * m + 114, 31)
    return date(year, month, day + 1)


def holidays(year: int) -> set[date]:
    """Lithuania's public holidays of a year."""
    sunday = easter(year)
    return {date(year, m, d) for m, d in _HOLIDAYS} | {sunday, sunday + timedelta(days=1)}


@dataclass(frozen=True)
class Rule:
    """Mixed waste on one day of every month, `day`. A day that is a Sunday or a public holiday
    moves to the next day that is neither (Saturdays are collection days)."""

    day: int

    def dates(self, year: int) -> set[date]:
        """The pickups of a year. A day not every month has raises ValueError."""
        result: set[date] = set()
        for month in range(1, 13):
            if self.day > month_end(year, month).day:
                raise ValueError(f"day {self.day} of every month: {year}-{month:02} hasn't one")
            day = date(year, month, self.day)
            while day.weekday() == 6 or day in holidays(day.year):
                day += timedelta(days=1)
            result.add(day)
        return result


def parse_rule(text: str) -> Rule | None:
    """Understands "kiekvieno mėnesio pirmą dieną" (the first day of every month), ...,
    "tryliktą" (the 13th), "dvidešimt pirmą" (the 21st). Returns None for anything else."""
    found = _RULE.fullmatch(clean_text(text).casefold().rstrip(". "))
    if not found:
        return None
    words = found["day"].split()
    if len(words) == 1:
        day = _ORDINALS.get(words[0])
    elif words[0] in _TENS and _ORDINALS.get(words[1], 10) < 10:
        day = _TENS[words[0]] + _ORDINALS[words[1]]
    else:
        day = None
    return Rule(day) if day and day <= 31 else None


# --- the rules' places -------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    """An eldership a rule names: all of it (`village` None, nothing `but`), one of its villages
    ("Vaikutėnų k. (Utenos sen.)") or all its villages but some ("Utenos sen. (visi kaimai,
    išskyrus Vaikutėnų k.)")."""

    eldership: str
    village: str | None = None
    but: tuple[str, ...] = ()

    @property
    def whole(self) -> bool:
        return self.village is None and not self.but


# "Užpalių sen.", "Utenos sen. (visi kaimai, išskyrus Vaikutėnų k.)", "Vaikutėnų k. (Utenos sen.)".
_WHOLE = re.compile(r"(?P<name>\w+)\s+sen\.")
_ALL_BUT = re.compile(
    r"(?P<name>\w+)\s+sen\.\s*\(\s*visi\s+kaimai\s*(?:,\s*išskyrus\s+(?P<but>[^()]+?))?\s*\)"
)
_VILLAGE_OF = re.compile(r"(?P<village>[^()]+?\s(?:k|vs)\.)\s*\(\s*(?P<name>\w+)\s+sen\.\s*\)")
_VILLAGE = re.compile(r"(?P<name>[^()]+?)\s(?:k|vs)\.")


def _eldership(name: str) -> str | None:
    """The register's eldership a place names ("Leliūnų", "UTENOS")."""
    return next((e for e in ELDERSHIPS if fold(e) == fold(name)), None)


def _items(text: str) -> list[str]:
    """A list split at its commas and "ir" (and), not those in brackets."""
    items: list[str] = []
    depth, start, i = 0, 0, 0
    while i < len(text):
        depth += (text[i] == "(") - (text[i] == ")")
        if depth == 0 and (gap := re.match(r"\s*,\s*|\s+ir\s+", text[i:])):
            items.append(text[start:i])
            i += gap.end()
            start = i
            continue
        i += 1
    items.append(text[start:])
    return [clean_text(item) for item in items]


def rule_places(text: str) -> list[Part]:
    """The elderships and villages a rule names. Places of no known kind or elderships the
    register doesn't have raise ValueError."""
    parts: list[Part] = []
    for item in _items(clean_text(text)):
        if found := _WHOLE.fullmatch(item):
            part = Part(found["name"])
        elif found := _ALL_BUT.fullmatch(item):
            but = _items(found["but"]) if found["but"] else []
            if not all(_VILLAGE.fullmatch(b) for b in but):
                raise ValueError(
                    f"villages left out of {found['name']} sen. of no known kind: {item!r}"
                )
            part = Part(found["name"], but=tuple(but))
        elif found := _VILLAGE_OF.fullmatch(item):
            part = Part(found["name"], village=found["village"])
        else:
            raise ValueError(f"places of no known kind: {item!r} (in {text!r})")
        eldership = _eldership(part.eldership)
        if eldership is None:
            raise ValueError(f"an eldership the register doesn't have: {item!r}")
        parts.append(Part(eldership, part.village, part.but))
    return parts


def _reader_text(parts: list[Part]) -> str:
    """The places as aratc.Routes reads them: "Visoje Užpalių sen.", "Utenos sen.: Vaikutėnų k.",
    "Utenos sen.: tik Utenos sen. esantys kaimai (be Vaikutėnų)"."""
    texts: list[str] = []
    for part in parts:
        if part.whole:
            texts.append(f"Visoje {part.eldership} sen.")
        elif part.village:
            texts.append(f"{part.eldership} sen.: {part.village}")
        else:
            but = ", ".join(_VILLAGE.fullmatch(b)["name"] for b in part.but)
            texts.append(
                f"{part.eldership} sen.: tik {part.eldership} sen. esantys kaimai (be {but})"
            )
    return " ".join(texts)


# --- the places ------------------------------------------------------------------

# The publisher's spellings of the town's streets, as aratc.Routes reads them.
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Lanko g..".
    (re.compile(r"\b(g|a|skg)\.\.(?=\s|,|$)"), r"\1."),
)


class Routes(raseiniai.Routes):
    """Reads the places of the routes as raseiniai.Routes reads Raseinių r.'s (aratc.Routes):

        Utenos m.: Algirdo g., Ąžuolijos g., ...                          streets of the town
        Leliūnų sen.                                                       a whole eldership
        Vyžuonų sen., Sudeikių sen.                                        whole elderships
        Tauragnų sen., Daugailių sen. ir Vaikutėnų k. (Utenos sen.)        and a village
        Saldutiškio sen., ... ir Utenos sen. (visi kaimai, išskyrus Vaikutėnų k.)

    A whole eldership is a fallback for the rows that name a village of it ("Vaikutėnų k."); the
    villages of one but some are those of the eldership but those.

    No street gets "no pickup" (build_locations): the town's file lists the streets of its
    individual houses, the shared containers of the apartment buildings have no file, and
    nothing says a street has none. A street no route names is left to the app, which offers
    the town's routes."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        # aratc.Routes for this municipality (raseiniai.Routes' own sets Raseinių r.'s).
        self.municipalities = (MUNICIPALITY,)
        aratc.Routes.__init__(self, index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        if text.startswith(TOWN_PREFIX):
            text = f"{TOWN} sen.:{text.removeprefix(TOWN_PREFIX)}"
            for pattern, replacement in _FIXES:
                text = pattern.sub(replacement, text)
            return text
        try:
            return _reader_text(rule_places(text))
        except ValueError:
            return text  # reported as places the reader doesn't know

    def streets(
        self, settlement: Settlement, part: str, name: str, kind: str | None, loose: bool = True
    ) -> set[str]:
        """aratc.Routes' streets, but a street written with its type is a street of that type:
        "Draugystės g." of the second route isn't Draugystės a., the square the first route
        names (the register has no Draugystės g., only Draugystės 1-oji g. to 18-oji g.)."""
        found = super().streets(settlement, part, name, kind, loose)
        wanted = _STREET_TYPES.get(kind or "")
        if not wanted:
            return found
        return {
            street_key(t)
            for t in settlement.streets
            if street_key(t) in found and _street_type(t) == wanted
        }


PROVIDER = Provider(
    id="utena",
    name=COMPANY,
    url=PAGE_URL,
    elderships=ELDERSHIPS | {TOWN},
    kinds=("household", "packaging", "glass", "green"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.UTENA_MUNICIPALITY,
    snapshot.UTENA_REGISTRY_FILE,
    snapshot.UTENA_ADDRESSES_FILE,
    # 2026: the town's 3 routes with mixed waste, green waste, packaging and glass, the 9
    # elderships' packaging and glass, and 5 rules of their mixed waste, which gave a mixed waste
    # schedule to every one of the 585 settlements.
    min_areas={"household": 6, "packaging": 9, "glass": 9, "green": 2},
    min_household_places=450,
    # About 17,800 addresses in 2026, 4,700 of them in the town.
    min_address_points=12_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page; `group` is "town" or "district", so each runs out on its own.
    `rules`: the district's mixed waste rules the page writes, to check the file's against."""

    year: int | None = None
    rules: tuple[str, ...] = field(default_factory=tuple)


class _Page(HTMLParser):
    """The page's links with the heading above them (<h6>Atliekų surinkimo ... grafikai 2026
    m.</h6><a href="...pdf">), and the items of the list under the heading of the elderships'
    mixed waste (<h3>Mišrių komunalinių atliekų išvežimo grafikas Utenos rajono seniūnijose</h3>
    ... <li>)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []  # (heading, href)
        self.rules: list[str] = []
        self.heading = ""  # of the last <h6>, "" after an <h3>
        self.section = ""  # of the last <h3>
        self.tag: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h3", "h6", "li"):
            self.tag, self.text = tag, []
        elif tag == "a":
            self.links.append((self.heading, dict(attrs).get("href") or ""))

    def handle_endtag(self, tag: str) -> None:
        if tag != self.tag:
            return
        text = clean_text("".join(self.text))
        if tag == "h6":
            self.heading = text
        elif tag == "h3":
            self.section, self.heading = text, ""
        elif fold(self.section).startswith("misriu komunaliniu atlieku isvezimo grafikas"):
            self.rules.append(text)
        self.tag = None

    def handle_data(self, data: str) -> None:
        if self.tag:
            self.text.append(data)


def _year(text: str) -> int | None:
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})\s*m\b", text)}
    return years.pop() if len(years) == 1 else None


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The PDFs of the page by the headings above their links ("Atliekų surinkimo apvažiavimo
    būdu Utenos mieste grafikai 2026 m."), the elderships' with the page's mixed waste rules; and
    warnings about schedules of no area we read."""
    collector = _Page()
    collector.feed(html)
    files: list[ScheduleFile] = []
    warnings: list[str] = []
    for heading, href in collector.links:
        url = urljoin(page_url, href)
        name = PurePosixPath(unquote(urlsplit(url).path)).name
        words = fold(heading)
        if not name.lower().endswith(".pdf") or "grafik" not in words:
            continue
        group = next((g for key, g in GROUPS.items() if key in words), None)
        year = _year(heading)
        if group is None or year is None:
            warnings.append(f"{name}: not read, a schedule of no area or year we read: {heading!r}")
            continue
        # Webflow puts an id before the name ("694a59ac..._Grafikas ... 2026 m. Utenos mieste.pdf").
        if (in_name := tratc.file_year(name.split("_", 1)[-1])) and in_name != year:
            raise ValueError(f"{name}: a file of {in_name}, its heading says {year}")
        if any(f.url == url for f in files):
            continue
        rules = tuple(collector.rules) if group == "district" else ()
        files.append(ScheduleFile("household", url, name, group=group, year=year, rules=rules))
    return files, warnings


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Of the town's files and the elderships', those of this year and later; if there are none,
    the newest. Of two for one year, the one linked first. A page without a file of the town or
    of the elderships raises ValidationError."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    for group in GROUPS.values():
        mine = [f for f in files if f.group == group]
        if not mine:
            raise build.ValidationError(f"no schedule of the {group} on the page")
        running = [f for f in mine if f.year >= today.year] or [
            f for f in mine if f.year == max(g.year for g in mine)
        ]
        if today.year not in {f.year for f in running}:
            warnings.append(f"no schedule of the {group} for {today.year} on the page")
        for year in sorted({f.year for f in running}):
            first, *others = [f for f in running if f.year == year]
            warnings += [
                f"{f.file_name}: not read, {first.file_name} is the {group}'s schedule for {year}"
                for f in others
            ]
            selected.append(first)
    return selected, warnings


def download(
    today: date, keep_days: int, tolerant: bool = False
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files in force. `tolerant`: a file that can't be downloaded is passed on empty, and
    keeps its rows of yesterday's data (parse_or_keep)."""
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, warnings = find_files(html)
    selected, more = select_files(files, today)
    warnings += more
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


# --- the files -------------------------------------------------------------------

# "BUITYJE SUSIDARIUSIŲ ATLIEKŲ SURINKIMO APVAŽIAVIMO BŪDU UTENOS MIESTE GRAFIKAS 2026 M." (folded).
_TITLE = re.compile(
    r"buityje susidariusiu atlieku surinkimo apvaziavimo budu (?P<where>.+?) grafikas "
    r"(?P<year>20\d{2}) m"
)
# The first column's heading of each file (folded).
_FIRST_COLUMN = {"town": "gatves pavadinimas", "district": "seniunijos"}
# The days of a month's cell: "12; 26", "3; 16; 30", "" (none).
_DAYS = re.compile(r"\d{1,2}(?:\s*;\s*\d{1,2})*\s*;?")
# A row's waste type by its words (folded); None: bulky and hazardous waste, collected by
# registration, not read.
_KINDS: dict[str, Kind | None] = {
    "misrios komunalines": "household",
    "biologiskai skaidzios": "green",
    "plastikas metalas popierius": "packaging",
    "stiklas": "glass",
    "pavojingos dideliu gabaritu": None,
}
# The kinds each file's table has: the elderships' mixed waste is in words under it.
_TABLE_KINDS: dict[str, frozenset[Kind]] = {
    "town": frozenset({"household", "green", "packaging", "glass"}),
    "district": frozenset({"packaging", "glass"}),
}
# An eldership's block: "Leliūnų sen. tel. +370 389 60816".
_BLOCK = re.compile(r"(?P<name>\w+)\s+sen\.(?:\s+tel\.\s*\+?[\d ]+)?")
# The heading of the elderships' mixed waste under their table, and the note under the rules.
# "Mišrių komunalinių atliekų išvežimas Utenos rajono seniūnijose 2026 m." (folded).
_MIXED = re.compile(
    r"misriu komunaliniu atlieku isvezimas utenos rajono seniunijose (?P<year>20\d{2}) m"
)
_NOTE = (
    "pastaba atlieku isvezimo dienai sutapus su sventine diena ar sekmadieniu atliekos bus "
    "vezamos artimiausia darbo diena"
)
# Routes of the town, at least: 3 in 2026.
MIN_ROUTES = 2


@dataclass
class _Block:
    label: str
    dates: dict[Kind, set[date]] = field(default_factory=dict)


def _table(table, group: str, year: int, where: str) -> list[_Block]:
    """The blocks of the file's table. Strict: a header of other columns, a cell that isn't
    days, a day the month doesn't have, a row of no waste type or of one the table shouldn't
    have, two rows of one kind in a block, and a row without dates raise ValueError."""
    rows = [[None if c is None else clean_text(c) for c in row] for row in table.extract()]
    header = [fold(c or "") for c in rows[0]]
    if header[:2] != [_FIRST_COLUMN[group], "atlieku rusys"] or [
        aratc.MONTHS.get(m) for m in header[2:]
    ] != list(range(1, 13)):
        raise ValueError(f"{where}: a header of {rows[0]}")
    blocks: list[_Block] = []
    for cells in rows[1:]:
        if len(cells) != 14:
            raise ValueError(f"{where}: a row of {len(cells)} cells: {cells[:3]}")
        if cells[0]:
            blocks.append(_Block(cells[0]))
        elif not blocks:
            raise ValueError(f"{where}: a row without places above it: {cells[:3]}")
        block = blocks[-1]
        label = fold(cells[1] or "")
        if label not in _KINDS:
            raise ValueError(f"{where}: a row of {cells[1]!r} ({block.label[:40]!r})")
        kind = _KINDS[label]
        if kind is None:
            continue  # bulky and hazardous waste, by registration
        if kind not in _TABLE_KINDS[group] or kind in block.dates:
            raise ValueError(f"{where}: a row of {kind} in {block.label[:40]!r}")
        dates: set[date] = set()
        for month, cell in enumerate(cells[2:], start=1):
            if cell and not _DAYS.fullmatch(cell):
                raise ValueError(f"{where}: not days: {cell!r}")
            last = month_end(year, month).day
            for day in (int(d) for d in re.findall(r"\d+", cell or "")):
                if not 1 <= day <= last:
                    raise ValueError(f"{where}: month {month} of {year} has no day {day}")
                dates.add(date(year, month, day))
        if not dates:
            raise ValueError(f"{where}: no dates of {kind} in {block.label[:40]!r}")
        block.dates[kind] = dates
    return blocks


@dataclass
class _Mixed:
    """A rule of the elderships' mixed waste: its places as the file writes them, and read."""

    places: str
    parts: list[Part]
    rule: Rule


def _rules(text: str, year: int, where: str) -> list[_Mixed]:
    """The elderships' mixed waste under their table: the places and the rule of each line,
    after the heading of the file's year, up to the note about holidays. Strict: no heading,
    another year, a line that isn't places and a rule we understand, a note in other words, an
    eldership without a rule for all its villages or with two, and villages left out of one
    that no other rule names raise ValueError."""
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    starts = [i for i, line in enumerate(lines) if _MIXED.fullmatch(fold(line))]
    if len(starts) != 1:
        raise ValueError(f"{where}: {len(starts)} headings of the elderships' mixed waste")
    (start,) = starts
    if int(_MIXED.fullmatch(fold(lines[start]))["year"]) != year:
        raise ValueError(f"{where}: the mixed waste rules of {lines[start]!r} in a file of {year}")
    found: list[str] = []
    note = None
    for line in lines[start + 1 :]:
        if note is not None:
            raise ValueError(f"{where}: {line[:60]!r} after the mixed waste rules")
        if fold(line).startswith("pastaba"):
            note = line
        elif found and not re.search(r"\s[-–]\s", line):
            found[-1] += f" {line}"  # a rule on two lines
        else:
            found.append(line)
    if note is None or fold(note) != _NOTE:
        raise ValueError(f"{where}: a note under the mixed waste rules of {note!r}")
    rules: list[_Mixed] = []
    for line in found:
        places, dash, words = line.rpartition(" - ") if " - " in line else line.rpartition(" – ")
        rule = parse_rule(words) if dash else None
        if rule is None:
            raise ValueError(f"{where}: an unrecognised mixed waste rule: {line!r}")
        try:
            parts = rule_places(places)
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from error
        rules.append(_Mixed(clean_text(places), parts, rule))
    parts = [p for r in rules for p in r.parts]
    rest = sorted(p.eldership for p in parts if not p.village)
    if rest != sorted(ELDERSHIPS):
        raise ValueError(f"{where}: mixed waste rules for all villages of {rest}")
    villages = {(p.eldership, fold(p.village)) for p in parts if p.village}
    if left := [b for p in parts for b in p.but if (p.eldership, fold(b)) not in villages]:
        raise ValueError(f"{where}: no mixed waste rule for {left}, left out of another")
    return rules


def _days(parts_by_day: list[tuple[int, list[Part]]]) -> dict[int, frozenset[str]]:
    days: dict[int, set[str]] = defaultdict(set)
    for day, parts in parts_by_day:
        days[day] |= {p.eldership for p in parts}
    return {day: frozenset(names) for day, names in days.items()}


def page_days(rules: tuple[str, ...]) -> dict[int, frozenset[str]]:
    """The elderships of each day of the page's rules ("Tauragnų sen. – Daugailių sen., Utenos sen.
    (Vaikutėnai) – kiekvieno mėnesio dešimtą dieną."), as far as they can be read."""
    found: list[tuple[int, list[Part]]] = []
    for text in rules:
        words = re.search(r"kiekvieno\s+mėnesio\s+\w+(?:\s+\w+)?\s+dieną", text, re.I)
        rule = parse_rule(words.group()) if words else None
        names = [_eldership(n) for n in re.findall(r"(\w+)\s+sen\.", text)]
        if rule is None or None in names:
            return {}
        found.append((rule.day, [Part(n) for n in names if n]))
    return _days(found)


def _check_page(source: SourceFile, rules: list[_Mixed]) -> list[str]:
    """The page's rules against the file's: the same elderships on each day, else a warning."""
    written = getattr(source, "rules", ())
    if not written:
        return [f"{source.file_name}: the page has no mixed waste rules to check the file's"]
    page = page_days(written)
    mine = _days([(r.rule.day, r.parts) for r in rules])
    if page == mine:
        return []
    return [
        f"{source.file_name}: the page's mixed waste rules aren't the file's: {'; '.join(written)}"
    ]


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of one file: a row per route and waste type, the town's named after its streets
    ("Utenos m.: Algirdo g., ..."), the elderships' after the eldership ("Leliūnų sen.") or, for
    mixed waste, the places of the rule ("Tauragnų sen., Daugailių sen. ir Vaikutėnų k. (Utenos
    sen.)"). Strict (see _table, _rules): also a title of the other file or another year than
    the link's, too few routes of the town, a route of the town without mixed waste, a block of
    an eldership the register doesn't have or two of one, and an eldership without mixed waste
    or with two rules raise ValueError."""
    if not content:
        raise ValueError(f"{source.file_name}: not downloaded")
    where = source.file_name
    group = source.group
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError(f"{where}: {len(pdf.pages)} pages")
        page = pdf.pages[0]
        tables = page.find_tables()
        if len(tables) != 1:
            raise ValueError(f"{where}: {len(tables)} tables")
        (table,) = tables
        above = page.crop((0, 0, page.width, table.bbox[1])).extract_text() or ""
        below = page.crop((0, table.bbox[3], page.width, page.height)).extract_text() or ""
        title = _TITLE.fullmatch(fold(above))
        if not title or GROUPS.get(title["where"]) != group:
            raise ValueError(f"{where}: the title {clean_text(above)!r} isn't of the {group}")
        year = int(title["year"])
        if year != getattr(source, "year", year):
            raise ValueError(f"{where}: the title says {year}, the link {source.year}")
        blocks = _table(table, group, year, where)
    areas: list[Area] = []
    warnings: list[str] = []

    def add(kind: Kind, name: str, dates: set[date]) -> None:
        area = Area(kind, name, LABEL, dates=dates, provider=PROVIDER.id)
        weekdays = {d.weekday() for d in dates}
        if len(weekdays) == 1:
            area.weekday = WEEKDAY_NAMES[weekdays.pop()]
        if any(a.id == area.id for a in areas):
            raise ValueError(f"{where}: two {kind} rows of {name[:60]!r}")
        areas.append(area)

    if group == "town":
        if len(blocks) < MIN_ROUTES:
            raise ValueError(f"{where}: only {len(blocks)} routes (expected {MIN_ROUTES})")
        for block in blocks:
            if "household" not in block.dates:
                raise ValueError(f"{where}: no mixed waste for {block.label[:60]!r}")
            for kind, dates in block.dates.items():
                add(kind, f"{TOWN_PREFIX} {block.label}", dates)
        return ParseResult(areas=areas, warnings=warnings)
    seen: list[str] = []
    for block in blocks:
        found = _BLOCK.fullmatch(block.label)
        eldership = _eldership(found["name"]) if found else None
        if eldership is None or eldership in seen:
            raise ValueError(f"{where}: a block of {block.label!r}")
        seen.append(eldership)
        for kind, dates in block.dates.items():
            add(kind, f"{eldership} sen.", dates)
    if missing := sorted(ELDERSHIPS - set(seen)):
        raise ValueError(f"{where}: no block of {', '.join(missing)}")
    rules = _rules(below, year, where)
    for mixed in rules:
        add("household", mixed.places, mixed.rule.dates(year))
    warnings += _check_page(source, rules)
    return ParseResult(areas=areas, warnings=warnings)


def parse_or_keep(
    source: SourceFile, content: bytes, published: Callable[[], dict] | None = None
) -> ParseResult:
    """parse_file, or for a file that can't be read, its rows of yesterday's data (`published`;
    None: raise instead): the town's ("Utenos m.: ...") or the elderships'."""
    try:
        return parse_file(source, content)
    except Exception as error:  # any failure of one file must not stop the other
        if published is None:
            raise
        town = source.group == "town"
        kept = build.published_rows(
            published(), PROVIDER, lambda r: r["name"].startswith(TOWN_PREFIX) == town
        )
        if not kept:
            raise
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} rows of the {source.group} are kept"
            ],
        )


# --- the source ------------------------------------------------------------------


def source(published: Callable[[], dict] | None = None) -> build.Source:
    """`published`: yesterday's data, for the files that can't be read (None: fail instead).
    Next year's file of the town or the elderships continues this year's routes as
    raseiniai.combine joins Raseinių r.'s, a file at a time."""
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

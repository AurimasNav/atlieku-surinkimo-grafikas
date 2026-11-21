"""Alytaus regionas: the schedules of the regional waste centre of Alytus county, UAB „Alytaus
regiono atliekų tvarkymo centras“, for the individual houses of six municipalities: Alytaus r.,
Prienų r., Lazdijų r., Varėnos r., Druskininkų sav. and Birštono sav. Alytus city isn't read:
its households mostly use shared containers. The centre publishes the schedules of every
company that empties the containers (UAB „Ecoservice“, UAB „Švara ID“, ...).

Its page has a section per municipality, a list of PDFs described in words ("individualių namų
maisto ir mišrių komunalinių atliekų surinkimo grafikas;"), some with a note of when they apply
("galioja iki 2026-11-30", "galioja nuo 2026-12-01"). The files of individual houses are found by
these texts, not by their URLs; those of shared containers, companies, public places and garden
communities aren't read, and a file that a newer one replaces ("galioja iki ...") is left out.
Druskininkai has a file of its own for the houses in garden communities, farmsteads and places
that are hard to reach: its rows are a group of their own, one more choice next to the village's
usual route.

A contract year runs from March to February ("2026 m. kovo mėn. - 2027 m. vasario mėn."), but
each file has its own months: the 2026 packaging files of Alytaus r. and Prienų r. run from
December 2026 to March 2028, those of Lazdijų r. from August, Druskininkai's from July. A table
has a column of places and one per month under year cells ("2026 m.", "2027 m."), with the days
("12;26", "5, 26", "-"); some have a column of elderships ("Seniūnija"), of week numbers ("Sav.d")
or of waste types (a row of packaging and one of glass dates per place):

    Vietovės pavadinimas                  | Atliekos tipas | Gruodis | Sausis | Vasaris | ...
    SIMNO SEN.: Simnas, Kaimynai. ...     | PAKUOTĖS       | 15      | 5, 26  | 16      | ...
                                          | STIKLAS        | -       | 23     | -       | ...

The tables are read from the positions of the words and the borders of the cells: a row ends at a
border across both the places and the dates, so a cell of dates can span several rows of places
(Prienų r.) and a place several rows of dates. Month titles written bottom to top (Varėnos r.)
are read too, and a table runs on to the next page. Strict: a cell of dates that isn't a list of
days, a day the month doesn't have, dates without a waste type and places without dates raise.

The places are written in many ways ("SIMNO SEN. Simnas, ...", "Dalyje Šilavoto sen.: ...",
"Druskininkų m.: Ąžuolo g., ...", "tik Jiezno sen. esantys kaimai (be Jiezno, ...)"); Routes links
them to the Address Register. A file of the next contract year continues the routes of this one
that cover the same places (combine).

Writes <out>/schedule.json and <out>/addresses.json, in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.aratc --out ../site/alytaus-ratc
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import pdfplumber

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import (
    _HOUSE,
    _SECTION_ITEM,
    _SETTLEMENT_TYPES,
    _STREET_TYPE,
    _UPPER,
    _WORD,
    Clause,
    Index,
    SectionRoutes,
    _near,
    _one_off,
    _section_parts,
    _Stop,
    _typo,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

PAGE_URL = "https://www.aratc.lt/atlieku-surinkimo-grafikai/"
NAME = "UAB „Alytaus regiono atliekų tvarkymo centras“"


@dataclass(frozen=True)
class Municipality:
    """A municipality of the page: the heading of its section, and its elderships."""

    label: str  # the rows' `district`: "Prienų r."
    heading: str  # in the heading of its section on the page, folded
    elderships: frozenset[str]  # register names; towns of no eldership get "<town> miesto"
    # Routes of each kind in its files, but those of a group of their own. The 2026 files had:
    # Alytaus r. 16 mixed waste, 3 food and 15 packaging and glass routes; Prienų r. 14, 2 and
    # 14; Lazdijų r. 17, 3 and 11; Varėnos r. 19, 2 and 12; Druskininkai 8, 4 and 6 (and one
    # route of its farmsteads); Birštonas one of each, for the whole municipality. Far fewer
    # means the format changed and the parser missed rows.
    min_areas: dict[Kind, int]


MUNICIPALITIES = (
    Municipality(
        "Alytaus r.",
        "alytaus rajonas",
        frozenset(
            {
                "Alovės",
                "Alytaus",
                "Butrimonių",
                "Daugų",
                "Krokialaukio",
                "Miroslavo",
                "Nemunaičio",
                "Pivašiūnų",
                "Punios",
                "Raitininkų",
                "Simno",
            }
        ),
        {"household": 12, "food": 2, "packaging": 12, "glass": 12},
    ),
    Municipality(
        "Prienų r.",
        "prienu rajonas",
        frozenset(
            {
                "Balbieriškio",
                "Išlaužo",
                "Jiezno",
                "Naujosios Ūtos",
                "Pakuonio",
                "Prienų",
                "Stakliškių",
                "Veiverių",
                "Šilavoto",
            }
        ),
        {"household": 10, "food": 1, "packaging": 10, "glass": 10},
    ),
    Municipality(
        "Lazdijų r.",
        "lazdiju rajonas",
        frozenset(
            {
                "Būdviečio",
                "Kapčiamiesčio",
                "Krosnos",
                "Kučiūnų",
                "Lazdijų",
                "Lazdijų miesto",
                "Noragėlių",
                "Seirijų",
                "Veisiejų",
                "Šeštokų",
                "Šventežerio",
            }
        ),
        {"household": 14, "food": 2, "packaging": 8, "glass": 8},
    ),
    Municipality(
        "Varėnos r.",
        "varenos rajonas",
        frozenset(
            {
                "Jakėnų",
                "Kaniavos",
                "Marcinkonių",
                "Matuizų",
                "Merkinės",
                "Valkininkų",
                "Varėnos",
                "Vydenių",
            }
        ),
        {"household": 14, "food": 1, "packaging": 9, "glass": 9},
    ),
    Municipality(
        "Druskininkų sav.",
        "druskininku savivaldybe",
        frozenset({"Druskininkų miesto", "Leipalingio", "Viečiūnų"}),
        {"household": 6, "food": 3, "packaging": 4, "glass": 4},
    ),
    Municipality(
        "Birštono sav.",
        "birstono savivaldybe",
        frozenset({"Birštono", "Birštono miesto"}),
        {"household": 1, "food": 1, "packaging": 1, "glass": 1},
    ),
)
BY_LABEL = {m.label: m for m in MUNICIPALITIES}
# The rows of Druskininkai's file for garden communities, farmsteads and places hard to reach.
REMOTE_GROUP = "Sodai, vienkiemiai ir sunkiai privažiuojamos valdos"
# The kinds of schedule a file of each kind can have.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "food"),
    "packaging": ("packaging", "glass"),
    "food": ("food",),
}
# Mixed waste is collected once a month, so most settlements have one route; the 2026 files gave
# a mixed waste schedule to 1,421 of the 1,558 settlements.
MIN_HOUSEHOLD_PLACES = 1_200
# The six municipalities had about 78,000 addresses in 2026.
MIN_ADDRESS_POINTS = 55_000
# The Kauno švara open-data file (schedule_pipeline.svara) also lists containers of these
# municipalities, as it names them. Their schedules are the centre's: svara.py mustn't read them.
KAUNO_SVARA_NAMES = ("Alytaus r. sav.", "Prienų r. sav.", "Druskininkų sav.", "Birštono sav.")


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page, with whom it serves and when it applies."""

    municipality: str = ""  # Municipality.label
    group: str | None = None  # REMOTE_GROUP
    valid_from: date | None = None  # "galioja nuo 2026-12-01"
    valid_until: date | None = None  # "galioja iki 2026-11-30"

    @property
    def part(self) -> tuple[str, str | None]:
        """Whose schedule it is, for build.current_rows: a file that ends is the newest of its
        municipality and group until the next one is read, whatever the others' files."""
        return self.municipality, self.group


# --- the page ----------------------------------------------------------------


class _Page(HTMLParser):
    """The page's list items with their texts and links, under the heading of their section."""

    def __init__(self) -> None:
        super().__init__()
        self.base: str | None = None
        self.items: list[tuple[str, str, list[str]]] = []
        self.heading = ""
        self.toggler: list[str] | None = None  # the text of a section's heading being read
        self.depth = 0  # of nested list items
        self.text: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "base" and attributes.get("href"):
            self.base = attributes["href"]
        elif tag == "a" and "accord-toggler" in (attributes.get("class") or "").split():
            self.toggler = []
        elif tag == "a" and self.depth and attributes.get("href"):
            self.links.append(attributes["href"] or "")
        elif tag == "li":
            self.depth += 1
            if self.depth == 1:
                self.text, self.links = [], []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.toggler is not None:
            self.heading = clean_text("".join(self.toggler))
            self.toggler = None
        elif tag == "li" and self.depth:
            self.depth -= 1
            if not self.depth:
                self.items.append((self.heading, clean_text("".join(self.text)), self.links))

    def handle_data(self, data: str) -> None:
        if self.toggler is not None:
            self.toggler.append(data)
        elif self.depth:
            self.text.append(data)


# Who a file is for, in the text of its item (folded): not individual houses.
OTHERS = (
    "bendro naudojimo",
    "daugiabuc",
    "imoni",
    "imones",
    "juridin",
    "viesu viet",
    "pagal sutart",
    "sodu bendrij",
    "garaz",
)
VALIDITY = re.compile(r"galioja\s+(nuo|iki)\s+(\d{4})-(\d{2})-(\d{2})")


def file_name(url: str) -> str:
    return PurePosixPath(unquote(urlsplit(url).path)).name


def _ascii(url: str) -> str:
    """The page links some files with letters as they are ("individualūs"), which an HTTP
    request can't carry: percent-encoded, keeping what already is ("%20")."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(parts.path, safe="/%:@!$&'()*+,;=")))


def _file_kind(folded: str) -> Kind | None:
    if any(word in folded for word in ("pakuoc", "stikl", "popier", "plastik")):
        return "packaging"
    if "misri" in folded:
        return "household"
    if "maist" in folded:
        return "food"
    return None


def find_files(html: str, page_url: str = PAGE_URL) -> list[ScheduleFile]:
    """The PDFs of individual houses the page links, by the texts of their items. The links
    are relative to the page's <base> (https://www.aratc.lt/), not to the page itself."""
    page = _Page()
    page.feed(html)
    base = urljoin(page_url, page.base) if page.base else page_url
    files: list[ScheduleFile] = []
    for heading, text, links in page.items:
        municipality = next((m for m in MUNICIPALITIES if m.heading in fold(heading)), None)
        folded = fold(text)
        kind = _file_kind(folded)
        houses = "individual" in folded or not any(word in folded for word in OTHERS)
        if municipality is None or kind is None or not houses:
            continue
        validity = {
            which: date(int(y), int(m), int(d))
            for which, y, m, d in VALIDITY.findall(text.replace("–", "-"))
        }
        remote = "vienkiem" in folded or "sunkiai privaz" in folded
        for link in links:
            url = _ascii(urljoin(base, link))
            if not urlsplit(url).path.lower().endswith(".pdf"):
                continue
            if any(f.url == url and f.municipality == municipality.label for f in files):
                continue
            files.append(
                ScheduleFile(
                    kind=kind,
                    url=url,
                    file_name=file_name(url),
                    municipality=municipality.label,
                    group=REMOTE_GROUP if remote else None,
                    valid_from=validity.get("nuo"),
                    valid_until=validity.get("iki"),
                )
            )
    return files


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Leaves out the files that have ended ("galioja iki" a date before today) and those a
    newer one replaces: a file valid until a date, next to another of the same municipality,
    kind and group that isn't. Each municipality must have its mixed waste and packaging files."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    for file in files:
        same = [
            f
            for f in files
            if f is not file
            and (f.municipality, f.kind, f.group) == (file.municipality, file.kind, file.group)
        ]
        if file.valid_until and file.valid_until < today:
            warnings.append(f"{file.file_name}: not read, it ended on {file.valid_until}")
        elif file.valid_until and any(
            f.valid_until is None or f.valid_until > file.valid_until for f in same
        ):
            newer = next(
                f for f in same if f.valid_until is None or f.valid_until > file.valid_until
            )
            warnings.append(
                f"{file.file_name}: not read, {newer.file_name} replaces it after "
                f"{file.valid_until}"
            )
        else:
            selected.append(file)
    missing = [
        f"{m.label} {kind}"
        for m in MUNICIPALITIES
        for kind in ("household", "packaging")
        if not any(f.municipality == m.label and f.kind == kind for f in selected)
    ]
    if missing:
        raise build.ValidationError(f"no schedule found on the page for {', '.join(missing)}")
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, warnings = select_files(find_files(html), today)
    return [(f, http.get(f.url, timeout=60)) for f in files], warnings


# --- the tables ------------------------------------------------------------------

MONTHS = {
    fold(name): number
    for number, name in enumerate(
        "Sausis Vasaris Kovas Balandis Gegužė Birželis Liepa Rugpjūtis Rugsėjis Spalis Lapkritis "
        "Gruodis".split(),
        start=1,
    )
}
# A word of a cell of dates: "12;26", "5,", "26", "-".
DAY_WORD = re.compile(r"\d{1,2}(?:[,;]\d{1,2})*[,;]?|[-–]")
# Waste types in a column of their own or in the title above a table (folded).
KIND_WORDS: tuple[tuple[str, Kind], ...] = (
    ("misri", "household"),
    ("komunalin", "household"),
    ("maist", "food"),
    ("stikl", "glass"),
    ("pakuo", "packaging"),
    ("pop", "packaging"),
    ("plast", "packaging"),
    ("antrin", "packaging"),
)
# Rows of a table that aren't places: titles, notices, contacts (folded).
NOT_PLACES = re.compile(
    r"grafik|tustinam|kreipt|gabarit|privaciu namu|isstum|privaziavim|atliekos i konteiner"
    r"|vezimo metu|rusiavimo centr|aikstel"
)
# The text of a whole-municipality row (Birštonas: "Individualūs konteineriai").
WHOLE = "Visa savivaldybė"


def _kinds(text: str, spaced: bool = False) -> set[Kind]:
    """The waste types a text names; `spaced`: also in letters set apart ("S T I K L A S")."""
    folded = fold(text)
    if spaced:
        folded += " " + folded.replace(" ", "")
    return {kind for word, kind in KIND_WORDS if word in folded}


@dataclass
class _Column:
    x0: float
    x1: float
    role: str  # "place", "district", "type", "skip"


@dataclass
class _Header:
    top: float  # of the band with the year cells and the columns' titles
    bottom: float  # of the months' titles
    months: list[tuple[float, date]]  # the centre of each month's column, and its first day
    left: float  # the border left of the first month
    columns: list[_Column]  # left of the months
    kind: Kind | None  # of the title above the table

    @property
    def place_x(self) -> float:
        place = next((c for c in self.columns if c.role == "place"), None)
        return (place.x0 + place.x1) / 2 if place else self.left - 20

    def month(self, x: float) -> date | None:
        """The month of the column at `x`, if `x` is in the columns of dates."""
        if x < self.left - 1:
            return None
        centres = [c for c, _ in self.months]
        spacing = (centres[-1] - centres[0]) / max(len(centres) - 1, 1)
        if x > centres[-1] + spacing:
            return None
        return min(self.months, key=lambda m: abs(m[0] - x))[1]

    def column(self, x: float) -> str | None:
        return next((c.role for c in self.columns if c.x0 - 1 <= x <= c.x1 + 1), None)


def _lines(words: list[dict]) -> list[list[dict]]:
    """Words in lines, top to bottom."""
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= 2:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _month_titles(words: list[dict]) -> list[tuple[float, float, float, int]]:
    """(centre x, top, bottom, month) of the months' titles, also those written bottom to top
    as a stack of letters ("s", "a", "v", "o", "K")."""
    titles = [
        ((w["x0"] + w["x1"]) / 2, w["top"], w["bottom"], MONTHS[fold(w["text"])])
        for w in words
        if fold(w["text"]) in MONTHS
    ]
    stacks: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["x0"]), w["top"])):
        last = stacks[-1][-1] if stacks else None
        if last and abs(word["x0"] - last["x0"]) <= 1.5 and -1 <= word["top"] - last["bottom"] <= 3:
            stacks[-1].append(word)
        else:
            stacks.append([word])
    for stack in stacks:
        text = fold("".join(w["text"] for w in stack)[::-1])
        # The 2026 packaging file of Varėnos r. writes "Rupjūtis".
        close = {n for name, n in MONTHS.items() if name == text or _one_off(name, text)}
        month = close.pop() if len(close) == 1 else None
        if month and len(text) > 2:
            x = (min(w["x0"] for w in stack) + max(w["x1"] for w in stack)) / 2
            titles.append((x, stack[0]["top"], stack[-1]["bottom"], month))
    return titles


Title = tuple[float, float, float, int]  # centre x, top, bottom, month


def _rows_of_months(words: list[dict], where: str) -> list[list[Title]]:
    """The rows of months' titles on a page: at least six months in a row, one after another."""
    titles = sorted(_month_titles(words), key=lambda t: (t[1] + t[2]) / 2)
    groups: list[list[Title]] = []
    for title in titles:
        middle = (title[1] + title[2]) / 2
        if groups and abs(middle - (groups[-1][0][1] + groups[-1][0][2]) / 2) <= 12:
            groups[-1].append(title)
        else:
            groups.append([title])
    rows = []
    for group in groups:
        group = sorted(group)
        months = [t[3] for t in group]
        if len(months) < 6:
            continue
        if any((b - a) % 12 != 1 for a, b in zip(months, months[1:], strict=False)):
            raise ValueError(f"{where}: months out of order: {months}")
        rows.append(group)
    return rows


def _header(
    titles: list[Title], words: list[dict], v_rules: list[tuple[float, float, float]], where: str
) -> _Header:
    """A table's columns from the row of its months' titles: the months with their years
    from the cells above them, and the columns left of them."""
    top = min(t[1] for t in titles)
    bottom = max(t[2] for t in titles)
    middle = (top + bottom) / 2
    # The borders of the cells in the row of the months' titles and in the first row below it
    # (Birštonas: the titles of the places and the waste types are one empty cell).
    borders = sorted(
        x for x, t, b in v_rules if t - 1 <= middle <= b + 1 or t - 1 <= bottom + 8 <= b + 1
    )
    left_borders = [x for x in borders if x < titles[0][0] - 8]
    left = max(left_borders) if left_borders else titles[0][0] - 20
    # The year cells above the months ("2026 m.").
    band = sorted(
        (w for w in words if top - 45 <= w["top"] < top and w["x0"] >= left - 5),
        key=lambda w: (round(w["top"]), w["x0"]),
    )
    cells = [
        w
        for w, after in zip(band, [*band[1:], None], strict=False)
        if re.fullmatch(r"20\d{2}", w["text"]) and after is not None and after["text"] == "m."
    ]
    # Not the title's "2026 – 2027 m." (Prienų r.): the cells of the row nearest the months.
    if cells:
        lowest = max(w["top"] for w in cells)
        cells = [w for w in cells if lowest - w["top"] <= 4]
    years = sorted({int(w["text"]) for w in cells})
    if not years:
        raise ValueError(f"{where}: no year above the months")
    months = [t[3] for t in titles]
    wraps = sum(1 for a, b in zip(months, months[1:], strict=False) if b < a)
    if len(years) != wraps + 1 or years != list(range(years[0], years[0] + len(years))):
        raise ValueError(f"{where}: year cells {years} don't fit the months {months}")
    year = years[0]
    columns_of_months: list[tuple[float, date]] = []
    for i, (x, *_, month) in enumerate(titles):
        if i and month < titles[i - 1][3]:
            year += 1
        columns_of_months.append((x, date(year, month, 1)))
    # Columns left of the dates, between the borders, named by their titles: in the rows of
    # the years and the months.
    head_top = min(min(w["top"] for w in cells), top)
    label_words = [w for w in words if head_top - 12 <= w["top"] <= bottom and w["x1"] <= left + 1]
    # Without borders, one column of places. Double lines are one border.
    edges: list[float] = []
    for x in sorted(x for x in left_borders if x < left - 4):
        if not edges or x - edges[-1] >= 4:
            edges.append(x)
    columns: list[_Column] = []
    for x0, x1 in zip(edges or [0], [*edges[1:], left], strict=False):
        if x1 - x0 < 4:
            continue
        title = fold(
            " ".join(w["text"] for w in label_words if x0 <= (w["x0"] + w["x1"]) / 2 <= x1)
        )
        if re.search(r"\bseniunij", title):
            role = "district"
        elif re.search(r"\b(tipas|rusis)\b", title):
            role = "type"
        elif re.search(r"\bsav\s*d\b", title):
            role = "skip"
        else:
            role = "place"
        columns.append(_Column(x0, x1, role))
    places = [c for c in columns if c.role == "place"]
    if len(places) > 1:
        # Birštonas: the column of the waste types has no title; it is the one right of the
        # places.
        places[-1].role = "type"
    return _Header(head_top, bottom, columns_of_months, left, columns, None)


def _title_kind(lines: list[list[dict]], above: float, after: float) -> Kind | None | bool:
    """The waste type in the title nearest above a table ("MAISTO ATLIEKOS", "... MIŠRIŲ
    KOMUNALINIŲ ... GRAFIKAS"): a kind, None if the title has several (a column of waste types
    tells them), False if there is no title."""
    for line in reversed(lines):
        if not after <= line[0]["top"] < above:
            continue
        text = " ".join(w["text"] for w in line)
        folded = fold(text)
        if "grafik" not in folded and "atliek" not in folded:
            continue
        kinds = _kinds(text)
        if len(kinds) == 1:
            return kinds.pop()
        if kinds:
            return None
    return False


def _boundaries(edges: list[tuple[float, float, float]], *xs: float) -> list[float]:
    """The heights of the horizontal borders that cross every one of `xs`."""
    found: list[float] = []
    for top in sorted({round(e[0], 1) for e in edges}):
        if found and top - found[-1] <= 2:
            continue
        near = [e for e in edges if abs(e[0] - top) <= 1.5]
        if all(any(e[1] - 1 <= x <= e[2] + 1 for e in near) for x in xs):
            found.append(top)
    return found


@dataclass
class _Record:
    """A row of a table between two borders across its places and dates."""

    places: list[str] = field(default_factory=list)
    dates: list[tuple[Kind | None, list[tuple[date, int]]]] = field(default_factory=list)
    other: list[str] = field(default_factory=list)  # words in the columns of dates, not days

    @property
    def name(self) -> str:
        return clean_text(" ".join(p for p in self.places if p))


def _text(words: list[dict]) -> str:
    text = ""
    for line in _lines(words):
        joined = " ".join(w["text"] for w in line)
        # "Vilkutaičio-" + "Keturakio g."
        text += joined if not text or re.search(r"\w-$", text) else f" {joined}"
    return clean_text(text)


def _record(
    header: _Header, words: list[dict], edges: list, top: float, bottom: float, where: str
) -> _Record:
    record = _Record()
    inside = [w for w in words if top <= (w["top"] + w["bottom"]) / 2 <= bottom]
    first = header.months[0][0]
    # Rows of places (several in one record when a cell of dates spans them) and of dates.
    place_rows = [top, *(y for y in _boundaries(edges, header.place_x) if top < y < bottom), bottom]
    date_rows = [top, *(y for y in _boundaries(edges, first) if top < y < bottom), bottom]
    for y0, y1 in zip(place_rows, place_rows[1:], strict=False):
        row = [w for w in inside if y0 <= (w["top"] + w["bottom"]) / 2 <= y1]
        district = _text([w for w in row if header.column((w["x0"] + w["x1"]) / 2) == "district"])
        place = _text([w for w in row if header.column((w["x0"] + w["x1"]) / 2) == "place"])
        record.places.append(f"{district}: {place}" if district and place else district or place)
    for y0, y1 in zip(date_rows, date_rows[1:], strict=False):
        row = [w for w in inside if y0 <= (w["top"] + w["bottom"]) / 2 <= y1]
        label = " ".join(w["text"] for w in row if header.column((w["x0"] + w["x1"]) / 2) == "type")
        kinds = _kinds(label, spaced=True)
        if len(kinds) > 1:
            raise ValueError(f"{where}: waste type {label!r}")
        kind = kinds.pop() if kinds else header.kind
        days: list[tuple[date, int]] = []
        for word in row:
            month = header.month((word["x0"] + word["x1"]) / 2)
            if month is None:
                continue
            if DAY_WORD.fullmatch(word["text"]):
                days += [(month, int(day)) for day in re.findall(r"\d+", word["text"])]
            else:
                record.other.append(word["text"])
        if days:
            record.dates.append((kind, days))
    return record


def _dates(days: list[tuple[date, int]], where: str) -> set[date]:
    dates: set[date] = set()
    for month, day in days:
        try:
            dates.add(month.replace(day=day))
        except ValueError as error:
            raise ValueError(f"{where}: day {day} of {month:%Y-%m}: {error}") from error
    return dates


def _place_name(text: str) -> str:
    """The places as the reader of routes expects them."""
    # Varėnos r. food waste: "Individualūs maisto atliekų konteineriai Varėnos m.", "...
    # Merkinės mstl. / Senosios Varėnos k."; Birštonas: "Individualūs konteineriai", the whole
    # municipality.
    text = re.sub(r"^Individual\w*\s+(?:maisto\s+atliekų\s+)?konteineriai\b\s*", "", text)
    return clean_text(text.replace(" / ", ", ")) or WHOLE


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The routes of one file. Strict: words in the columns of dates that aren't days (but in
    a title or a notice), a day the month doesn't have, dates without a waste type or places,
    places without dates and a file without tables raise ValueError."""
    return schedules(source, _records(source, content))


def _records(source: SourceFile, content: bytes) -> list[tuple[_Record, str]]:
    """The rows of the file's tables, with where they are."""
    records: list[tuple[_Record, str]] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        header: _Header | None = None
        for page in pdf.pages:
            where = f"{source.file_name} page {page.page_number}"
            # A tight line: with the default tolerance, a week number a little lower in the
            # next column ("I") breaks the words of the places into letters.
            words = page.extract_words(y_tolerance=1)
            lines = _lines(words)
            edges = [(e["top"], e["x0"], e["x1"]) for e in page.edges if e["orientation"] == "h"]
            v_rules = [
                ((e["x0"] + e["x1"]) / 2, e["top"], e["bottom"])
                for e in page.edges
                if e["orientation"] == "v"
            ]
            tables: list[tuple[_Header, float, float]] = []
            start = 0.0
            for titles in _rows_of_months(words, where):
                new = _header(titles, words, v_rules, where)
                kind = _title_kind(lines, new.top, start)
                new.kind = header.kind if kind is False and header else kind or None
                if header:
                    tables.append((header, start, new.top))
                header, start = new, new.bottom
            if header:
                tables.append((header, start, float(page.height)))
            for table, top, bottom in tables:
                rows = [
                    y
                    for y in _boundaries(edges, table.place_x, table.months[0][0])
                    if top - 1 <= y <= bottom + 1
                ]
                # A table run on from the last page can start with a row whose cells of dates
                # have no top border (Lazdijų r. packaging, page 2): the border of its places.
                upper = [y for y in _boundaries(edges, table.place_x) if top - 1 <= y <= bottom]
                if upper and (not rows or upper[0] < rows[0] - 2):
                    rows.insert(0, upper[0])
                for y0, y1 in zip(rows, rows[1:], strict=False):
                    record = _record(table, words, edges, y0, y1, where)
                    records.append((record, where))
    return records


def schedules(source: SourceFile, records: list[tuple[_Record, str]]) -> ParseResult:
    """The schedules of a file's rows: one per waste type of a row of places."""
    municipality = getattr(source, "municipality", "")
    group = getattr(source, "group", None)
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for record, where in records:
        text = record.name
        if record.other or not record.dates:
            if NOT_PLACES.search(fold(f"{text} {' '.join(record.other)}")) or not (
                text or record.dates
            ):
                continue  # a title, a notice, an empty row
            if record.other:
                raise ValueError(f"{where}: not days: {' '.join(record.other)!r} ({text[:60]!r})")
            raise ValueError(f"{where}: places without dates: {text[:80]!r}")
        if not text:
            raise ValueError(f"{where}: dates without places")
        name = _place_name(text)
        for kind, days in record.dates:
            if kind is None:
                raise ValueError(f"{where}: dates of no waste type ({text[:60]!r})")
            dates = _in_force(source, _dates(days, where))
            if not dates:
                continue
            area = Area(
                kind=kind,
                name=name,
                district=municipality or None,
                group=group,
                dates=dates,
                provider=PROVIDER.id,
            )
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{where}: {kind} of {name[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    if not areas:
        raise ValueError(f"{source.file_name}: no schedule table found")
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def _in_force(source: SourceFile, dates: set[date]) -> set[date]:
    """The dates within the file's validity on the page."""
    since = getattr(source, "valid_from", None) or date.min
    until = getattr(source, "valid_until", None) or date.max
    return {d for d in dates if since <= d <= until}


# --- the places ------------------------------------------------------------------

# "SIMNO SEN.", "Krokialaukio sen.:", "Visoje N. Ūtos sen.", "Dalyje Šilavoto sen.:", "Lazdijų
# miesto sen.:", "BUTRIMONIŲ SEN.,": an eldership; "Dalyje Prienų miesto.:": a town's streets.
_ELDERSHIP = re.compile(
    rf"(?:\b(?P<scope>Visoje|Dalyje|Dalis)\s+)?"
    rf"\b(?P<name>(?:Naujosios\s+)?{_WORD}(?:\s+(?i:miesto))?)\s+(?i:sen\b\.?|seniūnij\w*)\s*[:,]?",
    re.U,
)
_TOWN = re.compile(rf"(?:\b(?:Dalyje|Dalis)\s+)?\b(?P<name>{_WORD})\s+miesto\b\.?\s*:", re.U)
# "tik Jiezno sen. esantys kaimai (be Jiezno, Strazdiškių, Jiezno Kolonijų)": the villages of an
# eldership but these.
_VILLAGES_BUT = re.compile(
    rf"(?:tik\s+)?\b(?P<name>{_WORD})\s+sen\.?\s+(?i:esantys)\s+kaimai\s*"
    r"(?:\(\s*(?:be|i[sš]+kyrus)\s+(?P<but>[^)]*)\))?",
    re.U,
)
_STREET_TYPE_WORD = r"(?:g|al|pl|skg|aklg|tak|takas|a)"
# The publisher's spellings, as SectionRoutes reads them.
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "N. Ūtos sen.", "N.Ūtos".
    (re.compile(r"\bN\.\s*Ūtos\b"), "Naujosios Ūtos"),
    # Types in capitals or in words: "VARĖNOS M.:", "MERKINĖS MSTL.", "Valančiūnių K.", "Daugų
    # km.", "Daugų miestas", "LAZDIJŲ MIESTAS.", "Veičiūnų mst.".
    (re.compile(r"(?<=\w)\s+MSTL\.(?=\s|[,;:(]|$)"), " mstl."),
    (re.compile(r"(?<=\w)\s+M\.(?=\s|[,;:(]|$)"), " m."),
    (re.compile(r"(?<=\w)\s+K\.(?=\s|[,;:(]|$)"), " k."),
    (re.compile(r"\bkm\.(?=\s|[,;:(]|$)"), "k."),
    (re.compile(r"\bmiestas\b\.?", re.I), "m."),
    (re.compile(r"\bmst\.(?=\s|[,;:(]|$)", re.I), "mstl."),
    # "Marčiukonių k. k. Nemajūnų k.", "Merkinės k..".
    (re.compile(r"\b(k|m|mstl|vs)\.(?:\s+\1)?\.(?=\s|$)"), r"\1."),
    # "Perlojos k. I ir II skyriai": the parts of one village.
    (re.compile(r"\s+I\s+ir\s+II\s+skyri\w*"), ""),
    # "Byliškių sodų bendrijos": the garden communities by the village, whose addresses are
    # the village's.
    (re.compile(rf"\b({_WORD}(?:\s+{_WORD})?)\s+sodų\s+bendrij\w*"), r"\1 k."),
    # "Senosios Varėnos k. (Antakalnio g., ...). VARĖNOS M.: (...)": the next place.
    (re.compile(rf"\)\.\s+(?=[{_UPPER}])"), "), "),
    # "Ratnyčiosg.", "Tylos.g.".
    (re.compile(r"(?<=[a-ząčęėįšųūž]{3})\.?g\.(?=\s*[,;]|\s*$)"), " g."),
    # "Padirmiškis- Plenta": two villages.
    (re.compile(rf"(?<=\w)-\s+(?=[{_UPPER}])"), ", "),
    # A part of a street ("M. K. Čiurlionio g. (nuo 119 iki 175)", "Takniškių g.(Nuo Alytaus m.
    # iki viaduko)", "Kunigiškių g. nuo 1 iki 36"): some of its houses, as a house number would.
    (re.compile(rf"\b({_STREET_TYPE_WORD})\.?\s*\(\s*(?i:nuo)\b[^()]*\)"), r"\1. 0"),
    (re.compile(rf"\b({_STREET_TYPE_WORD})\.\s+nuo\s+\d+\s*\w?\s+iki\s+\d+\s*\w?"), r"\1. 0"),
    # "(be Jurginų g.)": but; "( tik Jurginų g.)": only.
    (re.compile(r"\(\s*be\s+"), "(išskyrus "),
    (re.compile(r"\(\s*tik\s+"), "("),
    # "Lazdijų k. - visas išskyrus Kauno g., Ramybės g., Padumblių k.": brackets, closed by
    # _close.
    (re.compile(r"\b(k|m|mstl|vs)\.\s*-\s*(?:visas\s+)?i[sš]+kyrus\s+"), r"\1. ⟪išskyrus "),
    # A settlement, then its streets: "VARĖNOS m.: (A. Smetonos g., ...)", "Perlojos k., (Šilo
    # g.)", "Druskininkų m.: Ąžuolo g., ...", "Lazdijų m. - Dariaus ir Girėno g.", "Senosios
    # Varėnos k. tik Antakalnio g.", "Miklusėnai: Ūdrijos g.".
    (re.compile(r"\b(k|m|mstl|vs)\.\s*[:,]?\s*\("), r"\1. ("),
    (re.compile(r"\b(k|m|mstl|vs)\.\s*(?:[:-]\s*)?(?:tik\s+)?(?=[^\s\d,;:()⟪.-])"), r"\1., "),
    (re.compile(rf"(?<=\w):\s+(?=[{_UPPER}])"), ", "),
)
_STREET_PART = re.compile(rf"^.*\b{_STREET_TYPE_WORD}\.?(?:\s*\d+\s*\w?)?$")
_OPEN = "⟪"  # a bracket the fixes open, without its end
_NO_TOWN = Settlement(code=0, name="", genitive="", abbr="m.", district="\0")


def _close(text: str) -> str:
    """Closes the brackets the fixes open (_OPEN) after the last street of their list:
    "Lazdijų k. ⟪išskyrus Kauno g., Ramybės g., Padumblių k." -> "Lazdijų k. (išskyrus Kauno
    g., Ramybės g.), Padumblių k."."""
    while (start := text.find(_OPEN)) >= 0:
        parts = text[start + 1 :].split(",")
        streets = 0
        while streets < len(parts) and _STREET_PART.match(parts[streets].strip()):
            streets += 1
        inside = ",".join(parts[:streets])
        after = ",".join(parts[streets:])
        text = text[:start] + (f"({inside})" if streets else "") + (f",{after}" if after else "")
    return text


def normalize(text: str) -> str:
    """The publisher's spellings, as SectionRoutes reads them."""
    text = clean_text(text)
    for pattern, replacement in _FIXES:
        text = pattern.sub(replacement, text)
    text = _close(text)
    # A bracket closed that was never opened: "Navickai (Navickų g. 2, ... 15); Gintaro g., ...
    # Rasos g)".
    depth, kept = 0, []
    for ch in text:
        if ch == ")" and depth == 0:
            continue
        depth += (ch == "(") - (ch == ")")
        kept.append(ch)
    return clean_text("".join(kept))


class Routes(SectionRoutes):
    """Reads one row of the centre's schedules: the places of one municipality (the row's
    `district`), in sections of elderships or not:

        SIMNO SEN. Simnas, Kaimynai. KROKIALAUKIO SEN. Dapkiškės, ...      nominative
        LAZDIJŲ MIESTAS. Alyvų g., ... LAZDIJŲ SEN. Buktos k., ...         genitive and type
        Visoje N. Ūtos sen. Dalyje Šilavoto sen.: Jasenava, ...            a whole eldership
        BUTRIMONIŲ SEN., PUNIOS SEN. Adamonys, ...                         a whole eldership
        Dalyje Jiezno sen.: tik Jiezno sen. esantys kaimai (be Jiezno, ...) but some villages
        Dalyje Prienų miesto.: Algirdo g., Alyvų g., ...                   streets of a town
        Druskininkų m.: Ąžuolo g., ... Viečiūnų sen.: Neravų k., ...       a town, then sections
        Miklusėnų k., Miroslovo k., Simno m., ...                          no sections
        Visa savivaldybė                                                   Birštono sav.

    The publisher's spellings are first written as SectionRoutes reads them (normalize). A
    settlement is looked up in the eldership its section names, and without a section in the
    whole municipality. A whole eldership is a fallback: a settlement another row of the kind
    names gets that row instead. The towns' streets that no route names have no pickup (shared
    containers of apartment buildings), as for Jurbarkas.
    """

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.unknown: list[str] = []
        self.named: dict[str, set[int]] | None = None
        self.kind = ""
        self.town = _NO_TOWN
        self.municipality = MUNICIPALITIES[0]
        mine = [s for s in index.registry.settlements if s.district in provider.elderships]
        self.places = {
            m.label: [s for s in mine if s.district in m.elderships] for m in MUNICIPALITIES
        }
        self.towns = {s.code for s in mine if s.abbr == "m."}

    def district(self, name: str) -> str | None:
        """The eldership of the row's municipality a section names ("SIMNO", "Naujosios
        Ūtos", "Lazdijų miesto")."""
        key = fold(name)
        exact = [d for d in self.municipality.elderships if fold(d) == key]
        if exact:
            return exact[0]
        town = key.endswith(" miesto")
        close = [
            d
            for d in self.municipality.elderships
            if ("miesto" in fold(d)) == town and _near(key.split()[0], fold(d).split()[0])
        ]
        return close[0] if len(close) == 1 else None

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        names = [f"{name} {n}" for n in re.findall(r"I{1,3}", numerals)] if numerals else [name]
        pool = self.places[self.municipality.label]
        here = [s for s in pool if s.district == district] if district else pool
        hits: list[Settlement] = []
        for one in names:
            key = fold(one)
            found = [s for s in here if key in (fold(s.name), fold(s.genitive))]
            if not found and numerals and one.endswith(" I"):
                # "Balnių I ir II k.": the register calls the first one Balniai.
                found = [s for s in here if fold(one[:-2]) in (fold(s.name), fold(s.genitive))]
            if not found and not numerals:
                # "Akmena" for Akmena I and II.
                found = [
                    s
                    for s in here
                    if any(
                        re.fullmatch(re.escape(key) + r" i{1,3}", fold(form))
                        for form in (s.name, s.genitive)
                    )
                ]
            for close in (_near, _one_off, _typo):
                if not found:
                    # Another ending or a typo ("Miroslovo k.", "Dainaviškiš k.", "Rantyčios
                    # k."), if only one name is that close.
                    near = [
                        s for s in here if close(key, fold(s.genitive)) or close(key, fold(s.name))
                    ]
                    found = near if len({s.name for s in near}) == 1 else []
            if not found and district and self.named is not None:
                # In another eldership of the municipality: the only one of that name, if no
                # row of the kind names it in its own.
                elsewhere = [s for s in pool if key in (fold(s.name), fold(s.genitive))]
                if len(elsewhere) == 1 and elsewhere[0].code not in self.named[self.kind]:
                    found = elsewhere
            abbr = _SETTLEMENT_TYPES.get(kind or "")
            wanted = {"m.": ("m.", "mstl."), "mstl.": ("mstl.", "m.")}.get(abbr or "", (abbr,))
            typed = next((t for a in wanted if (t := [s for s in found if s.abbr == a])), [])
            hits += typed or found
        return list({s.code: s for s in hits}.values())

    def section(self, district: str, text: str) -> list[_Stop]:
        """The settlements of an eldership's section, or without one ("") of the municipality,
        and their streets, as SectionRoutes reads them; but a street the settlement doesn't
        have leaves the streets after it to that settlement, two names without a comma
        ("Mieliūnai Novoplenta") are two settlements, and a settlement put in another eldership
        with some of its streets ("Pakuonio sen.: ... Bagrėnas (tik Jurginų g.)") is the only one
        of that name in the municipality."""
        stops: list[_Stop] = []
        current: list[_Stop] = []  # the settlement the streets after it belong to
        last: list[tuple[_Stop, set[str]]] = []  # the last street, for house numbers after it
        where = f"{district} sen." if district else self.municipality.label
        for part in _section_parts(text):
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0] if rest else None
            head = head.strip(" ,;:")
            if _HOUSE.fullmatch(head):
                for stop, keys in last:
                    stop.add(keys, houses=True)
                continue
            match = _SECTION_ITEM.fullmatch(head)
            name, numerals, kind = match.group("name", "numerals", "type") if match else ("",) * 3
            houses = bool(match and match.group("houses"))
            places: list[Settlement] = []
            if match and (kind in _SETTLEMENT_TYPES or numerals or not (kind or houses)):
                places = self.settlements(name, numerals, kind, district)
                if not places and district and spec and _STREET_TYPE.search(f" {fold(spec)} "):
                    places = self.settlements(name, numerals, kind, "")
                    places = places if len(places) == 1 else []
            if match and not places and kind not in _SETTLEMENT_TYPES:
                # A street of the settlement before it, or of the town in its own section.
                targets = current
                if not targets and district == self.town.district:
                    town = next((s for s in stops if s.settlement is self.town), None)
                    targets = [town or _Stop(self.town)]
                loose = bool(kind or houses)
                found = [(t, self.streets(t.settlement, head, name, kind, loose)) for t in targets]
                if any(keys for _, keys in found):
                    last = [(t, keys) for t, keys in found if keys]
                    for target, keys in last:
                        target.add(keys, houses)
                        if target not in stops:
                            stops.append(target)
                    continue
                if kind == "g":
                    # "Raudonėnų g." for the village Raudonėnai.
                    places = self.settlements(name, None, None, district)
                if not places and (kind or houses) and targets:
                    self.unknown += [
                        f"{t.settlement.genitive} {t.settlement.abbr}: {head[:60]}" for t in targets
                    ]
                    last = []
                    continue
                if not places and not (kind or houses) and len(words := name.split()) > 1:
                    split = [self.settlements(word, None, None, district) for word in words]
                    places = [s for hits in split for s in hits] if all(split) else []
            if not places:
                self.unknown.append(f"{where}: {head[:60]}")
                current, last = [], []
                continue
            current, last = [_Stop(s) for s in places], []
            stops += current
            if spec is not None:
                self.spec(current, spec)
        return stops

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        self.kind = area.kind
        self.municipality = BY_LABEL[area.district or ""]
        self.town = _NO_TOWN
        text = clean_text(area.name)
        for written, registered in self.provider.aliases:
            text = text.replace(written, registered)
        if fold(text) == fold(WHOLE):
            return [(s, Clause(area.id, None)) for s in self.places[self.municipality.label]], False
        rules: list[tuple[str | None, set[str]]] = []

        def villages_but(match: re.Match[str]) -> str:
            rules.append((self.district(match["name"]), set(_section_parts(match["but"] or ""))))
            return f" §{len(rules) - 1}§ "

        text = normalize(_VILLAGES_BUT.sub(villages_but, text))
        marks: list[tuple[int, int, str | None, Settlement, bool]] = []
        for m in _ELDERSHIP.finditer(text):
            marks.append(
                (m.start(), m.end(), self.district(m["name"]), _NO_TOWN, m["scope"] == "Visoje")
            )
        for m in _TOWN.finditer(text):
            town = next(
                (
                    s
                    for s in self.places[self.municipality.label]
                    if s.abbr == "m." and fold(s.genitive) == fold(m["name"])
                ),
                None,
            )
            marks.append(
                (m.start(), m.end(), town.district if town else None, town or _NO_TOWN, False)
            )
        marks.sort()
        clauses: list[tuple[Settlement, Clause]] = []
        lead = text[: marks[0][0]] if marks else text
        stops = self.section("", lead) if lead.strip(" .,;:") else []
        for i, (start, end, district, town, whole) in enumerate(marks):
            until = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            body = text[end:until]
            if district is None:
                self.unknown.append(text[start:end])
                continue
            self.town = town
            ruled = re.findall(r"§(\d+)§", body)
            for number in ruled:
                eldership, but = rules[int(number)]
                excluded = {
                    s.code
                    for name in but
                    for s in self.settlements(name.strip(" .,"), None, None, eldership or district)
                }
                clauses += self._whole(area, eldership or district, excluded)
            body = re.sub(r"§\d+§", "", body)
            if whole or (not body.strip(" .,;:") and town is _NO_TOWN and not ruled):
                clauses += self._whole(area, district, set())
            stops += self.section(district, re.sub(r"^\s*tik\s+", "", body.strip(" .,;:")))
            self.town = _NO_TOWN
        return clauses + [(s.settlement, c) for s in stops for c in s.clauses(area.id)], False

    def _whole(
        self, area: Area, district: str, excluded: set[int]
    ) -> list[tuple[Settlement, Clause]]:
        """Every settlement of an eldership but `excluded`: a fallback to the rows naming one."""
        return [
            (s, Clause(area.id, None, fallback=True))
            for s in self.places[self.municipality.label]
            if s.district == district and s.code not in excluded
        ]


PROVIDER = Provider(
    id="alytus",
    name=NAME,
    url=PAGE_URL,
    elderships=frozenset().union(*(m.elderships for m in MUNICIPALITIES)),
    # Typos too far from the register's names to be taken for them.
    aliases=(
        ("Veičiūnų mst.", "Viečiūnų mstl."),  # Druskininkai, farmsteads
        ("Aštriosiosios Kirsnos", "Aštriosios Kirsnos"),  # Lazdijų r., mixed waste
        ("Didžiosiosios Kirsnos", "Didžiosios Kirsnos"),
        ("Žiaunieriškės", "Žaunieriškiai"),  # Alytaus r., mixed waste
        ("Jiesenava", "Jasenava"),  # Prienų r., packaging
        ("Degnių k.", "Degsnių k."),  # Varėnos r., mixed waste
    ),
    kinds=("household", "food", "packaging", "glass"),
    reader=Routes,
)


def town_elderships(registry: Registry) -> Registry:
    """Birštonas and Druskininkai belong to no eldership in the register, and the app shows a
    place's eldership: they get one of their own, "Birštono miesto", as Jurbarkas has."""
    return Registry(
        [replace(s, district=s.district or f"{s.genitive} miesto") for s in registry.settlements]
    )


# --- this contract year and the next ------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]],
    registry: Registry,
    today: date,
    check: bool = True,
) -> list[str]:
    """Joins the routes of the files of each municipality and kind in place, and checks that
    each municipality has its routes.

    A place has one row per waste type, with all its dates. A file starts when its first
    pickup is; the newest file that has started is in force (or the first one, before any has).
    A route of a file that starts later and covers exactly the places of one route in force
    gives that route its dates (the next contract year's file, posted in February); the rest
    wait, with a warning, until their file starts. Routes of files that started earlier are
    dropped. With `check`, too few routes of a municipality, in force or in a later file, raise
    ValidationError."""
    reader = Routes(Index(registry), PROVIDER, defaultdict(dict))
    warnings: list[str] = []
    starts = {
        id(result): min(d for a in result.areas for d in a.dates)
        for _, result in parsed
        if result.areas
    }
    ends = {
        id(result): max(d for a in result.areas for d in a.dates)
        for _, result in parsed
        if result.areas
    }
    groups: dict[tuple, dict[date, list[tuple[ParseResult, Area]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for _, result in parsed:
        for area in result.areas:
            groups[(area.district, area.kind, area.group)][starts[id(result)]].append(
                (result, area)
            )
    for (label, kind, group), files in groups.items():
        started = [start for start in files if start <= today]
        base = max(started) if started else min(files)
        end = max(ends[id(result)] for result, _ in files[base])
        if end < today and base == max(files):
            warnings.append(f"{label} {kind}: the schedule ended on {end}, no newer one is read")
        current: dict[frozenset, list[Area]] = defaultdict(list)
        for _, area in files[base]:
            current[reader.signature(area)].append(area)
        for start in sorted(files):
            if start == base:
                continue
            later = files[start]
            minimum = BY_LABEL[label].min_areas.get(kind, 0) if check and group is None else 0
            if start > base and len(later) < minimum:
                raise build.ValidationError(
                    f"{label}: only {len(later)} {kind} routes in the file from {start} "
                    f"(expected at least {minimum})"
                )
            signatures = {id(area): reader.signature(area) for _, area in later}
            times = Counter(signatures.values())
            continued: set[int] = set()
            for result, area in later:
                same = current.get(signatures[id(area)], [])
                if start > base and signatures[id(area)] and len(same) == 1:
                    if times[signatures[id(area)]] == 1:
                        same[0].dates |= area.dates
                        continued.add(id(same[0]))
                        result.areas.remove(area)
                        continue
                if start > base:
                    warnings.append(
                        f"{label} {kind}: the route {area.name[:60]!r} from {start} doesn't "
                        f"match one in force; its dates are left out until then"
                    )
                result.areas.remove(area)
            if start > base:
                warnings += [
                    f"{label} {kind}: the route {area.name[:60]!r} has no dates from {start}"
                    for _, area in files[base]
                    if id(area) not in continued
                ]
    counts = Counter(
        (a.district, a.kind) for _, result in parsed for a in result.areas if a.group is None
    )
    missing = [
        f"{count} {kind} routes of {m.label} (expected at least {minimum})"
        for m in MUNICIPALITIES
        for kind, minimum in m.min_areas.items()
        if (count := counts[(m.label, kind)]) < minimum
    ]
    if check and missing:
        raise build.ValidationError("only " + "; ".join(missing))
    return warnings


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    {"household": 50, "food": 10, "packaging": 40, "glass": 40},
    MIN_HOUSEHOLD_PLACES,
    FILE_KINDS,
    combine,
)


# --- the output ------------------------------------------------------------------


def fetch_registry() -> Registry:
    return Registry(
        [
            s
            for name, _ in snapshot.ALYTUS_MUNICIPALITIES
            for s in address_register.fetch(name).settlements
        ]
    )


def fetch_points() -> list[address_points.AddressPoint]:
    return address_points.fetch_all([code for _, code in snapshot.ALYTUS_MUNICIPALITIES])


def check_places(dataset: dict) -> None:
    """Each municipality's settlements must get mixed waste schedules: a broken file doesn't
    show in the totals of six."""
    with_schedule = Counter(
        loc["district"] for loc in dataset["locations"] if "household" in loc.get("schedule", {})
    )
    for m in MUNICIPALITIES:
        places = sum(with_schedule[d] for d in m.elderships)
        everywhere = sum(1 for loc in dataset["locations"] if loc["district"] in m.elderships)
        if places < 0.6 * everywhere:
            raise build.ValidationError(
                f"{m.label}: only {places} of {everywhere} settlements got a mixed waste schedule"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    args = parser.parse_args(argv)

    registry, registry_note = build.live_or_snapshot(
        "Address Register",
        fetch_registry,
        lambda: snapshot.load_registry(snapshot.ALYTUS_REGISTRY_FILE),
    )
    points, points_note = build.live_or_snapshot(
        "Address points",
        fetch_points,
        lambda: snapshot.load_points(snapshot.ALYTUS_ADDRESSES_FILE),
    )
    registry = town_elderships(registry)
    try:
        results = build.build_parts((SOURCE,), registry, date.today(), args.keep_days, None)
        dataset = build.merge_parts([(r.provider, r.part) for r in results], PAGE_URL)
        check_places(dataset)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < MIN_ADDRESS_POINTS:
            raise build.ValidationError(f"only {len(addresses['points'])} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    notes = [n for n in (registry_note, points_note) if n]
    title = "Alytaus r., Prienų r., Lazdijų r., Varėnos r., Druskininkai, Birštonas (Alytaus RATC)"
    build.write_summary(dataset, results, notes, title, "alytaus-ratc/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

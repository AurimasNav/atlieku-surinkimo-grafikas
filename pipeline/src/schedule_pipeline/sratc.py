"""Šiaulių r., Akmenės r., Joniškio r., Kelmės r. and Pakruojo r.: schedules published by the
regional waste centre of Šiauliai county, UAB „Šiaulių regiono atliekų tvarkymo centras“.

The centre's site has a page per municipality (https://www.sratc.lt/grafikai-<x>-rajonas/), each
with a section "Atliekų surinkimo grafikai individualioms valdoms": a PDF a year for private
houses ("Visų rūšių atliekų surinkimas 2026 m.") with every kind of waste. The files' names and
folders differ per municipality and change when a file is revised, so they are found by the
section, or the word "individual" in the file's name, and the year in the link's text or the
file's name. Radviliškio r. lays its files out differently (and collects mixed waste once a
quarter) and isn't read; nor are the shared containers of apartment buildings.

The five municipalities are one source: one site, one template, one file in the output
(sratc/schedule.json, provider "siauliai"). A file that can't be read fails the whole build,
and yesterday's data is kept for all five.

Every file has the same template, a table per place (Excel printed to PDF):

    KURŠĖNŲ KAIMIŠKOJI SENIŪNIJA
    Gatvės (gyvenamosios vietovės)  | Mišrių komunalinių | Pakuočių ... | Stiklo ... | Žaliųjų ...
    pavadinimas                     |  atliekų grafikas  |              |            |
    Bijūnėlių k., Geruogės k., ...  | Sausis | 8         | Sausis | 30  | Sausis |   | Sausis |
                                    | Vasaris | 5        | Vasaris | 20 | Vasaris | 10 | ...
                                    | ... twelve months

A place is a list of villages, streets of a town or both; the eldership (or the town) is the
heading above the table or in its first row. The year is in the title ("... 2026 METAMS").
Waste types per file: mixed waste, packaging, glass, green waste (Joniškio r.: green and food
waste, read as food waste, as for Mažeikių r.), and bulky and hazardous waste, collected once or
twice a year and not read.

The places are linked to the Address Register by Blocks (below). Next year's files appear in
December: a place of next year that covers the same settlements and streets as one of this
year continues it (combine).

Writes <out>/schedule.json and <out>/addresses.json, in the format of the Vilniaus r. files, for
all five municipalities.
Run: python -m schedule_pipeline.sratc --out ../site/sratc
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import (
    _HOUSE,
    _NUMERALS,
    _QUOTES,
    _SECTION,
    _SETTLEMENT_TYPES,
    _SPELLINGS,
    _UPPER,
    _WORD,
    Clause,
    Index,
    SectionRoutes,
    _one_off,
    _section_parts,
    _Stop,
    street_key,
    streets_in,
    variant_key,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

PAGE_URL = "https://www.sratc.lt/kalendoriaus-grafikai/"


@dataclass(frozen=True)
class Municipality:
    """A municipality whose schedules the centre publishes."""

    name: str  # "Šiaulių r."
    page: str  # its page on the site
    register: tuple[str, int]  # the Address Register's name and code
    registry_file: Path
    addresses_file: Path
    # Its elderships, as the register names them.
    elderships: frozenset[str]
    # Fewer places in a file means the format changed and the parser missed some.
    min_blocks: int
    # Settlements that must get a mixed waste schedule: fewer means the matching broke.
    min_household_places: int


def _page(slug: str) -> str:
    return f"https://www.sratc.lt/grafikai-{slug}-rajonas/"


SIAULIU_R = Municipality(
    name="Šiaulių r.",
    page=_page("siauliu"),
    register=snapshot.SIAULIU_R_MUNICIPALITY,
    registry_file=snapshot.SIAULIU_R_REGISTRY_FILE,
    addresses_file=snapshot.SIAULIU_R_ADDRESSES_FILE,
    elderships=frozenset(
        {
            "Bubių",
            "Ginkūnų",
            "Gruzdžių",
            "Kairių",
            "Kuršėnų kaimiškoji",
            "Kuršėnų miesto",
            "Kužių",
            "Meškuičių",
            "Raudėnų",
            "Šakynos",
            "Šiaulių kaimiškoji",
        }
    ),
    min_blocks=90,
    min_household_places=350,
)
AKMENES_R = Municipality(
    name="Akmenės r.",
    page=_page("akmenes"),
    register=snapshot.AKMENES_R_MUNICIPALITY,
    registry_file=snapshot.AKMENES_R_REGISTRY_FILE,
    addresses_file=snapshot.AKMENES_R_ADDRESSES_FILE,
    elderships=frozenset(
        {
            "Akmenės",
            "Kruopių",
            "Naujosios Akmenės kaimiškoji",
            "Naujosios Akmenės miesto",
            "Papilės",
            "Ventos",
        }
    ),
    min_blocks=11,
    min_household_places=100,
)
JONISKIO_R = Municipality(
    name="Joniškio r.",
    page=_page("joniskio"),
    register=snapshot.JONISKIO_R_MUNICIPALITY,
    registry_file=snapshot.JONISKIO_R_REGISTRY_FILE,
    addresses_file=snapshot.JONISKIO_R_ADDRESSES_FILE,
    elderships=frozenset(
        {
            "Gaižaičių",
            "Gataučių",
            "Joniškio",
            "Kepalių",
            "Kriukų",
            "Rudiškių",
            "Satkūnų",
            "Saugėlaukio",
            "Skaistgirio",
            "Žagarės",
        }
    ),
    min_blocks=11,
    min_household_places=180,
)
KELMES_R = Municipality(
    name="Kelmės r.",
    page=_page("kelmes"),
    register=snapshot.KELMES_R_MUNICIPALITY,
    registry_file=snapshot.KELMES_R_REGISTRY_FILE,
    addresses_file=snapshot.KELMES_R_ADDRESSES_FILE,
    elderships=frozenset(
        {
            "Kelmės",
            "Kelmės apylinkių",
            "Kražių",
            "Kukečių",
            "Liolių",
            "Pakražančio",
            "Šaukėnų",
            "Tytuvėnų",
            "Tytuvėnų apylinkių",
            "Užvenčio",
            "Vaiguvos",
        }
    ),
    min_blocks=38,
    min_household_places=450,
)
PAKRUOJO_R = Municipality(
    name="Pakruojo r.",
    page=_page("pakruojo"),
    register=snapshot.PAKRUOJO_R_MUNICIPALITY,
    registry_file=snapshot.PAKRUOJO_R_REGISTRY_FILE,
    addresses_file=snapshot.PAKRUOJO_R_ADDRESSES_FILE,
    elderships=frozenset(
        {
            "Guostagalio",
            "Klovainių",
            "Linkuvos",
            "Lygumų",
            "Pakruojo",
            "Pašvitinio",
            "Rozalimo",
            "Žeimelio",
        }
    ),
    min_blocks=40,
    min_household_places=250,
)
MUNICIPALITIES = (SIAULIU_R, AKMENES_R, JONISKIO_R, KELMES_R, PAKRUOJO_R)
BY_NAME = {m.name: m for m in MUNICIPALITIES}


# --- the pages --------------------------------------------------------------------------


class _Links(HTMLParser):
    """The PDF links of a page with their texts and the title of the section they're in (the
    accordion "Atliekų surinkimo grafikai individualioms valdoms"), and the page's <base>."""

    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.base = page_url
        self.links: list[tuple[str, str, str]] = []
        self.open: list[tuple[str | None, bool, list[str]]] = []
        self.section = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "base" and values.get("href"):
            self.base = urljoin(self.base, values["href"] or "")
        elif tag == "a":
            toggler = "accord-toggler" in (values.get("class") or "")
            self.open.append((values.get("href"), toggler, []))

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.open:
            href, toggler, text = self.open.pop()
            if toggler:
                self.section = clean_text("".join(text))
            elif href:
                url = urljoin(self.base, href)
                self.links.append((url, clean_text("".join(text)), self.section))

    def handle_data(self, data: str) -> None:
        if self.open:
            self.open[-1][2].append(data)


def _year_in(text: str) -> int | None:
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}
    return years.pop() if len(years) == 1 else None


def file_name(url: str) -> str:
    return PurePosixPath(unquote(urlsplit(url).path)).name


# Files for other kinds of customers, linked next to those of private houses.
OTHER_FILES = ("daugiab", "bendro", "juridin", "kapin", "tekstil", "dezinf", "plovim", "pozemin")


def find_files(html: str, municipality: Municipality) -> list[tuple[SourceFile, int | None]]:
    """The schedules of private houses linked from a municipality's page, with their years (in
    the link's text, "Visų rūšių atliekų surinkimas 2026 m.", or the file's name)."""
    collector = _Links(municipality.page)
    collector.feed(html)
    files: list[tuple[SourceFile, int | None]] = []
    for url, text, section in collector.links:
        name = file_name(url)
        folded = fold(name)
        if not url.lower().endswith(".pdf") or any(word in folded for word in OTHER_FILES):
            continue
        if "individual" not in fold(section) and "individual" not in folded:
            continue
        if all(f.url != url for f, _ in files):
            year = _year_in(text) or _year_in(name)
            files.append((SourceFile("household", url, name, municipality.name), year))
    return files


def select_files(
    files: list[tuple[SourceFile, int | None]], municipality: Municipality, today: date
) -> tuple[list[SourceFile], list[str]]:
    """The files of this year and later; if there are none, the newest one. Of two for one year
    (a correction linked next to the original), the one linked last."""
    where = municipality.name
    warnings = [
        f"{where}: {f.file_name}: no year in its link or name; not read" for f, y in files if not y
    ]
    dated = [(f, y) for f, y in files if y]
    running = [(f, y) for f, y in dated if y >= today.year]
    if not running and dated:
        newest = max(y for _, y in dated)
        running = [(f, y) for f, y in dated if y == newest]
    if today.year not in {y for _, y in running}:
        warnings.append(f"{where}: no schedule for {today.year} on the page")
    selected: list[SourceFile] = []
    for year in sorted({y for _, y in running}):
        same = [f for f, y in running if y == year]
        selected.append(same[-1])
        warnings += [
            f"{where}: {f.file_name}: not read, {same[-1].file_name} is a newer schedule for {year}"
            for f in same[:-1]
        ]
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    files: list[tuple[SourceFile, bytes]] = []
    warnings: list[str] = []
    for municipality in MUNICIPALITIES:
        html = http.get(municipality.page, timeout=60).decode("utf-8", errors="replace")
        found = find_files(html, municipality)
        if not found:
            raise ValueError(f"{municipality.name}: no schedule of private houses on its page")
        chosen, notes = select_files(found, municipality, today)
        warnings += notes
        files += [(f, http.get(f.url, timeout=120)) for f in chosen]
    return files, warnings


# --- the files --------------------------------------------------------------------------

# The column titles of the waste types (folded). Bulky and hazardous waste: not read.
KINDS: tuple[tuple[str, Kind | None], ...] = (
    ("misri", "household"),
    ("pakuoc", "packaging"),
    ("stikl", "glass"),
    ("zaliuju maisto", "food"),  # Joniškio r.: "Žaliųjų/maisto ir virtuvės atliekų"
    ("zaliuju", "green"),
    ("didz", None),
)
MONTHS = [
    fold(name)
    for name in (
        "Sausis Vasaris Kovas Balandis Gegužė Birželis Liepa Rugpjūtis Rugsėjis Spalis Lapkritis "
        "Gruodis"
    ).split()
]
# Lines above a table and in its first column that aren't headings: the title, notes.
NOT_HEADINGS = re.compile(
    r"^\*|grafik|\buab\b|rajono$|valdu|metams|tvirtinu|surinkimo diena|surinkimas|pavadinimas"
)
# A day, maybe with a note: "13", "6 (perkelta iš 01 d.)" (moved from the 1st).
_NOTE = re.compile(r"\([^()]*\)")


def _kind(text: str) -> tuple[bool, Kind | None]:
    folded = fold(text)
    for phrase, kind in KINDS:
        if phrase in folded:
            return True, kind
    return False, None


def _month(text: str | None) -> int | None:
    folded = fold(text or "").replace(" ", "")
    return MONTHS.index(folded) + 1 if folded in MONTHS else None


def _lines(cell: str | None) -> list[str]:
    """The lines of a cell, a word broken at a hyphen joined."""
    lines: list[str] = []
    for line in (cell or "").split("\n"):
        line = clean_text(line)
        if lines and re.search(r"\w-$", lines[-1]):
            lines[-1] += line
        elif line:
            lines.append(line)
    return lines


# A settlement's or a street's type, or a garden community: a line that names places.
_TYPED = re.compile(r"\b(?:k|vs|mstl|m|g|tak|skg|al|a|pr|skv|aklg|pl|vienk|vns|sen)\.|\bSB\b", re.I)


def _cell_text(cell: str | None) -> str:
    """A cell's text on one line. A first line that names no place but describes the list after
    it ("Kuršėnų miesto dalis, išskyrus Daugėlius, Pavenčius") ends with a colon."""
    lines = _lines(cell)
    if len(lines) > 1 and not _TYPED.search(lines[0]) and not lines[0].endswith((",", ";", ":")):
        lines[0] += ":"
    return " ".join(lines)


def heading_of(lines: list[str]) -> str | None:
    """The last line that is an eldership's or a town's name ("KURŠĖNŲ MIESTO SENIŪNIJA",
    "Kelmės miestas 1", "Žagarė"), in sentence case."""
    found = None
    for line in lines:
        if line and not NOT_HEADINGS.search(fold(line)) and not re.search(r"\d{4}", line):
            found = line
    if found and found.upper() == found:
        found = found[0] + found[1:].lower()
    return found


def _year(pdf, source: SourceFile) -> int:
    """The year in the file's title ("... 2026 METAMS", "Grafikas 2026 m."), which must agree
    with the year in its name, if any."""
    first = pdf.pages[0].extract_text() or ""
    titled = re.search(r"(?<!\d)(20\d{2})\s*(?:m\b|metams|metų)", first[:600], re.I)
    named = _year_in(source.file_name)
    if titled and named and int(titled.group(1)) != named:
        raise ValueError(f"{source.file_name}: the title says {titled.group(1)}, the name {named}")
    year = int(titled.group(1)) if titled else named
    if year is None:
        raise ValueError(f"{source.file_name}: no year in its title or name")
    return year


@dataclass
class _Block:
    """One place's table: its heading, the lines of its first column and its dates."""

    heading: str | None
    page: int
    lines: list[str] = field(default_factory=list)
    dates: dict[Kind, set[date]] = field(default_factory=lambda: defaultdict(set))
    months: list[int] = field(default_factory=list)

    @property
    def name(self) -> str:
        text = ""
        for line in self.lines:
            text += line if not text else (" " if re.search(r"[,;:]$", text) else ", ") + line
        return clean_text(text)


def _days(cell: str, year: int, month: int, where: str) -> set[date]:
    """ "13, 27", "1;15;29", "1; 15;29", "6 (perkelta iš 01 d.);15", ".25", and spaced out to
    fill the cell: "1 0 ; 2 5"."""
    text = _NOTE.sub(" ", cell).strip()
    if re.fullmatch(r"(?:\S\s)+\S", text):
        text = re.sub(r"\s", "", text)
    days: set[date] = set()
    for token in re.split(r"[\s,;]+", text):
        token = token.strip(".")
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"{where}: not a list of days in month {month}: {cell!r}")
        try:
            days.add(date(year, month, int(token)))
        except ValueError as error:
            raise ValueError(f"{where}: {token} of month {month}: {error}") from error
    return days


def parse_blocks(source: SourceFile, content: bytes) -> tuple[int, list[_Block]]:
    """The year and the places of one file. Strict: a place without its twelve months, dates
    that aren't days, a month column without a waste type raise ValueError."""
    blocks: list[_Block] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        year = _year(pdf, source)
        heading: str | None = None
        block: _Block | None = None
        columns: dict[int, Kind | None] = {}
        for page_no, page in enumerate(pdf.pages, start=1):
            where = f"{source.file_name} page {page_no}"
            words = page.extract_words()
            above = 0.0
            for table in page.find_tables():
                top, bottom = table.bbox[1], table.bbox[3]
                lines: dict[int, list[str]] = defaultdict(list)
                for word in words:
                    if above - 1 <= word["top"] and word["bottom"] <= top + 1:
                        lines[round(word["top"])].append(word["text"])
                heading = heading_of([" ".join(lines[k]) for k in sorted(lines)]) or heading
                above = bottom
                for row in table.extract():
                    cells = [c or "" for c in row]
                    kinds = {i: _kind(c) for i, c in enumerate(cells) if i and c.strip()}
                    if sum(1 for found, _ in kinds.values() if found) >= 2:
                        columns = {i: kind for i, (found, kind) in kinds.items() if found}
                        continue
                    months = {i: _month(cells[i]) for i in columns if i < len(cells)}
                    month = next((m for m in months.values() if m), None)
                    if month is None:
                        # A heading or a note in the first column, the months' titles, or
                        # nothing.
                        if not any(c.strip() for c in cells[1:]):
                            heading = heading_of(_lines(cells[0])) or heading
                        continue
                    if any(m != month for m in months.values()):
                        raise ValueError(f"{where}: months {sorted(months.values())} in one row")
                    if month == 1 and block and block.months:
                        blocks.append(_close(block, where))
                        block = None
                    if block is None:
                        if month != 1:
                            raise ValueError(f"{where}: a table starting with month {month}")
                        block = _Block(heading, page_no)
                    if block.months and month != block.months[-1] + 1:
                        raise ValueError(f"{where}: month {month} after {block.months[-1]}")
                    block.months.append(month)
                    if text := _cell_text(cells[0]):
                        block.lines.append(text)
                    for i, kind in columns.items():
                        if kind and i + 1 < len(cells) and cells[i + 1].strip():
                            block.dates[kind] |= _days(cells[i + 1], year, month, where)
                    if month == 12:
                        blocks.append(_close(block, where))
                        block = None
        if block:
            blocks.append(_close(block, source.file_name))
    return year, blocks


def _close(block: _Block, where: str) -> _Block:
    if block.months != list(range(1, 13)):
        raise ValueError(f"{where}: a table with months {block.months}")
    if not block.lines:
        raise ValueError(f"{where}: dates without places")
    return block


def _stem(word: str) -> str:
    return word[: max(4, len(word) - 2)]


def elderships_of(heading: str | None, municipality: Municipality | None = None) -> list[str]:
    """The elderships (register names) a heading names, in its order: "KURŠĖNŲ MIESTO
    SENIŪNIJA", "Saugėlaukio-Kepalių seniūnijos", "Kruopių ir Naujosios Akmenės
    kaimiškoji/miesto seniūnijos", "Kelmės miestas 1" (the town's eldership), "Žagarė". A name
    inside a longer one ("Kelmės" in "Kelmės apylinkių") doesn't count. Without
    `municipality`, those of the municipality the heading names most of."""
    words = fold(heading or "").split()
    found: dict[str, tuple[Municipality, list[tuple[int, int]], int]] = {}
    for place in [municipality] if municipality else MUNICIPALITIES:
        for name in sorted(place.elderships):
            stems = [_stem(w) for w in fold(name).split()]
            spans = []
            for start, word in enumerate(words):
                if not word.startswith(stems[0]):
                    continue
                end: int | None = start
                for stem in stems[1:]:
                    # The next word, or the one after it: "kaimiškoji/miesto".
                    end = next(
                        (
                            p
                            for p in (end + 1, end + 2)
                            if p < len(words) and words[p].startswith(stem)
                        ),
                        None,
                    )
                    if end is None:
                        break
                if end is not None:
                    spans.append((start, end))
            if spans:
                found[name] = (place, spans, len(stems))

    def inside(span: tuple[int, int], size: int) -> bool:
        return any(
            other_size > size and o[0] <= span[0] and span[1] <= o[1]
            for _, other_spans, other_size in found.values()
            for o in other_spans
        )

    names = [
        (spans[0][0], name, place)
        for name, (place, spans, size) in found.items()
        if not all(inside(span, size) for span in spans)
    ]
    counts = Counter(place.name for _, _, place in names)
    if not counts:
        return []
    chosen = counts.most_common(1)[0][0]
    return [name for _, name, place in sorted(names) if place.name == chosen]


def municipality_of(eldership: str) -> Municipality | None:
    return next((m for m in MUNICIPALITIES if eldership in m.elderships), None)


# --- the places and the Address Register -------------------------------------------------

# Item of a list: a settlement or a street with its type and house numbers ("Juškaičių II k.",
# "Ventos g. 2, 2A", "Taikos skv.", "Kivyliai").
_ITEM = re.compile(
    rf"(?P<name>.+?)(?:\s+(?P<numerals>{_NUMERALS}))?"
    r"(?:\s+(?P<type>k|vs|mstl|m|g|al|pl|skg|aklg|tak|a|skv|pr)\b\.?)?"
    r"(?:\s*(?P<houses>\d+\s*[A-Za-z]?(?:\s*[,;]\s*\d+\s*[A-Za-z]?)*))?",
    re.U,
)
# The centre's spellings, as the register writes them, and the lists' punctuation.
_FIXES = (
    (re.compile(r",,"), "„"),  # SB ,,Paventys"
    (re.compile(r"\bSB\s*,\s*"), "SB "),  # SB, „Ventos pakrantė“
    (re.compile(r"\s+gyventojų ir įmonių\b", re.I), ""),  # Ginkūnų k. gyventojų ir įmonių
    (re.compile(r"\bNr\.\s*"), ""),  # Ventos g. Nr. 2, 2A; Kareiviškio k. (Nr. 3, Nr. 4)
    (re.compile(r"\bmiestelis\b", re.I), "mstl."),
    (re.compile(r"\b(?:vienk|vns)\.", re.I), "vs."),
    (re.compile(r"\bg\.\s*st\.", re.I), "geležinkelio stotis"),  # Tytuvėnų g. st.
    (re.compile(r"\s\.k\b"), " k."),  # Keidų .k
    (re.compile(r"(?<=\w) K\.(?=[\s,;]|$)"), " k."),  # Jautmalkės II K.
    (re.compile(r"\.\.(?=\s)"), ".,"),  # Taikos g.. Vilties g.
    # A comma before the type: "Kryžbarko, k.", "Uolos, g.", "Kriukų, mstl."
    (re.compile(r"(?<=[^\W\d_])\s*,\s*(k|vs|mstl|m|g|tak|skg|al|a)\.(?=[\s,;]|$)"), r" \1."),
    (re.compile(r"\b(g|tak|skg|al|aklg)(?=\s*[,;]|\s*$)"), r"\1."),  # Azalijų tak, Serbentų
    (re.compile(rf"(?<=\w) - (?=[{_UPPER}])"), ", "),  # Naujoji Akmenė - Žagarės g.
    (re.compile(r"\b(k|vs|mstl|m)\.\s+(I{1,3})\.?(?=\s*[(,;]|\s*$)"), r"\2 \1."),  # Pamūšio k. III.
    # "Paitaičių k. išskyrus Guobų ir Liepų g.": as if in brackets; "(be Užupio g.)": without.
    (re.compile(r"\b(k|vs|mstl|m)\.\s+(i[sš]+kyrus\b[^,;()]*)"), r"\1. (\2)"),
    (re.compile(r"\(\s*be\s+", re.I), "(išskyrus "),
    # "Janaučių k. ir Paprūdžių k.", "Noreikių k. ir SB", "Gražuolių g. ir Draugystės g.": two
    # places. Not "Dariaus ir Girėno g." nor "Akmenės I ir III k.".
    (re.compile(rf"\b(k|vs|mstl|m|g)\.\s+ir\s+(?=(?!I{{1,3}}\b)[{_UPPER}])"), r"\1., "),
)
# Parts of lists that aren't homes or name no place: businesses, "individualūs namai",
# "Kolektyviniai sodai" (no name).
_NOT_HOMES = re.compile(r"(?i:\bindividual\w*\s+nam|\bįmon|\bkolektyvin\w*\s+sod)|\bUAB\b")
# Gardens: "SB „Kriešinė“", "Sodų bendrijos RASA ir STATYBININKAS".
_GARDEN_PART = re.compile(r"^(?:S\s*/?\s*B\b|sodų bendrij\w*)", re.I)
# Some houses of a street: "Uosių g. lyginiai namo numeriai" (even numbers).
_SIDE = re.compile(r"\s*\b(?:ne)?lyginiai\b.*$", re.I)


@dataclass(eq=False)
class _Place(_Stop):
    """What one place of the list says about one settlement; `some` without streets: only some
    of its houses ("Ilgviečių k. Nr. 1;5;7", "Kareiviškio k. (Nr. 3, Nr. 4)")."""

    some: bool = False

    def clauses(self, area_id: str) -> list[Clause]:
        if self.some and self.streets is None:
            return [Clause(area_id, None, extra=True)]
        return super().clauses(area_id)


class Blocks(SectionRoutes):
    """Reads one place of the centre's files: the list in its first column, under the heading
    of its eldership (Area.district):

        Kuršėnų kaimiškoji seniūnija   Daugėlių k., Gūragių k., ..., SB „Šilelis“
        Akmenės ir Ventos seniūnijos   Ventos k., Paeglesių k., Akmenės I ir III k., ...
        Kelmės miestas 2               Agrastų g., ..., Kooperacijos g. (2-44, 1-39), ...
        Šiaulių kaimiškoji seniūnija   Pailių k. (Trumpoji g., ...), Raizgių k. (Žaibo g., ...)
        Bubių seniūnija                Gervėnų k., Kužių sen. Jakštaičių k. ( SB „Vyšnia“)

    A settlement is looked up in the elderships of the heading, or of an eldership named in
    the list ("Kužių sen."); one named under another eldership of its municipality is the only
    one of that name there, unless another place of its kind lists it in its own eldership
    (then it's reported). Streets before any settlement are the town's of the heading
    (Kuršėnai, Joniškis, Kelmė); streets after a settlement, in brackets or not, are the only
    ones of the place; with house numbers or "(ne)lyginiai namo numeriai", the place is one more
    choice for that street; a settlement with house numbers only is one more choice for the
    settlement. Garden communities ("SB „Kriešinė“") are one more choice in the street list of
    the settlement before them, or in brackets after them.
    """

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.unknown: list[str] = []
        self.named: dict[str, set[int]] | None = None
        self.missing: dict[str, Counter[str]] = defaultdict(Counter)
        self.kind = ""
        self.towns = {s.district: s for s in index.registry.settlements if s.abbr == "m."}
        # Street names with "ir" in them ("Dariaus ir Girėno"), which aren't two streets.
        self.joined = {
            fold(t.name) for s in index.registry.settlements for t in s.streets if " ir " in t.name
        }

    # -- the text --------------------------------------------------------------------

    def normalise(self, text: str) -> str:
        text = clean_text(text)
        for written, registered in self.provider.aliases:
            text = text.replace(written, registered)
        for pattern, replacement in _FIXES + _SPELLINGS:
            text = pattern.sub(replacement, text)
        # "Guobų ir Liepų g.": two streets, unless a street is called so.
        text = re.sub(
            rf"\b({_WORD}) ir ({_WORD}) (g|skg|tak|al)\.",
            lambda m: (
                m.group(0)
                if any(fold(f"{m.group(1)} ir {m.group(2)}") in name for name in self.joined)
                else f"{m.group(1)} {m.group(3)}., {m.group(2)} {m.group(3)}."
            ),
            text,
        )
        # "Kuršėnų miesto dalis, išskyrus Daugėlius, Pavenčius: Aido g., ...": a description.
        segments = text.split(":")
        kept = [
            s
            for i, s in enumerate(segments)
            if i == len(segments) - 1 or _TYPED.search(s) or _SECTION.search(s)
        ]
        return ", ".join(s.strip(" ,") for s in kept if s.strip(" ,"))

    # -- the settlements -------------------------------------------------------------

    def prepare(self, areas: list[Area]) -> None:
        # Also counts the names not found in their elderships, per kind (find).
        self.missing = defaultdict(Counter)
        super().prepare(areas)

    def within(self, name: str, numbered: bool, elderships: list[str]) -> list[Settlement]:
        """Settlements of one name (or a near one) in the elderships."""
        key = fold(name)
        found: list[Settlement] = []
        for district in elderships:
            if numbered:
                # Only the same number: "Balnių I" is near "Balnių II" to Index.candidates.
                same = [s for s in self.index.by_name.get(key, []) if s.district == district]
                if not same and name.endswith(" I"):
                    plain = self.index.by_name.get(fold(name[:-2]), [])
                    same = [s for s in plain if s.district == district]
                found += same
            else:
                found += self.index.candidates(name, district, strict=True)
        if not found and numbered:
            # "Pamūšio k. III" for the only Pamūšis of the eldership.
            plain = fold(re.sub(r"\s+I{1,3}$", "", name))
            same = [
                s
                for s in self.index.registry.settlements
                if s.district in elderships
                and re.fullmatch(re.escape(plain) + r"(?: i{1,3})?", fold(s.genitive))
            ]
            found = same if len(same) == 1 else []
        return found

    def typo(self, name: str, elderships: list[str], start: int = 0) -> list[Settlement]:
        """The settlement of the elderships one letter off the name, if only one is; with
        `start`, only after the first letters ("Gegiedžvario" for Gegiedždvaris, not
        "Mikaičių" for Bikaičiai)."""
        key = fold(name)
        close = [
            s
            for s in self.index.registry.settlements
            if s.district in elderships
            and any(
                _one_off(key, form) and key[:start] == form[:start]
                for form in (fold(s.genitive), fold(s.name))
            )
        ]
        return close if len({s.code for s in close}) == 1 else []

    def find(self, name: str, numbered: bool, elderships: list[str]) -> list[Settlement]:
        """Settlements of one name in the elderships, then elsewhere in their municipality,
        then one letter off."""
        found = self.within(name, numbered, elderships)
        own = municipality_of(elderships[0])
        if not found and own and self.named is None:
            self.missing[self.kind][f"{own.name}|{fold(name)}"] += 1
        elif not found and own and self.missing[self.kind][f"{own.name}|{fold(name)}"] == 1:
            # Under another eldership of the municipality: the only one of that name that no
            # place of this kind lists in its own eldership, if one place lists it so.
            others = sorted(own.elderships - set(elderships))
            elsewhere = [
                s
                for s in self.within(name, numbered, others) or self.typo(name, others, 4)
                if s.code not in self.named[self.kind]
            ]
            found = elsewhere if len({s.code for s in elsewhere}) == 1 else []
        return list({s.code: s for s in found or self.typo(name, elderships)}.values())

    def settlements_in(
        self, name: str, numerals: str | None, kind: str | None, elderships: list[str]
    ) -> list[Settlement]:
        names = [f"{name} {n}" for n in re.findall(r"I{1,3}", numerals)] if numerals else [name]
        hits: list[Settlement] = []
        for one in names:
            found = self.find(one, bool(numerals), elderships)
            abbr = _SETTLEMENT_TYPES.get(kind or "")
            if abbr:
                # A village written as a town may be one ("Juodaičių mstl."); a town written as a
                # village ("Karklėnų k.") only if no place of this kind names it as a town:
                # "Gruzdžių vs." isn't Gruzdžiai mstl., which has a place of its own.
                wanted = {
                    "k.": ("k.", "vs."),
                    "vs.": ("vs.", "k."),
                    "m.": ("m.", "mstl."),
                    "mstl.": ("mstl.", "m.", "k.", "vs."),
                }[abbr]
                typed = next((t for a in wanted if (t := [s for s in found if s.abbr == a])), [])
                if not typed and abbr in ("k.", "vs.") and self.named is not None:
                    named = self.named[self.kind]
                    typed = [s for s in found if s.abbr == "mstl." and s.code not in named]
                found = typed
            hits += found
        return list({s.code: s for s in hits}.values())

    def streets(
        self, settlement: Settlement, part: str, name: str, kind: str | None, loose: bool = True
    ) -> set[str]:
        if kind in ("skv", "pr"):
            # Types typed_streets doesn't know: "Taikos skv.", "Nepriklausomybės pr.".
            found = streets_in(name, settlement, loose=True)
            typed = {
                street_key(t)
                for t in settlement.streets
                if street_key(t) in found and fold(t.abbr).startswith(kind)
            }
            return typed or found
        return super().streets(settlement, part, name, kind, loose)

    # -- the places ------------------------------------------------------------------

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        self.kind = area.kind
        elderships = elderships_of(area.district)
        if not elderships:
            self.unknown.append(f"{area.district}: no eldership of this heading")
            return [], False
        own = municipality_of(elderships[0])
        text = self.normalise(area.name)
        # "Kužių sen. Jakštaičių k.", "Žagarės seniūnija: Žvelgaičių k.": another eldership.
        sections: list[tuple[list[str], str]] = []
        start, current = 0, elderships
        for mark in _SECTION.finditer(text):
            named = elderships_of(mark.group(0), own)
            if not named:
                continue
            sections.append((current, text[start : mark.start()]))
            start, current = mark.end(), named
        sections.append((current, text[start:]))
        stops: list[_Place] = []
        for names, part in sections:
            stops += self.places(names, part, area.district or "")
        return [(s.settlement, c) for s in stops for c in s.clauses(area.id)], False

    def places(self, elderships: list[str], text: str, heading: str) -> list[_Place]:
        """The settlements, streets and gardens of one eldership's part of a list."""
        stops: list[_Place] = []
        current: list[_Place] = []  # the settlements the streets after them belong to
        last: list[tuple[_Place, set[str]]] = []  # the last street, for house numbers after it
        garden_before = False
        towns = {t.code: t for d in elderships if (t := self.towns.get(d))}
        town = next(iter(towns.values())) if len(towns) == 1 else None
        for part in _section_parts(text):
            if _NOT_HOMES.search(part):
                continue
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0].strip() if rest else None
            head = head.strip(" ,;:")
            if _GARDEN_PART.match(head) or (garden_before and re.fullmatch(r"[\"'“„”].+", head)):
                garden_before = True
                homes = [s.settlement for s in current] or ([town] if town else [])
                self.gardens(stops, current, homes, part, spec, elderships, heading)
                continue
            garden_before = False
            if _HOUSE.fullmatch(head):
                # "Knygnešių g. 4,5,6": more houses of that street, or of that settlement.
                for stop, keys in last:
                    stop.add(keys, houses=True)
                continue
            some = bool(_SIDE.search(head))
            head = _SIDE.sub("", head)
            match = _ITEM.fullmatch(head)
            if not match:
                self.unknown.append(f"{heading}: {head[:60]}")
                current, last = [], []
                continue
            name, numerals, kind = match.group("name", "numerals", "type")
            houses = bool(match.group("houses")) or some
            if spec and re.fullmatch(r"[\d\s,;\-–A-Za-z]*\d[\d\s,;\-–A-Za-z]*", spec):
                houses, spec = True, None  # "Kooperacijos g. (2-44, 1-39)", "(3, 4)"
            places: list[Settlement] = []
            if kind in _SETTLEMENT_TYPES or numerals or not (kind or houses):
                places = self.settlements_in(name, numerals, kind, elderships)
            if not places and kind not in _SETTLEMENT_TYPES:
                # A street of the settlement before it, or of the heading's town.
                targets = current
                if not targets and town:
                    targets = [
                        next((s for s in stops if s.settlement is town), None) or _Place(town)
                    ]
                loose = bool(kind or houses)
                found = [(t, self.streets(t.settlement, head, name, kind, loose)) for t in targets]
                if any(keys for _, keys in found):
                    last = [(t, keys) for t, keys in found if keys]
                    for target, keys in last:
                        target.add(keys, houses)
                        if target not in stops:
                            stops.append(target)
                    continue
            if not places:
                self.unknown.append(f"{heading}: {head[:60]}")
                if kind in _SETTLEMENT_TYPES or not (kind or houses):
                    # The streets after a settlement we don't know aren't the one's before it.
                    current, last = [], []
                continue
            current = [_Place(s, some=houses) for s in places]
            last = [(stop, set()) for stop in current] if houses else []
            stops += current
            if spec is not None:
                self.spec(current, spec)
                if any(g for g in re.split(r"[,;]", spec) if _GARDEN_PART.match(g.strip())):
                    homes = [s.settlement for s in current]
                    self.gardens(stops, current, homes, spec, None, elderships, heading, True)
        return stops

    def gardens(
        self,
        stops: list[_Place],
        current: list[_Place],
        homes: list[Settlement],
        part: str,
        spec: str | None,
        elderships: list[str],
        heading: str,
        only: bool = False,
    ) -> None:
        """Garden communities, one more choice in the street list of their settlement (`homes`:
        the one before them, or the town), or of the one in brackets after them ("SB
        „Švendrelis“ (Noreikių k.)"). `only`: the gardens in brackets after a settlement are all
        of it the place serves ("Jakštaičių k. ( SB „Vyšnia“)")."""
        if spec:
            match = _ITEM.fullmatch(spec.strip(" ,;:"))
            if match and match.group("type") in _SETTLEMENT_TYPES:
                homes = self.settlements_in(*match.group("name", "numerals", "type"), elderships)
        labels = []
        # "SB „Vingis ir Kražantė“", 'SB „Paventys" SB „Šilelis“', 'SB "Stipirkiai", "Ąžuolas"'.
        for piece in re.split(r",|\bir\b|\s(?=SB\b)", part.split("(")[0] if spec else part):
            text = piece.strip(" ,;:")
            text = re.sub(r"^(?:S\s*/?\s*B|sodų bendrij\w*)\s*", "", text, flags=re.I)
            text = text.strip(f" {_QUOTES}")
            if text:
                label = f"SB „{text[0].upper() + text[1:].lower() if text.isupper() else text}“"
                labels.append((variant_key(label), label))
        # A garden community that has become a village of its name ("SB „Stipirkiai“"): the
        # village, all of it.
        own = municipality_of(elderships[0])
        for key, label in list(labels):
            name = fold(label.removeprefix("SB „").removesuffix("“"))
            villages = [
                s
                for s in self.index.by_name.get(name, [])
                if own and s.district in own.elderships and fold(s.name) == name
            ]
            if len(villages) == 1:
                stops.append(_Place(villages[0]))
                labels.remove((key, label))
        if not labels:
            return
        if not homes:
            self.unknown.append(f"{heading}: {part[:60]}")
            return
        for settlement in homes:
            for key, label in labels:
                self.variants[settlement.code].setdefault(key, label)
            if only:
                for stop in current:
                    if stop.settlement is settlement and stop.streets is None and not stop.some:
                        stops.remove(stop)
            stops.append(_Place(settlement, streets={key for key, _ in labels}))


PROVIDER = Provider(
    id="siauliai",
    name="UAB „Šiaulių regiono atliekų tvarkymo centras“",
    url=PAGE_URL,
    elderships=frozenset().union(*(m.elderships for m in MUNICIPALITIES)),
    # Places the lists write in a way they can't be read: a street before its village, a
    # village's street in brackets before the village; and names spelled other than the
    # register's, too far off to be taken for typos (the register's of the same eldership).
    aliases=(
        ("Vijoklių g. Vinkšnėnai", "Vinkšnėnų k. Vijoklių g."),
        ("Jovarų k., (tik Užupio g., Linksmučių k.)", "Jovarų k., Linksmučių k. (Užupio g.)"),
        ("K.Vaitekūnog.", "K. Vaitekūno g."),
        ("Kraštinės g.", "Kraštinė g."),  # Kuršėnai; one letter off Krantinės g. too
        ("Lelyjų g.", "Lelijų g."),  # Joniškis
        ("Obelių g.", "Obelų g."),  # Kelmė
        ("Naujosios skg.", "Naujasis skg."),  # Kelmė
        ("Kontrimiškės k.", "Kantrimiškio k."),  # Kuršėnų kaimiškoji sen.
        ("Žvigių k.", "Žvigų k."),  # Kairių sen.
        ("Piežų k.", "Pėžų k."),  # Raudėnų sen.
        ("Pamiškuopio k.", "Pamiškaupio k."),  # Bubių sen.
        ("Dusių k.", "Dusų k."),  # Papilės sen.
        ("Čiunių k.", "Čiuinių k."),  # Papilės sen.
        ("Kazilų k.", "Kazylų k."),  # Kriukų sen.
        ("Vazgalo k.", "Vakzalo k."),  # Kriukų sen.
        ("Bildžių k.", "Bilžių k."),  # Skaistgirio sen.
        ("Vyčių k.", "Vičių k."),  # Tytuvėnų apylinkių sen.
        ("Rimšų k.", "Rimšių k."),  # Tytuvėnų apylinkių sen.
        ("Pakėviuko k.", "Pakėvukų k."),  # Vaiguvos sen.
        ("Rauklaukaukio k.", "Rauklaukio vs."),  # Linkuvos sen.
    ),
    reader=Blocks,
    kinds=("household", "packaging", "glass", "green", "food"),
)
# The 2026 files had 234 places, each with mixed waste, packaging and glass; 51 with green
# waste and Joniškio r.'s 5 with green and food waste. Far fewer means the format changed and
# the parser missed places (each file is also checked: Municipality.min_blocks).
MIN_AREAS: dict[Kind, int] = {
    "household": 190,
    "packaging": 190,
    "glass": 190,
    "green": 35,
    "food": 3,
}
# One file has every kind.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "packaging", "glass", "green", "food")
}
# The five municipalities had about 77,000 addresses in 2026.
MIN_ADDRESS_POINTS = 55_000


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The places of one municipality's file, a row per kind of waste each. Strict: see
    parse_blocks; a heading that names no eldership of the municipality, and too few places,
    raise ValueError."""
    municipality = BY_NAME.get(source.municipality)
    if municipality is None:
        raise ValueError(f"{source.file_name}: for no municipality we know")
    _, blocks = parse_blocks(source, content)
    if len(blocks) < municipality.min_blocks:
        raise ValueError(
            f"{source.file_name}: only {len(blocks)} places (expected {municipality.min_blocks})"
        )
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for block in blocks:
        where = f"{source.file_name} page {block.page}"
        if not elderships_of(block.heading, municipality):
            raise ValueError(
                f"{where}: {block.heading!r} isn't an eldership of {municipality.name}"
            )
        if not block.dates:
            raise ValueError(f"{where}: no dates for {block.name[:60]!r}")
        for kind, dates in block.dates.items():
            area = Area(kind, block.name, block.heading, provider=PROVIDER.id, dates=set(dates))
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{where}: {kind} of {block.name[:60]!r} is listed twice")
                existing.dates |= area.dates
    return ParseResult(areas=list(areas.values()), warnings=warnings)


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins next year's places to this year's, in place, per municipality and kind.

    Next year's files may word the places differently, so a place of next year that covers
    exactly the same streets and settlements as one place of this year gives it its dates. The
    rest is left out, with a warning, until its year starts and it becomes the schedule in
    force; places of earlier years are dropped. A municipality without next year's file in
    January keeps this year's places, with their last dates (select_files warns)."""
    reader = Blocks(Index(registry), PROVIDER, defaultdict(dict))
    warnings: list[str] = []
    groups: dict[tuple[str, Kind], dict[int, list[tuple[ParseResult, Area]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for source, result in parsed:
        for area in result.areas:
            groups[(source.municipality, area.kind)][min(area.dates).year].append((result, area))
    for (municipality, kind), years in groups.items():
        started = [year for year in years if year <= today.year]
        base = max(started) if started else min(years)
        current: dict[frozenset, list[Area]] = defaultdict(list)
        for _, area in years[base]:
            current[reader.signature(area)].append(area)
        for year in sorted(years):
            if year == base:
                continue
            signatures = {id(area): reader.signature(area) for _, area in years[year]}
            times = Counter(signatures.values())
            continued: set[int] = set()
            for result, area in years[year]:
                signature = signatures[id(area)]
                same = current.get(signature, [])
                # One place of each year, and places we recognise: anything else could give a
                # settlement the dates of another place.
                if year > base and signature and len(same) == 1 and times[signature] == 1:
                    same[0].dates |= area.dates
                    continued.add(id(same[0]))
                elif year > base:
                    warnings.append(
                        f"{municipality} {kind}: the {year} place {area.name[:60]!r} doesn't "
                        f"match one {base} place; its dates are left out until {year}"
                    )
                result.areas.remove(area)
            if year > base:
                warnings += [
                    f"{municipality} {kind}: the {base} place {area.name[:60]!r} has no dates "
                    f"for {year}"
                    for _, area in years[base]
                    if id(area) not in continued
                ]
    return warnings


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MIN_AREAS,
    sum(m.min_household_places for m in MUNICIPALITIES),
    FILE_KINDS,
    combine,
)


# --- the output ------------------------------------------------------------------


def fetch_registry() -> Registry:
    """The settlements and streets of the five municipalities."""
    return Registry(
        [s for m in MUNICIPALITIES for s in address_register.fetch(m.register[0]).settlements]
    )


def load_registry() -> tuple[Registry, str]:
    loaded = [snapshot.load_registry(m.registry_file) for m in MUNICIPALITIES]
    return Registry([s for r, _ in loaded for s in r.settlements]), min(t for _, t in loaded)


def fetch_points() -> list[address_points.AddressPoint]:
    """The address points of the five municipalities. The file of house numbers is the whole
    country's (57 MB): downloaded once."""
    numbers = address_points._download(address_points.NUMBERS_FILE)
    points: list[address_points.AddressPoint] = []
    for m in MUNICIPALITIES:
        code = m.register[1]
        geometry = address_points._download(f"adr_gra_{code}.json")
        points += address_points.parse(geometry, numbers, code)
    return points


def load_points() -> tuple[list[address_points.AddressPoint], str]:
    loaded = [snapshot.load_points(m.addresses_file) for m in MUNICIPALITIES]
    return [p for points, _ in loaded for p in points], min(t for _, t in loaded)


def check_municipalities(dataset: dict) -> None:
    """Each municipality's places must get mixed waste schedules: fewer means its file or its
    matching broke, which the totals could hide."""
    served: Counter[str] = Counter()
    for location in dataset["locations"]:
        municipality = municipality_of(location["district"])
        if municipality and "household" in location.get("schedule", {}):
            served[municipality.name] += 1
    for m in MUNICIPALITIES:
        if served[m.name] < m.min_household_places:
            raise build.ValidationError(
                f"{m.name}: only {served[m.name]} settlements got a household schedule "
                f"(expected at least {m.min_household_places})"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    args = parser.parse_args(argv)

    registry, registry_note = build.live_or_snapshot(
        "Address Register", fetch_registry, load_registry
    )
    points, points_note = build.live_or_snapshot("Address points", fetch_points, load_points)
    try:
        results = build.build_parts((SOURCE,), registry, date.today(), args.keep_days, None)
        dataset = build.merge_parts([(r.provider, r.part) for r in results], PAGE_URL)
        check_municipalities(dataset)
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
    title = "Šiaulių r., Akmenės r., Joniškio r., Kelmės r. and Pakruojo r. (Šiaulių RATC)"
    build.write_summary(dataset, results, notes, title, "sratc/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

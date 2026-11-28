"""Telšių regionas: schedules published by the regional waste centre, UAB „Telšių regiono
atliekų tvarkymo centras“ (TRATC), for Mažeikių r., Telšių r., Plungės r. and Rietavo sav.

Its page for each municipality links one spreadsheet per waste type and calendar year, agreed
with the companies that do the collecting (2026 in Mažeikių r.: UAB „Ecoservice“ mixed and
food waste, UAB „Virginijus ir Ko“ packaging and glass):

    2027-MKA-grafikas-MAZEIKIAI.xlsx              mixed household waste
    2027-bioskaidzios-atliekos-MAZEIKIAI.xlsx     food and green waste (one container)
    Mazeikiai_pakuociu-grafikas-_2026.xlsx        packaging and glass
    2027-Stambiagabariciu-grafikas-MAZEIKIAI.xlsx bulky waste: by registration, not read
    2026-misriu_KP_SP_viesinimui-07.xlsx          Telšių r.: mixed waste, packaging ("KP") and
                                                  glass ("SP") in one file
    Kopija-Plunge-2026-grafikas-003-3.xlsx        a name that says nothing: the title above its
                                                  table does ("... pakuočių ir stiklo atliekų
                                                  išvežimo paslaugos grafikas 2026 m.")
    2027-m.-indiv-bioskaidzios-grafikas-PLUNGE.xlsx
                                                  Plungės r.: food and green waste of private
                                                  houses
    2027-m.-daugiabuciai-bioskaidzios-grafikas-Plunge.xlsx
                                                  and of apartment buildings: not read (below)

Telšių r. publishes its green and food waste schedule only as a PDF, which isn't read.

A spreadsheet for apartment buildings alone ("daugiabučiai" in its name, not "indiv") is the
schedule of their shared containers: Plungės r. 2027 has one column, "Plungės miesto
daugiabučiai", with the months in rows and a day or a weekday rule ("1/sav pirmad.") for no
list of places. It is left out by its name, as bulky waste is, without a warning: a warning
about a file keeps its name, so it would come back with every year's file. Next to the file of
private houses of the same kind and year, it would otherwise be taken for a correction of it.

A sheet is a table of routes with the days of every month:

    Nr. | Maršrutas                              | Sausis | Vasaris | Kovas     | ...
    1   | Žagarėlės g. miesto sen., Neries g., ... | 5; 19  | 2; 16   | 2; 16; 30 | ...
    7   | Lendriškiai, Laižuva, Barystės, ...     | 11     | 8       | 8         | ...

Files with several waste types have a row per type and route (the next ones without the
route's text), told apart by a column "Atliekų rūšis" ("Pakuočių atliekos", "Stiklo pakuotė",
"Mišrios komunalinės atliekos") or "Atliekos" ("mišrios", "KP", "SP"). Routes of the shared
containers of apartment buildings (weekdays instead of dates, and no list of places) and of
businesses aren't read.

A route is a list of streets of the municipality's town and of villages (locations.RouteList),
or of the villages of each eldership after its name, "Šateikių sen.: Aleksandravo k., ..."
(locations.SectionRoutes): the mixed waste files of Plungės r. and Rietavo sav. Next year's
files appear in autumn with the routes renumbered and reworded: a route that covers the same
places as one of this year's continues it (combine).

The four municipalities are written to one <out>/schedule.json and <out>/addresses.json, in
the format of the Vilniaus r. files, a part (model.Provider) each: the app downloads one file
for the region, and a municipality whose build fails keeps its part of yesterday's file.
Run: python -m schedule_pipeline.tratc --out ../site/mazeikiu-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cache, partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import openpyxl

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .dates import WEEKDAY_NAMES, parse_month, parse_weekdays
from .locations import Index, MixedRoutes, RouteList, SectionRoutes
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold

PAGES = "https://tratc.lt/atlieku-surinkimo-grafikai/"
PAGE_URL = f"{PAGES}atlieku-surinkimo-grafikai-mazeikiai/"
# Yesterday's data, for the part of a municipality whose build fails today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/mazeikiu-r"
COMPANY = "UAB „Telšių regiono atliekų tvarkymo centras“"


@dataclass(frozen=True)
class Municipality:
    """What differs per municipality: its page, whom its schedules serve, and how much of
    them to expect."""

    provider: Provider
    register: tuple[str, int]  # the Address Register's name and code
    registry_file: Path
    addresses_file: Path
    # Fewer routes of a kind than this, this year or in next year's file, means the format
    # changed and the parser or the matching missed rows.
    min_areas: dict[Kind, int]
    # Settlements that must get a mixed waste schedule.
    min_household_places: int
    min_address_points: int
    label: str  # for the job summary
    # Kinds of schedule in a file of each kind, where a file has more than one.
    file_kinds: dict[Kind, tuple[Kind, ...]] = field(
        default_factory=lambda: {"packaging": ("packaging", "glass")}
    )


MAZEIKIAI = Municipality(
    Provider(
        id="mazeikiai",
        name=COMPANY,
        url=PAGE_URL,
        # Every eldership of the municipality (register names).
        elderships=frozenset(
            {
                "Laižuvos",
                "Mažeikių",
                "Mažeikių apylinkės",
                "Reivyčių",
                "Sedos",
                "Šerkšnėnų",
                "Tirkšlių",
                "Viekšnių",
                "Židikų",
            }
        ),
        route_town="Mažeikiai",
        kinds=("household", "packaging", "glass", "food"),
    ),
    snapshot.MAZEIKIAI_MUNICIPALITY,
    snapshot.MAZEIKIAI_REGISTRY_FILE,
    snapshot.MAZEIKIAI_ADDRESSES_FILE,
    # The 2026 and 2027 files had 21-22 mixed waste routes, 17 packaging and 17 glass routes
    # and 4 food waste routes (Mažeikiai town only), and gave a mixed waste schedule to 131 of
    # the 190 settlements.
    min_areas={"household": 15, "packaging": 12, "glass": 12, "food": 3},
    min_household_places=100,
    # About 19,900 addresses in 2026.
    min_address_points=10_000,
    label="Mažeikių r.",
)
TELSIAI = Municipality(
    Provider(
        id="telsiai",
        name=COMPANY,
        url=f"{PAGES}atlieku-surinkimo-grafikai-telsiai/",
        elderships=frozenset(
            {
                "Degaičių",
                "Gadūnavo",
                "Luokės",
                "Nevarėnų",
                "Ryškėnų",
                "Telšių miesto",
                "Tryškių",
                "Upynos",
                "Varnių",
                "Viešvėnų",
                "Žarėnų",
            }
        ),
        route_town="Telšiai",
        section_town="Telšiai",
    ),
    snapshot.TELSIAI_MUNICIPALITY,
    snapshot.TELSIAI_REGISTRY_FILE,
    snapshot.TELSIAI_ADDRESSES_FILE,
    # 2026: 20 routes, each with mixed waste, packaging and glass dates, which gave a mixed
    # waste schedule to 232 of the 393 settlements (16,100 of the 16,700 addresses).
    min_areas={"household": 15, "packaging": 15, "glass": 15},
    min_household_places=200,
    # About 16,700 addresses in 2026.
    min_address_points=9_000,
    label="Telšių r.",
    file_kinds={"household": ("household", "packaging", "glass")},
)
PLUNGE = Municipality(
    Provider(
        id="plunge",
        name=COMPANY,
        url=f"{PAGES}atlieku-surinkimo-grafikai-plunge/",
        elderships=frozenset(
            {
                "Alsėdžių",
                "Babrungo",
                "Kulių",
                "Nausodžio",
                "Paukštakių",
                "Platelių",
                "Plungės miesto",
                "Stalgėnų",
                "Šateikių",
                "Žemaičių Kalvarijos",
                "Žlibinų",
            }
        ),
        route_town="Plungė",
        section_town="Plungė",
        kinds=("household", "packaging", "glass", "food"),
    ),
    snapshot.PLUNGE_MUNICIPALITY,
    snapshot.PLUNGE_REGISTRY_FILE,
    snapshot.PLUNGE_ADDRESSES_FILE,
    # 2026: 12 mixed waste routes (13 in 2027), 13 packaging and 13 glass routes and 5 food
    # waste routes (Plungė and a few villages), which gave a mixed waste schedule to 185 of the
    # 201 settlements.
    min_areas={"household": 9, "packaging": 10, "glass": 10, "food": 3},
    min_household_places=150,
    # About 14,100 addresses in 2026.
    min_address_points=8_000,
    label="Plungės r.",
)
RIETAVAS = Municipality(
    Provider(
        id="rietavas",
        name=COMPANY,
        url=f"{PAGES}atlieku-surinkimo-grafikai-rietavas/",
        elderships=frozenset({"Daugėdų", "Medingėnų", "Rietavo", "Rietavo miesto", "Tverų"}),
        route_town="Rietavas",
        section_town="Rietavas",
    ),
    snapshot.RIETAVAS_MUNICIPALITY,
    snapshot.RIETAVAS_REGISTRY_FILE,
    snapshot.RIETAVAS_ADDRESSES_FILE,
    # 2026: 4 mixed waste, 4 packaging and 4 glass routes, which gave a mixed waste schedule
    # to 88 of the 108 settlements.
    min_areas={"household": 3, "packaging": 3, "glass": 3},
    min_household_places=60,
    # About 3,500 addresses in 2026.
    min_address_points=2_000,
    label="Rietavo sav.",
)
MUNICIPALITIES = (MAZEIKIAI, TELSIAI, PLUNGE, RIETAVAS)
PROVIDER = MAZEIKIAI.provider


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(href)


def _name_words(name: str) -> tuple[str, list[str]]:
    folded = fold(name.replace("_", " "))  # "2028_MKA_grafikas.xlsx"
    return folded, folded.split()


def is_bulky(name: str) -> bool:
    """Bulky waste ("stambiagabaritės", "DGA") is collected by registration and isn't read."""
    folded, words = _name_words(name)
    return "stambiagabar" in folded or "dga" in words


def for_apartment_blocks(name: str) -> bool:
    """A schedule of the shared containers of apartment buildings alone ("2027-m.-daugiabuciai-
    bioskaidzios-grafikas-Plunge.xlsx"): no list of places, so it isn't read (as the _SHARED
    routes aren't). Not one that is for private houses too ("indiv")."""
    folded, _ = _name_words(name)
    return "daugiabu" in folded and "indiv" not in folded


def left_out(name: str) -> bool:
    """A spreadsheet that isn't read, by its name, without a warning."""
    return is_bulky(name) or for_apartment_blocks(name)


def classify(name: str) -> Kind | None:
    """By file name, or by the title above a table. "MKA" is "mišrios komunalinės
    atliekos"."""
    folded, words = _name_words(name)
    if left_out(name):
        return None
    if "pakuo" in folded or "stikl" in folded:
        return "packaging"
    if "bio" in folded or "maist" in folded:
        return "food"
    if "misri" in folded or "mka" in words:
        return "household"
    return None


def file_year(name: str) -> int | None:
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", name)}
    return years.pop() if len(years) == 1 else None


def spreadsheets(html: str, page_url: str = PAGE_URL) -> list[tuple[str, str]]:
    """(url, file name) of the spreadsheets the page links to (the PDFs next to them are the
    same tables, harder to read)."""
    collector = _Links()
    collector.feed(html)
    found: dict[str, str] = {}
    for href in collector.links:
        url = urljoin(page_url, href)
        path = PurePosixPath(unquote(urlsplit(url).path))
        if path.suffix.lower() == ".xlsx" and "/uploads/" in path.as_posix():
            found.setdefault(url, path.name)
    return list(found.items())


def find_files(
    html: str, page_url: str = PAGE_URL, unknown: list[str] | None = None
) -> list[SourceFile]:
    """The schedule spreadsheets linked from the page, by their names. Names of spreadsheets
    that are no kind of schedule we know are added to `unknown`."""
    files: list[SourceFile] = []
    for url, name in spreadsheets(html, page_url):
        kind = classify(name)
        if kind is not None:
            files.append(SourceFile(kind=kind, url=url, file_name=name))
        elif unknown is not None and not left_out(name):
            unknown.append(name)
    return files


def classify_content(content: bytes) -> Kind | None:
    """By the title above the table of the first sheet that has one."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):  # not a spreadsheet
        return None
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        texts = [[clean_text(c) for c in row] for row in _visible_rows(sheet)]
        header = _month_row(texts)
        if header is not None:
            return classify(" ".join(c for row in texts[:header] for c in row if c))
    return None


def _uploaded(file: SourceFile) -> str:
    """ "2026/09" from ".../uploads/2026/09/name.xlsx": when the file was put on the site."""
    match = re.search(r"/uploads/(\d{4}/\d{2})/", file.url)
    return match.group(1) if match else ""


def select_files(files: list[SourceFile], today: date) -> tuple[list[SourceFile], list[str]]:
    """Per kind, the files of this year and later; if there are none, the newest one. Of two
    files for the same year (a correction linked next to the original), the one uploaded
    last, or linked last."""
    selected: list[SourceFile] = []
    warnings: list[str] = []
    for kind in sorted({f.kind for f in files}):
        years = {f.url: file_year(f.file_name) for f in files if f.kind == kind}
        mine = [f for f in files if f.kind == kind and years[f.url]]
        warnings += [
            f"{f.file_name}: no year in the file name; not read"
            for f in files
            if f.kind == kind and not years[f.url]
        ]
        running = [f for f in mine if years[f.url] >= today.year]
        if not running and mine:
            newest = max(years[f.url] for f in mine)
            running = [f for f in mine if years[f.url] == newest]
        if mine and today.year not in {years[f.url] for f in running}:
            warnings.append(f"no {kind} schedule for {today.year} on the page")
        for year in sorted({years[f.url] for f in running}):
            same = [f for f in running if years[f.url] == year]
            newest = max(enumerate(same), key=lambda item: (_uploaded(item[1]), item[0]))[1]
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer {kind} schedule for {year}"
                for f in same
                if f is not newest
            ]
            selected.append(newest)
    return selected, warnings


def download(
    municipality: Municipality, today: date, keep_days: int
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    page = municipality.provider.url
    html = http.get(page, timeout=60).decode("utf-8", errors="replace")
    files: list[SourceFile] = []
    fetched: dict[str, bytes] = {}
    warnings: list[str] = []
    for url, name in spreadsheets(html, page):
        kind = classify(name)
        if kind is None and not left_out(name):
            # A name that doesn't tell ("Kopija-Plunge-2026-grafikas-003-3.xlsx"): the title
            # of its table does. A new way of naming the files must not go unnoticed.
            fetched[url] = http.get(url, timeout=60)
            kind = classify_content(fetched[url])
            if kind is None:
                warnings.append(f"{name}: a spreadsheet of no kind we know; not read")
        if kind is not None:
            files.append(SourceFile(kind=kind, url=url, file_name=name))
    selected, select_warnings = select_files(files, today)
    sources = [(f, fetched.get(f.url) or http.get(f.url, timeout=60)) for f in selected]
    return sources, warnings + select_warnings


# --- the spreadsheets ----------------------------------------------------------


def parse_days(value: object) -> list[int]:
    """A month cell: 28, "5; 19", "3;31" or "3; 17;31", or 14.28, two days typed with a dot
    that the spreadsheet took for a number. Raises ValueError for anything else, so a format
    change fails loudly."""
    if value is None:
        return []
    if isinstance(value, bool | datetime | date):
        raise ValueError(f"unrecognised day list: {value!r}")
    if isinstance(value, int | float):
        two = re.fullmatch(r"(\d{1,2})\.(\d{2})", repr(value))
        if value == int(value):
            days = [int(value)]
        elif two and int(two[1]) < int(two[2]):
            days = [int(two[1]), int(two[2])]
        else:
            raise ValueError(f"unrecognised day list: {value!r}")
    else:
        compact = re.sub(r"\s+", "", str(value))
        if not compact:
            return []
        if not re.fullmatch(r"\d{1,2}([;,]\d{1,2})*[;,]?", compact):
            raise ValueError(f"unrecognised day list: {value!r}")
        days = [int(d) for d in re.split(r"[;,]", compact) if d]
    if not all(1 <= d <= 31 for d in days):
        raise ValueError(f"day out of range in {value!r}")
    return days


def _visible_rows(sheet) -> list[list[object]]:
    """Cell values, with hidden columns and rows emptied: the files of this publisher keep
    stale numbers in columns hidden from the reader."""
    hidden: set[int] = set()
    for dimension in sheet.column_dimensions.values():
        if dimension.hidden:
            hidden |= set(range(dimension.min or 0, (dimension.max or dimension.min or 0) + 1))
    hidden_rows = {i for i, dimension in sheet.row_dimensions.items() if dimension.hidden}
    return [
        [None if i in hidden or line in hidden_rows else value for i, value in enumerate(row, 1)]
        for line, row in enumerate(sheet.iter_rows(values_only=True), start=1)
    ]


def _month_row(texts: list[list[str]]) -> int | None:
    """The row of the months' names, at the top of the table."""
    return next(
        (i for i, row in enumerate(texts) if sum(1 for c in row if parse_month(c)) >= 6), None
    )


def _row_kind(text: str) -> Kind | None:
    folded = fold(text)
    if "stikl" in folded or folded == "sp":
        return "glass"
    if "pakuo" in folded or folded == "kp":
        return "packaging"
    if "misri" in folded:
        return "household"
    return None


# "Plungės m. daugiabučių namų kolektyvinės surinkimo aikštelės": the shared containers of
# apartment buildings, with weekdays ("TREČIADIENIAIS") or dates for no list of places.
_SHARED = re.compile(r"daugiabu|kolektyvin")
# "Plungės raj.sav. juridiniai asmenys (įmonės)": businesses.
_BUSINESSES = re.compile(r"juridin|\bimon")
# Notes in the route column under the table, without dates (Plungės r. 2027 food waste): "Prašome
# konteinerius išstumti iki 8 val. ryto. ...", "Raudonai pažymėti - perkeltas iš kito maršruto."
_NOTE = re.compile(r"(?:prasome|raudonai pazymet)")


def parse_sheet(
    rows: list[list[object]], kind: Kind, title: str, where: str, provider: str = PROVIDER.id
) -> ParseResult:
    texts = [[clean_text(c) for c in row] for row in rows]
    header = _month_row(texts)
    if header is None:
        return ParseResult(areas=[])
    months = [(i, m) for i, c in enumerate(texts[header]) if (m := parse_month(c))]
    if [m for _, m in months] != sorted({m for _, m in months}):
        raise ValueError(f"{where}: unexpected month columns {texts[header]}")
    above = " ".join(c for row in texts[: header + 1] for c in row)
    years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", f"{above} {title}") or re.findall(
        r"(?<!\d)(20\d{2})(?!\d)", where
    )
    if not years:
        raise ValueError(f"{where}: cannot tell the year")
    year = int(years[0])

    # The column titles are in the month row or, with merged cells, in the row above it.
    titles = [
        fold(" ".join(texts[r][i] for r in (header - 1, header) if r >= 0 and i < len(texts[r])))
        for i in range(max(len(row) for row in texts))
    ]
    name_col = next((i for i, t in enumerate(titles) if "marsrutas" in t), None)
    if name_col is None:
        raise ValueError(f"{where}: no route column in {texts[header]}")
    kind_col = next(
        (i for i, t in enumerate(titles) if "atlieku rusis" in t or t == "atliekos"), None
    )
    weekday_col = next((i for i, t in enumerate(titles) if "savaites diena" in t), None)

    areas: dict[str, Area] = {}
    warnings: list[str] = []
    route = ""
    previous: Area | None = None  # the row above
    skipping = False  # the rows of a route that isn't read
    for line_no, (row, cells) in enumerate(
        zip(rows[header + 1 :], texts[header + 1 :], strict=True), start=header + 2
    ):
        name = cells[name_col]
        if re.match(r"(PASTAB|SUDERINTA)", name) or fold(name).startswith("primename"):
            break
        if fold(name).startswith("kolektyvinio"):
            # Shared containers of apartment buildings: weekday rules for a list of houses.
            warnings.append(f"{where}: the rules for shared containers have no dates; not read")
            break
        values = [row[i] if i < len(row) else None for i, _ in months]
        if not name and not any(clean_text(v) for v in values):
            continue
        if name.isdigit():  # a row that numbers the columns
            continue
        if _NOTE.match(fold(name)) and not any(clean_text(v) for v in values):
            continue  # a note, not a route
        if name:
            shared = bool(_SHARED.search(fold(name)))
            skipping = shared or bool(_BUSINESSES.search(fold(name)))
            if shared:
                warnings.append(f"{where} row {line_no}: shared containers; not read")
        if skipping:
            continue
        row_kind = kind
        # A second line of the row above, for a second date in a month: the other cells are
        # merged with the row above (Plungės r. 2026: "28" over "20" in January).
        more = kind_col is not None and not name and not cells[kind_col] and previous is not None
        if more:
            row_kind = previous.kind
        elif kind_col is not None:
            found = _row_kind(cells[kind_col])
            if found is None:
                raise ValueError(f"{where} row {line_no}: unknown waste type {cells[kind_col]!r}")
            row_kind = found
        elif not name:
            raise ValueError(f"{where} row {line_no}: dates without a route")
        route = name or route
        if not route:
            raise ValueError(f"{where} row {line_no}: dates before the first route")
        area = Area(kind=row_kind, name=route, provider=provider)
        for (_, month), value in zip(months, values, strict=True):
            try:
                for day in parse_days(value):
                    area.dates.add(date(year, month, day))
            except ValueError as error:
                raise ValueError(f"{where} row {line_no}: {error}") from error
        if not area.dates:
            warnings.append(f"{where} row {line_no}: no dates for {route[:60]!r}")
            continue
        if weekday_col is not None:
            weekdays = parse_weekdays(cells[weekday_col])
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays[0]]
        existing = areas.setdefault(area.id, area)
        if existing is not area:
            if not more:
                warnings.append(f"{where} row {line_no}: {route[:60]!r} is listed twice")
            existing.dates |= area.dates
        previous = existing
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_file(source: SourceFile, content: bytes, provider: Provider = PROVIDER) -> ParseResult:
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    result = ParseResult(areas=[])
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        where = f"{source.file_name} [{sheet.title}]"
        rows = _visible_rows(sheet)
        parsed = parse_sheet(rows, source.kind, sheet.title, where, provider.id)
        result.areas += parsed.areas
        result.warnings += parsed.warnings
    if not result.areas:
        raise ValueError(f"{source.file_name}: no schedule table found")
    # The year is read from the sheet; the file was chosen by the year in its name.
    expected = file_year(source.file_name)
    found = {d.year for area in result.areas for d in area.dates}
    if expected and found != {expected}:
        raise ValueError(
            f"{source.file_name}: the dates are of {sorted(found)}, the file name says {expected}"
        )
    return result


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]],
    registry: Registry,
    today: date,
    municipality: Municipality = MAZEIKIAI,
) -> list[str]:
    """Joins next year's routes to this year's, in place.

    A place has one row per waste type, with all its dates. Next year's file words and numbers
    the routes differently, so its rows are other rows: one that covers exactly the same streets
    and settlements as a row of this year gives that row its dates. The rest is left out, with
    a warning, until its year starts and it becomes the schedule in force.

    Next year's file is checked now, not on 1 January when it takes over: too few routes in
    it raise ValueError."""
    provider = municipality.provider
    index, variants = Index(registry), defaultdict(dict)
    if provider.reader:
        # A reader of the provider's own (maatc.Routes).
        reader = provider.reader(index, provider, variants)
    else:
        reader = RouteList(index, provider, variants)
        if provider.section_town:
            reader = MixedRoutes(reader, SectionRoutes(index, provider, variants))
    warnings: list[str] = []
    by_kind: dict[Kind, dict[int, list[tuple[ParseResult, Area]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for _, result in parsed:
        for area in result.areas:
            by_kind[area.kind][min(area.dates).year].append((result, area))
    for kind, years in by_kind.items():
        started = [year for year in years if year <= today.year]
        base = max(started) if started else min(years)
        current: dict[frozenset, list[Area]] = defaultdict(list)
        for _, area in years[base]:
            current[reader.signature(area)].append(area)
        for year in sorted(years):
            if year == base:
                continue
            minimum = municipality.min_areas.get(kind, 0)
            if year > base and len(years[year]) < minimum:
                raise ValueError(
                    f"only {len(years[year])} {kind} routes in the {year} file "
                    f"(expected at least {minimum})"
                )
            signatures = {id(area): reader.signature(area) for _, area in years[year]}
            times = Counter(signatures.values())
            continued: set[int] = set()
            for result, area in years[year]:
                signature = signatures[id(area)]
                same = current.get(signature, [])
                # One route of each year, and places we recognise: anything else could give
                # a place the dates of another route.
                if year > base and signature and len(same) == 1 and times[signature] == 1:
                    same[0].dates |= area.dates
                    continued.add(id(same[0]))
                elif year > base:
                    warnings.append(
                        f"{kind}: the {year} route {area.name[:60]!r} doesn't match one "
                        f"{base} route; its dates are left out until {year}"
                    )
                result.areas.remove(area)
            if year > base:
                warnings += [
                    f"{kind}: the {base} route {area.name[:60]!r} has no dates for {year}"
                    for _, area in years[base]
                    if id(area) not in continued
                ]
    return warnings


def source(municipality: Municipality) -> build.Source:
    return build.Source(
        municipality.provider,
        partial(download, municipality),
        partial(parse_file, provider=municipality.provider),
        municipality.min_areas,
        municipality.min_household_places,
        municipality.file_kinds,
        partial(combine, municipality=municipality),
    )


SOURCE = source(MAZEIKIAI)


# --- the output ------------------------------------------------------------------


def _once(fetch, source: str, down: set[str]):
    """`fetch`, unless `source` already failed for another municipality (added to `down`): the
    register's sites block cloud servers such as GitHub Actions runners, and each try costs
    its retries."""

    def live():
        if source in down:
            raise OSError("unavailable for the municipality before; not tried again")
        try:
            return fetch()
        except OSError:
            down.add(source)
            raise

    return live


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    parser.add_argument(
        "--published",
        default=PUBLISHED_URL,
        help="site folder with yesterday's schedule.json, for a municipality whose build fails",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any municipality's build fails instead of keeping its published part",
    )
    args = parser.parse_args(argv)

    loader = None if args.strict else cache(build.load_published(args.published))
    results: list[build.PartResult] = []
    registries: list[tuple[Municipality, Registry]] = []
    points: list[address_points.AddressPoint] = []
    notes: list[str] = []
    down: set[str] = set()  # live sources that failed
    try:
        for municipality in MUNICIPALITIES:
            name, code = municipality.register
            registry, registry_note = build.live_or_snapshot(
                f"Address Register ({municipality.label})",
                _once(partial(address_register.fetch, name), "register", down),
                partial(snapshot.load_registry, municipality.registry_file),
            )
            found, points_note = build.live_or_snapshot(
                f"Address points ({municipality.label})",
                _once(partial(address_points.fetch, code), "points", down),
                partial(snapshot.load_points, municipality.addresses_file),
            )
            notes += [n for n in (registry_note, points_note) if n]
            registries.append((municipality, registry))
            points += found
            results += build.build_parts(
                (source(municipality),), registry, date.today(), args.keep_days, loader
            )
        dataset = build.merge_parts([(r.provider, r.part) for r in results if r.part], PAGES)
        served = {loc["id"] for loc in dataset["locations"]}
        everything = Registry([s for _, registry in registries for s in registry.settlements])
        addresses = address_points.build_addresses(
            points, everything, served, dataset["generatedAt"]
        )
        places = Counter(addresses["places"][point[2]][0] for point in addresses["points"])
        for municipality, registry in registries:
            count = sum(places[f"g{s.code}"] for s in registry.settlements)
            if any(r.part for r in results if r.provider == municipality.provider) and (
                count < municipality.min_address_points
            ):
                raise build.ValidationError(f"{municipality.label}: only {count} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
        if r.error:
            if r.part:
                kept = f"the data published on {r.part['generatedAt'][:10]} is kept"
            else:
                kept = "there is no published data to keep, so it is left out"
            # An annotation on the workflow run.
            print(f"::warning::The {municipality.label} build failed; {kept}. {r.error}")

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    # A section per municipality: the company's name is the same in each.
    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
        part = r.part or {"locations": [], "areas": []}
        title, file_name = f"{municipality.label} (TRATC)", f"{args.out.name}/schedule.json"
        build.write_summary(part, [r], [], title, f"{municipality.label} in {file_name}")
    build.write_summary(dataset, [], notes, "Telšių RATC", f"{args.out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

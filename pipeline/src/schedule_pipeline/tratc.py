"""Mažeikių rajonas: schedules published by the regional waste centre, UAB „Telšių regiono
atliekų tvarkymo centras“ (TRATC).

Its page for the municipality links one spreadsheet per waste type and calendar year, agreed
with the companies that do the collecting (2026: UAB „Ecoservice“ mixed and food waste, UAB
„Virginijus ir Ko“ packaging and glass):

    2027-MKA-grafikas-MAZEIKIAI.xlsx              mixed household waste
    2027-bioskaidzios-atliekos-MAZEIKIAI.xlsx     food and green waste (one container)
    Mazeikiai_pakuociu-grafikas-_2026.xlsx        packaging and glass
    2027-Stambiagabariciu-grafikas-MAZEIKIAI.xlsx bulky waste: by registration, not read

A sheet is a table of routes with the days of every month:

    Nr. | Maršrutas                              | Sausis | Vasaris | Kovas     | ...
    1   | Žagarėlės g. miesto sen., Neries g., ... | 5; 19  | 2; 16   | 2; 16; 30 | ...
    7   | Lendriškiai, Laižuva, Barystės, ...     | 11     | 8       | 8         | ...

The packaging file has two rows per route (the second without the route's text), told apart by
a column "Atliekų rūšis": "Pakuočių atliekos" and "Stiklo pakuotė".

A route is a list of streets of Mažeikiai or of villages; locations.RouteList links them to the
Address Register. Next year's files appear in autumn with the routes renumbered and reworded:
a route that covers the same places as one of this year's continues it (combine).

Writes <out>/schedule.json and <out>/addresses.json, in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.tratc --out ../site/mazeikiu-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import openpyxl

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .dates import WEEKDAY_NAMES, parse_month, parse_weekdays
from .locations import Index, RouteList
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold

PAGE_URL = "https://tratc.lt/atlieku-surinkimo-grafikai/atlieku-surinkimo-grafikai-mazeikiai/"
MUNICIPALITY = snapshot.MAZEIKIAI_MUNICIPALITY  # the register's name and code
PROVIDER = Provider(
    id="mazeikiai",
    name="UAB „Telšių regiono atliekų tvarkymo centras“",
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
)
# The 2026 and 2027 files had 21-22 mixed waste routes, 17 packaging and 17 glass routes and 4
# food waste routes (Mažeikiai town only), and gave a mixed waste schedule to 131 of the
# 190 settlements. Far fewer means the format changed and the parser or the matching missed
# rows.
MIN_AREAS: dict[Kind, int] = {"household": 15, "packaging": 12, "glass": 12, "food": 3}
MIN_HOUSEHOLD_PLACES = 100
# The packaging file also has the glass schedule.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}
# Mažeikių r. had about 19,900 addresses in 2026.
MIN_ADDRESS_POINTS = 10_000


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(href)


def classify(name: str) -> Kind | None:
    """By file name. "MKA" is "mišrios komunalinės atliekos"; bulky waste ("stambiagabaritės",
    "DGA") is collected by registration and isn't read."""
    folded = fold(name)
    words = folded.split()
    if "stambiagabar" in folded or "dga" in words:
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


def find_files(html: str, page_url: str = PAGE_URL) -> list[SourceFile]:
    """The schedule spreadsheets linked from the page (the PDFs next to them are the same
    tables, harder to read)."""
    collector = _Links()
    collector.feed(html)
    files: list[SourceFile] = []
    seen: set[str] = set()
    for href in collector.links:
        url = urljoin(page_url, href)
        path = PurePosixPath(unquote(urlsplit(url).path))
        kind = classify(path.name)
        if path.suffix.lower() != ".xlsx" or "/uploads/" not in path.as_posix():
            continue
        if kind is None or url in seen:
            continue
        seen.add(url)
        files.append(SourceFile(kind=kind, url=url, file_name=path.name))
    return files


def select_files(files: list[SourceFile], today: date) -> tuple[list[SourceFile], list[str]]:
    """Per kind, the files of this year and later; if there are none, the newest one."""
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
        selected += running
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, warnings = select_files(find_files(html), today)
    return [(f, http.get(f.url, timeout=60)) for f in files], warnings


# --- the spreadsheets ----------------------------------------------------------


def parse_days(value: object) -> list[int]:
    """A month cell: 28, "5; 19", "3;31" or "3; 17;31". Raises ValueError for anything else,
    so a format change fails loudly."""
    if value is None:
        return []
    if isinstance(value, bool | datetime | date):
        raise ValueError(f"unrecognised day list: {value!r}")
    if isinstance(value, int | float):
        if value != int(value):
            raise ValueError(f"unrecognised day list: {value!r}")
        days = [int(value)]
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
    """Cell values, with hidden columns emptied: the files of this publisher keep stale numbers
    in columns hidden from the reader."""
    hidden: set[int] = set()
    for dimension in sheet.column_dimensions.values():
        if dimension.hidden:
            hidden |= set(range(dimension.min or 0, (dimension.max or dimension.min or 0) + 1))
    return [
        [None if i in hidden else value for i, value in enumerate(row, start=1)]
        for row in sheet.iter_rows(values_only=True)
    ]


def _row_kind(text: str) -> Kind | None:
    folded = fold(text)
    if "stikl" in folded:
        return "glass"
    if "pakuo" in folded:
        return "packaging"
    return None


def parse_sheet(rows: list[list[object]], kind: Kind, title: str, where: str) -> ParseResult:
    texts = [[clean_text(c) for c in row] for row in rows]
    header = next(
        (i for i, row in enumerate(texts) if sum(1 for c in row if parse_month(c)) >= 6), None
    )
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
    kind_col = next((i for i, t in enumerate(titles) if "atlieku rusis" in t), None)
    weekday_col = next((i for i, t in enumerate(titles) if "savaites diena" in t), None)

    areas: dict[str, Area] = {}
    warnings: list[str] = []
    route = ""
    for line_no, (row, cells) in enumerate(
        zip(rows[header + 1 :], texts[header + 1 :], strict=True), start=header + 2
    ):
        name = cells[name_col]
        if re.match(r"(PASTAB|SUDERINTA)", name):
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
        row_kind = kind
        if kind_col is not None:
            found = _row_kind(cells[kind_col])
            if found is None:
                raise ValueError(f"{where} row {line_no}: unknown waste type {cells[kind_col]!r}")
            row_kind = found
        elif not name:
            raise ValueError(f"{where} row {line_no}: dates without a route")
        route = name or route
        if not route:
            raise ValueError(f"{where} row {line_no}: dates before the first route")
        area = Area(kind=row_kind, name=route, provider=PROVIDER.id)
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
            warnings.append(f"{where} row {line_no}: {route[:60]!r} is listed twice")
            existing.dates |= area.dates
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    result = ParseResult(areas=[])
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        where = f"{source.file_name} [{sheet.title}]"
        parsed = parse_sheet(_visible_rows(sheet), source.kind, sheet.title, where)
        result.areas += parsed.areas
        result.warnings += parsed.warnings
    if not result.areas:
        raise ValueError(f"{source.file_name}: no schedule table found")
    return result


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins next year's routes to this year's, in place.

    A place has one row per waste type, with all its dates. Next year's file words and numbers
    the routes differently, so its rows are other rows: one that covers exactly the same streets
    and settlements as a row of this year gives that row its dates. The rest is left out, with
    a warning, until its year starts and it becomes the schedule in force."""
    reader = RouteList(Index(registry), PROVIDER, defaultdict(dict))
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
            for result, area in years[year]:
                same = current.get(reader.signature(area), [])
                if year > base and len(same) == 1:
                    same[0].dates |= area.dates
                elif year > base:
                    warnings.append(
                        f"{kind}: the {year} route {area.name[:60]!r} covers other places than "
                        f"any {base} route; its dates are left out until {year}"
                    )
                result.areas.remove(area)
    return warnings


SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MIN_AREAS,
    MIN_HOUSEHOLD_PLACES,
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

    name, code = MUNICIPALITY
    registry, registry_note = build.live_or_snapshot(
        "Address Register",
        partial(address_register.fetch, name),
        partial(snapshot.load_registry, snapshot.MAZEIKIAI_REGISTRY_FILE),
    )
    points, points_note = build.live_or_snapshot(
        "Address points",
        partial(address_points.fetch, code),
        partial(snapshot.load_points, snapshot.MAZEIKIAI_ADDRESSES_FILE),
    )
    try:
        results = build.build_parts((SOURCE,), registry, date.today(), args.keep_days, None)
        dataset = build.merge_parts([(r.provider, r.part) for r in results], PAGE_URL)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < MIN_ADDRESS_POINTS:
            raise build.ValidationError(f"only {len(addresses['points'])} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    notes = [n for n in (registry_note, points_note) if n]
    build.write_summary(dataset, results, notes, "Mažeikių r. (TRATC)", "mazeikiu-r/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

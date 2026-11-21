"""Klaipėdos rajonas: schedules published by the municipality's waste administrator, VšĮ
„Gargždų švara“. The waste is collected by UAB „Ekonovus“.

Its page links one spreadsheet per calendar year with every kind of waste (2026: "Grafikai
2026/grafikas 2026.xlsx", 2025: "GRAFIKAI 2025/2025 MKA+AZ (1).xlsx"):

    Gyvenvietė                      | Mišrios kom. | Plastikas - popierius | Stiklas | Žaliosios
    Ablingos k.                     | 01-02,...    | 01-02,01-16,...       | 01-25,..| 04-10,...
    Aukštkiemių k. - tik Airių g.,  | 01-08,...    |                       |         |
    Dituvos k. (išskyrus Žiemos g.) |              | 01-05,01-19,...       |         |

A row is a settlement, or some of its streets (locations.SettlementRows); a cell lists the
days of the year as MM-DD. The year is in the file's address. Next year's file appears in
December: its rows continue this year's rows of the same text (combine).

Writes <out>/schedule.json and <out>/addresses.json, in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.gargzdu --out ../site/klaipedos-r
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from datetime import date
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import openpyxl

from . import addresses as address_points
from . import build, http, snapshot
from . import registry as address_register
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, fold
from .tratc import _visible_rows

PAGE_URL = "https://www.gargzdusvara.eu/komunaliniu-atlieku-tvarkymo-grafikai/"
MUNICIPALITY = snapshot.KLAIPEDOS_MUNICIPALITY  # the register's name and code
PROVIDER = Provider(
    id="klaipedos",
    name="VšĮ „Gargždų švara“",
    url=PAGE_URL,
    # Every eldership of the municipality (register names).
    elderships=frozenset(
        {
            "Agluonėnų",
            "Dauparų-Kvietinių",
            "Dovilų",
            "Endriejavo",
            "Gargždų",
            "Judrėnų",
            "Kretingalės",
            "Priekulės",
            "Sendvario",
            "Veiviržėnų",
            "Vėžaičių",
        }
    ),
    settlement_rows=True,
    kinds=("household", "packaging", "glass", "green"),
)
# The 2026 file had 319 mixed waste, 312 packaging, 311 glass and 298 green waste rows (2025:
# 324, 311, 311 and 314), and gave a mixed waste schedule to 280 of the 294 settlements. Far fewer
# means the format changed and the parser or the matching missed rows.
MIN_AREAS: dict[Kind, int] = {"household": 250, "packaging": 250, "glass": 250, "green": 240}
MIN_HOUSEHOLD_PLACES = 250
# One file has every kind.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "packaging", "glass", "green")
}
# Klaipėdos r. had about 64,000 addresses in 2026.
MIN_ADDRESS_POINTS = 40_000
# The column titles (folded) of each kind.
COLUMNS: dict[str, Kind] = {
    "misri": "household",
    "komunalin": "household",
    "plastik": "packaging",
    "popier": "packaging",
    "pakuo": "packaging",
    "stikl": "glass",
    "zali": "green",
}


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    """The links of a page, and its <base href>: the page links "uploads/..." relative to the
    site's root, not to the page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.base: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.links.append(href)
        elif tag == "base" and href and self.base is None:
            self.base = href


def file_year(url: str) -> int | None:
    """The year in the file's folder or name: ".../Grafikai 2026/grafikas 2026.xlsx"."""
    path = unquote(urlsplit(url).path)
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", path)}
    return years.pop() if len(years) == 1 else None


def find_files(html: str, page_url: str = PAGE_URL) -> list[SourceFile]:
    """The spreadsheets linked from the page."""
    collector = _Links()
    collector.feed(html)
    base = urljoin(page_url, collector.base) if collector.base else page_url
    files: list[SourceFile] = []
    for href in collector.links:
        url = urljoin(base, href)
        path = PurePosixPath(unquote(urlsplit(url).path))
        if path.suffix.lower() != ".xlsx" or "/uploads/" not in path.as_posix().lower():
            continue
        if all(f.url != url for f in files):
            files.append(SourceFile(kind="household", url=url, file_name=path.name))
    return files


def select_files(files: list[SourceFile], today: date) -> tuple[list[SourceFile], list[str]]:
    """The files of this year and later; if there are none, the newest one. Of two files for
    the same year, the one linked last (a correction put next to the original)."""
    warnings = [
        f"{f.file_name}: no year in its address; not read" for f in files if not file_year(f.url)
    ]
    by_year: dict[int, list[SourceFile]] = defaultdict(list)
    for file in files:
        if year := file_year(file.url):
            by_year[year].append(file)
    years = [year for year in by_year if year >= today.year] or sorted(by_year)[-1:]
    if by_year and today.year not in years:
        warnings.append(f"no schedule for {today.year} on the page")
    selected: list[SourceFile] = []
    for year in sorted(years):
        *older, newest = by_year[year]
        warnings += [
            f"{f.file_name}: not read, {newest.file_name} is linked after it for {year}"
            for f in older
        ]
        selected.append(newest)
    return selected, warnings


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, warnings = select_files(find_files(html), today)
    return [(f, http.get(f.url, timeout=60)) for f in files], warnings


# --- the spreadsheet -------------------------------------------------------------


def parse_dates(value: object, year: int) -> set[date]:
    """A cell: "01-02,01-16,01-30" or "08-22, 09-19". Raises ValueError for anything else, so a
    format change fails loudly."""
    if value is None:
        return set()
    if not isinstance(value, str):
        raise ValueError(f"unrecognised list of days: {value!r}")
    compact = re.sub(r"\s+", "", value)
    if not compact:
        return set()
    if not re.fullmatch(r"\d{1,2}-\d{1,2}(,\d{1,2}-\d{1,2})*,?", compact):
        raise ValueError(f"unrecognised list of days: {value!r}")
    days = set()
    for item in filter(None, compact.split(",")):
        month, day = (int(n) for n in item.split("-"))
        days.add(date(year, month, day))  # ValueError for "02-30"
    return days


def _column_kind(title: str) -> Kind | None:
    folded = fold(title)
    return next((kind for word, kind in COLUMNS.items() if word in folded), None)


def parse_sheet(rows: list[list[object]], year: int, where: str) -> ParseResult:
    texts = [[clean_text(c) for c in row] for row in rows]
    header = next(
        (i for i, row in enumerate(texts) if row and fold(row[0]).startswith("gyvenviet")), None
    )
    if header is None:
        return ParseResult(areas=[])
    columns: list[tuple[int, Kind]] = []
    for i, title in enumerate(texts[header][1:], start=1):
        if not title:
            continue
        kind = _column_kind(title)
        if kind is None:
            raise ValueError(f"{where}: unknown column {title!r}")
        columns.append((i, kind))
    if len({kind for _, kind in columns}) != len(columns):
        raise ValueError(f"{where}: two columns of the same kind in {texts[header]}")

    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for line_no, (row, cells) in enumerate(
        zip(rows[header + 1 :], texts[header + 1 :], strict=True), start=header + 2
    ):
        name = cells[0] if cells else ""
        values = [(kind, row[i] if i < len(row) else None) for i, kind in columns]
        if not name and not any(clean_text(v) for _, v in values):
            continue
        if not name:
            raise ValueError(f"{where} row {line_no}: dates without a place")
        found = False
        for kind, value in values:
            try:
                dates = parse_dates(value, year)
            except ValueError as error:
                raise ValueError(f"{where} row {line_no}: {error}") from error
            if not dates:
                continue
            found = True
            area = Area(kind=kind, name=name, provider=PROVIDER.id, dates=dates)
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{where} row {line_no}: {kind} of {name[:60]!r} is listed twice")
                existing.dates |= area.dates
        if not found:
            warnings.append(f"{where} row {line_no}: no dates for {name[:60]!r}")
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    year = file_year(source.url)
    if year is None:
        raise ValueError(f"{source.file_name}: no year in its address")
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    result = ParseResult(areas=[])
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        where = f"{source.file_name} [{sheet.title}]"
        parsed = parse_sheet(_visible_rows(sheet), year, where)
        result.areas += parsed.areas
        result.warnings += parsed.warnings
    if not result.areas:
        raise ValueError(f"{source.file_name}: no schedule table found")
    # Rows on two sheets (2025: one row was on a sheet of its own).
    merged: dict[str, Area] = {}
    for area in result.areas:
        existing = merged.setdefault(area.id, area)
        if existing is not area:
            result.warnings.append(
                f"{source.file_name}: {area.kind} of {area.name[:60]!r} is listed twice"
            )
            existing.dates |= area.dates
    result.areas = list(merged.values())
    return result


# --- this year and the next ------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Joins next year's rows to this year's, in place.

    A place has one row per waste type, with all its dates: a row of next year's file with the
    same text as one of this year's gives it its dates. A row worded differently could cover
    other streets, so it is left out, with a warning, until its year starts and its file
    becomes the schedule in force; rows of earlier years are dropped.

    Next year's file is checked now, not on 1 January when it takes over: too few rows in it
    raise ValueError."""
    warnings: list[str] = []
    by_year: dict[int, list[tuple[ParseResult, Area]]] = defaultdict(list)
    for _, result in parsed:
        for area in result.areas:
            by_year[min(area.dates).year].append((result, area))
    if not by_year:
        return warnings
    started = [year for year in by_year if year <= today.year]
    base = max(started) if started else min(by_year)
    current = {area.id: area for _, area in by_year[base]}
    for year in sorted(by_year):
        if year == base:
            continue
        if year > base:
            for kind, minimum in MIN_AREAS.items():
                count = sum(1 for _, area in by_year[year] if area.kind == kind)
                if count < minimum:
                    raise ValueError(
                        f"only {count} {kind} rows in the {year} file (expected at least {minimum})"
                    )
        continued: set[str] = set()
        for result, area in by_year[year]:
            if year > base:
                if area.id in current:
                    current[area.id].dates |= area.dates
                    continued.add(area.id)
                else:
                    warnings.append(
                        f"{area.kind}: the {year} row {area.name[:60]!r} isn't in the {base} file; "
                        f"its dates are left out until {year}"
                    )
            result.areas.remove(area)
        if year > base:
            warnings += [
                f"{area.kind}: the {base} row {area.name[:60]!r} has no dates for {year}"
                for area in current.values()
                if area.id not in continued
            ]
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
        partial(snapshot.load_registry, snapshot.KLAIPEDOS_REGISTRY_FILE),
    )
    points, points_note = build.live_or_snapshot(
        "Address points",
        partial(address_points.fetch, code),
        partial(snapshot.load_points, snapshot.KLAIPEDOS_ADDRESSES_FILE),
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
    title = "Klaipėdos r. (Gargždų švara)"
    build.write_summary(dataset, results, notes, title, "klaipedos-r/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Schedules of UAB „Nemėžio komunalininkas“, which serves 11 elderships of Vilniaus rajonas.

The company publishes one schedule per quarter on https://www.nkom.lt/kita.html, as PDFs printed
from spreadsheets (the .xlsx links answer 403):

    Grafikas mišrių 2026 (10-12).xlsx - 2026 (10-12).pdf     mixed household waste
    Grafikas pakuočių 2026 (10-12).xlsx - 2026 (10-12).pdf   packaging and glass

Household table, then a section for shared container sites ("bendro naudojimo konteinerių
aikštelės", mostly apartment buildings) with weekly rules instead of dates:

    Seniūnija | Vietovė                       | Sav. diena            | Spalis | Lapkritis | ...
    Nemėžio   | Daržininkai, Talkotiškės, ... | Kas antrą trečiadienį | 7, 21  | 4, 18     | ...
    Juodšilių | Juodšilių k. (Durpių g. 7, 10) | Trečiadieniais       |        |           | ...

Packaging table: three month columns for plastic, paper and metal packaging, three for glass:

    Seniūnija | Vietovė                                    | Spalis | ... | Spalis | ... | Maršr.
    Nemėžio   | Nemėžis (Draugystės g., ...), Kuprioniškės | 9      | ... | 1      | ... | NCY 897

A row names many settlements; locations.PlaceList links them to the Address Register.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import pdfplumber

from . import http
from .dates import (
    WEEKDAY_NAMES,
    assign_years,
    find_year,
    month_end,
    parse_month,
    parse_weekdays,
    weekly_dates,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import fold
from .xlsx_parser import DEFAULT_GROUP

PAGE_URL = "https://www.nkom.lt/kita.html"
PROVIDER = Provider(
    id="nemezio",
    name="UAB „Nemėžio komunalininkas“",
    url=PAGE_URL,
    # Register names. The other 12 elderships of the district are served by Nemenčinė.
    elderships=frozenset(
        {
            "Juodšilių",
            "Kalvelių",
            "Lavoriškių",
            "Marijampolio",
            "Medininkų",
            "Mickūnų",
            "Nemėžio",
            "Pagirių",
            "Rudaminos",
            "Rukainių",
            "Šatrininkų",
        }
    ),
    place_lists=True,
)
# Shared container sites; the app asks "house or apartment?" when a place has both kinds of row.
SHARED_GROUP = "Daugiabučiai namai"
# The October-December 2026 files had 143 household rows (89 for private houses), 45 packaging
# and 45 glass rows, and gave a household schedule to 352 of the 372 settlements of these
# elderships. Far fewer means the format changed and the parser or the matching missed rows.
MIN_AREAS: dict[Kind, int] = {"household": 100, "packaging": 30, "glass": 30}
MIN_HOUSEHOLD_PLACES = 300
# The packaging file also has the glass schedule.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"packaging": ("packaging", "glass")}


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.base: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "base" and href:
            self.base = href
        elif tag == "a" and href:
            self.links.append(href)


def classify(name: str) -> Kind | None:
    """By file name: "Grafikas mišrių ..." / "mišriu" is household waste, "pakuočių" /
    "pakuociu" packaging (with glass in the same file)."""
    folded = fold(name)
    if "stikl" in folded:
        return "glass"
    if "pakuo" in folded:
        return "packaging"
    if "misri" in folded or "buitin" in folded:
        return "household"
    return None


def file_period(name: str) -> tuple[date, date] | None:
    """ "Grafikas mišrių 2026 (10-12).pdf" -> 1 October to 31 December 2026."""
    match = re.search(r"(20\d{2})\s*\(\s*(\d{1,2})\s*-\s*(\d{1,2})\s*\)", name)
    if not match:
        return None
    year, first, last = (int(g) for g in match.groups())
    if not (1 <= first <= 12 and 1 <= last <= 12):
        return None
    return date(year, first, 1), month_end(year + (last < first), last)


def _ascii_url(url: str) -> str:
    """The page links to paths with spaces and Lithuanian letters, partly encoded."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(unquote(parts.path), safe="/()-_.~!$&'*+,;=:@")))


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[SourceFile], list[SourceFile]]:
    """Every schedule linked from the page: (PDFs, spreadsheets). Older quarters are linked as
    both; the spreadsheets answer 403, so only the PDFs can be read."""
    collector = _Links()
    collector.feed(html)
    base = urljoin(page_url, collector.base) if collector.base else page_url
    files: list[SourceFile] = []
    spreadsheets: list[SourceFile] = []
    seen: set[str] = set()
    for href in collector.links:
        url = _ascii_url(urljoin(base, href))
        path = PurePosixPath(unquote(urlsplit(url).path))
        kind = classify(path.name)
        if "/uploads/" not in path.as_posix() or kind is None or url in seen:
            continue
        seen.add(url)
        # Older files' names are decomposed (NFD): "š" as "s" + caron. The URL keeps them as
        # linked; the name is normalised for display and comparison.
        name = unicodedata.normalize("NFC", path.name)
        source = SourceFile(kind=kind, url=url, file_name=name)
        if path.suffix.lower() == ".pdf":
            files.append(source)
        elif path.suffix.lower() in (".xlsx", ".xls"):
            spreadsheets.append(source)
    return files, spreadsheets


def unreadable(
    pdfs: list[SourceFile], spreadsheets: list[SourceFile], today: date, keep_days: int
) -> list[str]:
    """Warnings about recent periods published only as a spreadsheet, which can't be read."""
    covered = {(f.kind, file_period(f.file_name)) for f in pdfs}
    cutoff = today - timedelta(days=keep_days)
    return [
        f"{f.file_name}: only published as a spreadsheet, which the site doesn't serve; not read"
        for f in spreadsheets
        if (period := file_period(f.file_name))
        and period[1] >= cutoff
        and (f.kind, period) not in covered
    ]


def select_files(
    files: list[SourceFile], today: date, keep_days: int
) -> tuple[list[SourceFile], list[SourceFile]]:
    """(required, optional): per kind, the newest period and the one running today are
    required; older periods that ended within `keep_days`, and files whose name has no period,
    are read if they can be downloaded."""
    required: list[SourceFile] = []
    optional: list[SourceFile] = []
    cutoff = today - timedelta(days=keep_days)
    for kind in sorted({f.kind for f in files}):
        mine = [f for f in files if f.kind == kind]
        periods = {f.url: file_period(f.file_name) for f in mine}
        newest = max((p[1] for p in periods.values() if p), default=None)
        for f in mine:
            period = periods[f.url]
            if period is None:
                optional.append(f)
            elif period[1] == newest or period[0] <= today <= period[1]:
                required.append(f)
            elif period[1] >= cutoff:
                optional.append(f)
    return required, optional


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, spreadsheets = find_files(html)
    warnings = unreadable(files, spreadsheets, today, keep_days)
    required, optional = select_files(files, today, keep_days)
    sources = [(f, http.get(f.url, timeout=60)) for f in required]
    for f in optional:
        try:
            sources.append((f, http.get(f.url, timeout=60)))
        except OSError as error:  # older quarters are sometimes not served (403)
            warnings.append(f"{f.file_name}: not downloaded ({error})")
    return sources, warnings


# --- the PDFs ----------------------------------------------------------------


def parse_days(text: str) -> list[int]:
    """ "7, 21", "2, 16,30" and the letter-spaced "1 3 , 2 7" (13 and 27). Raises ValueError for
    anything else, so a format change fails loudly."""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return []
    if not re.fullmatch(r"\d{1,2}(,\d{1,2})*,?", compact):
        raise ValueError(f"unrecognised day list: {text!r}")
    days = [int(d) for d in compact.strip(",").split(",")]
    if not all(1 <= d <= 31 for d in days):
        raise ValueError(f"day out of range in {text!r}")
    return days


def _is_free_text(row: list[str | None]) -> bool:
    """Titles and notes span the table: pdfplumber returns None for the merged cells."""
    return any(c is None for c in row[2:]) or not any(clean_text(c) for c in row[1:])


def _skip_note(cells: list[str]) -> bool:
    return bool(re.match(r"(DĖMESIO|PASTABA)\b", cells[0]))


def _year_of(file_name: str, texts: list[str]) -> int | None:
    for text in texts:
        if year := find_year(text):
            return year
    period = file_period(file_name)
    return period[0].year if period else None


def _month_columns(
    cells: list[str], year: int | None, file_name: str
) -> list[tuple[int, int, int]]:
    months = [(i, parse_month(c)) for i, c in enumerate(cells) if i > 1 and c]
    months = [(i, m) for i, m in months if m]
    if not months:
        return []
    if year is None:
        raise ValueError(f"{file_name}: month header before any year")
    # Two groups of the same months (packaging, glass): each starts again from the first year.
    columns: list[tuple[int, int, int]] = []
    group: list[tuple[int, int]] = []
    for i, m in months:
        if group and m == group[0][1]:
            columns += _with_years(group, year)
            group = []
        group.append((i, m))
    return columns + _with_years(group, year)


def _with_years(group: list[tuple[int, int]], year: int) -> list[tuple[int, int, int]]:
    years = assign_years([m for _, m in group], year)
    return [(i, y, m) for (i, m), y in zip(group, years, strict=True)]


def _check_period(columns: list[tuple[int, int, int]], file_name: str, warnings: list[str]) -> None:
    period = file_period(file_name)
    if period and columns:
        first, last = min(columns, key=lambda c: (c[1], c[2])), max(columns, key=lambda c: c[1:])
        if (first[1], first[2]) != (period[0].year, period[0].month) or (last[1], last[2]) != (
            period[1].year,
            period[1].month,
        ):
            warnings.append(f"{file_name}: the file name and the month columns disagree")


def _add_dates(
    area: Area, cells: list[str], columns: list[tuple[int, int, int]], where: str
) -> None:
    for col, year, month in columns:
        try:
            days = parse_days(cells[col] if col < len(cells) else "")
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from error
        for day in days:
            try:
                area.dates.add(date(year, month, day))
            except ValueError as error:
                raise ValueError(f"{where}: invalid date {year}-{month}-{day}") from error


def _apply_rule(area: Area, rule: str, period: tuple[date, date] | None) -> None:
    """ "Pirmadieniais, penktadieniais" is every Monday and Friday. "Kas antrą trečiadienį"
    doesn't say which weeks, so it's kept as text."""
    weekdays = parse_weekdays(rule)
    words = re.findall(r"\w+", rule.casefold())
    named = [w for w in words if parse_weekdays(w)]
    if weekdays and period and "kas" not in words and all(w.endswith("iais") for w in named):
        area.dates = weekly_dates(weekdays, *period)
        area.weekday = ", ".join(WEEKDAY_NAMES[w] for w in weekdays)
    else:
        area.note = rule or None


def parse_household(content: bytes, file_name: str = "") -> ParseResult:
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    texts: list[str] = []
    year = _year_of(file_name, [])
    columns: list[tuple[int, int, int]] = []  # month columns of the main table
    period: tuple[date, date] | None = file_period(file_name)
    group: str | None = None
    last_district = ""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for line_no, row in enumerate(table, start=1):
                    cells = [clean_text(c) for c in row]
                    where = f"{file_name} page {page_no} row {line_no}"
                    if not any(cells):
                        continue
                    if fold(cells[0]) == "seniunija":
                        if len(cells) < 3 or "diena" not in fold(cells[2]):
                            raise ValueError(f"{where}: unexpected header {cells}")
                        year = _year_of(file_name, texts) or year
                        found = _month_columns(cells, year, file_name)
                        if found:
                            columns = found
                            _check_period(columns, file_name, warnings)
                            first, last = columns[0], columns[-1]
                            period = (date(first[1], first[2], 1), month_end(last[1], last[2]))
                            group = DEFAULT_GROUP
                        else:
                            shared = "bendro naudojimo" in fold(" ".join(texts[-2:]))
                            group = SHARED_GROUP if shared else DEFAULT_GROUP
                        continue
                    if _is_free_text(row) or _skip_note(cells):
                        texts.append(" ".join(c for c in cells if c))
                        continue
                    if group is None:
                        raise ValueError(f"{where}: data row before the table header")
                    # A row continued from the previous page has no eldership.
                    district = cells[0] or (last_district if cells[1] else "")
                    name, rule = cells[1], cells[2]
                    if not district or not name:
                        warnings.append(f"{where}: row without eldership or place: {cells}")
                        continue
                    last_district = district
                    area = Area(
                        kind="household",
                        name=name,
                        district=district,
                        group=group,
                        provider=PROVIDER.id,
                    )
                    _add_dates(area, cells, columns, where)
                    if area.dates:
                        area.weekday = rule or None
                        _check_weekday(area, where, warnings)
                    else:
                        _apply_rule(area, rule, period)
                    if not area.dates and not area.note:
                        warnings.append(f"{where}: no dates for {name[:60]!r}")
                        continue
                    _merge_into(areas, area, where, warnings)
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def _check_weekday(area: Area, where: str, warnings: list[str]) -> None:
    expected = parse_weekdays(area.weekday or "")
    if len(expected) != 1:
        return
    wrong = sorted(d for d in area.dates if d.weekday() != expected[0])
    if wrong:
        listed = ", ".join(d.isoformat() for d in wrong)
        warnings.append(
            f"{where}: {area.name[:40]!r} is on {area.weekday} but has dates on other "
            f"weekdays: {listed}"
        )


def _merge_into(areas: dict[str, Area], area: Area, where: str, warnings: list[str]) -> None:
    """The same place listed twice (two containers with different rules): one row with the
    dates of both, so no pickup is missed."""
    existing = areas.get(area.id)
    if existing is None:
        areas[area.id] = area
        return
    warnings.append(f"{where}: {area.name[:60]!r} is listed twice; the dates of both are kept")
    existing.dates |= area.dates
    rules = [r for r in (existing.weekday, area.weekday) if r]
    existing.weekday = " / ".join(dict.fromkeys(rules)) or None
    existing.note = None if existing.dates else (existing.note or area.note)


def parse_packaging(content: bytes, file_name: str = "") -> ParseResult:
    """Packaging and glass: each row gives a packaging and a glass row of the same place."""
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    texts: list[str] = []
    group_kinds: dict[int, Kind] = {}  # first column of each waste-type group
    columns: dict[Kind, list[tuple[int, int, int]]] = {}
    skipping = False
    last_district = ""
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for line_no, row in enumerate(table, start=1):
                    cells = [clean_text(c) for c in row]
                    where = f"{file_name} page {page_no} row {line_no}"
                    if not any(cells) or skipping:
                        continue
                    if fold(cells[0]) == "seniunija":
                        if len(cells) > 1 and "diena" in fold(cells[1]):
                            # Apartment buildings: a weekday per eldership and codes such as
                            # "KP1" for "odd weeks of the month", with no places or dates.
                            warnings.append(
                                f"{where}: the packaging rules for apartment buildings have no "
                                "dates; not read"
                            )
                            skipping = True
                            continue
                        group_kinds = {
                            i: ("glass" if "stikl" in fold(c) else "packaging")
                            for i, c in enumerate(cells)
                            if i > 1 and "pakuot" in fold(c)
                        }
                        if not group_kinds:
                            raise ValueError(f"{where}: no waste types in header {cells}")
                        continue
                    if group_kinds and not columns and not cells[0] and not cells[1]:
                        year = _year_of(file_name, texts)
                        found = _month_columns(cells, year, file_name)
                        if not found:
                            raise ValueError(f"{where}: expected month names, got {cells}")
                        _check_period(found, file_name, warnings)
                        for col, y, m in found:
                            start = max(i for i in group_kinds if i <= col)
                            columns.setdefault(group_kinds[start], []).append((col, y, m))
                        continue
                    if _is_free_text(row) or _skip_note(cells):
                        texts.append(" ".join(c for c in cells if c))
                        continue
                    if not columns:
                        raise ValueError(f"{where}: data row before the table header")
                    # A row continued from the previous page has no eldership.
                    district = cells[0] or (last_district if cells[1] else "")
                    name = cells[1]
                    if not district or not name:
                        warnings.append(f"{where}: row without eldership or place: {cells}")
                        continue
                    last_district = district
                    found_any = False
                    for kind, kind_columns in columns.items():
                        area = Area(kind=kind, name=name, district=district, provider=PROVIDER.id)
                        _add_dates(area, cells, kind_columns, where)
                        if area.dates:
                            found_any = True
                            _merge_into(areas, area, where, warnings)
                    if not found_any:
                        warnings.append(f"{where}: no dates for {name[:60]!r}")
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    if source.kind == "household":
        return parse_household(content, source.file_name)
    return parse_packaging(content, source.file_name)

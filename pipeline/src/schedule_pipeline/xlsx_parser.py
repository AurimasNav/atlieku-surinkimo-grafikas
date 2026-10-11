"""Parses the household waste schedule spreadsheet.

Layout (one sheet, several sections):

    Seniūnija | Kaimai | Gatvė | Savaitės diena | Birželis | Liepa | ...
    Avižienių |        | Aleksandravas | Ketvirtadienis | 11 d., 25 d. | 9d., 23d., | ...

The first section (individual houses) lists exact days per month. A later section
(apartment buildings) has no month columns and describes the schedule as a rule,
e.g. "kiekvienas mėnesio pirmadienis, penktadienis".
"""

from __future__ import annotations

import io
from datetime import date

import openpyxl

from .dates import (
    WEEKDAY_NAMES,
    assign_years,
    find_year,
    month_end,
    parse_days,
    parse_month,
    parse_weekdays,
    weekly_dates,
)
from .model import Area, Kind, ParseResult, clean_text

DEFAULT_GROUP = "Individualūs namai"


def _group_for_title(title: str) -> str:
    return "Daugiabučiai namai" if "daugiabu" in title.casefold() else DEFAULT_GROUP


def parse_xlsx(content: bytes, kind: Kind, file_name: str = "") -> ParseResult:
    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    areas: list[Area] = []
    warnings: list[str] = []

    for sheet in workbook.worksheets:
        rows = [[clean_text(c) for c in row] for row in sheet.iter_rows(values_only=True)]
        year = find_year(sheet.title) or find_year(file_name)
        if year is None:
            raise ValueError(f"cannot determine year from sheet {sheet.title!r} / {file_name!r}")

        # Months of the main section; rule-based sections reuse them as their date range.
        period: tuple[date, date] | None = None
        month_cols: list[tuple[int, int, int]] = []  # (column, year, month)
        group = DEFAULT_GROUP
        district = ""
        last_text = ""
        in_table = False

        for line_no, row in enumerate(rows, start=1):
            first = row[0] if row else ""
            if first.casefold() == "seniūnija":
                in_table = True
                district = ""
                group = _group_for_title(last_text)
                months = [(i, parse_month(h)) for i, h in enumerate(row) if parse_month(h)]
                if months:
                    years = assign_years([m for _, m in months], year)
                    month_cols = [(i, y, m) for (i, m), y in zip(months, years, strict=True)]
                    first_col, last_col = month_cols[0], month_cols[-1]
                    period = (
                        date(first_col[1], first_col[2], 1),
                        month_end(last_col[1], last_col[2]),
                    )
                else:
                    month_cols = []
                continue

            non_empty = [c for c in row if c]
            if not non_empty:
                continue
            if len(non_empty) == 1 and first:
                # A free-text line: notes, or the title of the next section.
                last_text = first
                in_table = False
                continue
            if not in_table:
                continue

            if first:
                district = first
            name = " ".join(c for c in (row[1], row[2]) if c)
            weekday_text = row[3] if len(row) > 3 else ""
            if not name:
                continue
            if "nėra objektų" in weekday_text.casefold():
                continue

            area = Area(kind=kind, name=name, district=district or None, group=group)
            if month_cols:
                area.weekday = weekday_text or None
                for col, col_year, month in month_cols:
                    cell = row[col] if col < len(row) else ""
                    try:
                        days = parse_days(cell)
                    except ValueError as error:
                        raise ValueError(f"{file_name} row {line_no}: {error}") from error
                    for day in days:
                        try:
                            area.dates.add(date(col_year, month, day))
                        except ValueError:
                            warnings.append(
                                f"{file_name} row {line_no}: invalid date {col_year}-{month}-{day}"
                            )
                _check_weekday(area, file_name, line_no, warnings)
            else:
                _apply_rule(area, weekday_text, period, file_name, line_no, warnings)

            if not area.dates and not area.note:
                warnings.append(f"{file_name} row {line_no}: no dates for {name!r}")
                continue
            areas.append(area)

    return ParseResult(areas=areas, warnings=warnings)


def _check_weekday(area: Area, file_name: str, line_no: int, warnings: list[str]) -> None:
    expected = parse_weekdays(area.weekday or "")
    if len(expected) != 1:
        return
    wrong = sorted(d for d in area.dates if d.weekday() != expected[0])
    if wrong:
        listed = ", ".join(d.isoformat() for d in wrong)
        warnings.append(
            f"{file_name} row {line_no}: {area.name[:40]!r} is on {area.weekday} "
            f"but has dates on other weekdays: {listed}"
        )


def _apply_rule(
    area: Area,
    rule: str,
    period: tuple[date, date] | None,
    file_name: str,
    line_no: int,
    warnings: list[str],
) -> None:
    weekdays = parse_weekdays(rule)
    lowered = rule.casefold()
    if lowered.startswith("kiekvien") and weekdays and period:
        area.dates = weekly_dates(weekdays, *period)
        area.weekday = ", ".join(WEEKDAY_NAMES[w] for w in weekdays)
        return
    # "kas antras mėnesio antradienis" doesn't say which weeks, so we don't guess.
    area.note = rule or None
    warnings.append(f"{file_name} row {line_no}: kept as text, no exact dates: {rule!r}")

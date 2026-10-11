"""Parses the packaging and glass schedule PDFs.

Each page has a table:

    (header)                         | 2026 m.  |         |           |
    Seniūnijos pavadinimas (...)     | Atliekos | Spalio  | Lapkričio | Gruodžio
    Nemenčinės m. Bezdonių ...       | Pakuotė  | 1 d.    | 2 d.      | 1 d.

The header row repeats on most pages; rows on pages without it use the last header seen.
"""

from __future__ import annotations

import io
from datetime import date

import pdfplumber

from .dates import assign_years, find_year, parse_days, parse_month
from .model import Area, Kind, ParseResult, clean_text


def parse_pdf(content: bytes, kind: Kind, file_name: str = "") -> ParseResult:
    areas: list[Area] = []
    warnings: list[str] = []
    year = find_year(file_name)
    month_cols: list[tuple[int, int, int]] = []  # (column, year, month)

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                for row in table:
                    cells = [clean_text(c) for c in row]
                    if not any(cells):
                        continue

                    row_year = next((find_year(c) for c in cells if find_year(c)), None)
                    if row_year and not any(parse_month(c) for c in cells[1:]):
                        year = row_year
                        continue

                    months = [(i, parse_month(c)) for i, c in enumerate(cells) if i > 0]
                    months = [(i, m) for i, m in months if m]
                    if months:
                        if year is None:
                            raise ValueError(f"{file_name}: month header before any year")
                        years = assign_years([m for _, m in months], year)
                        month_cols = [(i, y, m) for (i, m), y in zip(months, years, strict=True)]
                        continue

                    name = cells[0]
                    if not name:
                        warnings.append(f"{file_name} page {page_no}: row without area: {cells}")
                        continue
                    if not month_cols:
                        raise ValueError(f"{file_name} page {page_no}: data row before header")

                    area = Area(kind=kind, name=name)
                    for col, col_year, month in month_cols:
                        cell = cells[col] if col < len(cells) else ""
                        try:
                            days = parse_days(cell)
                        except ValueError as error:
                            raise ValueError(f"{file_name} page {page_no}: {error}") from error
                        for day in days:
                            area.dates.add(date(col_year, month, day))
                    if not area.dates:
                        warnings.append(f"{file_name} page {page_no}: no dates for {name[:60]!r}")
                        continue
                    areas.append(area)

    return ParseResult(areas=areas, warnings=warnings)

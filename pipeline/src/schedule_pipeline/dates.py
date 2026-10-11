"""Lithuanian month/weekday names and the date formats used in the schedules."""

from __future__ import annotations

import re
from datetime import date, timedelta

# Prefixes match both nominative ("Spalis") and genitive ("Spalio") forms.
_MONTH_PREFIXES = {
    "saus": 1,
    "vasar": 2,
    "kov": 3,
    "baland": 4,
    "geguž": 5,
    "birž": 6,
    "liep": 7,
    "rugpj": 8,
    "rugs": 9,
    "spal": 10,
    "lapkr": 11,
    "gruod": 12,
}

# Monday = 0. "pim" covers a typo seen in the source ("pimadienis").
_WEEKDAY_PREFIXES = {
    "pirm": 0,
    "pim": 0,
    "antrad": 1,
    "treč": 2,
    "ketv": 3,
    "penkt": 4,
    "šešt": 5,
    "sekm": 6,
}

WEEKDAY_NAMES = [
    "Pirmadienis",
    "Antradienis",
    "Trečiadienis",
    "Ketvirtadienis",
    "Penktadienis",
    "Šeštadienis",
    "Sekmadienis",
]


def parse_month(text: str) -> int | None:
    word = text.strip().casefold()
    for prefix, month in _MONTH_PREFIXES.items():
        if word.startswith(prefix):
            return month
    return None


def parse_weekdays(text: str) -> list[int]:
    """Finds all weekday names in a phrase like "kiekvienas mėnesio pirmadienis, penktadienis"."""
    found = []
    for word in re.findall(r"\w+", text.casefold()):
        for prefix, weekday in _WEEKDAY_PREFIXES.items():
            if word.startswith(prefix) and weekday not in found:
                found.append(weekday)
    return found


def parse_days(text: str) -> list[int]:
    """Parses day lists like "1d., 15d., 29d., " or the letter-spaced PDF form "1 5 d .".

    Returns an empty list for empty cells. Raises ValueError for text that isn't a day list,
    so format changes fail loudly instead of silently dropping dates.
    """
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return []
    if not re.fullmatch(r"(\d{1,2}d\.?,?)+", compact):
        raise ValueError(f"unrecognised day list: {text!r}")
    days = [int(d) for d in re.findall(r"(\d{1,2})d", compact)]
    for day in days:
        if not 1 <= day <= 31:
            raise ValueError(f"day out of range in {text!r}")
    return days


def find_year(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\s*m\b", text)
    return int(match.group(1)) if match else None


def assign_years(months: list[int], first_year: int) -> list[int]:
    """Gives each month column a year, rolling over when a schedule crosses New Year."""
    years = []
    year = first_year
    previous = None
    for month in months:
        if previous is not None and month < previous:
            year += 1
        years.append(year)
        previous = month
    return years


def weekly_dates(weekdays: list[int], start: date, end: date) -> set[date]:
    result = set()
    day = start
    while day <= end:
        if day.weekday() in weekdays:
            result.add(day)
        day += timedelta(days=1)
    return result


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)

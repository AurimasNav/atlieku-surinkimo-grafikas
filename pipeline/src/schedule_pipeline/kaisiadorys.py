"""Kaišiadorių rajonas: the schedules of SĮ „Kaišiadorių paslaugos“ (kaisiadoriupaslaugos.lt),
which empties the containers of the whole municipality since 16 November 2026: mixed waste,
packaging, glass and green waste. Until then UAB „Švara ID“ did, whose containers were in Kauno
švara's open-data file (svara.py read Kaišiadorių r. from it); the company took over for three
months, or until a tender picks the next operator.

Its schedules page is a WordPress plugin („tobalt-waste“) that asks the site for the year's data
as JSON: the page has a nonce (`var tobaltWaste = {"ajaxUrl": ..., "nonce": ...}`), and

    POST /wp-admin/admin-ajax.php  action=tobalt_waste_get_data&nonce=<nonce>&year=2026

answers (403 without the nonce)

    {"success": true, "data": {
      "year": 2026,
      "wasteTypes": [{"id": 1, "name": "Mišrios atliekos", ...}, ...],
      "locations": [{"id": 1125, "name": "Navasodų k.", "seniunija_name": "Kaišiadorių
                     apylinkės", "display_name": ..., "lat": ..., "lng": ...}, ...],
      "schedules": {"1125": {"1": {"1": [8, 22], "2": [5, 19], ...}, "3": {...}}, ...}}}

`schedules` is location id -> waste type id -> month -> days of the year asked for (an empty
list, not an object, when the year has none). The waste types are read by their names (KINDS):
mixed waste, packaging (paper, plastic and metal), glass and green waste; it has no food waste
yet, although food waste is collected in the towns since 23 November 2026. A type of another
name is left out, with a warning. Each location with a schedule is a row of each waste type it
has, with the eldership the data gives it (the register's names). This year and the next are
read (and last year in January, while its dates are kept), so next year's dates are read on the
day they appear; the site asks for at most one page every 10 seconds (robots.txt), so the
requests wait for each other. A year whose data has no schedules is left out.

The places (Rows, as locations.SettlementRows reads one settlement a row):

    Navasodų k.                                     a village of the row's eldership
    Anglinikų k., Vadžionių k., Anupravos k         typos, if one village of it is that close
    Vaidžionys, Žuvys, Lomeniai, Palomenės          a village in the nominative (or genitive)
    Mankuviškių k.                                  the villages numbered after it (I, II)
    Užtakų k. (Nedėjos g.)                          only these streets
    Užtakų k. (išskyrus Nedėjos g.).                the rest of the village
    Rumšiškių miestelis, Žiežmarių miestas          the towns (mstl., m.)
    Žaslių g., Liepų al., Geležinkeliečių takas     streets of Kaišiadorys (its eldership)
    Visos Žiežmarių seniūnijos gyvenamosios         every settlement of an eldership that no row
      vietovės; Kaišiadorių apylinkės               names: a fallback

A street of Kaišiadorys whose rows of a kind all have the dates of the town's row needs none
of its own (the app doesn't ask for the street); only the streets with other dates keep theirs.

Strict to the row's eldership: a village the row's eldership hasn't ("Mičiūnų k." of Paparčių)
is a warning, as is a garden community without an eldership (SB „Marios“) and a street
Kaišiadorys hasn't. Rows that aren't homes (cemeteries, the shared semi-underground containers)
are left out, with one warning that names them. A place two rows name the same way gets one of
them if their dates are the same ("Vaidžionys" and "Vadžionių k."); with other dates the app
asks which, and a warning says so. Rows of one name and eldership are one row with the dates of
both (Kaišiadorys has some streets twice).

Strict: a page without the nonce, an answer that isn't the year's data, a date that doesn't
exist and too few rows or places fail the build; the daily job then keeps yesterday's folder.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.kaisiadorys --out ../site/kaisiadoriu-r
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from . import build, http, maatc, raseiniai, snapshot
from .dates import WEEKDAY_NAMES
from .locations import _ROW_HEAD, Clause, Index, SettlementRows, _typo, typed_streets
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

PAGE_URL = "https://www.kaisiadoriupaslaugos.lt/kaisiadoriu-atlieku-isvezimo-grafikai/"
COMPANY = "SĮ „Kaišiadorių paslaugos“"
LABEL = "Kaišiadorių r."
ACTION = "tobalt_waste_get_data"
# robots.txt: Crawl-delay: 10.
CRAWL_DELAY = 10
# The elderships of the municipality (register names), as the data names them.
ELDERSHIPS = frozenset(
    {
        "Kaišiadorių apylinkės",
        "Kaišiadorių miesto",
        "Kruonio",
        "Nemaitonių",
        "Palomenės",
        "Paparčių",
        "Pravieniškių",
        "Rumšiškių",
        "Žaslių",
        "Žiežmarių",
        "Žiežmarių apylinkės",
    }
)
# The town whose rows are streets: its eldership has no other settlement.
TOWN_ELDERSHIP = "Kaišiadorių miesto"
# The waste types by the words of their names (folded): "Mišrios atliekos", "Popierius/plastikas/
# metalas", "Stiklo pakuotės", "Biologiškai skaidžios (žaliosios)".
KINDS: tuple[tuple[str, Kind], ...] = (
    ("misri", "household"),
    ("popier", "packaging"),
    ("plastik", "packaging"),
    ("stikl", "glass"),
    ("zaliosios", "green"),
    ("biologiskai skaid", "green"),
    ("maist", "food"),
)
# One file a year with every kind.
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "packaging", "glass", "green")
}
# Rows that aren't homes: cemeteries, the shared semi-underground containers, the washing of the
# containers.
_NOT_HOMES = re.compile(r"(?i:\bkapin\w*|\bpusiau\s+požemin\w*|\bplovim\w*|\bdezinfek\w*)")
# "Visos Žiežmarių seniūnijos gyvenamosios vietovės": every settlement of the eldership.
_WHOLE_ELDERSHIP = re.compile(r"Visos\s+(?P<name>.+?)\s+seniūnijos\s+gyvenamosios\s+vietovės", re.I)
# The rows' spellings, as the register writes them: "Rumšiškių miestelis", "Kaišiadorių
# miestas", "Anupravos k" (no dot), a trailing dot after a bracket.
_SPELLINGS = (
    (re.compile(r"\bmiestelis\b", re.I), "mstl."),
    (re.compile(r"\bmiestas\b", re.I), "m."),
    (re.compile(r"\b(k|vs|mstl|m)$"), r"\1."),
    (re.compile(r"\)\s*\.$"), ")"),
)
_TAG = re.compile(r"var\s+tobaltWaste\s*=\s*(\{.*?\});", re.S)


class Year(SourceFile):
    """The data of one year, as the site answers it."""

    def __init__(self, year: int, url: str):
        super().__init__("household", url, f"{year} m. atliekų išvežimo grafikai")
        self.year = year


@dataclass(frozen=True)
class _Tag:
    ajax_url: str
    nonce: str


def read_tag(html: str) -> _Tag:
    """The address and nonce the page's script asks the data with."""
    match = _TAG.search(html)
    if not match:
        raise ValueError(f"{PAGE_URL}: no tobaltWaste settings on the page")
    settings = json.loads(match.group(1))
    if not settings.get("nonce") or not settings.get("ajaxUrl"):
        raise ValueError(f"{PAGE_URL}: tobaltWaste has no nonce or ajaxUrl")
    return _Tag(settings["ajaxUrl"], settings["nonce"])


def years(today: date, keep_days: int) -> list[int]:
    """The years to read: this one and the next, and last year while its dates are kept."""
    return list(range((today - timedelta(days=keep_days)).year, today.year + 2))


def _get(url: str) -> bytes:
    return http.get(url, timeout=60)


def _post(url: str, form: dict[str, str]) -> bytes:
    return http.post(url, form, timeout=60)


def _wait(seconds: float) -> None:
    time.sleep(seconds)


def download(
    today: date,
    keep_days: int,
    get: Callable[[str], bytes] | None = None,
    post: Callable[[str, dict[str, str]], bytes] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The data of each year that has schedules (years); a year without is left out."""
    get, post, sleep = get or _get, post or _post, sleep or _wait
    tag = read_tag(get(PAGE_URL).decode("utf-8"))
    sources: list[tuple[SourceFile, bytes]] = []
    for year in years(today, keep_days):
        sleep(CRAWL_DELAY)
        content = post(tag.ajax_url, {"action": ACTION, "nonce": tag.nonce, "year": str(year)})
        if _data(content, year)["schedules"]:
            sources.append((Year(year, PAGE_URL), content))
    if not sources:
        raise build.ValidationError(
            f"no schedules for {', '.join(map(str, years(today, keep_days)))}"
        )
    return sources, []


def _data(content: bytes, year: int) -> dict:
    answer = json.loads(content)
    data = answer.get("data") if isinstance(answer, dict) else None
    if not answer.get("success") or not isinstance(data, dict):
        raise ValueError(f"the data of {year}: not a successful answer: {content[:200]!r}")
    if int(data.get("year", 0)) != year:
        raise ValueError(f"the data of {year}: the answer is of {data.get('year')}")
    for key in ("locations", "wasteTypes", "schedules"):
        if not isinstance(data.get(key), list | dict):
            raise ValueError(f"the data of {year}: no {key}")
    return data


def kind_of(name: str) -> Kind | None:
    folded = fold(name)
    return next((kind for words, kind in KINDS if words in folded), None)


def _weekday(dates: set[date]) -> str | None:
    days = {d.weekday() for d in dates}
    return WEEKDAY_NAMES[days.pop()] if len(days) == 1 else None


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of one year: a row per location and waste type, with its dates."""
    assert isinstance(source, Year)
    data = _data(content, source.year)
    schedules = data["schedules"] or {}
    if not isinstance(schedules, dict):
        raise ValueError(f"the data of {source.year}: schedules isn't an object")
    types = {str(t["id"]): t["name"] for t in data["wasteTypes"]}
    locations = {str(loc["id"]): loc for loc in data["locations"]}
    warnings: list[str] = []
    unknown_types = sorted(
        {types.get(t, t) for by in schedules.values() for t in by if not kind_of(types.get(t, t))}
    )
    warnings += [f"waste type „{name}“ isn't read" for name in unknown_types]
    areas: list[Area] = []
    not_homes: list[str] = []
    for location_id, by_type in schedules.items():
        location = locations.get(location_id)
        if location is None:
            raise ValueError(
                f"the data of {source.year}: a schedule of no location ({location_id})"
            )
        name = clean_text(location["name"])
        district = clean_text(location.get("seniunija_name")) or None
        if _NOT_HOMES.search(name):
            not_homes.append(name + (f" ({district} sen.)" if district else ""))
            continue
        for type_id, months in by_type.items():
            kind = kind_of(types.get(type_id, type_id))
            if not kind:
                continue
            dates = set()
            for month, days in months.items():
                for day in days:
                    try:
                        dates.add(date(source.year, int(month), int(day)))
                    except ValueError as error:
                        raise ValueError(
                            f"{name}: day {day} of {source.year}-{month} ({error})"
                        ) from error
            if dates:
                areas.append(
                    Area(
                        kind=kind,
                        name=name,
                        district=district,
                        weekday=_weekday(dates),
                        dates=dates,
                        provider=PROVIDER_ID,
                    )
                )
    if not_homes:
        warnings.append("rows that aren't homes left out: " + "; ".join(sorted(set(not_homes))))
    return ParseResult(areas, warnings)


# --- the places ------------------------------------------------------------------


class Rows(SettlementRows):
    """Reads the rows' places (see the module's docstring), strict to the row's eldership."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        super().__init__(index, provider, variants)
        self.district: str | None = None
        self.found: dict[str, tuple[list[tuple[Settlement, Clause]], list[str]]] = {}
        # Rows another row says all of, with the same dates: skipped, not unlinked.
        self.same: set[str] = set()

    def settlements(self, name: str, abbr: str | None) -> list[Settlement]:
        """The settlements of the row's eldership of that name (nominative or genitive), those
        numbered after it ("Mankuviškių k.": Mankuviškės I and II), or the one name a typo is
        close to."""
        key = fold(name)
        places = [s for s in self.places if s.district == self.district]
        hits = [s for s in places if key in (fold(s.genitive), fold(s.name))]
        if not hits:
            numbered = re.compile(re.escape(key) + r" i{1,3}")
            hits = [s for s in places if numbered.fullmatch(fold(s.genitive))]
        if not hits:
            near = [s for s in places if _typo(key, fold(s.genitive)) or _typo(key, fold(s.name))]
            if len({s.genitive for s in near}) == 1:
                hits = near
        typed = [s for s in hits if abbr and s.abbr == f"{abbr}."]
        return typed or hits

    def eldership(self, text: str) -> str | None:
        """The eldership a row of a whole eldership names: "Visos Žiežmarių seniūnijos
        gyvenamosios vietovės", "Kaišiadorių apylinkės" (the row's own: "Žiežmarių
        apylinkės" of Žiežmarių sen. is the town's)."""
        if match := _WHOLE_ELDERSHIP.fullmatch(text):
            text = match["name"]
        elif not text.endswith(" apylinkės"):
            return None
        named = next((d for d in self.provider.elderships if fold(d) == fold(text)), None)
        return self.district if named and self.district else named

    def read(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], list[str]]:
        """What a row says about which places, and the parts of it that are no place we know
        (none for a row that names no place at all: build_locations warns about it)."""
        self.unknown = []
        text = clean_text(area.name)
        for pattern, replacement in _SPELLINGS:
            text = pattern.sub(replacement, text)
        self.district = area.district if area.district in self.provider.elderships else None
        if eldership := self.eldership(text):
            places = [s for s in self.places if s.district == eldership]
            return [(s, Clause(area.id, None, fallback=True)) for s in places], []
        if not self.district:
            return [], []
        if self.district == TOWN_ELDERSHIP and not _ROW_HEAD.match(text):
            (town,) = [s for s in self.places if s.district == TOWN_ELDERSHIP]
            streets = typed_streets(text, town)
            return ([(town, Clause(area.id, streets))] if streets else []), []
        head = _ROW_HEAD.match(text)
        if not head:
            # "Vaidžionys", "Palomenės": a village without its type.
            return [(s, Clause(area.id, None)) for s in self.settlements(text, None)], []
        hits = self.settlements(head.group("name"), head.group("type"))
        spec = text[head.end() :].strip(" -–:")
        found = [(s, c) for s in hits for c in self.row_clauses(area, s, spec, False)]
        return found, list(self.unknown)

    def prepare(self, areas: list[Area]) -> None:
        """Reads every row, and keeps one of the rows of a kind that say the same about a place
        with the same dates ("Vaidžionys" and "Vadžionių k.", "Kaišiadorių apylinkės" and
        "Visos Kaišiadorių apylinkės seniūnijos gyvenamosios vietovės"). A street whose rows
        all have the dates of its settlement's row (most streets of Kaišiadorys) needs none of
        its own: the app doesn't ask for the street then."""
        self.found = {area.id: self.read(area) for area in areas}
        self.same = set()
        whole: dict[tuple, set[frozenset]] = defaultdict(set)
        by_street: dict[tuple, set[frozenset]] = defaultdict(set)
        for area in areas:
            for settlement, clause in self.found[area.id][0]:
                place = (area.kind, settlement.code)
                if clause.streets is None and not clause.excluded:
                    whole[place].add(frozenset(area.dates))
                for key in clause.streets or ():
                    by_street[(*place, key)].add(frozenset(area.dates))
        kept: dict[tuple, str] = {}
        for area in areas:
            found, unknown = self.found[area.id]
            mine = []
            for settlement, clause in found:
                place = (area.kind, settlement.code)
                if clause.streets and len(whole[place]) == 1:
                    streets = {
                        key for key in clause.streets if by_street[(*place, key)] != whole[place]
                    }
                    if not streets:
                        continue
                    clause = replace(clause, streets=streets)
                streets = frozenset(clause.streets) if clause.streets is not None else None
                key = (*place, streets, clause.fallback, clause.excluded, frozenset(area.dates))
                if kept.setdefault(key, area.id) == area.id:
                    mine.append((settlement, clause))
            if found and not mine:
                self.same.add(area.id)
            self.found[area.id] = (mine, unknown)

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        found, unknown = self.found.get(area.id) or self.read(area)
        self.unknown = unknown
        return found, area.id in self.same


def twice(areas: list[Area], registry: Registry) -> list[str]:
    """Warnings about places that rows of a kind with other dates name the same way: the app
    asks which."""
    reader = Rows(Index(registry), PROVIDER, defaultdict(dict))
    reader.prepare(areas)
    names: dict[tuple, list[str]] = defaultdict(list)
    for area in areas:
        for settlement, clause in reader.found[area.id][0]:
            # A row of a whole settlement; rows of streets (Kaišiadorys) are other streets.
            if clause.fallback or clause.streets is not None:
                continue
            place = (settlement.name, settlement.abbr, settlement.district, settlement.code)
            names[(area.kind, *place)].append(area.name)
    return [
        f"{name} {abbr} ({district} sen.) is named by {len(rows)} {kind} rows: "
        + "; ".join(sorted(rows))
        for (kind, name, abbr, district, _), rows in sorted(names.items())
        if len(rows) > 1
    ]


def combine(
    parsed: list[tuple[SourceFile, ParseResult]], registry: Registry, today: date
) -> list[str]:
    """Warns about the places rows of the newest year with other dates name the same way, with
    the dates the build keeps (the daily job's 31 days). Rows of one name of every year are one
    (build.merge_areas)."""
    current = build.current_rows(parsed, today)
    areas = [replace(a, dates=set(a.dates)) for _, r in parsed for a in r.areas]
    areas = build.drop_old_dates(build.merge_areas(areas), today - timedelta(KEEP_DAYS), current)
    return twice([a for a in areas if a.id in current], registry)


# The days of old dates the daily job keeps (main's --keep-days).
KEEP_DAYS = 31


PROVIDER_ID = "kaisiadorys"
PROVIDER = Provider(
    id=PROVIDER_ID,
    name=COMPANY,
    url=PAGE_URL,
    elderships=ELDERSHIPS,
    kinds=("household", "packaging", "glass", "green", "food"),
    reader=Rows,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.KAISIADORIU_MUNICIPALITY,
    snapshot.KAISIADORIU_REGISTRY_FILE,
    snapshot.KAISIADORIU_ADDRESSES_FILE,
    min_areas={"household": 200, "packaging": 200, "glass": 200},
    min_household_places=200,
    min_address_points=10_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)
SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MUNICIPALITY.min_areas,
    MUNICIPALITY.min_household_places,
    FILE_KINDS,
    combine,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days",
        type=int,
        default=KEEP_DAYS,
        help="drop pickup dates older than this many days",
    )
    args = parser.parse_args(argv)
    # The folder of one provider, as raseiniai.py builds its own; a build that fails writes
    # nothing (the daily job keeps yesterday's folder).
    return raseiniai.run(args.out, args.keep_days, None, MUNICIPALITY, lambda _: SOURCE)


if __name__ == "__main__":
    raise SystemExit(main())

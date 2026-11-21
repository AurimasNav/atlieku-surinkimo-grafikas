"""Kauno rajonas: schedules from the open-data file of UAB „Kauno švara“.

The company shares one CSV with every container it empties (nine municipalities, ~390k rows,
refreshed nightly). A row is one container at one address with its next pickup date and how
often it is emptied:

    Kauno r. sav.;Ringaudų sen.;Karkiškių k.;Ganyklų g.;2;52-MK-042246;2026-11-25;
    kas 14 dienų;Mišrios komunalinės   (one line in the file)

Only a few hundred distinct schedules hide behind the tens of thousands of containers, so the
output is the same shape as for Nemenčinė: a short list of schedules ("areas") with dates, and
an index from address to schedules. The index is split by eldership (seniūnija), because the
app only needs the user's own.

The file writes one place in several ways ("Akademija" and "Akademijos mstl.", "Vynuogyno" and
"Vynuogyno g.", "S. Žukausko g." and "Silvestro Žukausko g."), and lists the containers of one
building under several house numbers (house 8 has the food bin, flats 8-1 and 8-2 the mixed
ones). Spellings of one place are merged under the spelling most addresses use, checked
against the Address Register, and every address gets the containers of its building. The other
spellings stay in the address files as hidden aliases, so addresses saved under them keep
working. The list of towns gives each town its name in the Address Register too
("Akademijos mstl." is "Akademija"), which is what people type in the search.

Writes <out>/schedule.json and <out>/addresses/<eldership>.json. Run:
    python -m schedule_pipeline.svara --out ../site/kauno-r
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import snapshot
from .addresses import AddressPoint
from .http import ATTEMPTS, USER_AGENT
from .model import SCHEMA_VERSION, clean_text
from .registry import ATTRIBUTION, Registry, Settlement, fold

# The anonymous sharing link of the file, and the download address of the same document.
SHARE_URL = (
    "https://kaunosvara.sharepoint.com/:x:/s/Atviriduomenys/"
    "IQAoxJ77_IFQTqsKRL7G5bhvAQS-Vo2yqMaFOgJerhsreP8"
)
DOWNLOAD_URL = (
    "https://kaunosvara.sharepoint.com/sites/Atviriduomenys/_layouts/15/download.aspx"
    "?UniqueId=fb9ec428-81fc-4e50-ab0a-44bec6e5b86f"
)
PROVIDER = {
    "id": "kauno-svara",
    "name": "UAB „Kauno švara“",
    "url": "https://grafikai.svara.lt/",
}
MUNICIPALITY = "Kauno r. sav."

KINDS = {
    "Mišrios komunalinės": "household",
    "Maistinės atliekos": "food",
    "Žaliosios atliekos": "green",
    "Antrinės žaliavos": "packaging",
    "Antrinės žaliavos (popierius/plastikas)": "packaging",
    "Antrinės žaliavos (pakuotės)": "packaging",
    "Antrinės žaliavos (popierius)": "packaging",
    "Antrinės žaliavos (stiklas)": "glass",
}
MONTHS = {
    "sausį": 1,
    "vasarį": 2,
    "kovą": 3,
    "balandį": 4,
    "gegužę": 5,
    "birželį": 6,
    "liepą": 7,
    "rugpjūtį": 8,
    "rugsėjį": 9,
    "spalį": 10,
    "lapkritį": 11,
    "gruodį": 12,
}
WEEKDAYS = {
    "pirmadienį",
    "antradienį",
    "trečiadienį",
    "ketvirtadienį",
    "penktadienį",
    "šeštadienį",
    "sekmadienį",
}

# Dates are calculated this far ahead. The file is read again every day, so the phase of every
# schedule is always taken from its real next date.
HORIZON_DAYS = 180
KEEP_DAYS = 31
# Fewer than this in Kauno r. means the file or its format changed (2026: 63k rows, 39k addresses).
MIN_ROWS = 30_000
MIN_ADDRESSES = 20_000
# Share of rows whose waste type or frequency we may fail to understand.
MAX_SKIPPED = 0.05

# Types of settlements and streets as the file writes them (folded, without the dot), and the
# abbreviation the Address Register uses.
TOWN_TYPES = {
    "k": "k.",
    "km": "k.",
    "kaimas": "k.",
    "mstl": "mstl.",
    "miestelis": "mstl.",
    "m": "m.",
    "miestas": "m.",
    "vs": "vs.",
    "viensedis": "vs.",
}
STREET_TYPES = {
    "g": "g.",
    "gt": "g.",
    "gatve": "g.",
    "al": "al.",
    "aleja": "al.",
    "tak": "tak.",
    "takas": "tak.",
    "kel": "kel.",
    "kelias": "kel.",
    "pl": "pl.",
    "plentas": "pl.",
    "skg": "skg.",
    "skrg": "skg.",
    "skersgatvis": "skg.",
    "pr": "pr.",
    "prospektas": "pr.",
    "a": "a.",
    "aikste": "a.",
}
# A house number and what follows it: "8", "8A", "8-1", "20S-K1-2", "20S K2" (blocks are
# written with and without a dash). The containers of "8-1" and "8-2" are those of building 8.
BUILDING = re.compile(r"(\d+[A-Z]?)(?:-.+|-?K-?\d.*)?")


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    """Emptied every `every` days, in `months` only (all year if empty)."""

    every: int
    months: tuple[int, ...] = ()


def parse_rule(text: str) -> Rule | None:
    """Understands the frequency texts of the file, e.g. "kas 14 dienų", "kas 28 dienas,
    balandį, gegužę, …, lapkritį" and "kiekvieną mėnesio dieną, kiekvieną mėnesį, penktadienį"
    (every Friday). Returns None for anything else."""
    parts = [clean_text(p).casefold() for p in text.split(",") if clean_text(p)]
    if not parts:
        return None
    interval = re.fullmatch(r"kas (\d+) dien\w+", parts[0])
    if interval:
        months = []
        for part in parts[1:]:
            if part not in MONTHS:
                return None
            months.append(MONTHS[part])
        return Rule(int(interval.group(1)), tuple(sorted(months)))
    if (
        parts[:2] == ["kiekvieną mėnesio dieną", "kiekvieną mėnesį"]
        and len(parts) == 3
        and parts[2] in WEEKDAYS
    ):
        return Rule(7)
    return None


@dataclass(frozen=True)
class Schedule:
    """Containers emptied on the same days: same waste type, rule and phase."""

    kind: str
    rule: Rule
    # Day number of a pickup modulo `rule.every`: identical for every date of the schedule, so
    # the id stays the same from day to day and the app keeps the user's choice.
    phase: int
    text: str
    # Set when the next pickup is more than one interval away (green waste in winter): there
    # are no pickups before it.
    resumes: date | None = None

    @property
    def id(self) -> str:
        key = f"{self.kind}|{self.rule.every}|{self.phase}|{','.join(map(str, self.rule.months))}"
        if self.resumes:
            key += f"|{self.resumes.isoformat()}"
        return f"k{self.kind[0]}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"

    def dates(self, start: date, end: date) -> list[date]:
        start = max(start, self.resumes) if self.resumes else start
        first = start + timedelta(days=(self.phase - start.toordinal()) % self.rule.every)
        days = range((end - first).days + 1)
        result = [first + timedelta(days=n) for n in days[:: self.rule.every]]
        return [d for d in result if not self.rule.months or d.month in self.rule.months]

    def to_json(self, start: date, end: date) -> dict:
        data: dict = {"id": self.id, "kind": self.kind, "rule": self.text, "every": self.rule.every}
        if self.rule.months:
            data["months"] = list(self.rule.months)
        if self.resumes:
            data["resumes"] = self.resumes.isoformat()
        data["dates"] = [d.isoformat() for d in self.dates(start, end)]
        return data


def slug(name: str) -> str:
    """ "Užliedžių sen." -> "uzliedziu": a file name for an eldership."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r"\bsen\.?$", "", ascii_name.strip(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-") or "kita"


def house_key(value: str) -> tuple:
    """Sorts house numbers like people do: 2, 2A, 10, 10-1."""
    return tuple(int(p) if p.isdigit() else p.casefold() for p in re.findall(r"\d+|\D+", value))


# eldership -> town -> street -> house number -> schedule ids
Index = dict[str, dict[str, dict[str, dict[str, set[str]]]]]
# (eldership, town, street, house number)
Address = tuple[str, str, str, str]


def split_type(name: str, types: dict[str, str]) -> tuple[str, str | None]:
    """ "Vynuogyno g" -> ("vynuogyno", "g."), "Akademija" -> ("akademija", None): the folded
    name and the register's abbreviation of its type, if the name ends with one."""
    words = name.split()
    if len(words) > 1 and fold(words[-1]) in types:
        return fold(" ".join(words[:-1])), types[fold(words[-1])]
    return fold(name), None


def find_settlements(settlements: Iterable[Settlement], town: str) -> list[Settlement]:
    """The settlements `town` may be: the file mostly writes the genitive and the type
    ("Akademijos mstl."), sometimes the plain name ("Akademija") or a type without its dot."""
    base, kind = split_type(town, TOWN_TYPES)
    return [
        s
        for s in settlements
        if base in (fold(s.name), fold(s.genitive)) and kind in (None, s.abbr)
    ]


def find_street(settlement: Settlement, street: str) -> int | None:
    """The register code of `street` in `settlement`, or None if it isn't there or could be
    several streets. "J. Biliūno g." is "Jono Biliūno g.", and "Vynuogyno" is "Vynuogyno g." if
    no other street has that name."""
    base, kind = split_type(street, STREET_TYPES)
    codes = set()
    for candidate in settlement.streets:
        words = fold(candidate.name).split()
        # Any number of first names may be shortened to their initials.
        forms = {" ".join([w[0] for w in words[:k]] + words[k:]) for k in range(len(words))}
        if base in forms and kind in (None, candidate.abbr):
            codes.add(candidate.code)
    return codes.pop() if len(codes) == 1 else None


def _district(eldership: str) -> str:
    """ "Garliavos apylinkių sen." -> "garliavos apylinkiu", as the register names it."""
    return re.sub(r"\s+sen$", "", fold(eldership))


def _by_district(settlements: Iterable[Settlement]) -> dict[str, list[Settlement]]:
    result: dict[str, list[Settlement]] = defaultdict(list)
    for settlement in settlements:
        result[fold(settlement.district)].append(settlement)
    return result


def register_names(index: Index, registry: Registry | None) -> dict[str, dict[str, str]]:
    """eldership -> town -> the town's name in the Address Register, for towns the file writes
    otherwise: "Akademijos mstl." -> "Akademija". People search for that name (the nominative),
    and the genitive doesn't contain it. The settlement is looked up in the town's eldership,
    then in the whole district; a town with no settlement of that name, or with settlements of
    different names, gets none."""
    if not registry:
        return {}
    in_district = _by_district(registry.settlements)
    result: dict[str, dict[str, str]] = {}
    for eldership, towns in index.items():
        for town in towns:
            found = find_settlements(in_district.get(_district(eldership), []), town)
            names = {s.name for s in found or find_settlements(registry.settlements, town)}
            if len(names) == 1 and (name := names.pop()) != town:
                result.setdefault(eldership, {})[town] = name
    return result


def _same_places(
    names: dict[str, int], resolve: Callable[[str], int | None], types: dict[str, str]
) -> dict[str, str]:
    """Maps each spelling to the spelling of its place. `names` counts the addresses written
    with each spelling. Two spellings are one place if the register gives them the same code,
    or, for names it doesn't have, if they differ only in case, spaces, dots or a missing type
    ("Žiedo g", "Žiedo") and no other place has that name. "Darbininkų g." and "Darbininkų
    skg." stay apart. The spelling with the most addresses is kept: most phones saved it."""
    keys: dict[str, tuple] = {}
    for name in names:
        code = resolve(name)
        keys[name] = ("code", code) if code is not None else ("name", *split_type(name, types))
    places_named: dict[str, set[tuple]] = defaultdict(set)
    for name, key in keys.items():
        places_named[split_type(name, types)[0]].add(key)
    for name, key in keys.items():
        if key[0] == "name" and key[2] is None:
            others = places_named[key[1]] - {key}
            if len(others) == 1:
                keys[name] = next(iter(others))
    groups: dict[tuple, list[str]] = defaultdict(list)
    for name, key in keys.items():
        groups[key].append(name)
    result = {}
    for members in groups.values():
        # On a tie, the spelling with its type, then the first in alphabetical order.
        best = min(members, key=lambda n: (-names[n], split_type(n, types)[1] is None, n))
        result.update(dict.fromkeys(members, best))
    return result


@dataclass
class Merged:
    index: Index
    # Addresses as the file writes them -> the same address in `index`, for every spelling that
    # was merged into another one. Phones may have saved them.
    aliases: dict[Address, Address]
    counts: Counter[str]


def merge_spellings(index: Index, registry: Registry | None) -> Merged:
    """Merges the spellings of one town, street or house number into one: "Akademija" and
    "Akademijos mstl.", "Vynuogyno" and "Vynuogyno g.", "21 A" and "21A". A town listed under
    an eldership the register doesn't put it in moves to the register's eldership when that is
    certain (one settlement of that name in the district, and its streets are there); otherwise
    it stays, and is counted."""
    settlements = registry.settlements if registry else []
    in_district = _by_district(settlements)
    elderships = {_district(name): name for name in index}
    counts: Counter[str] = Counter()

    def settlement_of(eldership: str, town: str) -> Settlement | None:
        found = find_settlements(in_district.get(_district(eldership), []), town)
        return found[0] if len(found) == 1 else None

    moved: dict[tuple[str, str], str] = {}
    for eldership, towns in index.items():
        for town, streets in towns.items():
            if not settlements or settlement_of(eldership, town):
                continue
            found = find_settlements(settlements, town)
            if not found:
                continue
            target = elderships.get(fold(found[0].district)) if len(found) == 1 else None
            if target and all(find_street(found[0], street) is not None for street in streets):
                moved[(eldership, town)] = target
                counts["movedTowns"] += 1
            else:
                counts["otherEldership"] += 1

    staged: Index = {}
    origin: dict[Address, Address] = {}
    for eldership, towns in index.items():
        for town, streets in towns.items():
            target = moved.get((eldership, town), eldership)
            for street, houses in streets.items():
                for house, ids in houses.items():
                    place = staged.setdefault(target, {}).setdefault(town, {})
                    place.setdefault(street, {}).setdefault(house, set()).update(ids)
                    origin[(eldership, town, street, house)] = (target, town, street, house)

    merged: Index = {}
    final: dict[Address, Address] = {}
    for eldership, towns in staged.items():

        def town_code(town: str, eldership: str = eldership) -> int | None:
            settlement = settlement_of(eldership, town)
            return settlement.code if settlement else None

        town_sizes = {t: sum(len(h) for h in s.values()) for t, s in towns.items()}
        town_of = _same_places(town_sizes, town_code, TOWN_TYPES)
        for town in set(town_of.values()):
            members = [t for t in towns if town_of[t] == town]
            counts["towns"] += len(members) - 1
            settlement = settlement_of(eldership, town)
            street_sizes: Counter[str] = Counter()
            for member in members:
                for street, houses in towns[member].items():
                    street_sizes[street] += len(houses)

            def street_code(street: str, settlement: Settlement | None = settlement) -> int | None:
                return find_street(settlement, street) if settlement else None

            street_of = _same_places(dict(street_sizes), street_code, STREET_TYPES)
            counts["streets"] += len(street_of) - len(set(street_of.values()))
            # Spellings of one house number: "21 A" and "21A", "2e" and "2E".
            numbers: dict[tuple[str, str], set[str]] = defaultdict(set)
            for member in members:
                for street, houses in towns[member].items():
                    for house in houses:
                        numbers[(street_of[street], _house(house))].add(house)
            house_of = {
                (street, house): min(spellings, key=lambda h: (" " in h, h != h.upper(), h))
                for (street, _), spellings in numbers.items()
                for house in spellings
            }
            counts["houses"] += sum(len(spellings) - 1 for spellings in numbers.values())
            target = merged.setdefault(eldership, {}).setdefault(town, {})
            for member in members:
                for street, houses in towns[member].items():
                    for house, ids in houses.items():
                        key = (street_of[street], house_of[(street_of[street], house)])
                        target.setdefault(key[0], {}).setdefault(key[1], set()).update(ids)
                        final[(eldership, member, street, house)] = (eldership, town, *key)

    aliases = {}
    for address, staged_address in origin.items():
        if final[staged_address] != address:
            aliases[address] = final[staged_address]
    return Merged(merged, aliases, counts)


def fill_buildings(index: Index, kind_of: dict[str, str]) -> int:
    """Gives every house number the waste types of its building: the file may list the food
    bin of house 8 under "8" and the mixed waste bins under "8-1" and "8-2". A missing type is
    taken from the house itself (8). If the house doesn't have it either, it comes from the
    flats or blocks that do (8-1, 8-2): the schedules most of them have, or all of the most
    common ones on a tie. Types a house number already has are kept as they are. Returns how
    many house numbers got something."""
    changed = 0
    for streets in (s for towns in index.values() for s in towns.values()):
        for houses in streets.values():
            buildings: dict[str, list[str]] = defaultdict(list)
            for house in houses:
                match = BUILDING.fullmatch(_house(house).upper())
                buildings[match.group(1) if match else house].append(house)
            for building, members in buildings.items():
                if len(members) < 2:
                    continue
                of_kind = {
                    (h, kind): frozenset(i for i in houses[h] if kind_of[i] == kind)
                    for h in members
                    for kind in {kind_of[i] for i in houses[h]}
                }
                main = next((h for h in members if _house(h).upper() == building), None)
                added: dict[str, set[str]] = defaultdict(set)
                for kind in {kind for _, kind in of_kind}:
                    if main is not None and (main, kind) in of_kind:
                        ids = set(of_kind[(main, kind)])
                    else:
                        votes = Counter(of_kind[(h, kind)] for h in members if (h, kind) in of_kind)
                        top = max(votes.values())
                        ids = set().union(*(s for s, n in votes.items() if n == top))
                    for house in members:
                        if (house, kind) not in of_kind:
                            added[house] |= ids
                for house, ids in added.items():
                    houses[house] |= ids
                changed += len(added)
    return changed


def build(
    content: bytes, today: date, registry: Registry | None = None
) -> tuple[dict, dict[str, dict], list[str]]:
    """Returns (schedule.json, {eldership slug: addresses file}, warnings). With the Address
    Register (`registry`), spellings are merged by the register's codes; without it only
    spellings that differ in case, spaces, dots or a missing type are."""
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
    rows = [[clean_text(c) for c in row] for row in reader if len(row) == 9]
    rows = [row for row in rows if row[0] == MUNICIPALITY]
    if len(rows) < MIN_ROWS:
        raise ValidationError(f"only {len(rows)} rows for {MUNICIPALITY}")

    # Some rows have no eldership: take it from other rows of the same town.
    town_eldership = {row[2]: row[1] for row in rows if row[1]}
    schedules: dict[str, Schedule] = {}
    index: Index = {}
    skipped: Counter[str] = Counter()
    # Containers whose only date is long past have no pickup announced (not in service, or the
    # season is over): continuing their rhythm would invent dates.
    stale: Counter[str] = Counter()
    for _, eldership, town, street, house, _container, next_date, frequency, service in rows:
        kind = KINDS.get(service)
        rule = parse_rule(frequency)
        try:
            pickup = date.fromisoformat(next_date)
        except ValueError:
            pickup = None
        if not kind:
            skipped[f"waste type „{service}“"] += 1
            continue
        if not rule or not pickup:
            skipped[f"frequency „{frequency}“ / date „{next_date}“"] += 1
            continue
        if pickup < today - timedelta(days=rule.every):
            stale[kind] += 1
            continue
        resumes = pickup if pickup > today + timedelta(days=rule.every) else None
        schedule = Schedule(kind, rule, pickup.toordinal() % rule.every, frequency, resumes)
        schedules.setdefault(schedule.id, schedule)
        eldership = eldership or town_eldership.get(town, "")
        houses = index.setdefault(eldership, {}).setdefault(town, {}).setdefault(street, {})
        houses.setdefault(house, set()).add(schedule.id)

    warnings = [f"{count} rows skipped: {reason}" for reason, count in skipped.most_common()]
    warnings += [
        f"{count} {kind} containers without an upcoming pickup left out"
        for kind, count in stale.most_common()
    ]
    if sum(skipped.values()) > MAX_SKIPPED * len(rows):
        raise ValidationError("too many rows not understood: " + "; ".join(warnings))
    merged = merge_spellings(index, registry)
    index = merged.index
    filled = fill_buildings(index, {i: s.kind for i, s in schedules.items()})
    address_count = sum(
        len(houses)
        for towns in index.values()
        for streets in towns.values()
        for houses in streets.values()
    )
    if address_count < MIN_ADDRESSES:
        raise ValidationError(f"only {address_count} addresses for {MUNICIPALITY}")

    start, end = today - timedelta(days=KEEP_DAYS), today + timedelta(days=HORIZON_DAYS)
    ordered = sorted(
        schedules.values(),
        key=lambda s: (s.kind, s.rule.every, s.rule.months, s.phase, s.resumes or date.min),
    )
    # Address files refer to schedules by their position in this list, to stay small.
    position = {s.id: i for i, s in enumerate(ordered)}

    # File names stay the same as long as the elderships do: phones saved them.
    file_of: dict[str, str] = {}
    for eldership in sorted(set(index) | {a[0] for a in merged.aliases}, key=str.casefold):
        name = slug(eldership)
        while name in file_of.values():  # two elderships with the same ASCII name
            name += "-2"
        file_of[eldership] = name
    # Spellings merged into another one, by the eldership they were written under: town ->
    # street -> house -> [eldership file, town, street, house] of the address to use. Not shown
    # in the app's lists; they keep addresses saved with these spellings working.
    aliases: dict[str, dict] = {}
    for (eldership, town, street, house), target in sorted(merged.aliases.items()):
        streets = aliases.setdefault(eldership, {}).setdefault(town, {})
        streets.setdefault(street, {})[house] = [file_of[target[0]], *target[1:]]

    files: dict[str, dict] = {}
    elderships = []
    names = register_names(index, registry)
    for eldership, name in file_of.items():
        towns = index.get(eldership, {})
        files[name] = {
            "eldership": eldership,
            "towns": {
                town: {
                    street: {
                        house: sorted(position[i] for i in ids)
                        for house, ids in sorted(houses.items(), key=lambda kv: house_key(kv[0]))
                    }
                    for street, houses in sorted(streets.items(), key=lambda kv: kv[0].casefold())
                }
                for town, streets in sorted(towns.items(), key=lambda kv: kv[0].casefold())
            },
        }
        if eldership in aliases:
            files[name]["aliases"] = aliases[eldership]
        entry = {"id": name, "name": eldership, "towns": sorted(towns, key=str.casefold)}
        # Added later: apps that don't know it search the town names only.
        if eldership in names:
            entry["registerNames"] = dict(sorted(names[eldership].items()))
        elderships.append(entry)

    counts = Counter(s.kind for s in ordered)
    dataset = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": PROVIDER,
        "source": SHARE_URL,
        "municipality": MUNICIPALITY,
        "stats": {
            "rows": len(rows),
            "addresses": address_count,
            "towns": sum(len(t) for t in index.values()),
            "areas": dict(sorted(counts.items())),
            # Spellings of one place merged into one, and house numbers that got waste types
            # from the rest of their building (see merge_spellings and fill_buildings).
            "merged": {
                "towns": merged.counts["towns"],
                "streets": merged.counts["streets"],
                "houses": merged.counts["houses"],
                "townsMovedToTheirEldership": merged.counts["movedTowns"],
                "townsInAnotherEldership": merged.counts["otherEldership"],
                "aliases": len(merged.aliases),
                "filledFromBuilding": filled,
            },
        },
        # For monitoring (status.py).
        "warnings": len(warnings),
        "areas": [s.to_json(start, end) for s in ordered],
        "elderships": elderships,
    }
    return dataset, files, warnings


def _house(number: str) -> str:
    return re.sub(r"\s+", "", number).casefold()


def locate_table(
    files: dict[str, dict], registry: Registry, points: list[AddressPoint], generated_at: str
) -> tuple[dict, int]:
    """Coordinates for "use my location": the addresses of `files` found in the Address
    Register. `places` are [eldership file, eldership, town, street]; each point is
    [lat * 1e5, lon * 1e5, place index, house number]. Also returns how many addresses
    weren't found (they can still be picked by hand)."""
    by_settlement: dict[int, dict[tuple[int | None, str], AddressPoint]] = {}
    for point in points:
        by_settlement.setdefault(point.settlement, {})[(point.street, _house(point.number))] = point

    places: list[list[str]] = []
    rows = []
    missing = 0
    for file_name, data in files.items():
        for town, streets in data["towns"].items():
            candidates = find_settlements(registry.settlements, town)
            # Two villages of one name: the one in this eldership.
            same = [
                c
                for c in candidates
                if fold(c.district) and fold(c.district) in fold(data["eldership"])
            ]
            for street, houses in streets.items():
                place = None
                for house in houses:
                    found = None
                    for settlement in same or candidates:
                        code = find_street(settlement, street) if street else None
                        if street and code is None:
                            continue
                        known = by_settlement.get(settlement.code, {})
                        # "10-2" may be a flat or a building of house 10.
                        base = re.match(r"\d+[a-z]?", _house(house))
                        found = known.get((code, _house(house))) or (
                            known.get((code, base.group())) if base else None
                        )
                        if found:
                            break
                    if not found:
                        missing += 1
                        continue
                    if place is None:
                        place = len(places)
                        places.append([file_name, data["eldership"], town, street])
                    rows.append([round(found.lat * 1e5), round(found.lon * 1e5), place, house])
    rows.sort()
    table = {"generatedAt": generated_at, "source": ATTRIBUTION, "places": places, "points": rows}
    return table, missing


def fetch(sleep=time.sleep) -> bytes:
    """Downloads the CSV: opening the sharing link sets an anonymous cookie, which the download
    address then accepts."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
            )
            opener.addheaders = [("User-Agent", USER_AGENT)]
            with opener.open(SHARE_URL, timeout=120) as response:
                response.read()
            with opener.open(DOWNLOAD_URL, timeout=300) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == ATTEMPTS:
                raise
            sleep(2**attempt)
    raise AssertionError("unreachable")


def write(out: Path, dataset: dict, files: dict[str, dict]) -> None:
    def dump(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

    addresses = out / "addresses"
    addresses.mkdir(parents=True, exist_ok=True)
    for old in addresses.glob("*.json"):
        old.unlink()
    for name, data in files.items():
        dump(addresses / f"{name}.json", data)
    dump(out / "schedule.json", dataset)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument("--csv", type=Path, help="read this file instead of downloading")
    args = parser.parse_args(argv)

    content = args.csv.read_bytes() if args.csv else fetch()
    # The snapshot of the Address Register (see snapshot.py) tells which spellings are one place
    # and gives the addresses coordinates. Without it the app still works: fewer spellings are
    # merged, and "use my location" doesn't find Kauno r. addresses.
    registry = None
    if snapshot.KAUNO_REGISTRY_FILE.exists():
        registry, _ = snapshot.load_registry(snapshot.KAUNO_REGISTRY_FILE)
    try:
        dataset, files, warnings = build(content, date.today(), registry)
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    write(args.out, dataset, files)

    located = ""
    if registry and snapshot.KAUNO_ADDRESSES_FILE.exists():
        points, taken_at = snapshot.load_points(snapshot.KAUNO_ADDRESSES_FILE)
        table, missing = locate_table(files, registry, points, dataset["generatedAt"])
        (args.out / "points.json").write_text(
            json.dumps(table, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        located = (
            f'- {len(table["points"])} addresses with coordinates for "use my location" '
            f"({missing} not found in the Address Register snapshot of {taken_at})"
        )

    stats = dataset["stats"]
    named = sum(len(e.get("registerNames", {})) for e in dataset["elderships"])
    sizes = sorted((args.out / "addresses").glob("*.json"), key=lambda p: p.stat().st_size)
    lines = [
        "## Kauno r. (Kauno švara)",
        "",
        f"- {stats['rows']} containers at {stats['addresses']} addresses in {stats['towns']} towns",
        f"- {named} towns can also be searched by their name in the Address Register",
        f"- schedules: {', '.join(f'{count} {kind}' for kind, count in stats['areas'].items())}",
        f"- {len(files)} address files, largest {sizes[-1].stat().st_size // 1024} KB"
        f" ({sizes[-1].name})",
        "- spellings merged: {towns} towns, {streets} streets, {houses} house numbers;"
        " {townsMovedToTheirEldership} towns moved to their eldership,"
        " {townsInAnotherEldership} left under another one; {aliases} old spellings kept as"
        " aliases; {filledFromBuilding} house numbers got waste types of their building".format(
            **stats["merged"]
        ),
    ]
    lines += [located] if located else []
    lines += [f"- warning: {w}" for w in warnings]
    text = "\n".join(lines) + "\n"
    print(text)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

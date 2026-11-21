"""Kauno r. and Kaišiadorių r.: schedules from the open-data file of UAB „Kauno švara“.

The company shares one CSV with every container it empties (nine municipalities, ~390k rows,
refreshed nightly). A row is one container at one address with its next pickup date and how
often it is emptied:

    Kauno r. sav.;Ringaudų sen.;Karkiškių k.;Ganyklų g.;2;52-MK-042246;2026-11-25;
    kas 14 dienų;Mišrios komunalinės   (one line in the file)

Two of the municipalities are read (MUNICIPALITIES): Kauno r. and Kaišiadorių r., where the
company empties only mixed waste. Both are published together, so app versions that know Kauno
r. find the Kaišiadorių r. addresses too; elderships of Kaišiadorių r. say so (`municipality`).
The others are left out on purpose: Kauno m., Vilniaus m. and Alytaus m. are cities, which the
project doesn't cover; Alytaus r. has only packaging and glass here; and Prienų r., Birštonas
and Druskininkai come from the schedules of Alytaus RATC (FROM_ALYTAUS_RATC).

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

Writes <out>/schedule.json, <out>/addresses/<eldership>.json and <out>/points.json. Run:
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


@dataclass(frozen=True)
class Municipality:
    """A municipality of the file whose addresses are published."""

    # As the app shows it ("Kaišiadorių r.").
    name: str
    # Its source in monitoring (status.py).
    id: str
    # The first column of its rows: some municipalities are written two ways.
    spellings: tuple[str, ...]
    # Fewer than this means the file or its format changed.
    min_rows: int
    min_addresses: int
    # Its Address Register snapshot (snapshot.py).
    registry_file: Path
    addresses_file: Path


# Kauno r. first. Its file names, schedule positions, `stats` and `warnings` stay what they were
# when it was alone in the files, for the app versions and monitoring that know only Kauno r.;
# elderships of the others have a `municipality`. If the rows of Kauno r. can't be read, the
# build fails; another municipality is left out instead, with a warning.
MUNICIPALITIES = (
    # 2026: 63k rows, 39k addresses.
    Municipality(
        "Kauno r.",
        "kauno",
        ("Kauno r. sav.",),
        min_rows=30_000,
        min_addresses=20_000,
        registry_file=snapshot.KAUNO_REGISTRY_FILE,
        addresses_file=snapshot.KAUNO_ADDRESSES_FILE,
    ),
    # 2026: 8.7k rows, 7.8k addresses, mixed waste only.
    Municipality(
        "Kaišiadorių r.",
        "kaisiadorys",
        ("Kaišiadorių r. sav.", "Kaišiadorių rajono sav."),
        min_rows=4_000,
        min_addresses=3_500,
        registry_file=snapshot.KAISIADORIU_REGISTRY_FILE,
        addresses_file=snapshot.KAISIADORIU_ADDRESSES_FILE,
    ),
)
# In the file too, but never read here: their schedules come from UAB „Alytaus regiono atliekų
# tvarkymo centras“ (aratc.lt), the official source for them. Reading them here as well would
# give their addresses two sources. Their rules in this file ("pirmąjį mėnesyje ketvirtadienį",
# "30 mėnesio dieną, spalį") aren't all understood either.
FROM_ALYTAUS_RATC = frozenset({"Prienų r. sav.", "Birštono sav.", "Druskininkų sav."})

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
# Days of the week as date.weekday() numbers them.
WEEKDAYS = {
    "pirmadienį": 0,
    "antradienį": 1,
    "trečiadienį": 2,
    "ketvirtadienį": 3,
    "penktadienį": 4,
    "šeštadienį": 5,
    "sekmadienį": 6,
}
# "pirmąjį mėnesyje trečiadienį": the first Wednesday of the month.
ORDINALS = {"pirmąjį": 1, "antrąjį": 2, "trečiąjį": 3, "ketvirtąjį": 4}
EVERY_DAY = ["kiekvieną mėnesio dieną", "kiekvieną mėnesį"]

# Dates are calculated this far ahead. The file is read again every day, so the phase of every
# schedule is always taken from its real next date.
HORIZON_DAYS = 180
KEEP_DAYS = 31
# Share of rows of a municipality whose waste type or frequency we may fail to understand.
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
    "akl": "aklg.",
    "aklg": "aklg.",
    "aklagatvis": "aklg.",
}
# A town that was a miestelis is still written so after the register made it a miestas:
# "Žiežmarių mstl." is the town Žiežmariai.
FORMER_TYPES = {("mstl.", "m.")}
# Share of a town's addresses that must be on streets of a settlement elsewhere in the
# district to move it there (see merge_spellings).
MOVE_SHARE = 0.9
# A house number and what follows it: "8", "8A", "8-1", "20S-K1-2", "20S K2" (blocks are
# written with and without a dash). The containers of "8-1" and "8-2" are those of building 8.
BUILDING = re.compile(r"(\d+[A-Z]?)(?:-.+|-?K-?\d.*)?")


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    """Emptied every `every` days, in `months` only (all year if empty). Or on days of the week
    (`weekdays`, 0 = Monday): every week on each of them, or with `nth` on the nth of that day
    in every month (`every` is then 0)."""

    every: int
    months: tuple[int, ...] = ()
    weekdays: tuple[int, ...] = ()
    nth: int = 0

    @property
    def gap(self) -> int:
        """The most days between two pickups (outside the months it skips)."""
        return 35 if self.nth else self.every

    def allows(self, day: date) -> bool:
        """Whether `day` can be a pickup: the file's next date is checked with it."""
        if self.weekdays and day.weekday() not in self.weekdays:
            return False
        return not self.nth or (day.day - 1) // 7 + 1 == self.nth


def parse_rule(text: str) -> Rule | None:
    """Understands the frequency texts of the file, e.g. "kas 14 dienų", "kas 28 dienas,
    balandį, gegužę, …, lapkritį" and "kiekvieną mėnesio dieną, kiekvieną mėnesį, penktadienį"
    (every Friday), "…, pirmadienį, penktadienį" (every Monday and Friday) and "…, pirmąjį
    mėnesyje trečiadienį" (the first Wednesday of every month). Returns None for anything
    else."""
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
    days = parts[2:] if parts[:2] == EVERY_DAY else []
    if len(days) == 1 and days[0] in WEEKDAYS:
        # One day a week: weekly, with the phase of its next date.
        return Rule(7)
    if len(days) > 1 and all(day in WEEKDAYS for day in days):
        return Rule(7, weekdays=tuple(sorted({WEEKDAYS[day] for day in days})))
    nth = re.fullmatch(r"(\w+) mėnesyje (\w+)", days[0]) if len(days) == 1 else None
    if nth and nth.group(1) in ORDINALS and nth.group(2) in WEEKDAYS:
        return Rule(0, weekdays=(WEEKDAYS[nth.group(2)],), nth=ORDINALS[nth.group(1)])
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
        if self.rule.nth:
            key += f"|{self.rule.nth}.{self.rule.weekdays[0]}"
        if self.resumes:
            key += f"|{self.resumes.isoformat()}"
        return f"k{self.kind[0]}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"

    def dates(self, start: date, end: date) -> list[date]:
        start = max(start, self.resumes) if self.resumes else start
        if self.rule.nth:
            days = (start + timedelta(days=n) for n in range((end - start).days + 1))
            result = [d for d in days if self.rule.allows(d)]
        else:
            first = start + timedelta(days=(self.phase - start.toordinal()) % self.rule.every)
            days = range((end - first).days + 1)
            result = [first + timedelta(days=n) for n in days[:: self.rule.every]]
        return [d for d in result if not self.rule.months or d.month in self.rule.months]

    def to_json(self, start: date, end: date) -> dict:
        data: dict = {"id": self.id, "kind": self.kind, "rule": self.text}
        if self.rule.nth:
            # The nth weekday (0 = Monday) of every month. Added later; the app reads `dates`.
            data |= {"nth": self.rule.nth, "weekday": self.rule.weekdays[0]}
        else:
            data["every"] = self.rule.every
        if self.rule.months:
            data["months"] = list(self.rule.months)
        if self.resumes:
            data["resumes"] = self.resumes.isoformat()
        data["dates"] = [d.isoformat() for d in self.dates(start, end)]
        return data


def schedules_for(kind: str, rule: Rule, pickup: date, text: str, today: date) -> list[Schedule]:
    """The schedules of a container with this rule and next pickup. Several days a week are a
    weekly schedule each, so containers emptied on any of those days share them."""
    # The next pickup is more than one interval away (green waste in winter).
    resumes = pickup if pickup > today + timedelta(days=rule.gap) else None
    if rule.nth:
        return [Schedule(kind, rule, 0, text, resumes)]
    if rule.weekdays:
        # 1 January of the year 1, day 1, was a Monday: a weekday's days are (weekday + 1) % 7.
        weekly = Rule(7, rule.months)
        return [Schedule(kind, weekly, (day + 1) % 7, text, resumes) for day in rule.weekdays]
    return [Schedule(kind, rule, pickup.toordinal() % rule.every, text, resumes)]


def _order(schedule: Schedule) -> tuple:
    rule = schedule.rule
    return (
        schedule.kind,
        rule.every,
        rule.months,
        rule.nth,
        rule.weekdays,
        schedule.phase,
        schedule.resumes or date.min,
    )


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
    name and the register's abbreviation of its type, if the name ends with one. Of two types
    ("Liepų al. g."), the first is the one."""
    words = name.split()
    if len(words) > 2 and fold(words[-2]) in types and fold(words[-1]) in types:
        return fold(" ".join(words[:-2])), types[fold(words[-2])]
    if len(words) > 1 and fold(words[-1]) in types:
        return fold(" ".join(words[:-1])), types[fold(words[-1])]
    return fold(name), None


def find_settlements(settlements: Iterable[Settlement], town: str) -> list[Settlement]:
    """The settlements `town` may be: the file mostly writes the genitive and the type
    ("Akademijos mstl."), sometimes the plain name ("Akademija"), a type without its dot or a
    former type (FORMER_TYPES)."""
    base, kind = split_type(town, TOWN_TYPES)
    return [
        s
        for s in settlements
        if base in (fold(s.name), fold(s.genitive))
        and (kind in (None, s.abbr) or (kind, s.abbr) in FORMER_TYPES)
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
    certain (one settlement of that name in the district, and nine in ten of its addresses are
    on its streets); otherwise it stays, and is counted."""
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
            known = sum(len(h) for s, h in streets.items() if find_street(found[0], s) is not None)
            if target and known >= MOVE_SHARE * sum(len(h) for h in streets.values()):
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


@dataclass
class Part:
    """The schedules and addresses of one municipality."""

    municipality: Municipality
    rows: int
    schedules: dict[str, Schedule]
    merged: Merged
    filled: int
    addresses: int
    registry: Registry | None
    warnings: list[str]


def read_part(
    municipality: Municipality, rows: list[list[str]], today: date, registry: Registry | None
) -> Part:
    """Reads the rows of one municipality. With the Address Register (`registry`), spellings
    are merged by the register's codes; without it only spellings that differ in case, spaces,
    dots or a missing type are."""
    if len(rows) < municipality.min_rows:
        raise ValidationError(f"only {len(rows)} rows for {municipality.name}")

    def eldership_of(row: list[str]) -> str:
        # A few rows have the municipality in the place of the eldership.
        return "" if row[1] in municipality.spellings else row[1]

    # Some rows have no eldership: take it from other rows of the same town.
    town_eldership = {row[2]: name for row in rows if (name := eldership_of(row))}
    schedules: dict[str, Schedule] = {}
    index: Index = {}
    skipped: Counter[str] = Counter()
    # Containers whose only date is long past have no pickup announced (not in service, or the
    # season is over): continuing their rhythm would invent dates.
    stale: Counter[str] = Counter()
    for row in rows:
        _, _, town, street, house, _container, next_date, frequency, service = row
        kind = KINDS.get(service)
        rule = parse_rule(frequency)
        try:
            pickup = date.fromisoformat(next_date)
        except ValueError:
            pickup = None
        if not kind:
            skipped[f"waste type „{service}“"] += 1
            continue
        # The next date must be one the rule has: "pirmąjį mėnesyje trečiadienį" is the first
        # Wednesday of a month.
        if not rule or not pickup or not rule.allows(pickup):
            skipped[f"frequency „{frequency}“ / date „{next_date}“"] += 1
            continue
        if pickup < today - timedelta(days=rule.gap):
            stale[kind] += 1
            continue
        eldership = eldership_of(row) or town_eldership.get(town, "")
        houses = index.setdefault(eldership, {}).setdefault(town, {}).setdefault(street, {})
        for schedule in schedules_for(kind, rule, pickup, frequency, today):
            schedules.setdefault(schedule.id, schedule)
            houses.setdefault(house, set()).add(schedule.id)

    warnings = [f"{count} rows skipped: {reason}" for reason, count in skipped.most_common()]
    warnings += [
        f"{count} {kind} containers without an upcoming pickup left out"
        for kind, count in stale.most_common()
    ]
    if sum(skipped.values()) > MAX_SKIPPED * len(rows):
        raise ValidationError("too many rows not understood: " + "; ".join(warnings))
    merged = merge_spellings(index, registry)
    filled = fill_buildings(merged.index, {i: s.kind for i, s in schedules.items()})
    address_count = sum(
        len(houses)
        for towns in merged.index.values()
        for streets in towns.values()
        for houses in streets.values()
    )
    if address_count < municipality.min_addresses:
        raise ValidationError(f"only {address_count} addresses for {municipality.name}")
    return Part(
        municipality, len(rows), schedules, merged, filled, address_count, registry, warnings
    )


def read(
    content: bytes, today: date, registries: dict[str, Registry] | None = None
) -> tuple[list[Part], list[str], Counter[str]]:
    """The parts of MUNICIPALITIES that can be read, Kauno r. first; `registries` are their
    Address Register snapshots by municipality id. Also returns warnings about municipalities
    left out, and how many rows each municipality that isn't read has."""
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
    rows = [[clean_text(c) for c in row] for row in reader if len(row) == 9]
    municipality_of = {name: m for m in MUNICIPALITIES for name in m.spellings}
    rows_of: dict[str, list[list[str]]] = defaultdict(list)
    not_read: Counter[str] = Counter()
    for row in rows:
        if row[0] in municipality_of:
            rows_of[municipality_of[row[0]].id].append(row)
        else:
            not_read[row[0]] += 1

    registries = registries or {}
    parts: list[Part] = []
    left_out: list[str] = []
    for municipality in MUNICIPALITIES:
        rows = rows_of[municipality.id]
        try:
            parts.append(read_part(municipality, rows, today, registries.get(municipality.id)))
        except ValidationError as error:
            # Kauno r. fails the build (yesterday's files are kept). The others must not hold
            # it back: their addresses are left out until their rows can be read again.
            if not parts:
                raise
            left_out.append(f"{municipality.name} left out: {error}")
    return parts, left_out, not_read


def _stats(part: Part) -> dict:
    merged, counts = part.merged, Counter(s.kind for s in part.schedules.values())
    return {
        "rows": part.rows,
        "addresses": part.addresses,
        "towns": sum(len(t) for t in merged.index.values()),
        "areas": dict(sorted(counts.items())),
        # Spellings of one place merged into one, and house numbers that got waste types from
        # the rest of their building (see merge_spellings and fill_buildings).
        "merged": {
            "towns": merged.counts["towns"],
            "streets": merged.counts["streets"],
            "houses": merged.counts["houses"],
            "townsMovedToTheirEldership": merged.counts["movedTowns"],
            "townsInAnotherEldership": merged.counts["otherEldership"],
            "aliases": len(merged.aliases),
            "filledFromBuilding": part.filled,
        },
    }


def _files(
    part: Part, position: dict[str, int], taken: set[str], label: str | None
) -> tuple[dict[str, dict], list[dict]]:
    """The address files of one municipality and its entries in the list of elderships, which
    say `label` as their municipality. `taken` are file names other municipalities use."""
    index, merged = part.merged.index, part.merged
    # File names stay the same as long as the elderships do: phones saved them.
    file_of: dict[str, str] = {}
    for eldership in sorted(set(index) | {a[0] for a in merged.aliases}, key=str.casefold):
        name = slug(eldership)
        while name in taken:  # two elderships with the same ASCII name
            name += "-2"
        file_of[eldership] = name
        taken.add(name)
    # Spellings merged into another one, by the eldership they were written under: town ->
    # street -> house -> [eldership file, town, street, house] of the address to use. Not shown
    # in the app's lists; they keep addresses saved with these spellings working.
    aliases: dict[str, dict] = {}
    for (eldership, town, street, house), target in sorted(merged.aliases.items()):
        streets = aliases.setdefault(eldership, {}).setdefault(town, {})
        streets.setdefault(street, {})[house] = [file_of[target[0]], *target[1:]]

    files: dict[str, dict] = {}
    elderships = []
    names = register_names(index, part.registry)
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
        entry: dict = {"id": name, "name": eldership}
        # Added later: apps that don't know it take every eldership to be in Kauno r.
        if label:
            entry["municipality"] = label
        entry["towns"] = sorted(towns, key=str.casefold)
        # Added later: apps that don't know it search the town names only.
        if eldership in names:
            entry["registerNames"] = dict(sorted(names[eldership].items()))
        elderships.append(entry)
    return files, elderships


def assemble(parts: list[Part], today: date) -> tuple[dict, list[dict[str, dict]]]:
    """schedule.json and the address files of each part (by file name, in the order of
    `parts`)."""
    start, end = today - timedelta(days=KEEP_DAYS), today + timedelta(days=HORIZON_DAYS)
    # Address files refer to schedules by their position in this list, to stay small. Those of
    # Kauno r. come first, in their order, so its files are the same as when it was alone; the
    # schedules only the others have follow.
    ordered: list[Schedule] = []
    for part in parts:
        known = {s.id for s in ordered}
        ordered += sorted((s for s in part.schedules.values() if s.id not in known), key=_order)
    position = {s.id: i for i, s in enumerate(ordered)}

    taken: set[str] = set()
    files_of: list[dict[str, dict]] = []
    elderships: list[dict] = []
    for n, part in enumerate(parts):
        files, entries = _files(part, position, taken, part.municipality.name if n else None)
        files_of.append(files)
        elderships += entries

    first, *others = parts
    dataset: dict = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "provider": PROVIDER,
        "source": SHARE_URL,
        "municipality": first.municipality.spellings[0],
        "stats": _stats(first),
        # For monitoring (status.py).
        "warnings": len(first.warnings),
    }
    if others:
        # The same for the other municipalities: a source each in monitoring.
        dataset["otherMunicipalities"] = [
            {
                "id": part.municipality.id,
                "name": part.municipality.name,
                "stats": _stats(part),
                "warnings": len(part.warnings),
            }
            for part in others
        ]
    dataset["areas"] = [s.to_json(start, end) for s in ordered]
    dataset["elderships"] = elderships
    return dataset, files_of


def build(
    content: bytes, today: date, registries: dict[str, Registry] | None = None
) -> tuple[dict, dict[str, dict], list[str]]:
    """Returns (schedule.json, {eldership file: addresses file}, warnings); warnings of the
    municipalities after Kauno r. start with their name. `registries`: see read()."""
    parts, left_out, _ = read(content, today, registries)
    dataset, files_of = assemble(parts, today)
    files = {name: data for files in files_of for name, data in files.items()}
    first, *others = parts
    warnings = first.warnings + [
        f"{part.municipality.name}: {warning}" for part in others for warning in part.warnings
    ]
    return dataset, files, warnings + left_out


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


def join_tables(tables: list[dict]) -> dict:
    """One table of the tables of several municipalities: the places of the first keep their
    index, and the points stay sorted."""
    places: list[list[str]] = []
    rows: list[list] = []
    for table in tables:
        offset = len(places)
        places += table["places"]
        rows += [[lat, lon, place + offset, house] for lat, lon, place, house in table["points"]]
    rows.sort()
    return {**tables[0], "places": places, "points": rows}


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


def _summary(part: Part, files: dict[str, dict], folder: Path, located: str) -> list[str]:
    """The job summary of one municipality."""
    stats = _stats(part)
    named = sum(len(names) for names in register_names(part.merged.index, part.registry).values())
    sizes = sorted((folder / f"{name}.json" for name in files), key=lambda p: p.stat().st_size)
    lines = [
        f"## {part.municipality.name} (Kauno švara)",
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
    lines += [f"- warning: {w}" for w in part.warnings]
    return [*lines, ""]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument("--csv", type=Path, help="read this file instead of downloading")
    args = parser.parse_args(argv)

    content = args.csv.read_bytes() if args.csv else fetch()
    # The snapshots of the Address Register (see snapshot.py) tell which spellings are one place
    # and give the addresses coordinates. Without one the app still works: fewer spellings are
    # merged, and "use my location" doesn't find the addresses of that municipality.
    registries = {
        m.id: snapshot.load_registry(m.registry_file)[0]
        for m in MUNICIPALITIES
        if m.registry_file.exists()
    }
    today = date.today()
    try:
        parts, left_out, not_read = read(content, today, registries)
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    dataset, files_of = assemble(parts, today)
    write(args.out, dataset, {name: data for files in files_of for name, data in files.items()})

    lines: list[str] = []
    tables = []
    for part, files in zip(parts, files_of, strict=True):
        located = ""
        if part.registry and part.municipality.addresses_file.exists():
            points, taken_at = snapshot.load_points(part.municipality.addresses_file)
            table, missing = locate_table(files, part.registry, points, dataset["generatedAt"])
            tables.append(table)
            located = (
                f'- {len(table["points"])} addresses with coordinates for "use my location" '
                f"({missing} not found in the Address Register snapshot of {taken_at})"
            )
        lines += _summary(part, files, args.out / "addresses", located)
    if tables:
        (args.out / "points.json").write_text(
            json.dumps(join_tables(tables), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    lines += [f"- warning: {w}" for w in left_out]
    lines += [
        "",
        "Not read: "
        + ", ".join(
            f"{name or '(no municipality)'} ({count} rows"
            + (", from Alytaus RATC)" if name in FROM_ALYTAUS_RATC else ")")
            for name, count in not_read.most_common()
        ),
    ]
    text = "\n".join(lines) + "\n"
    print(text)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

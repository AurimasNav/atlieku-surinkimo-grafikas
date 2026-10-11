"""Links each settlement (and street) of the Address Register to its rows in every schedule.

The schedules describe their areas as free text in different shapes:

  household:  "Avižieniai (Akacijų aklg., Avižų g., ...)"            nominative, streets in ()
  packaging:  "Avižienių sen. kaimai : Bajorų k. tik Čiobrelių., Jurginų g. Bendorių k. ..."
  glass:      "Sužionių sen. kaimai iškyrus Pakryžės k., Veriškių k. Nemenčinės ..."

Instead of parsing every street format, we find settlement mentions using the register's
official names (nominative and genitive), then look for that settlement's official street
names in the text that follows the mention. A row then covers either a whole settlement or
some of its streets. "<X> sen. kaimai" without a list, or with "išskyrus", covers the whole
seniūnija apart from the settlements listed after "išskyrus".

Only exact, unambiguous links are published as such. Anything else is published as a short
list of candidate rows, and the app asks the user to choose.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .model import Area, Kind
from .registry import Registry, Settlement, Street, fold

KINDS: list[Kind] = ["household", "packaging", "glass"]

_UPPER = "A-ZĄČĘĖĮŠŲŪŽ"
_WORD = rf"[{_UPPER}][\wąčęėįšųūž-]*"
# Up to three capitalised words before a settlement type: "Aukštųjų Rusokų k.", "Visalaukės I k."
_MENTION = re.compile(rf"((?:{_WORD}\s+){{0,2}}{_WORD}(?:\s+I{{1,3}})?)\s*(k|vs|mstl|m)\s*\.", re.U)
_DISTRICT = re.compile(rf"({_WORD})\s+(?:sen|seniūnijos)\b\.?", re.U)
_EXCEPT = re.compile(r"i[sš]+kyrus", re.I)


@dataclass
class Clause:
    """One row's statement about one settlement."""

    area_id: str
    streets: set[str] | None  # street keys this row covers; None = the whole settlement
    fallback: bool = False  # from "<X> sen. kaimai": less specific than a named settlement


@dataclass
class Index:
    registry: Registry
    by_name: dict[str, list[Settlement]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        for s in self.registry.settlements:
            for form in {fold(s.name), fold(s.genitive)}:
                self.by_name[form].append(s)
        self.districts = sorted({s.district for s in self.registry.settlements})

    def district(self, text: str) -> str | None:
        """Maps the schedules' spellings ("Sužionys", "Nemenčinės mst.") to register names."""
        words = fold(text).split()
        if not words:
            return None
        town = any(w in ("m", "mst", "miesto") for w in words[1:])
        best, best_len = None, 0
        for district in self.districts:
            first = fold(district).split()[0]
            common = len(_common_prefix(words[0], first))
            is_town = "miesto" in fold(district)
            if common >= 5 and is_town == town and common > best_len:
                best, best_len = district, common
        return best

    def candidates(self, name: str, district: str | None) -> list[Settlement]:
        key = fold(name)
        hits = self.by_name.get(key, [])
        if district:
            in_district = [s for s in hits if s.district == district]
            if not in_district:
                # "Akmena" in a schedule covers the register's "Akmena I" and "Akmena II".
                in_district = [
                    s
                    for s in self.registry.settlements
                    if s.district == district
                    and any(
                        re.fullmatch(re.escape(key) + r" i{1,3}", fold(form))
                        for form in (s.name, s.genitive)
                    )
                ]
            if not in_district:
                # The schedules sometimes spell names differently from the register
                # ("Kalikstiškiai" for "Kalikstiškės", "Visalaukė" for "Visalaukė I"). Accept a
                # near match, but only inside the same seniūnija.
                in_district = [
                    s
                    for s in self.registry.settlements
                    if s.district == district
                    and any(_near(key, fold(form)) for form in (s.name, s.genitive))
                ]
            hits = in_district or hits
        return list({s.code: s for s in hits}.values())

    def find(self, name: str, district: str | None) -> Settlement | None:
        hits = self.candidates(name, district)
        return hits[0] if len(hits) == 1 else None


def _near(a: str, b: str) -> bool:
    """Same word apart from a grammatical ending: "kalikstiskiai" ~ "kalikstiskes",
    but not "akmena" ~ "akmenele" (an extra syllable is a different name)."""
    common = len(_common_prefix(a, b))
    if common < 5:
        return False
    endings = (a[common:], b[common:])
    return all(len(e) <= 3 and set(e) <= set("aeiouys") for e in endings)


def _common_prefix(a: str, b: str) -> str:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n]


def street_key(street: Street) -> str:
    return f"s{street.code}"


def variant_key(label: str) -> str:
    return "v" + hashlib.sha1(fold(label).encode()).hexdigest()[:8]


def streets_in(text: str, settlement: Settlement) -> set[str]:
    """Official street names of `settlement` that appear in `text`."""
    folded = f" {fold(text)} "
    return {street_key(t) for t in settlement.streets if f" {fold(t.name)} " in folded}


def household_clauses(
    index: Index, area: Area, variants: dict[int, dict[str, str]]
) -> list[tuple[Settlement, Clause]]:
    """ "Avižieniai (Akacijų aklg., ...)" -> Avižieniai, streets {Akacijų, ...}."""
    district = index.district(area.district or "")
    name = re.sub(r"\s*\((k|vs|mstl|m)\.?\)", "", area.name)  # "Akmena (k.)"
    words = name.split()
    # Longest leading run of words that is a settlement name: "Mažoji Riešė (...)".
    for n in range(min(4, len(words)), 0, -1):
        head = re.sub(r"\(.*", "", " ".join(words[:n])).strip(" ,")
        hits = index.candidates(re.sub(r"\s+(k|vs|mstl|m)\.?$", "", head), district)
        if hits:
            break
    else:
        return []
    # `head` stops before any "(", so this keeps the whole street list.
    rest = name[name.index(head) + len(head) :].strip(" ,")
    if not rest:
        # Applies to every match: "Akmena" -> "Akmena I" and "Akmena II".
        return [(s, Clause(area.id, None)) for s in hits]
    with_streets = [(s, streets_in(rest, s)) for s in hits]
    if any(streets for _, streets in with_streets):
        # One row can list streets of two same-named settlements (Bezdonys k. and mstl.).
        return [(s, Clause(area.id, streets)) for s, streets in with_streets if streets]
    if len(hits) > 1:
        return []
    # Not a street list, e.g. a garden community "S/B Telefonistas": offer it as its own choice.
    label = re.sub(r"^\(|\)$", "", rest).strip()
    key = variant_key(label)
    variants[hits[0].code][key] = label
    return [(hits[0], Clause(area.id, {key}))]


def listed_clauses(index: Index, area: Area) -> tuple[list[tuple[Settlement, Clause]], list]:
    """Packaging/glass rows. Returns explicit clauses and whole-seniūnija rules."""
    clauses: list[tuple[Settlement, Clause]] = []
    whole_districts: list[tuple[str, set[int]]] = []  # (district, excluded settlement codes)

    # Split the row at "<X> sen." markers; text before the first marker has no district.
    markers = list(_DISTRICT.finditer(area.name))
    parts = [(None, area.name[: markers[0].start()] if markers else area.name)]
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(area.name)
        parts.append((index.district(m.group(1)), area.name[m.end() : end]))

    for district, text in parts:
        mentions = []
        for m in _MENTION.finditer(text):
            words = m.group(1).split()
            # Prefer the longest name: "Aukštųjų Rusokų" before "Rusokų".
            for k in range(len(words)):
                hits = index.candidates(" ".join(words[k:]), district)
                if hits:
                    mentions += [(m, settlement) for settlement in hits]
                    break

        except_at = _EXCEPT.search(text)
        lead = text[: mentions[0][0].start()] if mentions else text
        if district and (
            (except_at and (not mentions or except_at.start() < mentions[0][0].start()))
            or (not mentions and re.fullmatch(r"\W*kaimai\W*", lead, re.I))
        ):
            excluded = {s.code for _, s in mentions}
            whole_districts.append((district, excluded))
            continue

        starts = sorted({m.start() for m, _ in mentions})
        for m, settlement in mentions:
            end = next((s for s in starts if s > m.start()), len(text))
            tail = text[m.end() : end]
            streets = streets_in(tail, settlement)
            clauses.append((settlement, Clause(area.id, streets or None)))
    return clauses, whole_districts


def resolve(clauses: list[Clause]) -> dict | None:
    """Turns everything the rows say about one settlement into what the app needs."""
    if not clauses:
        return None
    named = [c for c in clauses if not c.fallback]
    whole = sorted({c.area_id for c in named if c.streets is None})
    by_street: dict[str, set[str]] = defaultdict(set)
    for c in named:
        for key in c.streets or ():
            by_street[key].add(c.area_id)
    fallback = sorted({c.area_id for c in clauses if c.fallback})

    result: dict = {}
    if by_street:
        result["streets"] = {k: sorted(v) for k, v in sorted(by_street.items())}
    if len(whole) == 1:
        result["area"] = whole[0]
    elif len(whole) > 1:
        result["candidates"] = whole
    elif len(fallback) == 1:
        result["area"] = fallback[0]
    elif len(fallback) > 1:
        result["candidates"] = fallback
    return result or None


def build_locations(registry: Registry, areas: list[Area]) -> tuple[list[dict], dict]:
    index = Index(registry)
    per_settlement: dict[int, dict[Kind, list[Clause]]] = defaultdict(lambda: defaultdict(list))
    variants: dict[int, dict[str, str]] = defaultdict(dict)
    whole_rules: dict[Kind, list[tuple[str, set[int], str]]] = defaultdict(list)
    unmatched: list[str] = []
    served: set[str] = set()

    for area in areas:
        wholes: list = []
        if area.kind == "household":
            found = household_clauses(index, area, variants)
            if area.district and (district := index.district(area.district)):
                served.add(district)
        else:
            found, wholes = listed_clauses(index, area)
            whole_rules[area.kind] += [(d, ex, area.id) for d, ex in wholes]
        if not found and not wholes:
            unmatched.append(f"{area.kind}: {area.name[:80]}")
        for settlement, clause in found:
            per_settlement[settlement.code][area.kind].append(clause)

    locations = []
    stats: dict[str, int] = defaultdict(int)
    for settlement in registry.settlements:
        if settlement.district not in served:
            continue
        clauses = per_settlement[settlement.code]
        for kind, rules in whole_rules.items():
            for district, excluded, area_id in rules:
                if district == settlement.district and settlement.code not in excluded:
                    clauses[kind].append(Clause(area_id, None, fallback=True))

        schedule = {kind: r for kind in KINDS if (r := resolve(clauses.get(kind, [])))}
        street_keys = {k for r in schedule.values() for k in r.get("streets", {})}
        location: dict = {
            "id": f"g{settlement.code}",
            "name": settlement.name,
            "type": settlement.abbr,
            "district": settlement.district,
        }
        if street_keys:
            # The user needs to pick a street only where some schedule splits by street.
            location["streets"] = [[street_key(t), t.label] for t in settlement.streets] + [
                [key, label] for key, label in sorted(variants[settlement.code].items())
            ]
        if schedule:
            location["schedule"] = schedule
        locations.append(location)

        for kind in KINDS:
            r = schedule.get(kind)
            state = (
                "none"
                if not r
                else "single"
                if "area" in r and not r.get("streets")
                else ("byStreet" if r.get("streets") else "ambiguous")
            )
            stats[f"{kind}.{state}"] += 1

    stats["locations"] = len(locations)
    stats["unmatchedRows"] = len(unmatched)
    return locations, {"stats": dict(sorted(stats.items())), "unmatched": unmatched}

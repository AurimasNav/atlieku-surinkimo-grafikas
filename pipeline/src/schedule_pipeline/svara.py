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
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import snapshot
from .addresses import AddressPoint
from .http import ATTEMPTS, USER_AGENT
from .model import SCHEMA_VERSION, clean_text
from .registry import ATTRIBUTION, Registry, fold

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


def build(content: bytes, today: date) -> tuple[dict, dict[str, dict], list[str]]:
    """Returns (schedule.json, {eldership slug: addresses file}, warnings)."""
    reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
    rows = [[clean_text(c) for c in row] for row in reader if len(row) == 9]
    rows = [row for row in rows if row[0] == MUNICIPALITY]
    if len(rows) < MIN_ROWS:
        raise ValidationError(f"only {len(rows)} rows for {MUNICIPALITY}")

    # Some rows have no eldership: take it from other rows of the same town.
    town_eldership = {row[2]: row[1] for row in rows if row[1]}
    schedules: dict[str, Schedule] = {}
    # eldership -> town -> street -> house -> schedule ids
    index: dict[str, dict[str, dict[str, dict[str, set[str]]]]] = {}
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

    files: dict[str, dict] = {}
    elderships = []
    for eldership in sorted(index, key=str.casefold):
        towns = index[eldership]
        name = slug(eldership)
        while name in files:  # two elderships with the same ASCII name
            name += "-2"
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
        elderships.append({"id": name, "name": eldership, "towns": sorted(towns, key=str.casefold)})

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
    settlements: dict[str, list] = {}
    for settlement in registry.settlements:
        settlements.setdefault(fold(f"{settlement.genitive} {settlement.abbr}"), []).append(
            settlement
        )
    by_settlement: dict[int, dict[tuple[int | None, str], AddressPoint]] = {}
    for point in points:
        by_settlement.setdefault(point.settlement, {})[(point.street, _house(point.number))] = point

    def street_code(settlement, street: str) -> int | None:
        wanted = fold(street)
        for candidate in settlement.streets:
            words = fold(f"{candidate.name} {candidate.abbr}").split()
            # "J. Biliūno g." in the file is "Jono Biliūno g." in the register.
            if wanted in (" ".join(words), " ".join([words[0][0], *words[1:]])):
                return candidate.code
        return None

    places: list[list[str]] = []
    rows = []
    missing = 0
    for file_name, data in files.items():
        for town, streets in data["towns"].items():
            candidates = settlements.get(fold(town), [])
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
                        code = street_code(settlement, street) if street else None
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
    try:
        dataset, files, warnings = build(content, date.today())
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    write(args.out, dataset, files)

    # Coordinates come from a snapshot of the Address Register (see snapshot.py); without it the
    # app still works, only "use my location" doesn't find Kauno r. addresses.
    located = ""
    if snapshot.KAUNO_REGISTRY_FILE.exists() and snapshot.KAUNO_ADDRESSES_FILE.exists():
        registry, _ = snapshot.load_registry(snapshot.KAUNO_REGISTRY_FILE)
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
    sizes = sorted((args.out / "addresses").glob("*.json"), key=lambda p: p.stat().st_size)
    lines = [
        "## Kauno r. (Kauno švara)",
        "",
        f"- {stats['rows']} containers at {stats['addresses']} addresses in {stats['towns']} towns",
        f"- schedules: {', '.join(f'{count} {kind}' for kind, count in stats['areas'].items())}",
        f"- {len(files)} address files, largest {sizes[-1].stat().st_size // 1024} KB"
        f" ({sizes[-1].name})",
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

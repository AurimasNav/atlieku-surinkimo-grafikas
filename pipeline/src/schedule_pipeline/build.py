"""Entry point: scrape each provider's page, parse every schedule file, validate, write
schedule.json and addresses.json.

Vilniaus rajonas has two companies, each with its own part of schedule.json (model.Provider):
UAB „Nemenčinės komunalininkas“ (scrape.py) and UAB „Nemėžio komunalininkas“ (nemezio.py). A
part whose source is down or changed its format is replaced with the same part of the data
published yesterday, so one company's problem doesn't hold back the other's data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import addresses as address_points
from . import http, nemezio, scrape, snapshot
from . import registry as address_register
from .locations import build_locations
from .model import SCHEMA_VERSION, Area, Kind, ParseResult, Provider, SourceFile
from .pdf_parser import parse_pdf
from .registry import Registry
from .scrape import PAGE_URL, fetch, find_schedule_files
from .xlsx_parser import DEFAULT_GROUP, parse_xlsx

# Fewer areas than this means the format changed and the parser missed rows.
MIN_AREAS: dict[Kind, int] = {"household": 100, "packaging": 10, "glass": 10}
KINDS: tuple[Kind, ...] = ("household", "packaging", "glass", "food", "green")
# Share of household rows that must link to a register settlement; below it, matching broke.
MIN_LINKED_HOUSEHOLD = 0.85
# Served settlements had ~50k addresses in 2026; far fewer means the download went wrong.
MIN_ADDRESS_POINTS = 20_000
# Yesterday's data, for the part of a provider whose build fails today.
PUBLISHED_URL = "https://aurimasnav.github.io/atlieku-surinkimo-grafikas"


class ValidationError(Exception):
    pass


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    if source.file_name.lower().endswith(".xlsx"):
        return parse_xlsx(content, source.kind, source.file_name)
    if source.file_name.lower().endswith(".pdf"):
        return parse_pdf(content, source.kind, source.file_name)
    raise ValueError(f"unsupported file type: {source.file_name}")


Download = Callable[[date, int], tuple[list[tuple[SourceFile, bytes]], list[str]]]


def download_nemencine(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list]:
    html = fetch(PAGE_URL).decode("utf-8", errors="replace")
    return [(f, fetch(f.url)) for f in find_schedule_files(html)], []


@dataclass(frozen=True)
class Source:
    """How to build one provider's part of the data."""

    provider: Provider
    download: Download
    parse: Callable[[SourceFile, bytes], ParseResult]
    min_areas: dict[Kind, int]
    # Settlements that must get a household schedule.
    min_household_places: int = 0
    # Kinds of schedule in a file of each kind, where a file has more than one.
    file_kinds: dict[Kind, tuple[Kind, ...]] = field(default_factory=dict)
    # Joins the parsed files' rows in place before they are merged (tratc.combine: this year's
    # routes and the next's); returns warnings.
    combine: Callable[[list[tuple[SourceFile, ParseResult]], Registry, date], list[str]] | None = (
        None
    )


NEMENCINE = Source(scrape.PROVIDER, download_nemencine, parse_file, MIN_AREAS)
NEMEZIO = Source(
    nemezio.PROVIDER,
    nemezio.download,
    nemezio.parse_file,
    nemezio.MIN_AREAS,
    nemezio.MIN_HOUSEHOLD_PLACES,
    nemezio.FILE_KINDS,
)
SOURCES = (NEMENCINE, NEMEZIO)


def merge_areas(areas: list[Area]) -> list[Area]:
    """Combines rows with identical text from different periods (e.g. two quarterly PDFs)."""
    merged: dict[str, Area] = {}
    for area in areas:
        existing = merged.get(area.id)
        if existing:
            existing.dates |= area.dates
            existing.note = existing.note or area.note
        else:
            merged[area.id] = area
    return list(merged.values())


def current_rows(parsed: list[tuple[SourceFile, ParseResult]], today: date) -> set[str]:
    """Ids of the rows in the newest schedule of each kind: the files that still run past today,
    or, between the end of one period and the publication of the next, the latest ones."""
    ends: dict[tuple[Kind, str, str], list[tuple[date, ParseResult]]] = {}
    for source, result in parsed:
        dates = [d for a in result.areas for d in a.dates]
        if dates:
            # Each municipality's files on their own (sratc: one is late with next year's), and
            # each group's (aratc: Druskininkai's farmsteads).
            key = (source.kind, source.municipality, source.group)
            ends.setdefault(key, []).append((max(dates), result))
    ids: set[str] = set()
    for files in ends.values():
        latest = max(end for end, _ in files)
        for end, result in files:
            if end >= today or end == latest:
                ids |= {a.id for a in result.areas}
    return ids


def drop_old_dates(areas: list[Area], cutoff: date, keep: set[str] = frozenset()) -> list[Area]:
    """Drops dates before `cutoff`. Rows in `keep` stay with at least their last date, so the
    app can tell their place is served and when the last pickup was."""
    result = []
    for area in areas:
        recent = {d for d in area.dates if d >= cutoff}
        if not recent and area.id in keep and area.dates:
            recent = {max(area.dates)}
        area.dates = recent
        if area.dates or area.note:
            result.append(area)
    return result


def validate(areas: list[Area], kinds: set[str], min_areas: dict[Kind, int] = MIN_AREAS) -> None:
    """`kinds`: the kinds of schedule the files found on the page have."""
    problems = []
    for kind, minimum in min_areas.items():
        if kind not in kinds:
            problems.append(f"no {kind} schedule file found on the page")
            continue
        count = sum(1 for a in areas if a.kind == kind)
        if count < minimum:
            problems.append(f"only {count} {kind} areas parsed (expected at least {minimum})")
    if problems:
        raise ValidationError("; ".join(problems))


def coverage(areas: list[dict]) -> dict[str, dict[str, str]]:
    result = {}
    for kind in KINDS:
        dates = [d for a in areas if a["kind"] == kind for d in a["dates"]]
        if dates:
            result[kind] = {"from": min(dates), "to": max(dates)}
    return result


def _area_order(area: dict) -> tuple:
    # Individual houses first: most users live in one, and the picker shows rows in this order.
    group = area.get("group") or DEFAULT_GROUP
    return (
        area["kind"],
        group != DEFAULT_GROUP,
        area.get("district") or "",
        area["name"].casefold(),
    )


def build_dataset(
    sources: list[tuple[SourceFile, bytes]],
    registry: Registry,
    today: date,
    keep_days: int,
    source: Source = NEMENCINE,
) -> tuple[dict, list[str]]:
    """One provider's part: the same shape as schedule.json, with only its rows and places."""
    provider = source.provider
    parsed = [(file, source.parse(file, content)) for file, content in sources]
    areas = [area for _, result in parsed for area in result.areas]
    warnings = [warning for _, result in parsed for warning in result.warnings]
    if source.combine:
        warnings += source.combine(parsed, registry, today)
        areas = [area for _, result in parsed for area in result.areas]

    current_ids = current_rows(parsed, today)
    areas = drop_old_dates(merge_areas(areas), today - timedelta(days=keep_days), current_ids)
    for area in areas:
        area.current = area.id in current_ids
    files = [file for file, _ in sources]
    kinds = {k for f in files for k in source.file_kinds.get(f.kind, (f.kind,))}
    validate(areas, kinds, source.min_areas)

    # Only rows of the newest schedules take part in matching, so old periods can't create
    # ambiguity, and places stay linked between two pickups.
    current = [a for a in areas if a.current]
    locations, report = build_locations(registry, current, provider)
    household = [a for a in current if a.kind == "household"]
    unmatched_household = sum(1 for u in report["unmatched"] if u.startswith("household:"))
    if household and 1 - unmatched_household / len(household) < MIN_LINKED_HOUSEHOLD:
        raise ValidationError(
            f"only {len(household) - unmatched_household}/{len(household)} household rows "
            "matched an Address Register settlement"
        )
    places = sum(1 for loc in locations if "household" in loc.get("schedule", {}))
    if places < source.min_household_places:
        raise ValidationError(
            f"only {places} settlements got a household schedule "
            f"(expected at least {source.min_household_places})"
        )
    warnings += [f"not linked to any settlement: {u}" for u in report["unmatched"]]
    whole_municipality = provider.route_town or provider.settlement_rows or provider.section_town
    whole_municipality = whole_municipality or provider.reader
    unknown = "a settlement or a street" if whole_municipality else "a settlement of the eldership"
    warnings += [f"not {unknown}: {u}" for u in report.get("unknownPlaces", [])]

    rows = sorted((a.to_json() for a in areas), key=_area_order)
    dataset = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": provider.url,
        "addressSource": address_register.ATTRIBUTION,
        "files": [_file_json(f, provider) for f in files],
        "coverage": coverage(rows),
        "matching": report["stats"],
        "areas": rows,
        "locations": locations,
    }
    return dataset, warnings


def _file_json(file: SourceFile, provider: Provider) -> dict:
    data = {"kind": file.kind, "name": file.file_name, "url": file.url}
    if not provider.legacy:
        data["provider"] = provider.id
    return data


# --- several providers in one file -----------------------------------------------


def _is_mine(item: dict, provider: Provider) -> bool:
    """Rows, places and files of the first provider have no `provider` field."""
    return item.get("provider") == (None if provider.legacy else provider.id)


def published_part(published: dict, provider: Provider) -> dict | None:
    """A provider's part of the data published before, or None if it had none."""
    entry = next((p for p in published.get("providers", []) if p["id"] == provider.id), None)
    if entry is None and provider.legacy:
        entry = published  # published before there were several providers
    if entry is None:
        return None
    areas = [a for a in published["areas"] if _is_mine(a, provider)]
    if not areas:
        return None
    return {
        "schemaVersion": published["schemaVersion"],
        "generatedAt": entry["generatedAt"],
        "source": provider.url,
        "addressSource": published.get("addressSource", address_register.ATTRIBUTION),
        "files": [f for f in published.get("files", []) if _is_mine(f, provider)],
        "coverage": entry.get("coverage", {}),
        "matching": entry.get("matching", {}),
        "areas": areas,
        "locations": [loc for loc in published.get("locations", []) if _is_mine(loc, provider)],
        "warnings": entry.get("warnings", 0),
    }


def merge_parts(parts: list[tuple[Provider, dict]], source: str = PAGE_URL) -> dict:
    """schedule.json from the providers' parts. `source`, `files`, `coverage` and `matching`
    keep their meaning for the first provider's data; `providers` has each part's own."""
    providers = [
        {
            **provider.to_json(),
            "generatedAt": part["generatedAt"],
            "coverage": part["coverage"],
            "matching": part["matching"],
            "warnings": part.get("warnings", 0),
        }
        for provider, part in parts
    ]
    areas = sorted((a for _, part in parts for a in part["areas"]), key=_area_order)
    # Each part is in the register's order; a stable sort keeps it for places of the same name.
    locations = sorted(
        (loc for _, part in parts for loc in part["locations"]),
        key=lambda loc: (loc["district"], loc["name"]),
    )
    matching: dict[str, int] = {}
    for _, part in parts:
        for key, value in part["matching"].items():
            matching[key] = matching.get(key, 0) + value
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": source,
        "addressSource": address_register.ATTRIBUTION,
        "providers": providers,
        "files": [f for _, part in parts for f in part["files"]],
        "coverage": coverage(areas),
        "matching": dict(sorted(matching.items())),
        "areas": areas,
        "locations": locations,
        "warnings": sum(p["warnings"] for p in providers),
    }


@dataclass
class PartResult:
    provider: Provider
    part: dict | None
    warnings: list[str]
    # Why today's build of this part failed; the part is then yesterday's (or missing).
    error: str | None = None


def build_parts(
    sources: tuple[Source, ...],
    registry: Registry,
    today: date,
    keep_days: int,
    load_published: Callable[[], dict] | None,
) -> list[PartResult]:
    """Builds each provider's part. One that fails is replaced with its part of the published
    data (`load_published`; None: fail instead). Raises if a part can't be built or replaced
    and dropping it would take published data away from users."""
    results: list[PartResult] = []
    published: dict | None = None
    for source in sources:
        provider = source.provider
        try:
            files, download_warnings = source.download(today, keep_days)
            part, warnings = build_dataset(files, registry, today, keep_days, source)
            warnings = download_warnings + warnings
            part["warnings"] = len(warnings)
            results.append(PartResult(provider, part, warnings))
            continue
        except Exception as error:  # any failure of one source must not stop the others
            if load_published is None:
                raise
            traceback.print_exc()
            reason = f"{type(error).__name__}: {error}"
        if published is None:
            # Without yesterday's data we can't tell whether dropping the part takes data
            # away from users: fail, and the site keeps everything it has.
            published = load_published()
        kept = published_part(published, provider)
        if kept is None and provider.legacy:
            raise ValidationError(f"{provider.name}: {reason}; no published data to keep")
        results.append(PartResult(provider, kept, [], reason))
    return results


def load_published(base_url: str) -> Callable[[], dict]:
    def load() -> dict:
        return json.loads(http.get(f"{base_url}/schedule.json", timeout=60))

    return load


def write_summary(
    dataset: dict,
    results: list[PartResult],
    notes: list[str],
    title: str = "Schedule data",
    file_name: str = "schedule.json",
) -> None:
    lines = [f"## {title}", ""]
    for result in results:
        lines += _part_summary(result)
    if notes:
        lines += ["### Notes", ""] + [f"- {n}" for n in notes] + [""]
    lines.append(
        f"{file_name}: {len(dataset['locations'])} settlements, {len(dataset['areas'])} rows"
    )
    text = "\n".join(lines) + "\n"
    print(text)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)


def _part_summary(result: PartResult) -> list[str]:
    provider, part = result.provider, result.part
    lines = [f"### {provider.name}", ""]
    if result.error:
        state = f"published data from {part['generatedAt']} kept" if part else "left out"
        lines += [f"**Today's build failed ({state}):** {result.error}", ""]
    if part is None:
        return lines
    counts: dict[str, int] = {}
    for area in part["areas"]:
        counts[area["kind"]] = counts.get(area["kind"], 0) + 1
    for kind, count in counts.items():
        span = part["coverage"].get(kind, {})
        lines.append(f"- **{kind}**: {count} areas, {span.get('from')} → {span.get('to')}")
    stats = part["matching"]
    lines += ["", f"#### Locations ({stats.get('locations', 0)} settlements)", ""]
    lines += ["| | single row | by street | ask user | not in schedule |", "|---|---|---|---|---|"]
    for kind in provider.kinds:
        cells = [
            str(stats.get(f"{kind}.{s}", 0)) for s in ("single", "byStreet", "ambiguous", "none")
        ]
        lines.append(f"| {kind} | " + " | ".join(cells) + " |")
    if result.warnings:
        lines += ["", f"#### {len(result.warnings)} warnings", ""]
        lines += [f"- {w}" for w in result.warnings]
    return lines + [""]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="where to write schedule.json")
    parser.add_argument(
        "--keep-days",
        type=int,
        default=31,
        help="drop pickup dates older than this many days",
    )
    parser.add_argument(
        "--published",
        default=PUBLISHED_URL,
        help="site with yesterday's schedule.json, for the part of a provider whose build fails",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any provider's build fails instead of keeping its published part",
    )
    args = parser.parse_args(argv)

    registry, registry_note = live_or_snapshot(
        "Address Register", address_register.fetch, snapshot.load_registry
    )
    points, points_note = live_or_snapshot(
        "Address points", address_points.fetch, snapshot.load_points
    )
    loader = None if args.strict else load_published(args.published)
    try:
        results = build_parts(SOURCES, registry, date.today(), args.keep_days, loader)
        parts = [(r.provider, r.part) for r in results if r.part]
        dataset = merge_parts(parts)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < MIN_ADDRESS_POINTS:
            raise ValidationError(f"only {len(addresses['points'])} address points")
    except (ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    for r in results:
        if r.error:
            if r.part:
                kept = f"the data published on {r.part['generatedAt'][:10]} is kept"
            else:
                kept = "there is no published data to keep, so it is left out"
            # An annotation on the workflow run.
            print(f"::warning::The {r.provider.name} build failed; {kept}. {r.error}")

    notes = [n for n in (registry_note, points_note) if n]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    # Downloaded by the app only when the user asks to find their address by GPS.
    (args.out.parent / "addresses.json").write_text(
        json.dumps(addresses, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    write_summary(dataset, results, notes)
    return 0


def live_or_snapshot(name, fetch_live, load_snapshot):
    """Live data if the source answers; otherwise the committed snapshot (the register's sites
    block cloud servers such as GitHub Actions). Returns (data, note for the job summary)."""
    try:
        return fetch_live(), None
    except OSError as error:  # urllib errors, timeouts and connection failures
        data, taken_at = load_snapshot()
        age = snapshot.age_days(taken_at, date.today())
        note = (
            f"{name}: live source unavailable ({error}); "
            f"used the snapshot from {taken_at} ({age} days old)"
        )
        if age > snapshot.MAX_AGE_DAYS:
            note += (
                " - please refresh it: cd pipeline && uv run python -m schedule_pipeline.snapshot"
            )
        print(note, file=sys.stderr)
        return data, note


if __name__ == "__main__":
    sys.exit(main())

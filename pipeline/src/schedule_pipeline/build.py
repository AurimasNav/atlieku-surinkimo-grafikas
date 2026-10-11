"""Entry point: scrape the page, parse every schedule file, validate, write schedule.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import addresses as address_points
from . import registry as address_register
from .locations import build_locations
from .model import SCHEMA_VERSION, Area, Kind, ParseResult, SourceFile
from .pdf_parser import parse_pdf
from .registry import Registry
from .scrape import PAGE_URL, fetch, find_schedule_files
from .xlsx_parser import DEFAULT_GROUP, parse_xlsx

# Fewer areas than this means the format changed and the parser missed rows.
MIN_AREAS: dict[Kind, int] = {"household": 100, "packaging": 10, "glass": 10}
# Share of household rows that must link to a register settlement; below it, matching broke.
MIN_LINKED_HOUSEHOLD = 0.85
# Served settlements had ~50k addresses in 2026; far fewer means the download went wrong.
MIN_ADDRESS_POINTS = 20_000


class ValidationError(Exception):
    pass


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    if source.file_name.lower().endswith(".xlsx"):
        return parse_xlsx(content, source.kind, source.file_name)
    if source.file_name.lower().endswith(".pdf"):
        return parse_pdf(content, source.kind, source.file_name)
    raise ValueError(f"unsupported file type: {source.file_name}")


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


def drop_old_dates(areas: list[Area], cutoff: date) -> list[Area]:
    result = []
    for area in areas:
        area.dates = {d for d in area.dates if d >= cutoff}
        if area.dates or area.note:
            result.append(area)
    return result


def validate(areas: list[Area], files: list[SourceFile]) -> None:
    problems = []
    for kind, minimum in MIN_AREAS.items():
        if not any(f.kind == kind for f in files):
            problems.append(f"no {kind} schedule file found on the page")
            continue
        count = sum(1 for a in areas if a.kind == kind)
        if count < minimum:
            problems.append(f"only {count} {kind} areas parsed (expected at least {minimum})")
    if problems:
        raise ValidationError("; ".join(problems))


def coverage(areas: list[Area]) -> dict[str, dict[str, str]]:
    result = {}
    for kind in MIN_AREAS:
        dates = [d for a in areas if a.kind == kind for d in a.dates]
        if dates:
            result[kind] = {"from": min(dates).isoformat(), "to": max(dates).isoformat()}
    return result


def build_dataset(
    sources: list[tuple[SourceFile, bytes]], registry: Registry, today: date, keep_days: int
) -> tuple[dict, list[str]]:
    areas: list[Area] = []
    warnings: list[str] = []
    for source, content in sources:
        result = parse_file(source, content)
        areas.extend(result.areas)
        warnings.extend(result.warnings)

    areas = drop_old_dates(merge_areas(areas), today - timedelta(days=keep_days))
    files = [source for source, _ in sources]
    validate(areas, files)
    # Individual houses first: most users live in one, and the picker shows rows in this order.
    areas.sort(
        key=lambda a: (
            a.kind,
            (a.group or DEFAULT_GROUP) != DEFAULT_GROUP,
            a.district or "",
            a.name.casefold(),
        )
    )

    # Only rows that still matter take part in matching, so old periods can't create ambiguity.
    current = [a for a in areas if a.note or (a.dates and max(a.dates) >= today)]
    locations, report = build_locations(registry, current)
    household = [a for a in current if a.kind == "household"]
    unmatched_household = sum(1 for u in report["unmatched"] if u.startswith("household:"))
    if household and 1 - unmatched_household / len(household) < MIN_LINKED_HOUSEHOLD:
        raise ValidationError(
            f"only {len(household) - unmatched_household}/{len(household)} household rows "
            "matched an Address Register settlement"
        )
    warnings += [f"not linked to any settlement: {u}" for u in report["unmatched"]]

    dataset = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": PAGE_URL,
        "addressSource": address_register.ATTRIBUTION,
        "files": [{"kind": f.kind, "name": f.file_name, "url": f.url} for f in files],
        "coverage": coverage(areas),
        "matching": report["stats"],
        "areas": [a.to_json() for a in areas],
        "locations": locations,
    }
    return dataset, warnings


def write_summary(dataset: dict, warnings: list[str]) -> None:
    counts: dict[str, int] = {}
    for area in dataset["areas"]:
        counts[area["kind"]] = counts.get(area["kind"], 0) + 1
    lines = ["## Schedule data", ""]
    for kind, count in counts.items():
        span = dataset["coverage"].get(kind, {})
        lines.append(f"- **{kind}**: {count} areas, {span.get('from')} → {span.get('to')}")
    stats = dataset["matching"]
    lines += ["", f"### Locations ({stats['locations']} settlements)", ""]
    lines += ["| | single row | by street | ask user | not in schedule |", "|---|---|---|---|---|"]
    for kind in MIN_AREAS:
        cells = [
            str(stats.get(f"{kind}.{s}", 0)) for s in ("single", "byStreet", "ambiguous", "none")
        ]
        lines.append(f"| {kind} | " + " | ".join(cells) + " |")
    if warnings:
        lines += ["", f"### {len(warnings)} warnings", ""]
        lines += [f"- {w}" for w in warnings]
    text = "\n".join(lines) + "\n"
    print(text)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="where to write schedule.json")
    parser.add_argument(
        "--keep-days",
        type=int,
        default=31,
        help="drop pickup dates older than this many days",
    )
    args = parser.parse_args(argv)

    html = fetch(PAGE_URL).decode("utf-8", errors="replace")
    files = find_schedule_files(html)
    sources = [(f, fetch(f.url)) for f in files]
    registry = address_register.fetch()
    points = address_points.fetch()
    try:
        dataset, warnings = build_dataset(sources, registry, date.today(), args.keep_days)
        served = {loc["id"] for loc in dataset["locations"]}
        addresses = address_points.build_addresses(points, registry, served, dataset["generatedAt"])
        if len(addresses["points"]) < MIN_ADDRESS_POINTS:
            raise ValidationError(f"only {len(addresses['points'])} address points")
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    # Downloaded by the app only when the user asks to find their address by GPS.
    (args.out.parent / "addresses.json").write_text(
        json.dumps(addresses, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    write_summary(dataset, warnings)
    return 0


if __name__ == "__main__":
    sys.exit(main())

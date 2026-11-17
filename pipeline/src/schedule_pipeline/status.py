"""Publishes the state of the data for monitoring: status.json and metrics.txt.

When a source changes its format, the build of that source fails and the data published
yesterday stays online. Nothing breaks for users right away, so the signal to watch is the age
of the data: `generatedAt` stops moving. This step reads the files about to be published and
writes

    <site>/status.json   the same numbers as JSON
    <site>/metrics.txt   Prometheus text format, scraped straight from GitHub Pages

Run after the builds: python -m schedule_pipeline.status --site ../site
See docs/monitoring.md for the scrape job and alert rules.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

FIRST = "nemencine"  # the source of schedule.json rows without a `provider`


def _timestamp(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def collect(site: Path) -> dict:
    """What each source published: when, how much, and how many warnings."""
    sources: dict[str, dict] = {}
    path = site / "schedule.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        # Vilniaus r.: one file, a part per company (build.merge_parts). Rows and places of the
        # first company, Nemenčinė, have no `provider` field, nor has data from before there
        # were several.
        providers = data.get("providers") or [
            {"id": FIRST, "generatedAt": data["generatedAt"], "warnings": data.get("warnings", 0)}
        ]
        for provider in providers:
            mine = provider["id"]
            areas = [a for a in data["areas"] if a.get("provider", FIRST) == mine]
            places = [p for p in data.get("locations", []) if p.get("provider", FIRST) == mine]
            sources[mine] = {
                "generatedAt": provider["generatedAt"],
                "areas": dict(sorted(Counter(a["kind"] for a in areas).items())),
                "places": len(places),
                "warnings": provider.get("warnings", 0),
            }
    path = site / "kauno-r" / "schedule.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        sources["kauno"] = {
            "generatedAt": data["generatedAt"],
            "areas": data["stats"]["areas"],
            "places": data["stats"]["addresses"],
            "warnings": data.get("warnings", 0),
        }
    return {"checkedAt": datetime.now(UTC).isoformat(timespec="seconds"), "sources": sources}


def metrics(status: dict) -> str:
    """Prometheus text exposition format."""
    series = {
        "siuksliaveze_data_generated_timestamp_seconds": (
            "When the published data of a source was built (Unix time).",
            [({"source": s}, _timestamp(d["generatedAt"])) for s, d in status["sources"].items()],
        ),
        "siuksliaveze_data_areas": (
            "Schedules (groups of addresses with the same pickup days) per waste type.",
            [
                ({"source": s, "kind": kind}, count)
                for s, d in status["sources"].items()
                for kind, count in d["areas"].items()
            ],
        ),
        "siuksliaveze_data_places": (
            "Settlements (nemencine, nemezio) or addresses (kauno) the data covers.",
            [({"source": s}, d["places"]) for s, d in status["sources"].items()],
        ),
        "siuksliaveze_data_warnings": (
            "Warnings of the last build, e.g. rows that couldn't be linked to a settlement.",
            [({"source": s}, d["warnings"]) for s, d in status["sources"].items()],
        ),
        "siuksliaveze_status_checked_timestamp_seconds": (
            "When this file was written, by the daily job (Unix time).",
            [({}, _timestamp(status["checkedAt"]))],
        ),
    }
    lines = []
    for name, (help_text, samples) in series.items():
        lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
        for labels, value in samples:
            text = ",".join(f'{key}="{val}"' for key, val in labels.items())
            lines.append(f"{name}{{{text}}} {value}" if text else f"{name} {value}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", type=Path, required=True, help="directory that is published")
    args = parser.parse_args(argv)
    status = collect(args.site)
    if not status["sources"]:
        print("No data files found", file=sys.stderr)
        return 1
    (args.site / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.site / "metrics.txt").write_text(metrics(status), encoding="utf-8")
    print(metrics(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

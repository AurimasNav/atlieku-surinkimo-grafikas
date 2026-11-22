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
    # Vilniaus r., then Mažeikių r. (schedule_pipeline.tratc), Klaipėdos r.
    # (schedule_pipeline.gargzdu), Jurbarko r. (schedule_pipeline.taurage) and the five
    # municipalities of Šiaulių RATC (schedule_pipeline.sratc): the same format. Alytaus RATC's
    # six municipalities (schedule_pipeline.aratc) too, as one source, "alytus".
    # mazeikiu-r also has Telšių r., Plungės r. and Rietavo sav., a provider each; sratc has
    # Radviliškio r. next to the five ("radviliskis"); panevezio-ratc (schedule_pipeline.pratc)
    # a provider for each of its four municipalities; maatc the five municipalities of
    # Marijampolė county (schedule_pipeline.maatc), a provider each; silutes-r and ecoservice
    # (schedule_pipeline.ecoservice) Šilutės r., and Trakų r. and Šalčininkų r., a provider each;
    # kedainiu-r Kėdainių r. (schedule_pipeline.kedainiai), "kedainiai".
    # jurbarko-r also has Tauragės r., Šilalės r. and Pagėgių sav., a provider each.
    # raseiniu-r (schedule_pipeline.raseiniai) and jonavos-r (schedule_pipeline.jonava): a
    # provider each.
    # kretingos-r is Kretingos r. (schedule_pipeline.kretinga), "kretinga".
    # moletu-r is Molėtų r. (schedule_pipeline.moletai), "moletai".
    # skuodo-r is Skuodo r. (schedule_pipeline.skuodas), "skuodas".
    # ukmerges-r is Ukmergės r. (schedule_pipeline.ukmerge), "ukmerge".
    # anyksciu-r is Anykščių r. (schedule_pipeline.anyksciai), "anyksciai".
    # utenos-r is Utenos r. (schedule_pipeline.utena), "utena".
    # ignalinos-r is Ignalinos r. (schedule_pipeline.ignalina), "ignalina".
    # elektrenu-sav is Elektrėnų sav. (schedule_pipeline.elektrenai), "elektrenai".
    # sirvintu-r is Širvintų r. (schedule_pipeline.sirvintos), "sirvintos".
    for path in (
        site / "schedule.json",
        site / "mazeikiu-r" / "schedule.json",
        site / "klaipedos-r" / "schedule.json",
        site / "jurbarko-r" / "schedule.json",
        site / "sratc" / "schedule.json",
        site / "alytaus-ratc" / "schedule.json",
        site / "panevezio-ratc" / "schedule.json",
        site / "maatc" / "schedule.json",
        site / "raseiniu-r" / "schedule.json",
        site / "jonavos-r" / "schedule.json",
        site / "kretingos-r" / "schedule.json",
        site / "silutes-r" / "schedule.json",
        site / "ecoservice" / "schedule.json",
        site / "kedainiu-r" / "schedule.json",
        site / "moletu-r" / "schedule.json",
        site / "skuodo-r" / "schedule.json",
        site / "ukmerges-r" / "schedule.json",
        site / "anyksciu-r" / "schedule.json",
        site / "utenos-r" / "schedule.json",
        site / "ignalinos-r" / "schedule.json",
        site / "elektrenu-sav" / "schedule.json",
        site / "sirvintu-r" / "schedule.json",
    ):
        if not path.exists():
            continue
        # Mažeikių r., Klaipėdos r., Jurbarko r. and Šiaulių RATC list every settlement of their
        # municipalities: count those with a schedule, so the number moves when rows are lost.
        served_only = path.parent != site
        data = json.loads(path.read_text(encoding="utf-8"))
        # Vilniaus r.: one file, a part per company (build.merge_parts). Rows and places of the
        # first company, Nemenčinė, have no `provider` field, nor has data from before there
        # were several.
        providers = data.get("providers") or [
            {
                "id": FIRST,
                "generatedAt": data["generatedAt"],
                "warnings": data.get("warnings", 0),
            }
        ]
        for provider in providers:
            mine = provider["id"]
            areas = [a for a in data["areas"] if a.get("provider", FIRST) == mine]
            places = [p for p in data.get("locations", []) if p.get("provider", FIRST) == mine]
            sources[mine] = {
                "generatedAt": provider["generatedAt"],
                "areas": dict(sorted(Counter(a["kind"] for a in areas).items())),
                "places": sum(1 for p in places if p.get("schedule") or not served_only),
                "warnings": provider.get("warnings", 0),
                # The last pickup date per waste type: the schedules run out when the
                # publisher doesn't post the next period.
                "lastDate": {
                    kind: max(dates)
                    for kind in sorted({a["kind"] for a in areas})
                    if (
                        dates := [d for a in areas if a["kind"] == kind for d in a.get("dates", [])]
                    )
                },
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
        # The other municipalities of Kauno švara's file, published with Kauno r. (Kaišiadorių
        # r.: "kaisiadorys"): built together, counted apart.
        for part in data.get("otherMunicipalities", []):
            sources[part["id"]] = {
                "generatedAt": data["generatedAt"],
                "areas": part["stats"]["areas"],
                "places": part["stats"]["addresses"],
                "warnings": part["warnings"],
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
        "siuksliaveze_data_last_date_timestamp_seconds": (
            "The last pickup date the published schedules of a source have, per waste type.",
            [
                ({"source": s, "kind": kind}, _timestamp(f"{day}T00:00:00+00:00"))
                for s, d in status["sources"].items()
                for kind, day in d.get("lastDate", {}).items()
            ],
        ),
        "siuksliaveze_data_places": (
            "Settlements (nemencine, nemezio, mazeikiai, telsiai, plunge, rietavas, klaipedos, "
            "jurbarkas, taurage, silale, pagegiai, siauliai, radviliskis, alytus, pasvalys, "
            "rokiskis, birzai, panevezio-r, marijampole, vilkaviskis, kalvarija, kazluruda, "
            "sakiai, raseiniai, jonava, kretinga, silute, trakai, salcininkai, kedainiai, "
            "moletai, skuodas, ukmerge, anyksciai, utena, ignalina, elektrenai, sirvintos) or "
            "addresses (kauno, kaisiadorys) the data covers.",
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

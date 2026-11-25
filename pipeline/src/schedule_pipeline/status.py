"""Publishes the state of the data for monitoring: status.json and metrics.txt.

When a source changes its format, the build of that source fails and the data published
yesterday stays online. Nothing breaks for users right away, so the signal to watch is the age
of the data: `generatedAt` stops moving. This step reads the files about to be published and
writes

    <site>/status.json     the same numbers as JSON
    <site>/metrics.txt     Prometheus text format, scraped straight from GitHub Pages
    <site>/warnings.html   every source's build warnings, those pipeline/known-warnings.json
                           doesn't list first (the page the new-warnings alert links)
    <site>/warnings.json   the same as JSON

Run after the builds: python -m schedule_pipeline.status --site ../site
After checking that the new warnings of a build are harmless (or to start a new source's list),
acknowledge them: python -m schedule_pipeline.status --site ../site --write-known
See docs/monitoring.md for the scrape job and alert rules.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIRST = "nemencine"  # the source of schedule.json rows without a `provider`
# The warnings someone has checked, per source, as normalise() writes them.
KNOWN = Path(__file__).resolve().parents[2] / "known-warnings.json"
REPO_URL = "https://github.com/AurimasNav/atlieku-surinkimo-grafikas/blob/main"
KNOWN_URL = f"{REPO_URL}/pipeline/known-warnings.json"
DOCS_URL = f"{REPO_URL}/docs/monitoring.md#build-warnings"


def _timestamp(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def collect(site: Path, known: dict[str, set[str]] | None = None) -> dict:
    """What each source published: when, how much, how many warnings, and how many of them
    `known` (default: pipeline/known-warnings.json) doesn't list."""
    status, texts = read(site)
    count_new(status, texts, load_known() if known is None else known)
    return status


def read(site: Path) -> tuple[dict, dict[str, list[str] | None]]:
    """What each source published, and the texts of its warnings (None: published before the
    builds published them)."""
    sources: dict[str, dict] = {}
    texts: dict[str, list[str] | None] = {}
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
    # kupiskio-r is Kupiškio r. (schedule_pipeline.kupiskis), "kupiskis".
    # svencioniu-r is Švenčionių r. (schedule_pipeline.svencionys), "svencionys".
    # zarasu-r is Zarasų r. (schedule_pipeline.zarasai), "zarasai".
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
        site / "kupiskio-r" / "schedule.json",
        site / "svencioniu-r" / "schedule.json",
        site / "zarasu-r" / "schedule.json",
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
                **({"warningTexts": data["warningTexts"]} if "warningTexts" in data else {}),
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
            texts[mine] = provider.get("warningTexts")
    path = site / "kauno-r" / "schedule.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        sources["kauno"] = {
            "generatedAt": data["generatedAt"],
            "areas": data["stats"]["areas"],
            "places": data["stats"]["addresses"],
            "warnings": data.get("warnings", 0),
        }
        texts["kauno"] = data.get("warningTexts")
        # The other municipalities of Kauno švara's file, published with Kauno r. (Kaišiadorių
        # r.: "kaisiadorys"): built together, counted apart.
        for part in data.get("otherMunicipalities", []):
            sources[part["id"]] = {
                "generatedAt": data["generatedAt"],
                "areas": part["stats"]["areas"],
                "places": part["stats"]["addresses"],
                "warnings": part["warnings"],
            }
            texts[part["id"]] = part.get("warningTexts")
    status = {"checkedAt": datetime.now(UTC).isoformat(timespec="seconds"), "sources": sources}
    return status, texts


# --- warnings someone has checked ------------------------------------------------


# A place the build couldn't link (build.build_dataset): "not linked to any settlement:
# household: SB "Girios -7"". Its numbers are part of the place's name ("Kelmės miestas 3",
# "Sausio 13-osios g.", a house), and it has no row or page number.
PLACE = re.compile(
    r"not (?:linked to any settlement|a settlement or a street|a settlement of the eldership): "
)
# A Lithuanian month, any case ("birželis", "birželio"), as a file's period names it.
MONTH = r"(?:saus|vasar|kov|baland|gegu[žz]|bir[žz]el|liep|rugpj|rugs[ėe]j|spal|lapkri|gruod)\w*"
# The months of a file's period in its name: a range ("birželis-gruodis mėn",
# "sausio–birželio"), a month before "mėn", or right after the year ("2026 m- spalio.pdf").
PERIOD = re.compile(
    rf"\b{MONTH}\s*[-–—]\s*{MONTH}|\b{MONTH}(?=\s+mėn)|(?<=\d m- ){MONTH}|(?<=\d m\. ){MONTH}",
    re.IGNORECASE,
)
# The name of the file a warning starts with ("2026 m- birželis-gruodis mėn  Buitinių atliekų
# surinkimo grafikasP.xlsx row 715: ..."): only there do months name a period. A rule's text
# after it ("liepos mėn. paskutinis penktadienis") keeps its months.
FILE_NAME = re.compile(r"^[^:]*?\.(?:xlsx?|pdf|docx?|csv)\b", re.IGNORECASE)
# A site copy read instead of the site (snapshot.site_copy_note): the site refused the runner.
COPY = re.compile(r"unavailable \(.*\); used the copy from \S+ \(\d+ days? old\)")
USED_THE_COPY = ": unavailable; used the copy"


def normalise(text: str) -> str:
    """A warning as pipeline/known-warnings.json lists it: without what changes from one run to
    the next while the warning stays the same. A site copy's date and age, and the error the site
    gave (the copy is read either way), are left out. Numbers, and the months of the period in
    the name of the file a warning starts with, become #: row, page and line numbers move when a
    row is added above, and dates, years and a file's months change with every period, so
    "2026 m- birželis-gruodis mėn ... row 715: kept as text ..." is known whatever its row, and
    so is next half year's file. Except for those that are part of a name: a place's (PLACE)
    keeps its numbers, and so does a route ("route 13" is other places than "route 3")."""
    text = COPY.sub(USED_THE_COPY[2:], text)
    if PLACE.match(text):
        return text
    if name := FILE_NAME.match(text):
        text = PERIOD.sub("#", name[0]) + text[name.end() :]
    return re.sub(r"(\broute )?\d+", lambda m: m[0] if m[1] else "#", text)


def used_the_copy(text: str) -> bool:
    """Whether a warning only says that the build read a site's copy because the site refused
    GitHub's runner. Never new: some sites refuse it some days and answer others, and nobody
    has to act on that (a source whose build keeps failing is ScheduleDataStale's). So it isn't
    in pipeline/known-warnings.json either, whichever day it was written."""
    return normalise(text).endswith(USED_THE_COPY)


def load_known(path: Path = KNOWN) -> dict[str, set[str]]:
    """The warnings someone has checked, per source (normalised). No file: none."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # Every warning is new then, and the alert says so; failing here would stop the deploy.
        print(f"{path} not found: every warning counts as new", file=sys.stderr)
        return {}
    return {source: set(texts) for source, texts in data.items()}


def new_warnings(texts: list[str] | None, known: set[str]) -> list[str]:
    """The warnings of `texts` whose normalised text `known` doesn't list, in the build's order,
    but for a site copy used (used_the_copy). None (data published before the builds published
    their warnings) has none."""
    return [
        text for text in texts or [] if not used_the_copy(text) and normalise(text) not in known
    ]


def count_new(status: dict, texts: dict[str, list[str] | None], known: dict[str, set[str]]) -> None:
    """Adds `newWarnings` to each source of `status`: how many of its warnings `known` doesn't
    list, counted like `warnings` (a line each), so never more than that."""
    for source, numbers in status["sources"].items():
        numbers["newWarnings"] = len(new_warnings(texts.get(source), known.get(source, set())))


def known_from(
    texts: dict[str, list[str] | None], before: dict[str, set[str]]
) -> dict[str, list[str]]:
    """pipeline/known-warnings.json from the warnings of a site: each source's warnings,
    normalised, so one it no longer gives is dropped. A site copy used isn't listed: it is never
    new (used_the_copy), so the file is the same whether or not the site answered that day. A
    source the site doesn't have (its build failed or wasn't run), or whose data has no texts,
    keeps what it had."""
    known = {source: sorted(found) for source, found in before.items()}
    for source, found in texts.items():
        if found is not None:
            known[source] = sorted({normalise(t) for t in found if not used_the_copy(t)})
    return dict(sorted(known.items()))


def write_known(path: Path, known: dict[str, list[str]]) -> None:
    path.write_text(json.dumps(known, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def warnings_report(
    status: dict, texts: dict[str, list[str] | None], known: dict[str, set[str]]
) -> dict:
    """warnings.json: each source's warnings as its build wrote them, those whose normalised text
    pipeline/known-warnings.json doesn't list (`new`) apart from those it does (`known`)."""
    sources = {}
    for source, numbers in status["sources"].items():
        found = texts.get(source)
        new = new_warnings(found, known.get(source, set()))
        sources[source] = {
            "generatedAt": numbers["generatedAt"],
            "warnings": numbers["warnings"],
            "newWarnings": len(new),
            # False: data published before the builds published their warnings.
            "texts": found is not None,
            "new": new,
            "known": [text for text in found or [] if text not in new],
        }
    return {"checkedAt": status["checkedAt"], "sources": sources}


def _vilnius(iso: str) -> str:
    moment = datetime.fromisoformat(iso)
    try:
        return moment.astimezone(ZoneInfo("Europe/Vilnius")).strftime("%Y-%m-%d %H:%M (Vilnius)")
    except ZoneInfoNotFoundError:  # no time zone data (Windows without tzdata)
        return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def warnings_page(report: dict) -> str:
    """warnings.html: a table of the sources, then a section each (its id is the source, which
    the alert links), the new warnings first, then the known ones. No scripts."""
    e = html.escape
    sources = report["sources"]
    total = sum(data["newWarnings"] for data in sources.values())
    rows, sections = [], []
    # Sources with new warnings first, then by name.
    for source in sorted(sources, key=lambda s: (sources[s]["newWarnings"] == 0, s)):
        data = sources[source]
        new = data["newWarnings"]
        mark = ' class="new"' if new else ""
        rows.append(
            f'<tr{mark}><td><a href="#{e(source)}">{e(source)}</a></td>'
            f"<td>{data['warnings']}</td><td>{new}</td></tr>"
        )
        lines = [
            f'<section id="{e(source)}">',
            f"<h2>{e(source)}</h2>",
            f"<p><small>Built {e(_vilnius(data['generatedAt']))}: {data['warnings']} warnings,"
            f" {new} new.</small></p>",
        ]
        if not data["texts"]:
            lines.append(
                "<p>Published before the builds published their warnings: the job summary of"
                " its last run lists them.</p>"
            )
        if data["new"]:
            lines.append('<h3 class="new">New: not in pipeline/known-warnings.json</h3>')
            lines.append('<ul class="new">')
            lines += [f"<li>{e(text)}</li>" for text in data["new"]]
            lines.append("</ul>")
        if data["known"]:
            lines.append("<h3>Known</h3>")
            lines.append("<ul>")
            lines += [f"<li>{e(text)}</li>" for text in data["known"]]
            lines.append("</ul>")
        sections.append("\n".join([*lines, "</section>"]))
    rows_html, sections_html = "\n".join(rows), "\n".join(sections)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Šiukšliavežė: build warnings</title>
<style>
  body {{ margin: 0 auto; max-width: 960px; padding: 16px;
    font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  td, th {{ padding: 2px 16px 2px 0; text-align: left; }}
  .new {{ color: #b3261e; }}
  ul.new {{ border-left: 4px solid #b3261e; }}
  li {{ overflow-wrap: anywhere; }}
  small {{ color: #5e6b63; }}
</style>
</head>
<body>
<h1>Build warnings</h1>
<p>What the last build of each source warned about. <strong class="new">{total} new</strong>:
warnings that <a href="{KNOWN_URL}">pipeline/known-warnings.json</a> doesn't list (numbers, the
months of a file's period and a site copy's date are left out when comparing; a site copy used
because the site refused GitHub's runner is never new). Fix the parser, or acknowledge them as
<a href="{DOCS_URL}">docs/monitoring.md</a> says.</p>
<p><small>Checked {e(_vilnius(report["checkedAt"]))}.</small></p>
<table>
<tr><th>Source</th><th>Warnings</th><th>New</th></tr>
{rows_html}
</table>
{sections_html}
</body>
</html>
"""


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
            "moletai, skuodas, ukmerge, anyksciai, utena, ignalina, elektrenai, sirvintos, "
            "kupiskis, svencionys, zarasai) or addresses (kauno, kaisiadorys) the data covers.",
            [({"source": s}, d["places"]) for s, d in status["sources"].items()],
        ),
        "siuksliaveze_data_warnings": (
            "Warnings of the last build, e.g. rows that couldn't be linked to a settlement.",
            [({"source": s}, d["warnings"]) for s, d in status["sources"].items()],
        ),
        "siuksliaveze_data_new_warnings": (
            "Warnings of the last build that pipeline/known-warnings.json doesn't list.",
            [({"source": s}, d["newWarnings"]) for s, d in status["sources"].items()],
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
    parser.add_argument(
        "--known",
        type=Path,
        default=KNOWN,
        help="the warnings someone has checked (default: pipeline/known-warnings.json)",
    )
    parser.add_argument(
        "--write-known",
        action="store_true",
        help="acknowledge the site's warnings: rewrite --known from them, then report",
    )
    args = parser.parse_args(argv)
    status, texts = read(args.site)
    if not status["sources"]:
        print("No data files found", file=sys.stderr)
        return 1
    known = load_known(args.known)
    if args.write_known:
        listed = known_from(texts, known)
        write_known(args.known, listed)
        kept = sorted(s for s in listed if texts.get(s) is None)
        print(
            f"{args.known}: {sum(map(len, listed.values()))} warnings of {len(listed)} sources"
            + (f" ({', '.join(kept)} kept as they were: no texts on this site)" if kept else "")
        )
        known = {source: set(found) for source, found in listed.items()}
    count_new(status, texts, known)
    report = warnings_report(status, texts, known)
    (args.site / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.site / "metrics.txt").write_text(metrics(status), encoding="utf-8")
    (args.site / "warnings.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.site / "warnings.html").write_text(warnings_page(report), encoding="utf-8")
    print(metrics(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

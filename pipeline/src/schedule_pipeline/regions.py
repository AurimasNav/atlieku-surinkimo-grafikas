"""Publishes regions.json: the index of the region folders on the site, for the app.

The app downloads the regions it was built with (REGION_URLS in app/src/lib/config.ts) and those
this file lists, so a new folder reaches installed apps without an app update. The index is
written from the files about to be published, after the builds, so it lists exactly what is
deployed: a folder whose build failed with nothing to keep isn't there.

    python -m schedule_pipeline.regions --site ../site

A region is the site root or a folder directly under it with a schedule.json:

    {
      "schemaVersion": 1,
      "regions": [
        {"path": "", "kind": "settlements", "files": ["schedule.json", "addresses.json"],
         "providers": ["nemencine", "nemezio"]},
        {"path": "kauno-r/", "kind": "addresses", "files": ["schedule.json", "points.json"],
         "elderships": ["akademijos", ...], "providers": ["kauno-svara"]},
        {"path": "sratc/", "kind": "settlements", "files": ["schedule.json", "addresses.json"],
         "providers": ["siauliai"]},
        ...
      ]
    }

- `path`: the folder with a slash at the end, "" for the site root (Vilniaus r.); a file's URL is
  the site's URL, "/", the path and the file name.
- `kind`: "settlements" for schedule.json in the format of the root file (rows linked to the
  settlements and streets of the Address Register), "addresses" for UAB „Kauno švara“'s format
  (schedules per address, an address file per eldership in addresses/, schedule_pipeline.svara).
- `files`: which of schedule.json, addresses.json ("Use my location") and points.json (the same
  for the "addresses" kind) the folder has.
- `elderships`: for the "addresses" kind, the eldership files, addresses/<id>.json.
- `providers`: the ids of the companies in schedule.json (`providers[].id`; nemencine for the
  rows of the root file without one; `provider.id` of the "addresses" kind).

Apps ignore fields they don't know and regions of a kind they don't know, so both can be added
without a new schemaVersion. Bump it only for a change older apps would misread.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from schedule_pipeline.status import FIRST

SCHEMA_VERSION = 1
# The files of a region the app downloads, in this order.
FILES = ("schedule.json", "addresses.json", "points.json")


def region(site: Path, folder: Path) -> dict | None:
    """The entry of one folder, or None if it has no schedule.json."""
    schedule = folder / "schedule.json"
    if not schedule.is_file():
        return None
    data = json.loads(schedule.read_text(encoding="utf-8"))
    entry: dict = {
        "path": "" if folder == site else f"{folder.name}/",
        "kind": "addresses" if "elderships" in data else "settlements",
        "files": [name for name in FILES if (folder / name).is_file()],
    }
    if entry["kind"] == "addresses":
        entry["elderships"] = sorted(path.stem for path in (folder / "addresses").glob("*.json"))
        provider = data.get("provider") or {}
        entry["providers"] = [provider["id"]] if provider.get("id") else []
        return entry
    providers = [provider["id"] for provider in data.get("providers", [])]
    # Rows and places of the root file without a `provider` are Nemenčinė's (status.FIRST).
    if FIRST not in providers and any("provider" not in area for area in data.get("areas", [])):
        providers.insert(0, FIRST)
    entry["providers"] = providers
    return entry


def collect(site: Path) -> dict:
    """The index of the regions in `site`: the root first, then the folders by name."""
    folders = [site, *sorted(path for path in site.iterdir() if path.is_dir())]
    regions = [entry for folder in folders if (entry := region(site, folder))]
    return {"schemaVersion": SCHEMA_VERSION, "regions": regions}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", type=Path, required=True, help="directory that is published")
    args = parser.parse_args(argv)
    index = collect(args.site)
    if not index["regions"]:
        print("No schedule.json found", file=sys.stderr)
        return 1
    text = json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    (args.site / "regions.json").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

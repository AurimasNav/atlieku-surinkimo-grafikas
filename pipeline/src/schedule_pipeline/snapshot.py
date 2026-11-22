"""Snapshots of the Address Register data, kept in the repository.

The register's sites (get.data.gov.lt and registrucentras.lt) block requests from cloud
servers such as GitHub Actions runners, so the daily job can't always fetch them live. The
data changes slowly, so a snapshot refreshed from a machine in Lithuania is good enough:

    cd pipeline && uv run python -m schedule_pipeline.snapshot

The build tries the live sources first and falls back to these files. The same refresh saves
copies of the pages and files of the sites that refuse GitHub's runners too (site_copies):
silute.lt, kedainiai.lt, ukmerge.lt, sirvintos.lt and svencionys.lt. `--register` refreshes only the
register's snapshots and `--copies` only the copies; a CronJob in the maintainer's cluster in
Lithuania (k8s-at-home, gitops/siuksliaveze-snapshot) runs `--copies` daily and `--register`
monthly and opens a PR with what changed. Run it by hand only when those jobs fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from collections.abc import Callable, Collection
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from . import addresses as address_points
from . import registry as address_register
from .addresses import AddressPoint
from .registry import Registry

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REGISTRY_FILE = DATA_DIR / "registry-vilniaus-r.json"
ADDRESSES_FILE = DATA_DIR / "address-points-vilniaus-r.json"
# Kauno r. (schedule_pipeline.svara): only used to give its addresses coordinates.
KAUNO_MUNICIPALITY = ("Kauno rajono", 52)
KAUNO_REGISTRY_FILE = DATA_DIR / "registry-kauno-r.json"
KAUNO_ADDRESSES_FILE = DATA_DIR / "address-points-kauno-r.json"
# Mažeikių r. (schedule_pipeline.tratc).
MAZEIKIAI_MUNICIPALITY = ("Mažeikių rajono", 61)
MAZEIKIAI_REGISTRY_FILE = DATA_DIR / "registry-mazeikiu-r.json"
MAZEIKIAI_ADDRESSES_FILE = DATA_DIR / "address-points-mazeikiu-r.json"
# Klaipėdos r. (schedule_pipeline.gargzdu).
KLAIPEDOS_MUNICIPALITY = ("Klaipėdos rajono", 55)
KLAIPEDOS_REGISTRY_FILE = DATA_DIR / "registry-klaipedos-r.json"
KLAIPEDOS_ADDRESSES_FILE = DATA_DIR / "address-points-klaipedos-r.json"
# Jurbarko r. (schedule_pipeline.taurage).
JURBARKO_MUNICIPALITY = ("Jurbarko rajono", 94)
JURBARKO_REGISTRY_FILE = DATA_DIR / "registry-jurbarko-r.json"
JURBARKO_ADDRESSES_FILE = DATA_DIR / "address-points-jurbarko-r.json"
# Kaišiadorių r. (schedule_pipeline.svara, with Kauno r.).
KAISIADORIU_MUNICIPALITY = ("Kaišiadorių rajono", 49)
KAISIADORIU_REGISTRY_FILE = DATA_DIR / "registry-kaisiadoriu-r.json"
KAISIADORIU_ADDRESSES_FILE = DATA_DIR / "address-points-kaisiadoriu-r.json"
# Šiaulių r., Akmenės r., Joniškio r., Kelmės r. and Pakruojo r. (schedule_pipeline.sratc).
SIAULIU_R_MUNICIPALITY = ("Šiaulių rajono", 91)
SIAULIU_R_REGISTRY_FILE = DATA_DIR / "registry-siauliu-r.json"
SIAULIU_R_ADDRESSES_FILE = DATA_DIR / "address-points-siauliu-r.json"
AKMENES_R_MUNICIPALITY = ("Akmenės rajono", 32)
AKMENES_R_REGISTRY_FILE = DATA_DIR / "registry-akmenes-r.json"
AKMENES_R_ADDRESSES_FILE = DATA_DIR / "address-points-akmenes-r.json"
JONISKIO_R_MUNICIPALITY = ("Joniškio rajono", 47)
JONISKIO_R_REGISTRY_FILE = DATA_DIR / "registry-joniskio-r.json"
JONISKIO_R_ADDRESSES_FILE = DATA_DIR / "address-points-joniskio-r.json"
KELMES_R_MUNICIPALITY = ("Kelmės rajono", 54)
KELMES_R_REGISTRY_FILE = DATA_DIR / "registry-kelmes-r.json"
KELMES_R_ADDRESSES_FILE = DATA_DIR / "address-points-kelmes-r.json"
PAKRUOJO_R_MUNICIPALITY = ("Pakruojo rajono", 65)
PAKRUOJO_R_REGISTRY_FILE = DATA_DIR / "registry-pakruojo-r.json"
PAKRUOJO_R_ADDRESSES_FILE = DATA_DIR / "address-points-pakruojo-r.json"
# Radviliškio r. (schedule_pipeline.sratc, a source of its own next to the five).
RADVILISKIO_R_MUNICIPALITY = ("Radviliškio rajono", 71)
RADVILISKIO_R_REGISTRY_FILE = DATA_DIR / "registry-radviliskio-r.json"
RADVILISKIO_R_ADDRESSES_FILE = DATA_DIR / "address-points-radviliskio-r.json"
# The six municipalities of Alytaus RATC (schedule_pipeline.aratc), in one file.
ALYTUS_MUNICIPALITIES = (
    ("Alytaus rajono", 33),
    ("Prienų rajono", 69),
    ("Lazdijų rajono", 59),
    ("Varėnos rajono", 38),
    ("Druskininkų", 15),
    ("Birštono", 12),
)
ALYTUS_REGISTRY_FILE = DATA_DIR / "registry-alytaus-ratc.json"
ALYTUS_ADDRESSES_FILE = DATA_DIR / "address-points-alytaus-ratc.json"
# Telšių r., Plungės r. and Rietavo sav. (schedule_pipeline.tratc, next to Mažeikių r.).
TELSIAI_MUNICIPALITY = ("Telšių rajono", 78)
TELSIAI_REGISTRY_FILE = DATA_DIR / "registry-telsiu-r.json"
TELSIAI_ADDRESSES_FILE = DATA_DIR / "address-points-telsiu-r.json"
PLUNGE_MUNICIPALITY = ("Plungės rajono", 68)
PLUNGE_REGISTRY_FILE = DATA_DIR / "registry-plunges-r.json"
PLUNGE_ADDRESSES_FILE = DATA_DIR / "address-points-plunges-r.json"
RIETAVAS_MUNICIPALITY = ("Rietavo", 74)
RIETAVAS_REGISTRY_FILE = DATA_DIR / "registry-rietavo-sav.json"
RIETAVAS_ADDRESSES_FILE = DATA_DIR / "address-points-rietavo-sav.json"
# Tauragės r., Šilalės r. and Pagėgių sav. (schedule_pipeline.taurage, next to Jurbarko r.).
TAURAGES_MUNICIPALITY = ("Tauragės rajono", 77)
TAURAGES_REGISTRY_FILE = DATA_DIR / "registry-taurages-r.json"
TAURAGES_ADDRESSES_FILE = DATA_DIR / "address-points-taurages-r.json"
SILALES_MUNICIPALITY = ("Šilalės rajono", 87)
SILALES_REGISTRY_FILE = DATA_DIR / "registry-silales-r.json"
SILALES_ADDRESSES_FILE = DATA_DIR / "address-points-silales-r.json"
PAGEGIAI_MUNICIPALITY = ("Pagėgių", 63)
PAGEGIAI_REGISTRY_FILE = DATA_DIR / "registry-pagegiu-sav.json"
PAGEGIAI_ADDRESSES_FILE = DATA_DIR / "address-points-pagegiu-sav.json"
# Pasvalio r., Rokiškio r., Biržų r. and Panevėžio r. (schedule_pipeline.pratc).
PASVALIO_R_MUNICIPALITY = ("Pasvalio rajono", 67)
PASVALIO_R_REGISTRY_FILE = DATA_DIR / "registry-pasvalio-r.json"
PASVALIO_R_ADDRESSES_FILE = DATA_DIR / "address-points-pasvalio-r.json"
ROKISKIO_R_MUNICIPALITY = ("Rokiškio rajono", 73)
ROKISKIO_R_REGISTRY_FILE = DATA_DIR / "registry-rokiskio-r.json"
ROKISKIO_R_ADDRESSES_FILE = DATA_DIR / "address-points-rokiskio-r.json"
BIRZU_R_MUNICIPALITY = ("Biržų rajono", 36)
BIRZU_R_REGISTRY_FILE = DATA_DIR / "registry-birzu-r.json"
BIRZU_R_ADDRESSES_FILE = DATA_DIR / "address-points-birzu-r.json"
PANEVEZIO_R_MUNICIPALITY = ("Panevėžio rajono", 66)
PANEVEZIO_R_REGISTRY_FILE = DATA_DIR / "registry-panevezio-r.json"
PANEVEZIO_R_ADDRESSES_FILE = DATA_DIR / "address-points-panevezio-r.json"
# The five municipalities of Marijampolė county (schedule_pipeline.maatc, a part each).
MARIJAMPOLE_MUNICIPALITY = ("Marijampolės", 18)
MARIJAMPOLE_REGISTRY_FILE = DATA_DIR / "registry-marijampoles-sav.json"
MARIJAMPOLE_ADDRESSES_FILE = DATA_DIR / "address-points-marijampoles-sav.json"
VILKAVISKIS_MUNICIPALITY = ("Vilkaviškio rajono", 39)
VILKAVISKIS_REGISTRY_FILE = DATA_DIR / "registry-vilkaviskio-r.json"
VILKAVISKIS_ADDRESSES_FILE = DATA_DIR / "address-points-vilkaviskio-r.json"
KALVARIJA_MUNICIPALITY = ("Kalvarijos", 48)
KALVARIJA_REGISTRY_FILE = DATA_DIR / "registry-kalvarijos-sav.json"
KALVARIJA_ADDRESSES_FILE = DATA_DIR / "address-points-kalvarijos-sav.json"
KAZLU_RUDA_MUNICIPALITY = ("Kazlų Rūdos", 58)
KAZLU_RUDA_REGISTRY_FILE = DATA_DIR / "registry-kazlu-rudos-sav.json"
KAZLU_RUDA_ADDRESSES_FILE = DATA_DIR / "address-points-kazlu-rudos-sav.json"
SAKIAI_MUNICIPALITY = ("Šakių rajono", 84)
SAKIAI_REGISTRY_FILE = DATA_DIR / "registry-sakiu-r.json"
SAKIAI_ADDRESSES_FILE = DATA_DIR / "address-points-sakiu-r.json"
# Raseinių r. (schedule_pipeline.raseiniai) and Jonavos r. (schedule_pipeline.jonava).
RASEINIAI_MUNICIPALITY = ("Raseinių rajono", 72)
RASEINIAI_REGISTRY_FILE = DATA_DIR / "registry-raseiniu-r.json"
RASEINIAI_ADDRESSES_FILE = DATA_DIR / "address-points-raseiniu-r.json"
JONAVA_MUNICIPALITY = ("Jonavos rajono", 46)
JONAVA_REGISTRY_FILE = DATA_DIR / "registry-jonavos-r.json"
JONAVA_ADDRESSES_FILE = DATA_DIR / "address-points-jonavos-r.json"
# Kretingos r. (schedule_pipeline.kretinga).
KRETINGOS_MUNICIPALITY = ("Kretingos rajono", 56)
KRETINGOS_REGISTRY_FILE = DATA_DIR / "registry-kretingos-r.json"
KRETINGOS_ADDRESSES_FILE = DATA_DIR / "address-points-kretingos-r.json"
# Šilutės r., Trakų r. and Šalčininkų r. (schedule_pipeline.ecoservice, a part each).
SILUTE_MUNICIPALITY = ("Šilutės rajono", 88)
SILUTE_REGISTRY_FILE = DATA_DIR / "registry-silutes-r.json"
SILUTE_ADDRESSES_FILE = DATA_DIR / "address-points-silutes-r.json"
# A copy of the Šilutės r. schedule and the page that links it: silute.lt refuses GitHub's
# runners (HTTP 403), as the register's sites do (ecoservice.save_copy).
SILUTE_COPY_DIR = DATA_DIR / "schedules-silutes-r"
TRAKAI_MUNICIPALITY = ("Trakų rajono", 79)
TRAKAI_REGISTRY_FILE = DATA_DIR / "registry-traku-r.json"
TRAKAI_ADDRESSES_FILE = DATA_DIR / "address-points-traku-r.json"
SALCININKAI_MUNICIPALITY = ("Šalčininkų rajono", 85)
SALCININKAI_REGISTRY_FILE = DATA_DIR / "registry-salcininku-r.json"
SALCININKAI_ADDRESSES_FILE = DATA_DIR / "address-points-salcininku-r.json"
# Kėdainių r. (schedule_pipeline.kedainiai).
KEDAINIAI_MUNICIPALITY = ("Kėdainių rajono", 53)
KEDAINIAI_REGISTRY_FILE = DATA_DIR / "registry-kedainiu-r.json"
KEDAINIAI_ADDRESSES_FILE = DATA_DIR / "address-points-kedainiu-r.json"
# A copy of the Kėdainių r. page and the elderships' files it links: kedainiai.lt refuses
# GitHub's runners (HTTP 403) too (kedainiai.save_copy).
KEDAINIAI_COPY_DIR = DATA_DIR / "schedules-kedainiu-r"
# Molėtų r. (schedule_pipeline.moletai).
MOLETAI_MUNICIPALITY = ("Molėtų rajono", 62)
MOLETAI_REGISTRY_FILE = DATA_DIR / "registry-moletu-r.json"
MOLETAI_ADDRESSES_FILE = DATA_DIR / "address-points-moletu-r.json"
# Skuodo r. (schedule_pipeline.skuodas).
SKUODAS_MUNICIPALITY = ("Skuodo rajono", 75)
SKUODAS_REGISTRY_FILE = DATA_DIR / "registry-skuodo-r.json"
SKUODAS_ADDRESSES_FILE = DATA_DIR / "address-points-skuodo-r.json"
# Ukmergės r. (schedule_pipeline.ukmerge).
UKMERGE_MUNICIPALITY = ("Ukmergės rajono", 81)
UKMERGE_REGISTRY_FILE = DATA_DIR / "registry-ukmerges-r.json"
UKMERGE_ADDRESSES_FILE = DATA_DIR / "address-points-ukmerges-r.json"
# A copy of the Ukmergės r. page and the files it links: ukmerge.lt refuses GitHub's runners
# (HTTP 403) too (ukmerge.save_copy).
UKMERGE_COPY_DIR = DATA_DIR / "schedules-ukmerges-r"
# Anykščių r. (schedule_pipeline.anyksciai).
ANYKSCIAI_MUNICIPALITY = ("Anykščių rajono", 34)
ANYKSCIAI_REGISTRY_FILE = DATA_DIR / "registry-anyksciu-r.json"
ANYKSCIAI_ADDRESSES_FILE = DATA_DIR / "address-points-anyksciu-r.json"
# Utenos r. (schedule_pipeline.utena).
UTENA_MUNICIPALITY = ("Utenos rajono", 82)
UTENA_REGISTRY_FILE = DATA_DIR / "registry-utenos-r.json"
UTENA_ADDRESSES_FILE = DATA_DIR / "address-points-utenos-r.json"
# Ignalinos r. (schedule_pipeline.ignalina).
IGNALINA_MUNICIPALITY = ("Ignalinos rajono", 45)
IGNALINA_REGISTRY_FILE = DATA_DIR / "registry-ignalinos-r.json"
IGNALINA_ADDRESSES_FILE = DATA_DIR / "address-points-ignalinos-r.json"
# Elektrėnų sav. (schedule_pipeline.elektrenai).
ELEKTRENAI_MUNICIPALITY = ("Elektrėnų", 42)
ELEKTRENAI_REGISTRY_FILE = DATA_DIR / "registry-elektrenu-sav.json"
ELEKTRENAI_ADDRESSES_FILE = DATA_DIR / "address-points-elektrenu-sav.json"
# Širvintų r. (schedule_pipeline.sirvintos).
SIRVINTOS_MUNICIPALITY = ("Širvintų rajono", 89)
SIRVINTOS_REGISTRY_FILE = DATA_DIR / "registry-sirvintu-r.json"
SIRVINTOS_ADDRESSES_FILE = DATA_DIR / "address-points-sirvintu-r.json"
# A copy of the Širvintų r. pages and the files they link: sirvintos.lt refuses GitHub's runners
# (HTTP 403) too (sirvintos.save_copy).
SIRVINTOS_COPY_DIR = DATA_DIR / "schedules-sirvintu-r"
# Kupiškio r. (schedule_pipeline.kupiskis).
KUPISKIS_MUNICIPALITY = ("Kupiškio rajono", 57)
KUPISKIS_REGISTRY_FILE = DATA_DIR / "registry-kupiskio-r.json"
KUPISKIS_ADDRESSES_FILE = DATA_DIR / "address-points-kupiskio-r.json"
# Švenčionių r. (schedule_pipeline.svencionys).
SVENCIONYS_MUNICIPALITY = ("Švenčionių rajono", 86)
SVENCIONYS_REGISTRY_FILE = DATA_DIR / "registry-svencioniu-r.json"
SVENCIONYS_ADDRESSES_FILE = DATA_DIR / "address-points-svencioniu-r.json"
# A copy of the Švenčionių r. page and the files it links: svencionys.lt refuses GitHub's runners
# (HTTP 403) too (svencionys.save_copy).
SVENCIONYS_COPY_DIR = DATA_DIR / "schedules-svencioniu-r"
# Older than this, the job summary asks for a refresh (the build still succeeds).
MAX_AGE_DAYS = 60


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def save(
    registry: Registry,
    points: list[AddressPoint],
    registry_file: Path = REGISTRY_FILE,
    addresses_file: Path = ADDRESSES_FILE,
) -> None:
    taken = datetime.now(UTC).date().isoformat()
    _write(registry_file, {"takenAt": taken, **registry.to_json()})
    _write(
        addresses_file,
        {
            "takenAt": taken,
            # [settlement code, street code or 0, house number, lat * 1e6, lon * 1e6]
            "points": sorted(
                [p.settlement, p.street or 0, p.number, round(p.lat * 1e6), round(p.lon * 1e6)]
                for p in points
            ),
        },
    )


def load_registry(path: Path = REGISTRY_FILE) -> tuple[Registry, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Registry.from_json(data), data["takenAt"]


def load_points(path: Path = ADDRESSES_FILE) -> tuple[list[AddressPoint], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    points = [
        AddressPoint(settlement=g, street=s or None, number=n, lat=lat / 1e6, lon=lon / 1e6)
        for g, s, n, lat, lon in data["points"]
    ]
    return points, data["takenAt"]


def age_days(taken_at: str, today: date) -> int:
    return (today - date.fromisoformat(taken_at)).days


def utc_today() -> date:
    """Today in UTC, the date the snapshots and GitHub's runners use: a copy saved after
    midnight in Lithuania would otherwise be a day "younger" than the runner's today."""
    return datetime.now(UTC).date()


# A copy of a site that refuses GitHub's runners (ecoservice: silute.lt, kedainiai: kedainiai.lt,
# ukmerge: ukmerge.lt, sirvintos: sirvintos.lt, svencionys: svencionys.lt): its page as
# page.html, the files it links under
# the last part of their URLs, and this index with when it was taken, the page's URL and the
# files' names.
SITE_COPY_INDEX = "copy.json"
# A Google API key in a site's markup (a WordPress theme's Maps key, as kupkom.lt's): the
# publisher's browser key, but no secret scanner can tell, and the daily refresh commits the
# copies unattended. Saved pages have it replaced (redact).
GOOGLE_API_KEY = re.compile(rb"AIza[0-9A-Za-z_-]{35}")


def redact(markup: bytes) -> bytes:
    """A page with the Google API keys in it replaced by "AIza_REDACTED"."""
    return GOOGLE_API_KEY.sub(b"AIza_REDACTED", markup)


def _copy_name(url: str) -> str:
    return PurePosixPath(unquote(urlsplit(url).path)).name


def save_site_copy(
    folder: Path,
    page: str,
    html: bytes,
    files: list[tuple[str, bytes]],
    today: date,
    other_pages: Collection[str] = (),
) -> bool:
    """Saves a page and the files it links, (URL, content), in `folder`, replacing what was
    there, and returns True. If the copy there is of the same page and has the same files, it
    is left as it is, takenAt included, and the result is False: a page whose markup changed
    but whose schedule files didn't is no change, so the daily refresh opens no PR for it.
    `other_pages` are URLs among `files` that are pages too (sirvintos keeps a second page as
    a file): like the page, their content alone is no change. The pages are saved redacted
    (redact): the parsers don't read the keys."""
    contents = {_copy_name(url): content for url, content in files}
    markup = {_copy_name(url) for url in other_pages}
    if _same_copy(folder, page, contents, markup):
        return False
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        old.unlink()
    (folder / "page.html").write_bytes(redact(html))
    for url, content in files:
        name = _copy_name(url)
        (folder / name).write_bytes(redact(content) if name in markup else content)
    index = {"takenAt": today.isoformat(), "page": page, "files": [_copy_name(u) for u, _ in files]}
    (folder / SITE_COPY_INDEX).write_bytes((json.dumps(index, ensure_ascii=False) + "\n").encode())
    return True


def _same_copy(folder: Path, page: str, contents: dict[str, bytes], markup: set[str]) -> bool:
    """Whether the copy in `folder` is of `page` and has exactly these files (name: content),
    in any order; of the pages among them (`markup`), only that they are there."""
    try:
        index = json.loads((folder / SITE_COPY_INDEX).read_text(encoding="utf-8"))
        return (
            index["page"] == page
            and sorted(index["files"]) == sorted(contents)
            and (folder / "page.html").is_file()
            and all((folder / name).is_file() for name in markup)
            and all(
                (folder / name).read_bytes() == data
                for name, data in contents.items()
                if name not in markup
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def site_copy(folder: Path, url: str) -> bytes:
    """A page or file from its copy in `folder` (FileNotFoundError, an OSError, if none)."""
    page = json.loads((folder / SITE_COPY_INDEX).read_text(encoding="utf-8"))["page"]
    return (folder / ("page.html" if url == page else _copy_name(url))).read_bytes()


def site_copy_note(url: str, error: Exception, folder: Path, today: date) -> str:
    """The build warning for a copy read instead of `url`, with its date and age.

    Unlike the register's snapshots, it never asks for a refresh: the copies are refreshed
    daily (--copies) and one whose files didn't change keeps its takenAt, so the age says how long
    the site's files have stayed the same (a year for a yearly schedule), not how stale the
    copy is. A refresh that fails shows as a failed job in the cluster that runs it, and a
    schedule that ends without a newer file as ScheduleDataRunsOut (docs/monitoring.md)."""
    taken = json.loads((folder / SITE_COPY_INDEX).read_text(encoding="utf-8"))["takenAt"]
    age = age_days(taken, today)
    return f"{url}: unavailable ({error}); used the copy from {taken} ({age} days old)"


def site_copies() -> list[tuple[str, Callable[[Path], bool], Path]]:
    """The copies of the sites that refuse GitHub's runners: (label, save, folder), where
    save(folder) saves the page and its files there and returns whether the copy changed
    (save_site_copy). A new site adds a line."""
    from . import ecoservice, kedainiai, sirvintos, svencionys, ukmerge  # they import this module

    return [
        ("Šilutės r.", partial(ecoservice.save_copy, ecoservice.SILUTE), SILUTE_COPY_DIR),
        ("Kėdainių r.", kedainiai.save_copy, KEDAINIAI_COPY_DIR),
        ("Ukmergės r.", ukmerge.save_copy, UKMERGE_COPY_DIR),
        ("Širvintų r.", sirvintos.save_copy, SIRVINTOS_COPY_DIR),
        ("Švenčionių r.", svencionys.save_copy, SVENCIONYS_COPY_DIR),
    ]


def save_copies() -> int:
    """Refreshes every site copy. One that fails doesn't stop the others; the result is 1 if
    any did, 0 otherwise."""
    failed = 0
    for label, save_copy, folder in site_copies():
        try:
            changed = save_copy(folder)
        except Exception:  # the site is down, or its page changed: the other copies still run
            print(f"{label}: the copy in {folder} couldn't be refreshed", file=sys.stderr)
            traceback.print_exc()
            failed = 1
            continue
        done = "saved the page and its files" if changed else "no change to the files"
        print(f"{label}: {done} ({folder})")
    return failed


def save_register() -> None:
    """Saves the Address Register snapshots of every municipality."""
    registry = address_register.fetch()
    points = address_points.fetch()
    save(registry, points)
    count = f"{len(registry.settlements)} settlements and {len(points)} address points"
    print(f"Vilniaus r.: saved {count} to {DATA_DIR}")
    for label, (name, code), registry_file, addresses_file in (
        ("Kauno r.", KAUNO_MUNICIPALITY, KAUNO_REGISTRY_FILE, KAUNO_ADDRESSES_FILE),
        ("Mažeikių r.", MAZEIKIAI_MUNICIPALITY, MAZEIKIAI_REGISTRY_FILE, MAZEIKIAI_ADDRESSES_FILE),
        ("Klaipėdos r.", KLAIPEDOS_MUNICIPALITY, KLAIPEDOS_REGISTRY_FILE, KLAIPEDOS_ADDRESSES_FILE),
        ("Jurbarko r.", JURBARKO_MUNICIPALITY, JURBARKO_REGISTRY_FILE, JURBARKO_ADDRESSES_FILE),
        (
            "Kaišiadorių r.",
            KAISIADORIU_MUNICIPALITY,
            KAISIADORIU_REGISTRY_FILE,
            KAISIADORIU_ADDRESSES_FILE,
        ),
        ("Šiaulių r.", SIAULIU_R_MUNICIPALITY, SIAULIU_R_REGISTRY_FILE, SIAULIU_R_ADDRESSES_FILE),
        ("Akmenės r.", AKMENES_R_MUNICIPALITY, AKMENES_R_REGISTRY_FILE, AKMENES_R_ADDRESSES_FILE),
        (
            "Joniškio r.",
            JONISKIO_R_MUNICIPALITY,
            JONISKIO_R_REGISTRY_FILE,
            JONISKIO_R_ADDRESSES_FILE,
        ),
        ("Kelmės r.", KELMES_R_MUNICIPALITY, KELMES_R_REGISTRY_FILE, KELMES_R_ADDRESSES_FILE),
        (
            "Pakruojo r.",
            PAKRUOJO_R_MUNICIPALITY,
            PAKRUOJO_R_REGISTRY_FILE,
            PAKRUOJO_R_ADDRESSES_FILE,
        ),
        (
            "Radviliškio r.",
            RADVILISKIO_R_MUNICIPALITY,
            RADVILISKIO_R_REGISTRY_FILE,
            RADVILISKIO_R_ADDRESSES_FILE,
        ),
        ("Telšių r.", TELSIAI_MUNICIPALITY, TELSIAI_REGISTRY_FILE, TELSIAI_ADDRESSES_FILE),
        ("Plungės r.", PLUNGE_MUNICIPALITY, PLUNGE_REGISTRY_FILE, PLUNGE_ADDRESSES_FILE),
        ("Rietavo sav.", RIETAVAS_MUNICIPALITY, RIETAVAS_REGISTRY_FILE, RIETAVAS_ADDRESSES_FILE),
        ("Tauragės r.", TAURAGES_MUNICIPALITY, TAURAGES_REGISTRY_FILE, TAURAGES_ADDRESSES_FILE),
        ("Šilalės r.", SILALES_MUNICIPALITY, SILALES_REGISTRY_FILE, SILALES_ADDRESSES_FILE),
        ("Pagėgių sav.", PAGEGIAI_MUNICIPALITY, PAGEGIAI_REGISTRY_FILE, PAGEGIAI_ADDRESSES_FILE),
        (
            "Pasvalio r.",
            PASVALIO_R_MUNICIPALITY,
            PASVALIO_R_REGISTRY_FILE,
            PASVALIO_R_ADDRESSES_FILE,
        ),
        (
            "Rokiškio r.",
            ROKISKIO_R_MUNICIPALITY,
            ROKISKIO_R_REGISTRY_FILE,
            ROKISKIO_R_ADDRESSES_FILE,
        ),
        ("Biržų r.", BIRZU_R_MUNICIPALITY, BIRZU_R_REGISTRY_FILE, BIRZU_R_ADDRESSES_FILE),
        (
            "Panevėžio r.",
            PANEVEZIO_R_MUNICIPALITY,
            PANEVEZIO_R_REGISTRY_FILE,
            PANEVEZIO_R_ADDRESSES_FILE,
        ),
        (
            "Marijampolės sav.",
            MARIJAMPOLE_MUNICIPALITY,
            MARIJAMPOLE_REGISTRY_FILE,
            MARIJAMPOLE_ADDRESSES_FILE,
        ),
        (
            "Vilkaviškio r.",
            VILKAVISKIS_MUNICIPALITY,
            VILKAVISKIS_REGISTRY_FILE,
            VILKAVISKIS_ADDRESSES_FILE,
        ),
        (
            "Kalvarijos sav.",
            KALVARIJA_MUNICIPALITY,
            KALVARIJA_REGISTRY_FILE,
            KALVARIJA_ADDRESSES_FILE,
        ),
        (
            "Kazlų Rūdos sav.",
            KAZLU_RUDA_MUNICIPALITY,
            KAZLU_RUDA_REGISTRY_FILE,
            KAZLU_RUDA_ADDRESSES_FILE,
        ),
        ("Šakių r.", SAKIAI_MUNICIPALITY, SAKIAI_REGISTRY_FILE, SAKIAI_ADDRESSES_FILE),
        (
            "Raseinių r.",
            RASEINIAI_MUNICIPALITY,
            RASEINIAI_REGISTRY_FILE,
            RASEINIAI_ADDRESSES_FILE,
        ),
        ("Jonavos r.", JONAVA_MUNICIPALITY, JONAVA_REGISTRY_FILE, JONAVA_ADDRESSES_FILE),
        (
            "Kretingos r.",
            KRETINGOS_MUNICIPALITY,
            KRETINGOS_REGISTRY_FILE,
            KRETINGOS_ADDRESSES_FILE,
        ),
        ("Šilutės r.", SILUTE_MUNICIPALITY, SILUTE_REGISTRY_FILE, SILUTE_ADDRESSES_FILE),
        ("Trakų r.", TRAKAI_MUNICIPALITY, TRAKAI_REGISTRY_FILE, TRAKAI_ADDRESSES_FILE),
        (
            "Šalčininkų r.",
            SALCININKAI_MUNICIPALITY,
            SALCININKAI_REGISTRY_FILE,
            SALCININKAI_ADDRESSES_FILE,
        ),
        (
            "Kėdainių r.",
            KEDAINIAI_MUNICIPALITY,
            KEDAINIAI_REGISTRY_FILE,
            KEDAINIAI_ADDRESSES_FILE,
        ),
        ("Molėtų r.", MOLETAI_MUNICIPALITY, MOLETAI_REGISTRY_FILE, MOLETAI_ADDRESSES_FILE),
        ("Skuodo r.", SKUODAS_MUNICIPALITY, SKUODAS_REGISTRY_FILE, SKUODAS_ADDRESSES_FILE),
        ("Ukmergės r.", UKMERGE_MUNICIPALITY, UKMERGE_REGISTRY_FILE, UKMERGE_ADDRESSES_FILE),
        (
            "Anykščių r.",
            ANYKSCIAI_MUNICIPALITY,
            ANYKSCIAI_REGISTRY_FILE,
            ANYKSCIAI_ADDRESSES_FILE,
        ),
        ("Utenos r.", UTENA_MUNICIPALITY, UTENA_REGISTRY_FILE, UTENA_ADDRESSES_FILE),
        ("Ignalinos r.", IGNALINA_MUNICIPALITY, IGNALINA_REGISTRY_FILE, IGNALINA_ADDRESSES_FILE),
        (
            "Elektrėnų sav.",
            ELEKTRENAI_MUNICIPALITY,
            ELEKTRENAI_REGISTRY_FILE,
            ELEKTRENAI_ADDRESSES_FILE,
        ),
        (
            "Širvintų r.",
            SIRVINTOS_MUNICIPALITY,
            SIRVINTOS_REGISTRY_FILE,
            SIRVINTOS_ADDRESSES_FILE,
        ),
        ("Kupiškio r.", KUPISKIS_MUNICIPALITY, KUPISKIS_REGISTRY_FILE, KUPISKIS_ADDRESSES_FILE),
        (
            "Švenčionių r.",
            SVENCIONYS_MUNICIPALITY,
            SVENCIONYS_REGISTRY_FILE,
            SVENCIONYS_ADDRESSES_FILE,
        ),
    ):
        registry, points = address_register.fetch(name), address_points.fetch(code)
        save(registry, points, registry_file, addresses_file)
        count = f"{len(registry.settlements)} settlements and {len(points)} address points"
        print(f"{label}: saved {count} to {DATA_DIR}")
    registry = Registry(
        [s for name, _ in ALYTUS_MUNICIPALITIES for s in address_register.fetch(name).settlements]
    )
    points = address_points.fetch_all([code for _, code in ALYTUS_MUNICIPALITIES])
    save(registry, points, ALYTUS_REGISTRY_FILE, ALYTUS_ADDRESSES_FILE)
    count = f"{len(registry.settlements)} settlements and {len(points)} address points"
    print(f"Alytaus RATC: saved {count} to {DATA_DIR}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m schedule_pipeline.snapshot",
        description="Refresh the data in pipeline/data that GitHub's runners can't download. "
        "Without options, both.",
    )
    parser.add_argument(
        "--register", action="store_true", help="only the Address Register snapshots"
    )
    parser.add_argument(
        "--copies",
        action="store_true",
        help="only the copies of the sites that refuse GitHub's runners "
        "(a copy whose files didn't change is left as it is)",
    )
    args = parser.parse_args(argv)
    both = not args.register and not args.copies
    if args.register or both:
        save_register()
    return save_copies() if args.copies or both else 0


if __name__ == "__main__":
    sys.exit(main())

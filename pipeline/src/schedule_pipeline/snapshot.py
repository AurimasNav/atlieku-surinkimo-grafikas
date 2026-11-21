"""Snapshots of the Address Register data, kept in the repository.

The register's sites (get.data.gov.lt and registrucentras.lt) block requests from cloud
servers such as GitHub Actions runners, so the daily job can't always fetch them live. The
data changes slowly, so a snapshot refreshed from a machine in Lithuania is good enough:

    cd pipeline && uv run python -m schedule_pipeline.snapshot

The build tries the live sources first and falls back to these files.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

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


def main() -> int:
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
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
# Older than this, the job summary asks for a refresh (the build still succeeds).
MAX_AGE_DAYS = 60


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )


def save(registry: Registry, points: list[AddressPoint]) -> None:
    taken = datetime.now(UTC).date().isoformat()
    _write(REGISTRY_FILE, {"takenAt": taken, **registry.to_json()})
    _write(
        ADDRESSES_FILE,
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
    print(f"Saved {count} to {DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Address points for "use my location": every served address with its coordinates.

The app downloads this file only when the user asks to locate them, then finds the nearest
address on the phone, so the user's position is never sent anywhere.

Source: VĮ Registrų centras, Adresų registras open data files
(https://www.registrucentras.lt/aduomenys/), coordinates in WGS84 (E_KOORD/N_KOORD).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from . import http
from .registry import ATTRIBUTION, Registry

FILES = "https://www.registrucentras.lt/aduomenys/?byla="
MUNICIPALITY_CODE = 41  # Vilniaus rajono savivaldybė
POINTS_FILE = f"adr_gra_{MUNICIPALITY_CODE}.json"
NUMBERS_FILE = "adr_stat_lr.csv"  # whole country; filtered to the municipality while reading


@dataclass
class AddressPoint:
    settlement: int  # GYV_KODAS
    street: int | None  # GAT_KODAS
    number: str  # "12", "12A", "3-1"
    lat: float
    lon: float


def _download(name: str) -> bytes:
    # This server rejects unknown user agents, so present a browser one.
    return http.get(FILES + name, timeout=300, user_agent="Mozilla/5.0")


def parse(points_geojson: bytes, numbers_csv: bytes) -> list[AddressPoint]:
    numbers: dict[int, str] = {}
    reader = csv.DictReader(io.StringIO(numbers_csv.decode("utf-8")), delimiter="|")
    for row in reader:
        if row["SAV_KODAS"] != str(MUNICIPALITY_CODE):
            continue
        number = row["NR"] + (f"-{row['KORPUSO_NR']}" if row["KORPUSO_NR"] else "")
        numbers[int(row["AOB_KODAS"])] = number

    points = []
    for feature in json.loads(points_geojson)["features"]:
        p = feature["properties"]
        if p.get("E_KOORD") is None or p.get("N_KOORD") is None:
            continue
        points.append(
            AddressPoint(
                settlement=int(p["GYV_KODAS"]),
                street=int(p["GAT_KODAS"]) if p.get("GAT_KODAS") else None,
                number=numbers.get(int(p["AOB_KODAS"]), ""),
                lat=float(p["N_KOORD"]),
                lon=float(p["E_KOORD"]),
            )
        )
    return points


def fetch() -> list[AddressPoint]:
    return parse(_download(POINTS_FILE), _download(NUMBERS_FILE))


def build_addresses(
    points: list[AddressPoint], registry: Registry, served: set[str], generated_at: str
) -> dict:
    """Compact table for the app. `places` are [location id, street key or "", street label];
    each point is [lat * 1e5, lon * 1e5, place index, house number]."""
    street_labels = {t.code: t.label for s in registry.settlements for t in s.streets}
    places: list[list[str]] = []
    place_index: dict[tuple[str, str], int] = {}
    rows = []
    for point in points:
        location_id = f"g{point.settlement}"
        if location_id not in served:
            continue
        street_key = f"s{point.street}" if point.street else ""
        key = (location_id, street_key)
        if key not in place_index:
            place_index[key] = len(places)
            places.append([location_id, street_key, street_labels.get(point.street or 0, "")])
        rows.append(
            [round(point.lat * 1e5), round(point.lon * 1e5), place_index[key], point.number]
        )

    rows.sort()
    return {"generatedAt": generated_at, "source": ATTRIBUTION, "places": places, "points": rows}

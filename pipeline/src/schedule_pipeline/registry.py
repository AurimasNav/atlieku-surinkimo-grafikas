"""Settlements and streets of Vilnius district from the Lithuanian Address Register.

Source: VĮ Registrų centras, Adresų registras, published as open data on the national
open data portal (https://get.data.gov.lt/datasets/gov/rc/ar/:ns). No key is needed.
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://get.data.gov.lt/datasets/gov/rc/ar"
MUNICIPALITY = "Vilniaus rajono"
ATTRIBUTION = "Adresų registras, VĮ Registrų centras"


def fold(text: str) -> str:
    """Lower-case, strip diacritics and punctuation, collapse spaces: "J.K. Chodkevičiaus"
    and "J. K. Chodkevičiaus" both become "j k chodkeviciaus"."""
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]+", " ", text).strip()


@dataclass
class Street:
    code: int
    name: str  # e.g. "Akacijų"
    abbr: str  # e.g. "g.", "akl.", "al."

    @property
    def label(self) -> str:
        return f"{self.name} {self.abbr}"


@dataclass
class Settlement:
    code: int
    name: str  # nominative, e.g. "Abakai"
    genitive: str  # e.g. "Abakų", the form the PDF schedules use
    abbr: str  # "k.", "vs.", "mstl.", "m."
    district: str  # seniūnija, genitive as in the register, e.g. "Avižienių"
    streets: list[Street] = field(default_factory=list)


@dataclass
class Registry:
    settlements: list[Settlement]

    def to_json(self) -> dict:
        return {
            "settlements": [
                {
                    "code": s.code,
                    "name": s.name,
                    "genitive": s.genitive,
                    "abbr": s.abbr,
                    "district": s.district,
                    "streets": [[t.code, t.name, t.abbr] for t in s.streets],
                }
                for s in self.settlements
            ]
        }

    @classmethod
    def from_json(cls, data: dict) -> Registry:
        return cls(
            [
                Settlement(
                    code=s["code"],
                    name=s["name"],
                    genitive=s["genitive"],
                    abbr=s["abbr"],
                    district=s["district"],
                    streets=[Street(code, name, abbr) for code, name, abbr in s["streets"]],
                )
                for s in data["settlements"]
            ]
        )

    @classmethod
    def load(cls, path: Path) -> Registry:
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


def _get_all(path: str, query: str) -> list[dict]:
    rows: list[dict] = []
    page = None
    while True:
        url = f"{API}/{path}?{query}" + (f"&page('{page}')" if page else "")
        with urllib.request.urlopen(url, timeout=120) as response:
            data = json.load(response)
        rows += data["_data"]
        page = data.get("_page", {}).get("next")
        if not page or not data["_data"]:
            return rows


def fetch() -> Registry:
    """Downloads the current settlements and streets of Vilnius district (a few seconds)."""
    municipality = next(
        m
        for m in _get_all("savivaldybe/Savivaldybe", "select(_id,pavadinimas)&limit(1000)")
        if m["pavadinimas"] == MUNICIPALITY
    )
    by_municipality = f"savivaldybe._id=%22{municipality['_id']}%22&limit(10000)"
    districts = {
        d["_id"]: d["pavadinimas"]
        for d in _get_all("seniunija/Seniunija", by_municipality)
        if not d.get("sen_iki")
    }
    settlements = {
        s["_id"]: Settlement(
            code=s["gyv_kodas"],
            name=s["pavadinimas"],
            genitive=s["pavadinimas_k"],
            abbr=s["tipo_santrumpa"],
            district=districts.get((s.get("seniunija") or {}).get("_id"), ""),
        )
        for s in _get_all("gyvenamojivietove/GyvenamojiVietove", by_municipality)
        if not s.get("gyv_iki")
    }
    # Streets can't be filtered by municipality, so page through the whole country (~70k).
    for street in _get_all("gatve/Gatve", "limit(20000)"):
        owner = settlements.get(street["gyvenamoji_vietove"]["_id"])
        if owner and not street.get("gat_iki"):
            owner.streets.append(
                Street(street["gat_kodas"], street["pavadinimas"], street["tipo_santrumpa"])
            )
    result = sorted(settlements.values(), key=lambda s: (s.district, s.name))
    for settlement in result:
        settlement.streets.sort(key=lambda t: t.name)
    return Registry(result)

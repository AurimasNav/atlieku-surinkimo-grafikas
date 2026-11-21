from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Kind = Literal["household", "packaging", "glass", "food", "green"]

# Bump only for breaking changes: installed apps refuse data newer than they understand.
# Additive fields (like `locations`) keep the version.
SCHEMA_VERSION = 1


def clean_text(value: object) -> str:
    """Collapses whitespace (including newlines and non-breaking spaces) to single spaces."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


@dataclass
class Area:
    """One row of a schedule: a group of addresses that share the same pickup dates."""

    kind: Kind
    name: str
    district: str | None = None
    group: str | None = None
    weekday: str | None = None
    # Free-text rule from the source when it can't be turned into exact dates.
    note: str | None = None
    dates: set[date] = field(default_factory=set)
    # Part of the newest published schedule for its kind, even if its dates have passed (glass
    # is collected once a quarter, so most rows are between pickups most of the time).
    current: bool = False
    # Provider.id of a company added after the first one (Nemenčinė, None), whose rows were
    # published before providers existed: their ids must not change.
    provider: str | None = None

    @property
    def id(self) -> str:
        # Stable across runs as long as the source text doesn't change, so the app can
        # keep the user's selection when a new period is published.
        key = "|".join([self.kind, self.group or "", self.district or "", self.name.casefold()])
        if self.provider:
            key += f"|{self.provider}"
        return f"{self.kind[0]}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"

    def to_json(self) -> dict:
        data: dict = {"id": self.id, "kind": self.kind, "name": self.name}
        for key in ("district", "group", "weekday", "note"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        data["dates"] = [d.isoformat() for d in sorted(self.dates)]
        if self.current:
            data["current"] = True
        if self.provider:
            data["provider"] = self.provider
        return data


@dataclass(frozen=True)
class Provider:
    """A waste company and the elderships (seniūnijos, register names) it serves."""

    id: str
    name: str
    url: str  # the page with its official schedules
    elderships: frozenset[str]
    # Rows list many settlements, comma-separated (locations.PlaceList).
    place_lists: bool = False
    # Rows are routes of the whole municipality: settlements, and streets of this town
    # (locations.RouteList).
    route_town: str | None = None
    # Rows are one settlement each, then which of its streets (locations.SettlementRows).
    settlement_rows: bool = False
    # Rows are routes in sections: the settlements of an eldership after its name ("Šimkaičių
    # sen.:"), or streets of this town (locations.SectionRoutes).
    section_town: str | None = None
    # Places the rows name in a way the register can't tell apart, as the rows write them and
    # as the register's genitive with its type: ("Naukaimio k. (Vytėnų)", "Naukaimio II k.").
    aliases: tuple[tuple[str, str], ...] = ()
    kinds: tuple[Kind, ...] = ("household", "packaging", "glass")
    # The first provider, published before there were several: its rows, places and files carry
    # no `provider` field, and its row ids stay as they were.
    legacy: bool = False

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "url": self.url}


@dataclass
class SourceFile:
    kind: Kind
    url: str
    file_name: str


@dataclass
class ParseResult:
    areas: list[Area]
    warnings: list[str] = field(default_factory=list)

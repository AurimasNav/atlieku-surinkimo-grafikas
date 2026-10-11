from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Kind = Literal["household", "packaging", "glass"]

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

    @property
    def id(self) -> str:
        # Stable across runs as long as the source text doesn't change, so the app can
        # keep the user's selection when a new period is published.
        key = "|".join([self.kind, self.group or "", self.district or "", self.name.casefold()])
        return f"{self.kind[0]}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"

    def to_json(self) -> dict:
        data: dict = {"id": self.id, "kind": self.kind, "name": self.name}
        for key in ("district", "group", "weekday", "note"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        data["dates"] = [d.isoformat() for d in sorted(self.dates)]
        return data


@dataclass
class SourceFile:
    kind: Kind
    url: str
    file_name: str


@dataclass
class ParseResult:
    areas: list[Area]
    warnings: list[str] = field(default_factory=list)

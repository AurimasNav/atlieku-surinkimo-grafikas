"""Šilutės r., Trakų r. and Šalčininkų r.: the schedules of the individual houses that UAB
„Ecoservice“ empties, in the PDFs of three pages:

    Šilutės r.      the municipality's page of waste management (silute.lt), one file:
                    "... buitinių atliekų ir antrinių žaliavų (iš individualių namų valdų)
                    konteinerių išvežimo grafikas 2026 m."
    Trakų r.        https://ecoservice.lt/trakugrafikai/, one file, its link "Peržiūrėti
                    grafiką" under "2026 m. Trakų r. mišrių komunalinių atliekų, pakuočių bei
                    stiklo atliekų surinkimo grafikas"
    Šalčininkų r.   https://ecoservice.lt/salcininkugrafikai/, "Individualių valdų mišrių
                    komunalinių atliekų išvežimo grafikas" and "... antrinių žaliavių ..."

The files are found by the texts of their links (or the heading before a link that says
nothing), then by the year in the file's name (tratc.select_files). A new year's files are
posted in December or January. silute.lt refuses GitHub's runners (HTTP 403, as the Address
Register's sites do): when it doesn't answer, the page and file are read from the copy in
pipeline/data that `python -m schedule_pipeline.snapshot` takes, with a warning of its age.

The files are tables Excel made, in the style of the Ecoservice files of Marijampolė county
(maatc.py), read with pdfplumber's table finder from the upright letters only, under a row of
months (names, or I-XII in Trakų r.):

    Šilutės r.: a block per route, the places in a row across the table, then the months and a
    row of days per waste type:

        ŠILUTĖS SENIŪNIJA: Pagrynių k., Šlažų k.
                     | Mėnuo        | Sausis | Vasaris | ... | Balandis | ...
                     | Mišrios      | 5      | 2       | ... | 13, 27   | ...
                     | komunalinės  |        |         |     |          |
                     | Pakuotės     | 5      | 2       | ... | 27       | ...
                     | Stiklas      | 5      | 2       | ... | 27       | ...

    Trakų r.: a row per route with its weekday, places and two rows of days, the containers of
    every waste type and those of mixed waste only:

        SAVAITĖS DIENOS | VIETOVĖ                  | ATLIEKŲ RŪŠIS               | I  | ...
        I               | Lentvario m.: Alyvų g.,  | VISŲ RŪŠIŲ KONTEINERIAI ... | 26 | ...
                        |                          | TIK buitinių atliekų ...    | 12 | ...

    Šalčininkų r. mixed waste: a row per route, its weekday and eldership, villages in capitals
    with their streets ("AKMENYNĖS K. - Bažnyčios g., Naujoji g., BAGDŽIULIŲ K., ..."); an
    eldership's cell spans its routes. Packaging and glass: an eldership, its places (none: the
    whole eldership) and a row of each ("POP", "STIK").

Strict: a month's cell that isn't days, a day the month doesn't have, places without dates,
dates without places or of no waste type, a column of an unknown title, a title year other
than the file name's, and a title whose waste type isn't the link's raise ValueError. Dates
that aren't on a route's weekday are a warning (Trakų r. 2026: "18" in August for a
Wednesday route).

The places are read by maatc.Routes (aratc.Routes: sections of elderships, a town's streets,
"(išskyrus ...)", "(tik ...)"), with this publisher's spellings first ("ŠILUTĖS MIESTO GATVĖS:",
"ŠVĖKŠNOS MIESTELIO GATVĖS:", the streets of a village after a dash). A street named with some
of its houses ("Gėlių g. (nelyginiai numeriai iki 25 ...)", "Gilijos g. (1, 3, 5, ...)") is that
street: the routes that name it are the choices the app gives. No street gets "no pickup": the
files list the streets of private houses, nothing says the others have none.

Next year's files continue the routes of this year that cover the same places (tratc.combine).

Two folders, a part (model.Provider) per municipality, as maatc writes its five:

    python -m schedule_pipeline.ecoservice --region silutes-r --out ../site/silutes-r
    python -m schedule_pipeline.ecoservice --region ecoservice --out ../site/ecoservice
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import cache, partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import addresses as address_points
from . import aratc, build, http, maatc, snapshot, tratc
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import (
    _SECTION_ITEM,
    _UPPER,
    _WORD,
    Clause,
    Index,
    _section_parts,
    _Stop,
    street_key,
    typed_streets,
    variant_key,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

COMPANY = "UAB „Ecoservice“"
SILUTE_PAGE = (
    "https://www.silute.lt/veiklos-sritys/aplinkosauga-ir-atlieku-tvarkymas/atlieku-tvarkymas/10160"
)
TRAKAI_PAGE = "https://ecoservice.lt/trakugrafikai/"
SALCININKAI_PAGE = "https://ecoservice.lt/salcininkugrafikai/"
# The page of every municipality's schedules, for the folder of Trakų r. and Šalčininkų r.
ECOSERVICE_PAGES = "https://ecoservice.lt/grafikai/"


# --- the places ------------------------------------------------------------------

# "ŠILUTĖS SENIŪNIJA:", "Trakų sen.:", "AKMENYNĖS SEN.:", "Eišiškių sen.", and those of two
# words: "ŽEMAIČIŲ NAUMIESČIO SENIŪNIJA:", "Senųjų Trakų sen.:", "BALTOSIOS VOKĖS SEN.:".
_ELDERSHIP = re.compile(
    rf"(?:\b(?P<scope>Visoje|Dalyje|Dalis)\s+)?"
    rf"\b(?P<name>(?:(?i:Žemaičių|Senųjų|Baltosios)\s+)?{_WORD})\s+(?i:sen\b\.?|seniūnij\w*)"
    r"\s*[:,]?",
    re.U,
)
_STREET = r"(?:g|skg|al|pl|tak|a|aklg|kel)"
# The houses of a street in a bracket: "(nelyginiai numeriai iki 25 ir lyginiai numeriai iki 28
# namo)", "(lyginiai namų numeriai)", "(15, 17, 19)", "(nuo Klaipėdos g. iki Cintijoniškių g.)",
# "(10,14namas)".
_HOUSES_WORDS = r"(?:\d|numer|nuo\b|iki\b|nam[oųa]|lygin|nelygin|sankr|posuk|posūk)"
# The publisher's spellings, as maatc.Routes reads them (before its own).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "ŠILUTĖS MIESTO GATVĖS:", "ŠVĖKŠNOS MIESTELIO GATVĖS:": the town's streets.
    (re.compile(rf"\b({_WORD})\s+(?i:miesto)\s+(?i:gatvės)\s*:"), r"\1 m.:"),
    (re.compile(rf"\b({_WORD})\s+(?i:miestelio)\s+(?i:gatvės)\s*:"), r"\1 mstl.:"),
    # The garden communities whose streets follow: 'SB„Voveraitė“ - ', 'S/B " Baldininkas" - ',
    # 'S/B "Poilsi".,'.
    (re.compile(r"\bS\s*/?\s*B\s*[\"„“”]\s*[^\"“”]*[\"“”]\s*\.?\s*-?\s*"), ""),
    # "Trakų sen., Trakų m. Užpelkių k., Veličkavos k., Žaizdrių k. – prie Trakų miesto
    # prijungtos teritorijos.": villages joined to the town, which the register still has.
    (
        re.compile(
            rf"\b({_WORD})\s+sen\.,\s*\1\s+m\.\s+(?=(?:[^–()]|\([^()]*\))*[–-]\s*prie\s+\1\s+"
            r"miesto\s+prijungtos)"
        ),
        r"\1 sen.: ",
    ),
    (re.compile(r"\s*[–-]\s*prie\s+\w+\s+miesto\s+prijungtos\s+teritorijos\.?"), ""),
    # "(be gatvių)": the addresses of a village without a street, the village's route for any
    # street no other route names.
    (re.compile(r"\s*\(\s*be\s+gatvi\w*\s*\)", re.I), ""),
    # "RŪDNINKŲ K. - ..., Poligonas; Ryto g., ...": the military range among the village's
    # streets, no homes.
    (re.compile(r"\bPoligonas\s*;\s*"), ""),
    # Some houses of a street: the street ("Gėlių g. (nelyginiai numeriai iki 25 ...)",
    # "Gilijos g., ( 25, 27, ...)", "Geležinkelio g(9,11,13)", "Rodūnės g nuo posūkio su
    # Žalioji g. 66 ...", "A. Mickevičiaus g.iki 48 mano)", "Saulėtoji g. 20", "Uogų g.25"),
    # and of a village by number ("Rudnios k.,(10,14namas)").
    (
        re.compile(rf"\b({_STREET})\.?\s*,?\s*\((?=[^()]*{_HOUSES_WORDS})[^()]*\)\.?", re.I),
        r"\1.",
    ),
    (re.compile(rf"\b({_STREET})(?:\.\s*|\s+)(?:nuo|iki)\b[^,;()]*\)?"), r"\1."),
    # "Krantinės g.,(nuo 27 namo nr. Lauko g., ...": a bracket of houses that isn't closed.
    (
        re.compile(
            rf"\(\s*(?:nuo|iki)\s+\d+\s*[a-zA-Z]?\s*(?:namo)?\s*(?:nr\.?)?\s*(?=[{_UPPER}])"
        ),
        "",
    ),
    (re.compile(rf"\b({_WORD})\s+(?:nuo|iki)\s+\d+\s*\w*\s*namo\s*nr\.?\s+g\."), r"\1 g."),
    (re.compile(rf"\b({_STREET})\.\s*\d+\s*[A-Za-z]?\b\s*(?=[,;)]|$|[{_UPPER}])"), r"\1. "),
    (re.compile(r"\bk\.\s*,?\s*\(\s*([\d\s,;]+)\s*nam\w*\s*\)"), r"k. (\1)"),
    # "Jašiūnų mstl., .( Aušros g., ...)": the town's streets.
    (re.compile(r",\s*\.\s*\("), " ("),
    # Types in capitals without a dot ("TARTOKO K", "BENOS VS,"), and without a dot before the
    # next place ("Geležinkelio g Gėlių g.", "Žalioji g ŽEMAITIŠKIŲ VS.", "Tartoko k Sodų g.").
    (re.compile(rf"\b([{_UPPER}]{{3,}})\s+K(?=\s|[,;:(]|$)"), r"\1 k."),
    (re.compile(rf"\b([{_UPPER}]{{3,}})\s+VS(?=\s|[,;:(]|$)"), r"\1 vs."),
    (re.compile(rf"(?<=[\wąčęėįšųūž]{{3}})\s+(g|k)(?=\s+[{_UPPER}])"), r" \1."),
    # A dash between places ("Ramioji g.-DAINAVOS k.", "Šalčininkėlių g.- TARTOKO K"), a dash
    # before a comma ("EIŠIŠKIŲ M. -, A. Mickevičiaus g."), no space after a type
    # ("Žalioji g.JURŠIŠKIŲ K.", "Marcinkiškės k.MILETIŠKIŲ K.", "m.A. Mickevičiaus g."), two
    # dots ("Žižmų g.. GUDELIŲ k.").
    (re.compile(rf"(?<=[gk])\.\s*-\s*(?=[{_UPPER}]{{2}})"), "., "),
    (re.compile(r"\s+-\s*,"), ","),
    (re.compile(rf"\b(g|k|m|vs|mstl|pl|al|skg|K|M|VS|MSTL)\.(?=[{_UPPER}])"), r"\1. "),
    (re.compile(r"\.{2,}"), "."),
)
# A part of a town in words: "Trakų m. – buvusi Babriškių k. teritorija", which the town's
# list of streets gets as a choice of its own. Kept as "Trakų m. (⟦0⟧)" through
# aratc.normalize, which would split it.
_TOWN_PART = re.compile(
    rf"\b(?P<town>{_WORD})\s+m\.\s*[–-]\s*(?P<label>buvusi\s+[^,;]*?teritorija)"
)
_TOWN_PART_MARK = re.compile(r"(?P<town>.+?)\s+m\.\s*\(⟦(?P<number>\d+)⟧\)")
_THIRD = re.compile(r"\b3-(i?)asis\b")
# The next place after the streets of a bracket that isn't closed: ", Keidžių k.".
_NEXT_PLACE = re.compile(rf",\s*(?={_WORD}(?:\s+{_WORD})*\s+(?:k|vs|mstl|m)\.)")


def _close_brackets(text: str) -> str:
    """Closes a bracket of streets that isn't, before the next place: "Jašiūnų mstl.(Azalijų
    g., ..., Žalioji g., Keidžių k., Krokšlių vs., ..." (Šalčininkų r. 2026 packaging), or at
    the end."""
    opened: list[int] = []
    for i, ch in enumerate(text):
        if ch == "(":
            opened.append(i)
        elif ch == ")" and opened:
            opened.pop()
    for start in reversed(opened):
        after = _NEXT_PLACE.search(text, start)
        end = after.start() if after else len(text)
        text = f"{text[:end]}){text[end:]}"
    return text


class Routes(maatc.Routes):
    """Reads the places of one municipality's rows (its provider's), as maatc.Routes does,
    with the spellings of these files first (_FIXES), elderships of two words, a part of a town
    in words ("Trakų m. – buvusi Babriškių k. teritorija": a choice of its own in the town's
    list of streets), and a village the row puts in another eldership, of which the
    municipality has several, by the streets in its bracket ("Senųjų Trakų sen.: ... Varnikų k.
    (be Pakrantės g. ir Kraštinė g.)": the Varnikai of Trakų sen. that has them)."""

    eldership = _ELDERSHIP

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        super().__init__(index, provider, variants)
        self.town_parts: list[str] = []  # of the row being read

    @staticmethod
    def municipality_of(provider: Provider) -> maatc.Municipality:
        return BY_PROVIDER[provider.id]

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        text = _close_brackets(text)
        self.town_parts = []

        def town_part(match: re.Match[str]) -> str:
            self.town_parts.append(clean_text(match["label"]))
            return f"{match['town']} m. (⟦{len(self.town_parts) - 1}⟧)"

        return super().spellings(_TOWN_PART.sub(town_part, text))

    def section(self, district: str, text: str) -> list[_Stop]:
        kept: list[str] = []
        stops: list[_Stop] = []
        for part in _section_parts(text):
            if match := _TOWN_PART_MARK.fullmatch(part):
                stops += self._town_part(match["town"], self.town_parts[int(match["number"])])
            elif elsewhere := self._elsewhere(district, part):
                stops += elsewhere
            else:
                kept.append(part)
        return super().section(district, ", ".join(kept)) + stops

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        """maatc.Routes' clauses; a street of a town's list that the town doesn't have is that
        of the place of its eldership that has it: none more if the route has that place
        whole ("Lentvario m. (Gabijos g., ...)" of Račkūnai, "Račkūnų k." in the same route),
        or its one place ("Šilutės m.: ... Aviečių g." of Pagryniai, another route's)."""
        found, skipped = super().clauses(area)
        whole = {s.code for s, c in found if c.streets is None and not c.fallback}
        unknown = []
        for entry in self.unknown:
            where, _, street = entry.partition(": ")
            towns = [
                s
                for s in self.places[self.municipality.label]
                if s.abbr in ("m.", "mstl.") and f"{s.genitive} {s.abbr}" == where
            ]
            # Spelled as the register does: not a typo of another street.
            having = {
                s.code: (s, keys)
                for town in towns
                for s in self.places[self.municipality.label]
                if s.district == town.district
                and s is not town
                and (keys := {street_key(t) for t in s.streets if fold(t.label) == fold(street)})
            }
            if having and having.keys() & whole:
                continue
            if len(having) == 1:
                settlement, keys = next(iter(having.values()))
                found.append((settlement, Clause(area.id, keys)))
                continue
            unknown.append(entry)
        self.unknown = unknown
        return found, skipped

    def streets(
        self, settlement: Settlement, part: str, name: str, kind: str | None, loose: bool = True
    ) -> set[str]:
        """maatc.Routes' streets, and "3-asis" for the register's "3-iasis" and the other way
        round: Šilutė has "Baldininkų 3-iasis tak." and "Aušros 3-asis tak.", the file writes
        both "3-asis"."""
        found = super().streets(settlement, part, name, kind, loose)
        if found or not _THIRD.search(part):
            return found

        def other(text: str) -> str:
            return _THIRD.sub(lambda m: "3-asis" if m[1] else "3-iasis", text)

        return super().streets(settlement, other(part), other(name), kind, loose)

    def _town_part(self, name: str, label: str) -> list[_Stop]:
        towns = [s for s in self.settlements(name, None, "m", "") if s.abbr == "m."]
        if len(towns) != 1:
            self.unknown.append(f"{name} m.: {label[:60]}")
            return []
        label = label[0].upper() + label[1:]
        key = variant_key(label)
        self.variants[towns[0].code].setdefault(key, label)
        return [_Stop(towns[0], {key})]

    def _elsewhere(self, district: str, part: str) -> list[_Stop]:
        """A village the section's eldership doesn't have, of which the municipality has
        several: those of one other eldership that have the streets of its bracket."""
        head, _, rest = part.partition("(")
        if not district or not rest:
            return []
        match = _SECTION_ITEM.fullmatch(head.strip(" ,;:"))
        if not match or match["type"] != "k" or match["numerals"]:
            return []
        if self.settlements(match["name"], None, "k", district):
            return []
        key = fold(match["name"])
        spec = rest.rsplit(")", 1)[0]
        bare = re.sub(r"^\s*(?:be|i[sš]+kyrus|tik)\b", "", spec)
        parts = [p for chunk in re.split(r"\bir\b", bare) for p in _section_parts(chunk)]
        having = [
            s
            for s in self.places[self.municipality.label]
            if key in (fold(s.name), fold(s.genitive)) and any(typed_streets(p, s) for p in parts)
        ]
        if len({s.district for s in having}) != 1:
            return []
        stops = [_Stop(s) for s in having]
        self.spec(stops, spec)
        return stops


def _provider(id: str, page: str, elderships: set[str], aliases=()) -> Provider:
    return Provider(
        id=id,
        name=COMPANY,
        url=page,
        elderships=frozenset(elderships),
        aliases=aliases,
        kinds=("household", "packaging", "glass"),
        reader=Routes,
    )


# Mixed waste, packaging and glass in one file.
ALL_IN_ONE: dict[Kind, tuple[Kind, ...]] = {"household": ("household", "packaging", "glass")}

SILUTE = maatc.Municipality(
    _provider(
        "silute",
        SILUTE_PAGE,
        {
            "Gardamo",
            "Juknaičių",
            "Katyčių",
            "Kintų",
            "Rusnės",
            "Saugų",
            "Usėnų",
            "Vainuto",
            "Šilutės",
            "Švėkšnos",
            "Žemaičių Naumiesčio",
        },
        aliases=(
            ("Vilkėnų I, II, III k.", "Vilkėno I, II, III k."),
            ("M. Hofmono g.", "M. Hofmano g."),  # Mikelio Hofmano g.
        ),
    ),
    snapshot.SILUTE_MUNICIPALITY,
    snapshot.SILUTE_REGISTRY_FILE,
    snapshot.SILUTE_ADDRESSES_FILE,
    # 2026: 27 routes, each with mixed waste, packaging and glass dates, which gave a mixed
    # waste schedule to 271 of the 297 settlements.
    min_areas={"household": 20, "packaging": 20, "glass": 20},
    min_household_places=220,
    # About 16,400 addresses in 2026.
    min_address_points=11_000,
    label="Šilutės r.",
    file_kinds=ALL_IN_ONE,
)
TRAKAI = maatc.Municipality(
    _provider(
        "trakai",
        TRAKAI_PAGE,
        {
            "Aukštadvario",
            "Grendavės",
            "Lentvario",
            "Onuškio",
            "Paluknio",
            "Rūdiškių",
            "Senųjų Trakų",
            "Trakų",
        },
    ),
    snapshot.TRAKAI_MUNICIPALITY,
    snapshot.TRAKAI_REGISTRY_FILE,
    snapshot.TRAKAI_ADDRESSES_FILE,
    # 2026: 24 routes, each with mixed waste, packaging and glass dates, which gave a mixed
    # waste schedule to 324 of the 437 settlements.
    min_areas={"household": 18, "packaging": 18, "glass": 18},
    min_household_places=260,
    # About 25,800 addresses in 2026.
    min_address_points=18_000,
    label="Trakų r.",
    file_kinds=ALL_IN_ONE,
)
SALCININKAI = maatc.Municipality(
    _provider(
        "salcininkai",
        SALCININKAI_PAGE,
        {
            "Akmenynės",
            "Baltosios Vokės",
            "Butrimonių",
            "Dainavos",
            "Dieveniškių",
            "Eišiškių",
            "Gerviškių",
            "Jašiūnų",
            "Kalesninkų",
            "Pabarės",
            "Poškonių",
            "Turgelių",
            "Šalčininkų",
        },
        aliases=(
            ("S GIRIOS K.", "GIRIOS K."),
            ("NEBIGĖNŲ K.", "NEGIBĖNŲ K."),  # Negibėnai, with Negibėnų g.
            ("A.MIckeviciau g.", "A. Mickevičiaus g."),
            ("Kovo g.11-osios g.", "Kovo 11-osios g."),
        ),
    ),
    snapshot.SALCININKAI_MUNICIPALITY,
    snapshot.SALCININKAI_REGISTRY_FILE,
    snapshot.SALCININKAI_ADDRESSES_FILE,
    # 2026: 34 mixed waste routes, and 19 packaging and glass routes (a file of their own),
    # which gave a mixed waste schedule to 384 of the 444 settlements.
    min_areas={"household": 25, "packaging": 14, "glass": 14},
    min_household_places=300,
    # About 16,500 addresses in 2026.
    min_address_points=11_000,
    label="Šalčininkų r.",
    file_kinds={"packaging": ("packaging", "glass")},
)
MUNICIPALITIES = (SILUTE, TRAKAI, SALCININKAI)
BY_PROVIDER = {m.provider.id: m for m in MUNICIPALITIES}


@dataclass(frozen=True)
class Region:
    """A folder of the site: its municipalities, a part each."""

    municipalities: tuple[maatc.Municipality, ...]
    source: str  # schedule.json's `source`
    title: str  # of the job summary


REGIONS = {
    "silutes-r": Region((SILUTE,), SILUTE_PAGE, "Šilutės r. (Ecoservice)"),
    "ecoservice": Region((TRAKAI, SALCININKAI), ECOSERVICE_PAGES, "Trakų r., Šalčininkų r."),
}


# --- the pages ---------------------------------------------------------------


class _Links(HTMLParser):
    """The page's links with their texts, and the text before each (a heading above a link
    that says nothing: "Peržiūrėti grafiką")."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []
        self.before: list[str] = []
        self.skip = 0  # inside <script> or <style>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "a":
            self.href, self.text = dict(attrs).get("href") or "", []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag == "a" and self.href is not None:
            before = clean_text(" ".join(self.before))[-300:]
            self.links.append((self.href, clean_text("".join(self.text)), before))
            self.href, self.before = None, []

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self.href is not None:
            self.text.append(data)
        else:
            self.before.append(data)


# Files that aren't the schedules of individual houses, by their texts (folded).
OTHERS = maatc.OTHERS + ("pusiau pozemin", "aikstel", "kolektyvin")


def file_kind(text: str) -> Kind | None:
    """The kind of a file by its text: "... mišrių komunalinių atliekų ..." and "... buitinių
    atliekų ir antrinių žaliavų ..." are mixed waste (Šilutės r. and Trakų r.: with packaging
    and glass inside), "... antrinių žaliavių ..." packaging."""
    folded = fold(text)
    if "maist" in folded:
        return "food"
    if "komunalin" in folded or "buitin" in folded:
        return "household"
    if "stikl" in folded:
        return "glass"
    if "pakuo" in folded or "antrin" in folded:
        return "packaging"
    return None


def find_files(html: str, page_url: str) -> list[SourceFile]:
    """The PDF schedules the page links, by the texts of their links or the text before."""
    collector = _Links()
    collector.feed(html)
    files: list[SourceFile] = []
    for href, text, before in collector.links:
        url = urljoin(page_url, href)
        path = urlsplit(url).path
        if not path.lower().endswith(".pdf") or "/uploads/" not in path:
            continue
        described = text if file_kind(text) else before[-200:]
        kind = file_kind(described)
        folded = fold(described)
        if kind is None or "grafik" not in folded or any(word in folded for word in OTHERS):
            continue
        if any(f.url == url for f in files):
            continue
        files.append(SourceFile(kind=kind, url=url, file_name=PurePosixPath(unquote(path)).name))
    return files


# Copies of the page and files of a site that refuses GitHub's runners, taken from a machine
# it answers (snapshot.py), as the Address Register's: silute.lt answers them HTTP 403.
COPIES = {"silute": snapshot.SILUTE_COPY_DIR}
COPY_INDEX = snapshot.SITE_COPY_INDEX


def _live(url: str) -> bytes:
    return http.get(url, timeout=60)


_copied = snapshot.site_copy


def _download(
    municipality: maatc.Municipality, today: date, get
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    page = municipality.provider.url
    html = get(page).decode("utf-8", errors="replace")
    files, warnings = tratc.select_files(find_files(html, page), today)
    return [(f, get(f.url)) for f in files], warnings


def download(
    municipality: maatc.Municipality, today: date, keep_days: int
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The municipality's page and the files it links, or where the site doesn't answer and
    there is a copy (COPIES), the copy's, with a warning that says how old it is."""
    try:
        return _download(municipality, today, _live)
    except OSError as error:
        folder = COPIES.get(municipality.provider.id)
        if folder is None or not (folder / COPY_INDEX).exists():
            raise
        files, warnings = _download(municipality, today, partial(_copied, folder))
        note = snapshot.site_copy_note(municipality.provider.url, error, folder, today)
        print(note, file=sys.stderr)
        return files, [note, *warnings]


def save_copy(municipality: maatc.Municipality, folder: Path, today: date | None = None) -> None:
    """Saves the municipality's page and the files it links in `folder`, for download when
    the site doesn't answer: python -m schedule_pipeline.snapshot."""
    page = municipality.provider.url
    today = today or snapshot.utc_today()
    html = _live(page)
    files, _ = tratc.select_files(find_files(html.decode("utf-8", "replace"), page), today)
    contents = [(f.url, _live(f.url)) for f in files]
    snapshot.save_site_copy(folder, page, html, contents, today)


# --- the tables ------------------------------------------------------------------

_ROMAN = {r: n for n, r in enumerate("I II III IV V VI VII VIII IX X XI XII".split(), start=1)}
# The weekday of a route: "I" (Monday) to "VII", "vII".
_WEEKDAY = re.compile(r"(?i:VII|VI|IV|V|III|II|I)")
# A weekday at the start of a line of places (Trakų r. 2026: the cell of a route's weekday is
# one with its places, "... Naujosios\nIII Sodybos g., ...").
_WEEKDAY_LINE = re.compile(r"^(VII|VI|IV|V|III|II|I)\s+(?!k\.|vs\.)", re.M)
# An eldership's cell: "AKMENYNĖS SEN.:", "Eišiškių sen.", "BALTOSIOS VOKĖS SEN.:".
_ELDERSHIP_CELL = re.compile(rf"(?:{_WORD}\s+)?{_WORD}\s+(?i:sen\b\.?|seniūnij\w*)\s*[.:,]?", re.U)
# A line of places that ran over its cell's lower border into the next route's: a type and
# streets without the name, which is the last word of the route above ("VĖŽIONIŲ" + "K -
# Jazminų g", Šalčininkų r. 2026).
_RUN_ON = re.compile(r"(?:K|k|M|m)\.?\s+-\s+\S.*")
# The waste types of a cell (folded), by the start of a word: "Mišrios komunalinės", "VISŲ
# RŪŠIŲ KONTEINERIAI Buitinių atliekų ir popierius, plastikas, stiklas", "TIK buitinių atliekų
# konteineriai", "Pakuotės", "POP", "STIK" (not "plastikas").
KIND_WORDS: tuple[tuple[re.Pattern[str], Kind], ...] = (
    (re.compile(r"\b(?:misri|komunalin|buitin)"), "household"),
    (re.compile(r"\bmaist"), "food"),
    (re.compile(r"\bstik"), "glass"),
    (re.compile(r"\b(?:pakuo|pop|plast|antrin)"), "packaging"),
)
# The titles of the columns before the months (folded), and what they hold.
TITLES: tuple[tuple[str, str], ...] = (
    ("savait", "weekday"),
    ("vietov", "places"),
    ("marsrut", "places"),
    ("rusis", "kind"),
    ("menuo", "kind"),
    ("seniunij", "eldership"),
)
# Rows that aren't places: titles, notices, the contacts under the table (folded).
NOT_PLACES = re.compile(
    rf"{maatc.NOT_PLACES.pattern}|\becoservice\b|^(?:adresas|telefonas|darbo laikas)\b"
)
# The waste types of a file of each kind's title (folded), the first that matches.
TITLE_KINDS: tuple[tuple[str, Kind], ...] = (
    ("maist", "food"),
    ("komunalin", "household"),
    ("buitin", "household"),
    ("stikl", "glass"),
    ("pakuo", "packaging"),
    ("antrin", "packaging"),
)


def kinds(text: str) -> set[Kind]:
    folded = fold(text)
    return {kind for pattern, kind in KIND_WORDS if pattern.search(folded)}


@dataclass
class _Header:
    """A row of months: which column is which."""

    months: dict[int, date]  # column -> the month's first day
    width: int
    roles: dict[int, str]  # columns before the months, by their titles


def _title_role(title: str, where: str) -> str | None:
    folded = fold(title)
    if not folded:
        return None
    for word, role in TITLES:
        if word in folded:
            return role
    raise ValueError(f"{where}: a column {title!r} before the months")


def _is_titles(cells: list[str]) -> bool:
    """A row of the columns' titles above the months (Trakų r.)."""
    filled = [fold(c) for c in cells if c]
    return bool(filled) and all(
        len(c.split()) <= 3 and any(w in c for w, _ in TITLES) for c in filled
    )


def _header(cells: list[str], titles: list[str] | None, year: int, where: str) -> _Header | None:
    """A row of at least six months one after another, by name or number: its columns, the
    titles of those before them from the row or the row above (`titles`)."""
    found: dict[int, int] = {}
    for i, cell in enumerate(cells):
        number = aratc.MONTHS.get(fold(cell)) or _ROMAN.get(cell.strip())
        if number:
            found[i] = number
    if len(found) < 6:
        return None
    columns = sorted(found)
    numbers = [found[i] for i in columns]
    if columns != list(range(columns[0], columns[0] + len(columns))) or any(
        (b - a) % 12 != 1 for a, b in zip(numbers, numbers[1:], strict=False)
    ):
        raise ValueError(f"{where}: months out of order: {numbers}")
    months: dict[int, date] = {}
    for i in columns:
        if months and found[i] < months[i - 1].month:
            year += 1
        months[i] = date(year, found[i], 1)
    first = columns[0]
    named = [c for c in cells[:first] if fold(c)]
    source = cells if named or titles is None else titles
    roles = {i: role for i in range(first) if (role := _title_role(source[i], where))}
    return _Header(months, len(cells), roles)


def _role(cell: str) -> str:
    """What a cell of a column without a title holds, by its text."""
    if _WEEKDAY.fullmatch(cell):
        return "weekday"
    if _ELDERSHIP_CELL.fullmatch(cell):
        return "eldership"
    if kinds(cell) and len(fold(cell).split()) <= 6:
        return "kind"
    return "places"


def _title(text: str) -> tuple[str, int | None]:
    """The file's title, folded, and its year: "... GRAFIKAS 2026 METAMS", "... surinkimo
    grafikas Šilutės rajono savivaldybės teritorijoje 2026 m.", "... grafikas Šalčininkų r.
    2026 m."."""
    folded = fold(text)
    match = re.search(r"\bgrafik\w*\b.{0,80}?\b(20\d{2})\s+(?:m|metams|metu)\b", folded)
    if not match:
        return "", None
    return folded[: match.end()], int(match.group(1))


@dataclass
class _Route:
    """A route's places, its weekday if the table says, and the days of each set of waste
    types collected on them."""

    places: str
    where: str
    weekday: int | None = None  # 1 (Monday) to 7
    dates: list[tuple[frozenset[Kind], set[date]]] = field(default_factory=list)


def _routes(source: SourceFile, content: bytes) -> list[_Route]:
    """The routes of a file. Strict (ValueError): a month's cell that isn't days, a day the
    month doesn't have, places without dates, dates without places or of no waste type, a
    column of an unknown title, and a file without a table."""
    routes: list[_Route] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        first = (pdf.pages[0].filter(maatc._upright).extract_text() or "") if pdf.pages else ""
        title, year = _title(first)
        if year is None:
            raise ValueError(f"{source.file_name}: no title with a year")
        expected = tratc.file_year(source.file_name)
        if expected and year != expected:
            raise ValueError(f"{source.file_name}: the title says {year}, the file name {expected}")
        kind = next((kind for word, kind in TITLE_KINDS if word in title), None)
        if kind != source.kind:
            raise ValueError(f"{source.file_name}: a {kind} schedule, its link says {source.kind}")
        header: _Header | None = None
        current: _Route | None = None  # the route whose days are being read
        pending: list[str] = []  # rows of places across the table, until the months under them
        titles: list[str] | None = None  # a row of the columns' titles, above the months
        eldership = ""  # of the routes under an eldership's cell that spans them
        for page in pdf.pages:
            where = f"{source.file_name} page {page.page_number}"
            for table in page.filter(maatc._upright).extract_tables():
                for row in table:
                    raw = [value or "" for value in row]
                    cells = [maatc._cell(value) for value in raw]
                    text = " ".join(c for c in cells if c)
                    if not text:
                        continue
                    new = _header(cells, titles, year, where)
                    if new:
                        header, current, titles, eldership = new, None, None, ""
                        if pending:
                            current = _Route(" ".join(pending), where)
                            routes.append(current)
                            pending = []
                        continue
                    if NOT_PLACES.search(fold(text)):
                        continue
                    if _is_titles(cells):
                        titles = cells
                        continue
                    titles = None
                    if header is None:
                        pending.append(text)
                        continue
                    if len(cells) != header.width:
                        raise ValueError(
                            f"{where}: a row of {len(cells)} columns under {header.width}"
                        )
                    dates: set[date] = set()
                    for i, month in header.months.items():
                        for day in maatc._days(cells[i], where):
                            try:
                                dates.add(month.replace(day=day))
                            except ValueError as error:
                                raise ValueError(
                                    f"{where}: day {day} of {month:%Y-%m}: {error}"
                                ) from error
                    first_month = min(header.months)
                    if not dates:
                        filled = [c for c in cells if c]
                        if len(filled) == 1 and not any(cells[i] for i in header.months):
                            pending.append(text)  # places across the table (Šilutės r.)
                            continue
                        raise ValueError(f"{where}: places without dates: {text[:80]!r}")
                    if pending:
                        raise ValueError(f"{where}: places without dates: {pending[0][:80]!r}")
                    weekday, places, label, elder = None, [], [], ""
                    for i in range(first_month):
                        cell, value = cells[i], raw[i]
                        if not cell:
                            continue
                        role = header.roles.get(i) or _role(cell)
                        if role == "weekday" and not _WEEKDAY.fullmatch(cell):
                            # The weekday's cell with the places in it.
                            line = _WEEKDAY_LINE.search(value)
                            if line:
                                weekday = _ROMAN[line.group(1)]
                                value = value[: line.start()] + value[line.end() :]
                            role, cell = "places", maatc._cell(value)
                        if role == "weekday":
                            weekday = _ROMAN[cell.upper()]
                        elif role == "eldership":
                            elder = cell
                        elif role == "kind":
                            label.append(cell)
                        else:
                            lines = value.strip().split("\n")
                            if routes and _RUN_ON.fullmatch(lines[0].strip()):
                                routes[-1].places += f" {clean_text(lines[0])}"
                                cell = maatc._cell("\n".join(lines[1:]))
                            if cell:
                                places.append(cell)
                    if elder:
                        eldership = elder
                    if places or elder:
                        name = clean_text(" ".join(places))
                        if eldership:
                            # "AKMENYNĖS SEN.: AKMENYNĖS K. - ...", "Akmenynės sen." alone.
                            section = re.sub(r"[\s.:,]+$", "", eldership)
                            name = f"{section}.: {name}" if name else f"{section}."
                        current = _Route(name, where, weekday)
                        routes.append(current)
                    elif current is None:
                        raise ValueError(f"{where}: dates without places ({text[:60]!r})")
                    found = kinds(" ".join(label)) if label else {source.kind}
                    if not found:
                        raise ValueError(f"{where}: dates of no waste type ({label!r})")
                    current.dates.append((frozenset(found), dates))
        if pending:
            raise ValueError(f"{source.file_name}: places without dates: {pending[0][:80]!r}")
    if not routes:
        raise ValueError(f"{source.file_name}: no schedule table found")
    return routes


def _usual_weekday(dates: set[date]) -> int | None:
    """The weekday (1-7) of all but one or two of six dates or more, where the table has no
    column of weekdays: the others are likely typos (Šalčininkų r. 2026 packaging, Jašiūnų
    sen.: "17" in November for a Friday route)."""
    if len(dates) < 6:
        return None
    weekday, count = Counter(d.isoweekday() for d in dates).most_common(1)[0]
    return weekday if count >= len(dates) - 2 else None


def parse_file(
    source: SourceFile, content: bytes, municipality: maatc.Municipality = SILUTE
) -> ParseResult:
    """The schedules of a file's routes: one per waste type of a route. A file has only the
    waste types `Municipality.file_kinds` gives its kind, or it raises ValueError."""
    allowed = municipality.file_kinds.get(source.kind, (source.kind,))
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for route in _routes(source, content):
        name = route.places
        if maatc.SHARED.search(fold(name)):
            warnings.append(f"{route.where}: shared containers, not read: {name[:60]!r}")
            continue
        by_kind: dict[Kind, set[date]] = defaultdict(set)
        for found, dates in route.dates:
            for kind in found:
                by_kind[kind] |= dates
        for kind, dates in sorted(by_kind.items()):
            if kind not in allowed:
                raise ValueError(f"{route.where}: {kind} dates in a {source.kind} file")
            weekday = route.weekday or _usual_weekday(dates)
            off = sorted(d for d in dates if weekday and d.isoweekday() != weekday)
            if weekday and off:
                days = ", ".join(d.isoformat() for d in off)
                warnings.append(
                    f"{route.where}: {kind} of {name[:60]!r} on {days}, not on its weekday "
                    f"({WEEKDAY_NAMES[weekday - 1]})"
                )
            area = Area(
                kind=kind,
                name=name,
                district=municipality.label,
                dates=dates,
                provider=municipality.provider.id,
            )
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{route.where}: {kind} of {name[:60]!r} is listed twice")
                existing.dates |= area.dates
                existing.weekday = existing.weekday if existing.weekday == area.weekday else None
    return ParseResult(areas=list(areas.values()), warnings=warnings)


# --- the sources and the output ----------------------------------------------------


def source(municipality: maatc.Municipality) -> build.Source:
    return build.Source(
        municipality.provider,
        partial(download, municipality),
        partial(parse_file, municipality=municipality),
        municipality.min_areas,
        municipality.min_household_places,
        municipality.file_kinds,
        partial(tratc.combine, municipality=municipality),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--region", choices=sorted(REGIONS), required=True, help="the folder")
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    parser.add_argument(
        "--published",
        help="site folder with yesterday's schedule.json, for a municipality whose build fails "
        "(default: the region's folder on the site)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any municipality's build fails instead of keeping its published part",
    )
    args = parser.parse_args(argv)
    region = REGIONS[args.region]
    published = args.published or f"{build.PUBLISHED_URL}/{args.region}"

    loader = None if args.strict else cache(build.load_published(published))
    results: list[build.PartResult] = []
    registries: list[tuple[maatc.Municipality, Registry]] = []
    points: list[address_points.AddressPoint] = []
    notes: list[str] = []
    down: set[str] = set()  # live sources that failed
    try:
        for municipality in region.municipalities:
            name, code = municipality.register
            registry, registry_note = build.live_or_snapshot(
                f"Address Register ({municipality.label})",
                tratc._once(partial(address_register.fetch, name), "register", down),
                partial(snapshot.load_registry, municipality.registry_file),
            )
            found, points_note = build.live_or_snapshot(
                f"Address points ({municipality.label})",
                tratc._once(partial(address_points.fetch, code), "points", down),
                partial(snapshot.load_points, municipality.addresses_file),
            )
            notes += [n for n in (registry_note, points_note) if n]
            registries.append((municipality, registry))
            points += found
            results += build.build_parts(
                (source(municipality),), registry, date.today(), args.keep_days, loader
            )
        parts = [(r.provider, r.part) for r in results if r.part]
        dataset = build.merge_parts(parts, region.source)
        served = {loc["id"] for loc in dataset["locations"]}
        everything = Registry([s for _, registry in registries for s in registry.settlements])
        addresses = address_points.build_addresses(
            points, everything, served, dataset["generatedAt"]
        )
        places = Counter(addresses["places"][point[2]][0] for point in addresses["points"])
        for municipality, registry in registries:
            count = sum(places[f"g{s.code}"] for s in registry.settlements)
            if any(r.part for r in results if r.provider == municipality.provider) and (
                count < municipality.min_address_points
            ):
                raise build.ValidationError(f"{municipality.label}: only {count} address points")
    except (build.ValidationError, OSError, ValueError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1

    for municipality, r in zip(region.municipalities, results, strict=True):
        if r.error:
            if r.part:
                kept = f"the data published on {r.part['generatedAt'][:10]} is kept"
            else:
                kept = "there is no published data to keep, so it is left out"
            # An annotation on the workflow run.
            print(f"::warning::The {municipality.label} build failed; {kept}. {r.error}")

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    # A section per municipality: the company's name is the same in each.
    for municipality, r in zip(region.municipalities, results, strict=True):
        part = r.part or {"locations": [], "areas": []}
        title, file_name = f"{municipality.label} (Ecoservice)", f"{args.out.name}/schedule.json"
        build.write_summary(part, [r], [], title, f"{municipality.label} in {file_name}")
    build.write_summary(dataset, [], notes, region.title, f"{args.out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

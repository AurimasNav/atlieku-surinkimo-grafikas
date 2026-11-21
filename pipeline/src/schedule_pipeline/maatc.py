"""Marijampolės regionas: the schedules of the individual houses of the five municipalities of
Marijampolė county, published by its regional waste centre, UAB „Marijampolės apskrities
atliekų tvarkymo centras“ (maatc.lt): Marijampolės sav., Vilkaviškio r., Kalvarijos sav., Kazlų
Rūdos sav. and Šakių r. UAB „Ecoservice“ collects mixed waste everywhere, and packaging and glass
everywhere but in Šakių r.; UAB „Ekonovus“ collects food waste everywhere, and packaging and glass
in Šakių r. Marijampolė is mostly apartment buildings with shared containers, whose schedules
aren't read; the streets of its private houses are in the files.

The centre has a page per municipality (…/marijampoles-sav/, …/sakiu-raj-sav/) whose buttons
describe each file ("2026 m. Šakių rajono sav. individualių valdų mišrių komunalinių atliekų
konteinerių aptarnavimo grafikas"). The files of individual houses are found by these texts and
the year in the file's name; those of shared containers, their washing, businesses, cemeteries,
rest areas and bulky waste aren't read. A new year's files are posted in December.

The files are tables in two templates, both read with pdfplumber's table finder from the upright
letters only:

    Ecoservice: a block per route, the places in a row across the table, then the months and a
    row of days per set of containers emptied those days:

        KAZLŲ RŪDOS SEN.: Kazlų I k. (tik Miško g., Beržų g.).
                                                             | sausis | vasaris | kovas | ...
        Mišrios komunalinės atliekos/Pakuočių (mėlynas)      | 5      | 2       | 2, 30 | ...
        konteineris/Stiklo konteineris
        Mišrios komunalinės atliekos                         | 19     | 16      | 16    | ...

    (Vilkaviškio r. packaging: rows "Popierius / Plastikas" and "Stiklas", "-" for no pickup,
    and a column of weekdays.) The elderships, written bottom to top in a column on the left,
    aren't read: the places name theirs ("KAZLŲ RŪDOS SEN.:", "MARIJAMPOLĖS M.:").

    Ekonovus: a row per route, with its places and days, under a row of months:

        Grafikas          | Maršrutas                               | Sausis | ... | Gruodis
        kas 14 d.,        | Gelgaudiškio sen.: Daukantiškių k., ... | 14,28  | ... | 2,16,30
        trečiadienis 7321 | Šakių sen.: Giedručių k.                |        |     |

The places are read by aratc.Routes, the reader of the Alytus county files, which are written in
the same ways (sections of elderships, a town's streets, "(išskyrus ...)", "(tik ...)", "(nuo
... iki ...)"). Next year's files continue the routes of this year that cover the same places
(tratc.combine).

The five municipalities are written to one <out>/schedule.json and <out>/addresses.json, a part
(model.Provider) each, as tratc does: the app downloads one file for the region, and a
municipality whose build fails keeps its part of yesterday's file.
Run: python -m schedule_pipeline.maatc --out ../site/maatc
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
from . import aratc, build, http, snapshot, tratc
from . import registry as address_register
from .dates import WEEKDAY_NAMES
from .locations import (
    _EXCEPT,
    _UPPER,
    _WORD,
    Clause,
    Index,
    _section_parts,
    _Stop,
    street_key,
    typed_streets,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold

PAGES = "https://maatc.lt/atlieku-isvezimo-grafikai/"
# Yesterday's data, for the part of a municipality whose build fails today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/maatc"
COMPANY = "UAB „Marijampolės apskrities atliekų tvarkymo centras“"


@dataclass(frozen=True)
class Municipality(tratc.Municipality):
    """What differs per municipality (tratc.Municipality: its page is its provider's url), with
    its elderships as aratc.Routes reads them."""

    @property
    def elderships(self) -> frozenset[str]:
        return self.provider.elderships


# --- the places ------------------------------------------------------------------

# "MOKOLŲ SEN.:", "LIUDVINAVO SEN:", "Kidulių sen.:", and the elderships of two words, "KAZLŲ
# RŪDOS SEN.:", "Kudirkos Naumiesčio sen.:" (aratc's marks have one).
_ELDERSHIP = re.compile(
    rf"(?:\b(?P<scope>Visoje|Dalyje|Dalis)\s+)?"
    rf"\b(?P<name>(?:(?i:Kazlų|Kudirkos)\s+)?{_WORD})\s+(?i:sen\b\.?|seniūnij\w*)\s*[:,]?",
    re.U,
)


_STREET = r"(?:g|skg|al|pl|tak|a)"
# House numbers: "8", "Nr. 105", "1, 1D", "4 ir 5", "11-17,17B ir 18", "41 iki 87 nelyginiai"
# is handled by aratc ("nuo ... iki").
_HOUSES = (
    r"(?:[Nn]r\.\s*)?\d+\s*[A-Za-z]?(?:\s*(?:[,;-]|ir)\s*(?:[Nn]r\.\s*)?\d+\s*[A-Za-z]?)*"
    r"(?:\s+(?:visi\s+)?(?:ne)?lygin\w*)?"
)
# The bracket of a village with some of its houses, once "tik"/"išskyrus" and the village's
# own name are taken off: "Nr. 5, 6, 11-17,17B ir 18", "4 ir 5", "nuo 1 iki 8", "Paparčio
# sodai", "Šilgalių sodai".
_SOME_OF_A_VILLAGE = re.compile(
    rf"{_HOUSES}|nuo\s+\d+\s*[A-Za-z]?\s+iki\s+\d+\s*[A-Za-z]?|[^,()]*\bsodai", re.I
)
# A street of the villages in its bracket, as the town's streets list it: "Panoramos g.
# (Liepynų k.)", "Panausupio g. (Marijampolės m. ir Triobiškių k.)", "Žalioji g.(Striūpų k.)".
_PLACE = rf"{_WORD}(?:\s+{_WORD})*\s+(?:k|m|mstl)\."
_STREET_OF = re.compile(
    rf"(?P<street>.+?\b{_STREET}\.)\s*\(\s*(?P<places>{_PLACE}(?:\s*,?\s*(?:ir\s+)?{_PLACE})*)\s*\)"
)


def _numbered(match: re.Match[str]) -> str:
    """ "Šakališkių (nuo 1-oji iki 18-oji) g." -> "Šakališkių 1-oji g., ..., Šakališkių 18-oji
    g."; "Tylioji 1, 3, 5, 7-oji g." -> "Tylioji 1-oji g., Tylioji 3-oji g., ..."."""
    name, groups = match["name"], match.groupdict()
    if groups.get("first"):
        numbers = range(int(groups["first"]), int(groups["last"]) + 1)
    else:
        numbers = [int(n) for n in re.findall(r"\d+", groups["numbers"])]
    return ", ".join(f"{name} {n}-oji g." for n in numbers)


# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], object], ...] = (
    # The part of a town in a bracket: "MARIJAMPOLĖS M. (Senamiestis):", "M.(Šakališkių sodai):".
    (re.compile(r"\b([Mm])\.\s*\([^()]*\)\s*:"), r"\1.:"),
    # A garden community in quotes with its streets: "„Atžalos sodai“ (Atžalos g., ...)".
    (re.compile(r"„[^“”\"]*[“”\"]\s*\(((?:[^()]|\([^()]*\))*)\)"), r"\1"),
    # Numbered streets of the gardens: "Šakališkių (nuo 1-oji iki 18-oji) g.", "Ramybės g. (nuo
    # 1-oji iki 8-oji) g.", "Tylioji 1, 3, 5, 7-oji g.".
    (
        re.compile(
            rf"(?P<name>{_WORD})\s+(?:g\.\s*)?\(\s*nuo\s+(?P<first>\d+)\s*-?\s*i?oji\s+iki\s+"
            rf"(?P<last>\d+)\s*-?\s*i?oji\s*\)\s*g\."
        ),
        _numbered,
    ),
    (
        re.compile(rf"(?P<name>{_WORD})\s+(?P<numbers>\d+(?:\s*,\s*\d+)+)\s*-\s*i?oji\s+g\."),
        _numbered,
    ),
    # "Kumelionių k. (įskaitant Vingio g., ...)": the whole village, these streets too.
    (re.compile(r"\s*\(\s*įskaitant\b(?:[^()]|\([^()]*\))*\)"), ""),
    # A street's houses after a comma: "Miško g., (1, 1A, 3)", "Gedimino g., 1-18,".
    (re.compile(rf"\b({_STREET})\.\s*,\s*(?=\()"), r"\1. "),
    (re.compile(rf"\b({_STREET})\.,\s*{_HOUSES}(?=\s*[,;.]|\s*$)"), r"\1. 0"),
    # Some houses of a street, as a house number tells aratc.Routes: one more choice for it.
    (re.compile(rf"\b({_STREET})\.\s*\(\s*(?:tik\s+)?{_HOUSES}\s*\)\.?"), r"\1. 0"),
    # "Ramybės g. ir Jurginų g.": two streets.
    (re.compile(rf"\b({_STREET})\.\s+ir\s+(?=[{_UPPER}])"), r"\1., "),
    # "Puskelnių k. SB.": the garden community of the village, whose addresses are its.
    (re.compile(r"\bk\.\s+SB\."), "k."),
    # "Bridžių VS.", "Maironio sk.".
    (re.compile(r"(?<=\w)\s+VS\.(?=\s|[,;:(]|$)"), " vs."),
    (re.compile(r"(?<=\w)\s+sk\.(?=\s*[,;)]|\s*$)"), " skg."),
    # A whole eldership: "visa Klausučių seniūnija", "visa Gražiškių sen. išskyrus Skardupių k.
    # (Pajevonio g. 1, ...)" (the houses left out are another route's), "Pilviškių
    # seniūnijos kaimai išskyrus Gabriškių k., ..." (the villages left out are other routes').
    (
        re.compile(
            rf"\bvis[ao]\s+({_WORD})\s+(?:sen\b\.?|seniūnij\w*)"
            rf"(?:\s+i[sš]+kyrus\s+(?:(?!\b{_WORD}\s+(?i:sen)\b)[^()])*(?:\([^()]*\))?)?"
        ),
        r"Visoje \1 sen.",
    ),
    (
        re.compile(
            rf"\b({_WORD})\s+seniūnijos\s+kaimai\b(?:\s+i[sš]+kyrus\b.*?)?"
            rf"(?=\s+{_WORD}\s+(?i:sen)\b|$)"
        ),
        r"Visoje \1 sen.",
    ),
)


class Routes(aratc.Routes):
    """Reads the places of one municipality's rows (its provider's), as aratc.Routes does:

        KAZLŲ RŪDOS M.: Alyvų g., Gedimino g., ...                     a town's streets
        MOKOLŲ SEN.: Kumelionių k. (įskaitant Vingio g., ...), ...      sections of elderships
        LIUDVINAVO SEN.: ... MARIJAMPOLĖS M.: Vygrių g., ...           and of a town
        Kidulių sen.: Aleksandravos k., ... Sudargo sen.: ...          (Ekonovus)
        Marijampolės m. (A. Civinsko g., ...) Triobiškių k. (...)      streets in brackets

    and also: the town named in another eldership's section ("MOKOLŲ SEN.: ... MARIJAMPOLĖS
    M.: Vytauto g."), the town's eldership without "miesto" ("VILKAVIŠKIO SEN.:"), a street of
    a village in the town's list ("Panoramos g. (Liepynų k.)"), and some houses of a village by
    number ("Balaikų k. (tik Balaikų k. 3)", "Limarkų k. (išskyrus 4 ir 5)"): one more choice
    for the village next to its route. A whole eldership ("visa Gižų seniūnija") is a fallback
    that doesn't keep the elderships' other rows from naming its villages.

    No town gets "no pickup" for a street no route names (build_locations): the files list the
    streets of private houses, and those of apartment buildings are in the shared containers'
    files, which aren't read, so nothing says a street has none. The app offers the town's
    routes instead."""

    eldership = _ELDERSHIP

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (self.municipality_of(provider),)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()
        self.some_houses: set[int] = set()  # villages of the row read for some houses only
        # Stops of the section being read: villages of one name without the bracket's streets.
        self.dropped: set[int] = set()

    @staticmethod
    def municipality_of(provider: Provider) -> Municipality:
        """The municipality whose rows the provider has: a subclass reads another region's
        (ecoservice.Routes)."""
        return BY_PROVIDER[provider.id]

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return text

    def prepare(self, areas: list[Area]) -> None:
        """The settlements the rows of each kind name, not as part of a whole eldership: a
        village a row puts in another eldership is still found there ("KETURVALAKIŲ SEN.:
        Antupių k.", of Gižų sen., which another row has whole)."""
        named: dict[str, set[int]] = defaultdict(set)
        for area in areas:
            named[area.kind] |= {s.code for s, c in self.clauses(area)[0] if not c.fallback}
        self.named = named

    def district(self, name: str) -> str | None:
        # "VILKAVIŠKIO SEN.: Vilkaviškio m. Gudelių g. 6B, 7": the town's eldership.
        return super().district(name) or super().district(f"{name} miesto")

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        found = super().settlements(name, numerals, kind, district)
        if not found and district and kind == "m":
            # A town in another eldership's section: the only town of that name.
            found = [s for s in super().settlements(name, None, kind, "") if s.abbr == "m."]
        key = fold(name)
        if found and district and not numerals and self.named is not None:
            # Rather than a name one letter off in the section's eldership ("Putriškių k." in
            # Liudvinavo sen., which has Petriškiai), the only settlement of exactly that name
            # in another (Putriškiai, Patašinės sen.), if no row of the kind names it in its own.
            if all(key not in (fold(s.name), fold(s.genitive)) for s in found):
                exact = [
                    s
                    for s in self.places[self.municipality.label]
                    if key in (fold(s.name), fold(s.genitive))
                ]
                if len(exact) == 1 and exact[0].code not in self.named[self.kind]:
                    found = exact
        return found

    def section(self, district: str, text: str) -> list[_Stop]:
        """aratc.Routes' section, with the streets of villages in a town's list read on their
        own: "Panoramos g. (Liepynų k.)" is Liepynai's, "Panausupio g. (Marijampolės m. ir
        Triobiškių k.)" the town's and Triobiškiai's."""
        kept: list[str] = []
        stops: list[_Stop] = []
        for part in _section_parts(text):
            match = _STREET_OF.fullmatch(part)
            if not match:
                kept.append(part)
                continue
            street = match["street"]
            for name, abbr in re.findall(
                rf"({_WORD}(?:\s+{_WORD})*)\s+(k|m|mstl)\.", match["places"]
            ):
                found = self.settlements(name, None, abbr, "")
                if any(s.abbr == "m." for s in found):
                    kept.append(street)
                    continue
                # Of villages of one name, those that have the street.
                streets = {s.code: self.streets(s, street, street, "g") for s in found}
                for settlement in found:
                    if streets[settlement.code]:
                        stops.append(_Stop(settlement, set(streets[settlement.code])))
                if not any(streets.values()):
                    self.unknown.append(f"{name} {abbr}.: {street[:60]}")
        self.dropped = set()
        found = super().section(district, ", ".join(kept))
        return [stop for stop in found if id(stop) not in self.dropped] + stops

    def spec(self, stops: list[_Stop], spec: str) -> None:
        """A bracket after a village's name; of some of its houses by number, the village is
        one more choice ("tik"), or the route's still ("išskyrus")."""
        text = spec.strip()
        excluding = bool(_EXCEPT.match(text))
        rest = _EXCEPT.sub("", text, count=1) if excluding else text
        rest = re.sub(r"^\s*tik\b", "", rest).strip()
        for stop in stops:
            # "(tik Balaikų k. 3)"
            rest = re.sub(rf"^{re.escape(stop.settlement.genitive)}\s+k\.?\s*", "", rest)
        if not _SOME_OF_A_VILLAGE.fullmatch(rest):
            if len(stops) > 1 and not excluding:
                # Of villages of one name, those that have the streets: Triobiškiai of Patašinės
                # sen., not of Liudvinavo sen., has "Triobiškių k. (Ajerų g., ...)".
                having = [
                    s
                    for s in stops
                    if any(typed_streets(p, s.settlement) for p in _section_parts(rest))
                ]
                if having and len(having) < len(stops):
                    self.dropped |= {id(s) for s in stops if s not in having}
                    stops = having
            super().spec(stops, spec)
            return
        if excluding:
            return
        # "(tik Paparčio sodai)": the gardens' streets, "Paparčio g.", "Paparčio 1-oji g.", ...
        garden = re.fullmatch(r"(.+?)\s+sodai", rest)
        for stop in stops:
            keys = {
                street_key(t)
                for t in stop.settlement.streets
                if garden and f"{fold(t.name)} ".startswith(f"{fold(garden[1])} ")
            }
            if keys:
                stop.add(keys, houses=False)
            else:
                stop.streets = stop.streets or set()
                self.some_houses.add(stop.settlement.code)

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.some_houses = set()
        found, skipped = super().clauses(area)
        for settlement, clause in found:
            if settlement.code in self.some_houses and clause.streets == set():
                clause.extra = True
        return found, skipped


def _provider(
    id: str, page: str, elderships: set[str], aliases: tuple[tuple[str, str], ...] = ()
) -> Provider:
    return Provider(
        id=id,
        name=COMPANY,
        url=f"{PAGES}{page}/",
        elderships=frozenset(elderships),
        aliases=aliases,
        kinds=("household", "food", "packaging", "glass"),
        reader=Routes,
    )


# Mixed waste, packaging and glass in one file of Ecoservice.
ALL_IN_ONE: dict[Kind, tuple[Kind, ...]] = {"household": ("household", "packaging", "glass")}

MARIJAMPOLE = Municipality(
    _provider(
        "marijampole",
        "marijampoles-sav",
        {"Igliaukos", "Liudvinavo", "Marijampolės miesto", "Mokolų", "Patašinės", "Sasnavos"},
        aliases=(
            (", Butlerienės skg.", ", P. Butlerienės skg."),
            # The register has no railway station settlement: the village of the name.
            ("Vinčų glž. st.", "Vinčų k."),
        ),
    ),
    snapshot.MARIJAMPOLE_MUNICIPALITY,
    snapshot.MARIJAMPOLE_REGISTRY_FILE,
    snapshot.MARIJAMPOLE_ADDRESSES_FILE,
    # 2026: 32 routes, each with mixed waste, packaging and glass dates, and 8 food waste
    # routes (Marijampolė and three villages by it), which gave a mixed waste schedule to 269
    # of the 279 settlements.
    min_areas={"household": 24, "food": 6, "packaging": 24, "glass": 24},
    min_household_places=220,
    # About 21,800 addresses in 2026.
    min_address_points=15_000,
    label="Marijampolės sav.",
    file_kinds=ALL_IN_ONE,
)
VILKAVISKIS = Municipality(
    _provider(
        "vilkaviskis",
        "vilkaviskio-raj-sav",
        {
            "Bartninkų",
            "Gižų",
            "Gražiškių",
            "Keturvalakių",
            "Klausučių",
            "Kybartų",
            "Pajevonio",
            "Pilviškių",
            "Vilkaviškio miesto",
            "Virbalio",
            "Vištyčio",
            "Šeimenos",
        },
        # Typos too far from the register's names to be taken for them.
        aliases=(("PAVEJONIO SEN.", "PAJEVONIO SEN."), ("PAVEVONIO SEN.", "PAJEVONIO SEN.")),
    ),
    snapshot.VILKAVISKIS_MUNICIPALITY,
    snapshot.VILKAVISKIS_REGISTRY_FILE,
    snapshot.VILKAVISKIS_ADDRESSES_FILE,
    # 2026: 29 mixed waste routes, 18 packaging and glass routes (their own file) and 6 food
    # waste routes (Vilkaviškis, Kybartai and three villages), which gave a mixed waste
    # schedule to 357 of the 360 settlements.
    min_areas={"household": 22, "food": 4, "packaging": 14, "glass": 14},
    min_household_places=300,
    # About 17,600 addresses in 2026.
    min_address_points=12_000,
    label="Vilkaviškio r.",
)
KALVARIJA = Municipality(
    _provider(
        "kalvarija",
        "kalvarijos-sav",
        {"Akmenynų", "Kalvarijos", "Liubavo", "Sangrūdos"},
        aliases=(("Skersabalių II k.", "Skersabalių k."),),  # the register has one
    ),
    snapshot.KALVARIJA_MUNICIPALITY,
    snapshot.KALVARIJA_REGISTRY_FILE,
    snapshot.KALVARIJA_ADDRESSES_FILE,
    # 2026: 11 routes with mixed waste, packaging and glass and 2 food waste routes
    # (Kalvarija and Santaka), which gave a mixed waste schedule to 133 of the 160 settlements.
    min_areas={"household": 8, "food": 1, "packaging": 8, "glass": 8},
    min_household_places=110,
    # About 6,000 addresses in 2026.
    min_address_points=4_000,
    label="Kalvarijos sav.",
    file_kinds=ALL_IN_ONE,
)
KAZLU_RUDA = Municipality(
    _provider("kazluruda", "kazlu-rudos-sav", {"Antanavo", "Jankų", "Kazlų Rūdos", "Plutiškių"}),
    snapshot.KAZLU_RUDA_MUNICIPALITY,
    snapshot.KAZLU_RUDA_REGISTRY_FILE,
    snapshot.KAZLU_RUDA_ADDRESSES_FILE,
    # 2026: 13 routes with mixed waste, packaging and glass and 2 food waste routes (the
    # town), which gave a mixed waste schedule to 145 of the 183 settlements.
    min_areas={"household": 10, "food": 1, "packaging": 10, "glass": 10},
    min_household_places=120,
    # About 4,700 addresses in 2026.
    min_address_points=3_000,
    label="Kazlų Rūdos sav.",
    file_kinds=ALL_IN_ONE,
)
SAKIAI = Municipality(
    _provider(
        "sakiai",
        "sakiu-raj-sav",
        {
            "Barzdų",
            "Gelgaudiškio",
            "Griškabūdžio",
            "Kidulių",
            "Kriūkų",
            "Kudirkos Naumiesčio",
            "Lekėčių",
            "Lukšių",
            "Plokščių",
            "Sintautų",
            "Slavikų",
            "Sudargo",
            "Šakių",
            "Žvirgždaičių",
        },
        aliases=(
            ("J.Staugaučio g.", "J. Staugaičio g."),  # Justino Staugaičio g.
            ("Jotyškių II k.", "Jotyškių k."),  # Plokščių sen. has one
        ),
    ),
    snapshot.SAKIAI_MUNICIPALITY,
    snapshot.SAKIAI_REGISTRY_FILE,
    snapshot.SAKIAI_ADDRESSES_FILE,
    # 2026: 28 mixed waste routes (Ecoservice), 13 packaging, 16 glass and 2 food waste routes
    # (Ekonovus, a file each), which gave a mixed waste schedule to 459 of the 507
    # settlements.
    min_areas={"household": 21, "food": 1, "packaging": 10, "glass": 12},
    min_household_places=400,
    # About 13,700 addresses in 2026.
    min_address_points=9_000,
    label="Šakių r.",
    file_kinds={},
)
MUNICIPALITIES = (MARIJAMPOLE, VILKAVISKIS, KALVARIJA, KAZLU_RUDA, SAKIAI)
BY_PROVIDER = {m.provider.id: m for m in MUNICIPALITIES}


# --- the page ----------------------------------------------------------------


class _Links(HTMLParser):
    """The page's links with their texts."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.href, self.text = dict(attrs).get("href") or "", []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            self.links.append((self.href, clean_text("".join(self.text))))
            self.href = None

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)


# Files that aren't the schedules of individual houses, by their texts (folded): shared
# containers and their washing, businesses, cemeteries, rest areas, bulky waste.
OTHERS = (
    "bendro naudojimo",
    "bendrojo naudojimo",
    "plovimo",
    "juridin",
    "kapiniu",
    "poilsiaviec",
    "gabarit",
    "daugiabuc",
)


def file_kind(text: str) -> Kind | None:
    """The kind of a file by its text: "... mišrių komunalinių atliekų, pakuočių ir antrinių
    žaliavų ..." is mixed waste (with packaging and glass inside), "... mišrių pakuočių ..."
    packaging, "... stiklo pakuočių ..." glass, "... maisto ..." food."""
    folded = fold(text)
    if "maist" in folded:
        return "food"
    if "komunalin" in folded:
        return "household"
    if "stikl" in folded:
        return "glass"
    if "pakuo" in folded or "antrin" in folded:
        return "packaging"
    return None


def find_files(html: str, page_url: str) -> list[SourceFile]:
    """The PDFs of individual houses the page links, by the texts of their buttons."""
    collector = _Links()
    collector.feed(html)
    files: list[SourceFile] = []
    for href, text in collector.links:
        url = urljoin(page_url, href)
        folded = fold(text)
        kind = file_kind(text)
        if not urlsplit(url).path.lower().endswith(".pdf") or kind is None:
            continue
        if "individual" not in folded or any(word in folded for word in OTHERS):
            continue
        if any(f.url == url for f in files):
            continue
        name = PurePosixPath(unquote(urlsplit(url).path)).name
        files.append(SourceFile(kind=kind, url=url, file_name=name))
    return files


def download(
    municipality: Municipality, today: date, keep_days: int
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    page = municipality.provider.url
    html = http.get(page, timeout=60).decode("utf-8", errors="replace")
    files, warnings = tratc.select_files(find_files(html, page), today)
    return [(f, http.get(f.url, timeout=60)) for f in files], warnings


# --- the tables ------------------------------------------------------------------

# The days of a month's cell: "5", "2, 30", "2; 16; 30", "08,22"; "-" or nothing: none.
_DAYS = re.compile(r"\d{1,2}(?:\s*[,;]\s*\d{1,2})*")
# Rows that aren't places: titles and notices (folded).
NOT_PLACES = re.compile(r"\bgrafik|\bprimename\b|\bisstumti\b|\bpastatyti\b")
# Routes of shared containers (folded), should a file of individual houses have one.
SHARED = re.compile(r"daugiabuc|bendro naudojimo|kolektyvin")
# The waste types of a file of each kind's title (folded), the first that matches.
TITLE_KINDS: tuple[tuple[str, Kind], ...] = (
    ("maist", "food"),
    ("komunalin", "household"),
    ("stikl", "glass"),
    ("pakuo", "packaging"),
)


@dataclass
class _Header:
    """A row of months: which column is which."""

    months: dict[int, date]  # column -> the month's first day
    width: int  # the table's columns
    places: int | None  # the column of the places ("Maršrutas"); None: rows of their own above
    skip: frozenset[int]  # columns not read ("Grafikas": how often, and the route's number)


def _cell(value: str | None) -> str:
    """A cell's lines in one: "Meškučių 11-" + "oji g." is "Meškučių 11-oji g."."""
    return clean_text(re.sub(r"(?<=\w)-\n(?=\w)", "-", value or ""))


def _header(cells: list[str], year: int, where: str) -> _Header | None:
    found = {i: aratc.MONTHS[fold(c)] for i, c in enumerate(cells) if fold(c) in aratc.MONTHS}
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
    titles = {fold(c): i for i, c in enumerate(cells[: columns[0]]) if c}
    if set(titles) - {"grafikas", "marsrutas"}:
        raise ValueError(f"{where}: columns {sorted(titles)} before the months")
    places = titles.get("marsrutas")
    if titles and places is None:
        raise ValueError(f"{where}: no column of places")
    skip = frozenset(i for title, i in titles.items() if title != "marsrutas")
    return _Header(months, len(cells), places, skip)


def _upright(obj: dict) -> bool:
    """Not the letters of the elderships written bottom to top: their baseline is vertical
    (pdfplumber's `upright` is true for them in the files Excel saves itself)."""
    if obj.get("object_type") != "char":
        return True
    a, b = obj["matrix"][:2]
    return abs(a) >= abs(b)


def _days(text: str, where: str) -> list[int]:
    if text in ("", "-", "–"):
        return []
    if not _DAYS.fullmatch(text):
        raise ValueError(f"{where}: not days: {text!r}")
    return [int(day) for day in re.findall(r"\d+", text)]


def _title(text: str) -> tuple[str, int | None]:
    """The file's title, folded, and its year: "... APTARNAVIMO GRAFIKAS 2026 METAMS", "...
    SURINKIMO IŠ INDIVIDUALIŲ KONTEINERIŲ GRAFIKAS 2026 M."."""
    folded = fold(text)
    match = re.search(r"\bgrafik\w*\s+(20\d{2})\s+(?:m|metams|metu)\b", folded)
    if not match:
        return "", None
    # Not Ekonovus' contacts above it ("Informacija tel.: ... ekonovus.lt").
    title = re.sub(r"^.*?\bekonovus lt\b", "", folded[: match.end()])
    return title, int(match.group(1))


@dataclass
class _Route:
    """A row of places and the days of each set of waste types collected on them."""

    places: str
    where: str
    dates: list[tuple[frozenset[Kind], set[date]]] = field(default_factory=list)


def _routes(source: SourceFile, content: bytes) -> list[_Route]:
    """The routes of a file. Strict: a cell of a month that isn't days, a day the month doesn't
    have, dates of no waste type or without places, places without dates and a file without a
    table raise ValueError."""
    routes: list[_Route] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        first = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        title, year = _title(first)
        if year is None:
            raise ValueError(f"{source.file_name}: no title with a year")
        expected = tratc.file_year(source.file_name)
        if expected and year != expected:
            raise ValueError(f"{source.file_name}: the title says {year}, the file name {expected}")
        # The waste type of a file whose rows don't name it (Ekonovus): the title's, which must
        # be the one its button on the page says.
        kind = next((kind for word, kind in TITLE_KINDS if word in title), None)
        if kind != source.kind:
            raise ValueError(f"{source.file_name}: a {kind} schedule, its link says {source.kind}")
        header: _Header | None = None
        current: _Route | None = None  # the route whose days are being read (Ecoservice)
        pending: list[str] = []  # rows of places, until the months under them (Ecoservice)
        for page in pdf.pages:
            where = f"{source.file_name} page {page.page_number}"
            for table in page.filter(_upright).extract_tables():
                for row in table:
                    cells = [_cell(c) for c in row]
                    text = " ".join(c for c in cells if c)
                    if not text:
                        continue
                    new = _header(cells, year, where)
                    if new:
                        header, current = new, None
                        if header.places is None:
                            if not pending:
                                raise ValueError(f"{where}: months without places above them")
                            current = _Route(" ".join(pending), where)
                            routes.append(current)
                        elif pending:
                            raise ValueError(f"{where}: places without dates: {pending[0][:80]!r}")
                        pending = []
                        continue
                    if NOT_PLACES.search(fold(text)):
                        continue
                    filled = [c for c in cells if c]
                    # A row of places across the table (Ecoservice): one cell, in whichever
                    # column it starts (Vilkaviškio r. mixed waste: that of January).
                    if header is None or (len(filled) == 1 and not _DAYS.fullmatch(filled[0])):
                        if header and header.places is not None:
                            raise ValueError(f"{where}: places without dates: {text[:80]!r}")
                        pending.append(text)
                        continue
                    if len(cells) != header.width:
                        raise ValueError(
                            f"{where}: a row of {len(cells)} columns under {header.width}"
                        )
                    dates: set[date] = set()
                    for i, month in header.months.items():
                        for day in _days(cells[i], where):
                            try:
                                dates.add(month.replace(day=day))
                            except ValueError as error:
                                raise ValueError(
                                    f"{where}: day {day} of {month:%Y-%m}: {error}"
                                ) from error
                    if header.places is not None:
                        places = cells[header.places]
                        if not places:
                            raise ValueError(f"{where}: dates without places")
                        routes.append(_Route(places, where, [(frozenset({source.kind}), dates)]))
                        continue
                    if pending or current is None:
                        raise ValueError(f"{where}: dates without places ({text[:60]!r})")
                    label = " ".join(c for i, c in enumerate(cells) if c and i not in header.months)
                    # Without a label (Vilkaviškio r. mixed waste), the title's waste type.
                    kinds = frozenset(aratc._kinds(label) if label else {source.kind})
                    if not kinds:
                        raise ValueError(f"{where}: dates of no waste type ({label[:60]!r})")
                    current.dates.append((kinds, dates))
        if pending:
            raise ValueError(f"{source.file_name}: places without dates: {pending[0][:80]!r}")
    if not routes:
        raise ValueError(f"{source.file_name}: no schedule table found")
    return routes


def parse_file(
    source: SourceFile, content: bytes, municipality: Municipality = MARIJAMPOLE
) -> ParseResult:
    """The schedules of a file's routes: one per waste type of a route. A file has only the
    waste types `Municipality.file_kinds` gives its kind (the mixed waste file of Marijampolės,
    Kalvarijos and Kazlų Rūdos sav. has packaging and glass too), or it raises ValueError."""
    allowed = municipality.file_kinds.get(source.kind, (source.kind,))
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for route in _routes(source, content):
        name = route.places
        if SHARED.search(fold(name)):
            warnings.append(f"{route.where}: shared containers, not read: {name[:60]!r}")
            continue
        by_kind: dict[Kind, set[date]] = defaultdict(set)
        for kinds, dates in route.dates:
            for kind in kinds:
                by_kind[kind] |= dates
        if not any(by_kind.values()):
            raise ValueError(f"{route.where}: places without dates: {name[:80]!r}")
        for kind, dates in sorted(by_kind.items()):
            if kind not in allowed:
                raise ValueError(f"{route.where}: {kind} dates in a {source.kind} file")
            if not dates:
                continue
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


def source(municipality: Municipality) -> build.Source:
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
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    parser.add_argument(
        "--published",
        default=PUBLISHED_URL,
        help="site folder with yesterday's schedule.json, for a municipality whose build fails",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any municipality's build fails instead of keeping its published part",
    )
    args = parser.parse_args(argv)

    loader = None if args.strict else cache(build.load_published(args.published))
    results: list[build.PartResult] = []
    registries: list[tuple[Municipality, Registry]] = []
    points: list[address_points.AddressPoint] = []
    notes: list[str] = []
    down: set[str] = set()  # live sources that failed
    try:
        for municipality in MUNICIPALITIES:
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
        dataset = build.merge_parts([(r.provider, r.part) for r in results if r.part], PAGES)
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

    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
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
    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
        part = r.part or {"locations": [], "areas": []}
        title, file_name = f"{municipality.label} (MAATC)", f"{args.out.name}/schedule.json"
        build.write_summary(part, [r], [], title, f"{municipality.label} in {file_name}")
    build.write_summary(dataset, [], notes, "MAATC", f"{args.out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

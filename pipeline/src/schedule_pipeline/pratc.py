"""Panevėžio regionas: the schedules of the regional waste centre of Panevėžys county, UAB
„Panevėžio regiono atliekų tvarkymo centras“ (PRATC), for the individual houses of Pasvalio r.,
Rokiškio r., Biržų r. and Panevėžio r. Panevėžys city isn't read.

Its page has a section per municipality ("Pasvalio r. atliekų išvežimo grafikai"), a list item
per file that says what the file is ("Pakuočių (individualių valdų) konteinerių aptarnavimo
grafikas"); the link's own text is mostly just "grafikas". The files of individual houses are
found by these texts. Those of shared containers ("bendro naudojimo"), businesses, textiles,
bulky waste, cemeteries and container washing aren't read, nor a link without text (an old file
still linked, but not shown on the page), nor Panevėžio r.'s food waste. Panevėžio r.'s mixed
waste schedule is a Word document (.doc), a table of routes with notes in free words, which
pratc_word.py reads with the help of a transcription of its notes; when it can't be read, its
rows of yesterday's data are kept (parse_file). The year of a file is in its address ("2026
grafikai/") or, failing that, in its titles.

The spreadsheets come in three layouts:

    Grafikas | Maršrutas                                   | Sausis | Vasaris | ...
    M01 5783 | Pasvalio apylinkių sen.: Brazdigala, ...      | 8      | 5       | ...

  read by tratc.parse_sheet, as the files of Telšių RATC: Pasvalio r. (every kind), Rokiškio r.
  (packaging and glass; food), Panevėžio r. (packaging; glass) and Biržų r. (food). A file with
  several sheets has one per waste type, which the title above its table names ("... STIKLO
  PAKUOČIŲ ATLIEKŲ SURINKIMO ... GRAFIKAS 2026 M.").

    Nr. | Maršrutas (vietovė)              | 2026 m.
        |                                  | Sausis                      | Vasaris | ...
    5   | Degenių k., Rumpiškėnų, ...      | Pirmą mėnesio ketvirtadienį
        |                                  | 1                           | 5       | ...

  Rokiškio r. mixed waste (parse_rules): a rule for each route, then a row of its days.

    Gatvės/Kaimo pavadinimas   | Buitinių atliekų grafikas | Pakuočių ... | Stiklo grafikas
    Beržiniai, Diemedžiai, ... | Sausis  | 7               | Sausis | 7   | Sausis |
                               | Vasaris | 4               | Vasaris | 4  | Vasaris | 4
                               | ... twelve months

  Biržų r. mixed waste, packaging and glass (parse_blocks): a block of twelve rows per place, as
  in the PDFs of Šiaulių RATC (sratc).

Shared containers ("BENDRO NAUDOJIMO KONTEINERIAI", "Bendro naudojimo:", "kolektyvinio
naudojimo", "daugiabučiai namai") aren't read: their rows are left out, and of a cell that lists
the individual and the shared containers of one route only the individual ones are read.

The places are lists of settlements and streets, in sections of elderships ("Pasvalio apylinkių
sen.: Diliauskų k., ...") or not ("Beržiniai, Diemedžiai, ...", "Miliūnų-Miegonių-Iciūnų
kaimai"), which Places links to the Address Register. Next year's files are read as soon as
they are linked: a route of next year that covers the same places as one of this year continues
it (combine).

The four municipalities are written to one <out>/schedule.json and <out>/addresses.json, a part
(model.Provider) each, as the four of Telšių RATC: a municipality whose build fails keeps its
part of yesterday's file.
Run: python -m schedule_pipeline.pratc --out ../site/panevezio-ratc
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import cache, partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import openpyxl

from . import addresses as address_points
from . import build, http, pratc_word, snapshot, worddoc
from . import registry as address_register
from .dates import WEEKDAY_NAMES, parse_month, parse_weekdays
from .locations import (
    _HOUSE,
    _NUMERALS,
    _STREET_TYPES,
    _UPPER,
    _WORD,
    Clause,
    Index,
    SectionRoutes,
    _near,
    _one_off,
    _section_parts,
    _Stop,
    _street_type,
    _typo,
    street_key,
    typed_streets,
)
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Registry, Settlement, fold
from .sratc import _Block, _close, _days, _month
from .tratc import _month_row, _once, _visible_rows, parse_days, parse_sheet

PAGE_URL = "https://www.pratc.lt/atlieku-isvezimas-atlieku-isvezimas/"
# Yesterday's data, for the part of a municipality whose build fails today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/panevezio-ratc"
COMPANY = "UAB „Panevėžio regiono atliekų tvarkymo centras“"


# --- the places --------------------------------------------------------------------------

_SETTLEMENT_TYPES = {"k": "k.", "vs": "vs.", "mstl": "mstl.", "m": "m.", "glžst": "glž. st."}
# A settlement or a street with its type, and house numbers: "Pagojo II k.", "Pušaloto vs.",
# "Panemunėlio glžst." (the railway station, normalised), "Rūtų sk.", "Ventos g. 2, 2A".
_ITEM = re.compile(
    rf"(?P<name>.+?)(?:\s+(?P<numerals>{_NUMERALS}))?"
    r"(?:\s+(?P<type>k|vs|mstl|m|glžst|g|al|pl|skg|sk|aklg|tak|takas|a)\b\.?)?"
    r"(?:\s*(?P<houses>\d+\s*[A-Za-z]?(?:\s*[,;]\s*\d+\s*[A-Za-z]?)*))?",
    re.U,
)
# An eldership before its part of a list ("Pasvalio apylinkių sen.:", "Rokiškio kaimiškoji
# sen.:", "Vaškų sen.,"), or after a settlement it tells apart ("Pagojų k. Kazliškio sen.").
_MARK = re.compile(
    rf"\b({_WORD}(?:\s+(?:{_WORD}|apylinkių|kaimiškoji|miesto))?)\s+sen\b\.?\s*([:,]?)", re.U
)
# "(Papilio sen.)" after a settlement: of that eldership.
_HINT = re.compile(r"(.+?)\s+sen\b\.?", re.U)
# Parts of a list that are shared containers of apartment buildings.
_SHARED_PART = re.compile(r"daugiabu|bendro naudojimo|kolektyvin")
# The publisher's spellings, as Places reads them.
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bkaima[si]\b", re.I), "k."),
    (re.compile(r"\bmiestelis\b", re.I), "mstl."),
    (re.compile(r"\bmiestas\b", re.I), "m."),
    (re.compile(r"\b(?:vnk|vienk)\.", re.I), "vs."),
    # Panemunėlis' railway station: "Panemunėlio glž. st.", "g.st.", "g.s".
    (re.compile(r"\b(?:glž\.?\s*st|g\.\s*st|g\.\s*s)\b\.?", re.I), "glžst."),
    # "(tik Beržytės g., ...)": only; "(be ...)": but.
    (re.compile(r"\(\s*tik\s+", re.I), "("),
    (re.compile(r"\(\s*be\s+", re.I), "(išskyrus "),
    (re.compile(r"\(\s+"), "("),
    (re.compile(r"\s+\)"), ")"),
    # "...-Gudelių kaimai - // -Bučiūnų-...": the line went on.
    (re.compile(r"\s*-?\s*//\s*-?\s*"), ", "),
    # A type without its dot: "Mitrišiūnų k,", "Ajerų skg,"; "Jokūbaičių k. I".
    (re.compile(r"\b(k|vs|mstl|m|g|skg|sk|aklg|tak|al)(?=\s*[,;]|\s*$)"), r"\1."),
    (re.compile(r"\b(k|vs|mstl|m)\.\s+(I{1,3})(?=\s*[(,;]|\s*$)"), r"\2 \1."),
)
# A full stop between two places, outside brackets: "Ubiškiai. Astravo sodai: ...", "Varlynė.
# Pumpėnų sen.:"; not after a type ("Pušaloto mstl. Pumpėnų ...") nor in "(nuo Respubl. G. iki
# ...)".
_FULL_STOP = re.compile(
    rf"(?<=[^\W\d_]{{3}})(?<!mstl)(?<!aklg)(?<!skg)(?<!tak)(?<!sen)\.\s+(?=[{_UPPER}])"
)
# "Sinagogų-Mikėno-...-Pirties gatvės": streets of the municipality's town.
_STREETS_RUN = re.compile(r"(?:^|(?<=[,;]))(?P<run>[^,;]*?)\s+gatvės\b", re.I)
_TYPED = re.compile(r"\s(?:g|skg|sk|aklg|tak|takas|al|a)\.$")
# "Rinkuškių sodai:", "Astravo sodai:": the streets of gardens.
_GARDENS = re.compile(rf"\b({_WORD})\s+sodai\s*:", re.U)
_NO_TOWN = Settlement(code=0, name="", genitive="", abbr="m.", district="\0")


def _outside(pattern: re.Pattern[str], replacement: str, text: str) -> str:
    """`pattern.sub(replacement, ...)` on the parts of `text` outside brackets."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "(" and depth == 0:
            parts += [pattern.sub(replacement, text[start:i])]
            start = i
        elif ch == ")" and depth == 1:
            parts += [text[start : i + 1]]
            start = i + 1
        depth = max(0, depth + (ch == "(") - (ch == ")"))
    rest = text[start:]
    return "".join([*parts, rest if depth else pattern.sub(replacement, rest)])


def _dashes(text: str) -> list[str]:
    """Splits a text at the hyphens outside brackets."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        depth += (ch == "(") - (ch == ")")
        if ch == "-" and depth <= 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


class Places(SectionRoutes):
    """Reads one row of the centre's schedules: settlements and streets of one municipality,

        Pasvalio apylinkių sen.: Diliauskų k., ... Pasvalio miesto sen.: Pasvalio m. - Atžalyno g.
        Pumpėnų sen.: Aukštagojis, Auriliškiai, ... Pasvalio miesto sen., Pasvalys: Ajerų g., ...
        Krekenavos sen.: Krekenavos mstl. (išskyrus Beržytės g., ...), Krekenavos vs.
        Rokiškio miesto sen.: Rokiškio m. (Alyvų g., Aušros g., ...)
        Papilys, Valkiškiai, ..., Parovėja (Papilio sen.)
        Varniūnai, ... Astravo sodai: Aviečių g., ... Biržų miestas: Astravo g., Tiškevičių g.
        Kazliškis-Pagojų k. Kazliškio sen., Stramilių k., Rokiškio kaimiškoji sen.
        Miliūnų-Miegonių-Lauciūnų-Vyžūnos-Sodelių-Iciūnų kaimai
        Sinagogų-Mikėno-...-Jūžintų (už geležinkelio) gatvės, Parokiškės k., ...

    A list with an eldership before its part ("X sen.:") is read in sections: a settlement is
    looked up in its section's eldership (or elsewhere in the municipality, if it's the only
    one of that name and no row of its kind names it in its own). A list without is read in the
    whole municipality: an eldership after a settlement ("Pagojų k. Kazliškio sen.", "Parovėja
    (Papilio sen.)") tells which, and of settlements of one name in several elderships the one
    in the eldership of most of the list, or around its town, is meant (which); if none is, the
    name is reported and not read, rather than given to a village far away. Hyphens
    between names are commas, but in a name of the register ("G. Petkevičaitės-Bitės g.");
    "...-Ramybės gatvės" are streets of the municipality's town. Streets after a settlement are
    its streets: those of a route, with "išskyrus" those it leaves out, and with house numbers
    one more choice for that street. A street several routes name, each a part of it ("Aušros
    g (nuo Respubl. G. iki Ąžuolų g.)"), has each of them for a choice.

    No town or village gets "no pickup" for a street no route names: the routes leave out
    streets of private houses (new ones, and some whose files list them only under shared
    containers), and nothing says those have no pickup. The app offers the place's routes.
    """

    # build_locations: no settlement's unnamed streets are "no pickup".
    towns_by_street: set[int] = set()

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.unknown: list[str] = []
        self.named: dict[str, set[int]] | None = None
        self.kind = ""
        self.town = _NO_TOWN
        self.common: list[str] = []
        self.municipality = BY_ID[provider.id]
        mine = [s for s in index.registry.settlements if s.district in provider.elderships]
        self.forms: dict[str, list[tuple[Settlement, tuple[str, str]]]] = defaultdict(list)
        for s in mine:
            forms = (fold(s.name), fold(s.genitive))
            self.forms[""].append((s, forms))
            self.forms[s.district].append((s, forms))
        # The towns of the "<town> miesto" elderships, whose sections name the town's streets.
        self.towns = {
            s.district: s for s in mine if s.abbr == "m." and fold(s.district).endswith("miesto")
        }
        self.main_town = next(
            (s for s in mine if s.abbr == "m." and s.name == self.municipality.town), None
        )
        # Pairs of words joined by a hyphen in a name of the register ("Petkevičaitės-Bitės").
        self.joined = {
            (fold(left.split()[-1]), fold(right.split()[0]))
            for s in mine
            for name in (s.name, *(t.name for t in s.streets))
            for left, right in zip(name.split("-"), name.split("-")[1:], strict=False)
            if left.strip() and right.strip()
        }

    # -- the text --------------------------------------------------------------------

    def normalize(self, text: str) -> str:
        text = clean_text(text)
        for written, registered in self.provider.aliases:
            text = text.replace(written, registered)
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        text = _outside(_FULL_STOP, ", ", text)
        text = self.street_runs(text)
        text = self.split_dashes(text)
        return clean_text(self.gardens(text))

    def street_runs(self, text: str) -> str:
        """ "Sinagogų-Mikėno-...-Pirties gatvės" -> "Rokiškio m., Sinagogų g., Mikėno g., ...".
        A street named with its part ("Aušros g (nuo Respubl. G. iki Ąžuolų g.)", "Jūžintų (už
        geležinkelio)") is the street: the routes that name it are its choices."""
        town = self.main_town
        if town is None:
            return text

        def streets(match: re.Match[str]) -> str:
            pieces = []
            for piece in _dashes(match["run"]):
                piece = re.sub(r"\s*\([^()]*\)", "", piece).strip()
                piece = re.sub(r"\s(g|skg|sk|aklg|tak|al|a)$", r" \1.", piece)
                if not _TYPED.search(piece):
                    piece += " g."
                pieces.append(piece)
            return f"{town.genitive} m., " + ", ".join(pieces)

        return _STREETS_RUN.sub(streets, text)

    def split_dashes(self, text: str) -> str:
        """Hyphens between names are commas: "Miliūnų-Miegonių", "Pandėlio m.-Stanikūnų",
        "Pasvalio m. - Atžalyno g."; not in a name of the register."""

        def comma(match: re.Match[str]) -> str:
            pair = (fold(match[1]), fold(match[2]))
            return match[0] if pair in self.joined else f"{match[1]}, "

        return re.sub(r"([^\W\d_]+\.?)\s*-\s*(?=([^\W\d_]+))", comma, text)

    def gardens(self, text: str) -> str:
        """The streets of garden communities ("Rinkuškių sodai: Rožių aklg., ...", "Liepų
        sodai: Rožių takas, ...") as streets of the settlements the register puts them in:
        "Rinkuškių k. (Rožių aklg., ...)", "Biržų m. (Rožių takas, ...), Ruoliškio k. (Samanų
        tak., ...)". A garden's list ends at the next one, or the next town or village before a
        colon ("Biržų miestas: Astravo g., ...")."""
        result, done = [], 0
        for match in _GARDENS.finditer(text):
            if match.start() < done:
                continue
            rest = text[match.end() :]
            end = len(rest)
            if ":" in rest:
                colon = rest.index(":")
                comma = rest.rfind(",", 0, colon)
                end = comma if comma >= 0 else colon
            result += [text[done : match.start()], self.garden(match[1], rest[:end])]
            done = match.end() + end
        return "".join([*result, text[done:]])

    def garden(self, name: str, text: str) -> str:
        """A garden's streets in brackets after the settlements that have them: a village of the
        garden's name, the municipality's town or, failing them, the only other settlement that
        has a street of that name and type. Streets of none go to the first, which reports
        them."""
        villages = [
            s
            for s in self.index.by_name.get(fold(name), [])
            if s.district in self.provider.elderships
        ]
        first = [*villages, *([self.main_town] if self.main_town else [])]
        owners: dict[int, tuple[Settlement, list[str]]] = {}
        unknown: list[str] = []
        for part in _section_parts(text):
            match = _ITEM.fullmatch(part)
            owner = None
            if match and match["type"] and match["type"] not in _SETTLEMENT_TYPES:
                owner = next((s for s in first if self.typed(part, match["type"], s)), None)
                if owner is None:
                    others = [s for s, _ in self.forms[""] if self.typed(part, match["type"], s)]
                    owner = others[0] if len(others) == 1 else None
            if owner is None:
                unknown.append(part)
            else:
                owners.setdefault(owner.code, (owner, []))[1].append(part)
        if unknown:
            home = next((s for s, _ in owners.values()), first[0] if first else None)
            if home is None:
                return f"{name} sodai: {text}"
            owners.setdefault(home.code, (home, []))[1].extend(unknown)
        return "".join(f"{s.genitive} {s.abbr} ({', '.join(p)}), " for s, p in owners.values())

    @staticmethod
    def typed(part: str, kind: str, settlement: Settlement) -> set[str]:
        """The streets of `settlement` a part names with their type: "Karklų g.", not Karklų
        tak."""
        wanted = _STREET_TYPES.get(fold(kind), fold(kind))
        found = typed_streets(part, settlement)
        return {
            street_key(t)
            for t in settlement.streets
            if street_key(t) in found and _street_type(t) == wanted
        }

    def district(self, name: str) -> str | None:
        """The eldership of the municipality a list names: "Pasvalio apylinkių", "Vaškų"."""
        key = fold(name)
        exact = [d for d in self.provider.elderships if fold(d) == key]
        if exact:
            return exact[0]
        found = self.index.district(name)
        return found if found in self.provider.elderships else None

    def marks(self, text: str) -> list[tuple[int, int, str, str]]:
        """(start, end, eldership, ":" or "," or "") of the elderships a list names, but in
        brackets."""
        found = []
        for match in _MARK.finditer(text):
            if text[: match.start()].count("(") > text[: match.start()].count(")"):
                continue
            name, start = match[1], match.start(1)
            district = self.district(name)
            if district is None and " " in name:
                # Of two words, an eldership's name may be only the second.
                rest = name.split(maxsplit=1)[1]
                district, start = self.district(rest), start + name.index(rest)
            if district:
                found.append((start, match.end(), district, match[2]))
        return found

    # -- the settlements -------------------------------------------------------------

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        """Settlements of one name (or a near one) in the eldership, or without one in the
        municipality."""
        names = [f"{name} {n}" for n in re.findall(r"I{1,3}", numerals)] if numerals else [name]
        forms = self.forms[district]
        codes = {s.code for s, _ in forms}
        hits: list[Settlement] = []
        for one in names:
            key = fold(one)
            found = [s for s in self.index.by_name.get(key, []) if s.code in codes]
            if not found and numerals and one.endswith(" I"):
                # "Balnių I ir II k.": the register calls the first one Balniai.
                found = [s for s in self.index.by_name.get(fold(one[:-2]), []) if s.code in codes]
            if not found and not numerals:
                # "Akmena" for Akmena I and II.
                pattern = re.compile(re.escape(key) + r" i{1,3}")
                found = [s for s, f in forms if any(pattern.fullmatch(x) for x in f)]
            for close in (_near, _one_off, _typo):
                if not found:
                    # Another ending or a typo ("Rumpiškėnų", "Keleežerių"), if only one name
                    # is that close.
                    near = [s for s, f in forms if close(key, f[0]) or close(key, f[1])]
                    found = near if len({s.name for s in near}) == 1 else []
            if not found and district and self.named is not None:
                # In another eldership: the only one of that name, if no row of the kind names
                # it in its own.
                elsewhere = [
                    s
                    for s in self.index.by_name.get(key, [])
                    if s.district in self.provider.elderships
                ]
                if len(elsewhere) == 1 and elsewhere[0].code not in self.named[self.kind]:
                    found = elsewhere
            abbr = _SETTLEMENT_TYPES.get(kind or "")
            wanted = {
                "m.": ("m.", "mstl."),
                "mstl.": ("mstl.", "m."),
                "k.": ("k.", "vs."),
                "vs.": ("vs.", "k."),
            }.get(abbr or "", (abbr,))
            typed = next((t for a in wanted if (t := [s for s in found if s.abbr == a])), [])
            hits += typed or found
        return list({s.code: s for s in hits}.values())

    def which(self, places: list[Settlement]) -> str | None:
        """Of settlements of one name in several elderships, the eldership meant: the one of
        most of the list's other settlements, or the one around their town ("Bajorų k.,
        Rokiškio m. - ...": Rokiškio kaimiškoji, not Kriaunų)."""
        districts = {s.district for s in places}
        chosen = next((d for d in self.common if d in districts), None)
        if chosen is None:
            stems = {fold(d).split()[0] for d in self.common}
            around = [d for d in districts if fold(d).split()[0] in stems]
            chosen = around[0] if len(around) == 1 else None
        return chosen

    def elderships_of(self, text: str) -> list[str]:
        """The elderships of the settlements a list names that are of only one, most first."""
        counts: Counter[str] = Counter()
        for part in _section_parts(text):
            head = part.partition("(")[0].strip(" ,;:")
            match = _ITEM.fullmatch(head)
            if not match or (match["type"] and match["type"] not in _SETTLEMENT_TYPES):
                continue
            hits = self.settlements(match["name"], match["numerals"], match["type"], "")
            districts = {s.district for s in hits}
            if len(districts) == 1:
                counts[districts.pop()] += 1
        return [district for district, _ in counts.most_common()]

    # -- the lists -------------------------------------------------------------------

    def text_of(self, area: Area) -> str:
        """The list a row's name is (DocumentRoutes: written otherwise)."""
        return area.name

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        self.kind = area.kind
        self.town = _NO_TOWN
        text = self.normalize(self.text_of(area))
        marks = self.marks(text)
        if not any(punctuation == ":" for *_, punctuation in marks):
            # No sections: an eldership after a settlement tells which ("Pagojų k. Kazliškio
            # sen."), unless it starts the list.
            for start, end, district, _ in reversed(marks):
                before, after = text[:start].rstrip(" ,;-"), text[end:].lstrip(" ,;-")
                if before:
                    text = f"{before} ({district} sen.)" + (f", {after}" if after else "")
            marks = [m for m in self.marks(text) if not text[: m[0]].strip(" ,;-")]
        lead = text[: marks[0][0]] if marks else text
        self.common = self.elderships_of(lead)
        stops = self.section("", lead) if lead.strip(" .,;:") else []
        for i, (_, end, district, _) in enumerate(marks):
            until = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            self.town = self.towns.get(district, _NO_TOWN)
            stops += self.section(district, text[end:until])
        self.town = _NO_TOWN
        return [(s.settlement, c) for s in stops for c in s.clauses(area.id)], False

    def section(self, district: str, text: str) -> list[_Stop]:
        """The settlements of an eldership's part of a list, or ("") of a list without
        sections, and their streets."""
        stops: list[_Stop] = []
        current: list[_Stop] = []  # the settlements the streets after them belong to
        last: list[tuple[_Stop, set[str]]] = []  # the last street, for house numbers after it
        where = f"{district} sen." if district else self.municipality.label
        for part in _section_parts(re.sub(r"\s*:\s*", ", ", text)):
            if _SHARED_PART.search(fold(part)):
                current, last = [], []
                continue
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0].strip() if rest else None
            head = head.strip(" ,;:")
            hint = None
            if spec and (match := _HINT.fullmatch(spec)) and (found := self.district(match[1])):
                hint, spec = found, None
            if _HOUSE.fullmatch(head):
                for stop, keys in last:
                    stop.add(keys, houses=True)
                continue
            match = _ITEM.fullmatch(head)
            if not match:
                self.unknown.append(f"{where}: {head[:60]}")
                current, last = [], []
                continue
            name, numerals, kind = match.group("name", "numerals", "type")
            houses = bool(match["houses"])
            here = hint or district
            places: list[Settlement] = []
            if kind in _SETTLEMENT_TYPES or numerals or not (kind or houses):
                places = self.settlements(name, numerals, kind, here)
            if not places and kind not in _SETTLEMENT_TYPES:
                # A street of the settlement before it, or of the town of its section.
                targets = current
                if not targets and self.town is not _NO_TOWN:
                    town = next((s for s in stops if s.settlement is self.town), None)
                    targets = [town or _Stop(self.town)]
                loose = bool(kind or houses)
                found = [(t, self.streets(t.settlement, head, name, kind, loose)) for t in targets]
                if any(keys for _, keys in found):
                    last = [(t, keys) for t, keys in found if keys]
                    for target, keys in last:
                        target.add(keys, houses)
                        if target not in stops:
                            stops.append(target)
                    continue
                if kind == "g" and not targets:
                    # "Raudonėnų g." for the village Raudonėnai; not in a list of streets.
                    places = self.settlements(name, None, None, here)
                if not places and (kind or houses) and targets:
                    self.unknown += [
                        f"{t.settlement.genitive} {t.settlement.abbr}: {head[:60]}" for t in targets
                    ]
                    last = []
                    continue
            if not places:
                self.unknown.append(f"{where}: {head[:60]}")
                current, last = [], []
                continue
            if not here and len({s.district for s in places}) > 1:
                chosen = self.which(places)
                if chosen is None:
                    districts = ", ".join(sorted({f"{s.district} sen." for s in places}))
                    self.unknown.append(f"{where}: {head[:60]} (in {districts})")
                    current, last = [], []
                    continue
                places = [s for s in places if s.district == chosen]
            current, last = [_Stop(s) for s in places], []
            stops += current
            if spec is not None:
                self.spec(current, spec)
        return stops


class DocumentRoutes(Places):
    """Places, and the mixed waste routes of Panevėžio r.'s Word document (pratc_word), whose
    names pratc_word.places writes as the lists Places reads: "Paliūniškio, Klimbalės, ...
    gyvenviečių", "Ramygalos gatvių: Biliūno, ... taip pat Daniūnų, ... gyvenviečių".

    "... ir kitų Karsakiškio seniūnijos gyvenviečių" (and the eldership's other settlements)
    gives the route to every settlement of the eldership as a fallback, which a route that
    names a settlement overrides (locations.resolve), as "X sen. kaimai" elsewhere."""

    def text_of(self, area: Area) -> str:
        return pratc_word.places(area.name)[0] if area.kind == "household" else area.name

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        found, skipped = super().clauses(area)
        rest = pratc_word.places(area.name)[1] if area.kind == "household" else None
        if rest is not None:
            district = self.district(rest)
            if district is None:
                self.unknown.append(f"{self.municipality.label}: {rest} sen.")
            else:
                found += [
                    (s, Clause(area.id, None, fallback=True))
                    for s in self.index.registry.settlements
                    if s.district == district
                ]
        return found, skipped


# --- the municipalities ----------------------------------------------------------------


@dataclass(frozen=True)
class Municipality:
    """A municipality of the page: its section, whom its schedules serve, and how much of them
    to expect."""

    provider: Provider
    heading: str  # in the title of its section on the page, folded: "pasvalio r"
    register: tuple[str, int]  # the Address Register's name and code
    registry_file: Path
    addresses_file: Path
    label: str  # for the job summary and the warnings
    town: str  # its town (nominative), whose streets the lists name without it
    # Fewer rows of a kind than this, this year or in next year's file, means the format
    # changed and the parser or the matching missed rows.
    min_areas: dict[Kind, int]
    # Settlements that must get a mixed waste schedule, and any schedule (check_places).
    min_household_places: int
    min_places: int
    min_address_points: int
    # Kinds of schedule in a file of each kind, where a file has more than one.
    file_kinds: dict[Kind, tuple[Kind, ...]] = field(default_factory=dict)
    # Kinds published as a Word 97-2003 document (pratc_word) instead of a spreadsheet.
    documents: tuple[Kind, ...] = ()


def _provider(
    id: str, elderships: set[str], kinds: tuple[Kind, ...], reader: type = Places, **more
) -> Provider:
    """`kinds`: also the kinds of the files read (Panevėžio r.: not its food waste)."""
    return Provider(
        id=id,
        name=COMPANY,
        url=PAGE_URL,
        elderships=frozenset(elderships),
        reader=reader,
        kinds=kinds,
        **more,
    )


PASVALYS = Municipality(
    _provider(
        "pasvalys",
        {
            "Daujėnų",
            "Joniškėlio apylinkių",
            "Joniškėlio miesto",
            "Krinčino",
            "Namišių",
            "Pasvalio apylinkių",
            "Pasvalio miesto",
            "Pumpėnų",
            "Pušaloto",
            "Saločių",
            "Vaškų",
        },
        ("household", "packaging", "glass", "food"),
    ),
    "pasvalio r",
    snapshot.PASVALIO_R_MUNICIPALITY,
    snapshot.PASVALIO_R_REGISTRY_FILE,
    snapshot.PASVALIO_R_ADDRESSES_FILE,
    label="Pasvalio r.",
    town="Pasvalys",
    # 2026: 31 mixed waste routes, 10 packaging and 30 glass routes and one food waste route
    # (Pasvalys and two villages), which gave a mixed waste schedule to 259 of the 391
    # settlements and some schedule to 267.
    min_areas={"household": 24, "packaging": 8, "glass": 24, "food": 1},
    min_household_places=200,
    min_places=200,
    # About 12,200 addresses in 2026.
    min_address_points=8_000,
    file_kinds={"packaging": ("packaging", "glass")},
)
ROKISKIS = Municipality(
    _provider(
        "rokiskis",
        {
            "Juodupės",
            "Jūžintų",
            "Kamajų",
            "Kazliškio",
            "Kriaunų",
            "Obelių",
            "Pandėlio",
            "Panemunėlio",
            "Rokiškio kaimiškoji",
            "Rokiškio miesto",
        },
        ("household", "packaging", "glass", "food"),
        aliases=(
            # The mixed waste routes: a town and its suburb, one street of two types, missing
            # hyphens, streets as the food waste routes and the register write them, and
            # villages one letter off, too short to be taken for typos.
            ("Obelių miestas ir priemiestis", "Obelių m., Obelių Priemiestis"),
            ("Parko g. ir sk.", "Parko g.-Parko sk."),
            ("Pirties Respublikos", "Pirties-Respublikos"),
            ("P. Jakšto Janulionio - Dariaus", "P. Jakšto-Janulionio-Dariaus"),
            ("Upės takas", "Upės Tako g."),
            ("Tyzenhauzų a.", "Tyzenhauzų al."),
            ("Skersinės-Siaurosios-", "Skersinės-Siauroji-"),
            ("Žemaitės-Geležinkelio-", "Žemaitės-Geležinkeliečių-"),
            ("Kęstučio-Paupio-", "Kęstučio-Paupės-"),
            ("Sporto-Lašo-", "Sporto-V. Lašo-"),
            ("Brizgių, Alksių,", "Brizgių, Alksnių,"),  # Juodupės sen.
            ("Mickūnų-Čelkų-", "Mickūnų-Čelkių-"),  # Jūžintų sen.
            ("Petriošiškio-Rūdžų", "Petriošiškio-Rudžių"),  # Kamajų sen.
        ),
    ),
    "rokiskio r",
    snapshot.ROKISKIO_R_MUNICIPALITY,
    snapshot.ROKISKIO_R_REGISTRY_FILE,
    snapshot.ROKISKIO_R_ADDRESSES_FILE,
    label="Rokiškio r.",
    town="Rokiškis",
    # 2026: 18 mixed waste routes (and 4 of shared containers, not read), 14 packaging and 42
    # glass routes and 2 food waste routes (Rokiškis and a few villages), which gave a mixed
    # waste schedule to 249 of the 692 settlements (its list of villages is shorter than the
    # packaging one) and some schedule to 363.
    min_areas={"household": 14, "packaging": 10, "glass": 30, "food": 1},
    min_household_places=190,
    min_places=280,
    # About 16,300 addresses in 2026.
    min_address_points=11_000,
    file_kinds={"packaging": ("packaging", "glass")},
)
BIRZAI = Municipality(
    _provider(
        "birzai",
        {
            "Biržų miesto",
            "Nemunėlio Radviliškio",
            "Pabiržės",
            "Papilio",
            "Parovėjos",
            "Pačeriaukštės",
            "Vabalninko",
            "Širvėnos",
        },
        ("household", "packaging", "glass", "food"),
        aliases=(("N. Radviliškis", "Nemunėlio Radviliškis"),),
    ),
    "birzu r",
    snapshot.BIRZU_R_MUNICIPALITY,
    snapshot.BIRZU_R_REGISTRY_FILE,
    snapshot.BIRZU_R_ADDRESSES_FILE,
    label="Biržų r.",
    town="Biržai",
    # 2026: 46 places, each with mixed waste, packaging and glass dates, and 3 food waste
    # routes (Biržai and three villages), which gave a mixed waste schedule to 292 of the 531
    # settlements.
    min_areas={"household": 35, "packaging": 35, "glass": 35, "food": 2},
    min_household_places=220,
    min_places=220,
    # About 13,000 addresses in 2026.
    min_address_points=8_000,
    file_kinds={"household": ("household", "packaging", "glass")},
)
PANEVEZIO_R = Municipality(
    _provider(
        "panevezio-r",
        {
            "Karsakiškio",
            "Krekenavos",
            "Miežiškių",
            "Naujamiesčio",
            "Panevėžio",
            "Paįstrio",
            "Raguvos",
            "Ramygalos",
            "Smilgių",
            "Upytės",
            "Vadoklių",
            "Velžio",
        },
        ("household", "packaging", "glass"),
        reader=DocumentRoutes,
    ),
    "panevezio r",
    snapshot.PANEVEZIO_R_MUNICIPALITY,
    snapshot.PANEVEZIO_R_REGISTRY_FILE,
    snapshot.PANEVEZIO_R_ADDRESSES_FILE,
    label="Panevėžio r.",
    town="",
    # 2026: 26 mixed waste routes in 29 rows (pratc_word; route 3 is four), 16 packaging and 48
    # glass routes, which gave a mixed waste schedule to 248 of the 737 settlements (97 of them
    # all of Karsakiškio sen.), a packaging schedule to 398 and some schedule to 453.
    min_areas={"household": 22, "packaging": 12, "glass": 36},
    min_household_places=190,
    min_places=300,
    # About 30,600 addresses in 2026.
    min_address_points=20_000,
    documents=("household",),
)
MUNICIPALITIES = (PASVALYS, ROKISKIS, BIRZAI, PANEVEZIO_R)
BY_ID = {m.provider.id: m for m in MUNICIPALITIES}


# --- the page ----------------------------------------------------------------------------


class _Page(HTMLParser):
    """The page's list items with their texts and links (and the links' texts), under the
    title of their section ("Pasvalio r. atliekų išvežimo grafikai")."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, str, list[tuple[str, str]]]] = []
        self.section = ""
        self.title: list[str] | None = None
        self.text: list[str] | None = None
        self.links: list[tuple[str, str]] = []
        self.link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "div" and "about-us-stats-title" in (values.get("class") or "").split():
            self.title = []
        elif tag == "li":
            self.text, self.links = [], []
        elif tag == "a" and self.text is not None and values.get("href"):
            self.link = (values["href"] or "", [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self.title is not None:
            self.section = clean_text("".join(self.title))
            self.title = None
        elif tag == "a" and self.link is not None:
            href, text = self.link
            self.links.append((href, clean_text("".join(text))))
            self.link = None
        elif tag == "li" and self.text is not None:
            self.items.append((self.section, clean_text("".join(self.text)), self.links))
            self.text = None

    def handle_data(self, data: str) -> None:
        for collecting in (self.title, self.text, self.link[1] if self.link else None):
            if collecting is not None:
                collecting.append(data)


# What a file is for, in the text of its item (folded): not the individual houses' pickups.
OTHERS = (
    "bendro naudojimo",
    "juridin",
    "tekstil",
    "gabarit",
    "kapini",
    "plovim",
    "dezinfek",
    "apvaziav",
)


def file_name(url: str) -> str:
    return PurePosixPath(unquote(urlsplit(url).path)).name


def _year_in(text: str) -> int | None:
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}
    return years.pop() if len(years) == 1 else None


def file_kind(text: str) -> Kind | None:
    """By the text of the file's item: "Pakuočių (stiklo) ... grafikas" is glass, "Pakuočių ir
    stiklo ..." packaging and glass, "Mišrių komunalinių ir pakuočių ..." (Biržų r.) mixed
    waste, packaging and glass."""
    folded = fold(text)
    if "stikl" in folded and not re.search(r"\bir stikl", folded):
        return "glass"
    if "komunalin" in folded or "misri" in folded:
        return "household"
    if "pakuo" in folded:
        return "packaging"
    if "maist" in folded:
        return "food"
    return None


def find_files(
    html: str, page_url: str = PAGE_URL
) -> tuple[list[tuple[Municipality, SourceFile, int | None]], list[str]]:
    """The spreadsheets of individual houses the page links (Panevėžio r.'s mixed waste: Word
    documents), with their municipalities and the years in their links (None: not there), and
    warnings for a file of a kind we read that isn't of its format."""
    page = _Page()
    page.feed(html)
    found: list[tuple[Municipality, SourceFile, int | None]] = []
    warnings: list[str] = []
    for section, text, links in page.items:
        municipality = next((m for m in MUNICIPALITIES if m.heading in fold(section)), None)
        kind = file_kind(text)
        if municipality is None or kind is None or any(w in fold(text) for w in OTHERS):
            continue
        if kind not in municipality.provider.kinds:
            continue  # Panevėžio r.'s food waste
        for href, label in links:
            if not label:
                continue  # not shown on the page: an old file still linked
            url = urljoin(page_url, href)
            name = file_name(url)
            if kind in municipality.documents and not name.lower().endswith(".doc"):
                warnings.append(
                    f"{municipality.label}: {name}: not a Word 97-2003 document; not read"
                )
                continue
            if kind not in municipality.documents and not name.lower().endswith(".xlsx"):
                warnings.append(f"{municipality.label}: {name}: not a spreadsheet; not read")
                continue
            if any(f.url == url for m, f, _ in found if m is municipality):
                continue
            year = _year_in(f"{label} {text} {unquote(urlsplit(url).path)}")
            found.append((municipality, SourceFile(kind, url, name), year))
    return found, warnings


def content_year(content: bytes) -> int | None:
    """The year in a spreadsheet's titles: its sheets' names and the rows above its tables; or
    in the title of a Word document."""
    if worddoc.is_document(content):
        try:
            return pratc_word.read(content).year
        except ValueError:
            return None
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):  # not a spreadsheet
        return None
    texts: list[str] = []
    for sheet in workbook.worksheets:
        if sheet.sheet_state == "visible":
            texts.append(sheet.title)
            for row in sheet.iter_rows(max_row=5, values_only=True):
                texts += [clean_text(c) for c in row if isinstance(c, str)]
    return _year_in(" ".join(texts))


def select_files(
    files: list[tuple[SourceFile, int | None]], municipality: Municipality, today: date
) -> tuple[list[SourceFile], list[str]]:
    """Per kind, the files of this year and later; if there are none, the newest one. Of two
    for one year (a correction linked next to the original), the one linked last."""
    where = municipality.label
    selected: list[SourceFile] = []
    warnings: list[str] = []
    for kind in sorted({f.kind for f, _ in files}):
        mine = [(f, y) for f, y in files if f.kind == kind]
        warnings += [
            f"{where}: {f.file_name}: no year in its link or titles; not read"
            for f, y in mine
            if not y
        ]
        dated = [(f, y) for f, y in mine if y]
        running = [(f, y) for f, y in dated if y >= today.year]
        if not running and dated:
            newest = max(y for _, y in dated)
            running = [(f, y) for f, y in dated if y == newest]
        if dated and today.year not in {y for _, y in running}:
            warnings.append(f"{where}: no {kind} schedule for {today.year} on the page")
        for year in sorted({y for _, y in running}):
            same = [f for f, y in running if y == year]
            selected.append(same[-1])
            warnings += [
                f"{where}: {f.file_name}: not read, {same[-1].file_name} is a newer {kind} "
                f"schedule for {year}"
                for f in same[:-1]
            ]
    return selected, warnings


def fetch_page() -> str:
    return http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")


def download(
    municipality: Municipality,
    today: date,
    keep_days: int,
    page: Callable[[], str] = fetch_page,
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    found, warnings = find_files(page())
    mine = [(f, y) for m, f, y in found if m is municipality]
    contents = {f.url: http.get(f.url, timeout=60) for f, _ in mine}
    dated = [(f, y or content_year(contents[f.url])) for f, y in mine]
    selected, notes = select_files(dated, municipality, today)
    warnings = [w for w in warnings if w.startswith(f"{municipality.label}:")]
    return [(f, contents[f.url]) for f in selected], warnings + notes


# --- the spreadsheets --------------------------------------------------------------------


def _route_column(texts: list[list[str]], header: int) -> int | None:
    """The column of the routes, titled "Maršrutas" in the row of the months or above it."""
    for i in range(max(len(row) for row in texts)):
        title = " ".join(
            texts[r][i] for r in range(max(0, header - 2), header + 1) if i < len(texts[r])
        )
        if "marsrutas" in fold(title):
            return i
    return None


def _sheet_kind(text: str) -> Kind | None:
    """The waste type of a sheet, by the title above its table ("... STIKLO PAKUOČIŲ
    ATLIEKŲ ...", "... MIŠRIŲ KOMUNALINIŲ ATLIEKŲ ...") or its name."""
    folded = fold(text)
    for word, kind in (
        ("stikl", "glass"),
        ("maist", "food"),
        ("pakuo", "packaging"),
        ("komunalin", "household"),
    ):
        if word in folded:
            return kind
    return None


def _with_rules(texts: list[list[str]], header: int) -> bool:
    """A table of rules ("Pirmą mėnesio ketvirtadienį") over rows of days, not of days in the
    rows of the routes: most routes have words in their first month."""
    column = _route_column(texts, header)
    first = next(i for i, c in enumerate(texts[header]) if parse_month(c))
    if column is None:
        return False
    rules = [
        bool(re.search(r"[^\W\d_]{3}", row[first] if first < len(row) else ""))
        for row in texts[header + 1 :]
        if column < len(row) and row[column]
    ]
    return bool(rules) and sum(rules) > len(rules) / 2


_INDIVIDUAL = re.compile(r"^\s*Individual\w*\s*:\s*", re.I)
_SHARED_TAIL = re.compile(r"\s*\bBendro naudojimo\s*:.*$", re.I | re.S)
_CONTAINERS = re.compile(r"\s*\(\s*individualaus naudojimo konteineriai\s*\)", re.I)
# Not routes: a waste code ("KODAS | 20 01 99 02"), a note ("Taip pat ... galite rasti
# https://...").
_NOT_ROUTES = re.compile(r"^\d{2} \d{2} \d{2}|^taip pat\b|https?:", re.I)


def _individual(
    rows: list[list[object]], texts: list[list[str]], header: int, where: str
) -> tuple[list[list[object]], list[str]]:
    """The rows of individual houses: a row of shared containers is emptied, and of a cell
    with both ("Individualūs: ... Bendro naudojimo: ...") the individual part kept."""
    column = _route_column(texts, header)
    if column is None:
        return rows, []
    result: list[list[object]] = []
    warnings: list[str] = []
    for line_no, (row, cells) in enumerate(zip(rows, texts, strict=True), start=1):
        if line_no <= header + 1 or column >= len(row) or not cells[column]:
            result.append(row)
            continue
        if fold(cells[column]).startswith(("bendro naudojimo", "kolektyvinio naudojimo")):
            warnings.append(f"{where} row {line_no}: shared containers; not read")
            result.append([None] * len(row))
        elif _NOT_ROUTES.search(cells[column]) or fold(cells[0]) == "kodas":
            result.append([None] * len(row))
        else:
            text = _INDIVIDUAL.sub("", str(row[column]))
            text = _CONTAINERS.sub("", _SHARED_TAIL.sub("", text))
            result.append([*row[:column], text, *row[column + 1 :]])
    return result, warnings


def parse_rules(
    rows: list[list[object]],
    texts: list[list[str]],
    header: int,
    kind: Kind,
    title: str,
    where: str,
    provider: str,
) -> ParseResult:
    """A table of a rule per route ("Pirmą ir trečią antradienį") and the row of its days below
    it. Routes of shared containers have a rule and no days, and aren't read; a day the rule
    doesn't allow is a warning. Strict: a cell that isn't a list of days raises ValueError."""
    months = [(i, m) for i, c in enumerate(texts[header]) if (m := parse_month(c))]
    if [m for _, m in months] != list(range(1, 13)):
        raise ValueError(f"{where}: unexpected month columns {texts[header]}")
    above = " ".join(c for row in texts[: header + 1] for c in row)
    year = _year_in(above) or _year_in(title)
    if year is None:
        raise ValueError(f"{where}: cannot tell the year")
    column = _route_column(texts, header)
    if column is None:
        raise ValueError(f"{where}: no route column in {texts[header]}")
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    route: tuple[str, str, str, int] | None = None  # name, number, rule, line

    def left_out(route: tuple[str, str, str, int]) -> None:
        name, number, _, line = route
        if number.endswith("*") or re.search(r"daugiabu|aikstel", fold(name)):
            warnings.append(f"{where} row {line}: shared containers; not read")
        else:
            warnings.append(f"{where} row {line}: no days for {name[:60]!r}")

    for line_no, (row, cells) in enumerate(
        zip(rows[header + 1 :], texts[header + 1 :], strict=True), start=header + 2
    ):
        name = cells[column] if column < len(cells) else ""
        number = cells[0] if column else ""
        values = [row[i] if i < len(row) else None for i, _ in months]
        if name:
            if number == "*":
                break  # the note under the table
            if route:
                left_out(route)
            rule = cells[months[0][0]] if months[0][0] < len(cells) else ""
            route = (name, number, rule, line_no)
            continue
        if not any(clean_text(v) for v in values):
            continue
        if route is None:
            raise ValueError(f"{where} row {line_no}: days before the first route")
        area = Area(kind=kind, name=route[0], provider=provider)
        for (_, month), value in zip(months, values, strict=True):
            try:
                area.dates |= {date(year, month, day) for day in parse_days(value)}
            except ValueError as error:
                raise ValueError(f"{where} row {line_no}: {error}") from error
        weekdays = parse_weekdays(route[2])
        odd = sorted(d for d in area.dates if weekdays and d.weekday() not in weekdays)
        if odd:
            warnings.append(
                f"{where} row {line_no}: {', '.join(d.isoformat() for d in odd)} isn't a day of "
                f"the rule {route[2]!r}"
            )
        existing = areas.setdefault(area.id, area)
        if existing is not area:
            warnings.append(f"{where} row {line_no}: {route[0][:60]!r} is listed twice")
            existing.dates |= area.dates
        route = None
    if route:
        left_out(route)
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def _block_kind(text: str) -> tuple[bool, Kind | None]:
    """A column title of a block ("Buitinių atliekų grafikas", "Pakuočių atliekų ir antrinių
    žaliavų grafikas", "Stiklo grafikas"): whether it is one, and its waste type."""
    folded = fold(text)
    if "grafik" not in folded:
        return False, None
    for word, kind in (
        ("buitin", "household"),
        ("komunalin", "household"),
        ("misri", "household"),
        ("stikl", "glass"),
        ("pakuo", "packaging"),
        ("maist", "food"),
    ):
        if word in folded:
            return True, kind
    return True, None


def parse_blocks(
    rows: list[list[object]], texts: list[list[str]], title: str, where: str, provider: str
) -> ParseResult:
    """A block of twelve rows per place: the place in the first column, the waste types'
    titles above, each month's name in the column before its days. Strict: a block without
    its twelve months, days that aren't days and a place without dates raise ValueError."""
    year = _year_in(title) or _year_in(" ".join(c for row in texts for c in row))
    blocks: list[_Block] = []
    columns: dict[int, Kind | None] = {}
    block: _Block | None = None
    for line_no, (row, cells) in enumerate(zip(rows, texts, strict=True), start=1):
        titles = {i: kind for i, c in enumerate(cells) if i for ok, kind in [_block_kind(c)] if ok}
        if len(titles) >= 2:
            columns = titles
            continue
        months = {i: m for i, c in enumerate(cells) if (m := _month(c))}
        if not months:
            continue
        if not columns:
            raise ValueError(f"{where} row {line_no}: months under no waste types")
        if year is None:
            raise ValueError(f"{where}: cannot tell the year")
        month = next(iter(months.values()))
        if any(m != month for m in months.values()):
            raise ValueError(f"{where} row {line_no}: months {sorted(months.values())} in one row")
        if month == 1 and block and block.months:
            blocks.append(_close(block, f"{where} row {line_no}"))
            block = None
        if block is None:
            if month != 1:
                raise ValueError(f"{where} row {line_no}: a place starting with month {month}")
            block = _Block(None, line_no)
        if block.months and month != block.months[-1] + 1:
            raise ValueError(f"{where} row {line_no}: month {month} after {block.months[-1]}")
        block.months.append(month)
        if cells[0]:
            block.lines.append(cells[0])
        for i in months:
            kind = columns.get(i + 1, columns.get(i))
            value = row[i + 1] if i + 1 < len(row) else None
            if kind and clean_text(value):
                block.dates[kind] |= _days(str(value), year, month, f"{where} row {line_no}")
        if month == 12:
            blocks.append(_close(block, f"{where} row {line_no}"))
            block = None
    if block:
        blocks.append(_close(block, where))
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for block in blocks:
        if not block.dates:
            raise ValueError(f"{where} row {block.page}: no dates for {block.name[:60]!r}")
        for kind, dates in block.dates.items():
            area = Area(kind, block.name, provider=provider, dates=set(dates))
            existing = areas.setdefault(area.id, area)
            if existing is not area:
                warnings.append(f"{where} row {block.page}: {kind} of {block.name[:60]!r} twice")
                existing.dates |= area.dates
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_file(
    source: SourceFile,
    content: bytes,
    municipality: Municipality = PASVALYS,
    published: Callable[[], dict] | None = None,
) -> ParseResult:
    """The routes of every visible sheet of a file, in whichever of the three layouts, or of a
    Word document (parse_document). Strict: a file without a table, rows of a waste type its
    kind doesn't have, dates of several years or of another year than its link's raise
    ValueError."""
    if source.kind in municipality.documents:
        return parse_document(source, content, municipality, published)
    provider = municipality.provider.id
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    result = ParseResult(areas=[])
    for sheet in workbook.worksheets:
        if sheet.sheet_state != "visible":
            continue
        where = f"{source.file_name} [{sheet.title}]"
        rows = _visible_rows(sheet)
        if not rows:
            continue
        texts = [[clean_text(c) for c in row] for row in rows]
        header = _month_row(texts)
        if header is None:
            parsed = parse_blocks(rows, texts, sheet.title, where, provider)
        else:
            above = " ".join(c for row in texts[:header] for c in row if c)
            kind = _sheet_kind(above) or _sheet_kind(sheet.title) or source.kind
            if _with_rules(texts, header):
                parsed = parse_rules(rows, texts, header, kind, sheet.title, where, provider)
            else:
                rows, notes = _individual(rows, texts, header, where)
                parsed = parse_sheet(rows, kind, sheet.title, where, provider)
                parsed.warnings[:0] = notes
        result.areas += parsed.areas
        result.warnings += parsed.warnings
    if not result.areas:
        raise ValueError(f"{source.file_name}: no schedule table found")
    allowed = set(municipality.file_kinds.get(source.kind, (source.kind,)))
    if others := sorted({a.kind for a in result.areas} - allowed):
        raise ValueError(f"{source.file_name}: {', '.join(others)} in a {source.kind} file")
    years = {d.year for area in result.areas for d in area.dates}
    linked = _year_in(unquote(urlsplit(source.url).path))
    if len(years) != 1 or (linked and years != {linked}):
        raise ValueError(
            f"{source.file_name}: the dates are of {sorted(years)}"
            + (f", the link says {linked}" if linked else "")
        )
    for area in result.areas:
        weekdays = {d.weekday() for d in area.dates}
        if len(weekdays) == 1:
            area.weekday = WEEKDAY_NAMES[weekdays.pop()]
    return result


def parse_document(
    source: SourceFile,
    content: bytes,
    municipality: Municipality,
    published: Callable[[], dict] | None = None,
) -> ParseResult:
    """The rows of a Word document (pratc_word.parse), or, if it can't be read (a route with
    notes the transcription doesn't have, a changed layout), the municipality's rows of its kind
    in yesterday's data (`published`; None: raise instead), so its other kinds are still
    updated, as raseiniai.parse_or_keep does for a file."""
    try:
        return pratc_word.parse(source, content, municipality.provider.id)
    except Exception as error:  # any failure of the document must not stop the spreadsheets
        if published is None:
            raise
        kept = build.published_rows(
            published(), municipality.provider, lambda row: row["kind"] == source.kind
        )
        if not kept:
            raise
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} {source.kind} rows of {municipality.label} are kept"
            ],
        )


# --- this year and the next ------------------------------------------------------------


def combine(
    parsed: list[tuple[SourceFile, ParseResult]],
    registry: Registry,
    today: date,
    municipality: Municipality = PASVALYS,
) -> list[str]:
    """Joins next year's routes to this year's, in place, per kind.

    A place has one row per waste type, with all its dates. Next year's files may word and
    number the routes differently, so a route of next year that covers exactly the same streets
    and settlements as one route of this year gives it its dates. The rest is left out, with a
    warning, until its year starts and it becomes the schedule in force; routes of earlier
    years are dropped. Next year's file is checked now, not on 1 January: too few routes in it
    raise ValueError."""
    reader = municipality.provider.reader(Index(registry), municipality.provider, defaultdict(dict))
    warnings: list[str] = []
    by_kind: dict[Kind, dict[int, list[tuple[ParseResult, Area]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for _, result in parsed:
        for area in result.areas:
            by_kind[area.kind][min(area.dates).year].append((result, area))
    for kind, years in by_kind.items():
        started = [year for year in years if year <= today.year]
        base = max(started) if started else min(years)
        current: dict[frozenset, list[Area]] = defaultdict(list)
        for _, area in years[base]:
            current[reader.signature(area)].append(area)
        for year in sorted(years):
            if year == base:
                continue
            minimum = municipality.min_areas.get(kind, 0)
            if year > base and len(years[year]) < minimum:
                raise ValueError(
                    f"only {len(years[year])} {kind} routes in the {year} file "
                    f"(expected at least {minimum})"
                )
            signatures = {id(area): reader.signature(area) for _, area in years[year]}
            times = Counter(signatures.values())
            continued: set[int] = set()
            for result, area in years[year]:
                signature = signatures[id(area)]
                same = current.get(signature, [])
                # One route of each year, and places we recognise: anything else could give
                # a place the dates of another route.
                if year > base and signature and len(same) == 1 and times[signature] == 1:
                    same[0].dates |= area.dates
                    continued.add(id(same[0]))
                elif year > base:
                    warnings.append(
                        f"{kind}: the {year} route {area.name[:60]!r} doesn't match one "
                        f"{base} route; its dates are left out until {year}"
                    )
                result.areas.remove(area)
            if year > base:
                warnings += [
                    f"{kind}: the {base} route {area.name[:60]!r} has no dates for {year}"
                    for _, area in years[base]
                    if id(area) not in continued
                ]
    return warnings


def source(
    municipality: Municipality,
    page: Callable[[], str] = fetch_page,
    published: Callable[[], dict] | None = None,
) -> build.Source:
    """`published`: yesterday's data, for a Word document that can't be read (parse_document;
    None: fail instead)."""
    return build.Source(
        municipality.provider,
        partial(download, municipality, page=page),
        partial(parse_file, municipality=municipality, published=published),
        municipality.min_areas,
        municipality.min_household_places,
        municipality.file_kinds,
        partial(combine, municipality=municipality),
    )


# --- the output --------------------------------------------------------------------------


def check_places(municipality: Municipality, part: dict) -> None:
    """A municipality's settlements must get schedules: fewer means its files or the matching
    broke, which the rows' counts don't show."""
    served = sum(1 for loc in part["locations"] if loc.get("schedule"))
    if served < municipality.min_places:
        raise build.ValidationError(
            f"{municipality.label}: only {served} settlements got a schedule "
            f"(expected at least {municipality.min_places})"
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
    page = cache(fetch_page)  # one page for the four
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
                _once(partial(address_register.fetch, name), "register", down),
                partial(snapshot.load_registry, municipality.registry_file),
            )
            found, points_note = build.live_or_snapshot(
                f"Address points ({municipality.label})",
                _once(partial(address_points.fetch, code), "points", down),
                partial(snapshot.load_points, municipality.addresses_file),
            )
            notes += [n for n in (registry_note, points_note) if n]
            registries.append((municipality, registry))
            points += found
            built = build.build_parts(
                (source(municipality, page, loader),),
                registry,
                date.today(),
                args.keep_days,
                loader,
            )
            for result in built:
                if result.part is None or result.error:
                    continue
                try:
                    check_places(municipality, result.part)
                except build.ValidationError as error:
                    if loader is None:
                        raise
                    # As build_parts does for a build that fails: yesterday's part.
                    result.part = build.published_part(loader(), municipality.provider)
                    result.warnings, result.error = [], f"ValidationError: {error}"
            results += built
        dataset = build.merge_parts([(r.provider, r.part) for r in results if r.part], PAGE_URL)
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
        # A Word document that can't be read (parse_document): the rows kept say why.
        for warning in r.warnings:
            if municipality.documents and "can't be read" in warning:
                print(f"::warning::{municipality.label}: {warning}")

    args.out.mkdir(parents=True, exist_ok=True)
    for file_name_, data in (("schedule.json", dataset), ("addresses.json", addresses)):
        (args.out / file_name_).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    # A section per municipality: the company's name is the same in each.
    for municipality, r in zip(MUNICIPALITIES, results, strict=True):
        part = r.part or {"locations": [], "areas": []}
        title, out_file = f"{municipality.label} (PRATC)", f"{args.out.name}/schedule.json"
        build.write_summary(part, [r], [], title, f"{municipality.label} in {out_file}")
    build.write_summary(dataset, [], notes, "Panevėžio RATC", f"{args.out.name}/schedule.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

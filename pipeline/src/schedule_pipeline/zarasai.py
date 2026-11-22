"""Zarasų rajonas: the schedules the municipality publishes on its page (zarasai.lt) for the
individual containers of the whole municipality: mixed waste, emptied by UAB „Zarasų būstas“,
and packaging and glass, by UAB „Zarasų komunalininkas“.

The page has a table of the kinds of waste, each with its schedule linked by the day it
applies from:

    Atliekų rūšis                                         Išvežimo grafikas
    Komunalinės atliekos                                  Nuo 2026-01-01      a scan
    Antrinės žaliavos (stiklas, plastikas, popierius)     Nuo 2026-01-01      a PDF made in Word
    Maisto atliekos                                       Nuo 2026-01-01      a scan (not read)

The files are found by these texts. Not read: food waste (a scanned table of dates for streets
of Zarasai and for Dusetos and Užtiltė), the shared containers ("Kolektyvinio naudojimo
konteinerių išvežimo grafikai"), textiles, cooking oil and bulky waste.

**Mixed waste** is a scan of three pages without text: a paragraph per route, the weekdays of
the month it is emptied on, then its places after each eldership, printed in bold:

    2-ą ir paskutinį mėnesio pirmadienį – Zarasų sen. Šaltupės g. nuo 66 nr. iki 70 nr., ...
    PIRMAS MĖN. PIRMADIENIS     Imbrado sen. Avilių mstl., ... Dusetų sen. Antazavės mstl., ...

It is transcribed in pipeline/data/rules-zarasu-r.json (RULES_FILE) with the scan's address and
SHA-256. Every day the build downloads the scan the page links and compares its hash. While it is
the same, the rules become dates (Rule, with svara.Rule's nth weekday of the month) from
`--keep-days` ago to HORIZON_DAYS ahead: rules don't end, so mixed waste never runs out. If the
scan changed, the build fails ("the published scan changed (new hash …); re-transcribe
pipeline/data/rules-zarasu-r.json") and the workflow keeps yesterday's folder, so
ScheduleDataStale tells the owner to transcribe it again (CONTRIBUTING.md). The scan says nothing
about holidays: a pickup on a public holiday stays where its rule puts it.

**Packaging and glass** are one table of six schedules ("1 grafikas" to "6 grafikas"), each a
row of a day a month for packaging (the blue containers) and one for glass (the green ones, "-"
for none that month), and its addresses ("Zarasų miestas: Aukštaičių g., ... Kaimai: Dimitriškių
k., ..."). A file a year, made in December (the 2026 one on 29 December 2025).

Both companies are one provider, the publisher, as for Širvintų r.: the app takes a settlement's
schedules from one location, so two providers can't share the municipality's settlements. A
changed scan therefore holds back a new packaging file too, until the scan is transcribed again.

The places are read by Routes (aratc.Routes, as utena.Routes): in the rules, a village with its
streets ("Užtiltės k. Vasaknų g. 12, 14, ...": some houses, one more choice for that street next
to the village's other route), and the streets of the eldership's town (Zarasai, Dusetos): the
town's routes list the streets of its private houses, a street with some of its houses
("Aušros g. 7, 8, 10, ...", "Vilniaus g. nuo Salos g. iki Vytauto g. sankryžos") being that
street, as sirvintos.Routes reads Širvintos'. No street gets "no pickup": the shared containers
of apartment buildings have a file of their own, and a street no route names is left to the
app, which offers the town's routes.

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.zarasai --out ../site/zarasu-r
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import NamedTuple
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot, svara
from .dates import WEEKDAY_NAMES, month_end
from .locations import _SECTION_ITEM, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Settlement, fold

PAGE_URL = "https://www.zarasai.lt/veiklos-sritys/aplinkos-apsauga/atlieku-tvarkymas/269"
PUBLISHER = "Zarasų rajono savivaldybė"
LABEL = "Zarasų r."
# The elderships of the municipality (register names); Zarasai is in Zarasų sen., Dusetos in
# Dusetų sen.
ELDERSHIPS = frozenset({"Dusetų", "Imbrado", "Salako", "Turmanto", "Zarasų"})
# The transcription of the mixed waste scan.
RULES_FILE = snapshot.DATA_DIR / "rules-zarasu-r.json"
RULES_PATH = "pipeline/data/rules-zarasu-r.json"
# The rules' dates are calculated this far ahead (about 13 months), from `--keep-days` ago.
HORIZON_DAYS = 400
# The rows of the page's table that are read, by the start of their first cell (folded).
ROWS: dict[str, Kind] = {"komunalines atliekos": "household", "antrines zaliavos": "packaging"}


# --- the rules -------------------------------------------------------------------

# "1-ą", ..., "4-ą" and "paskutinį" (the last) of "1-ą ir 3-ą mėnesio antradienį"; "PIRMAS" to
# "TREČIAS" of "PIRMAS MĖN. PIRMADIENIS" (folded to lower case). -1: the last of the month.
_WEEKS_ACCUSATIVE = {"paskutinį": -1} | {f"{n}-ą": n for n in range(1, 6)}
_WEEKS_NOMINATIVE = {
    "pirmas": 1,
    "antras": 2,
    "trečias": 3,
    "ketvirtas": 4,
    "penktas": 5,
    "paskutinis": -1,
}
_WEEKDAYS_NOMINATIVE = {name.casefold(): n for n, name in enumerate(WEEKDAY_NAMES)}
_RULE = re.compile(r"(?P<weeks>.+?)\s+(?:mėnesio|mėn\.)\s+(?P<day>\w+)")


@dataclass(frozen=True)
class Rule:
    """Mixed waste on the `weeks`-th `weekday` (0 = Monday) of every month; -1 is the last."""

    weekday: int
    weeks: tuple[int, ...]

    def dates(self, start: date, end: date) -> set[date]:
        """The pickups from `start` to `end`, by svara.Rule's nth weekday of the month."""
        return {
            day
            for week in self.weeks
            for day in svara.Schedule(
                "household", svara.Rule(0, weekdays=(self.weekday,), nth=week), 0, ""
            ).dates(start, end)
        }


def parse_rule(text: str) -> Rule | None:
    """Understands "2-ą ir paskutinį mėnesio pirmadienį" (the second and the last Monday of the
    month), "Paskutinį mėn. trečiadienį", "1-ą i 3-ą mėnesio ketvirtadienį" ("i" for "ir", as the
    scan has it) and "PIRMAS MĖN. PIRMADIENIS" (the first Monday). None for anything else."""
    found = _RULE.fullmatch(clean_text(text).casefold())
    if not found:
        return None
    words = re.split(r"\s+(?:ir|i)\s+", found["weeks"])
    if (weekday := svara.WEEKDAYS.get(found["day"])) is not None:
        weeks = [_WEEKS_ACCUSATIVE.get(w) for w in words]
    elif (weekday := _WEEKDAYS_NOMINATIVE.get(found["day"])) is not None:
        weeks = [_WEEKS_NOMINATIVE.get(w) for w in words]
    else:
        return None
    if None in weeks or len(set(weeks)) != len(weeks):
        return None
    return Rule(weekday, tuple(weeks))


# --- the rules' places -----------------------------------------------------------

_UPPER = "A-ZĄČĘĖĮŠŲŪŽ"
_WORD = rf"[{_UPPER}][\wąčęėįšųūž-]*"
# A settlement: "Padustėlio k.", "Apkartų I k.", "Avilių mstl.", "Veselavos k" (without its dot),
# and what follows it in the same place: its street, its houses, or a place after a missing
# comma ("Kartašovkos vs. Suvieko k.").
_PLACE = re.compile(
    rf"(?P<place>{_WORD}(?:\s+{_WORD})?(?:\s+I{{1,3}})?\s+(?:k|vs|mstl|m)\b\.?)(?:\s+(?P<rest>.+))?"
)
# A street: "Šaltupės g.", "K. Būgos g.", "Dariaus ir Girėno g.", "Suvieko kel.", and what follows.
_STREET = re.compile(rf"(?P<street>[{_UPPER}][^,]*?\s(?:g|skg|kel|al|pl|a)\.)(?:\s+(?P<rest>.+))?")
# Some houses: "7, 8, 10, 10A", "nuo 66 nr. iki 70 nr.", "6, 8, 10, 12 nr. ir nuo 17 nr. iki 47
# nr.", "1, 2, 3, 4, 5, 7, 9, 11 ir 15 nr.".
_HOUSE = r"\d+[A-Z]?(?:\s*nr\.)?"
_HOUSES = re.compile(rf"(?:nuo\s+)?{_HOUSE}(?:(?:\s*,\s*|\s+ir\s+(?:nuo\s+)?|\s+iki\s+){_HOUSE})*")
# A part of a street: "nuo Salos g. iki Vytauto g. sankryžos".
_BETWEEN = re.compile(r"nuo\s+[^,]+?\s(?:g|skg)\.\s+iki\s+[^,]+?\s(?:g|skg)\.\s+sankryžos")
# "Kauno g. išskyrus nurodytus ketvirtadienį ir pirmadienį": the street but the houses the
# other routes name.
_EXCEPT = re.compile(r"išskyrus\s+nurodytus\s+\w+(?:\s+ir\s+\w+)*")
# Where the places of a row split: a comma before a capital (house numbers are digits).
_SPLIT = re.compile(rf",\s+(?=[{_UPPER}])")
_SECTIONS = re.compile(rf"\b({'|'.join(sorted(ELDERSHIPS))}) sen\. ")


class _Token(NamedTuple):
    """A settlement ("place") or a street of a rule's places. A street's `houses`: only some of
    its houses; `attached`: written after its settlement without a comma ("Vencavų k. Vencavo
    g. 13")."""

    kind: str
    text: str
    houses: bool = False
    attached: bool = False


def _street(text: str, attached: bool) -> _Token:
    found = _STREET.fullmatch(text)
    rest = found["rest"] if found else None
    if not found or (rest and not any(p.fullmatch(rest) for p in (_HOUSES, _BETWEEN, _EXCEPT))):
        raise ValueError(f"places of no known kind: {text!r}")
    return _Token("street", found["street"], bool(rest) and not _EXCEPT.fullmatch(rest), attached)


def tokens(place: str) -> list[_Token]:
    """The settlements and streets of one place of a rule (rules-zarasu-r.json): "Padustėlio k.
    Vytauto Striogos g. 1, 2, ...", "Likančių k. 1, 2" (houses of a village without streets: the
    village), "Kauno g. nuo 44 nr. iki 90 nr.". Places of no known kind raise ValueError."""
    if found := _PLACE.fullmatch(place):
        settlement = found["place"]
        head = [_Token("place", settlement if settlement.endswith(".") else f"{settlement}.")]
        rest = found["rest"]
        if rest is None or _HOUSES.fullmatch(rest):
            return head
        if _PLACE.fullmatch(rest):
            return head + tokens(rest)
        return [*head, _street(rest, attached=True)]
    return [_street(place, attached=False)]


def sections(name: str) -> list[tuple[str, list[str]]]:
    """The elderships of a rule's row and their places: "Zarasų sen. Šaltupės g. nuo 66 nr. iki
    70 nr., Magutiškių vs., ..." -> [("Zarasų", ["Šaltupės g. nuo 66 nr. iki 70 nr.", ...])]."""
    parts = _SECTIONS.split(name)
    if parts[0].strip() or len(parts) < 3:
        raise ValueError(f"no eldership at the start of {name[:60]!r}")
    pairs = zip(parts[1::2], parts[2::2], strict=True)
    return [(eldership, _SPLIT.split(body.strip())) for eldership, body in pairs]


@dataclass(frozen=True)
class MixedRule:
    """A rule of the transcription: its words, what they mean, and its row's name, its places
    after each eldership ("Zarasų sen. Šaltupės g. nuo 66 nr. iki 70 nr., Magutiškių vs., ...")."""

    text: str
    rule: Rule
    name: str


@dataclass(frozen=True)
class Transcription:
    url: str
    sha256: str
    rules: tuple[MixedRule, ...]


_TOP_KEYS = {"url", "sha256", "title", "approved", "transcribed", "notes", "rules"}
_RULE_KEYS = {"rule", "weekday", "weeks", "places"}


def load_rules(path: Path | None = None) -> Transcription:
    """The transcription of the mixed waste scan. Strict: other keys, a rule in other words or
    whose words aren't its weekday and weeks, an eldership the municipality doesn't have, places
    of no known kind, a place that would be read as two, and two rules of the same places raise
    ValueError."""
    data = json.loads((path or RULES_FILE).read_text(encoding="utf-8"))
    if set(data) - _TOP_KEYS or not re.fullmatch(r"[0-9a-f]{64}", data["sha256"]):
        raise ValueError(f"{RULES_PATH}: keys {sorted(data)}, sha256 {data.get('sha256')!r}")
    rules: list[MixedRule] = []
    for entry in data["rules"]:
        where = f"{RULES_PATH}: {entry.get('rule')!r}"
        if set(entry) != _RULE_KEYS:
            raise ValueError(f"{where}: keys {sorted(entry)}")
        rule = parse_rule(entry["rule"])
        written = Rule(_WEEKDAYS_NOMINATIVE.get(entry["weekday"], -1), tuple(entry["weeks"]))
        if rule is None or rule != written:
            raise ValueError(f"{where}: not {entry['weekday']} of weeks {entry['weeks']}")
        texts: list[str] = []
        seen: set[str] = set()
        for section in entry["places"]:
            eldership, places = section["eldership"], section["places"]
            if set(section) != {"eldership", "places"} or eldership not in ELDERSHIPS:
                raise ValueError(f"{where}: a section of {section}")
            if eldership in seen or not places:
                raise ValueError(f"{where}: {eldership} sen. twice or without places")
            seen.add(eldership)
            for place in places:
                if _SPLIT.search(place) or place != clean_text(place):
                    raise ValueError(f"{where}: {place!r} would be read as two places")
                tokens(place)  # raises for places of no known kind
            texts.append(f"{eldership} sen. {', '.join(places)}")
        rules.append(MixedRule(entry["rule"], rule, " ".join(texts)))
    if len({r.name for r in rules}) != len(rules):
        raise ValueError(f"{RULES_PATH}: two rules of the same places")
    return Transcription(data["url"], data["sha256"], tuple(rules))


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as aratc.Routes reads them.
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "Avilių.mstl." (packaging).
    (re.compile(r"(?<=\w)\.(?=mstl\.)"), " "),
)
# The owner of a street of the eldership's town (Routes._section).
_TOWN = -1
# The packaging schedules' addresses: "Zarasų miestas: Aukštaičių g., ... Kaimai: Dimitriškių
# k., ...", "Kaimai ir miesteliai: Juodalaukių k., ...".
_ADDRESSES = re.compile(
    rf"(?:(?P<town>{_WORD})\s+miestas:\s*(?P<streets>[^:]+?)\s*)?"
    r"(?:Kaimai(?:\s+ir\s+miesteliai)?:\s*(?P<villages>[^:]+))?"
)


class Routes(aratc.Routes):
    """Reads the places of the rows as aratc.Routes reads those of Alytus county, after writing
    them as it reads them (spellings):

        Zarasų sen. Šaltupės g. nuo 66 nr. iki 70 nr., Magutiškių vs., Statybininkų g., ...
          -> Zarasų sen.: Zarasų m. (Šaltupės g., Statybininkų g., ...), Magutiškių vs.
        Dusetų sen. ... Užtiltės k. Vasaknų g. 12, 14, 24, 26, 30, Vasaknų k., ...
          -> Dusetų sen.: ..., Užtiltės k. (Vasaknų g. 0), Vasaknų k., ...
        Zarasų miestas: Aukštaičių g., ... Kaimai: Dimitriškių k., ...
          -> Zarasų m. (Aukštaičių g., ...), Dimitriškių k., ...  (the whole municipality's)

    A street of a rule's places is its settlement's: the one it is written after, with the
    streets after it ("Padustėlio k. Alyvų g., Beržų g., ..."), or the one before it that has
    it ("Didžiadvario k., Pasartės g. 1, 3, 5"), or the one after it that has it ("Kloviškių
    k., Senųjų Baibių g., Baibių k."), else the eldership's town's ("Magutiškių vs.,
    Statybininkų g."). A village with streets is those streets in that route, not the whole
    village, as an address writes a street and its village: Didžiadvaris and Baibiai, named
    whole by other routes, keep those. A village's street with some of its houses is one more
    choice for that street ("0", a house number to aratc.Routes); a town's is the street.

    No street gets "no pickup" (build_locations): the routes list the streets of private
    houses and nothing says a street has none. The app offers the town's routes instead."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()

    def spellings(self, text: str) -> str:
        try:
            if _SECTIONS.match(text):  # a rule's places
                return " ".join(self._section(e, places) for e, places in sections(text))
            return self._addresses(text)  # a packaging schedule's
        except ValueError:
            return text  # reported as places the reader doesn't know

    def _addresses(self, text: str) -> str:
        """A packaging schedule's addresses. They name no elderships: a village of a name
        several elderships have ("Sniegiškių k.") is the one in an eldership of the row's other
        places (Zarasų sen.'s, with Štadviliai and Gružtai), or is reported."""
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        found = _ADDRESSES.fullmatch(text)
        if not found or not (found["streets"] or found["villages"]):
            raise ValueError(text)
        lead = [f"{found['town']} m. ({found['streets']})"] if found["streets"] else []
        villages = _SPLIT.split(found["villages"]) if found["villages"] else []
        named = {v: {s.district for s in self._named(_Token("place", v), "")} for v in villages}
        here = {d for districts in named.values() if len(districts) == 1 for d in districts}
        sections: dict[str, list[str]] = {}
        for village, districts in named.items():
            if len(districts) <= 1:
                lead.append(village)
            elif len(districts & here) == 1:
                sections.setdefault(min(districts & here), []).append(village)
            else:
                self.unknown.append(f"{village} (in {len(districts)} elderships)")
        texts = [", ".join(lead)] + [f"{d} sen.: {', '.join(vs)}" for d, vs in sections.items()]
        return " ".join(t for t in texts if t)

    def _named(self, token: _Token, district: str) -> list[Settlement]:
        found = _SECTION_ITEM.fullmatch(token.text)
        if not found:
            return []
        return self.settlements(*found.group("name", "numerals", "type"), district)

    def _has(self, settlements: list[Settlement], street: str) -> bool:
        found = _SECTION_ITEM.fullmatch(street)
        return bool(found) and any(
            self.streets(s, street, found["name"], found["type"]) for s in settlements
        )

    def _section(self, eldership: str, places: list[str]) -> str:
        """One eldership's places, as aratc.Routes reads them (see the class)."""
        found = [t for place in places for t in tokens(place)]
        named = {i: self._named(t, eldership) for i, t in enumerate(found) if t.kind == "place"}
        town = [
            s
            for s in self.places[self.municipality.label]
            if s.district == eldership and s.abbr == "m."
        ]
        # Each street's settlement, by its index; _TOWN: the town's; None: no one's.
        owners: dict[int, int | None] = {}
        before: int | None = None
        for i, token in enumerate(found):
            if token.kind == "place":
                before = i
                continue
            after = next((j for j in named if j > i), None)
            # "Padustėlio k. Alyvų g., Beržų g., Pušų g., ...": the list of its streets goes on.
            listed = before is not None and owners.get(i - 1, _TOWN) == before
            if token.attached or listed or self._has(named.get(before, []), token.text):
                owners[i] = before
            elif after is not None and self._has(named[after], token.text):
                owners[i] = after
            elif town and self._has(town, token.text):
                owners[i] = _TOWN
            else:
                owners[i] = before  # reported as a street the settlement doesn't have
        streets: dict[int | None, list[str]] = {i: [] for i in [*named, _TOWN, None]}
        for i, owner in owners.items():
            token = found[i]
            village = token.houses and owner not in (_TOWN, None)
            streets[owner].append(f"{token.text} 0" if village else token.text)
        parts = [f"{town[0].genitive} m. ({', '.join(streets[_TOWN])})"] if streets[_TOWN] else []
        for i in named:
            text = found[i].text
            parts.append(f"{text} ({', '.join(streets[i])})" if streets[i] else text)
        return f"{eldership} sen.: {', '.join(parts + streets[None])}"


PROVIDER = Provider(
    id="zarasai",
    name=PUBLISHER,
    url=PAGE_URL,
    elderships=ELDERSHIPS,
    # Names too far from the register's for the reader to tell: Žalioji g. of Zarasai; Bartkiškė
    # I, Turmanto sen.'s only Bartkiškė ("Bartkiškės I k." in the packaging file); Boleslovava,
    # Imbrado sen., by Konecpolis and Meiriškėlės, the places next to it in the scan.
    aliases=(
        ("Žaliosios g.", "Žalioji g."),
        ("Bartkiškių k.", "Bartkiškės I k."),
        ("Boleslavovos k.", "Boleslovavos k."),
    ),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.ZARASAI_MUNICIPALITY,
    snapshot.ZARASAI_REGISTRY_FILE,
    snapshot.ZARASAI_ADDRESSES_FILE,
    # 2026: 26 mixed waste rules, which gave a mixed waste schedule to 297 of the 762
    # settlements (8,188 of the 9,660 addresses: the scan leaves out many small villages), and
    # 6 packaging and glass schedules (66 settlements).
    min_areas={"household": 20, "packaging": 5, "glass": 5},
    min_household_places=250,
    # About 9,700 addresses in 2026, 1,700 of them in Zarasai.
    min_address_points=6_500,
    label=LABEL,
    file_kinds={"household": ("household",), "packaging": ("packaging", "glass")},
)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page, from the day its link names (`since`). The mixed waste scan's rules
    give the dates from `start` to `end`."""

    since: date | None = None
    start: date | None = None
    end: date | None = None


class _Table(HTMLParser):
    """The rows of the page's tables: each cell's text and links (href, text)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, list[tuple[str, str]]]]] = []
        self.cell: list[str] | None = None
        self.links: list[tuple[str, str]] = []
        self.link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th") and self.rows:
            self.cell, self.links = [], []
        elif tag == "a" and self.cell is not None:
            self.link = (dict(attrs).get("href") or "", [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.link is not None:
            self.links.append((self.link[0], clean_text("".join(self.link[1]))))
            self.link = None
        elif tag in ("td", "th") and self.cell is not None:
            self.rows[-1].append((clean_text("".join(self.cell)), self.links))
            self.cell = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)
        if self.link is not None:
            self.link[1].append(data)


def find_files(html: str, page_url: str = PAGE_URL) -> list[ScheduleFile]:
    """The PDFs of the rows of mixed waste ("Komunalinės atliekos") and of packaging ("Antrinės
    žaliavos (stiklas, plastikas, popierius)"), linked by the day they apply from ("Nuo
    2026-01-01"). Strict: such a row without a link, or with a link of other words or to
    another kind of file, raises ValueError."""
    table = _Table()
    table.feed(html)
    files: list[ScheduleFile] = []
    for row in table.rows:
        label = fold(row[0][0]) if row else ""
        kind = next((k for words, k in ROWS.items() if label.startswith(words)), None)
        if kind is None:
            continue
        links = row[1][1] if len(row) > 1 else []
        if not links:
            raise ValueError(f"the row {row[0][0]!r} links no schedule")
        for href, text in links:
            since = re.fullmatch(r"Nuo (\d{4}-\d{2}-\d{2})", text)
            url = urljoin(page_url, href)
            name = PurePosixPath(unquote(urlsplit(url).path)).name
            if not since or not name.lower().endswith(".pdf"):
                raise ValueError(f"the row {row[0][0]!r} links {text!r}: {url}")
            files.append(ScheduleFile(kind, url, name, since=date.fromisoformat(since[1])))
    return files


def select_files(files: list[ScheduleFile], today: date, keep_days: int) -> list[ScheduleFile]:
    """The mixed waste scan, with the window of its rules' dates (from `keep_days` ago, or the
    day its link names, to HORIZON_DAYS ahead), and the packaging files (a year each). A page
    without the scan or with two, or without a packaging file, raises ValidationError."""
    scans = [f for f in files if f.kind == "household"]
    if len(scans) != 1:
        raise build.ValidationError(f"{len(scans)} mixed waste schedules on the page, not 1")
    packaging = [f for f in files if f.kind == "packaging"]
    if not packaging:
        raise build.ValidationError("no packaging schedule on the page")
    (scan,) = scans
    start = max(scan.since or today, today - timedelta(days=keep_days))
    return [replace(scan, start=start, end=today + timedelta(days=HORIZON_DAYS)), *packaging]


def download(today: date, keep_days: int) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files = select_files(find_files(html), today, keep_days)
    return [(f, http.get(f.url, timeout=60)) for f in files], []


# --- the files -------------------------------------------------------------------


def parse_mixed(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of the transcription (load_rules), a row per rule with its dates from
    `source.start` to `source.end`, while the scan is the one transcribed: one with another
    hash raises ValidationError."""
    rules = load_rules()
    digest = hashlib.sha256(content).hexdigest()
    if digest != rules.sha256:
        raise build.ValidationError(
            f"the published scan changed (new hash {digest}); re-transcribe {RULES_PATH}"
        )
    start, end = getattr(source, "start", None), getattr(source, "end", None)
    if start is None or end is None:
        raise ValueError(f"{source.file_name}: no window for the rules' dates")
    warnings = []
    if source.url != rules.url:
        warnings.append(f"{source.file_name}: the scan transcribed from {rules.url}, now here")
    areas = [
        Area(
            "household",
            rule.name,
            LABEL,
            weekday=WEEKDAY_NAMES[rule.rule.weekday],
            dates=rule.rule.dates(start, end),
            provider=PROVIDER.id,
        )
        for rule in rules.rules
    ]
    return ParseResult(areas, warnings)


# "Pakuočių ir antrinių žaliavų išvežimo iš individualių valdų GRAFIKAS 2026 M." (folded).
_TITLE = re.compile(
    r"pakuociu ir antriniu zaliavu isvezimo is individualiu valdu grafikas (?P<year>20\d{2}) m"
)
# The rows of a schedule (folded first cells), and of its two kinds.
_HEADING = re.compile(r"(?P<number>\d+) grafikas")
_KINDS: dict[str, Kind] = {
    "melynas konteineris pakuociu popieriaus plastiko ir metalo atliekoms": "packaging",
    "zalias konteineris stiklo atliekoms": "glass",
}


@dataclass
class _Schedule:
    number: int
    dates: dict[Kind, set[date]] = field(default_factory=dict)
    addresses: str = ""


def _days(cells: list[str | None], kind: Kind, year: int, where: str) -> set[date]:
    """A row of a day a month ("19", "-": none that month; glass only)."""
    if len(cells) != 13 or fold(cells[0] or "") != "diena":
        raise ValueError(f"{where}: a row of days of {cells}")
    dates: set[date] = set()
    for month, cell in enumerate(cells[1:], start=1):
        if cell == "-" and kind == "glass":
            continue
        if not cell or not cell.isdigit() or not 1 <= int(cell) <= month_end(year, month).day:
            raise ValueError(f"{where}: not a day of {year}-{month:02}: {cell!r}")
        dates.add(date(year, month, int(cell)))
    return dates


def _schedules(rows: list[list[str | None]], year: int, where: str) -> list[_Schedule]:
    """The schedules of the file's tables. Strict: a row of other words, months out of order, a
    day the month doesn't have, a schedule without packaging, glass or addresses, and numbers out
    of order raise ValueError."""
    found: list[_Schedule] = []
    kind: Kind | None = None
    expect = "heading"
    for cells in rows:
        first = fold(cells[0] or "")
        rest = [c for c in cells[1:] if c]
        if not first and not rest:
            continue  # the empty row between two schedules
        heading = _HEADING.fullmatch(first)
        if heading and expect == "heading":
            if int(heading["number"]) != len(found) + 1:
                raise ValueError(f"{where}: {cells[0]!r} after {len(found)} schedules")
            found.append(_Schedule(len(found) + 1))
            first, rest, expect = fold(rest[0]) if len(rest) == 1 else "", [], "kind"
        # Packaging, then glass.
        wanted = "glass" if found and found[-1].dates else "packaging"
        if expect == "kind" and _KINDS.get(first) == wanted and not rest:
            kind, expect = _KINDS[first], "months"
        elif expect == "months" and first == "menuo":
            if [aratc.MONTHS.get(fold(c or "")) for c in cells[1:]] != list(range(1, 13)):
                raise ValueError(f"{where}: months of {cells}")
            expect = "days"
        elif expect == "days" and kind:
            found[-1].dates[kind] = _days(cells, kind, year, where)
            expect = "kind" if kind == "packaging" else "addresses"
        elif expect == "addresses" and first == "adresas" and len(rest) == 1:
            found[-1].addresses = rest[0]
            expect = "heading"
        else:
            raise ValueError(f"{where}: a row of {cells[:3]} (expected {expect})")
    if expect != "heading" or not found:
        raise ValueError(f"{where}: {len(found)} schedules, the last without its {expect}")
    return found


def parse_packaging(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of the packaging file: a packaging and a glass row per schedule, named after its
    addresses. Strict (see _schedules): also a title of another kind, a year other than its
    link's, and addresses of no known form raise ValueError."""
    where = source.file_name
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        title = _TITLE.match(fold(pdf.pages[0].extract_text() or ""))
        if not title:
            raise ValueError(f"{where}: not a packaging schedule of individual houses")
        year = int(title["year"])
        since = getattr(source, "since", None)
        if since and since.year != year:
            raise ValueError(f"{where}: a schedule of {year}, its link says from {since}")
        rows = [
            [clean_text(c) if c is not None else None for c in row]
            for page in pdf.pages
            for table in page.find_tables()
            for row in table.extract()
        ]
    areas: list[Area] = []
    for schedule in _schedules(rows, year, where):
        name = clean_text(schedule.addresses)
        found = _ADDRESSES.fullmatch(name)
        if not found or not (found["streets"] or found["villages"]):
            raise ValueError(f"{where}: addresses of no known form: {name[:60]!r}")
        for kind, dates in schedule.dates.items():
            area = Area(kind, name, LABEL, dates=dates, provider=PROVIDER.id)
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            if any(a.id == area.id for a in areas):
                raise ValueError(f"{where}: two {kind} schedules of {name[:60]!r}")
            areas.append(area)
    return ParseResult(areas)


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The rows of the mixed waste scan (its transcription) or of a packaging file."""
    return (parse_mixed if source.kind == "household" else parse_packaging)(source, content)


# --- the source ------------------------------------------------------------------

SOURCE = build.Source(
    PROVIDER,
    download,
    parse_file,
    MUNICIPALITY.min_areas,
    MUNICIPALITY.min_household_places,
    MUNICIPALITY.file_kinds,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="directory for the output files")
    parser.add_argument(
        "--keep-days", type=int, default=31, help="drop pickup dates older than this many days"
    )
    args = parser.parse_args(argv)
    # The folder of one provider, as raseiniai.py builds its own. Without published data to
    # fall back on: a build that fails (a changed scan) writes nothing, and the workflow keeps
    # yesterday's folder.
    return raseiniai.run(args.out, args.keep_days, None, MUNICIPALITY, lambda _: SOURCE)


if __name__ == "__main__":
    raise SystemExit(main())

"""Anykščių rajonas: the schedules of UAB „Anykščių komunalinis ūkis“ (anykom.lt), which empties
the containers of the individual houses of the municipality: mixed waste, packaging and glass,
and in Anykščiai also biodegradable (green) waste.

Its page links two PDFs a year, made in Word: "MIŠRIŲ IR ANTRINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026
M." for the villages and small towns, and "MIŠRIŲ, ANTRINIŲ IR BIOLOGINIŲ ATLIEKŲ IŠVEŽIMO
GRAFIKAS 2026 M." "(Anykščių miestas)" for the town. The files are found by these texts and the
year in them. A file may be revised in its year (the villages' 2026 file of 31 December 2025 was
replaced on 30 March 2026, with other dates for Gyliai): the link keeps its text and the file its
name, but the new file is in the folder of the month it was uploaded in
(".../assets/uploads/2026/03/421f0ee1.pdf", the first one in ".../2025/12/421f0ee1-2.pdf"). Of
two files of one year, the one uploaded last is read, then the one linked last. Bulky waste and
the washing of containers aren't read. A new year's files are expected in December.

A file is a block per route:

    1. Vėjeliškis, Piktagalys,            Mišrių ir antrinių atliekų išvežimo grafikas 2026 m.
    Naujonys, Zablackai                   sausis vasaris kovas ... gruodis
    MIŠRIŲ atliekų konteineris            8      5       5     ... 3
    PAKUOTĖS atliekų konteineris (su
    mėlynu dangčiu) arba MĖLYNOS          8      5       5     ... 3
    spalvos maišas
    STIKLO pakuotės konteineris (su žaliu         5            4   ...    3
    dangčiu) arba ŽALIOS spalvos maišas

and the town's two also a row "BIOLOGINIŲ atliekų konteineris". The blocks are read from the
positions of the words (a day under its month), not with pdfplumber's table finder, which splits
the columns of some routes in two. The places are villages in the nominative, some small towns
and villages in the genitive with their type ("Kavarskas mst.", "Svėdasų mstl.", "Gylių k."), and
the town by the bank of the Šventoji ("Anykščių miestas, DEŠINYSIS UPĖS KRANTAS"). No file lists
streets: the town's two routes are for all of it, and the app asks which bank. The heading "kas
antrą savaitę" over the town's routes was there in 2025, when mixed waste was collected every
other week; the 2026 dates are once a month (twice in January), and are read as they are.

Next year's file continues this year's routes that cover the same places (raseiniai.combine). A
file that can't be downloaded or read keeps its rows of yesterday's data, and the other file is
still updated (as raseiniai.py does).

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.anyksciai --out ../site/anyksciu-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot
from .dates import WEEKDAY_NAMES
from .locations import Clause, Index
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Settlement, fold

PAGE_URL = "https://anykom.lt/paslaugos/komunaliniu-atlieku-tvarkymas/"
# Yesterday's data, for the files that can't be read today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/anyksciu-r"
COMPANY = "UAB „Anykščių komunalinis ūkis“"
LABEL = "Anykščių r."
# The town's file (`SourceFile.group`); the villages' file has none.
TOWN = "Anykščių miestas"
# The waste types of each file.
KINDS: dict[str, tuple[Kind, ...]] = {
    "": ("household", "packaging", "glass"),
    TOWN: ("household", "packaging", "glass", "green"),
}
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {"household": KINDS[TOWN]}
# Of a route's mixed waste dates, at least this share falls on one or two weekdays (Kavarskas
# had Thursdays and Mondays in 2025), and few on weekends: the right year and months (holidays
# move a few).
SAME_WEEKDAY = 0.75


# --- the places ------------------------------------------------------------------

# The publisher's spellings, as aratc.Routes reads them (Routes.spellings).
_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "I Svirnai", "II Kurkliai": the register's Svirnai I, Kurkliai II.
    (re.compile(r"\b(I{1,3})\s+([A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž-]+)"), r"\2 \1"),
    # "Anykščių miestas, DEŠINYSIS UPĖS KRANTAS": the whole town. The bank tells the town's two
    # routes apart: the app asks.
    (re.compile(r",?\s*\b(?:DEŠINYSIS|KAIRYSIS)\s+UPĖS\s+KRANTAS\b", re.I), ""),
)
_TOWNS = ("m.", "mstl.")


@dataclass
class _Read:
    """What the lookups of one row found, in the row's order, and the settlements a name may
    only mean."""

    lookups: list[list[Settlement]] = field(default_factory=list)
    loose: set[int] = field(default_factory=set)
    sure: set[int] = field(default_factory=set)


class Routes(aratc.Routes):
    """Reads the places of a route, as aratc.Routes reads a list of places of a municipality
    without elderships' sections ("Vėjeliškis, Piktagalys, ...", "Kavarskas mst.", "Gylių k.",
    "Anykščių miestas"), looked up in the whole municipality, with three rules of its own:

    - Of a name several elderships have (Pienionys, Katlėriai, Vikonys, ...), the one of the
      eldership of the nearest places before or after it in the list that are of one of them
      ("Pienionys, Jokūbava, Ažuožeriai": Ažuožeriai is of Anykščių sen., so are that Pienionys
      and Jokūbava; "Mackeliškiai, Pienionys": of Kavarsko sen.), else of most of the row; if
      none, all of them, as fallbacks.
    - A name without its type that a town and a village have ("Kavarskas", "Viešintos",
      "Kurkliai") means the village, and the town only as a fallback: the town's route is the
      one that names it with its type ("Kavarskas mst.").
    - A name without a numeral ("Kurkliai") also means the numbered villages of that name
      (Kurkliai I and II), as fallbacks: a route that names one ("II Kurkliai") is its route.

    No town gets "no pickup" for a street no route names (build_locations): no file lists
    streets."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()
        self.read: _Read | None = None

    def spellings(self, text: str) -> str:
        for pattern, replacement in _FIXES:
            text = pattern.sub(replacement, text)
        return text

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        hits = super().settlements(name, numerals, kind, district)
        if self.read is None or district:
            return hits
        loose: set[int] = set()
        if not kind and {s.abbr in _TOWNS for s in hits} == {True, False}:
            loose |= {s.code for s in hits if s.abbr in _TOWNS}
        if not numerals and hits:
            key = re.escape(fold(name))
            codes = {s.code for s in hits}
            numbered = [
                s
                for s in self.places[self.municipality.label]
                if re.fullmatch(key + r" i{1,3}", fold(s.name)) and s.code not in codes
            ]
            loose |= {s.code for s in numbered}
            hits = hits + numbered
        self.read.loose |= loose
        self.read.sure |= {s.code for s in hits} - loose
        self.read.lookups.append(hits)
        return hits

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.read = _Read()
        try:
            found, skipped = super().clauses(area)
            read = self.read
        finally:
            self.read = None
        codes = {s.code for s, _ in found}
        # The eldership of each place of the row that is of one, in the row's order (None for
        # the others); and of most of them.
        sure = [
            hits[0].district
            if len({s.district for s in hits}) == 1 and hits[0].code in codes
            else None
            for hits in read.lookups
        ]
        most = [d for d, _ in Counter(d for d in sure if d).most_common()]
        dropped: set[int] = set()
        loose = read.loose - read.sure
        for i, hits in enumerate(read.lookups):
            districts = {s.district for s in hits}
            if len(districts) < 2:
                continue
            best = _nearest(sure, i, districts) or next((d for d in most if d in districts), None)
            if best:
                dropped |= {s.code for s in hits if s.district != best}
            else:
                loose |= {s.code for s in hits}
        result = []
        for settlement, clause in found:
            if settlement.code in dropped:
                continue
            if settlement.code in loose:
                clause.fallback = True
            result.append((settlement, clause))
        return result, skipped


def _nearest(elderships: list[str | None], i: int, wanted: set[str]) -> str | None:
    """The eldership of `wanted` of the nearest place before or after the `i`th that has one;
    None if there is none, or the nearest on either side differ."""
    for step in range(1, len(elderships)):
        near = {
            d
            for j in (i - step, i + step)
            if 0 <= j < len(elderships) and (d := elderships[j]) in wanted
        }
        if near:
            return near.pop() if len(near) == 1 else None
    return None


ELDERSHIPS = frozenset(
    {
        "Andrioniškio",
        "Anykščių",
        "Debeikių",
        "Kavarsko",
        "Kurklių",
        "Skiemonių",
        "Svėdasų",
        "Traupio",
        "Troškūnų",
        "Viešintų",
    }
)
PROVIDER = Provider(
    id="anyksciai",
    name=COMPANY,
    url=PAGE_URL,
    # Every eldership of the municipality (register names).
    elderships=ELDERSHIPS,
    aliases=(
        # Other names of places of the register, in the elderships of the places next to them:
        # it has no Senieji Elmininkai ("Old Elmininkai", next to Naujieji Elmininkai), but
        # Elmininkai I and II; no Pavariai (a near name is Padvariai of Svėdasų sen.), but
        # Pavarės I-IV; no Pelyšėliai, but Pelyšėlės I and II; no Kariūnai, but Karūniai.
        ("Senieji Elmininkai", "Elmininkai I ir II"),
        ("Pavariai", "Pavarės I, Pavarės II, Pavarės III, Pavarės IV"),
        ("Pelyšėliai", "Pelyšėlės I ir II"),
        ("Kariūnai", "Karūniai"),
    ),
    kinds=("household", "packaging", "glass", "green"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.ANYKSCIAI_MUNICIPALITY,
    snapshot.ANYKSCIAI_REGISTRY_FILE,
    snapshot.ANYKSCIAI_ADDRESSES_FILE,
    # 2026: 23 routes of the villages and small towns and 2 of the town, each with mixed waste,
    # packaging and glass, which gave a mixed waste schedule to 280 of the 749 settlements
    # (13,038 of the 14,861 addresses).
    min_areas={"household": 20, "packaging": 20, "glass": 20},
    min_household_places=220,
    # About 14,900 addresses in 2026.
    min_address_points=10_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page; `group` is TOWN for the town's file, "" for the villages', so each
    runs out on its own (build.current_rows)."""

    year: int | None = None
    # The month it was uploaded in, from its folder ("assets/uploads/2026/03/"): of two files of
    # one year, the later one is a revision.
    uploaded: tuple[int, int] = (0, 0)


class _Links(HTMLParser):
    """The page's links, with their texts and the text of their paragraphs."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []  # (href, text, paragraph)
        self.open: list[tuple[str, list[str]]] = []  # links of the paragraph being read
        self.paragraph: list[str] | None = None
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self.close()
            self.paragraph, self.open = [], []
        elif tag == "a":
            self.href, self.text = dict(attrs).get("href") or "", []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            if self.paragraph is None:
                self.links.append((self.href, clean_text("".join(self.text)), ""))
            else:
                self.open.append((self.href, self.text))
            self.href = None
        elif tag == "p":
            self.close()

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.text.append(data)
        if self.paragraph is not None:
            self.paragraph.append(data)

    def close(self) -> None:
        paragraph = clean_text("".join(self.paragraph or []))
        for href, text in self.open:
            self.links.append((href, clean_text("".join(text)), paragraph))
        self.open, self.paragraph = [], None


# "MIŠRIŲ IR ANTRINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 M.", "MIŠRIŲ, ANTRINIŲ IR BIOLOGINIŲ
# ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 M." (folded).
_LINK = re.compile(r"\bmisriu\b.*\bisvezimo grafikas (20\d{2}) m\b")
_UPLOADED = re.compile(r"/uploads/(20\d{2})/(\d{2})/")


def find_files(html: str, page_url: str = PAGE_URL) -> list[ScheduleFile]:
    """The PDFs of mixed waste by the texts of their links: the town's says "(Anykščių
    miestas)" after it, and names biodegradable waste. Not bulky waste, the washing of
    containers, nor links without a text of a schedule ("1. " linked an older file in 2025)."""
    collector = _Links()
    collector.feed(html)
    collector.close()
    files: list[ScheduleFile] = []
    for href, text, paragraph in collector.links:
        url = urljoin(page_url, href)
        path = unquote(urlsplit(url).path)
        match = _LINK.search(fold(text))
        if not path.lower().endswith(".pdf") or not match or any(f.url == url for f in files):
            continue
        town = "biologin" in fold(text) or fold(TOWN) in fold(paragraph)
        uploaded = _UPLOADED.search(path)
        files.append(
            ScheduleFile(
                kind="household",
                url=url,
                file_name=PurePosixPath(path).name,
                group=TOWN if town else "",
                year=int(match[1]),
                uploaded=(int(uploaded[1]), int(uploaded[2])) if uploaded else (0, 0),
            )
        )
    return files


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Of the town's files and the villages', those of this year and later; if there are none,
    the newest. Of two for one year, the one uploaded last (a revision), else the one linked
    last. Both must have a file."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    for group in KINDS:
        mine = [f for f in files if f.group == group]
        if not mine:
            raise build.ValidationError(f"no schedule of {group or 'the villages'} on the page")
        running = [f for f in mine if f.year >= today.year] or [
            f for f in mine if f.year == max(g.year for g in mine)
        ]
        if today.year not in {f.year for f in running}:
            warnings.append(f"{group or 'the villages'}: no schedule for {today.year} on the page")
        for year in sorted({f.year for f in running}):
            same = [f for f in running if f.year == year]
            newest = max(reversed(same), key=lambda f: f.uploaded)
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer schedule for {year}"
                for f in same
                if f is not newest
            ]
            selected.append(newest)
    return selected, warnings


def download(
    today: date, keep_days: int, tolerant: bool = False
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files in force. `tolerant`: a file that can't be downloaded is passed on empty, and
    keeps its rows of yesterday's data (parse_or_keep)."""
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    selected, warnings = select_files(find_files(html), today)
    sources: list[tuple[SourceFile, bytes]] = []
    for file in selected:
        try:
            sources.append((file, http.get(file.url, timeout=60)))
        except OSError as error:
            if not tolerant:
                raise
            warnings.append(f"{file.file_name}: couldn't be downloaded ({error})")
            sources.append((file, b""))
    return sources, warnings


# --- the blocks ------------------------------------------------------------------

# A route's number before its places: "1.", "20.", "5.Keblonys" (2025).
_NUMBER = re.compile(r"\d{1,2}\.(?!\d)\s*")
# The days of a month: "8", "8,22", "2,30".
_DAYS = re.compile(r"\d{1,2}(?:,\d{1,2})*")
# The first word of a row's label (folded), and its waste type.
_LABELS: dict[str, Kind] = {
    "misriu": "household",
    "pakuotes": "packaging",
    "stiklo": "glass",
    "biologiniu": "green",
}
# Titles over the blocks (folded): "Mišrių ir antrinių atliekų išvežimo grafikas 2026 m.",
# "Atliekų išvežimo grafikas 2026 m.".
_TITLE = re.compile(r"(?:misriu ir antriniu )?atlieku isvezimo grafikas (20\d{2}) m")
# Lines that aren't read (folded): "kas antrą savaitę" over the town's routes, and the notice
# under every route of the 2025 files ("Išvežimo dieną konteinerį pastatyti ...").
_NOT_READ = re.compile(r"kas antra savaite|isvezimo diena konteineri")


@dataclass
class _Label:
    kind: Kind
    top: float
    bottom: float
    text: list[str]


@dataclass
class _Block:
    """A route: its places, its row of months, its labels and its rows of days."""

    places: list[str]
    where: str
    months: list[float] | None = None  # the centre of each month's word
    labels: list[_Label] = field(default_factory=list)
    rows: list[tuple[float, dict[int, str]]] = field(default_factory=list)  # (middle, days)

    @property
    def name(self) -> str:
        """The places, without the route's number."""
        text = clean_text(" ".join(self.places))
        number = _NUMBER.match(text)
        return text[number.end() if number else 0 :].strip()

    def month(self, x: float) -> int:
        """The month of the column at `x`: the nearest month's word."""
        months = self.months or []
        spacing = (months[-1] - months[0]) / 11
        if not months[0] - spacing / 2 <= x <= months[-1] + spacing / 2:
            raise ValueError(f"{self.where}: a day outside the months, at {x:.0f}")
        return min(range(12), key=lambda i: abs(months[i] - x)) + 1

    def dates(self, year: int) -> dict[Kind, set[date]]:
        """The dates of each waste type: a row of days is the one of the label beside it (the
        days of a label of two or three lines are beside its second or between its lines)."""
        if not self.months or not self.labels:
            raise ValueError(f"{self.where}: no months or labels for {self.name[:60]!r}")
        result: dict[Kind, set[date]] = {}
        for middle, days in self.rows:
            label = min(
                self.labels,
                key=lambda lb: max(lb.top - middle, middle - lb.bottom, 0),
            )
            if label.kind in result:
                raise ValueError(f"{self.where}: two rows of {label.kind} for {self.name[:60]!r}")
            dates: set[date] = set()
            for month, text in days.items():
                for day in text.split(","):
                    try:
                        dates.add(date(year, month, int(day)))
                    except ValueError as error:
                        raise ValueError(
                            f"{self.where}: month {month} of {year} has no day {day}"
                        ) from error
            result[label.kind] = dates
        for label in self.labels:
            if label.kind not in result:
                result[label.kind] = set()
        return result


def _months(line: raseiniai._Line, where: str) -> list[dict] | None:
    """The words of a row of months ("sausis vasaris ... gruodis"). Months out of order raise
    ValueError."""
    found = [w for w in line.words if fold(w["text"]) in aratc.MONTHS]
    if len(found) < 6:
        return None
    if [aratc.MONTHS[fold(w["text"])] for w in found] != list(range(1, 13)):
        raise ValueError(f"{where}: months {[w['text'] for w in found]}")
    return found


def _blocks(pdf, name: str) -> tuple[str, set[int], list[_Block]]:
    """The heading of a file (the lines above its first route), the years of its titles and its
    routes. Strict: words right of the labels that aren't days, months or a title, days before a
    route's months, a page without months and a file without a route raise ValueError."""
    heading: list[str] = []
    years: set[int] = set()
    blocks: list[_Block] = []
    block: _Block | None = None
    for page in pdf.pages:
        where = f"{name} page {page.page_number}"
        lines = raseiniai._lines(page)
        rows = [m for line in lines if (m := _months(line, where))]
        if not rows:
            raise ValueError(f"{where}: no months")
        # Left of the first month: the places and the labels.
        split = min(m[0]["x0"] for m in rows) - 2
        for line in lines:
            text = clean_text(line.text)
            if not blocks and not _NUMBER.match(line.words[0]["text"]):
                heading.append(text)
                continue
            if _NOT_READ.search(fold(text)):
                continue
            left = [w for w in line.words if w["x1"] < split]
            right = [w for w in line.words if w["x1"] >= split]
            if left:
                words = clean_text(" ".join(w["text"] for w in left))
                first = left[0]["text"]
                if _NUMBER.match(first):
                    block = _Block([words], where)
                    blocks.append(block)
                elif block is None:
                    raise ValueError(f"{where}: {words[:60]!r} before the first route")
                elif (kind := _LABELS.get(fold(first))) and first.isupper():
                    block.labels.append(_Label(kind, line.top, line.bottom, [words]))
                elif block.labels:
                    block.labels[-1].text.append(words)
                    block.labels[-1].bottom = line.bottom
                else:
                    block.places.append(words)
            if not right:
                continue
            if months := _months(line, where):
                if block is None or block.months:
                    raise ValueError(f"{where}: months without a route above them")
                block.months = [(w["x0"] + w["x1"]) / 2 for w in months]
                continue
            texts = [w["text"] for w in right]
            if title := _TITLE.fullmatch(fold(" ".join(texts))):
                years.add(int(title[1]))
                continue
            if not all(_DAYS.fullmatch(t) for t in texts):
                raise ValueError(f"{where}: not days: {' '.join(texts)[:60]!r}")
            if block is None or not block.months:
                raise ValueError(f"{where}: days before the months")
            days: dict[int, list[str]] = defaultdict(list)
            for word in right:
                days[block.month((word["x0"] + word["x1"]) / 2)].append(word["text"])
            block.rows.append((line.middle, {m: ",".join(t) for m, t in days.items()}))
    if not blocks:
        raise ValueError(f"{name}: no route found")
    return clean_text(" ".join(heading)), years, blocks


def _years(text: str) -> set[int]:
    return {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The schedules of a file's routes: one per waste type of a route, named after its places
    ("Vėjeliškis, Piktagalys, Naujonys, Zablackai"). Strict (see _blocks): also a heading of
    another year than the link's or of the other file, a waste type the file doesn't have, a
    route without mixed waste or listed twice, and mixed waste dates that mostly miss one working
    day (the wrong year or months) raise ValueError."""
    where = source.file_name
    if not content:
        raise ValueError(f"{where}: not downloaded")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        heading, years, blocks = _blocks(pdf, where)
    linked = getattr(source, "year", None)
    years |= _years(heading)
    if not linked or years != {linked}:
        raise ValueError(f"{where}: a schedule of {sorted(years)}, its link says {linked}")
    town = fold(f"({TOWN})") in fold(heading)
    if town != (source.group == TOWN):
        raise ValueError(f"{where}: {heading[:80]!r} isn't the file its link says")
    allowed = KINDS[source.group]
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for block in blocks:
        name = block.name
        if not name:
            raise ValueError(f"{block.where}: a route without places")
        for kind, dates in sorted(block.dates(linked).items()):
            if kind not in allowed:
                raise ValueError(f"{block.where}: {kind} in the file of {source.group or LABEL}")
            if not dates:
                warnings.append(f"{block.where}: no {kind} dates for {name[:60]!r}")
                continue
            weekdays = Counter(d.weekday() for d in dates)
            usual = sum(times for _, times in weekdays.most_common(2))
            weekend = weekdays[5] + weekdays[6]
            if kind == "household" and (
                usual < SAME_WEEKDAY * len(dates) or weekend > 0.1 * len(dates)
            ):
                raise ValueError(
                    f"{block.where}: the mixed waste dates of {name[:60]!r} aren't on one or two "
                    "working days: the wrong year or months?"
                )
            area = Area(kind, name, district=LABEL, dates=dates, provider=PROVIDER.id)
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[next(iter(weekdays))]
            if area.id in areas:
                raise ValueError(f"{block.where}: {kind} of {name[:60]!r} is listed twice")
            areas[area.id] = area
        if not any(a.kind == "household" and a.name == name for a in areas.values()):
            raise ValueError(f"{block.where}: no mixed waste for {name[:60]!r}")
    return ParseResult(areas=list(areas.values()), warnings=warnings)


def parse_or_keep(
    source: SourceFile, content: bytes, published: Callable[[], dict] | None = None
) -> ParseResult:
    """parse_file, or for a file that can't be read, its rows of yesterday's data (`published`;
    None: raise instead): the town's or the villages'."""
    try:
        return parse_file(source, content)
    except Exception as error:  # any failure of one file must not stop the other
        if published is None:
            raise
        town = source.group == TOWN

        def mine(row: dict) -> bool:
            return row["name"].startswith(TOWN) == town

        kept = build.published_rows(published(), PROVIDER, mine)
        if not kept:
            raise
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} rows of {source.group or 'the villages'} are kept"
            ],
        )


# --- the source ------------------------------------------------------------------


def source(published: Callable[[], dict] | None = None) -> build.Source:
    """`published`: yesterday's data, for the files that can't be read (None: fail instead).
    Next year's file continues this year's routes as raseiniai.combine joins Raseinių r.'s, the
    town's and the villages' on their own."""
    return build.Source(
        PROVIDER,
        partial(download, tolerant=published is not None),
        partial(parse_or_keep, published=published),
        MUNICIPALITY.min_areas,
        MUNICIPALITY.min_household_places,
        MUNICIPALITY.file_kinds,
        partial(raseiniai.combine, municipality=MUNICIPALITY),
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
        help="site folder with yesterday's schedule.json, for the files that can't be read",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail if any file can't be read instead of keeping its published rows",
    )
    args = parser.parse_args(argv)
    published = None if args.strict else args.published
    # The folder of one provider, as raseiniai.py builds its own.
    return raseiniai.run(args.out, args.keep_days, published, MUNICIPALITY, source)


if __name__ == "__main__":
    raise SystemExit(main())

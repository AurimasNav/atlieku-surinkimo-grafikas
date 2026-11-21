"""Molėtų rajonas: the schedules of UAB „Molėtų švara“ (moletusvara.lt), which empties the
containers of the whole municipality: mixed waste, packaging and glass, and the town's green
waste.

Its page has a section per eldership and one for the town ("ALANTOS SENIŪNIJA", "MOLĖTŲ
MIESTAS"), each with a one-page PDF ("2026 m. Molėtų r. Alantos sen. komunalinių atliekų
surinkimo grafikas", "2026 m. Molėtų miesto komunalinių atliekų surinkimo grafikai"). The files are
found by these texts and the year in them; each file's title names its eldership and year
("MOLĖTŲ R. ALANTOS SEN. KOMUNALINIŲ ATLIEKŲ SURINKIMO GRAFIKAS", "2026 m. Individualūs ir bendri
konteineriai"), which must agree. The section of the shared containers of apartment buildings and
businesses has no file yet and isn't read, nor are the extra pickups businesses order. A new
year's files are expected in December.

A file is one table, read with pdfplumber's table finder:

    Gyvenvietė                         | Atliekų rūšys | Sausis | ... | Balandis | ... | Gruodis
    Mišrios komunalinės atliekos
    Pagrindinės gyvenvietės: Alanta    | Mišrios kom.  | 13     | ... | 14 / 24  | ... | 8
    Alanta ir seniūnijos kaimai:       | Mišrios kom.  | 13     | ... | 14       | ... | 8
      Adomiškėlis, ..., Žygeliškis ir kiti...
    Užsakomieji papildomi aptarnavimai | Mišrios kom.  | -      | ... | 13 / 20 / 27 | ... | -
    Rūšiuotos atliekos (pakuotės)
    Alanta ir seniūnijos kaimai: ...   | Plastikas ... | 23     | ... | 24       | ... | 30
                                       | Stiklas       | 23     | ... | 24       | ... | -

The main settlements ("Pagrindinės gyvenvietės") have mixed waste twice a month from April to
September, the eldership's villages once a month on the first of those days: the settlements the
villages' row names first ("Alanta ir seniūnijos kaimai") take the main settlements' row, which
parse_file checks has every date of the villages' row. "... ir kiti" is every other village of the
eldership, a fallback to the rows that name a village; Luokesos sen.'s file is also for part of
Giedraičių sen. ("MOLĖTŲ R. LUOKESOS SEN. IR DALIES GIEDRAIČIŲ SEN. ...", "Luokesa, ... ir
seniūnijų kaimai"), so a village of Giedraičių sen. that neither file names gets both, and the app
asks. The town's file lists the streets of its individual houses in three routes, some streets
in part ("Vilniaus g. (iki 79 nr.)": one more choice for that street), and four villages around
the town, of Luokesos sen. ("Ažubalių k."); its green waste row is the whole town ("Molėtų
miestas"). A town street no route names is left to the app.

A notice the page has next to a file is checked if it is the one it had in 2026 ("ATKREIPIAME
DĖMESĮ, KAD PAANKSTINAMAS KIEKVIENO MĖNESIO PIRMAS ATLIEKŲ RINKIMAS (perkeliamas iš ketvirtadienio
į antradienį)": the file's first mixed waste pickup of each month must be on a Tuesday), and
reported otherwise.

The places are read by aratc.Routes. Next year's file of an eldership continues this year's
routes if they cover the same places (raseiniai.combine). A file that can't be downloaded or read
keeps its rows of yesterday's data, and the other files are still updated (as raseiniai.py does).

Writes <out>/schedule.json and <out>/addresses.json in the format of the Vilniaus r. files.
Run: python -m schedule_pipeline.moletai --out ../site/moletu-r
"""

from __future__ import annotations

import argparse
import io
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

import pdfplumber

from . import aratc, build, http, maatc, raseiniai, snapshot, tratc
from .dates import WEEKDAY_NAMES, parse_weekdays
from .locations import Index, _section_parts, _Stop
from .model import Area, Kind, ParseResult, Provider, SourceFile, clean_text
from .registry import Settlement, fold

PAGE_URL = "https://www.moletusvara.lt/atlieku-surinkimo-grafikai/"
# Yesterday's data, for the files that can't be read today.
PUBLISHED_URL = f"{build.PUBLISHED_URL}/moletu-r"
COMPANY = "UAB „Molėtų švara“"
LABEL = "Molėtų r."
# Molėtai belongs to no eldership in the register: it gets one of its own
# (aratc.town_elderships), as Birštonas and Druskininkai do.
TOWN = "Molėtų miesto"
# The elderships of the municipality (register names), each with a file.
ELDERSHIPS = frozenset(
    {
        "Alantos",
        "Balninkų",
        "Dubingių",
        "Giedraičių",
        "Inturkės",
        "Joniškio",
        "Luokesos",
        "Mindūnų",
        "Suginčių",
        "Videniškių",
        "Čiulėnų",
    }
)
# The eldership around the town, whose villages next to it the town's file lists ("Ažubalių k.",
# "Paluokesos k.", "Svistapolio k.", "Kanapelkos k."): Ažubaliai is also a village of Alantos sen.
SUBURBS = "Luokesos"
FILE_KINDS: dict[Kind, tuple[Kind, ...]] = {
    "household": ("household", "packaging", "glass", "green")
}


# --- the places ------------------------------------------------------------------

# "Pagrindinės gyvenvietės: Alanta": the main settlements of an eldership.
_MAIN = re.compile(r"Pagrindinės\s+gyvenvietės\s*:\s*(?P<places>.+)", re.I)
# "Alanta ir seniūnijos kaimai: Adomiškėlis, ... ir kiti...", "Luokesa, ... ir seniūnijų kaimai:
# ...": these settlements, then the eldership's villages, these and the others.
_VILLAGES = re.compile(
    r"(?P<first>.+?)\s+ir\s+seniūnij(?P<plural>os|ų)\s+kaimai\s*:\s*(?P<places>.+?)"
    r"\s+ir\s+kiti\s*\.*",
    re.I,
)
# A route's elderships before its places: "Alantos sen.:", "Luokesos sen. ir dalies Giedraičių
# sen.:".
_ROUTE = re.compile(
    r"(?P<own>\w+)\s+sen\.(?:\s+ir\s+dalies\s+(?P<part>\w+)\s+sen\.)?\s*:\s*(?P<rest>.*)"
)
# A town street in part: "Vilniaus g. (iki 79 nr.)", "Sporto g. (nuo 8 nr.)": one more choice for
# that street, as a house number tells aratc.Routes.
_SOME_HOUSES = re.compile(r"\b(g|al|skg|pl|tak)\.\s*\(\s*(?:iki|nuo)\s+\d+\s*nr\.?\s*\)", re.I)
_VILLAGE = re.compile(r".+\s(?:k|vs)\.")


def _names(text: str) -> list[str]:
    """The settlements of a list, folded: "Inturkė, Miežonys,Ūta" -> ["inturke", ...]."""
    return [fold(part) for part in re.split(r"\s*,\s*", text) if part.strip()]


class Routes(aratc.Routes):
    """Reads the places of the routes, as aratc.Routes reads those of Alytus county:

        Alantos sen.: Pagrindinės gyvenvietės: Alanta                     the main settlements
        Alantos sen.: Alanta ir seniūnijos kaimai: Adomiškėlis, ... ir kiti...
        Luokesos sen. ir dalies Giedraičių sen.: Luokesa, ... ir seniūnijų kaimai: ... ir kiti...
        Molėtų m.: Alberto Jauniškio g., ..., Ažubalių k., ...           streets of the town
        Molėtų miestas                                                   the whole town

    The villages' row of mixed waste leaves the settlements it names first to the main
    settlements' row (parse_file checks they are in it); its packaging and glass rows are for
    them too. "ir kiti" is the whole eldership, and the part of another the file is also for, a
    fallback to the rows that name a village. A village a route puts in another eldership than
    the register ("Mindūnų sen.: ... Cezariškiai", of Čiulėnų sen.) is the only one of that name,
    if no row of the kind names it in its own.

    No town gets "no pickup" for a street no route names (build_locations): the town's file
    lists the streets of individual houses, the shared containers have no file yet, and nothing
    says a street has none. The app offers the town's routes instead."""

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.municipalities = (MUNICIPALITY,)
        super().__init__(index, provider, variants)
        self.towns_by_street: set[int] = set()
        # The other eldership the row's file is for in part ("ir dalies Giedraičių sen.").
        self.part: str | None = None

    def spellings(self, text: str) -> str:
        """The rows' names written as aratc.Routes reads them (self.kind is the row's)."""
        self.part = None
        text = _SOME_HOUSES.sub(r"\1. 0", text)
        if text.startswith("Molėtų m.:"):
            return f"{TOWN} sen.:{text.removeprefix('Molėtų m.:')}"
        route = _ROUTE.fullmatch(text)
        if not route:
            return text
        self.part = self.district(route["part"]) if route["part"] else None
        elderships = [route["own"], *([route["part"]] if route["part"] else [])]
        places = route["rest"]
        if main := _MAIN.fullmatch(places):
            places = main["places"]
        elif villages := _VILLAGES.fullmatch(places):
            places = villages["places"]
            if self.kind != "household":
                places = f"{villages['first']}, {places}"
            places += "".join(f" Visoje {e} sen." for e in elderships)
        return f"{route['own']} sen.: {places}"

    def prepare(self, areas: list[Area]) -> None:
        """The settlements the rows of each kind name, not as part of a whole eldership: a
        village a row puts in another eldership is still found there, though the rows of its
        own have every village of theirs."""
        named: dict[str, set[int]] = defaultdict(set)
        for area in areas:
            named[area.kind] |= {s.code for s, c in self.clauses(area)[0] if not c.fallback}
        self.named = named

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        """aratc.Routes' settlements; one the route's eldership doesn't have, nor the only one of
        its name elsewhere, is looked up in the eldership the file is also for in part: "Jaurai"
        in Luokesos sen.'s file is Jaurai of Giedraičių sen. (Alantos sen. has one too)."""
        found = super().settlements(name, numerals, kind, district)
        if not found and self.part and district and district != self.part:
            found = super().settlements(name, numerals, kind, self.part)
        return found

    def section(self, district: str, text: str) -> list[_Stop]:
        """aratc.Routes' section; the town's streets are the town's, and the villages its file
        lists are those of Luokesos sen. around it ("Ažubalių k.")."""
        if district != TOWN:
            return super().section(district, text)
        if self.town is aratc._NO_TOWN:
            towns = [s for s in self.places[LABEL] if s.district == TOWN and s.abbr == "m."]
            self.town = towns[0] if len(towns) == 1 else aratc._NO_TOWN
        parts = _section_parts(text)
        villages = [p for p in parts if _VILLAGE.fullmatch(p.strip())]
        streets = [p for p in parts if p not in villages]
        stops = super().section(district, ", ".join(streets))
        return stops + (super().section(SUBURBS, ", ".join(villages)) if villages else [])


PROVIDER = Provider(
    id="moletai",
    name=COMPANY,
    url=PAGE_URL,
    elderships=ELDERSHIPS | {TOWN},
    kinds=("household", "packaging", "glass", "green"),
    reader=Routes,
)
MUNICIPALITY = maatc.Municipality(
    PROVIDER,
    snapshot.MOLETAI_MUNICIPALITY,
    snapshot.MOLETAI_REGISTRY_FILE,
    snapshot.MOLETAI_ADDRESSES_FILE,
    # 2026: 11 elderships with mixed waste of their main settlements and villages, packaging and
    # glass, and the town's 3 routes and its green waste, which gave a mixed waste schedule to
    # every one of the 891 settlements.
    min_areas={"household": 18, "packaging": 10, "glass": 10, "green": 1},
    min_household_places=700,
    # About 16,500 addresses in 2026, 1,750 of them in the town.
    min_address_points=11_000,
    label=LABEL,
    file_kinds=FILE_KINDS,
)


# --- the page ----------------------------------------------------------------


@dataclass
class ScheduleFile(SourceFile):
    """A file of the page; `group` is its eldership (register name, or TOWN), so each
    eldership's file runs out on its own. `notices`: the text next to its link."""

    year: int | None = None
    notices: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _Section:
    heading: str
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, text)
    text: list[str] = field(default_factory=list)  # all but the links'


class _Sections(HTMLParser):
    """The page's sections: a heading ("<a class="accord-toggler">ALANTOS SENIŪNIJA</a>") and
    what its <div class="accord"> holds."""

    def __init__(self) -> None:
        super().__init__()
        self.base: str | None = None
        self.sections: list[_Section] = []
        self.depth = 0  # of <div>s
        self.inside: int | None = None  # the depth of the section's <div class="accord">
        self.heading: list[str] | None = None
        self.href: str | None = None
        self.link: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "base" and attributes.get("href"):
            self.base = attributes["href"]
        elif tag == "div":
            self.depth += 1
            if "accord" in classes and self.sections and self.inside is None:
                self.inside = self.depth
        elif tag == "a" and "accord-toggler" in classes:
            self.heading = []
        elif tag == "a" and self.inside is not None:
            self.href, self.link = attributes.get("href") or "", []
        elif tag in ("br", "p") and self.inside is not None:
            self.sections[-1].text.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            if self.inside == self.depth:
                self.inside = None
            self.depth -= 1
        elif tag == "a" and self.heading is not None:
            self.sections.append(_Section(clean_text("".join(self.heading))))
            self.heading = None
        elif tag == "a" and self.href is not None:
            self.sections[-1].links.append((self.href, clean_text("".join(self.link))))
            self.href = None

    def handle_data(self, data: str) -> None:
        if self.heading is not None:
            self.heading.append(data)
        elif self.href is not None:
            self.link.append(data)
        elif self.inside is not None:
            self.sections[-1].text.append(data)


# "2026 m. Molėtų r. Alantos sen. komunalinių atliekų surinkimo grafikas", "2026 m. Molėtų miesto
# komunalinių atliekų surinkimo grafikai".
_LINK = re.compile(
    r"(?P<year>20\d{2})\s*m\.\s+Molėtų\s+(?:r\.\s+(?P<name>\w+)\s+sen\.|(?P<town>miesto))\s+"
    r"komunalinių\s+atliekų\s+surinkimo\s+grafika[si]",
    re.I,
)


def _eldership(name: str) -> str | None:
    """The register's eldership a link or a title names ("Alantos", "ČIULĖNŲ")."""
    return next((e for e in ELDERSHIPS if fold(e) == fold(name)), None)


def find_files(html: str, page_url: str = PAGE_URL) -> tuple[list[ScheduleFile], list[str]]:
    """The PDFs of the page by the texts of their links, with the notices next to them. A PDF of
    another text is reported, but those of the shared containers' section. The links are
    relative to the page's <base> (https://www.moletusvara.lt/)."""
    collector = _Sections()
    collector.feed(html)
    base = urljoin(page_url, collector.base) if collector.base else page_url
    files: list[ScheduleFile] = []
    warnings: list[str] = []
    for section in collector.sections:
        notice = clean_text("".join(section.text))
        for href, text in section.links:
            url = urljoin(base, href)
            path = unquote(urlsplit(url).path)
            if not path.lower().endswith(".pdf"):
                continue
            name = PurePosixPath(path).name
            link = _LINK.search(text)
            group = (TOWN if link["town"] else _eldership(link["name"])) if link else None
            if group is None:
                if not re.search(r"kolektyvin|juridini", fold(f"{section.heading} {text}")):
                    warnings.append(f"{name}: not read, a link of no eldership: {text!r}")
                continue
            if not fold(section.heading).startswith(fold(group).split()[0]):
                raise ValueError(f"{name}: the file of {group} under {section.heading!r}")
            year = int(link["year"])
            if (in_name := tratc.file_year(name)) and in_name != year:
                raise ValueError(f"{name}: a file of {in_name}, its link says {year}")
            if any(f.url == url for f in files):
                continue
            files.append(
                ScheduleFile(
                    kind="household",
                    url=url,
                    file_name=name,
                    group=group,
                    year=year,
                    notices=(notice,) if notice else (),
                )
            )
    return files, warnings


def select_files(files: list[ScheduleFile], today: date) -> tuple[list[ScheduleFile], list[str]]:
    """Per eldership, the files of this year and later; if there are none, the newest one. Of
    two for one year, the one linked last. Every eldership and the town must have its file."""
    selected: list[ScheduleFile] = []
    warnings: list[str] = []
    groups: dict[str, list[ScheduleFile]] = defaultdict(list)
    for file in files:
        groups[file.group].append(file)
    for group, mine in groups.items():
        running = [f for f in mine if f.year >= today.year] or [
            f for f in mine if f.year == max(g.year for g in mine)
        ]
        if today.year not in {f.year for f in running}:
            warnings.append(f"{group} sen.: no schedule for {today.year} on the page")
        for year in sorted({f.year for f in running}):
            *older, newest = [f for f in running if f.year == year]
            warnings += [
                f"{f.file_name}: not read, {newest.file_name} is a newer schedule for {year}"
                for f in older
            ]
            selected.append(newest)
    if missing := sorted((ELDERSHIPS | {TOWN}) - set(groups)):
        raise build.ValidationError(f"no schedule found on the page for {', '.join(missing)}")
    return selected, warnings


def download(
    today: date, keep_days: int, tolerant: bool = False
) -> tuple[list[tuple[SourceFile, bytes]], list[str]]:
    """The files in force. `tolerant`: a file that can't be downloaded is passed on empty, and
    keeps its rows of yesterday's data (parse_or_keep)."""
    html = http.get(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    files, warnings = find_files(html)
    selected, more = select_files(files, today)
    warnings += more
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


# --- the table -------------------------------------------------------------------

# "MOLĖTŲ R. ALANTOS SEN. KOMUNALINIŲ ATLIEKŲ SURINKIMO GRAFIKAS", "MOLĖTŲ R. LUOKESOS SEN. IR
# DALIES GIEDRAIČIŲ SEN. ...", "MOLĖTŲ MIESTO KOMUNALINIŲ ATLIEKŲ SURINKIMO GRAFIKAI", then
# "2026 m. Individualūs ir bendri konteineriai".
_TITLE = re.compile(
    r"MOLĖTŲ\s+(?:R\.\s+(?P<name>\w+)\s+SEN\.(?:\s+IR\s+DALIES\s+(?P<part>\w+)\s+SEN\.)?|"
    r"(?P<town>MIESTO))\s+KOMUNALINIŲ\s+ATLIEKŲ\s+SURINKIMO\s+GRAFIKA[SI]\s+"
    r"(?P<year>20\d{2})\s*m\.\s+Individualūs(?:\s+ir\s+bendri)?\s+konteineriai",
    re.I,
)
_HEADER = re.compile(r"(?:gyvenviete|gatves pavadinimas) atlieku rusys (?P<months>.+)")
# The days of a month's cell: "13", "14 / 24", "13 / 20 / 27", "-".
_DAYS = re.compile(r"\d{1,2}(?:\s*/\s*\d{1,2})*|-")
# The headings of the eldership files' parts (folded), and the kinds of their rows.
_PARTS: dict[str, tuple[Kind, ...]] = {
    "misrios komunalines atliekos": ("household",),
    "rusiuotos atliekos pakuotes": ("packaging", "glass"),
}
# A row's waste type by its words (folded): "Mišrios komunalinės", "Plastikas Metalas Popierius",
# "Stiklas", "Bioskaidžios" (grass, branches, garden waste: green waste).
_KINDS: dict[str, Kind] = {
    "misrios komunalines": "household",
    "plastikas metalas popierius": "packaging",
    "stiklas": "glass",
    "bioskaidzios": "green",
}
# "ATKREIPIAME DĖMESĮ, KAD PAANKSTINAMAS KIEKVIENO MĖNESIO PIRMAS ATLIEKŲ RINKIMAS (perkeliamas
# iš ketvirtadienio į antradienį)": the first mixed waste pickup of each month moved to another
# weekday.
_EARLIER = re.compile(
    r"ATKREIPIAME\s+DĖMESĮ\s*,?\s+KAD\s+PAANKSTINAMAS\s+KIEKVIENO\s+MĖNESIO\s+PIRMAS\s+ATLIEKŲ\s+"
    r"RINKIMAS\s*\(\s*perkeliamas\s+iš\s+(?P<from>\w+)\s+į\s+(?P<to>\w+)\s*\)",
    re.I,
)


@dataclass
class _Row:
    label: str
    kind: Kind
    dates: set[date]


def _rows(pdf, year: int, where: str) -> list[_Row]:
    """The table's rows of dates with their labels (the rows of businesses' extra pickups left
    out). Strict: a header of other columns, a cell that isn't days, a day the month doesn't
    have, a row of no waste type or of another than its part's raise ValueError."""
    tables = [(page, table) for page in pdf.pages for table in page.find_tables()]
    if len(tables) != 1:
        raise ValueError(f"{where}: {len(tables)} tables")
    page, table = tables[0]
    header = fold(page.crop(table.rows[0].bbox).extract_text() or "")
    found = _HEADER.fullmatch(header)
    months = found["months"].split() if found else []
    if [aratc.MONTHS.get(m) for m in months] != list(range(1, 13)):
        raise ValueError(f"{where}: a header of {header!r}")
    rows: list[_Row] = []
    part: tuple[Kind, ...] | None = None  # the town's file has no parts
    label = ""
    for cells in table.extract()[1:]:
        cells = [None if c is None else clean_text(c) for c in cells]
        texts = [c for c in cells if c]
        if not texts:
            continue
        if len(texts) == 1 and fold(texts[0]) in _PARTS:
            part = _PARTS[fold(texts[0])]
            continue
        values = [c for c in cells if c is not None]
        if len(values) == 14:
            label, values = values[0], values[1:]
        elif not (len(values) == 13 and cells[0] is None and label):
            raise ValueError(f"{where}: a row of {len(values)} cells: {texts[:3]}")
        kind = _KINDS.get(fold(values[0]))
        if kind is None or (part is not None and kind not in part):
            raise ValueError(f"{where}: a row of {values[0]!r} ({label[:40]!r})")
        if re.search(r"uzsakomieji|juridiniams", fold(label)):
            continue  # extra pickups that businesses order
        dates: set[date] = set()
        for month, cell in enumerate(values[1:], start=1):
            if not _DAYS.fullmatch(cell):
                raise ValueError(f"{where}: not days: {cell!r}")
            for day in re.findall(r"\d+", cell):
                try:
                    dates.add(date(year, month, int(day)))
                except ValueError as error:
                    raise ValueError(f"{where}: day {day} of {year}-{month:02}") from error
        if not dates:
            raise ValueError(f"{where}: no dates of {values[0]!r} ({label[:40]!r})")
        rows.append(_Row(label, kind, dates))
    return rows


def _check_villages(rows: list[_Row], where: str) -> None:
    """The settlements the villages' row of mixed waste names first ("Alanta ir seniūnijos
    kaimai") have the main settlements' row, which has every date of the villages' row: the
    reader leaves them to it."""
    mixed = [r for r in rows if r.kind == "household"]
    main = [r for r in mixed if _MAIN.fullmatch(r.label)]
    for row in mixed:
        villages = _VILLAGES.fullmatch(row.label)
        if not villages:
            continue
        if len(main) != 1:
            raise ValueError(f"{where}: {len(main)} rows of main settlements")
        first, mains = _names(villages["first"]), _names(_MAIN.fullmatch(main[0].label)["places"])
        if not set(first) <= set(mains):
            raise ValueError(f"{where}: {villages['first']!r} aren't all main settlements")
        if not row.dates <= main[0].dates:
            raise ValueError(f"{where}: the villages have mixed waste the main settlements haven't")


def _check_notices(source: SourceFile, rows: list[_Row]) -> list[str]:
    """The notices next to the file's link: the one about the first pickup of each month is
    checked against the file, others are reported."""
    warnings: list[str] = []
    for notice in getattr(source, "notices", ()):
        earlier = _EARLIER.fullmatch(clean_text(notice))
        if not earlier:
            warnings.append(f"{source.file_name}: a notice next to it on the page: {notice!r}")
            continue
        weekdays = parse_weekdays(earlier["to"]), parse_weekdays(earlier["from"])
        if [len(w) for w in weekdays] != [1, 1]:
            raise ValueError(f"{source.file_name}: a notice of no weekdays: {notice!r}")
        (to,), _ = weekdays
        for row in rows:
            if row.kind != "household":
                continue
            firsts = {d.month: d for d in sorted(row.dates, reverse=True)}
            wrong = sorted(d for d in firsts.values() if d.weekday() != to)
            if wrong:
                raise ValueError(
                    f"{source.file_name}: the page moves the first pickup of each month to "
                    f"{WEEKDAY_NAMES[to]}, the file has {wrong[0]} ({row.label[:40]!r})"
                )
    return warnings


def parse_file(source: SourceFile, content: bytes) -> ParseResult:
    """The schedules of a file's routes, named after the eldership and the places as the file
    writes them ("Alantos sen.: Pagrindinės gyvenvietės: Alanta", "Molėtų m.: Alberto Jauniškio
    g., ..."). Strict: a title of another eldership or year than the link's, a villages' row of
    mixed waste whose first settlements aren't main ones or whose dates aren't theirs, a label the
    reader doesn't know or two rows of one kind and place raise ValueError."""
    if not content:
        raise ValueError(f"{source.file_name}: not downloaded")
    where = source.file_name
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = clean_text(" ".join(page.extract_text() or "" for page in pdf.pages))
        title = _TITLE.search(text)
        if not title:
            raise ValueError(f"{where}: no title with the eldership and year")
        group = TOWN if title["town"] else _eldership(title["name"])
        year = int(title["year"])
        if group != source.group or year != getattr(source, "year", year):
            raise ValueError(
                f"{where}: the title says {group or title['name']} {year}, "
                f"the link {source.group} {getattr(source, 'year', '')}"
            )
        rows = _rows(pdf, year, where)
    part = _eldership(title["part"]) if title["part"] else None
    if title["part"] and part is None:
        raise ValueError(f"{where}: an eldership the register doesn't have: {title['part']!r}")
    _check_villages(rows, where)
    warnings = _check_notices(source, rows)
    areas: list[Area] = []
    for row in rows:
        if group == TOWN:
            name = row.label if fold(row.label) == "moletu miestas" else f"Molėtų m.: {row.label}"
        else:
            villages = _VILLAGES.fullmatch(row.label)
            if not (_MAIN.fullmatch(row.label) or villages):
                raise ValueError(f"{where}: places of no known kind: {row.label[:60]!r}")
            if villages and (villages["plural"] == "ų") != bool(part):
                raise ValueError(
                    f"{where}: {row.label[:60]!r} in a file of "
                    + (f"{group} and part of {part} sen." if part else f"{group} sen. only")
                )
            sections = f"{group} sen." + (f" ir dalies {part} sen." if part else "")
            name = f"{sections}: {row.label}"
        area = Area(row.kind, name, district=LABEL, dates=row.dates, provider=PROVIDER.id)
        weekdays = {d.weekday() for d in row.dates}
        if len(weekdays) == 1:
            area.weekday = WEEKDAY_NAMES[weekdays.pop()]
        if any(a.id == area.id for a in areas):
            raise ValueError(f"{where}: two {row.kind} rows of {row.label[:60]!r}")
        areas.append(area)
    if not any(a.kind == "household" for a in areas):
        raise ValueError(f"{where}: no mixed waste")
    return ParseResult(areas=areas, warnings=warnings)


def _prefix(group: str) -> str:
    """The start of the names of a file's rows."""
    return "Molėtų m" if group == TOWN else f"{group} sen."


def parse_or_keep(
    source: SourceFile, content: bytes, published: Callable[[], dict] | None = None
) -> ParseResult:
    """parse_file, or for a file that can't be read, its eldership's rows of yesterday's data
    (`published`; None: raise instead)."""
    try:
        return parse_file(source, content)
    except Exception as error:  # any failure of one file must not stop the others
        if published is None:
            raise
        prefix = _prefix(source.group)
        kept = build.published_rows(published(), PROVIDER, lambda r: r["name"].startswith(prefix))
        if not kept:
            raise
        return ParseResult(
            kept,
            [
                f"{source.file_name}: can't be read ({type(error).__name__}: {error}); "
                f"yesterday's {len(kept)} rows of {source.group} sen. are kept"
            ],
        )


# --- the source ------------------------------------------------------------------


def source(published: Callable[[], dict] | None = None) -> build.Source:
    """`published`: yesterday's data, for the files that can't be read (None: fail instead).
    Next year's file of an eldership continues this year's routes as raseiniai.combine joins
    Raseinių r.'s, an eldership at a time."""
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
    # The folder of one provider, as raseiniai.py builds its own; the town gets an eldership.
    return raseiniai.run(
        args.out, args.keep_days, published, MUNICIPALITY, source, aratc.town_elderships
    )


if __name__ == "__main__":
    raise SystemExit(main())

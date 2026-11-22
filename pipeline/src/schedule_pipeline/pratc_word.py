"""Panevėžio r.'s mixed waste schedule: the Word document Panevėžio RATC links in Panevėžio r.'s
section of its page ("Mišrių komunalinių atliekų surinkimo grafikas", a .doc read by
worddoc.py), for pratc.py.

Under a title with the year ("Panevėžio rajono gyventojų buitinių atliekų išvežimo grafikai 2026
m."), a table of routes, one or two to a cell:

    3. Dembavos, Vaivadų, Paežerio I (visos išskyrus Miglės, Kedrų ir Medeinos gatvės), ...,
       Vyčių gyvenviečių grafikas:                                    (ketvirtadieniai)
         Sausis     * 2-3;  15; 29 d.         Liepa           02;  16;  30 d.
         Vasaris         12; 26 d.            Rugpjūtis       13 ; 27 d.
         ... six lines of two months
    *Vietoje 2026m. sausio 1d. Šeškų, ... gyvenvietes aptarnausime sausio 2d.*
    Panevėžio aplinkl. 201, Šeškų k., aptarnaujamas 01.15; 02.12; 03.12; ...

A route is its number, its places ("... gyvenviečių grafikas:"), its weekdays in brackets and
the days of every month, read strictly: twelve months, each once, and only days ("02, 30 d.",
"13 27d"). Under some routes, notes in free words, which aren't parsed: a pickup moved for a
public holiday, for some of the route's villages only (the "2-3" above), one house with a route
of its own. After the table, a notice (when to put the containers out).

A route with notes, or marks in its days ("*26", "2-3"), is read from its transcription in
pipeline/data/schedule-panevezio-r-mixed.json: its rows as a person read them, each with its
places and every date. An entry is used only while the route's text in the file (whitespace
aside) is exactly the entry's `text`, so a changed route is never read with an old reading; the
same for the texts outside the routes (`texts`, which change no date). A route with notes or
marks that has no entry fails the file, and pratc keeps yesterday's mixed waste rows of
Panevėžio r. until it is transcribed: `uv run python -m schedule_pipeline.pratc_word` adds a
draft of each missing entry, its dates read from the route's days, for a person to correct
from the notes (CONTRIBUTING.md). Routes without notes are read from the file itself, so a
corrected day in one of them needs no transcription.

The places are lists of settlements in the genitive ("Paliūniškio, Klimbalės, ...
gyvenviečių"), a town's streets ("Ramygalos gatvių: Biliūno, Dariaus ir Girėno, ... taip pat
Daniūnų, ... gyvenviečių"), "(visos išskyrus Miglės, Kedrų ir Medeinos gatvės)" and "ir kitų
Karsakiškio seniūnijos gyvenviečių" (the eldership's other settlements), which `places` turns
into the lists pratc.Places reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import snapshot, worddoc
from .dates import WEEKDAY_NAMES, parse_weekdays
from .model import Area, ParseResult, SourceFile, clean_text

TRANSCRIPTION = snapshot.DATA_DIR / "schedule-panevezio-r-mixed.json"
_COMMAND = "uv run python -m schedule_pipeline.pratc_word, CONTRIBUTING.md"

MONTHS = (
    "sausis",
    "vasaris",
    "kovas",
    "balandis",
    "gegužė",
    "birželis",
    "liepa",
    "rugpjūtis",
    "rugsėjis",
    "spalis",
    "lapkritis",
    "gruodis",
)
# A month of the table, nominative (the notes write "sausio", "gruodžio").
_MONTH = re.compile(rf"\b({'|'.join(MONTHS)})\b", re.I)
# A day ("08", "29d", "27 d"), marked ("*26") or a range of days ("2-3").
_DAY = r"(\*{0,2})\s*(\d{1,2})(?:\s*-\s*(\d{1,2}))?(?:\s*d\b\.?)?"
_DAYS = re.compile(rf"[\s.,;]*(?:{_DAY}[\s.,;]*)+")
# A route's first paragraph: "3. Dembavos, ...", "3.* Paežerio I k. ...", "09. Algirdavos".
_NUMBER = re.compile(r"\s*(\d{1,2})\.(\*?)(?=\s)")
_WEEKDAY = r"(?:pirma|antra|trečia|ketvirta|penkta|šešta|sekma)dieniai"
# Its weekdays: "(ketvirtadieniai)", "(pirmadieniai-antradieniai)".
_RULE = re.compile(rf"\(\s*({_WEEKDAY}(?:\s*-\s*{_WEEKDAY})*)\s*\)", re.I)
_TITLE_WORD = re.compile(r"\bgrafik", re.I)
_GRAFIKAS = re.compile(r"[\s,]*\bgrafikas\s*:?\s*$", re.I)


@dataclass
class Route:
    number: str  # "3", "3*"
    places: str  # "Dembavos, Vaivadų, ... gyvenviečių": the name of its row
    rule: str  # "ketvirtadieniai"
    text: str  # all of it, whitespace collapsed: what a transcription is for
    # Per month, its days: (mark, first day, last day; the same but in a range).
    days: dict[int, list[tuple[str, int, int]]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def plain(self) -> bool:
        """Without notes, marks or ranges: the table says everything."""
        return not self.notes and all(
            not mark and first == last for days in self.days.values() for mark, first, last in days
        )

    def dates(self, year: int) -> set[date]:
        """Its days; of a range ("2-3"), every day (for a draft)."""
        return {
            date(year, month, day)
            for month, days in self.days.items()
            for _, first, last in days
            for day in range(first, last + 1)
        }

    def first_note(self) -> str:
        """What makes it need a transcription, for a message."""
        if self.notes:
            return self.notes[0]
        month, days = next(
            (m, d) for m, d in self.days.items() if any(x[0] or x[1] != x[2] for x in d)
        )
        return f"{MONTHS[month - 1].capitalize()} " + "; ".join(
            f"{mark}{first}" + (f"-{last}" if last != first else "") for mark, first, last in days
        )


@dataclass
class Document:
    year: int
    routes: list[Route]
    texts: list[str]  # outside the routes: the paragraphs after the table


def read(content: bytes, name: str = "the document") -> Document:
    """The routes of the document. Strict: a document without its title's year, a route without
    its weekdays, its twelve months or with words among its days, and a day that isn't one
    raise ValueError."""
    text = worddoc.text(content)
    end = text.rfind("\x07")
    if end < 0:
        raise ValueError(f"{name}: no table")
    paragraphs = re.split(r"[\r\x07]", text[:end])
    texts = [clean_text(p) for p in text[end + 1 :].split("\r") if clean_text(p)]
    starts = [i for i, p in enumerate(paragraphs) if _NUMBER.match(p)]
    if not starts:
        raise ValueError(f"{name}: no routes")
    title = [clean_text(p) for p in paragraphs[: starts[0]] if clean_text(p)]
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", " ".join(title))}
    if len(title) != 1 or not _TITLE_WORD.search(title[0]) or len(years) != 1:
        raise ValueError(f"{name}: no title with the year above the routes: {title}")
    year = years.pop()
    routes: list[Route] = []
    for i, start in enumerate(starts):
        until = starts[i + 1] if i + 1 < len(starts) else len(paragraphs)
        routes.append(_route(paragraphs[start:until], year, name))
    numbers = [r.number for r in routes]
    if len(set(numbers)) != len(numbers):
        raise ValueError(f"{name}: routes numbered twice: {numbers}")
    return Document(year, routes, texts)


def _route(paragraphs: list[str], year: int, name: str) -> Route:
    match = _NUMBER.match(paragraphs[0])
    assert match
    number = f"{int(match[1])}{match[2]}"
    where = f"{name}: route {number}"
    whole = "\r".join(paragraphs)
    rule = _RULE.search(whole)
    if rule is None:
        raise ValueError(f"{where}: no weekdays in brackets after its places")
    route = Route(number, _places(whole[match.end() : rule.start()]), rule[1], clean_text(whole))
    if not route.places:
        raise ValueError(f"{where}: no places")
    for line in whole[rule.end() :].split("\r"):
        if not line.strip():
            continue
        parts = _MONTH.split(line)
        if len(parts) == 1:
            route.notes.append(clean_text(line))
            continue
        if parts[0].strip(" .,;"):
            raise ValueError(f"{where}: {parts[0].strip()!r} before the months")
        for month_name, days in zip(parts[1::2], parts[2::2], strict=True):
            month = MONTHS.index(month_name.casefold()) + 1
            if month in route.days:
                raise ValueError(f"{where}: {month_name} twice")
            if not _DAYS.fullmatch(days):
                raise ValueError(f"{where}: not days of {month_name}: {days.strip()!r}")
            found = []
            for mark, first, last in re.findall(_DAY, days):
                first_day, last_day = int(first), int(last or first)
                if last_day < first_day:
                    raise ValueError(f"{where}: days {first}-{last} of {month_name}")
                for day in (first_day, last_day):
                    try:
                        date(year, month, day)
                    except ValueError as error:
                        raise ValueError(f"{where}: day {day} of {month_name}") from error
                found.append((mark, first_day, last_day))
            route.days[month] = found
    if sorted(route.days) != list(range(1, 13)):
        missing = [MONTHS[m - 1] for m in range(1, 13) if m not in route.days]
        raise ValueError(f"{where}: no days of {', '.join(missing)}")
    return route


def _places(header: str) -> str:
    """A route's places as its name: its lines joined ("Ievų\\rLaisvės": a comma where a line
    ends without one), without "grafikas:"."""
    lines = [line.strip() for line in header.split("\r") if line.strip()]
    text = ""
    for line in lines:
        text += line if not text else (" " if text[-1] in ",;:" else ", ") + line
    text = re.sub(r"\s+([,;:])", r"\1", clean_text(text))
    return _GRAFIKAS.sub("", text).strip(" ,;:")


# --- the transcription -----------------------------------------------------------------


def load_transcription(path: Path = TRANSCRIPTION) -> dict:
    """The transcription file, checked: an entry per route text, rows with names and dates."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"files", "texts", "routes"}:
        raise ValueError(f"{path.name}: expected files, texts and routes, not {sorted(data)}")
    seen: set[str] = set()
    for entry in data["routes"]:
        if set(entry) != {"number", "text", "rows"} or not entry["rows"]:
            raise ValueError(f"{path.name}: an entry without its number, text or rows: {entry}")
        if entry["text"] in seen:
            raise ValueError(f"{path.name}: route {entry['number']} transcribed twice")
        seen.add(entry["text"])
        for row in entry["rows"]:
            if set(row) != {"name", "dates"} or not row["name"] or not row["dates"]:
                raise ValueError(f"{path.name}: route {entry['number']}: a row {row}")
            if row["dates"] != sorted(set(row["dates"])):
                raise ValueError(f"{path.name}: {row['name'][:40]!r}: dates out of order")
            for day in row["dates"]:
                date.fromisoformat(day)
    return data


def parse(
    source: SourceFile, content: bytes, provider: str, transcription: dict | None = None
) -> ParseResult:
    """The mixed waste rows of the document: a route without notes from its days, the others
    from the transcription (`transcription`: load_transcription()). Strict: a route with notes
    or marks the transcription doesn't have, a text after the table it doesn't have, a year
    other than the link's, and transcribed dates of other years raise ValueError. A day of a
    route without notes that isn't one of its weekdays is a warning, and stays."""
    name = source.file_name
    document = read(content, name)
    linked = {
        int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", unquote(urlsplit(source.url).path))
    }
    if linked and linked != {document.year}:
        raise ValueError(f"{name}: a schedule of {document.year}, the link says {sorted(linked)}")
    transcription = transcription if transcription is not None else load_transcription()
    transcribed = {entry["text"]: entry for entry in transcription["routes"]}
    where = TRANSCRIPTION.name
    unknown = [t for t in document.texts if t not in transcription["texts"]]
    if unknown:
        raise ValueError(
            f"{name}: text after the table that {where} doesn't have: {unknown[0][:80]!r}; "
            f"re-transcribe ({_COMMAND})"
        )
    missing = [r for r in document.routes if not r.plain and r.text not in transcribed]
    if missing:
        listed = "; ".join(f"route {r.number} ({r.first_note()[:60]!r})" for r in missing)
        raise ValueError(
            f"{name}: notes that {where} doesn't have: {listed}; re-transcribe "
            f"{'them' if len(missing) > 1 else 'it'} ({_COMMAND})"
        )
    areas: dict[str, Area] = {}
    warnings: list[str] = []
    for route in document.routes:
        if entry := transcribed.get(route.text):
            rows = [
                (row["name"], {date.fromisoformat(d) for d in row["dates"]})
                for row in entry["rows"]
            ]
            odd = sorted(
                d
                for _, dates in rows
                for d in dates
                if d.year not in (document.year, document.year + 1)
            )
            if odd:
                raise ValueError(
                    f"{where}: route {route.number}: {odd[0]} in a {document.year} file"
                )
        else:
            rows = [(route.places, route.dates(document.year))]
            weekdays = parse_weekdays(route.rule)
            odd = sorted(d for d in rows[0][1] if d.weekday() not in weekdays)
            if odd:
                warnings.append(
                    f"{name} route {route.number}: {', '.join(d.isoformat() for d in odd)} isn't "
                    f"a day of the rule {route.rule!r}"
                )
        for row_name, dates in rows:
            area = Area("household", row_name, provider=provider, dates=dates)
            weekdays = {d.weekday() for d in dates}
            if len(weekdays) == 1:
                area.weekday = WEEKDAY_NAMES[weekdays.pop()]
            if areas.setdefault(area.id, area) is not area:
                raise ValueError(f"{name}: two rows named {row_name[:60]!r}")
    return ParseResult(areas=list(areas.values()), warnings=warnings)


# --- the places ------------------------------------------------------------------------

# "ir kitų Karsakiškio seniūnijos gyvenviečių": and the eldership's other settlements.
_REST = re.compile(r",?\s*\bir\s+kitų\s+(\w+)\s+seniūnijos\s+gyvenviečių\b", re.I)
# "of the settlement(s)", "of / for the residents": not places.
_NOT_PLACES = re.compile(
    r"\s*\b(?:gyvenviečių|gyvenvietės|gyvenvietes|gyventojų|gyventojams)\b", re.I
)
# "Plukių sodų", "Bernatonių sodų": the gardens of a village, its streets in the register (not
# "..., Sodų" of a list of streets, nor a village Sodai).
_GARDENS = re.compile(r"(?<=[^\W\d_])\s+sodų\b", re.I)
# "(visos išskyrus Miglės, Kedrų ir Medeinos gatvės)", "(Miglės, Kedrų ir Medeinos gatvės)".
_BRACKET_STREETS = re.compile(r"\(\s*(?:visos\s+)?(išskyrus\s+)?([^()]*?)\s+gatvės\s*\)", re.I)
# "Ramygalos gatvių: Biliūno, Dariaus ir Girėno, ... taip pat Daniūnų ...": a town's streets.
_TOWN_STREETS = re.compile(r"(\w+)\s+gatvių\s*:\s*(.*?)(?=\s+taip\s+pat\b|$)", re.I)
_TYPED = re.compile(r"\s(?:g|gatvė|sk|skg|skr|a|al|aklg|tak|takas|pl|kel|aplinkl)\.?$", re.I)


def places(name: str) -> tuple[str, str | None]:
    """A row's name as the list pratc.Places reads, and the eldership whose other settlements
    it also serves (genitive, "Karsakiškio"), if it says so:

        Naujarodžių gyvenvietės ir Krekenavos gatvių: Akmenės, ..., Žibučių
          -> Naujarodžių, Krekenavos m., Akmenės g., ..., Žibučių g.
        Paežerio I (visos išskyrus Miglės, Kedrų ir Medeinos gatvės), Šeškų, ...
          -> Paežerio I (išskyrus Miglės g., Kedrų g., Medeinos g.), Šeškų, ...

    "Krekenavos m." is the town of that name, a small town (mstl.) too; a street's name keeps
    its "ir" ("Dariaus ir Girėno")."""
    rest = None
    if match := _REST.search(name):
        rest, name = match[1], name[: match.start()] + name[match.end() :]
    text = _NOT_PLACES.sub("", name)
    text = re.sub(r"\bkm\.", "k.", text)

    def bracket(match: re.Match[str]) -> str:
        streets = [s.strip() for s in re.split(r",|\s+ir\s+", match[2]) if s.strip()]
        return f"({match[1] or ''}{', '.join(_street(s) for s in streets)})"

    text = _BRACKET_STREETS.sub(bracket, text)
    parts, done = [], 0
    for match in _TOWN_STREETS.finditer(text):
        streets = [s.strip() for s in match[2].split(",") if s.strip()]
        parts += [_between(text[done : match.start()]), f"{match[1]} m."]
        parts += [_street(s) for s in streets]
        done = match.end()
    parts.append(_between(text[done:]))
    text = ", ".join(p.strip(" ,;") for p in parts if p.strip(" ,;"))
    return re.sub(r"\s*,(?:\s*,)+", ",", text).strip(" ,;"), rest


def _between(text: str) -> str:
    """Places outside a town's streets: "ir" and "taip pat" (also) between them, outside
    brackets, are commas; a village's gardens are the village."""
    text = re.sub(r"^\s*taip\s+pat\s+|\s+taip\s+pat\s+", ", ", text, flags=re.I)
    parts = re.split(r"(\([^()]*\))", text)
    return "".join(
        p if p.startswith("(") else _GARDENS.sub("", re.sub(r"\s+ir\s+", ", ", p)) for p in parts
    )


def _street(name: str) -> str:
    """ "Biliūno" -> "Biliūno g."; "Malūno sk.", "Laisvės a." as they are."""
    return name if _TYPED.search(f" {name}") else f"{name} g."


# --- a draft of the transcription ------------------------------------------------------


def draft(documents: list[tuple[str, bytes]], old: dict) -> tuple[dict, list[str]]:
    """The transcription for `documents` ((url, content) of each file the page links): the
    entries of `old` still used, and a draft of each missing one, with the route's places for
    a name and its days for dates (both days of a range). Returns it and what to check."""
    routes: list[Route] = []
    texts: list[str] = []
    years: dict[str, int] = {}
    for url, content in documents:
        document = read(content, url)
        routes += [r for r in document.routes if r.text not in {x.text for x in routes}]
        texts += [t for t in document.texts if t not in texts]
        years.update({r.text: document.year for r in document.routes})
    kept = {e["text"]: e for e in old.get("routes", []) if e["text"] in years}
    todo: list[str] = []
    entries = []
    for route in routes:
        if route.text in kept:
            entries.append(kept[route.text])
        elif not route.plain:
            dates = sorted(d.isoformat() for d in route.dates(years[route.text]))
            entries.append(
                {
                    "number": route.number,
                    "text": route.text,
                    "rows": [{"name": route.places, "dates": dates}],
                }
            )
            todo.append(
                f"route {route.number}: apply its notes and marks to its rows: "
                f"{route.notes or [route.first_note()]}"
            )
    new_texts = [t for t in texts if t not in old.get("texts", [])]
    todo += [f"a text after the table: check that it changes no date: {t!r}" for t in new_texts]
    files = [
        {"url": url, "sha256": hashlib.sha256(content).hexdigest()} for url, content in documents
    ]
    return {"files": files, "texts": texts, "routes": entries}, todo


def dump(data: dict) -> str:
    """The transcription as it is committed: indented, a row's dates on one line."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        re.sub(
            r'\[\s+("\d{4}-\d\d-\d\d"(?:,\s+"\d{4}-\d\d-\d\d")*)\s+\]',
            lambda m: "[" + re.sub(r",\s+", ", ", m[1]) + "]",
            text,
        )
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update the transcription of Panevėžio r.'s mixed waste schedule from the "
        "files the page links: keep the entries still used, add drafts of the missing ones."
    )
    parser.add_argument("--out", type=Path, default=TRANSCRIPTION, help="the transcription file")
    args = parser.parse_args(argv)
    from . import http, pratc  # pratc imports this module

    found, _ = pratc.find_files(pratc.fetch_page())
    urls = [
        f.url
        for m, f, _ in found
        if m is pratc.PANEVEZIO_R and f.file_name.lower().endswith(".doc")
    ]
    if not urls:
        print("No Word document of Panevėžio r. on the page", file=sys.stderr)
        return 1
    old = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    data, todo = draft([(url, http.get(url, timeout=60)) for url in urls], old)
    args.out.write_text(dump(data), encoding="utf-8", newline="\n")
    print(f"Wrote {args.out}")
    for line in todo:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

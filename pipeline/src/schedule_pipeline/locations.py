"""Links each settlement (and street) of the Address Register to its rows in every schedule.

The schedules describe their areas as free text in different shapes:

  household:  "Avižieniai (Akacijų aklg., Avižų g., ...)"            nominative, streets in ()
  packaging:  "Avižienių sen. kaimai : Bajorų k. tik Čiobrelių., Jurginų g. Bendorių k. ..."
  glass:      "Sužionių sen. kaimai iškyrus Pakryžės k., Veriškių k. Nemenčinės ..."

and Nemėžio komunalininkas lists many settlements per row, comma-separated, each with its
streets in brackets (see PlaceList):

  "Mickūnų" | "Akmenynė, Mažeikiai (be Kairėnų ir Girios g.), Mickūnų mstl. (Gaidūnų g., ...)"

Instead of parsing every street format, we find settlement mentions using the register's
official names (nominative and genitive), then look for that settlement's official street
names in the text that follows the mention. A row then covers either a whole settlement or
some of its streets. "<X> sen. kaimai" without a list, or with "išskyrus", covers the whole
seniūnija apart from the settlements listed after "išskyrus".

Only exact, unambiguous links are published as such. Anything else is published as a short
list of candidate rows, and the app asks the user to choose.

Each seniūnija is served by one company (model.Provider). A settlement is linked only to rows
of its own company, so a village of the same name elsewhere can't pick up another's row.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .model import Area, Kind, Provider
from .registry import Registry, Settlement, Street, fold

KINDS: list[Kind] = ["household", "packaging", "glass"]

_UPPER = "A-ZĄČĘĖĮŠŲŪŽ"
_WORD = rf"[{_UPPER}][\wąčęėįšųūž-]*"
# Up to three capitalised words before a settlement type: "Aukštųjų Rusokų k.", "Visalaukės I k."
_MENTION = re.compile(rf"((?:{_WORD}\s+){{0,2}}{_WORD}(?:\s+I{{1,3}})?)\s*(k|vs|mstl|m)\s*\.", re.U)
_DISTRICT = re.compile(rf"({_WORD})\s+(?:sen|seniūnijos)\b\.?", re.U)
_EXCEPT = re.compile(r"i[sš]+kyrus", re.I)


@dataclass
class Clause:
    """One row's statement about one settlement."""

    area_id: str
    # Street keys this row covers; None = the whole settlement; empty = some streets, unrecognised.
    streets: set[str] | None
    fallback: bool = False  # from "<X> sen. kaimai": less specific than a named settlement
    # Only some houses of these streets ("Durpių g. 7, 10", a shared container site): one more
    # choice for the street, next to the row that serves the rest of it.
    extra: bool = False


@dataclass
class Index:
    registry: Registry
    by_name: dict[str, list[Settlement]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        for s in self.registry.settlements:
            for form in {fold(s.name), fold(s.genitive)}:
                self.by_name[form].append(s)
        self.districts = sorted({s.district for s in self.registry.settlements})

    def district(self, text: str) -> str | None:
        """Maps the schedules' spellings ("Sužionys", "Nemenčinės mst.") to register names."""
        words = fold(text).split()
        if not words:
            return None
        town = any(w in ("m", "mst", "miesto") for w in words[1:])
        best, best_len = None, 0
        for district in self.districts:
            first = fold(district).split()[0]
            common = len(_common_prefix(words[0], first))
            is_town = "miesto" in fold(district)
            if common >= 5 and is_town == town and common > best_len:
                best, best_len = district, common
        return best

    def candidates(self, name: str, district: str | None, strict: bool = False) -> list[Settlement]:
        """Settlements called `name`, preferring those in `district`; with `strict`, only those."""
        key = fold(name)
        hits = self.by_name.get(key, [])
        if district:
            in_district = [s for s in hits if s.district == district]
            if not in_district:
                # "Akmena" in a schedule covers the register's "Akmena I" and "Akmena II".
                in_district = [
                    s
                    for s in self.registry.settlements
                    if s.district == district
                    and any(
                        re.fullmatch(re.escape(key) + r" i{1,3}", fold(form))
                        for form in (s.name, s.genitive)
                    )
                ]
            if not in_district:
                # The schedules sometimes spell names differently from the register
                # ("Kalikstiškiai" for "Kalikstiškės", "Visalaukė" for "Visalaukė I"). Accept a
                # near match, but only inside the same seniūnija.
                in_district = [
                    s
                    for s in self.registry.settlements
                    if s.district == district
                    and any(_near(key, fold(form)) for form in (s.name, s.genitive))
                ]
            hits = in_district if strict else (in_district or hits)
        return list({s.code: s for s in hits}.values())

    def find(self, name: str, district: str | None) -> Settlement | None:
        hits = self.candidates(name, district)
        return hits[0] if len(hits) == 1 else None


def _near(a: str, b: str) -> bool:
    """Same word apart from a grammatical ending: "kalikstiskiai" ~ "kalikstiskes",
    but not "akmena" ~ "akmenele" (an extra syllable is a different name)."""
    common = len(_common_prefix(a, b))
    if common < 5:
        return False
    endings = (a[common:], b[common:])
    return all(len(e) <= 3 and set(e) <= set("aeiouys") for e in endings)


def _one_off(a: str, b: str) -> bool:
    """A typo: one letter changed, missing or added, in a word long enough not to be another
    name ("Padvarnikai" for "Padvarninkai", "Zastaičių" for "Zastaučių")."""
    if a == b or min(len(a), len(b)) < 7 or abs(len(a) - len(b)) > 1:
        return False
    n = len(_common_prefix(a, b))
    return a[n + 1 :] == b[n + 1 :] or a[n:] == b[n + 1 :] or a[n + 1 :] == b[n:]


def _common_prefix(a: str, b: str) -> str:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n]


def street_key(street: Street) -> str:
    return f"s{street.code}"


def variant_key(label: str) -> str:
    return "v" + hashlib.sha1(fold(label).encode()).hexdigest()[:8]


def streets_in(text: str, settlement: Settlement, loose: bool = False) -> set[str]:
    """Official street names of `settlement` that appear in `text`, also when the schedule
    shortens a first name to its initial: "J.Bulhako g." is "Jano Bulhako g.".

    `loose` (Nemėžio's lists) also accepts several initials ("A. L. Bekiu" is "Augusto
    Liudviko Bekiu"), the surname alone when no other street ends with it ("Morkūno g."), and
    numbered streets in one go ("Tulpės 1,2,3,4-oji")."""
    folded = f" {fold(text)} "
    last_words: dict[str, int] = defaultdict(int)
    for street in settlement.streets:
        last_words[fold(street.name).split()[-1]] += 1

    def mentioned(name: str) -> bool:
        words = fold(name).split()
        forms = [words]
        if len(words) > 1:
            forms += [[w[0] for w in words[:k]] + words[k:] for k in range(1, len(words))]
            if not loose:
                forms = forms[:2]
            elif all(w.isalpha() for w in words) and len(words[-1]) >= 5:
                if last_words[words[-1]] == 1:
                    forms.append(words[-1:])
        return any(f" {' '.join(form)} " in folded for form in forms)

    found = {street_key(t) for t in settlement.streets if mentioned(t.name)}
    if loose:
        for stem, numbers in re.findall(r" ([a-z]+) ((?:\d+ )+)i?oji ", folded):
            wanted = set(numbers.split())
            for t in settlement.streets:
                m = re.fullmatch(rf"{stem} (\d+) i?o\w*", fold(t.name))
                if m and m.group(1) in wanted:
                    found.add(street_key(t))
    return found


def household_clauses(
    index: Index, area: Area, variants: dict[int, dict[str, str]]
) -> list[tuple[Settlement, Clause]]:
    """ "Avižieniai (Akacijų aklg., ...)" -> Avižieniai, streets {Akacijų, ...}."""
    district = index.district(area.district or "")
    name = re.sub(r"\s*\((k|vs|mstl|m)\.?\)", "", area.name)  # "Akmena (k.)"
    words = name.split()
    # Longest leading run of words that is a settlement name: "Mažoji Riešė (...)".
    for n in range(min(4, len(words)), 0, -1):
        head = re.sub(r"\(.*", "", " ".join(words[:n])).strip(" ,")
        hits = index.candidates(re.sub(r"\s+(k|vs|mstl|m)\.?$", "", head), district)
        if hits:
            break
    else:
        return []
    # `head` stops before any "(", so this keeps the whole street list.
    rest = name[name.index(head) + len(head) :].strip(" ,")
    if not rest:
        # Applies to every match: "Akmena" -> "Akmena I" and "Akmena II".
        return [(s, Clause(area.id, None)) for s in hits]
    with_streets = [(s, streets_in(rest, s)) for s in hits]
    if any(streets for _, streets in with_streets):
        # One row can list streets of two same-named settlements (Bezdonys k. and mstl.).
        return [(s, Clause(area.id, streets)) for s, streets in with_streets if streets]
    if len(hits) > 1:
        return []
    # Not a street list, e.g. a garden community "S/B Telefonistas": offer it as its own choice.
    label = re.sub(r"^\(|\)$", "", rest).strip()
    key = variant_key(label)
    variants[hits[0].code][key] = label
    return [(hits[0], Clause(area.id, {key}))]


def listed_clauses(index: Index, area: Area) -> tuple[list[tuple[Settlement, Clause]], list]:
    """Packaging/glass rows. Returns explicit clauses and whole-seniūnija rules."""
    clauses: list[tuple[Settlement, Clause]] = []
    whole_districts: list[tuple[str, set[int]]] = []  # (district, excluded settlement codes)

    # Split the row at "<X> sen." markers; text before the first marker has no district.
    markers = list(_DISTRICT.finditer(area.name))
    parts = [(None, area.name[: markers[0].start()] if markers else area.name)]
    for i, m in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(area.name)
        parts.append((index.district(m.group(1)), area.name[m.end() : end]))

    for district, text in parts:
        mentions = []
        for m in _MENTION.finditer(text):
            words = m.group(1).split()
            # Prefer the longest name: "Aukštųjų Rusokų" before "Rusokų".
            for k in range(len(words)):
                hits = index.candidates(" ".join(words[k:]), district)
                if hits:
                    mentions += [(m, settlement) for settlement in hits]
                    break

        except_at = _EXCEPT.search(text)
        lead = text[: mentions[0][0].start()] if mentions else text
        if district and (
            (except_at and (not mentions or except_at.start() < mentions[0][0].start()))
            or (not mentions and re.fullmatch(r"\W*kaimai\W*", lead, re.I))
        ):
            excluded = {s.code for _, s in mentions}
            whole_districts.append((district, excluded))
            continue

        starts = sorted({m.start() for m, _ in mentions})
        for m, settlement in mentions:
            end = next((s for s in starts if s > m.start()), len(text))
            tail = text[m.end() : end]
            streets = streets_in(tail, settlement)
            # "X k. tik <streets we don't recognise>" still covers only part of X: an empty set,
            # so it can't pass for the row of the whole settlement.
            restricted = bool(re.search(r"\btik\b", tail, re.I))
            clauses.append(
                (settlement, Clause(area.id, streets or (set() if restricted else None)))
            )
    return clauses, whole_districts


# --- Nemėžio komunalininkas: lists of settlements ------------------------------

_QUOTES = "\"'“”„«»"
_TYPE_WORDS = {"k": "k.", "vs": "vs.", "mstl": "mstl.", "m": "m."}
# A settlement name, then optionally its type ("Mickūnų mstl.", "Kyviškių geležinkelio st.";
# "g." is a typo seen for "k.") and house numbers ("Voverių k. 1"). The dot is optional: a
# part's last dot is cut off with the comma after it.
_HEAD = re.compile(
    r"(?P<name>.+?)"
    r"(?:\s+(?:(?P<type>k|vs|mstl|m|g)\b\.?|(?P<station>gele[žz]inkelio\s+st)\b\.?))?"
    r"(?:\s+(?P<houses>\d+[A-Za-z]?(?:\s*,\s*\d+[A-Za-z]?)*))?",
    re.I,
)
_GARDEN = re.compile(rf"\bS\s*/?\s*B\s*[{_QUOTES}]?\s*([^{_QUOTES}(),]+?)\s*[{_QUOTES}]", re.U)
# "(bendri)", "(bendro naud.)": shared containers; "(visi)": all; "(ind.)": private houses.
_NOTES = {"bendri": "shared", "bendro naud": "shared", "bendro naudojimo": "shared"}
_NOTES |= {"visi": "all", "ind": "all"}
# Rows or parts of rows that aren't homes: businesses, a cemetery, shops (by their brand, with a
# capital: "iki" is also "until", as in "Pergalės g. iki geležinkelio").
_NOT_HOMES = re.compile(
    r"\b(?:(?i:įmon\w*|kapinės|paukštynas|lentpjūvė|homanit)|Maxima|Iki|MAXIMA|IKI)\b"
)
_HOUSE_NUMBERS = re.compile(r"\b(g|pl|al|skg|aklg|tak|kel)\s*\.\s*\d", re.I)
_RANGE = re.compile(r"\b(nuo|iki)\b[^,()]*", re.I)  # "Pergalės g. nuo 35 iki galo"
_PARTLY = re.compile(r"[^,()]*\b(nuo|iki)\b[^,()]*", re.I)  # the street with its range
_EXCLUDING = re.compile(r"^\s*(be|i[sš]kyrus)\b", re.I)
_ROMAN = re.compile(r"I{1,3}|IV|V")


def split_places(text: str) -> list[str]:
    """Splits a row at the commas between settlements, not those inside brackets. A bracket
    followed by a capital also ends a part (a missing comma: "Migūnai (...) Raguvėlė")."""
    parts: list[str] = []
    depth, start, i = 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
            gap = re.match(rf"\s+(?=[{_UPPER}])", text[i + 1 :])
            if depth == 0 and gap:
                parts.append(text[start : i + 1])
                i = start = i + 1 + gap.end()
                continue
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip(" .;") for p in parts if p.strip(" .;")]


def garden_label(text: str) -> tuple[str, str] | None:
    """'SB „Rasa“', 'SB"Atžalynas-2"', 'SB Prekyba' -> (variant key, 'SB „Rasa“')."""
    match = _GARDEN.search(text + '"')
    if not match:
        return None
    name = re.sub(r"\s*-\s*", "-", match.group(1).strip())
    label = f"SB „{name}“"
    return variant_key(label), label


@dataclass
class _Place:
    settlement: Settlement
    streets: set[str] | None
    extra: bool
    fallback: bool


class PlaceList:
    """Reads one row of a provider whose rows list many settlements:

        Akmenynė, Mažeikiai (be Kairėnų ir Girios g.), Mickūnų geležinkelio st.,
        Uosininkai I, II, Mickūnų mstl. (Gaidūnų g., ...), SB „Rasa“- Piktakonių k.

    Names are nominative, or genitive with their type; brackets hold streets ("be ..." and
    "išskyrus ..." list the streets that are not included), garden communities (SB, offered as
    one more choice in the street list) or a note ("bendri": shared containers, one more choice
    next to the row of the houses). House numbers mean only some houses of those streets.
    """

    def __init__(
        self,
        index: Index,
        provider: Provider,
        variants: dict[int, dict[str, str]],
        gardens: dict[str, dict[str, int]] | None,
    ) -> None:
        self.index = index
        self.provider = provider
        self.variants = variants
        # district -> garden key -> settlement code, from rows that say where a garden is;
        # None while collecting them (first pass).
        self.gardens = gardens
        # Parts of the last row read that name no settlement we know.
        self.unknown: list[str] = []

    def settlements(self, name: str, district: str | None, kind: str | None) -> list:
        hits = [
            s
            for s in self.index.candidates(name, district, strict=True)
            if s.district in self.provider.elderships
        ]
        if kind:
            hits = [s for s in hits if s.abbr == kind] or hits
        else:
            # "Kena" is the village, not the railway station of the same name.
            hits = [s for s in hits if s.abbr != "glž. st."] or hits
        return hits

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        """Returns the clauses and whether the row only names places that aren't homes."""
        self.unknown = []
        district = self.index.district(area.district or "")
        if district not in self.provider.elderships:
            return [], False
        shared_row = (area.group or "") == "Daugiabučiai namai"
        places: list[_Place] = []
        homes = False
        previous: _Place | None = None
        base = ""  # "Uosininkai" in "Uosininkai I, II, III"
        for part in split_places(area.name):
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0] if rest else None
            head = head.strip(" .,-")
            if _NOT_HOMES.search(head) or (spec is not None and _NOT_HOMES.search(spec)):
                continue
            homes = True
            garden = garden_label(part)
            if garden and fold(head).startswith("sb"):
                # "SB „Rasa“- Piktakonių k." or a garden on its own: where is it?
                after = re.split(rf"[{_QUOTES}]", part)[-1].strip(" -–")
                target = self._garden_home(garden[0], after, district, previous)
                if target:
                    self._add_variant(target, garden)
                    places.append(_Place(target, {garden[0]}, shared_row, False))
                continue
            if _ROMAN.fullmatch(head) and base:
                head = f"{base} {head}"
            if re.fullmatch(r"\d+[A-Za-z]?", head) and previous:
                previous.extra = True  # "Rokantų k. 1, 2, 3": more house numbers
                continue
            if fold(head) in _NOTES and spec is None:
                # 'SB "Atžalynas-2", bendri': a note about the place before it.
                if previous and _NOTES[fold(head)] == "shared":
                    previous.extra = True
                continue
            notes = []
            words = head.split()
            while len(words) > 1 and fold(words[-1]) in _NOTES:
                notes.append(_NOTES[fold(words.pop())])
            match = _HEAD.fullmatch(" ".join(words))
            if not match:
                continue
            name = match.group("name")
            kind = "glž. st." if match.group("station") else None
            if match.group("type") and match.group("type").lower() in _TYPE_WORDS:
                kind = _TYPE_WORDS[match.group("type").lower()]
            hits = self.settlements(name, district, kind)
            if not hits:
                text = _RANGE.sub(" ", part)
                if previous and (streets := streets_in(text, previous.settlement, True)):
                    # "Skaidiškės (...), Minsko pl.": more streets of the previous place;
                    # "Lavoriškių k., Vilniaus g. 24": the shared containers of those houses.
                    if previous.streets is not None:
                        previous.streets |= streets
                    elif shared_row:
                        previous.streets = streets
                    previous.extra |= bool(_HOUSE_NUMBERS.search(part))
                else:
                    self.unknown.append(part)
                continue
            base = re.sub(r"\s+(I{1,3}|IV|V)$", "", hits[0].name)
            for settlement in hits:
                streets, extra = self._streets(settlement, spec)
                extra = extra or shared_row or bool(match.group("houses")) or "shared" in notes
                place = _Place(settlement, streets, extra, fallback=len(hits) > 1 and not kind)
                places.append(place)
                previous = place
        clauses = [
            (p.settlement, Clause(area.id, p.streets, fallback=p.fallback, extra=p.extra))
            for p in places
        ]
        return clauses, not homes

    def _streets(self, settlement: Settlement, spec: str | None) -> tuple[set[str] | None, bool]:
        """(streets, only some houses) for the bracket after a settlement's name."""
        if spec is None:
            return None, False
        note = _NOTES.get(fold(spec))
        if note:
            return None, note == "shared"
        text = _RANGE.sub(" ", spec)
        if _EXCLUDING.match(text):
            # "be Verslo, Pergalės g. iki 1-31": a street left out only in part stays in.
            excluded = streets_in(_PARTLY.sub(" ", spec), settlement, loose=True)
            if not excluded:
                return None, False  # only houses or a garden are left out
            return {street_key(t) for t in settlement.streets} - excluded, False
        streets = streets_in(text, settlement, loose=True)
        for part in re.split(r",", spec):
            if garden := garden_label(part):
                self._add_variant(settlement, garden)
                streets.add(garden[0])
        extra = bool(_HOUSE_NUMBERS.search(spec)) or "bendr" in fold(spec)
        return streets, extra

    def _add_variant(self, settlement: Settlement, garden: tuple[str, str]) -> None:
        key, label = garden
        self.variants[settlement.code].setdefault(key, label)

    def _garden_home(
        self, key: str, after: str, district: str | None, previous: _Place | None
    ) -> Settlement | None:
        if after:
            match = _HEAD.fullmatch(after.strip(" .,"))
            if match:
                kind = _TYPE_WORDS.get((match.group("type") or "").lower())
                hits = self.settlements(match.group("name"), district, kind)
                if len(hits) == 1:
                    return hits[0]
        if self.gardens is None:
            return None  # first pass: only gardens whose place is named
        code = (self.gardens.get(district or "") or {}).get(key)
        if code is not None:
            return next(s for s in self.index.registry.settlements if s.code == code)
        label = self.variants_label(key)
        if label:
            name = label.removeprefix("SB „").removesuffix("“")
            hits = self.settlements(name, district, None)
            if len(hits) == 1:
                return hits[0]
        return previous.settlement if previous else None

    def variants_label(self, key: str) -> str | None:
        for labels in self.variants.values():
            if key in labels:
                return labels[key]
        return None


def known_gardens(
    registry: Registry, variants: dict[int, dict[str, str]]
) -> dict[str, dict[str, int]]:
    """district -> garden key -> settlement, for gardens only one settlement lists."""
    by_code = {s.code: s for s in registry.settlements}
    found: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for code, labels in variants.items():
        for key in labels:
            found[by_code[code].district][key].add(code)
    return {
        district: {key: next(iter(codes)) for key, codes in keys.items() if len(codes) == 1}
        for district, keys in found.items()
    }


# --- TRATC: routes ---------------------------------------------------------------

_STREET_END = re.compile(r"\b(g|skg|aklg|tak|takas|al|alėja|pl|kel|kelias|a)\s*\.?\s*$", re.I)
_PART_DISTRICT = re.compile(rf"({_WORD})\s+sen\b\.?", re.U)
_ROW_DISTRICT = re.compile(rf"^\s*({_WORD})\s+sen\b\.?\s*:", re.U)
_GARDENS_OF = re.compile(rf"^({_WORD})\s+sodai$", re.U)
_NUMBERED = r"(?: i{1,3})(?: ir i{1,3})*"


class RouteList:
    """Reads one row of a schedule whose rows are routes of a whole municipality, with no
    eldership column:

        Žagarėlės g. miesto sen., Neries g., M. Pečkauskaitės g. (Vaisių g., Obuolių g.), ...
        Lendriškiai, Laižuva, Lėlaičiai (Tirkšlių sen.), Tučiai I ir II, SB „Linelis“
        Sedos sen: Kalnijos, Užežerė

    A part is a settlement (nominative), a street of the municipality's town (`route_town`), or
    a garden community, which is offered as one more choice in the town's street list. A name
    that several elderships have is the one of the eldership named in the row or, failing
    that, of the eldership most of the row's other settlements are in.
    """

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.variants = variants
        self.town = next(
            s
            for s in index.registry.settlements
            if s.name == provider.route_town and s.abbr == "m."
        )
        self.unknown: list[str] = []

    def settlements(self, name: str) -> list[Settlement]:
        key = fold(re.sub(r"\s+(k|vs|mstl|m)\.?$", "", name.strip()))
        if not key:
            return []
        everything = self.index.registry.settlements
        hits = [s for s in everything if fold(s.name) == key]
        if not hits:
            # "Tučiai I ir II", or "Tučiai" for both.
            base = re.sub(rf"{_NUMBERED}$", "", key)
            hits = [
                s for s in everything if re.fullmatch(re.escape(base) + _NUMBERED, fold(s.name))
            ]
        if not hits:
            # A different ending ("Skuodiškės" for "Skuodiškiai"), if only one name is close.
            # Or a typo ("Padvarnikai" for "Padvarninkai").
            for close in (_near, _one_off):
                near = [s for s in everything if close(key, fold(s.name))]
                if len({s.name for s in near}) == 1:
                    return near
        return hits

    def town_streets(self, part: str) -> set[str]:
        streets = streets_in(part, self.town, loose=True)
        match = re.fullmatch(r"(.+?)\s+(\w+)\.?", part.strip())
        if streets or not match:
            return streets
        # A typo in a street's name ("Geldiškio skg." for "Gediškio skg."), if it has the
        # same type and only one street is that close.
        name, kind = fold(match.group(1)), fold(match.group(2))
        close = [
            t
            for t in self.town.streets
            if fold(t.abbr).startswith(kind[:3]) and _one_off(name, fold(t.name))
        ]
        return {street_key(close[0])} if len(close) == 1 else set()

    def garden_streets(self, label: str) -> set[str]:
        """The town's streets named after a garden community: "Rasos 1-oji g." ... for SB
        „Rasa“, "Ašvos Sodo 2-oji g." for SB „Ašva“. Only numbered and "Sodo" streets: "Ašvos
        g." is an ordinary street."""
        name = fold(label.removeprefix("SB „").removesuffix("“"))
        if len(name) < 4:
            return set()
        pattern = re.compile(re.escape(name[:-1]) + r"\w{0,2}(?: sodo)?(?: \d+ \w+)?")
        return {
            street_key(t)
            for t in self.town.streets
            if pattern.fullmatch(fold(t.name)) and re.search(r"\d| sodo", fold(t.name))
        }

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        text = area.name
        row_district = None
        if match := _ROW_DISTRICT.match(text):
            row_district = self.index.district(match.group(1))
            text = text[match.end() :]
        text = re.sub(rf"^\s*{re.escape(self.town.genitive)}\s+m\.\s*:?", "", text)
        text = re.sub(r"\bmiesto sen\b\.?", "", text)  # "Žagarėlės g. miesto sen."

        town_streets: set[str] = set()
        # (settlements of one name, eldership named for them, streets in brackets)
        named: list[tuple[list[Settlement], str | None, str | None]] = []
        streets_of: dict[int, set[str]] = defaultdict(set)
        for part in split_places(text):
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0] if rest else None
            head = head.strip(" .,-:")
            if fold(head).startswith(("sb ", "s b ")) and (garden := garden_label(head)):
                self.variants[self.town.code].setdefault(*garden)
                town_streets |= {garden[0]} | self.garden_streets(garden[1])
                continue
            if match := _GARDENS_OF.match(head):
                # "Kurmaičių sodai": the streets "Kurmaičių Sodo 1-oji g." ... of any settlement.
                stem = fold(match.group(1)) + " sodo"
                found = False
                for settlement in self.index.registry.settlements:
                    keys = {
                        street_key(t) for t in settlement.streets if fold(t.name).startswith(stem)
                    }
                    streets_of[settlement.code] |= keys
                    found = found or bool(keys)
                if not found:
                    self.unknown.append(part)
                continue
            hits = [] if _STREET_END.search(head) else self.settlements(head)
            if hits:
                district = row_district
                if spec and (match := _PART_DISTRICT.search(spec)):
                    district, spec = self.index.district(match.group(1)), None
                named.append((hits, district, spec))
                continue
            streets = self.town_streets(part)
            if streets:
                town_streets |= streets
            else:
                self.unknown.append(part)

        # Where most of the row is: decides between villages of the same name.
        sure = [hits[0].district for hits, _, _ in named if len({s.district for s in hits}) == 1]
        common = [district for district, _ in Counter(sure).most_common()]
        clauses: list[tuple[Settlement, Clause]] = []
        for hits, district, spec in named:
            fallback = False
            districts = {s.district for s in hits}
            if len(districts) > 1:
                wanted = district if district in districts else None
                wanted = wanted or next((d for d in common if d in districts), None)
                if wanted:
                    hits = [s for s in hits if s.district == wanted]
                else:
                    fallback = True
            for settlement in hits:
                streets = streets_in(spec, settlement, loose=True) if spec else None
                clauses.append((settlement, Clause(area.id, streets or None, fallback=fallback)))
        by_code = {s.code: s for s in self.index.registry.settlements}
        whole = {s.code for s, c in clauses if c.streets is None}
        for code, keys in streets_of.items():
            if keys and code not in whole:
                clauses.append((by_code[code], Clause(area.id, keys)))
        if town_streets:
            clauses.append((self.town, Clause(area.id, town_streets)))
        return clauses, False

    def signature(self, area: Area) -> frozenset:
        """What the row covers, to tell whether two years' rows are the same route."""
        clauses, _ = self.clauses(area)
        return frozenset(
            (s.code, key) for s, c in clauses for key in (sorted(c.streets) if c.streets else [""])
        )


def resolve(clauses: list[Clause], simplify: bool = False) -> dict | None:
    """Turns everything the rows say about one settlement into what the app needs.

    `simplify`: a settlement split by street whose streets all lead to the same row gets that
    row directly, so the app doesn't ask for a street for nothing."""
    if not clauses:
        return None
    extras = [c for c in clauses if c.extra]
    clauses = [c for c in clauses if not c.extra]
    named = [c for c in clauses if not c.fallback]
    whole = sorted({c.area_id for c in named if c.streets is None})
    by_street: dict[str, set[str]] = defaultdict(set)
    for c in named:
        for key in c.streets or ():
            by_street[key].add(c.area_id)
    fallback = sorted({c.area_id for c in clauses if c.fallback})
    # Rows limited to streets we couldn't recognise: better than nothing if no other row applies.
    unknown = sorted({c.area_id for c in named if c.streets is not None and not c.streets})

    if extras:
        # Rows for some houses only (shared containers, house numbers): one more choice next to
        # the row that would apply otherwise.
        street_rows = set().union(*by_street.values()) if by_street else set()
        others = set(whole) or set(fallback) or street_rows or set(unknown)
        for c in extras:
            for key in c.streets or ():
                by_street[key] = (by_street.get(key) or set(others)) | {c.area_id}
        loose = {c.area_id for c in extras if not c.streets}
        if loose and whole:
            whole = sorted(set(whole) | loose)
        elif loose and fallback:
            fallback = sorted(set(fallback) | loose)
        elif loose and not by_street:
            unknown = sorted(set(unknown) | loose)

    result: dict = {}
    if by_street:
        result["streets"] = {k: sorted(v) for k, v in sorted(by_street.items())}
    if len(whole) == 1:
        result["area"] = whole[0]
    elif len(whole) > 1:
        result["candidates"] = whole
    elif len(fallback) == 1:
        result["area"] = fallback[0]
    elif len(fallback) > 1:
        result["candidates"] = fallback
    elif not by_street and len(unknown) == 1:
        result["area"] = unknown[0]
    elif not by_street and len(unknown) > 1:
        result["candidates"] = unknown
    if simplify and set(result) == {"streets"}:
        rows = {row for rows in result["streets"].values() for row in rows}
        if len(rows) == 1:
            result = {"area": rows.pop()}
    if simplify and "area" in result and "streets" in result:
        # A garden named in the row of its village: no need to ask for the street.
        if all(rows == [result["area"]] for rows in result["streets"].values()):
            del result["streets"]
    return result or None


def build_locations(
    registry: Registry, areas: list[Area], provider: Provider | None = None
) -> tuple[list[dict], dict]:
    """Locations of the settlements `areas` serve. With `provider`, only settlements of its
    elderships, linked only to its rows."""
    index = Index(registry)
    per_settlement: dict[int, dict[Kind, list[Clause]]] = defaultdict(lambda: defaultdict(list))
    variants: dict[int, dict[str, str]] = defaultdict(dict)
    whole_rules: dict[Kind, list[tuple[str, set[int], str]]] = defaultdict(list)
    unmatched: list[str] = []
    unknown_parts: list[str] = []  # place-list rows: names that are no settlement we know
    served: set[str] = set()
    place_lists = bool(provider and provider.place_lists)
    routes = RouteList(index, provider, variants) if provider and provider.route_town else None
    reader = PlaceList(index, provider, variants, None) if provider and place_lists else None
    kinds = list(provider.kinds) if provider else KINDS
    if reader:
        # First pass: where the garden communities are, from rows that say so.
        for area in areas:
            reader.clauses(area)
        reader.gardens = known_gardens(registry, variants)

    for area in areas:
        wholes: list = []
        skipped = False
        if routes:
            found, skipped = routes.clauses(area)
            unknown_parts += [f"{area.kind}: {part[:80]}" for part in routes.unknown]
            served |= provider.elderships
        elif reader:
            found, skipped = reader.clauses(area)
            unknown_parts += [
                f"{area.kind}: {part[:80]} ({area.district} sen.)" for part in reader.unknown
            ]
            if area.kind == "household" and (district := index.district(area.district or "")):
                served.add(district)
        elif area.kind == "household":
            found = household_clauses(index, area, variants)
            if area.district and (district := index.district(area.district)):
                served.add(district)
        else:
            found, wholes = listed_clauses(index, area)
            whole_rules[area.kind] += [(d, ex, area.id) for d, ex in wholes]
        if provider:
            found = [(s, c) for s, c in found if s.district in provider.elderships]
        if not found and not wholes and not skipped:
            unmatched.append(f"{area.kind}: {area.name[:80]}")
        for settlement, clause in found:
            per_settlement[settlement.code][area.kind].append(clause)
    if provider:
        served &= provider.elderships

    locations = []
    stats: dict[str, int] = defaultdict(int)
    for settlement in registry.settlements:
        if settlement.district not in served:
            continue
        clauses = per_settlement[settlement.code]
        for kind, rules in whole_rules.items():
            for district, excluded, area_id in rules:
                if district == settlement.district and settlement.code not in excluded:
                    clauses[kind].append(Clause(area_id, None, fallback=True))

        simplify = place_lists or bool(routes)
        schedule = {kind: r for kind in kinds if (r := resolve(clauses.get(kind, []), simplify))}
        if routes:
            # A route names every street it serves, so a street no route names has no pickup
            # (apartment buildings with shared containers, gardens without food waste). An
            # empty list says so; without it the app would offer every row of the town.
            every = [street_key(t) for t in settlement.streets] + sorted(variants[settlement.code])
            for r in schedule.values():
                if set(r) == {"streets"}:
                    r["streets"] = dict(
                        sorted({**dict.fromkeys(every, []), **r["streets"]}.items())
                    )
        street_keys = {k for r in schedule.values() for k in r.get("streets", {})}
        location: dict = {
            "id": f"g{settlement.code}",
            "name": settlement.name,
            "type": settlement.abbr,
            "district": settlement.district,
        }
        if provider and not provider.legacy:
            location["provider"] = provider.id
        if street_keys:
            # The user needs to pick a street only where some schedule splits by street.
            location["streets"] = [[street_key(t), t.label] for t in settlement.streets] + [
                [key, label] for key, label in sorted(variants[settlement.code].items())
            ]
        if schedule:
            location["schedule"] = schedule
        locations.append(location)

        for kind in kinds:
            r = schedule.get(kind)
            state = (
                "none"
                if not r
                else "single"
                if "area" in r and not r.get("streets")
                else ("byStreet" if r.get("streets") else "ambiguous")
            )
            stats[f"{kind}.{state}"] += 1

    stats["locations"] = len(locations)
    stats["unmatchedRows"] = len(unmatched)
    report = {"stats": dict(sorted(stats.items())), "unmatched": unmatched}
    if reader or routes:
        report["unknownPlaces"] = unknown_parts
    return locations, report

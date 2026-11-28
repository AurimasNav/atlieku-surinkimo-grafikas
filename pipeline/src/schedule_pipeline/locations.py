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

from .model import Area, Kind, Provider, clean_text
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
    # Streets left out of a row of the whole settlement ("Dituvos k. išskyrus Žiemos g."): they
    # get the rows that name them, or none.
    excluded: frozenset[str] = frozenset()


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


def _typo(a: str, b: str) -> bool:
    """One letter off, or two neighbouring letters swapped ("Klipčšių" for "Klipščių")."""
    if a == b or _one_off(a, b):
        return a != b
    n = len(_common_prefix(a, b))
    return len(a) == len(b) >= 7 and a[n : n + 2] == b[n : n + 2][::-1] and a[n + 2 :] == b[n + 2 :]


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
# A garden community: 'SB „Rasa“', 'S/B "Legotė"', 'SB Prekyba'; Mažeikių r. 2027 writes
# 'Sb „Šaltinėlis“' too. Not a word that starts with "Sb" ("Sbarro"): no IGNORECASE.
_GARDEN = re.compile(
    rf"\bS(?:\s*/?\s*B|b\b)\s*[{_QUOTES}]?\s*([^{_QUOTES}(),]+?)\s*[{_QUOTES}]", re.U
)
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
_ROW_DISTRICT = re.compile(rf"^\s*({_WORD})\s+(?:sen\b\.?|seniūnij\w*)\s*:", re.U)
_GARDENS_OF = re.compile(rf"^({_WORD})\s+sodai$", re.U)
# "Tučiai I ir II", "Sarakai I-II".
_NUMBERED = r"(?: i{1,3})(?:(?: ir)? i{1,3})*"
# "Ryškėnų seniūnija: ..., Žilvičiai_Sodai : Ąžuolas, Klevas": garden communities after it.
# Or "Sodų bendrijos: Alksnėnų k., Kaušėnų k.", in villages of those names.
_GARDENS = re.compile(r"(?:^|[\s_,])Sodai\s*:|\bSodų\s+bendrijos\s*:")
# "1. Plungės m.: Aronijų skg., ...  2. Sodų bendrijos: ...": numbered parts of a row.
_NUMBERED_PART = re.compile(r"(?:^|\s)\d\.\s+(?=[A-ZĄČĘĖĮŠŲŪŽ])")
# "... Žvejeliškės gatvių individualūs namai.", "Varniai gyventojai": private houses,
# residents.
_HOUSES = re.compile(r"(?:\bgatvių\s+)?\bindividualūs\s+namai\b|\bgyventojai\b")


class RouteList:
    """Reads one row of a schedule whose rows are routes of a whole municipality, with no
    eldership column:

        Žagarėlės g. miesto sen., Neries g., M. Pečkauskaitės g. (Vaisių g., Obuolių g.), ...
        Lendriškiai, Laižuva, Lėlaičiai (Tirkšlių sen.), Tučiai I ir II, SB „Linelis“
        Sedos sen: Kalnijos, Užežerė
        Telšių miesto Aukštoji, Degaičių skg., ..., Žvejeliškės gatvių individualūs namai.
        Ryškėnų seniūnija: Brazdeikiai, ..., Žilvičiai_Sodai : Ąžuolas, Klevas, Putinas

    A part is a settlement (nominative), a street of the municipality's town (`route_town`, with
    or without its type), or a garden community: "SB „Linelis“" is offered as one more choice
    in the town's street list; one after "Sodai :" is the streets named after it ("Ąžuolo Sodų
    1-oji g.", ... of Užgiriai). A name that several elderships have is the one of the
    eldership named in the row or, failing that, of the eldership most of the row's other
    settlements are in.
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
        # Rules added for the other municipalities of Telšių RATC (set by MixedRoutes): of the
        # town's streets of one name, only those of the type the row writes (of_its_type); a
        # town street rather than a village's other form (street_rather); "išskyrus" in a
        # village's brackets leaves those streets out; of villages of one name, the one with
        # the streets in brackets. Mažeikių r.'s rows have always been read without them, and
        # its data is kept as it was.
        self.precise = False

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
        if not hits and (short := re.fullmatch(r"([a-z]) (\w+)", key)):
            # "D.Palūkstis" for Didysis Palūkstis.
            pattern = re.compile(rf"{short[1]}\w* {short[2]}")
            hits = [s for s in everything if pattern.fullmatch(fold(s.name))]
        return hits

    def street_rather(self, head: str, spec: str | None, hits: list[Settlement]) -> bool:
        """ "Degaičių" in a list of streets of Telšiai is Degaičių g., not the village
        Degaičiai, and "Žarėnų (nuo 1 iki 45)" some houses of Žarėnų g.: a name that is no
        settlement's own, nor written with a settlement's type or its streets in brackets, and
        is the name of one of the town's streets."""
        key = fold(head)
        if re.search(r"\s(k|vs|mstl|m)\.?$", head) or any(fold(s.name) == key for s in hits):
            return False
        if spec and any(streets_in(spec, s, loose=True) for s in hits):
            return False
        return any(fold(t.name) == key for t in self.town.streets)

    def town_streets(self, part: str) -> set[str]:
        streets = streets_in(part, self.town, loose=True)
        match = re.fullmatch(r"(.+?)\s+(\w+)\.?", part.strip())
        if streets and self.precise:
            return self.of_its_type(part, streets)
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

    def of_its_type(self, part: str, streets: set[str]) -> set[str]:
        """Of the town's streets of one name that `part` names, those of the type it writes:
        "Ežero skg." isn't Ežero g.; without a type ("Ežero", "K. Mindaugo"), the "g."."""
        same: dict[str, list[Street]] = defaultdict(list)
        for street in self.town.streets:
            if street_key(street) in streets:
                same[fold(street.name)].append(street)
        folded = f" {fold(part)} "
        result: set[str] = set()
        for name, found in same.items():
            last = name.split()[-1]
            written = [
                t
                for t in found
                if any(
                    f" {last} {spelling} " in folded
                    for spelling, kind in _STREET_TYPES.items()
                    if kind == _street_type(t)
                )
            ]
            plain = [t for t in found if _street_type(t) == "g"]
            result |= {street_key(t) for t in (written or plain or found)}
        return result

    def named_gardens(self, name: str) -> dict[int, set[str]]:
        """The streets of a garden community named in the nominative after "Sodai :", in any
        settlement: "Ąžuolo Sodų 1-oji g.", ... for Ąžuolas, "Žemaičio Sodų 1-oji g." for
        Žemaitis."""
        stem = re.sub(r"(?:tis|as|is|ys|us|a|e)$", "", fold(name).split()[-1])
        if len(stem) < 4:
            return {}
        pattern = re.compile(re.escape(stem) + r"\w{0,3} sod[ou]\b")
        found: dict[int, set[str]] = {}
        for settlement in self.index.registry.settlements:
            keys = {street_key(t) for t in settlement.streets if pattern.match(fold(t.name))}
            if keys:
                found[settlement.code] = keys
        return found

    def garden_streets(self, label: str) -> set[str]:
        """The town's streets named after a garden community: "Rasos 1-oji g." ... for SB
        „Rasa“, "Ašvos Sodo 2-oji g." for SB „Ašva“. Only numbered and "Sodo" streets: "Ašvos
        g." is an ordinary street. Telšiai: "Ramunės Sodų 1-oji g."."""
        name = fold(label.removeprefix("SB „").removesuffix("“"))
        if len(name) < 4:
            return set()
        pattern = re.compile(re.escape(name[:-1]) + r"\w{0,2}(?: sod[ou])?(?: \d+ \w+)?")
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
        # "Mažeikių m.", "Telšių miesto Aukštoji, ...", "Plungės m.individualių namų: ...".
        town = rf"^\s*{re.escape(self.town.genitive)}\s+(?:m\.|miesto\b(?!\s+sen))"
        text = re.sub(rf"{town}\s*(?:individualių\s+namų\b)?\s*:?", "", text)
        text = re.sub(r"\bmiesto sen\b\.?", "", text)  # "Žagarėlės g. miesto sen."
        text = _NUMBERED_PART.sub(", ", _HOUSES.sub("", text))
        gardens = ""
        if match := _GARDENS.search(text):
            text, gardens = text[: match.start()], text[match.end() :]

        town_streets: set[str] = set()
        # (settlements of one name, eldership named for them, streets in brackets, whether
        # the name is the one of several numbered villages: "Viešvėnai" for Viešvėnai I and
        # II, of which another row may name one)
        named: list[tuple[list[Settlement], str | None, str | None, bool]] = []
        streets_of: dict[int, set[str]] = defaultdict(set)
        parts = [(part, False) for part in split_places(text)]
        parts += [(part, True) for part in split_places(gardens)]
        for part, in_gardens in parts:
            if part.startswith("(") and part.endswith(")"):
                # "(Austelės g. ir L. Andrijausko 2;2A, Siraičiai)": streets of the place last.
                inside, _, last = part[1:-1].rpartition(",")
                if inside and self.settlements(last):
                    part = f"{last.strip()} ({inside})"
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
            if hits and self.precise and self.street_rather(head, spec, hits):
                hits = []
            if hits:
                district = row_district
                if spec and (match := _PART_DISTRICT.search(spec)):
                    district, spec = self.index.district(match.group(1)), None
                key = re.escape(fold(head))
                numbered = len(hits) > 1 and all(
                    re.fullmatch(key + _NUMBERED, fold(s.name)) for s in hits
                )
                named.append((hits, district, spec, numbered))
                continue
            if in_gardens:
                # "Sodai : Ąžuolas": the streets "Ąžuolo Sodų 1-oji g." ... of any settlement.
                found_gardens = self.named_gardens(head)
                for code, keys in found_gardens.items():
                    streets_of[code] |= keys
                if not found_gardens:
                    self.unknown.append(part)
                continue
            streets = self.town_streets(part)
            if streets:
                town_streets |= streets
            else:
                self.unknown.append(part)

        # Where most of the row is: decides between villages of the same name.
        sure = [hits[0].district for hits, *_ in named if len({s.district for s in hits}) == 1]
        common = [district for district, _ in Counter(sure).most_common()]
        clauses: list[tuple[Settlement, Clause]] = []
        for hits, district, spec, numbered in named:
            fallback = numbered
            districts = {s.district for s in hits}
            if len(districts) > 1 and spec and self.precise:
                # "Kalniškiai (Giraitės g.)": the Kalniškiai that has a Giraitės g.
                streets = [s for s in hits if streets_in(spec, s, loose=True)]
                if len({s.district for s in streets}) == 1:
                    hits, districts = streets, {streets[0].district}
            if len(districts) > 1:
                wanted = district if district in districts else None
                wanted = wanted or next((d for d in common if d in districts), None)
                if wanted:
                    hits = [s for s in hits if s.district == wanted]
                else:
                    fallback = True
            for settlement in hits:
                streets = streets_in(spec, settlement, loose=True) if spec else None
                if self.precise and spec and _EXCEPT.match(spec.strip()):
                    # "Pakerai (išskyrus Skalsos g.)": the rest of the village.
                    left_out = frozenset(streets or ())
                    clause = Clause(area.id, None, fallback=fallback, excluded=left_out)
                    clauses.append((settlement, clause))
                    continue
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
            (s.code, key)
            for s, c in clauses
            for key in [*(sorted(c.streets) if c.streets else [""]), *(f"-{k}" for k in c.excluded)]
        )


# --- Gargždų švara: a settlement per row ------------------------------------------------

# "Aukštkiemių k.", "Klemiškės II k.", "Saulažolių k.- (...)": the genitive and the type.
_ROW_HEAD = re.compile(r"^(?P<name>.+?)\s+(?P<type>k|vs|mstl|m)\s*\.(?=[\s(\-–]|$)", re.U)
# Rows of businesses ("įmonės", "Gobergiškės įm."), a military area, a filling station.
_NOT_HOMES_ROW = re.compile(r"(?i:\bįmon\w*|\bįm\.|\bpoligon\w*|\bdegalin\w*)")
_SHARED_ROW = re.compile(r"(?i:\bbendr\w*\s+naudojim\w*)")
_ELDERSHIP_ONLY = re.compile(rf"^\(?\s*({_WORD})\s+sen\b\.?\s*\)?$", re.U)
# "Dituvos g. (nuo Nidos g. link Priekulės m.)": the street is listed in full in every row that
# has a part of it, and the user picks the row; the streets named for the range aren't in it.
_RANGE_BRACKET = re.compile(r"\([^()]*\b(?:nuo|iki)\b[^()]*\)", re.I)
# "J. Basanavičiaus g. ( Išskyrus Basanavičiaus g. 68, ...)": a few houses left out; the
# street stays in the row.
_HOUSES_LEFT_OUT = re.compile(r"\(\s*i[sš]+kyrus\b[^()]*\d[^()]*\)", re.I)
# "Gedimino g. 17", "Smilgų g. poriniai namai": some houses of the street.
_SOME_HOUSES = re.compile(r"\b(?:g|pl|al|skg|sk|aklg|tak|kel)\s*\.?\s*\d|porin", re.I)
# Street types as the schedule writes them (folded) and as the register abbreviates them.
_STREET_TYPES = {
    "g": "g",
    "gatve": "g",
    "skg": "skg",
    "sk": "skg",
    "skr": "skg",
    "tak": "tak",
    "takas": "tak",
    "al": "al",
    "aleja": "al",
    "aklg": "aklg",
    "akl": "aklg",
    "pl": "pl",
    "a": "a",
    "kel": "kel",
    "kelias": "kel",
}
_STREET_TYPE = re.compile(rf" ({'|'.join(_STREET_TYPES)})(?: \d+ ?[a-z]?)?(?= )")


def _street_type(street: Street) -> str:
    abbr = fold(street.abbr)
    return _STREET_TYPES.get(abbr, abbr)


def typed_streets(part: str, settlement: Settlement) -> set[str]:
    """The streets of `settlement` one part of a list names ("tik Airių g.", "Gedimino sk.
    34"). Only parts with a street type: "naujoji Kalotė" isn't "Naujoji g."."""
    folded = f" {fold(part)} "
    types = {_STREET_TYPES[m.group(1)] for m in _STREET_TYPE.finditer(folded)}
    if not types:
        return set()
    found = streets_in(part, settlement, loose=True)

    def written_with_its_type(street: Street) -> bool:
        # "Gedimino g." isn't "Gedimino skg.", which streets_in can't tell apart.
        kind = _street_type(street)
        last = fold(street.name).split()[-1]
        return any(
            f" {last} {spelling} " in folded
            for spelling, same in _STREET_TYPES.items()
            if same == kind
        )

    typed = {
        street_key(t)
        for t in settlement.streets
        if street_key(t) in found and written_with_its_type(t)
    }
    if typed or found:
        return typed or found
    # A typo in the name ("Moctaičių g." for "Mostaičių g."), if only one street of that type
    # is that close.
    words = fold(re.sub(r"\d.*$", "", part)).split()
    close = {
        street_key(t)
        for t in settlement.streets
        if _street_type(t) in types
        and (n := len(fold(t.name).split())) < len(words)
        and _typo(" ".join(words[-n - 1 : -1]), fold(t.name))
    }
    return close if len(close) == 1 else set()


class SettlementRows:
    """Reads one row of a schedule whose rows are one settlement each, in the genitive with its
    type, then which of its streets the row is for:

        Ablingos k.
        Aukštkiemių k. - tik Airių g., Architektų a., ...       only these streets
        Aukštkiemių k. (išskyrus Aukštučių g., Gavaitės g.)    the rest of the settlement
        Girininkų k. - Judrėnų sen.                            of two villages of that name
        Kiškėnų k. - (tik SB "Tolupis")                        a garden community
        Dovilų mstl. - tik bendro naudojimo                    shared containers
        Kalotės k. - naujoji Kalotė                            a part named in words

    A row for the rest of a settlement leaves its excluded streets to the rows that name them.
    A part named in words is one more candidate row for the settlement: the user picks it by
    its name. The lists of streets leave out new streets, so a street no row names is offered
    the settlement's rows of that kind to choose from. Rows of businesses aren't homes and are
    skipped.
    """

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.places = [s for s in index.registry.settlements if s.district in provider.elderships]
        self.unknown: list[str] = []

    def settlements(self, name: str, abbr: str | None) -> list[Settlement]:
        key = fold(name)
        hits = [s for s in self.places if key in (fold(s.genitive), fold(s.name))]
        if not hits:
            # A typo ("Gargdždų m.", "Klipčšių k."), if only one name is that close.
            near = [s for s in self.places if _typo(key, fold(s.genitive))]
            if len({s.genitive for s in near}) == 1:
                hits = near
        typed = [s for s in hits if abbr and s.abbr == f"{abbr}."]
        return typed or hits

    def street(self, part: str, settlement: Settlement) -> set[str]:
        return typed_streets(part, settlement)

    def streets(self, text: str, settlement: Settlement, where: str) -> tuple[set[str], list]:
        """The streets a list names, and its gardens (variant key, label). Parts that look like
        a street but name none of the settlement's are reported."""
        keys: set[str] = set()
        gardens: list[tuple[str, str]] = []
        for part in re.split(r"[,;()]", text):
            part = part.strip(" .-–:")
            if not part:
                continue
            if garden := garden_label(part):
                gardens.append(garden)
                continue
            found = self.street(part, settlement)
            keys |= found
            if not found and _STREET_TYPE.search(f" {fold(part)} "):
                self.unknown.append(f"{where}: {part[:60]}")
        return keys, gardens

    def row_clauses(self, area: Area, settlement: Settlement, spec: str, shared: bool) -> list:
        """What one row says about `settlement`, from the text after its name."""
        where = f"{settlement.genitive} {settlement.abbr}"
        if fold(spec).startswith("nuo "):
            # "nuo Klaipėdos pusės iki Pervalkos g.": a part named in words.
            return [Clause(area.id, None, extra=shared)]
        text = _HOUSES_LEFT_OUT.sub(" ", _RANGE_BRACKET.sub(" ", spec))
        before, after = text, None
        if match := _EXCEPT.search(text):
            before = text[: match.start()]
            # Streets left out only in part ("Smilgų g. poriniai namai") stay in the row.
            after = ",".join(
                p for p in re.split(r"[,;()]", text[match.end() :]) if not _SOME_HOUSES.search(p)
            )
        named, gardens = self.streets(before, settlement, where)
        excluded, gardens_out = self.streets(after, settlement, where) if after else (set(), [])
        # Garden communities are choices next to the streets: 'Kiškėnų k. - (tik SB "Tolupis")',
        # or the gardens a list of streets names ('..., Žvejų g., SB "Minija"').
        for key, label in gardens + gardens_out:
            self.variants[settlement.code].setdefault(key, label)
        mine = {key for key, _ in gardens}
        if named or (mine and after is None):
            # "Gargždų m. - (..., Žiburių g., išskyrus Rasos g., ...)"
            return [Clause(area.id, (named - excluded) | mine, extra=shared)]
        if after is not None:
            # "Dituvos k. (išskyrus Žiemos g., ...)", 'Kiškėnų k. - (išskyrus SB "Tolupis")'.
            excluded |= {key for key, _ in gardens_out}
            rest = Clause(area.id, None, extra=shared, excluded=frozenset(excluded))
            return [rest] + ([Clause(area.id, mine, extra=shared)] if mine else [])
        if _STREET_TYPE.search(f" {fold(text)} "):
            return [Clause(area.id, set(), extra=shared)]  # streets we don't recognise
        # "naujoji Kalotė", "tik bendro naudojimo", or nothing: the whole settlement.
        return [Clause(area.id, None, extra=shared)]

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        """Returns the clauses and whether the row is for something other than homes."""
        self.unknown = []
        text = clean_text(area.name)
        if _NOT_HOMES_ROW.search(text):
            return [], True
        shared = bool(_SHARED_ROW.search(text))
        head = _ROW_HEAD.match(text)
        if not head:
            # 'SB "Vaiteliai" (Bendro naudojimo konteineriai)': the garden of the village of its
            # name.
            garden = garden_label(text) if fold(text).startswith("sb ") else None
            hits = self.settlements(garden[1][4:-1], None) if garden else []
            if garden and len(hits) == 1:
                self.variants[hits[0].code].setdefault(*garden)
                return [(hits[0], Clause(area.id, {garden[0]}, extra=shared))], False
            self.unknown.append(text[:80])
            return [], False
        hits = self.settlements(head.group("name"), head.group("type"))
        if not hits:
            self.unknown.append(head.group(0))
            return [], False
        spec = text[head.end() :].strip(" -–:")
        if match := _ELDERSHIP_ONLY.match(spec):
            district = self.index.district(match.group(1))
            hits = [s for s in hits if s.district == district]
            if not hits:
                self.unknown.append(text[:80])
            return [(s, Clause(area.id, None, extra=shared)) for s in hits], False
        return [(s, c) for s in hits for c in self.row_clauses(area, s, spec, shared)], False


# --- Tauragės RATC: routes in sections -----------------------------------------------------

# "Šimkaičių sen.:", "JURBARKŲ SENIŪNIJA:", "JURBARKO MIESTO SENIŪNIJA:", "JURBARKŲ SENIŪNIJA",
# "Žemaičių Kalvarijos sen.:".
_SECTION = re.compile(
    rf"\b({_WORD}(?:\s+{_WORD})?(?:\s+(?i:miesto))?)\s+(?i:sen\b\.?|seniūnija\b)\s*:?", re.U
)
# Villages of one name, numbered: "Jokūbaičių I ir II k.", "Skirsnemuniškių I, II ir III k.".
_NUMERALS = r"I{1,3}(?:\s*(?:,|ir)\s*I{1,3})*"
_SETTLEMENT_TYPES = {"k": "k.", "vs": "vs.", "mstl": "mstl.", "m": "m."}
# A settlement or a street with its type, and house numbers: "Paalsio II k.", "Ryto g.15",
# "Lauko g 2B", "Pušų 14", "Jurbarkas".
_SECTION_ITEM = re.compile(
    rf"(?P<name>.+?)(?:\s+(?P<numerals>{_NUMERALS}))?"
    r"(?:\s+(?P<type>k|vs|mstl|m|g|al|pl|skg|aklg|tak|a)\b\.?)?"
    r"(?:\s*(?P<houses>\d+\s*[A-Za-z]?(?:\s*[,;]\s*\d+\s*[A-Za-z]?)*))?",
    re.U,
)
_HOUSE = re.compile(r"\d+\s*[A-Za-z]?")
# The spellings of the publisher, as the register writes them: "Kalnėnų kaimas", "Jurbarko
# miestas", "Skirsnemunės mst.", "Pilies I k,", "Jokūbaičių k. I (...)".
_SPELLINGS = (
    (re.compile(r"\bkaima[si]\b", re.I), "k."),
    (re.compile(r"\bmiestas\b", re.I), "m."),
    (re.compile(r"\bmst\.(?=\s|,|$)"), "mstl."),
    (re.compile(r"\b(k|vs|mstl|m)(?=\s*[,;]|\s*$)"), r"\1."),
    (re.compile(r"\b(k|vs|mstl|m)\.\s+(I{1,3})(?=\s*[(,;]|\s*$)"), r"\2 \1."),
)


def _section_parts(text: str) -> list[str]:
    """Splits a list at the commas and semicolons between places, not those inside brackets or
    between numerals ("Skirsnemuniškių I, II ir III k."), and where a comma is missing before a
    capital: after a type, a bracket or a house number ("Motiškių k. Eimučių k.", "Rukšnių k.
    Piliakalnio g. Vajotų k.", "(Vytauto Didžiojo g.) Naujasodžių k.", "Lauko g 2B Jurbarkų
    k.")."""
    parts: list[str] = []
    depth, start = 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth:
            continue
        elif ch in ",;" and not re.match(rf"\s*{_NUMERALS}\b", text[i + 1 :]):
            parts.append(text[start:i])
            start = i + 1
        elif (
            ch.isspace()
            and re.search(r"(?:\b(?:k|vs|mstl|m|g)\.|\)|\b\d+[A-Za-z]?)$", text[start:i])
            and re.match(rf"\s*[{_UPPER}]", text[i:])
        ):
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip(" ,;:") for p in parts if p.strip(" ,;:.")]


@dataclass(eq=False)
class _Stop:
    """What one route says about one settlement."""

    settlement: Settlement
    streets: set[str] | None = None  # None: the whole settlement
    houses: set[str] = field(default_factory=set)  # streets of which only some houses
    excluded: set[str] = field(default_factory=set)

    def add(self, keys: set[str], houses: bool) -> None:
        if not keys:
            return
        if self.streets is None:
            self.streets = set()
        if houses:
            self.houses |= keys
            self.streets -= keys
        else:
            self.streets |= keys

    def clauses(self, area_id: str) -> list[Clause]:
        if self.streets is None:
            return [Clause(area_id, None, excluded=frozenset(self.excluded))]
        result = [Clause(area_id, set(self.streets))] if self.streets else []
        if houses := self.houses - self.streets:
            result.append(Clause(area_id, houses, extra=True))
        # Only streets we don't recognise: some of the settlement, not the whole.
        return result or [Clause(area_id, set())]


class SectionRoutes:
    """Reads one row of a schedule whose rows are routes through several elderships, each
    named before its settlements (genitive with the type, or nominative), and through streets
    of the municipality's town (`section_town`):

        Jurbarko m., privačių namų konteineriai gatvėse: Dainių g., Eglių g., ...
        Jurbarkų sen.: Jurbarkų k., Dainių k. (Užtvankos g., Vakaro g.), Klišių k. (Eržvilko g.
        14), Naujasodžių k. (išskyrus Kauno g. 99, ...; Obelų g., Dariaus ir Girėno g.)
        Skirsnemunės sen.: Skirsnemunės mstl., Skirsnemuniškių I, II ir III k.
        JURBARKO MIESTO SENIŪNIJA: Jurbarkas, Ryto g.15,16; Lauko g. 20, 22, 24
        JURBARKŲ SENIŪNIJA: Naujasodžių kaimas Dariaus ir Girėno g. 138a, 103; Kauno g.

    A settlement is looked up in its eldership only. Streets in brackets or after its name are
    the only ones of the route; with house numbers, the route is one more choice for that street
    next to the route of the rest of it; "išskyrus" leaves streets to the routes that name them
    (only some houses left out: the street stays). Streets named before any settlement in the
    town's section are the town's. A bracket without a street ("Naukaimio k. (Vadžgirys)") tells
    villages of one name apart, which the eldership already does, or `Provider.aliases`.

    A village the row puts in another eldership ("Viešvilės sen.: Kazikėnų k.", of Smalininkų
    sen.) is the only one of that name, if no row of its kind names it in its own eldership
    (`prepare`): if one does, the other is a place the register doesn't know.
    """

    def __init__(self, index: Index, provider: Provider, variants: dict[int, dict[str, str]]):
        self.index = index
        self.provider = provider
        self.variants = variants
        self.town = next(
            s
            for s in index.registry.settlements
            if s.name == provider.section_town and s.abbr == "m."
        )
        # "Jurbarko m., privačių namų konteineriai gatvėse:"
        self.town_mark = re.compile(rf"\b{re.escape(self.town.genitive)}\s+m\.\s*(?:,[^,:]*)?:")
        # Towns whose routes name the streets of private houses (build_locations).
        self.towns_by_street = {self.town.code}
        self.unknown: list[str] = []
        # Settlements the rows of each kind name in their own eldership; None before prepare.
        self.named: dict[str, set[int]] | None = None
        self.kind = ""  # of the row being read

    def prepare(self, areas: list[Area]) -> None:
        """First pass: the settlements the rows of each kind name in their own eldership."""
        named: dict[str, set[int]] = defaultdict(set)
        for area in areas:
            named[area.kind] |= {s.code for s, _ in self.clauses(area)[0]}
        self.named = named

    def settlements(
        self, name: str, numerals: str | None, kind: str | None, district: str
    ) -> list[Settlement]:
        names = [f"{name} {n}" for n in re.findall(r"I{1,3}", numerals)] if numerals else [name]
        hits: list[Settlement] = []
        for one in names:
            key = fold(one)
            if numerals:
                # Only the same number: "Balnių I" is near "Balnių II" to Index.candidates.
                found = [s for s in self.index.by_name.get(key, []) if s.district == district]
                if not found and one.endswith(" I"):
                    # "Balnių I ir II k.": the register calls the first one Balniai.
                    plain = self.index.by_name.get(fold(one[:-2]), [])
                    found = [s for s in plain if s.district == district]
            else:
                found = self.index.candidates(one, district, strict=True)
            if not found:
                # A typo ("Batraitiškės k." for "Baltraitiškės"), if only one name is that close.
                found = [
                    s
                    for s in self.index.registry.settlements
                    if s.district == district
                    and (_one_off(key, fold(s.genitive)) or _one_off(key, fold(s.name)))
                ]
                found = found if len({s.code for s in found}) == 1 else []
            if not found and self.named is not None:
                # In another eldership: the only one of that name, if no row names it in its own.
                elsewhere = [
                    s
                    for s in self.index.by_name.get(key, [])
                    if s.district in self.provider.elderships
                ]
                if len(elsewhere) == 1 and elsewhere[0].code not in self.named[self.kind]:
                    found = elsewhere
            abbr = _SETTLEMENT_TYPES.get(kind or "")
            # A town is "m." or "mstl.": "Smalininkų mstl." is Smalininkai m., not the village.
            wanted = {"m.": ("m.", "mstl."), "mstl.": ("mstl.", "m.")}.get(abbr or "", (abbr,))
            typed = next((t for a in wanted if (t := [s for s in found if s.abbr == a])), [])
            hits += typed or found
        return list({s.code: s for s in hits}.values())

    def streets(
        self, settlement: Settlement, part: str, name: str, kind: str | None, loose: bool = True
    ) -> set[str]:
        """The streets of `settlement` a part names: "Ryto g.15", "Pušų 14", "Putinų g." (a
        different ending of Putino g., if only one street is that close). Not `loose`, only the
        name as it is: "Smukučiai" (a part of Jurbarkas) isn't Smukučių g."""
        found = typed_streets(part, settlement) if kind else streets_in(name, settlement, True)
        if found or not loose:
            return found
        key = fold(name)
        close = {
            street_key(t)
            for t in settlement.streets
            if (_near(key, fold(t.name)) or _one_off(key, fold(t.name)))
            and (not kind or _street_type(t) == _STREET_TYPES.get(kind))
        }
        return close if len(close) == 1 else set()

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        self.unknown = []
        self.kind = area.kind
        text = clean_text(area.name)
        for written, registered in self.provider.aliases:
            text = text.replace(written, registered)
        for pattern, replacement in _SPELLINGS:
            text = pattern.sub(replacement, text)
        marks = []
        for m in _SECTION.finditer(text):
            name, start = m.group(1), m.start(1)
            district = self.index.district(name)
            if district not in self.provider.elderships and " " in name:
                # Of two words, an eldership's name is only the second ("Babrungo"), unless both
                # are ("Žemaičių Kalvarijos").
                rest = name.split(maxsplit=1)[1]
                district, start = self.index.district(rest), start + name.index(rest)
            marks.append((start, m.end(), district))
        marks += [(m.start(), m.end(), self.town.district) for m in self.town_mark.finditer(text)]
        marks.sort()
        lead = text[: marks[0][0]] if marks else text
        if lead.strip(" .,;:"):
            self.unknown.append(lead.strip()[:80])
        stops: list[_Stop] = []
        for i, (start, end, district) in enumerate(marks):
            until = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            if district in self.provider.elderships:
                stops += self.section(district, text[end:until])
            else:
                self.unknown.append(text[start:end])
        return [(s.settlement, c) for s in stops for c in s.clauses(area.id)], False

    def section(self, district: str, text: str) -> list[_Stop]:
        """The settlements of one eldership's section, and their streets."""
        stops: list[_Stop] = []
        current: list[_Stop] = []  # the settlement the streets after it belong to
        last: list[tuple[_Stop, set[str]]] = []  # the last street, for house numbers after it
        for part in _section_parts(text):
            head, _, rest = part.partition("(")
            spec = rest.rsplit(")", 1)[0] if rest else None
            head = head.strip(" ,;:")
            if spec is not None and "isvez" in fold(spec):
                spec = None  # "(atliekos išvežamos į Pašilio g. ...)": where the waste is taken
            if _HOUSE.fullmatch(head):
                # "Dariaus ir Girėno g. 138a, 103": more houses of that street.
                for stop, keys in last:
                    stop.add(keys, houses=True)
                continue
            match = _SECTION_ITEM.fullmatch(head)
            name, numerals, kind = match.group("name", "numerals", "type") if match else ("",) * 3
            houses = bool(match and match.group("houses"))
            places: list[Settlement] = []
            if match and (kind in _SETTLEMENT_TYPES or numerals or not (kind or houses)):
                places = self.settlements(name, numerals, kind, district)
            if match and not places and kind not in _SETTLEMENT_TYPES:
                # A street of the settlement before it, or of the town in its own section.
                targets = current
                if not targets and district == self.town.district:
                    town = next((s for s in stops if s.settlement is self.town), None)
                    targets = [town or _Stop(self.town)]
                # Only a name written as a street is matched loosely.
                loose = bool(kind or houses)
                found = [(t, self.streets(t.settlement, head, name, kind, loose)) for t in targets]
                if any(keys for _, keys in found):
                    last = [(t, keys) for t, keys in found if keys]
                    for target, keys in last:
                        target.add(keys, houses)
                        if target not in stops:
                            stops.append(target)
                    continue
                if kind == "g":
                    # "Raudonėnų g." for the village Raudonėnai.
                    places = self.settlements(name, None, None, district)
            if not places:
                self.unknown.append(f"{district} sen.: {head[:60]}")
                current, last = [], []
                continue
            current, last = [_Stop(s) for s in places], []
            stops += current
            if spec is not None:
                self.spec(current, spec)
        return stops

    def spec(self, stops: list[_Stop], spec: str) -> None:
        """A bracket after a settlement's name: its streets, houses, or streets left out."""
        excluding = bool(_EXCEPT.match(spec.strip()))
        text = _EXCEPT.sub("", spec, count=1) if excluding else spec
        last: list[tuple[_Stop, set[str]]] = []
        for part in _section_parts(text):
            if _HOUSE.fullmatch(part):
                for stop, keys in [] if excluding else last:
                    stop.add(keys, houses=True)
                continue
            match = _SECTION_ITEM.fullmatch(part)
            if not match or not (_STREET_TYPE.search(f" {fold(part)} ") or match["houses"]):
                continue  # "(Vadžgirys)": which of two villages, not a street
            houses = bool(match["houses"])
            last = []
            for stop in stops:
                keys = self.streets(stop.settlement, part, match["name"], match["type"])
                if not keys:
                    where = f"{stop.settlement.genitive} {stop.settlement.abbr}"
                    self.unknown.append(f"{where}: {part[:60]}")
                elif excluding:
                    # Only some houses left out: the rest of the street stays in the route.
                    stop.excluded |= set() if houses else keys
                else:
                    stop.add(keys, houses)
                    last.append((stop, keys))

    def signature(self, area: Area) -> frozenset:
        """What the row covers, to tell whether two years' rows are the same route."""
        clauses, _ = self.clauses(area)
        return frozenset(
            (s.code, key, c.extra)
            for s, c in clauses
            for key in [*(sorted(c.streets) if c.streets else [""]), *(f"-{k}" for k in c.excluded)]
        )


# An eldership's section of a route: "Šateikių sen.:", "Žemaičių Kalvarijos sen.:".
_SECTIONED = re.compile(rf"\b{_WORD}(?:\s+(?i:miesto))?\s+sen\.\s*:", re.U)


class MixedRoutes:
    """Routes of both shapes in one provider's files, each read by the reader of its shape:
    those in elderships' sections ("Šateikių sen.: Aleksandravo k., ...", the mixed waste files
    of Plungės r. and Rietavo sav.) by SectionRoutes, lists of places ("Paežerė, Grumbliai,
    Tarvainiai (Miško g., ...)", their packaging files) by RouteList.

    No town gets "no pickup" for a street no route names (build_locations): those of Telšiai
    left out of the file include streets of private houses (Išdegos Pušies g., Džiugailės g.),
    and none of the files lists the apartment buildings' streets. The app offers the town's
    routes instead."""

    towns_by_street: set[int] = set()

    def __init__(self, routes: RouteList, sections: SectionRoutes):
        self.routes = routes
        self.routes.precise = True
        self.sections = sections
        self.unknown: list[str] = []

    def reader(self, area: Area) -> RouteList | SectionRoutes:
        return self.sections if _SECTIONED.search(area.name) else self.routes

    def prepare(self, areas: list[Area]) -> None:
        self.sections.prepare([a for a in areas if self.reader(a) is self.sections])

    def clauses(self, area: Area) -> tuple[list[tuple[Settlement, Clause]], bool]:
        reader = self.reader(area)
        found = reader.clauses(area)
        self.unknown = reader.unknown
        return found

    def signature(self, area: Area) -> frozenset:
        return self.reader(area).signature(area)


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
    for c in named:
        for key in c.excluded:
            by_street.setdefault(key, set())  # so the row of the whole doesn't apply to it
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
    rows = (
        SettlementRows(index, provider, variants) if provider and provider.settlement_rows else None
    )
    sections = (
        SectionRoutes(index, provider, variants) if provider and provider.section_town else None
    )
    # A provider's own reader (Provider.reader), e.g. sratc.Blocks, aratc.Routes.
    own = provider.reader(index, provider, variants) if provider and provider.reader else None
    # Both: rows of either shape (MixedRoutes).
    mixed = MixedRoutes(routes, sections) if routes and sections else None
    # Towns whose routes name every street with a pickup (SectionRoutes and aratc.Routes).
    towns_by_street = getattr(mixed or sections or own, "towns_by_street", set())
    # Readers of rows that cover the whole municipality, without an eldership column.
    municipal = mixed or routes or rows or sections or own
    reader = PlaceList(index, provider, variants, None) if provider and place_lists else None
    kinds = list(provider.kinds) if provider else KINDS
    if reader:
        # First pass: where the garden communities are, from rows that say so.
        for area in areas:
            reader.clauses(area)
        reader.gardens = known_gardens(registry, variants)
    if sections:
        (mixed or sections).prepare(areas)
    if own:
        own.prepare(areas)

    for area in areas:
        wholes: list = []
        skipped = False
        if municipal:
            found, skipped = municipal.clauses(area)
            unknown_parts += [f"{area.kind}: {part[:80]}" for part in municipal.unknown]
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

        simplify = place_lists or bool(municipal)
        schedule = {kind: r for kind in kinds if (r := resolve(clauses.get(kind, []), simplify))}
        town = settlement.code in towns_by_street
        # MixedRoutes: neither its towns nor its villages; the app offers their rows for a
        # street no route names.
        if (routes and not mixed) or town:
            # A route names every street it serves, so a street no route names has no pickup
            # (apartment buildings with shared containers, gardens without food waste). An
            # empty list says so; without it the app would offer every row of the town. Not
            # for SettlementRows: its lists of streets leave out new streets, whose houses
            # are served, so the app offers the settlement's rows. SectionRoutes' town: its
            # routes name the streets of private houses, but not each one for every kind (Bočių
            # g. of Jurbarkas has green waste, no mixed waste route): only a street no route of
            # any kind names has none.
            every = [street_key(t) for t in settlement.streets] + sorted(variants[settlement.code])
            if town:
                named = {key for r in schedule.values() for key in r.get("streets", {})}
                every = [key for key in every if key not in named]
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
    if reader or municipal:
        report["unknownPlaces"] = unknown_parts
    return locations, report

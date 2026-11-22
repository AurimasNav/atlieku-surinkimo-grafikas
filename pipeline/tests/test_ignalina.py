"""Ignalinos r.: the pages of SĮ „Kompata“, its PDFs of mixed waste, packaging and food waste,
their rows, the half years that cross the new year, and the published folder."""

import json
from collections import Counter
from datetime import date, timedelta

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import build, ignalina, regions, snapshot, status
from schedule_pipeline.build import ValidationError, build_dataset, merge_parts
from schedule_pipeline.model import Area, ParseResult
from schedule_pipeline.registry import Registry

REGISTRY = Registry.load(FIXTURES / "ignalina" / "registry-ignalinos-r-2026-11-22.json")
TODAY = date(2026, 11, 22)
FILES = "https://site-2329934.mozfiles.com/files/2329934/"
# The pages (mixed waste, packaging, food waste) and their copies in fixtures/ignalina/.
PAGES = dict(zip(ignalina.PAGES, ("komunaliniu.html", "pakuociu.html", "maisto.html"), strict=True))
# The files the pages link for the whole municipality, and their copies.
COPIES = {
    "Komunaliniu_atlieku_surinkimo_is_individualiu_konteineriu_2026m_-_2027m_11-04men-1.pdf": (
        "misrios-2026-11-2027-04.pdf"
    ),
    "2026_metu_plastiko__popieriaus__metalo__stiklo_pakuociu_surinkimo_is_individualiu"
    "_konteineriu_grafikas__atsisiusti_PDF_-1.pdf": "pakuotes-2026.pdf",
    "Maisto_atlieku_isvezimo_grafikas_2026-2027m_.pdf": "maisto-2026-11-2027-04.pdf",
}


def page_files(url):
    return ignalina.find_files(fixture(f"ignalina/{PAGES[url]}").decode("utf-8"), url)


(MIXED,), _ = page_files(ignalina.PAGES[0])
(PACKAGING,), _ = page_files(ignalina.PAGES[1])
(FOOD,), _ = page_files(ignalina.PAGES[2])


def content(file):
    return fixture(f"ignalina/{COPIES[file.file_name]}")


def parsed(file):
    return ignalina.parse_file(file, content(file))


def schedule_file(kind, start, end, name=None):
    name = name or f"{kind}-{start}-{end}.pdf"
    return ignalina.ScheduleFile(kind, f"{FILES}{name}", name, start=start, end=end)


@pytest.fixture(scope="module")
def part():
    files = [(f, content(f)) for f in (MIXED, PACKAGING, FOOD)]
    return build_dataset(files, REGISTRY, TODAY, 31, ignalina.SOURCE)


def place(data, name, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name and district in (None, loc["district"])
    )


def row(data, area_id):
    return next(a for a in data["areas"] if a["id"] == area_id)


def rows_of(data, name, kind, street=None, district=None):
    """The names of the rows of a place, or of one of its streets."""
    location = place(data, name, district)
    schedule = location["schedule"][kind]
    if street is None:
        ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    else:
        key = next(k for k, label in location["streets"] if label == street)
        ids = schedule["streets"][key]
    return sorted(row(data, i)["name"] for i in ids)


def by_name(result, name, kind="household"):
    return next(a for a in result.areas if a.kind == kind and a.name == name)


# --- the pages ---------------------------------------------------------------


def test_finds_the_files_by_their_links():
    assert (MIXED.kind, MIXED.start, MIXED.end) == (
        "household",
        date(2026, 11, 1),
        date(2027, 4, 30),
    )
    assert (PACKAGING.kind, PACKAGING.start, PACKAGING.end) == (
        "packaging",
        date(2026, 1, 1),
        date(2026, 12, 31),
    )
    assert (FOOD.kind, FOOD.start, FOOD.end) == ("food", date(2026, 11, 1), date(2027, 4, 30))
    assert MIXED.url == f"{FILES}{MIXED.file_name}"
    assert MIXED.months == [(2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3), (2027, 4)]
    assert [m for _, m in PACKAGING.months] == list(range(1, 13))


def test_the_elderships_parts_and_the_gardens_are_not_read():
    # The mixed waste page links 13 PDFs: the municipality's, the garden communities' (October
    # to December) and the parts of the town and the 11 elderships in 11 files ("Ceikinių
    # seniūnija (atsisiųsti PDF)"); the packaging page 12, the food waste page 4. Only the
    # municipality's are read, without warnings.
    for url, count in zip(ignalina.PAGES, (13, 12, 4), strict=True):
        assert fixture(f"ignalina/{PAGES[url]}").decode("utf-8").count(".pdf") == count
        files, warnings = page_files(url)
        assert len(files) == 1 and warnings == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "KOMUNALINIŲ ATLIEKŲ SURINKIMO IŠ INDIVIDUALIŲ KONTEINERIŲ 2026 M. LAPKRIČIO MĖN. - "
            "2027 M. BALANDŽIO MĖN. GRAFIKAS",
            (date(2026, 11, 1), date(2027, 4, 30)),
        ),
        (
            "MAISTO ATLIEKŲ SURINKIMO IŠ INDIVIDUALIŲ KONTEINERIŲ 2026 - 2027 METŲ LAPKRIČIO - "
            "BALANDŽIO MĖN. GRAFIKAS*",
            (date(2026, 11, 1), date(2027, 4, 30)),
        ),
        (
            "Komunaliniu_atlieku_surinkimo_is_individualiu_konteineriu_2026m_-_2027m_11-04men-1.pdf",
            (date(2026, 11, 1), date(2027, 4, 30)),
        ),
        # One year: the months after the last are of the next.
        ("2026 m. lapkričio–balandžio mėn.", (date(2026, 11, 1), date(2027, 4, 30))),
        ("2027 m. gegužės - spalio mėn.", (date(2027, 5, 1), date(2027, 10, 31))),
        ("2026 M. SPALIO - GRUODŽIO MĖN.", (date(2026, 10, 1), date(2026, 12, 31))),
        (
            "2026 metų plastiko, popieriaus, metalo, stiklo pakuočių surinkimo iš individualių "
            "konteinerių grafikas (atsisiųsti PDF)",
            (date(2026, 1, 1), date(2026, 12, 31)),
        ),
        ("Grafikas (atsisiųsti PDF)", None),
        ("2026 m. sausio, vasario ir kovo mėn.", None),
        ("2025-2027 m.", None),
    ],
)
def test_periods(text, expected):
    assert ignalina.period(text) == expected


def test_reads_the_files_with_dates_still_to_publish():
    selected, warnings = ignalina.select_files([MIXED, PACKAGING, FOOD], TODAY)
    assert selected == [MIXED, PACKAGING, FOOD] and warnings == []
    # In February, last year's packaging is still read until a month after its end, and alone
    # while no newer file is linked.
    selected, _ = ignalina.select_files([MIXED, PACKAGING, FOOD], date(2027, 3, 1))
    assert selected == [MIXED, PACKAGING, FOOD]


def test_the_next_half_year_is_read_when_it_is_linked():
    following = schedule_file("household", date(2027, 5, 1), date(2027, 10, 31))
    files = [following, MIXED, PACKAGING]
    selected, _ = ignalina.select_files(files, date(2027, 4, 27))
    assert selected == [MIXED, following, PACKAGING]
    # Once April's dates are older than a month, only the new half year.
    selected, _ = ignalina.select_files(files, date(2027, 6, 5))
    assert selected == [following, PACKAGING]
    # Late: the last half year keeps being read.
    selected, _ = ignalina.select_files([MIXED, PACKAGING], date(2027, 6, 5))
    assert selected == [MIXED, PACKAGING]


def test_of_two_files_for_one_period_the_one_linked_first_is_read():
    newer = schedule_file("household", MIXED.start, MIXED.end, "patikslintas.pdf")
    selected, warnings = ignalina.select_files([newer, MIXED, PACKAGING], TODAY)
    assert selected == [newer, PACKAGING]
    assert warnings == [
        f"{MIXED.file_name}: not read, patikslintas.pdf is linked first for 2026-11-01 - "
        "2027-04-30",
        "no food waste schedule on the pages",
    ]


def test_pages_without_mixed_waste_or_packaging_fail():
    with pytest.raises(ValidationError, match="no packaging schedule on the pages"):
        ignalina.select_files([MIXED, FOOD], TODAY)
    with pytest.raises(ValidationError, match="no mixed waste schedule on the pages"):
        ignalina.select_files([PACKAGING, FOOD], TODAY)


def test_links_of_other_schedules_are_reported():
    html = (
        '<a href="/a.pdf">Didelių gabaritų atliekų surinkimo 2027 m. grafikas</a>'
        '<a href="/b.pdf">Maisto atliekų surinkimo grafikas</a>'
        '<a href="/c.pdf">Dūkšto seniūnija (PDF)</a>'
        '<a href="/d.pdf">Komunalinių atliekų surinkimo iš sodų bendrijų 2027 m. grafikas</a>'
    )
    files, warnings = ignalina.find_files(html)
    assert files == []
    assert warnings == [
        "a.pdf ('Didelių gabaritų atliekų surinkimo 2027 m. grafikas'): a schedule of no kind "
        "we read",
        "b.pdf ('Maisto atliekų surinkimo grafikas'): no period in its link or name; not read",
    ]


# --- the tables ------------------------------------------------------------------

VILNIAUS = "Ignalinos m.: Vilniaus - Budrių - Ažušilės gatvių kvartalas"
GELEZINKELIO = "Ignalinos m.: Geležinkelio - Turistų - Smėlio gatvių kvartalas"


def test_mixed_waste_from_november_to_april():
    result = parsed(MIXED)
    assert len(result.areas) == 63 and result.warnings == []
    assert {a.name.split(":")[0] for a in result.areas} == {
        "Ignalinos m.",
        *(f"{e} sen." for e in ignalina.ELDERSHIPS),
    }
    town = by_name(result, VILNIAUS)
    assert town.district == "Ignalinos r." and town.provider == "ignalina"
    # November and December of 2026, January to April of 2027: every other Tuesday.
    assert sorted(town.dates) == [
        date(2026, 11, 3),
        date(2026, 11, 17),
        date(2026, 12, 1),
        date(2026, 12, 22),
        date(2027, 1, 5),
        date(2027, 1, 19),
        date(2027, 2, 2),
        date(2027, 2, 16),
        date(2027, 3, 2),
        date(2027, 3, 23),
        date(2027, 4, 6),
        date(2027, 4, 20),
    ]
    assert town.weekday == "Antradienis"
    # "8,22": January's days without a space.
    assert {date(2027, 1, 8), date(2027, 1, 22)} <= by_name(result, GELEZINKELIO).dates
    # Places and days in rows of their own to the table finder.
    zuikiske = by_name(result, "Ignalinos sen.: Zuikiškė, Panižiškė")
    assert (min(zuikiske.dates), max(zuikiske.dates), len(zuikiske.dates)) == (
        date(2026, 11, 2),
        date(2027, 4, 19),
        13,
    )
    # The section of Naujojo Daugėliškio sen. ("N. DAUGĖLIŠKIO SENIŪNIJA") goes on over a page.
    assert by_name(result, "Naujojo Daugėliškio sen.: Medinos").dates >= {date(2026, 11, 18)}
    # A comma without a space.
    assert by_name(result, "Ceikinių sen.: Ceikiniai, Čižiškiai, Velykamiškis")


def test_packaging_and_glass_of_2026():
    result = parsed(PACKAGING)
    kinds = Counter(a.kind for a in result.areas)
    assert kinds == {"packaging": 61, "glass": 61} and result.warnings == []
    # The town's quarters as the mixed waste file names them ("Ignalinos miestas – Vilniaus -
    # ..."): the same rows for the places.
    town = by_name(result, VILNIAUS, "packaging")
    assert (min(town.dates), max(town.dates), len(town.dates)) == (
        date(2026, 1, 27),
        date(2026, 12, 29),
        12,
    )
    assert town.weekday == "Antradienis"
    assert by_name(result, VILNIAUS, "glass").dates == {date(2026, 4, 29), date(2026, 9, 30)}
    # Months without a pickup: February, April and November.
    vaisniunai = by_name(result, "Ignalinos sen.: Vaišniūnai, Trainiškis, Jonalaukis", "packaging")
    assert sorted({d.month for d in vaisniunai.dates}) == [1, 3, 5, 6, 7, 8, 9, 10, 12]
    # The summer houses, May to October.
    aza = by_name(result, "Ignalinos sen.: Azos k. (sezonas)", "packaging")
    assert (min(aza.dates), max(aza.dates)) == (date(2026, 5, 11), date(2026, 10, 12))
    # Its label in a row of its own: "Kazitiškis, ..." | "" then "" | "POP/PLAST/M" | days.
    kazitiskis = next(
        a for a in result.areas if a.kind == "glass" and a.name.startswith("Kazitiškio sen.: Kaz")
    )
    assert kazitiskis.dates == {date(2026, 6, 17), date(2026, 10, 15)}


def test_food_waste_from_november_to_april():
    result = parsed(FOOD)
    assert [a.name for a in result.areas] == [
        VILNIAUS,
        GELEZINKELIO,
        "Ignalinos sen.: Strigailiškis",
        "Ignalinos sen.: Girminiai",
        "Ignalinos sen.: Bėčiūnai",
        "Dūkšto sen.: Dūkštas, Ažukarklinė",
        "Vidiškių sen.: Vidiškės, Bališkiai",
    ]
    assert sorted(by_name(result, VILNIAUS, "food").dates) == [
        date(2026, 11, 11),
        date(2026, 12, 16),
        date(2027, 1, 13),
        date(2027, 2, 10),
        date(2027, 3, 17),
        date(2027, 4, 14),
    ]


def test_a_link_for_other_months_fails():
    other = schedule_file("household", date(2027, 5, 1), date(2027, 10, 31), MIXED.file_name)
    with pytest.raises(
        ValueError, match=r"months \[11, 12, 1, 2, 3, 4\], the link says 2027-05-01"
    ):
        ignalina.parse_file(other, content(MIXED))


def test_a_title_of_another_period_fails():
    other = schedule_file("household", date(2027, 11, 1), date(2028, 4, 30), MIXED.file_name)
    with pytest.raises(ValueError, match="isn't of the mixed waste of 2027-11-01 - 2028-04-30"):
        ignalina.parse_file(other, content(MIXED))


def test_dates_of_another_year_fail(monkeypatch):
    # Read a year late, the days fall on other weekdays.
    other = schedule_file("household", date(2027, 11, 1), date(2028, 4, 30), MIXED.file_name)
    monkeypatch.setattr(ignalina, "period", lambda text: (other.start, other.end))
    with pytest.raises(ValueError, match="aren't on one working day"):
        ignalina.parse_file(other, content(MIXED))


def test_the_packaging_file_linked_as_mixed_waste_fails():
    other = schedule_file("household", date(2026, 1, 1), date(2026, 12, 31), PACKAGING.file_name)
    with pytest.raises(ValueError, match="above the first section"):
        ignalina.parse_file(other, content(PACKAGING))


def test_too_few_rows_fail(monkeypatch):
    monkeypatch.setitem(ignalina.MIN_ROWS, "food", 8)
    with pytest.raises(ValueError, match=r"only 7 rows \(expected 8\)"):
        parsed(FOOD)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: ignalina._dates("3, 17a", 2026, 11, "here"), "unrecognised days '3, 17a'"),
        (lambda: ignalina._dates("31", 2026, 11, "here"), "month 11 of 2026 has no day 31"),
        (lambda: ignalina._dates("29", 2027, 2, "here"), "month 2 of 2027 has no day 29"),
        (lambda: ignalina._section("UTENOS SENIŪNIJA", "here"), "a section of no eldership"),
        (lambda: ignalina._section("DŪKŠTO MIESTAS", "here"), "a section of no eldership"),
        (
            lambda: ignalina._months(["Lapkritis", "Gruodis", "Pastaba"], "household", "here"),
            "for the months",
        ),
    ],
)
def test_cells_we_don_t_know_fail(call, message):
    with pytest.raises(ValueError, match=message):
        call()


def test_the_sections():
    assert ignalina._section("IGNALINOS MIESTAS", "here") == "Ignalinos m."
    assert ignalina._section("N. DAUGĖLIŠKIO SENIŪNIJA", "here") == "Naujojo Daugėliškio sen."
    assert ignalina._section("NAUJOJO DAUGĖLIŠKIO SENIŪNIJA", "here") == "Naujojo Daugėliškio sen."
    assert ignalina._section("Dūkšto seniūnija", "here") == "Dūkšto sen."


class _Page:
    """A page whose text outside its tables is `text`."""

    page_number = 3

    def __init__(self, text):
        self.text = text

    def outside_bbox(self, bbox):
        return self

    def extract_text(self):
        return self.text


def test_notes_next_to_the_tables():
    usual = (
        "TVIRTINU\nVadovė\nRasa Šatienė\n"
        "Klientai konsultuojami tel.: +370 665 94 192; +370 386 52 107\n"
        "Konteineriai turi būti išstatyti prie važiuojamosios kelio dalies iki 7 val. ryto.\n"
        "*Grafikas gali būti koreguojamas dėl nenumatytų aplinkybių.\n"
    )
    assert ignalina._notes(_Page(usual), [], "file.pdf") == []
    changed = usual + "Gruodžio 24 d. atliekos bus surenkamos gruodžio 23 d.\n"
    assert ignalina._notes(_Page(changed), [], "file.pdf") == [
        "file.pdf page 3: 'Gruodžio 24 d. atliekos bus surenkamos gruodžio 23 d.' next to the table"
    ]


# --- the places ------------------------------------------------------------------


def test_counts(part):
    data, _ = part
    assert len(data["areas"]) == 192
    stats = data["matching"]
    for kind, expected in (
        ("household", [264, 1, 0, 434]),
        ("packaging", [307, 1, 3, 388]),
        ("glass", [307, 1, 3, 388]),
        ("food", [7, 1, 0, 691]),
    ):
        states = ("single", "byStreet", "ambiguous", "none")
        assert [stats.get(f"{kind}.{s}", 0) for s in states] == expected, kind
    assert len(data["locations"]) == 699


def test_settlements_without_mixed_waste(part):
    data, _ = part
    points, _ = snapshot.load_points(snapshot.IGNALINA_ADDRESSES_FILE)
    addresses = Counter(f"g{p.settlement}" for p in points)
    without = Counter(
        {
            (loc["name"], loc["district"]): addresses[loc["id"]]
            for loc in data["locations"]
            if "household" not in loc.get("schedule", {})
        }
    )
    # Villages no mixed waste file names, most of them small or without addresses: 1,856 of
    # 10,669 addresses in November 2026. Some are in the packaging file's rows of summer houses
    # (Antalgė, Gervelės).
    assert len(without) == 434
    assert sum(without.values()) == 1_856
    assert without.most_common(3) == [
        (("Antalgė", "Rimšės"), 28),
        (("Gervelės", "Naujojo Daugėliškio"), 26),
        (("Kalviasalis", "Naujojo Daugėliškio"), 25),
    ]


def test_acceptance_examples(part):
    data, _ = part
    # Zuikiškė (Ignalinos sen.), "Zuikiškė, Panižiškė": every other Monday, 2 November 2026 ->
    # 19 April 2027 in the file.
    assert rows_of(data, "Zuikiškė", "household") == ["Ignalinos sen.: Zuikiškė, Panižiškė"]
    # Didžiasalis of Didžiasalio sen.: every other Thursday, 12 November 2026 -> 29 April 2027.
    name = rows_of(data, "Didžiasalis", "household", district="Didžiasalio")[0]
    didziasalis = by_name(parsed(MIXED), name)
    assert (min(didziasalis.dates), max(didziasalis.dates), len(didziasalis.dates)) == (
        date(2026, 11, 12),
        date(2027, 4, 29),
        13,
    )
    assert didziasalis.weekday == "Ketvirtadienis"


def test_the_town(part):
    data, _ = part
    for kind in ("household", "packaging", "glass", "food"):
        for street in ("Vilniaus g.", "Budrių g.", "Ažušilės g."):
            assert rows_of(data, "Ignalina", kind, street) == [VILNIAUS], (kind, street)
        for street in ("Geležinkelio g.", "Turistų g.", "Smėlio g."):
            assert rows_of(data, "Ignalina", kind, street) == [GELEZINKELIO], (kind, street)
    # The other 68 streets (Laisvės g., Ąžuolo g., the cul-de-sacs Budrių aklg. and Vilniaus
    # aklg., ...): the files say nothing of them, so the app offers both quarters.
    town = place(data, "Ignalina")
    named = town["schedule"]["household"]["streets"]
    unnamed = [label for key, label in town["streets"] if key not in named]
    assert len(named) == 6 and len(unnamed) == 68
    assert {"Laisvės g.", "Ąžuolo g.", "Budrių aklg.", "Vilniaus aklg."} <= set(unnamed)
    assert "none" not in town["schedule"]["household"]
    # Dūkštas, a town too, in one row.
    assert rows_of(data, "Dūkštas", "household") == ["Dūkšto sen.: Dūkštas, Ažukarklinė"]
    assert rows_of(data, "Dūkštas", "food") == ["Dūkšto sen.: Dūkštas, Ažukarklinė"]


def test_numbered_villages(part):
    data, _ = part
    # "Bajorai (I)" has a row of its own; "Bajorai" in another row are Bajorai II and III.
    assert rows_of(data, "Bajorai I", "household") == ["Kazitiškio sen.: Bajorai (I)"]
    for name in ("Bajorai II", "Bajorai III"):
        assert rows_of(data, name, "household") == [
            "Kazitiškio sen.: Gedžiūnai, Bajorai, Asiūklė, Apkartai, Antakmenė"
        ]
    # "Girutiškė (II)" and "Girutiškė"; "Krikonys (I)" and "Krikonys".
    assert rows_of(data, "Girutiškė I", "household") == [
        "Dūkšto sen.: Moliakalnis, Gerkonys, Girutiškė"
    ]
    assert rows_of(data, "Girutiškė II", "household")[0].startswith("Dūkšto sen.: Tumelina, ")
    assert rows_of(data, "Krikonys I", "household")[0].startswith("Mielagėnų sen.: Bernotai, ")
    assert rows_of(data, "Krikonys II", "household")[0].startswith("Mielagėnų sen.: Gilūtos, ")
    # "Seniškis I (sezonas)" of packaging: "Seniškis" of the other row is Seniškis II. Mixed
    # waste names only "Seniškis": both.
    assert rows_of(data, "Seniškis I", "packaging")[0].endswith("Markiniškė (sezonas)")
    assert rows_of(data, "Seniškis II", "packaging")[0].startswith(
        "Naujojo Daugėliškio sen.: Kūtiškės, "
    )
    assert rows_of(data, "Seniškis I", "household") == rows_of(data, "Seniškis II", "household")
    # "Kandrotiškė (I)": not Kandrotiškė II, which no file names.
    assert "Ceikinių sen.: Rubelninkai, Kandrotiškė (I), Dimbeliai" in rows_of(
        data, "Kandrotiškė I", "household"
    )
    assert "schedule" not in place(data, "Kandrotiškė II")


def test_villages_of_one_name(part):
    data, _ = part
    for district, start in (
        ("Ignalinos", "Ignalinos sen.: Meironys, "),
        ("Didžiasalio", "Didžiasalio sen.: Didžiasalis, "),
        ("Dūkšto", "Dūkšto sen.: Tumelina, "),
    ):
        assert rows_of(data, "Didžiasalis", "household", district=district)[0].startswith(start)
    # "Medinos" in the section of Naujojo Daugėliškio sen.: its farmstead, not the village of
    # Linkmenų sen.
    assert rows_of(data, "Medinos", "household", district="Naujojo Daugėliškio") == [
        "Naujojo Daugėliškio sen.: Medinos"
    ]
    assert "schedule" not in place(data, "Medinos", "Linkmenų")


def test_names_written_otherwise(part):
    data, _ = part
    for name, district, kind, start in (
        ("Senasis Daugėliškis", None, "household", "Naujojo Daugėliškio sen.: Senas Daugėliškis"),
        ("Naujasis Daugėliškis", None, "household", "Naujojo Daugėliškio sen.: Kūtiškės, Naujas"),
        ("Kūtiškė", None, "household", "Naujojo Daugėliškio sen.: Kūtiškės, "),
        ("Kovališkės", None, "household", "Rimšės sen.: Gaidė, "),  # "Kavoliškės"
        ("Juodagalviai", None, "household", "Mielagėnų sen.: Gilūtos, "),  # "Juodgalviai"
        ("Dysna", None, "packaging", "Didžiasalio sen.: Didžiasalis, "),  # "Dysnai"
        ("Naujieji Bajorai", None, "household", "Linkmenų sen.: Šakarva, Bajorai, "),
        ("Senieji Bajorai", None, "household", "Linkmenų sen.: Šakarva, Bajorai, "),
        ("Aza", None, "packaging", "Ignalinos sen.: Azos k. (sezonas)"),
        ("Palaukiškė II", None, "packaging", "Ignalinos sen.: Palaukiškės II k., "),
        ("Beržininkai II", "Rimšės", "household", "Rimšės sen.: Gaidė, "),
    ):
        assert rows_of(data, name, kind, district=district)[0].startswith(start), name


def test_the_app_asks(part):
    data, _ = part
    # Two packaging rows name Antagavė ("Antagavė (prie Gavaičio ež.)" and "Antagavė"),
    # Poviliškė and Trapikiškė (the year round and the summer houses): the app asks.
    assert rows_of(data, "Antagavė", "packaging") == [
        "Ignalinos sen.: Antagavė (prie Gavaičio ež.), Strigailiškis, Gaveikėnai, Palūšė",
        "Ignalinos sen.: Gaureliai, Meškėnai, Naujasalis, Ramutiškė, Sabališkė, Zablatiškė, "
        "Savuliai, Nastazavas, Leileikos, Rimašiai, Burkolai, Narsutiškė, Zuikos, Garbūnai, "
        "Rukšiškė, Dindos, Petriškė, Antagavė",
    ]
    assert rows_of(data, "Poviliškė", "glass") == [
        "Ignalinos sen.: Bendoriškė, Pakryžė, Poviliškė (sezonas)",
        "Ignalinos sen.: Zuikiškė, Poviliškė, Kūjiškė, Mažulonys, Vėlionys",
    ]
    assert len(rows_of(data, "Trapikiškė", "packaging")) == 2


def test_warnings(part):
    _, warnings = part
    assert sorted(warnings) == sorted(
        [
            "not a settlement or a street: household: Dūkšto sen.: Dūkšteliai",
            "not a settlement or a street: packaging: Dūkšto sen.: Dūkšteliai",
            "not a settlement or a street: glass: Dūkšto sen.: Dūkšteliai",
            "not a settlement or a street: household: Rimšės sen.: Verginiai",
        ]
    )


# --- the periods -----------------------------------------------------------------


def moved(result, weeks):
    """The rows of a file, `weeks` later (on the same weekdays): another period's file."""
    return ParseResult(
        [
            Area(
                a.kind,
                a.name,
                a.district,
                provider=a.provider,
                dates={d + timedelta(weeks=weeks) for d in a.dates},
            )
            for a in result.areas
        ]
    )


FOLLOWING = schedule_file("household", date(2027, 5, 1), date(2027, 10, 31))


def test_the_next_half_year_continues_the_rows_of_the_same_places():
    # 27 April 2027: May-October is linked next to November-April.
    current, following = parsed(MIXED), moved(parsed(MIXED), 26)
    renamed = next(a for a in following.areas if a.name == VILNIAUS)
    renamed.name = f"{VILNIAUS}, Smilgų g."
    warnings = ignalina.combine(
        [(MIXED, current), (FOLLOWING, following)], REGISTRY, date(2027, 4, 27)
    )
    # Every row but one names the same places: it gets May's dates.
    assert following.areas == []
    assert sum(max(a.dates) > date(2027, 5, 1) for a in current.areas) == 62
    assert max(by_name(current, VILNIAUS).dates) == date(2027, 4, 20)
    assert warnings == [
        f"Ignalinos r. household: the 2027-05-01 place {renamed.name[:60]!r} doesn't match one "
        "2026-11-01 place; its dates are left out until 2027-05-01",
        f"Ignalinos r. household: the 2026-11-01 place {VILNIAUS!r} has no dates for 2027-05-01",
    ]
    # In May the new half year takes over.
    current, following = parsed(MIXED), moved(parsed(MIXED), 26)
    files = [(MIXED, current), (FOLLOWING, following)]
    assert ignalina.combine(files, REGISTRY, date(2027, 5, 3)) == []
    assert [len(r.areas) for _, r in files] == [0, 63]


def test_next_year_s_packaging_continues_this_year_s():
    next_year = schedule_file("packaging", date(2027, 1, 1), date(2027, 12, 31))
    current, following = parsed(PACKAGING), moved(parsed(PACKAGING), 52)
    files = [(PACKAGING, current), (next_year, following)]
    assert ignalina.combine(files, REGISTRY, date(2026, 12, 20)) == []
    assert following.areas == []
    assert max(by_name(current, VILNIAUS, "packaging").dates) == date(2027, 12, 28)


def test_a_half_year_that_ends_without_the_next():
    files = [(f, content(f)) for f in (MIXED, PACKAGING)]
    data, warnings = build_dataset(files, REGISTRY, date(2027, 5, 20), 31, ignalina.SOURCE)
    assert warnings[:2] == [
        "the mixed waste schedule ended on 2027-04-30; no newer one is read",
        "the packaging schedule ended on 2026-12-31; no newer one is read",
    ]
    # The rows keep their last dates, a month on.
    area = place(data, "Zuikiškė")["schedule"]["household"]["area"]
    assert row(data, area)["dates"] == ["2027-04-19"]


def test_the_next_half_year_in_place_of_the_last():
    # Linked in place of the last before it starts: the last one's April dates are lost.
    warnings = ignalina.combine(
        [(FOLLOWING, moved(parsed(MIXED), 26))], REGISTRY, date(2027, 4, 27)
    )
    assert warnings == ["no mixed waste schedule for today; the next starts on 2027-05-01"]


def test_overlapping_files_fail():
    whole_year = schedule_file("household", date(2027, 1, 1), date(2027, 12, 31))
    with pytest.raises(ValueError, match="overlap"):
        ignalina.combine(
            [(MIXED, parsed(MIXED)), (whole_year, moved(parsed(MIXED), 26))], REGISTRY, TODAY
        )


# --- the published folder --------------------------------------------------------


def test_published_folder_and_its_metrics(part, tmp_path):
    data, warnings = part
    built = [(ignalina.PROVIDER, {**data, "warnings": len(warnings)})]
    dataset = merge_parts(built, ignalina.PAGE_URL)
    assert [p["id"] for p in dataset["providers"]] == ["ignalina"]
    assert all(a["provider"] == "ignalina" for a in dataset["areas"])
    folder = tmp_path / "ignalinos-r"
    folder.mkdir()
    (folder / "schedule.json").write_text(json.dumps(dataset), encoding="utf-8")
    (folder / "addresses.json").write_text("{}", encoding="utf-8")
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="ignalina"} 320' in text
    assert 'siuksliaveze_data_areas{source="ignalina",kind="food"} 7' in text
    assert 'siuksliaveze_data_warnings{source="ignalina"} 4' in text
    # regions.json lists the folder, so installed apps download it.
    assert regions.collect(tmp_path)["regions"] == [
        {
            "path": "ignalinos-r/",
            "kind": "settlements",
            "files": ["schedule.json", "addresses.json"],
            "providers": ["ignalina"],
        }
    ]


def serve(url, timeout=0):
    """The pages and their files, from the fixtures."""
    if url in PAGES:
        return fixture(f"ignalina/{PAGES[url]}")
    by_url = {f.url: COPIES[f.file_name] for f in (MIXED, PACKAGING, FOOD)}
    if url in by_url:
        return fixture(f"ignalina/{by_url[url]}")
    raise OSError(f"HTTP Error 404: {url}")


def refused(*args, **kwargs):
    raise OSError("HTTP Error 403: Forbidden")


def test_main_writes_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(ignalina.http, "get", serve)
    monkeypatch.setattr(ignalina.raseiniai.address_register, "fetch", refused)
    monkeypatch.setattr(ignalina.raseiniai.address_points, "fetch", refused)
    assert ignalina.main(["--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["ignalina"]
    assert {f["name"] for f in data["files"]} == set(COPIES)
    addresses = json.loads((tmp_path / "addresses.json").read_text(encoding="utf-8"))
    assert len(addresses["points"]) > ignalina.MUNICIPALITY.min_address_points


def test_a_page_without_the_files_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(ignalina.http, "get", lambda url, timeout=0: b"<html></html>")
    monkeypatch.setattr(build, "live_or_snapshot", lambda name, live, snap: (snap()[0], None))
    assert ignalina.main(["--out", str(tmp_path)]) == 1
    assert not (tmp_path / "schedule.json").exists()

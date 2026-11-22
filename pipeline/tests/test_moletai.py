"""Molėtų r.: the page of UAB „Molėtų švara“, its twelve PDFs (one per eldership and the town's),
the main settlements' and the villages' rows, the town's streets, the notice next to Alantos
sen.'s file, and yesterday's rows for a file that can't be read."""

import json
from datetime import date
from urllib.parse import unquote

import pytest
from test_parsers import FIXTURES, fixture

from schedule_pipeline import aratc, build, moletai, regions, status
from schedule_pipeline.build import build_dataset, merge_parts
from schedule_pipeline.registry import Registry

TODAY = date(2026, 11, 21)
UPLOADS = "https://www.moletusvara.lt/uploads/Grafikai/"
# The files the page links, by their names, and their copies in fixtures/moletai.
COPIES = {
    "2026_ALANTOS_SEN_grafikas.pdf": "alantos.pdf",
    "2026_BALNINKU_SEN_grafikas.pdf": "balninku.pdf",
    "2026_CIULENU_SEN_grafikas.pdf": "ciulenu.pdf",
    "2026_DUBINGIU_SEN_grafikas.pdf": "dubingiu.pdf",
    "2026_GIEDRAICIU_SEN_grafikas.pdf": "giedraiciu.pdf",
    "2026_INTURKES_SEN_grafikas.pdf": "inturkes.pdf",
    "2026_JONISKIO_SEN_grafikas.pdf": "joniskio.pdf",
    "2026_LUOKESOS_SEN_ir_dalies_GIEDRAICIU_SEN_grafikas.pdf": "luokesos.pdf",
    "2026_MINDUNU_SEN_grafikas.pdf": "mindunu.pdf",
    "2026_MOLETU_MIESTAS_(1).pdf": "moletu-m.pdf",
    "2026_SUGINCIU_SEN_grafikas.pdf": "suginciu.pdf",
    "2026_VIDENISKIU_SEN_grafikas.pdf": "videniskiu.pdf",
}
REGISTRY = "moletai/registry-moletu-r-2026-11-21.json"
NOTICE = (
    "ATKREIPIAME DĖMESĮ, KAD PAANKSTINAMAS KIEKVIENO MĖNESIO PIRMAS ATLIEKŲ RINKIMAS "
    "(perkeliamas iš ketvirtadienio į antradienį)"
)


def serve(url, timeout=0):
    """The saved page and files, as moletai.http.get."""
    if url == moletai.PAGE_URL:
        return fixture("moletai/page.html")
    return fixture(f"moletai/{COPIES[unquote(url.rsplit('/', 1)[-1])]}")


def parsed(copy, group, year=2026, notices=()):
    file = moletai.ScheduleFile(
        "household", f"{UPLOADS}{copy}", copy, group=group, year=year, notices=notices
    )
    return moletai.parse_file(file, fixture(f"moletai/{copy}"))


@pytest.fixture(scope="module")
def built():
    """The part as the daily job builds it from the page, with every date of the year kept."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(moletai.http, "get", serve)
        files, warnings = moletai.download(TODAY, 366)
        registry = aratc.town_elderships(Registry.load(FIXTURES / REGISTRY))
        data, more = build_dataset(files, registry, TODAY, 366, moletai.source())
    return files, data, warnings + more


def place(data, name, kind=None, district=None):
    return next(
        loc
        for loc in data["locations"]
        if loc["name"] == name
        and kind in (None, loc["type"])
        and district in (None, loc["district"])
    )


def rows(data, name, waste="household", kind=None, district=None):
    """The names of a place's rows of a kind."""
    schedule = place(data, name, kind, district)["schedule"][waste]
    ids = [schedule["area"]] if "area" in schedule else schedule["candidates"]
    by_id = {a["id"]: a for a in data["areas"]}
    return [by_id[i] for i in ids]


# --- the page ----------------------------------------------------------------


def test_finds_a_file_per_eldership_and_the_towns_by_their_links():
    files, warnings = moletai.find_files(fixture("moletai/page.html").decode("utf-8"))
    assert sorted(f.file_name for f in files) == sorted(COPIES)
    assert {f.group for f in files} == moletai.ELDERSHIPS | {moletai.TOWN}
    assert {(f.kind, f.year) for f in files} == {("household", 2026)}
    # Relative to the page's <base>, not to the page.
    assert all(f.url.startswith(UPLOADS) for f in files)
    # The notice next to Alantos sen.'s link, and none next to the others.
    assert {f.group: f.notices for f in files if f.notices} == {"Alantos": (NOTICE,)}
    assert warnings == []


def test_next_years_file_of_an_eldership_is_read_next_to_this_years():
    def file(group, year):
        return moletai.ScheduleFile(
            "household", f"{UPLOADS}{group}{year}.pdf", "x", group=group, year=year
        )

    groups = moletai.ELDERSHIPS | {moletai.TOWN}
    files = [file(g, 2026) for g in groups] + [file("Alantos", 2027), file("Mindūnų", 2025)]
    chosen, warnings = moletai.select_files(files, TODAY)
    assert sorted(f.year for f in chosen if f.group == "Alantos") == [2026, 2027]
    assert len(chosen) == 13 and warnings == []
    with pytest.raises(build.ValidationError, match="Videniškių"):
        moletai.select_files([f for f in files if f.group != "Videniškių"], TODAY)


def test_links_of_other_years_elderships_or_texts():
    def page(heading, href, text):
        return (
            f'<base href="https://www.moletusvara.lt/" /><div><a class="accord-toggler" href="#">'
            f'{heading}</a><div class="accord"><div><p><a href="{href}">{text}</a></p></div></div>'
            "</div>"
        )

    link = "2026 m. Molėtų r. Alantos sen. komunalinių atliekų surinkimo grafikas"
    with pytest.raises(ValueError, match="a file of 2027, its link says 2026"):
        moletai.find_files(page("ALANTOS SENIŪNIJA", "uploads/2027_ALANTOS.pdf", link))
    with pytest.raises(ValueError, match="the file of Alantos under 'BALNINKŲ SENIŪNIJA'"):
        moletai.find_files(page("BALNINKŲ SENIŪNIJA", "uploads/a.pdf", link))
    # A PDF of another text is reported; one of the shared containers isn't.
    files, warnings = moletai.find_files(page("ALANTOS SENIŪNIJA", "uploads/a.pdf", "Pakeitimai"))
    assert files == [] and warnings == ["a.pdf: not read, a link of no eldership: 'Pakeitimai'"]
    shared = page("Kolektyvinio naudojimo ir juridinių asmenų konteineriai", "u/b.pdf", "2026 m.")
    assert moletai.find_files(shared) == ([], [])


# --- the tables ------------------------------------------------------------------


def test_the_main_settlements_villages_packaging_and_glass():
    result = parsed("alantos.pdf", "Alantos", notices=(NOTICE,))
    areas = {a.name: a for a in result.areas}
    main = areas["Alantos sen.: Pagrindinės gyvenvietės: Alanta"]
    villages = next(a for a in result.areas if a.kind == "household" and a is not main)
    assert villages.name.startswith("Alantos sen.: Alanta ir seniūnijos kaimai: Adomiškėlis,")
    assert villages.name.endswith("Šunakojai, Žygeliškis ir kiti...")
    # "13 | 10 | 10 | 14 / 24 | ... | 8": twice a month from April to September.
    assert sorted(main.dates)[:5] == [
        date(2026, 1, 13),
        date(2026, 2, 10),
        date(2026, 3, 10),
        date(2026, 4, 14),
        date(2026, 4, 24),
    ]
    assert len(main.dates) == 18 and len(villages.dates) == 12 and villages.dates < main.dates
    assert villages.weekday == "Antradienis" and main.weekday is None
    kinds = sorted(a.kind for a in result.areas)
    assert kinds == ["glass", "household", "household", "packaging"]
    glass = next(a for a in result.areas if a.kind == "glass")
    # "23 | - | - | 24 | - | - | 24 | - | - | 23 | - | -": four times a year.
    assert sorted(glass.dates) == [
        date(2026, 1, 23),
        date(2026, 4, 24),
        date(2026, 7, 24),
        date(2026, 10, 23),
    ]
    # The businesses' extra pickups aren't read, the notice agrees with the file.
    assert not any("Užsakomieji" in a.name for a in result.areas)
    assert result.warnings == []
    assert {a.district for a in result.areas} == {"Molėtų r."}


def test_the_towns_streets_and_green_waste():
    areas = parsed("moletu-m.pdf", moletai.TOWN).areas
    assert (
        sorted(a.kind for a in areas)
        == ["glass"] * 3 + ["green"] + ["household"] * 3 + ["packaging"] * 3
    )
    green = next(a for a in areas if a.kind == "green")
    assert green.name == "Molėtų miestas" and len(green.dates) == 17
    first = next(a for a in areas if a.kind == "household")
    assert first.name.startswith("Molėtų m.: Alberto Jauniškio g., Aušros g.,")
    assert first.name.endswith("Vilniaus g. (iki 79 nr.), Žalioji g.")


def test_the_file_of_an_eldership_and_part_of_another():
    areas = parsed("luokesos.pdf", "Luokesos").areas
    assert {a.name.split(":")[0] for a in areas} == {"Luokesos sen. ir dalies Giedraičių sen."}


def test_a_notice_the_file_disagrees_with_fails_another_is_reported():
    later = NOTICE.replace("į antradienį", "į trečiadienį")
    with pytest.raises(ValueError, match="first pickup of each month to Trečiadienis"):
        parsed("alantos.pdf", "Alantos", notices=(later,))
    result = parsed("balninku.pdf", "Balninkų", notices=("Grafikas atnaujintas",))
    assert result.warnings == [
        "balninku.pdf: a notice next to it on the page: 'Grafikas atnaujintas'"
    ]


def test_a_title_of_another_eldership_or_year_fails():
    with pytest.raises(ValueError, match="the title says Alantos 2026, the link Balninkų 2026"):
        parsed("alantos.pdf", "Balninkų")
    with pytest.raises(ValueError, match="the link Alantos 2027"):
        parsed("alantos.pdf", "Alantos", year=2027)


def test_villages_whose_first_settlements_arent_main_ones_fail():
    def row(label, days):
        return moletai._Row(label, "household", {date(2026, 1, d) for d in days})

    main = row("Pagrindinės gyvenvietės: Alanta", [13, 27])
    moletai._check_villages([main, row("Alanta ir seniūnijos kaimai: A ir kiti...", [13])], "x")
    with pytest.raises(ValueError, match="aren't all main settlements"):
        moletai._check_villages([main, row("Kazlai ir seniūnijos kaimai: A ir kiti", [13])], "x")
    with pytest.raises(ValueError, match="the main settlements haven't"):
        moletai._check_villages([main, row("Alanta ir seniūnijos kaimai: A ir kiti", [14])], "x")


# --- the places ----------------------------------------------------------------


def test_counts(built):
    _, data, warnings = built
    stats = data["matching"]
    assert stats["locations"] == 891
    # Every settlement has mixed waste; the villages of Giedraičių sen. that neither its file nor
    # Luokesos sen.'s names have both, and the town is split by street.
    assert (stats["household.single"], stats["household.ambiguous"]) == (793, 97)
    assert (stats["household.byStreet"], stats.get("household.none", 0)) == (1, 0)
    assert (stats["packaging.single"], stats["glass.single"]) == (793, 793)
    assert (stats["green.single"], stats["green.none"]) == (1, 890)
    kinds = {}
    for area in data["areas"]:
        kinds[area["kind"]] = kinds.get(area["kind"], 0) + 1
    assert kinds == {"household": 25, "packaging": 14, "glass": 14, "green": 1}
    # Antapusnė in Dubingių sen.'s file: the register has one in Giedraičių sen. and one in
    # Luokesos sen.
    assert warnings == [
        f"not a settlement or a street: {kind}: Dubingių sen.: Antapusnė"
        for kind in ("household", "packaging", "glass")
    ]


def test_a_village_and_a_main_settlement(built):
    _, data, _ = built
    # Adomiškėlis, Alantos sen.: the villages' row.
    (row,) = rows(data, "Adomiškėlis")
    assert row["name"].startswith("Alantos sen.: Alanta ir seniūnijos kaimai:")
    assert (len(row["dates"]), row["dates"][0], row["dates"][-1]) == (
        12,
        "2026-01-13",
        "2026-12-08",
    )
    # Alanta, named first in the villages' row too, has only the main settlements' row.
    (row,) = rows(data, "Alanta", kind="mstl.")
    assert row["name"] == "Alantos sen.: Pagrindinės gyvenvietės: Alanta"
    assert (len(row["dates"]), row["dates"][0], row["dates"][-1]) == (
        18,
        "2026-01-13",
        "2026-12-08",
    )
    # Its packaging is the villages' row's.
    (row,) = rows(data, "Alanta", "packaging", kind="mstl.")
    assert row["name"].startswith("Alantos sen.: Alanta ir seniūnijos kaimai:")
    # A village no file names: "ir kiti...", its eldership's villages.
    (row,) = rows(data, "Adomiškis")
    assert row["name"].startswith("Alantos sen.: Alanta ir seniūnijos kaimai:")


def test_places_of_other_elderships_and_the_part_of_giedraiciai(built):
    _, data, _ = built
    # Cezariškiai, a main settlement of Mindūnų sen.'s file, is of Čiulėnų sen. in the register.
    (row,) = rows(data, "Cezariškiai")
    assert place(data, "Cezariškiai")["district"] == "Čiulėnų"
    assert row["name"] == "Mindūnų sen.: Pagrindinės gyvenvietės: Mindūnai, Cezariškiai, Juodiškės"
    # Žalvariai (Giedraičių sen.) is a main settlement of Luokesos sen.'s file; "Jaurai" in its
    # list is Jaurai of Giedraičių sen., not of Alantos sen.
    (row,) = rows(data, "Žalvariai")
    assert row["name"].startswith("Luokesos sen. ir dalies Giedraičių sen.: Pagrindinės")
    (row,) = rows(data, "Jaurai", district="Giedraičių")
    assert row["name"].startswith("Luokesos sen. ir dalies Giedraičių sen.: Luokesa")
    (row,) = rows(data, "Jaurai", district="Alantos")
    assert row["name"].startswith("Alantos sen.:")
    # A village of Giedraičių sen. neither file names: either.
    found = rows(data, "Laumėnai")
    assert sorted(r["name"].split(":")[0] for r in found) == [
        "Giedraičių sen.",
        "Luokesos sen. ir dalies Giedraičių sen.",
    ]


def test_the_town_and_its_villages(built):
    _, data, _ = built
    town = place(data, "Molėtai", "m.")
    assert town["district"] == "Molėtų miesto"
    streets = {label: key for key, label in town["streets"]}
    by_street = town["schedule"]["household"]["streets"]
    by_id = {a["id"]: a for a in data["areas"]}

    def routes(street):
        """The first street of each of the routes of a street."""
        return sorted(by_id[i]["name"].split(",")[0] for i in by_street[streets[street]])

    assert routes("Kalno g.") == ["Molėtų m.: Alberto Jauniškio g."]
    # "Vilniaus g. (iki 79 nr.)" and "(nuo 105 nr.)", no route for its houses between: the
    # town's routes to choose from, as for Raseinių Bažnyčios g.
    assert routes("Vilniaus g.") == [
        "Molėtų m.: Alberto Jauniškio g.",
        "Molėtų m.: Algirdo g.",
        "Molėtų m.: Aplinkkelio g.",
    ]
    # A street no route names is left to the app.
    assert streets["Liepų g."] not in by_street
    (green,) = rows(data, "Molėtai", "green", kind="m.")
    assert green["name"] == "Molėtų miestas"
    # "Ažubalių k." in the town's file: Ažubaliai of Luokesos sen., not of Alantos sen.
    (row,) = rows(data, "Ažubaliai", district="Luokesos")
    assert row["name"].startswith("Molėtų m.: Alberto Jauniškio g.")
    (row,) = rows(data, "Ažubaliai", district="Alantos")
    assert row["name"].startswith("Alantos sen.:")


# --- a file that can't be read, and the folder -----------------------------------


def test_a_file_that_cant_be_read_keeps_yesterdays_rows(built):
    files, data, _ = built
    published = merge_parts(
        [(moletai.PROVIDER, {**data, "warnings": 0, "generatedAt": "2026-11-20"})],
        moletai.PAGE_URL,
    )
    town = next(f for f, _ in files if f.group == moletai.TOWN)
    result = moletai.parse_or_keep(town, b"", lambda: published)
    assert (
        sorted(a.kind for a in result.areas)
        == ["glass"] * 3 + ["green"] + ["household"] * 3 + ["packaging"] * 3
    )
    assert "yesterday's 10 rows of Molėtų miesto sen. are kept" in result.warnings[0]
    luokesa = next(f for f, _ in files if f.group == "Luokesos")
    assert len(moletai.parse_or_keep(luokesa, b"", lambda: published).areas) == 4
    with pytest.raises(ValueError, match="not downloaded"):
        moletai.parse_or_keep(town, b"", None)


def test_the_folder(tmp_path, monkeypatch):
    def blocked(*args):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(moletai.http, "get", serve)
    monkeypatch.setattr(moletai.raseiniai.address_register, "fetch", blocked)
    monkeypatch.setattr(moletai.raseiniai.address_points, "fetch", blocked)
    out = tmp_path / "moletu-r"
    assert moletai.main(["--strict", "--out", str(out)]) == 0
    data = json.loads((out / "schedule.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["providers"]] == ["moletai"]
    assert place(data, "Molėtai", "m.")["district"] == "Molėtų miesto"
    assert regions.region(tmp_path, out) == {
        "path": "moletu-r/",
        "kind": "settlements",
        "files": ["schedule.json", "addresses.json"],
        "providers": ["moletai"],
    }
    assert status.main(["--site", str(tmp_path)]) == 0
    text = (tmp_path / "metrics.txt").read_text(encoding="utf-8")
    assert 'siuksliaveze_data_places{source="moletai"} 891' in text

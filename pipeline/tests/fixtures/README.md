# Test fixtures

Snapshots of the schedule page and files published by UAB "Nemenčinės komunalininkas" at
<https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/>, downloaded on
2026-10-11 (`household-2026-11-09.xlsx`: the November 2026 version, without the empty
"Gatvė" column). They are kept here only so the parsers can be tested against real input.

`nemezio-*` are the schedule page and the October-December 2026 files of UAB "Nemėžio
komunalininkas" at <https://www.nkom.lt/kita.html>, downloaded on 2026-11-17:
`nemezio-household-2026-q4.pdf` is "Grafikas mišrių 2026 (10-12).xlsx - 2026 (10-12).pdf",
`nemezio-packaging-2026-q4.pdf` is "Grafikas pakuočių 2026 (10-12).xlsx - 2026 (10-12).pdf"
(packaging and glass).

`tratc/` has the Mažeikiai page of UAB "Telšių regiono atliekų tvarkymo centras" at
<https://tratc.lt/atlieku-surinkimo-grafikai/atlieku-surinkimo-grafikai-mazeikiai/> and the
2026 and 2027 spreadsheets it links (mixed, food and green, packaging and glass), downloaded on
2026-11-17, with the Address Register extract for Mažeikių r. of the same day. `page-telsiai.html`,
`page-plunge.html` and `page-rietavas.html` are its pages of Telšių r., Plungės r. and Rietavo
sav. (the same address, ending `-telsiai/`, `-plunge/`, `-rietavas/`), downloaded on 2026-11-21
with the spreadsheets they link, bulky waste aside: Telšių r. 2026 (mixed waste, packaging and
glass in one file), Plungės r. 2026 and 2027 (mixed waste; packaging and glass, the 2026 one
named `Kopija-Plunge-2026-grafikas-003-3.xlsx`) and 2026 food and green waste, Rietavo sav. 2026
(mixed waste) and 2026 and 2027 (packaging and glass); and the Address Register extracts for
the three municipalities of that day.

`gargzdu/` has the page of VšĮ "Gargždų švara" (Klaipėdos r.) at
<https://www.gargzdusvara.eu/komunaliniu-atlieku-tvarkymo-grafikai/> and the 2026 spreadsheet it
links, downloaded on 2026-11-21, with the Address Register extract for Klaipėdos r. of the same
day. `2025 MKA+AZ (1).xlsx` is the 2025 spreadsheet, still on the site at the address the page
linked in 2025 (other column titles, spaces in the lists of days, a second sheet).

`taurage/` has the schedule page of UAB "Tauragės regiono atliekų tvarkymo centras" at
<https://www.uabtratc.lt/atlieku-surinkimo-grafikai/> and the two 2026 PDFs of Jurbarko r. it
links (mixed and green waste, packaging and glass), downloaded on 2026-11-21, with the Address
Register extract for Jurbarko r. of the same day. Also the 2026 PDFs of the other three
municipalities on that page, downloaded on 2026-11-21: Tauragės r. (the villages' mixed waste
`Taurages-rajonas_MKA_2026_suderintas-naujas-1.pdf`, the town's mixed waste and food waste
`Taurages-miestas_MKA_2026_suderintas.pdf` and `Taurages-miestas_ZA_2026_suderintas.pdf`,
packaging and glass of both `Taurages-miestas-ir-rajonas_pakuotes_2026_suderintas-03-10.pdf`),
Šilalės r. (mixed and green waste, packaging and glass) and Pagėgių sav. (every kind in one
file); and the Address Register extracts for the three of that day.

`sratc/` has the pages of Šiaulių r. and Akmenės r. of UAB "Šiaulių regiono atliekų tvarkymo
centras" (<https://www.sratc.lt/grafikai-siauliu-rajonas/>, `.../grafikai-akmenes-rajonas/`) and
the 2026 PDFs for private houses of its five municipalities, downloaded on 2026-11-21, renamed:
`siauliu-r-2026.pdf` is "2026 m- individualių valdų grafikas Šiaulių rajonas 260831.pdf",
`akmenes-r-2026.pdf` "2026 m- individualių valdų grafikas Akmenės r-.pdf", `joniskio-r-2026.pdf`
"2026 - individualios.pdf", `kelmes-r-2026.pdf` "2026 - individualūs.pdf" and
`pakruojo-r-2026.pdf` "2026 m grafikai/2026 m- pakruojo individualiu valdu grafikas.pdf". With
the Address Register extract for the five municipalities of the same day, in one file.
`radviliskio-rajonas.html` is its page of Radviliškio r. (`.../grafikai-radviliskio-rajonas/`),
downloaded on 2026-11-21 with the two files for private houses it links, renamed:
`radviliskio-r-mka-2026-q4.pdf` is "2026 m indiv- valdų MKA ir BSA surinkimas_sv.pdf" (mixed and
green waste, October-December 2026) and `radviliskio-r-pop-2026.pdf` "2026 m grafikai/2026 m
radviliskio indiv- valdu POP ir stiklo surinkimas.pdf" (packaging and glass, 2026); with the
Address Register extract for Radviliškio r. of the same day
(`registry-radviliskio-r-2026-11-21.json`).

`aratc/` has the schedule page of UAB "Alytaus regiono atliekų tvarkymo centras" at
<https://www.aratc.lt/atlieku-surinkimo-grafikai/> and the PDFs of individual houses it links,
downloaded on 2026-11-21, renamed (the page links them under `uploads/Grafikai/`):
`alytaus-r-mka.pdf` is "Alytaus r 2026-2027 MA MKA gyventojai.pdf", `alytaus-r-pa.pdf` "Alytaus
r 2026-2028 PA STKL individualūs.pdf", `prienu-r-mka.pdf` "Prienu r MA MKA 2026-2027
gyventojai.pdf", `prienu-r-pa.pdf` "Prienu r 2026 12-2028 03  PA STKL individualus.pdf",
`lazdiju-mka.pdf` "Lazdiju r 2026-2027 MKA individualūs.pdf", `lazdiju-ma.pdf` "Lazdiju r
2026-2027 MA individualus 2026-06-30.pdf", `lazdiju-pa.pdf` "Lazdiju r 2026 08 - 2027 02 PA STKL
individualus namai.pdf", `varenos-mka.pdf` "Varenos r 2026-2027 MKA individualūs.pdf",
`varenos-ma.pdf` "Varėnos rajono savivaldybės maisto atliekų konteinerių aptarnavimo grafikas
2026 - 2027 metams.pdf", `varenos-pa.pdf` "Varenos r 2026-2027 PA STKL individualūs.pdf",
`druskininku-mka.pdf` "Druskininku sav 2026 04-2027 - 02 MA MKA gyventojai individualus.pdf",
`druskininku-sodai.pdf` "SODŲ, VIENKIEMIŲ IR SUNKIAI PRIVAŽIUOJAMŲ INDIVIDUALIŲ VALDŲ MIŠRIŲ
KOMUNALINIŲ ATLIEKŲ SURINKIMO DRUSKININKŲ SAVIVALDYBĖS TERITORIJOJE GRAFIKAS 2026 - 2027 M.pdf",
`druskininku-pa.pdf` "Druskininku sav PA STKL 2026-2027 Individualus namai 2026.06.30.pdf",
`birstono-mka.pdf` "Birstono sav 2026-2027 MA MKA gyventojai.pdf" and `birstono-pa.pdf`
"Birstono sav 2026-2027 PA STKL gyventojai.pdf". With the Address Register extract for the six
municipalities of the same day.

`maatc/` has the schedule pages of the five municipalities of UAB "Marijampolės apskrities
atliekų tvarkymo centras" (<https://maatc.lt/atlieku-isvezimo-grafikai/marijampoles-sav/>,
`.../vilkaviskio-raj-sav/`, `.../kalvarijos-sav/`, `.../kazlu-rudos-sav/`, `.../sakiu-raj-sav/`,
renamed `page-<provider id>.html`) and the 2026 PDFs of individual houses they link (made by UAB
"Ecoservice" and UAB "Ekonovus"), downloaded on 2026-11-21 and renamed
`<provider id>-<kind>.pdf`: `marijampole-household.pdf` is "2026-m.-Marijampoles-sav.-
individualiu-valdu-misriu-komunaliniu-atlieku-pakuociu-ir-antriniu-zaliavu-konteineriu-
aptarnavimo-grafikas.pdf", `vilkaviskis-packaging.pdf` "2026-m.-Vilkaviskio-raj.-sav.-
individualiu-valdu-antriniu-zaliavu-ir-pakuociu-konteineriu-aptarnavimo-grafikas.pdf",
`sakiai-glass.pdf` "2026-m.-Sakiu-rajono-sav.-stiklo-pakuociu-atlieku-surinkimo-is-individualiu-
konteineriu-grafikas-.pdf", `kalvarija-food.pdf` "2026-m.-Kalvarijos-sav.-individualiu-maisto-
surinkimo-grafikas.pdf" and so on (`test_maatc.COPIES` lists all thirteen). With the Address
Register extracts of the five municipalities of the same day.

`ecoservice/` has the schedules of UAB "Ecoservice" for Šilutės r., Trakų r. and Šalčininkų r.,
downloaded on 2026-11-21 and renamed `<provider id>-<kind>.pdf`, with the pages that link them
(`page-<provider id>.html`): Šilutės r.'s waste management page
(<https://www.silute.lt/veiklos-sritys/aplinkosauga-ir-atlieku-tvarkymas/atlieku-tvarkymas/10160>)
and `silute-household.pdf`, "isvezimai_valdos_2026silute.pdf"; <https://ecoservice.lt/trakugrafikai/>
and `trakai-household.pdf`, "Traku-r.-atlieku-surinkimo-grafikas-2026.pdf";
<https://ecoservice.lt/salcininkugrafikai/>, `salcininkai-household.pdf`
"Individualiu-valdu-misriu-komunaliniu-atlieku-surinkimo-grafikas-Salcininku-r.-2026-m.pdf" and
`salcininkai-packaging.pdf` "Individualiu-valdu-antriniu-zaliavu-isvezimo-grafikas-Salcininku-r.-
2026-m.pdf" (`test_ecoservice.COPIES`). With the Address Register extracts of the three
municipalities of the same day.

`pratc/` has the schedule page of UAB "Panevėžio regiono atliekų tvarkymo centras" at
<https://www.pratc.lt/atlieku-isvezimas-atlieku-isvezimas/> and the 2026 spreadsheets of
individual houses it links, downloaded on 2026-11-21, renamed (the page links them under
`uploads/rinkliava/<municipality>/2026 grafikai/`, Biržų r.'s food waste file under `uploads/`):
`pasvalio-r-mka.xlsx` is "Bendro ir individualaus naudojimo mišrių kom- atliekų kont- aptarnavimo
grafikas.xlsx", `pasvalio-r-pakuotes.xlsx` "Individualaus naudojimo pakuočių konteinerių
aptarnavimo grafikas.xlsx", `pasvalio-r-maistas.xlsx` "Maisto atliekų konteinerių aptarnavimo
grafikas_Pasvalio r-.xlsx", `rokiskio-r-mka.xlsx` "Mišrių komunalinių atliekų surinkimo
grafikas.xlsx", `rokiskio-r-pakuotes.xlsx` "Pakuočių konteinerių (individualių valdų) aptarnavimo
grafikas.xlsx", `rokiskio-r-maistas.xlsx` "Maisto atliekų surinkimo grafikas_Rokiškio r-.xlsx",
`birzu-r-individualios.xlsx` "INDIVIDUALIŲ VALDŲ mišrių kom- ir pakuočių atliekų kont-
aptarnavimo grafikas.xlsx", `birzu-r-maistas.xlsx` "NAUJAS Maisto atliekų konteinerių
aptranavimo grafikas_Biržų r-.xlsx", `panevezio-r-pakuotes.xlsx` "Pakuočių konteinerių
(individualių valdų) aptarnavimo grafikas1.xlsx" and `panevezio-r-stiklas.xlsx` "Pakuočių stiklo
konteinerių (individualių valdų) aptarnavimo grafikas.xlsx". With the Address Register extracts
for Pasvalio r., Rokiškio r., Biržų r. and Panevėžio r. of the same day. `panevezio-r-mka.doc` is
Panevėžio r.'s 2026 mixed waste schedule, "Mišrių komunalinių grafikas1.doc" (a Word 97-2003
document, uploaded on 5 January 2026), downloaded on 2026-11-22; the transcription of its notes
in `pipeline/data/schedule-panevezio-r-mixed.json` is of this file.

`kedainiai/` has the page of waste schedules of Kėdainių rajono savivaldybė at
<https://www.kedainiai.lt/gyventojui/atlieku-tvarkymas/atlieku-isvezimo-grafikai/1538> (line
endings made LF) and the 2026 files of individual houses it links, one per eldership, downloaded
on 2026-11-21. The links lead to `/lt/doclib/<id>`, which serves the file under its own name;
the copies are named after the eldership: `dotnuvos.docx` is "Dotnuvos seniūnija.docx",
`kedainiu-miesto.docx` "Kėdainių miesto seniūnija.docx", `surviliskio.docx` "Surviliškio
seniūnija (2).docx", `josvainiu.pdf` "Josvainiai.pdf" (the only PDF) and so on
(`test_kedainiai.COPIES` maps the ids to the copies). With the Address Register extract for
Kėdainių r. of the same day.

`raseiniai/` has the waste page of UAB "Raseinių komunalinės paslaugos" at
<https://www.rkp.lt/atlieku-tvarkymas/> and the 25 PDFs it links for 2026 (bulky waste and the
rules aside), downloaded on 2026-11-21 and renamed `<eldership>-mka.pdf` (mixed waste) and
`<eldership>-pak.pdf` (packaging and glass), with `-m-` for the towns' elderships: `betygalos-mka.pdf`
is "2026 metų atliekų surinkimo grafikai/Betygalos sen. mišrios komunalinės atliekos.pdf",
`ariogalos-m-pak.pdf` "... /Ariogalos m. pakuočių atliekos.pdf", `raseiniu-m-mka.pdf` "Raseinių m.
MKA.pdf" (in no year's folder) and `zalios.pdf` "... /Biologiškai skaidžios atliekos.pdf" (green
waste); `test_raseiniai.COPIES` lists all of them. With the Address Register extract for Raseinių
r. of the same day.

`jonava/` has the two schedule pages of UAB "Jonavos paslaugos", the elderships' at
<https://www.jonavospaslaugos.lt/straipsniai/atlieku-tvarkymo-grafikas-jonavos-rajono-seniuniju-gyventojams>
(`page.html`) and the town's at `.../atlieku-tvarkymo-grafikas-jonavos-miesto-gyventojams`
(`page-town.html`), and the nine 2026 PDFs they link, downloaded on 2026-11-21 and renamed after
their elderships: `bukoniu.pdf` is "2026-m.--grafikas-Bukonių-seniūnija.pdf", `ruklos.pdf`
"2026-m.--grafikas-buvusios-Ruklos-seniūnija.pdf", `jonavos-m.pdf`
"Maketas-grafikas-2026-Derinimui-2.pdf" (the town) and so on (`test_jonava.COPIES`). With the
Address Register extract for Jonavos r. of the same day.

`kretinga/` has the schedule page of SĮ "Kretingos komunalininkas" (Kretingos r.) at
<https://www.kretkom.lt/atlieku-isvezimo-grafikai/> and the 2026 PDFs it links, downloaded on
2026-11-21 and renamed: `misrios-2026-h1.pdf` is "2026 m- mišrios atliekos  I pusmetis.pdf"
(mixed waste, January-June), `misrios-2026-h2.pdf` "GRAFIKAS 2026 m- mišrios atliekos  II
pusmetis (7-12 mėn).pdf" (July-December), `pakuotes-2026.pdf` "2026 m- PA grafikas.pdf"
(packaging and glass), `maisto-2026.pdf` "Maisto atliekų surinkimas 2026 m.pdf" (Kretinga's
food waste) and `zaliosios-2026.pdf` "Žaliųjų-biriųjų atliekų išvežimo grafikas Kretingos mieste
2026 m- 04-11 mėn_.pdf" (Kretinga's green waste, April-November). With the Address Register
extract for Kretingos r. of the same day.

`moletai/` has the schedule page of UAB "Molėtų švara" (Molėtų r.) at
<https://www.moletusvara.lt/atlieku-surinkimo-grafikai/> and the twelve 2026 PDFs it links,
downloaded on 2026-11-21 and renamed after their elderships: `alantos.pdf` is
"2026_ALANTOS_SEN_grafikas.pdf", `luokesos.pdf` "2026_LUOKESOS_SEN_ir_dalies_GIEDRAICIU_SEN_
grafikas.pdf", `moletu-m.pdf` "2026_MOLETU_MIESTAS_(1).pdf" (the town) and so on
(`test_moletai.COPIES`). With the Address Register extract for Molėtų r. of the same day.

`skuodas/` has the schedule page of Skuodo rajono savivaldybė (Skuodo r.) at
<https://skuodas.lt/atlieku-tvarkymas-ir-surinkimo-grafikai-2025-m/> and the 2026 spreadsheets
it links, downloaded on 2026-11-21 and renamed: `misrios-2026.xls` is "cia-1.xls" (mixed waste,
a legacy Excel workbook), `pakuotes-2026.xlsx` "cia.xlsx" (packaging) and `stiklo-2026.xlsx`
"cia-2.xlsx" (glass) (`test_skuodas.COPIES`). With the Address Register extract for Skuodo r. of
the same day.

`ukmerge/` has the mixed waste page of the Ukmergės r. municipality at
<https://www.ukmerge.lt/misrios-komunalines-atliekos/> and the four 2026 PDFs of UAB "Ukmergės
autobusų parkas" it links, downloaded on 2026-11-21 and renamed: `miestas-2026-h1.pdf` is
"2026_m._sausio-gegus_mn._Ukmerges_miesto_komunalini_ir_pakuoi_atliek_surinkimo_grafikas_(002).pdf"
(the town, January-May), `miestas-2026-h2.pdf` "2026_m._birelio-gruodio_mn._Ukmergs_miesto_...pdf"
(the town, June-December), and `rajonas-2026-h1.pdf` and `rajonas-2026-h2.pdf` the district's of
the same periods (`test_ukmerge.COPIES`). With the Address Register extract for Ukmergės r. of
the same day.

`anyksciai/` has the waste page of UAB "Anykščių komunalinis ūkis" (Anykščių r.) at
<https://anykom.lt/paslaugos/komunaliniu-atlieku-tvarkymas/> and the two 2026 PDFs it links,
downloaded on 2026-11-21 and renamed: `kaimai-2026.pdf` is `assets/uploads/2026/03/421f0ee1.pdf`
("MIŠRIŲ IR ANTRINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 M.", the villages and small towns, the
revision of 30 March 2026) and `miestas-2026.pdf` `assets/uploads/2025/12/02c3dd29.pdf` ("MIŠRIŲ,
ANTRINIŲ IR BIOLOGINIŲ ATLIEKŲ IŠVEŽIMO GRAFIKAS 2026 M." of Anykščiai). With the Address Register
extract for Anykščių r. of the same day.

`utena/` has the waste page of UAB "Utenos komunalininkas" (Utenos r.) at
<https://www.utenoskom.lt/paslaugos/atlieku-tvarkymas> and the two 2026 PDFs it links,
downloaded on 2026-11-22 and renamed: `miestas-2026.pdf` is "Grafikas antrinių ir mišrių 2026 m.
Utenos mieste.pdf" (the town) and `seniunijos-2026.pdf` "Grafikas antrinių ir mišrių 2026 m.
Utenos rajono seniūnijose.pdf" (the elderships, with their mixed waste rules)
(`test_utena.COPIES`). With the Address Register extract for Utenos r. of the same day.

`ignalina/` has the three schedule pages of SĮ "Kompata" (Ignalinos r.) at
<https://www.kompata.lt/grafikai/puslapis/> (`komunaliniu.html`, mixed waste),
<https://www.kompata.lt/grafikai/pakuociu-surinkimo-grafikas/> (`pakuociu.html`) and
<https://www.kompata.lt/grafikai/maisto-atlieku-surinkimo-grafikas/> (`maisto.html`), and the
three PDFs of the whole municipality they link, downloaded on 2026-11-22 and renamed:
`misrios-2026-11-2027-04.pdf` is
"Komunaliniu_atlieku_surinkimo_is_individualiu_konteineriu_2026m_-_2027m_11-04men-1.pdf" (mixed
waste, November 2026 to April 2027), `pakuotes-2026.pdf`
"2026_metu_plastiko__popieriaus__metalo__stiklo_pakuociu_surinkimo_is_individualiu_konteineriu_grafikas__atsisiusti_PDF_-1.pdf"
(packaging and glass, 2026) and `maisto-2026-11-2027-04.pdf`
"Maisto_atlieku_isvezimo_grafikas_2026-2027m_.pdf" (food waste) (`test_ignalina.COPIES`). With
the Address Register extract for Ignalinos r. of the same day.

`elektrenai/` has the schedule pages of UAB "Elektrėnų komunalinis ūkis" (Elektrėnų sav.) on
eku.lt, downloaded on 2026-11-22 (line endings made LF) and named after their titles: `grafikai.html`
is the list of the years' pages, "Atliekų išvežimo grafikai"
(<https://www.eku.lt/atlieku-ir-teritoriju-tvarkymas/atlieku-isvezimo-grafikai/569>), `2026.html`
the page "2026 m." (…/2026-m./652), `2026-rusiuoju.html` its "Rūšiuoju buitinės atliekas" (…/654),
`2026-buitiniu.html` "Buitinių atliekų išvežimo grafikas" (…/656, mixed waste) and
`2026-antriniu.html` "Antrinių (rūšiuojamų) atliekų išvežimo grafikas" (…/653, packaging and
glass); the `2025*.html` files are the same pages of 2025 (…/651, 629, 627, 628)
(`test_elektrenai.COPIES`). With the Address Register extract for Elektrėnų sav. of the same day.

`sirvintos/` has the two schedule pages of the Širvintų r. municipality (sirvintos.lt),
`misrios-page.html` (mixed waste) and `antrines-page.html` (packaging and glass), and the PDFs
they link, downloaded on 2026-11-22 and renamed: `misrios-2026-06-12.pdf` is
"misrios-grafikas-2026-m_06-16.pdf" (mixed waste, June-December 2026), `misrios-2026-04-06.pdf`
"grafikas-mk-2026-m..pdf" (April-June 2026) and `antrines-2026.pdf`
"sirvintos-2026-m.-grafikas.pdf" (packaging and glass, 2026) (`test_sirvintos.COPIES`); and
`misrios-2025-05-2026-04.pdf`, "grafikas-sirvintos-mka-2025-2026.pdf" (May 2025-April 2026), which
the page linked in 2025 (web archive) and the site still serves. With the Address Register extract
for Širvintų r. of the same day.

`zarasai/` has the waste page of the Zarasų r. municipality
(<https://www.zarasai.lt/veiklos-sritys/aplinkos-apsauga/atlieku-tvarkymas/269>) and
`pakuotes-2026.pdf`, the packaging and glass PDF it links
("pakuociu-ir-antriniu-zaliavu-isvezimo-is-ind.-valdu-grafikas_2026.pdf"), downloaded on
2026-11-22, with the Address Register extract for Zarasų r. of the same day. The mixed waste scan
("misriu.pdf", 1.4 MB of images) isn't kept: `test_zarasai` reads the committed transcription in
`pipeline/data/rules-zarasu-r.json` with the hash of a few test bytes in place of the scan's.

These files belong to their publishers and are **not** covered by this project's Apache 2.0
license.

When a publisher changes the format, add the new file here and a test that covers it.

`registry-*.json` and `addresses-sample.*` are extracts of the Address Register (Adresų
registras) open data of VĮ Registrų centras, from get.data.gov.lt and
registrucentras.lt/aduomenys. The address sample covers Avižieniai and Aleksandravas only.

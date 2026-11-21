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
2026-11-17, with the Address Register extract for Mažeikių r. of the same day.

`gargzdu/` has the page of VšĮ "Gargždų švara" (Klaipėdos r.) at
<https://www.gargzdusvara.eu/komunaliniu-atlieku-tvarkymo-grafikai/> and the 2026 spreadsheet it
links, downloaded on 2026-11-21, with the Address Register extract for Klaipėdos r. of the same
day. `2025 MKA+AZ (1).xlsx` is the 2025 spreadsheet, still on the site at the address the page
linked in 2025 (other column titles, spaces in the lists of days, a second sheet).

`taurage/` has the schedule page of UAB "Tauragės regiono atliekų tvarkymo centras" at
<https://www.uabtratc.lt/atlieku-surinkimo-grafikai/> and the two 2026 PDFs of Jurbarko r. it
links (mixed and green waste, packaging and glass), downloaded on 2026-11-21, with the Address
Register extract for Jurbarko r. of the same day.

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

These files belong to their publishers and are **not** covered by this project's Apache 2.0
license.

When a publisher changes the format, add the new file here and a test that covers it.

`registry-*.json` and `addresses-sample.*` are extracts of the Address Register (Adresų
registras) open data of VĮ Registrų centras, from get.data.gov.lt and
registrucentras.lt/aduomenys. The address sample covers Avižieniai and Aleksandravas only.

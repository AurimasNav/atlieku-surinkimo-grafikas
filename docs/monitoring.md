# Monitoring the data

The daily **Schedule data** job reads the providers' files. When a provider changes a file's
format, moves it or introduces something the parser doesn't understand, the build of that
source fails **and yesterday's data stays published**, so nothing breaks for users right away.
GitHub emails the repository owner about the failed run, but the reliable signal is the data
itself: it stops getting newer.

Users see it too: when the data of the company behind their schedule hasn't been rebuilt for 7
days (`providers[].generatedAt`, or Kauno švara's `generatedAt`), the app shows a warning with a
link to the company's official schedule (`app/src/lib/freshness.ts`).

There are forty-three sources:

| `source` | Company | Published in |
|---|---|---|
| `nemencine` | UAB „Nemenčinės komunalininkas“, 12 elderships of Vilniaus r. | `schedule.json` (rows and places without a `provider` field) |
| `nemezio` | UAB „Nemėžio komunalininkas“, the other 11 elderships of Vilniaus r. | `schedule.json` (`provider: "nemezio"`) |
| `kauno` | UAB „Kauno švara“, Kauno r. | `kauno-r/` |
| `kaisiadorys` | UAB „Kauno švara“, Kaišiadorių r. | `kauno-r/` (elderships with `municipality: "Kaišiadorių r."`) |
| `mazeikiai` | UAB „Telšių regiono atliekų tvarkymo centras“, Mažeikių r. | `mazeikiu-r/` |
| `telsiai` | UAB „Telšių regiono atliekų tvarkymo centras“, Telšių r. | `mazeikiu-r/` (`provider: "telsiai"`) |
| `plunge` | UAB „Telšių regiono atliekų tvarkymo centras“, Plungės r. | `mazeikiu-r/` (`provider: "plunge"`) |
| `rietavas` | UAB „Telšių regiono atliekų tvarkymo centras“, Rietavo sav. | `mazeikiu-r/` (`provider: "rietavas"`) |
| `klaipedos` | VšĮ „Gargždų švara“, Klaipėdos r. | `klaipedos-r/` |
| `jurbarkas` | UAB „Tauragės regiono atliekų tvarkymo centras“, Jurbarko r. | `jurbarko-r/` |
| `taurage` | UAB „Tauragės regiono atliekų tvarkymo centras“, Tauragės r. | `jurbarko-r/` (`provider: "taurage"`) |
| `silale` | UAB „Tauragės regiono atliekų tvarkymo centras“, Šilalės r. | `jurbarko-r/` (`provider: "silale"`) |
| `pagegiai` | UAB „Tauragės regiono atliekų tvarkymo centras“, Pagėgių sav. | `jurbarko-r/` (`provider: "pagegiai"`) |
| `siauliai` | UAB „Šiaulių regiono atliekų tvarkymo centras“, Šiaulių r., Akmenės r., Joniškio r., Kelmės r. and Pakruojo r. | `sratc/` |
| `radviliskis` | UAB „Šiaulių regiono atliekų tvarkymo centras“, Radviliškio r. | `sratc/` (`provider: "radviliskis"`) |
| `alytus` | UAB „Alytaus regiono atliekų tvarkymo centras“, Alytaus r., Prienų r., Lazdijų r., Varėnos r., Druskininkų and Birštono sav. | `alytaus-ratc/` (rows with the municipality in `district`) |
| `pasvalys` | UAB „Panevėžio regiono atliekų tvarkymo centras“, Pasvalio r. | `panevezio-ratc/` (`provider: "pasvalys"`) |
| `rokiskis` | UAB „Panevėžio regiono atliekų tvarkymo centras“, Rokiškio r. | `panevezio-ratc/` (`provider: "rokiskis"`) |
| `birzai` | UAB „Panevėžio regiono atliekų tvarkymo centras“, Biržų r. | `panevezio-ratc/` (`provider: "birzai"`) |
| `panevezio-r` | UAB „Panevėžio regiono atliekų tvarkymo centras“, Panevėžio r. | `panevezio-ratc/` (`provider: "panevezio-r"`) |
| `marijampole` | UAB „Marijampolės apskrities atliekų tvarkymo centras“, Marijampolės sav. | `maatc/` (`provider: "marijampole"`) |
| `vilkaviskis` | UAB „Marijampolės apskrities atliekų tvarkymo centras“, Vilkaviškio r. | `maatc/` (`provider: "vilkaviskis"`) |
| `kalvarija` | UAB „Marijampolės apskrities atliekų tvarkymo centras“, Kalvarijos sav. | `maatc/` (`provider: "kalvarija"`) |
| `kazluruda` | UAB „Marijampolės apskrities atliekų tvarkymo centras“, Kazlų Rūdos sav. | `maatc/` (`provider: "kazluruda"`) |
| `sakiai` | UAB „Marijampolės apskrities atliekų tvarkymo centras“, Šakių r. | `maatc/` (`provider: "sakiai"`) |
| `raseiniai` | UAB „Raseinių komunalinės paslaugos“, Raseinių r. | `raseiniu-r/` (`provider: "raseiniai"`) |
| `jonava` | UAB „Jonavos paslaugos“, Jonavos r. | `jonavos-r/` (`provider: "jonava"`) |
| `kretinga` | SĮ „Kretingos komunalininkas“, Kretingos r. | `kretingos-r/` |
| `silute` | UAB „Ecoservice“, Šilutės r. | `silutes-r/` (`provider: "silute"`) |
| `trakai` | UAB „Ecoservice“, Trakų r. | `ecoservice/` (`provider: "trakai"`) |
| `salcininkai` | UAB „Ecoservice“, Šalčininkų r. | `ecoservice/` (`provider: "salcininkai"`) |
| `kedainiai` | Kėdainių rajono savivaldybės administracija (collected by UAB „Ekonovus“), Kėdainių r. | `kedainiu-r/` (`provider: "kedainiai"`) |
| `moletai` | UAB „Molėtų švara“, Molėtų r. | `moletu-r/` (`provider: "moletai"`) |
| `skuodas` | Skuodo rajono savivaldybė (collected by UAB „Ekonovus“), Skuodo r. | `skuodo-r/` |
| `ukmerge` | UAB „Ukmergės autobusų parkas“, Ukmergės r. | `ukmerges-r/` |
| `anyksciai` | UAB „Anykščių komunalinis ūkis“, Anykščių r. | `anyksciu-r/` (`provider: "anyksciai"`) |
| `utena` | UAB „Utenos komunalininkas“, Utenos r. | `utenos-r/` |
| `ignalina` | SĮ „Kompata“, Ignalinos r. | `ignalinos-r/` |
| `elektrenai` | UAB „Elektrėnų komunalinis ūkis“, Elektrėnų sav. | `elektrenu-sav/` |
| `sirvintos` | Širvintų rajono savivaldybė (collected by UAB „Ecoservice“), Širvintų r. | `sirvintu-r/` (`provider: "sirvintos"`) |
| `kupiskis` | UAB „Kupiškio komunalininkas“, Kupiškio r. | `kupiskio-r/` |
| `svencionys` | Švenčionių rajono savivaldybė, Švenčionių r. | `svencioniu-r/` |
| `zarasai` | Zarasų rajono savivaldybė (mixed waste collected by UAB „Zarasų būstas“, packaging and glass by UAB „Zarasų komunalininkas“), Zarasų r. | `zarasu-r/` (`provider: "zarasai"`) |

The two Vilniaus r. companies share one `schedule.json`, so the app needs one download. When
one of them fails, its part of yesterday's file is kept (its `providers[].generatedAt` stays
old) and the run gets a warning annotation; the other part is still updated. If a company has
no published part to keep, the file is published without it.

`kauno` and `kaisiadorys` come from one file of Kauno švara and are built by one step into
`kauno-r/`, so installed apps find Kaišiadorių r. addresses without an update. They share
`generatedAt` but are counted apart (Kaišiadorių r. in `otherMunicipalities[]` of
`kauno-r/schedule.json`). If the rows of Kauno r. can't be read, the step fails and yesterday's
`kauno-r/` is kept for both. If only those of Kaišiadorių r. can't (too few, or too many not
understood), Kauno r. is published without them: `kaisiadorys` disappears from `metrics.txt`
and `ScheduleDataSourceMissing` fires.

`siauliai` is one file a year for each of five municipalities, from one site in one template,
built by one step into `sratc/`. If any of the five files can't be read, their part of
yesterday's file is kept for all five (its `generatedAt` stays old, so `ScheduleDataStale`
fires) and the run gets a warning annotation. If one municipality's places stop matching the
Address Register (`sratc.check_municipalities`), the step fails and yesterday's `sratc/` is
kept. Its metrics are the five together: the last date is the latest of the five, so
`ScheduleDataRunsOut` stays quiet if one municipality posts next year's file and another
doesn't; the build's warnings name the late one ("Akmenės r.: no schedule for 2027 on the
page").

`radviliskis` is Radviliškio r., from the same site in other layouts, by other collectors:
mixed waste (with the town's green waste) a quarter at a time, packaging and glass a year at a
time. It is a second part of `sratc/schedule.json`, built by the same step but on its own: when
one of the two parts fails, its part of yesterday's file is kept and the other is still
updated. The next quarter's mixed waste file is read as soon as the page links it, next to the
last one or in its place; until its months start, its places continue those of the quarter in
force. If no newer file is linked when a quarter ends, its places keep their last dates and the
build warns ("Radviliškio r.: the mixed waste schedule ended on 2026-12-31; no newer one is
read"). If the page replaces the last quarter's file before the next one starts, that quarter's
last dates are lost, with a warning ("no mixed waste schedule for today; the next starts on
…").

`alytus` is one source for the six municipalities of Alytaus RATC: one page, one company behind
the schedules, one build step. A file of any of them that can't be read, or a municipality left
without mixed waste schedules (`aratc.check_places`), fails the build, and yesterday's
`alytaus-ratc/` is kept for all six. Its last pickup date per waste type is the latest of the
six; a municipality whose file has ended without a newer one shows as a build warning
("Lazdijų r. household: the schedule ended on …").

The four municipalities of Telšių RATC share `mazeikiu-r/schedule.json`, a part (`providers[]`)
each, built by one step, so installed apps find Telšių r., Plungės r. and Rietavo sav. without
an update. The folder keeps its name, and `mazeikiai` still means Mažeikių r. alone, so
existing dashboards and alerts keep working. When one municipality fails, its part of
yesterday's file is kept (its `generatedAt` stays old, so `ScheduleDataStale` fires for it) and
the run gets a warning annotation; the others are still updated. A municipality with no
published part to keep is left out. If none can be built, yesterday's `mazeikiu-r/` is kept.

The four municipalities of Tauragės RATC share `jurbarko-r/schedule.json` in the same way, a
part each: `jurbarkas` still means Jurbarko r. alone, and Tauragės r., Šilalės r. and Pagėgių
sav. are `taurage`, `silale` and `pagegiai`. Built by one step; a municipality that fails keeps
its part of yesterday's file, and if none can be built, yesterday's `jurbarko-r/` is kept.

The four municipalities of Panevėžio RATC share `panevezio-ratc/schedule.json` and
`addresses.json` the same way, a part each, built by one step. A municipality whose build
fails, or whose settlements stop getting schedules (`pratc.check_places`), keeps its part of
yesterday's file (its `generatedAt` stays old, so `ScheduleDataStale` fires for it) and the run
gets a warning annotation; the others are still updated. If none can be built, yesterday's
`panevezio-ratc/` is kept. Installed apps find `panevezio-ratc/` through `regions.json` (below).

Panevėžio r.'s mixed waste schedule is a Word document (.doc), a table of routes, some with
notes in free words under them (a pickup moved for a holiday, for some villages only; one house
with a route of its own). The routes without notes are read from the file. Those with notes are
read from their transcription in `pipeline/data/schedule-panevezio-r-mixed.json`, which is used
only while a route's text in the file is exactly the text transcribed (`pratc_word.py`). If the
file can't be read, because a route has notes (or a text after the table) the transcription
doesn't have or its layout changed, `panevezio-r` keeps its mixed waste rows of yesterday's data,
its packaging and glass are still updated, and the build warns ("Mišrių komunalinių
grafikas1.doc: can't be read (ValueError: …: notes that schedule-panevezio-r-mixed.json doesn't
have: route 13 (…); re-transcribe it …); yesterday's 29 household rows of Panevėžio r. are
kept"), so `ScheduleDataNewWarnings` fires but `generatedAt` moves. Re-transcribe the routes
it names (CONTRIBUTING.md). Next year's document will need that too, since its notes are about
next year's holidays: until it is transcribed, this year's rows run out and
`ScheduleDataRunsOut` fires for `panevezio-r` mixed waste.

The five municipalities of Marijampolė county share `maatc/schedule.json` in the same way, a
part each, built by one step from the regional waste centre's page of each municipality (the
schedules of UAB „Ecoservice“ and UAB „Ekonovus“): a municipality whose files can't be read
keeps its part of yesterday's file, the others are still updated. Installed apps find `maatc/`
through `regions.json` (below).

`kedainiai` is Kėdainių r.: a file per eldership, eleven of them, linked from the municipality's
page under the heading of their year (Word documents, and a PDF for Josvainių sen. in 2026),
built by one step into `kedainiu-r/` with a part of its own. A file that can't be read keeps
its eldership's rows of yesterday's data, as for `raseiniai` (below), and the build warns
("Dotnuvos seniūnija (2026): can't be read (...); yesterday's 6 rows of Dotnuvos sen. are
kept"); if the build fails as a whole, the part of yesterday's file is kept (`ScheduleDataStale`).
An eldership missing from the page is a build warning ("no file for Vilainių sen. on the page").
The glass days are the packaging days printed in red, so a file that stops marking them in red,
or marks other days red, can't be read.

kedainiai.lt answers GitHub's runners 403 (their network, whatever the user agent), as silute.lt
does (below), and no other official source has the files: when the page or a file can't be
downloaded, the job reads the copy of the page and its files in `pipeline/data/schedules-kedainiu-r/`
in the same way as Šilutės r.'s, with a build warning that gives its age ("https://www.kedainiai.lt/...:
unavailable (HTTP Error 403: Forbidden); used the copy from 2026-11-22 (0 days old)"). The
live-build check reads it too, so it still tests the parser. A CronJob in the maintainer's
cluster in Lithuania refreshes the copy daily (`uv run python -m schedule_pipeline.snapshot
--copies`, CONTRIBUTING.md) and opens and merges a PR when a file changed, so next year's files
(December or January) or a corrected one (about once a year, in the first half) reach the site
within a day. A copy whose files didn't change keeps its date, so the warning's age is how long
the files have stayed the same, and it asks for no refresh: a refresh that fails shows as
`KubeJobFailed` in that cluster. Next year's files are read as soon as the page (or the copy)
has them; if the page links them instead of this year's before 31 December, this year's last
pickups are lost, with a warning per eldership ("no 2026 schedule for Dotnuvos sen. on the
page"). Installed apps find `kedainiu-r/` through `regions.json` (below).

`raseiniai` and `jonava` are a folder each, `raseiniu-r/` and `jonavos-r/`, built by a step each
from a PDF per eldership and kind (25 files of Raseinių r., 9 of Jonavos r.). A file that can't be
downloaded or read keeps its rows of yesterday's data and the run's other files are still read:
the build warns ("Betygalos sen. mišrios komunalinės atliekos.pdf: can't be read (...);
yesterday's 4 household rows of Betygalos sen. are kept"), so `ScheduleDataNewWarnings` fires,
but `generatedAt` moves. A page that no longer links a file of every eldership fails the build,
and yesterday's folder is kept (`ScheduleDataStale`). Installed apps find both folders through
`regions.json` (below).

`kretinga` is Kretingos r., from the PDFs of the municipal company that collects its waste:
mixed waste half a year at a time (January to June, July to December), packaging and glass and
Kretinga's food waste a year at a time, Kretinga's green waste from April to November. Its own
step builds `kretingos-r/`; if it fails, yesterday's folder is kept. The next half year's mixed
waste file is read as soon as the page links it, next to the last one or in its place; until
its months start, its routes continue those of the half year in force that cover the same
places. If no newer file is linked when a half year ends, its routes keep their last dates and
the build warns ("the mixed waste schedule ended on 2026-12-31; no newer one is read"). If the
page replaces the last half year's file before the next one starts, its last dates are lost,
with a warning ("no mixed waste schedule for today; the next starts on …"). Installed apps
find `kretingos-r/` through `regions.json` (below).

The schedules UAB „Ecoservice“ publishes for Šilutės r. (on the municipality's page), and for
Trakų r. and Šalčininkų r. (on ecoservice.lt), are built by one module, a step per folder:
`silutes-r/` and `ecoservice/`, a part per municipality. A municipality whose files can't be
read keeps its part of yesterday's file; if none of a folder's can be built, yesterday's folder
is kept. Installed apps find both through `regions.json`. silute.lt refuses GitHub's runners
(HTTP 403), so `silute` is built from the copy of its page and file in `pipeline/data` that the
daily refresh takes (`uv run python -m schedule_pipeline.snapshot --copies`, as for Kėdainių
r.), with a build warning that says how old it is: next year's file reaches the site within a
day of being posted, and `ScheduleDataRunsOut` fires for `silute` in late December if it isn't.

`moletai` is Molėtų r., from a PDF per eldership and the town's (12 files) of the company that
collects its waste: mixed waste, packaging and glass a year at a time, and the town's green
waste. Its own step builds `moletu-r/`. As for `raseiniai` and `jonava`, a file that can't be
downloaded or read keeps its rows of yesterday's data, with a warning, and the other files are
still read; a page that no longer links a file of every eldership fails the build, and
yesterday's folder is kept. A notice next to a file on the page other than the one it had in
2026 is a build warning (`ScheduleDataNewWarnings`). Installed apps find `moletu-r/` through
`regions.json` (below).

`skuodas` is Skuodo r., from the three spreadsheets on the municipality's page (mixed waste,
packaging, glass), a year at a time. Its own step builds `skuodo-r/`; if it fails, yesterday's
folder is kept. Next year's file of a kind is read as soon as the page links it; until its year
starts, its routes continue this year's that cover the same places. If no newer file is linked
when a year ends, its routes keep their last dates and the build warns ("no mixed waste schedule
for 2027 on the page"). Installed apps find `skuodo-r/` through `regions.json` (below).

`ukmerge` is Ukmergės r., from the PDFs of UAB „Ukmergės autobusų parkas“ on the
municipality's page: mixed waste, packaging and glass of the town and of the district, a file
each per period, January to May and June to December. Its own step builds `ukmerges-r/`; if it
fails, yesterday's folder is kept. The next period's files are read as soon as the page links
them, next to the last ones or in their place; until their months start, their routes continue
those of the period in force that cover the same places. If no newer file of the town or of the
district is linked when a period ends, its routes keep their last dates and the build warns
("the schedule of the district ended on 2026-12-31; no newer one is read"). Installed apps find
`ukmerges-r/` through `regions.json` (below). ukmerge.lt refuses GitHub's runners (HTTP 403), so
`ukmerge` is built from the copy of its page and files in `pipeline/data/schedules-ukmerges-r/`
that the daily refresh takes (as for Kėdainių r.), with a build warning that says how old it
is: the next period's files reach the site within a day of being posted (mid-December and
mid-May), and `ScheduleDataRunsOut` fires for `ukmerge` in late May and December if they
aren't.

`anyksciai` is Anykščių r., from the two PDFs a year of the municipal company that collects its
waste: one of the villages and small towns (mixed waste, packaging and glass) and one of
Anykščiai (also green waste). Its own step builds `anyksciu-r/`. A file that can't be downloaded
or read keeps its rows of yesterday's data and the other file is still read, with a build warning
("421f0ee1.pdf: can't be read (...); yesterday's 69 rows of the villages are kept"), so
`ScheduleDataNewWarnings` fires but `generatedAt` moves; a page that no longer links both fails
the build, and yesterday's folder is kept (`ScheduleDataStale`). The company revises a year's
file in its year (the villages' 2026 file on 30 March): the page links the new one by the same
text, and of two files of one year the one uploaded last is read. Installed apps find
`anyksciu-r/` through `regions.json` (below).

`utena` is Utenos r., from the two PDFs of UAB „Utenos komunalininkas“ (the town's and the
elderships'), a year at a time: mixed waste, packaging and glass, and the town's green waste. The
elderships' mixed waste is written in words ("kiekvieno mėnesio pirmą dieną", the first day of
every month), which the build turns into the year's dates, a Sunday or a public holiday moved to
the next day as the file's note says; a rule in other words fails the build. Its own step builds
`utenos-r/`. As for `moletai`, a file that can't be downloaded or read keeps its rows of
yesterday's data, with a warning, and the other file is still read; a page without the town's or
the elderships' file fails the build, and yesterday's folder is kept. The page writes the rules
too; if the elderships it gives a day differ from the file's, the build warns
(`ScheduleDataNewWarnings`). Installed apps find `utenos-r/` through `regions.json` (below).

`ignalina` is Ignalinos r., from the PDFs of SĮ „Kompata“ on kompata.lt: mixed waste and food
waste half a year at a time (November to April, May to October: a period crosses the new year),
packaging and glass a year at a time. Its own step builds `ignalinos-r/`; if it fails,
yesterday's folder is kept. The next period's file of a kind is read as soon as a page links
it, next to the last one or in its place; until its months start, its rows continue those of
the period in force that cover the same places. If no newer file is linked when a period ends,
its rows keep their last dates and the build warns ("the mixed waste schedule ended on
2027-04-30; no newer one is read"). If a page replaces the last period's file before the next
one starts, its last dates are lost, with a warning ("no mixed waste schedule for today; the
next starts on …"). Text next to a file's table other than its usual notes (a changed pickup,
say) is a build warning (`ScheduleDataNewWarnings`). Installed apps find `ignalinos-r/`
through `regions.json` (below).

`elektrenai` is Elektrėnų sav., from the schedule pages (HTML tables, no files) of UAB
„Elektrėnų komunalinis ūkis“ on eku.lt: mixed waste, and packaging and glass, of the households
that sort their waste, a page each per year. The pages are found from the company's list of the
years' pages ("2026 m."). Its own step builds `elektrenu-sav/`; if it fails (a table, a note or
a page of a layout it doesn't know), yesterday's folder is kept. Next year's pages are read as
soon as its year's page lists them (a year's page that doesn't list them yet is a build warning
until its year starts); until then, its routes continue this year's that cover the same places.
If no newer year is listed when a year ends, its routes keep their last dates and the build
warns ("no page of 2027"). Installed apps find `elektrenu-sav/` through `regions.json` (below).

`sirvintos` is Širvintų r., from the PDFs on the municipality's two pages: mixed waste for
periods of their own (May to April until 2026, then April to June and June to December 2026),
packaging and glass a year at a time. Its own step builds `sirvintu-r/`; if it fails, yesterday's
folder is kept. A mixed waste file's period is the months of its table. The next period's file
is read as soon as the page links it, next to the last one or in its place; until its months
start, its routes continue those of the period in force that cover the same places, and from its
first month it replaces the last file (the June-December 2026 file replaced April-June's June).
If no newer file is linked when a period ends, its routes keep their last dates and the build
warns ("the mixed waste schedule ended on 2026-12-31; no newer one is read"). Installed apps find
`sirvintu-r/` through `regions.json` (below). sirvintos.lt refuses GitHub's runners (HTTP 403),
so `sirvintos` is built from the copy of its pages and files in `pipeline/data/schedules-sirvintu-r/`
that the daily refresh takes (as for Kėdainių r.; the packaging page, kept as a file, counts as a
page, so its markup alone is no change), with a build warning that says how old it is: a new
period's or year's file reaches the site within a day of being posted (in 2026 two weeks into the
mixed waste periods, packaging in December).

`kupiskis` is Kupiškio r., from the page of UAB „Kupiškio komunalininkas“ on kupkom.lt. Its mixed
waste exists only as rules on the page ("2-as mėnesio antradienis", the second Tuesday of every
month), for the town's individual houses and for the villages of each eldership. Rules don't
expire, so the build turns them into dates for a rolling window, from a month ago to the end of
the 13th month ahead (in November 2026, to 31 December 2027), as Kauno švara's dates are
calculated ahead: its last mixed waste date is always about a year away, so `ScheduleDataRunsOut`
doesn't apply to it. What notices a broken page is the build itself: a rule in other words, a
section of no place it knows, an eldership without rules or a page without the packaging file fail
it, yesterday's folder is kept (its dates still reach a year ahead) and `ScheduleDataStale` fires
the next day. The build can't notice a page left unchanged while the company changes its days;
the town's dated schedule (a PDF a year) is checked against the town's rule, and other dates are a
build warning (`ScheduleDataNewWarnings`), as is a village that two rules name in two spellings.
Packaging and glass come in a PDF a half year (January to June, July to December), the food waste
of the town and four villages in one a year. The next period's file is read as soon as the page
links it, next to the last one or in its place; until its months start, its blocks continue those
in force that cover the same places. If no newer file is linked when a period ends, its blocks
keep their last dates and the build warns ("the packaging schedule ended on 2026-12-31; no newer
one is read"). Its own step builds `kupiskio-r/`; if it fails, yesterday's folder is kept.
Installed apps find `kupiskio-r/` through `regions.json` (below).

`svencionys` is Švenčionių r., from the PDFs on the municipality's page. Mixed waste is one
sheet of **rules** with no dates and no year (made in January 2025): a weekday and weeks of the
month, "I III" (the first and the third such weekday) or "II IV", per group of places. The build
turns them into dates for a **rolling window**, from the 31 days back the data keeps to the end
of the 13th month after today's (in November 2026: 22 October 2026 to 31 December 2027), so the
window moves on with every daily run and the mixed waste rows never run out; a public holiday
isn't moved (nothing in the files says it would be). Packaging and glass come a year at a time
(the 2026 file was uploaded in December 2025 and corrected on 5 January 2026): dates for nine
elderships, and for Pabradės and Magūnų sen. rules of the year's months ("IV pirmadienis", every
month), which become that year's dates only, so the file runs out like any yearly file. Its
own step builds `svencioniu-r/`. A file that can't be downloaded or read keeps its rows of
yesterday's data, with a warning (`ScheduleDataNewWarnings`), and the other file is still read;
a page without both, a rule or a note in words the build doesn't know, or text next to the tables
it doesn't know (a changed rule could be written there) fails that file. If the build fails as a
whole, yesterday's folder is kept (`ScheduleDataStale`). Next year's packaging file is read as soon
as the page links it; until its year starts, its rows continue this year's that cover the same
places. A dated packaging column whose dates aren't the rule in its header ("II mėnesio
trečiadienis") is a build warning. Installed apps find `svencioniu-r/` through `regions.json`
(below). svencionys.lt refuses GitHub's runners (HTTP 403), so `svencionys` is built from the
copy of its page and files in `pipeline/data/schedules-svencioniu-r/` that the daily refresh
takes (as for Kėdainių r.), with a build warning that says how old it is: next year's packaging
file, or a new sheet of rules, reaches the site within a day of being posted.

`zarasai` is Zarasų r., from the municipality's page: mixed waste is a scanned image of rules
("2-ą ir paskutinį mėnesio pirmadienį", the second and the last Monday of the month, and the
places of each route), which can't be read as text. It was transcribed once into
`pipeline/data/rules-zarasu-r.json`, with the scan's address and SHA-256. Every day the build
downloads the scan the page links and compares its hash: while it is the same, the rules become
dates from a month ago to about 13 months ahead, so the mixed waste schedule never runs out and
`ScheduleDataRunsOut` doesn't watch it. If the scan changed (a new hash), or the page no longer
links one scan, the build fails ("the published scan changed (new hash …); re-transcribe
pipeline/data/rules-zarasu-r.json") and yesterday's `zarasu-r/` is kept, so `ScheduleDataStale`
fires for `zarasai` the next day: transcribe the new scan (CONTRIBUTING.md) and merge the PR.
Packaging and glass come from a text PDF, a year at a time, read as usual. Both are one part,
the publisher's, as for Širvintų r. (the app takes a settlement's schedules from one place in
the file), so while the scan waits for its new transcription, a new packaging file waits too.
Installed apps find `zarasu-r/` through `regions.json` (below). zarasai.lt refuses GitHub's
runners (HTTP 403), so `zarasai` is built from the copy of its page, the scan and the packaging
file in `pipeline/data/schedules-zarasu-r/` that the daily refresh takes (as for Kėdainių r.),
with a build warning that says how old it is, and the hash check compares the copy's scan: a new
scan reaches the copy within a day of being posted, and the build stops the day the copy has it.

The job therefore publishes the state of the data with every run:

- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/metrics.txt` (Prometheus format)
- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/status.json` (the same as JSON)
- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/warnings.html` (every source's build
  warnings, the new ones first; `warnings.html#<source>` jumps to a source) and `warnings.json`
  (the same as JSON)

| Metric | Meaning |
|---|---|
| `siuksliaveze_data_generated_timestamp_seconds{source}` | when the published data of `nemencine` / `nemezio` / `kauno` / `kaisiadorys` / `mazeikiai` / `telsiai` / `plunge` / `rietavas` / `klaipedos` / `jurbarkas` / `taurage` / `silale` / `pagegiai` / `siauliai` / `radviliskis` / `alytus` / `pasvalys` / `rokiskis` / `birzai` / `panevezio-r` / `marijampole` / `vilkaviskis` / `kalvarija` / `kazluruda` / `sakiai` / `raseiniai` / `jonava` / `kretinga` / `silute` / `trakai` / `salcininkai` / `kedainiai` / `moletai` / `skuodas` / `ukmerge` / `anyksciai` / `utena` / `ignalina` / `elektrenai` / `sirvintos` / `kupiskis` / `svencionys` / `zarasai` was built |
| `siuksliaveze_data_areas{source,kind}` | schedules per waste type |
| `siuksliaveze_data_places{source}` | settlements (`nemencine`, `nemezio`; for `mazeikiai`, `telsiai`, `plunge`, `rietavas`, `klaipedos`, `jurbarkas`, `taurage`, `silale`, `pagegiai`, `siauliai`, `radviliskis`, `alytus`, `pasvalys`, `rokiskis`, `birzai`, `panevezio-r`, `marijampole`, `vilkaviskis`, `kalvarija`, `kazluruda`, `sakiai`, `raseiniai`, `jonava`, `kretinga`, `silute`, `trakai`, `salcininkai`, `kedainiai`, `moletai`, `skuodas`, `ukmerge`, `anyksciai`, `utena`, `ignalina`, `elektrenai`, `sirvintos`, `kupiskis`, `svencionys` and `zarasai` those with a schedule) or addresses (`kauno`, `kaisiadorys`) covered |
| `siuksliaveze_data_last_date_timestamp_seconds{source,kind}` | the last pickup date in the published schedules (not for `kauno` and `kaisiadorys`, whose dates are calculated ahead; `kupiskis` mixed waste is calculated ahead too, to the end of the 13th month, and `svencionys` mixed waste, the end of its rules' rolling window, about 13 months ahead; `zarasai`'s mixed waste dates are calculated ahead too, so its last date is always about 13 months away) |
| `siuksliaveze_data_warnings{source}` | warnings of the last build, e.g. rows not linked to a settlement |
| `siuksliaveze_data_new_warnings{source}` | warnings of the last build that [`pipeline/known-warnings.json`](../pipeline/known-warnings.json) doesn't list: new typos and renamed places show up here (see [Build warnings](#build-warnings)) |
| `siuksliaveze_status_checked_timestamp_seconds` | when the daily job last wrote this file |

If a source fails, its `generated` time stays old while `checked` keeps moving:
`ScheduleDataStale` (below) fires for that source. If the job doesn't publish at all (the
schedule didn't start, the run hit its time limit, the deploy failed), both stay old together:
that is one problem, so only `ScheduleDataNotPublished` fires, not an alert per source.

### Build warnings

Every build lists what it couldn't read cleanly: a row whose place isn't a settlement, a text
kept without exact dates, a site copy used because the site didn't answer. Most of them stay the
same from day to day and have been checked, so the count alone says little. Each part of
`schedule.json` (and Kauno švara's `kauno-r/schedule.json`, with its other municipalities)
therefore publishes the texts next to the count (`warningTexts`), and the status step compares
them with [`pipeline/known-warnings.json`](../pipeline/known-warnings.json), the warnings
someone has checked, per source. `siuksliaveze_data_new_warnings` counts the rest, and
`warnings.html` lists them first.

The comparison leaves out what changes from run to run while the warning stays the same: numbers
become `#` (row, page and line numbers, dates and years), and so do the months of the period in
the name of the file a warning starts with (`2026 m- birželis-gruodis mėn …xlsx row 715` and
next half year's `2027 m- sausis-birželis mėn …xlsx row 20` are both `# m- # mėn …xlsx row #`;
a rule's months, after the file name, stay). The numbers of a name stay: those of a place a row
names (`SB "Girios -7"`, `Kelmės miestas 3`, a house number, in "not a settlement …" and "not
linked to any settlement …" warnings, which have no row numbers) and a route's (`route 13` is
other places than `route 3`). A site copy's
"unavailable (…); used the copy from … (… days old)" becomes "unavailable; used the copy". A
source that published its data before the texts were published counts no new warnings.

A site copy used is never new, and `--write-known` doesn't list it: six sites (`kedainiai`,
`silute`, `sirvintos`, `svencionys`, `ukmerge`, `zarasai`) refuse GitHub's runners on some days
and answer on others, which nobody has to act on, and a baseline written on a day such a site
answered would otherwise turn its next refusal into an alert. A source whose build keeps failing
is `ScheduleDataStale`'s.

A new warning stays new until it is fixed or acknowledged, however many days pass. The live
check of a PR that touches `pipeline/` shows the same: its job summary compares each source's
warnings with the published ones and lists the new ones, and the check fails while there are
any that the published `warnings.json` doesn't list as new too. Those it does are already live
(the alert is firing, whatever the PR does): the summary lists them apart, as "already live",
and they don't fail the check, so one new warning on the site doesn't turn every pipeline PR
(Renovate's too) red. To acknowledge them, after checking that they are harmless:

1. Get the site the warnings come from: the `schedule-data-<PR>` artifact of the PR's live
   check, or the `github-pages` artifact of the daily run. The latter is a zip with
   `artifact.tar` inside, kept for one day:
   `gh run download <run> -n github-pages -D dl && mkdir site && tar -xf dl/artifact.tar -C site`.
2. In `pipeline/`, run `uv run python -m schedule_pipeline.status --site <site> --write-known`.
   It rewrites `known-warnings.json` from the site's warnings: a source's list becomes what its
   build gave, so warnings it no longer gives are dropped; sources the site doesn't have keep
   their lists.
3. Commit `pipeline/known-warnings.json` (a branch and a PR, as always). Once it is merged and
   the next run has deployed, the metric goes back to 0 and the alert resolves.

To fix a warning instead, fix the parser or the data (an alias, a correction); once the build no
longer gives it, `--write-known` drops it from the file the next time.

### The index of regions

The last step before the deploy writes
`https://aurimasnav.github.io/atlieku-surinkimo-grafikas/regions.json`
(`schedule_pipeline.regions`): every region folder in `site/`, the root `schedule.json` of
Vilniaus r. included, with its `kind`, its `files` and its `providers`. It is generated from
what is about to be deployed, after the steps that keep yesterday's data, so nothing lists
regions by hand.

The app reads it on every refresh and downloads the folders it lists next to the ones it was
built with (`REGION_URLS` in `app/src/lib/config.ts`), so a new folder in the format of
`schedule.json` (`kind: "settlements"`, with an `addresses.json` for "Use my location")
reaches installed apps without an app update. If `regions.json` can't be downloaded, the app
uses the copy it saved last time, or its built-in list. A folder that a newer `regions.json`
no longer lists is taken off the phones, except the built-in ones, so remove a published folder
only on purpose. A folder in Kauno švara's per-address format (`kind: "addresses"`) is listed
too, but the app reads that format from `kauno-r/` only: another such folder still needs an
app update. Fields can be added to the file without a new `schemaVersion`; the app ignores the
ones it doesn't know, and regions of a kind it doesn't know.

## Prometheus

GitHub Pages serves the file as plain text, which Prometheus scrapes directly; no exporter and
no access from GitHub to your network is needed. The data changes once a day, so scrape rarely.

```yaml
scrape_configs:
  - job_name: siuksliaveze-data
    scheme: https
    metrics_path: /atlieku-surinkimo-grafikas/metrics.txt
    scrape_interval: 15m
    static_configs:
      - targets: [aurimasnav.github.io]
```

Alert rules:

Every rule reads the newest sample of the last 30 minutes with `last_over_time(...[30m])`. A
plain selector like `siuksliaveze_data_places` only looks back 5 minutes (Prometheus'
`--query.lookback-delta`), so with a 15-minute scrape it has no value for 10 of every 15
minutes: alerts with `for:` never fire, and the others fire and resolve every 15 minutes.
Keep the window at least twice the scrape interval. `ScheduleDataNotPublished` reads the last
hour instead: two missed scrapes in a row empty a 30-minute window, and the alert would resolve
with nothing fixed and fire again 30 minutes later.

```yaml
groups:
  - name: siuksliaveze-data
    rules:
      - alert: ScheduleDataNotPublished
        # The job runs daily at 04:17 UTC and writes checked_timestamp at the end of every run
        # that publishes, whatever its sources' builds did: 30 hours means the job itself missed
        # a run (the schedule didn't start, the run hit its time limit, the deploy failed). One
        # alert for all sources. [1h] bridges up to three missed scrapes in a row; a longer
        # outage is ScheduleDataNotScraped's. The newest sample still wins, so a publish clears it.
        expr: time() - last_over_time(siuksliaveze_status_checked_timestamp_seconds[1h]) > 30 * 3600
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "The daily job hasn't published for {{ $value | humanizeDuration }}"
          description: "Check the last run of the Schedule data workflow on GitHub."
      - alert: ScheduleDataStale
        # A source the last published run didn't rebuild: its build failed and yesterday's part
        # was kept, so its data lags the job's checked time by more than a run takes (2 hours).
        # It fires 30 hours after the source's last good build. While the whole job is late,
        # every source is about as old as the checked time, so only ScheduleDataNotPublished
        # fires. max(): `on ()` needs one checked series.
        expr: |-
          (time() - last_over_time(siuksliaveze_data_generated_timestamp_seconds[30m]) > 30 * 3600)
            and
          (max(last_over_time(siuksliaveze_status_checked_timestamp_seconds[30m]))
            - on () group_right last_over_time(siuksliaveze_data_generated_timestamp_seconds[30m])
            > 2 * 3600)
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "Schedule data of {{ $labels.source }} is {{ $value | humanizeDuration }} old"
          description: "The daily build of this source fails, so the job keeps publishing its old data. See the Schedule data workflow on GitHub."
      - alert: ScheduleDataShrank
        expr: last_over_time(siuksliaveze_data_places[30m]) < 0.9 * last_over_time(siuksliaveze_data_places[30m] offset 1d)
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }} covers 10% fewer places than yesterday"
      # A warning pipeline/known-warnings.json doesn't list (new typo or renamed place?). It
      # stays until the parser is fixed or the warning acknowledged (see Build warnings).
      - alert: ScheduleDataNewWarnings
        expr: last_over_time(siuksliaveze_data_new_warnings[30m]) > 0
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }}: {{ $value }} new build warnings (not in pipeline/known-warnings.json)"
          dashboard: "https://aurimasnav.github.io/atlieku-surinkimo-grafikas/warnings.html#{{ $labels.source }}"
      # Mažeikių r., Klaipėdos r., Jurbarko r. and Šiaulių RATC get one file per year. If next
      # year's isn't posted, or the job no longer recognises it, the build stays green while
      # the reminders stop after the last date. Only these sources: the quarterly files of the
      # Vilniaus r. companies come close to their last date every quarter. Klaipėdos r. collects
      # glass four or five times a year and green waste from April to November, Jurbarko r.
      # glass four times a year (last on 3 December 2026) and green waste last in mid-December,
      # and Šiaulių RATC glass four times a year (last between 30 October and 31 December 2026
      # in its five municipalities) and green and food waste last in November, before next
      # year's files are usually posted: so only their mixed waste and packaging.
      # Telšių r., Plungės r. and Rietavo sav. (same publisher as Mažeikių r.): every kind
      # of Telšių r. and Plungės r. ends on 28-31 December, and Plungės r. food waste on 18
      # December 2026, watched too: its 2027 file wasn't posted on 21 November, so this fires
      # from 11 December until it is. Rietavo sav. collects glass four times a year (last on 25
      # November 2027), so only its mixed waste and packaging.
      # Alytaus RATC's contract year runs from March to February. The last mixed waste pickups
      # of its six municipalities fall between 9 and 27 February 2027, and `alytus` has the
      # latest of them: the alert means none of next year's mixed waste files has been read.
      # Not its packaging and glass: those of Alytaus r. and Prienų r. run to March 2028 (a new
      # contract from December 2026), which hides the others' February ends.
      # Radviliškio r.: its mixed waste file covers a quarter (October-December 2026), its
      # packaging file a year, both to 31 December 2026. They were made in the last days before
      # their periods (the mixed waste file on 24 September, the 2026 packaging file on 29
      # December 2025), so a week's notice would fire every quarter: 2 days, so the alert means
      # the period's last pickups are 1-2 days away and nothing newer has been read. Not its
      # glass (four or five times a year, the latest on 25 December 2026, before next year's
      # file is usually posted) nor its green waste (last in November).
      # Tauragės r., Šilalės r. and Pagėgių sav. (same publisher as Jurbarko r.): the kinds
      # whose 2026 schedules end on 15-31 December, so this fires from 8 December at the
      # earliest. Tauragės r. glass is collected four times a year (last on 30 November 2026)
      # and Pagėgių sav. green waste last on 11 December, so not those.
      # Panevėžio RATC: the mixed waste, packaging and glass of its four municipalities end on
      # 25-31 December 2026 (glass is collected once a quarter, but some route has a pickup in
      # the last week). Not food waste, whose last pickups are on 10-23 December. Its 2026
      # files were uploaded on 30 and 31 December 2025, so expect this to fire in the last week
      # of December until next year's are read. Panevėžio r.'s mixed waste (a Word document,
      # dated, a year at a time) ends on 2 January 2027, a pickup a note of the 2026 document
      # moves from 1 January, so it fires from 26 December; the 2026 document was uploaded on 5
      # January 2026, and next year's must be transcribed before it is read (its notes), so
      # expect it to fire into January.
      # The five municipalities of Marijampolė county get calendar-year files, posted in
      # December (the 2026 PDFs were made between 2 and 16 December 2025). Mixed waste,
      # packaging and food waste end on 28-31 December everywhere. Not glass: every four weeks,
      # last on 18 December 2026 in Kazlų Rūdos sav. and on 24 December in Vilkaviškio r.
      # Raseinių r. and Jonavos r. get calendar-year files too (Raseinių r.'s 2026 PDFs were
      # made on 22 December 2025). Raseinių r.: mixed waste, packaging and glass end on 29-31
      # December (glass four times a year, but some route in December); not green waste, last
      # on 12 November. Jonavos r.: mixed waste and packaging end on 30-31 December; not glass,
      # four times a year, last on 30 October.
      # Kretingos r.: mixed waste comes half a year at a time, so it nears its end every June and
      # December (its last pickups on 30 June and 31 December 2026); packaging and Kretinga's food
      # waste a year at a time (last on 21 and 23 December 2026). Its files are posted a week or
      # two before their periods (the 2026 files were made on 15 December 2025, the July-December
      # mixed waste file on 23 June 2026), so a week's notice would fire every half year: 2 days,
      # as for Radviliškio r. Not glass (once a quarter, from the packaging file; the latest on 28
      # December 2026) nor green waste (April to November).
      # Šilutės r., Trakų r. and Šalčininkų r. (UAB „Ecoservice“): calendar-year files whose
      # every kind ends on 28-31 December 2026 (glass and packaging have a route with a pickup in
      # the last week). The 2026 files of Šilutės r. and Šalčininkų r. were made on 17-18
      # December 2025, Trakų r.'s on 15 January 2026, so expect this to fire for `trakai` from
      # about 24 December until next year's file is read.
      # Kėdainių r. gets calendar-year files: the latest mixed waste pickup is on 31 December
      # 2026 (Kėdainiai, every two weeks), packaging on 28 December, so this fires from 24
      # December if next year's files aren't read by then. In January the last date stays 31
      # December, in the past, so it keeps firing, rightly: the app has no dates until they
      # are. The 2026 files were made on 8 December 2025; the page with 2025's was dated 3
      # January 2025 (web archive). It was last edited on 23 February 2026, for a corrected
      # Surviliškio sen. file.
      # Not glass: four times a year, last in October.
      # Molėtų r.: calendar-year files (the 2026 PDFs were made on 18 December 2025). Mixed
      # waste ends on 1-14 December 2026 and packaging on 15-31 December, so this fires from 7
      # December until next year's files are read. Not glass (four times a year, last on 30
      # October) nor the town's green waste (last on 17 December).
      # Skuodo r.: calendar-year files; mixed waste ends on 31 December 2026 (Skuodas town's
      # weekly pickups on 25 and 28 December) and packaging on 29 December. Its 2026 packaging
      # file was uploaded on 30 December 2025, the mixed waste file on 23 January 2026, so expect
      # this to fire from 24 December until next year's files are read, maybe into January. Not
      # glass, five times a year, last on 2 December 2026.
      # Ukmergės r.: every kind comes in two periods a year, January to May and June to
      # December, so mixed waste and packaging near their ends every May and December (the last
      # pickups on 28-29 May and 29 December 2026). The files are posted two or three weeks
      # before their periods (made on 17-18 December 2025 and 13 May 2026), but are read from
      # the copy in pipeline/data (ukmerge.lt refuses the runners), which the daily refresh
      # takes after they are posted: a week's notice, as for Šilutės r., so there is time to
      # refresh it by hand if that fails. Not
      # glass, once or twice a period and last weeks before its end (1 May and 4 December
      # 2026). The town's and the district's files are one source: a late file of one of them
      # doesn't fire while the other's newer file is read.
      # Anykščių r.: calendar-year files; mixed waste, packaging and glass end on 31 December 2026
      # (glass four times a year, but one route on 31 December). Not Anykščiai's green waste,
      # last on 21-22 December. The 2026 files were made on 18 December (the town's) and 31
      # December 2025 (the villages'), so expect this to fire from 24 December until next
      # year's villages' file is read.
      # Utenos r.: calendar-year files, the town's and the elderships' (the 2026 PDFs were made
      # on 1 and 9 December 2025 and uploaded on 23 December). Mixed waste ends on 30 December
      # 2026 (the town's; the elderships' rules give 1-14 December) and packaging on 30 December,
      # so this fires from 23 December until next year's files are read. Not glass (four times
      # a year, last on 30 October) nor the town's green waste (last on 15-17 December). As for
      # Ukmergės r., a late file of the town or of the elderships doesn't fire while the other's
      # newer file is read.
      # Ignalinos r.: mixed waste and food waste come half a year at a time, November to April
      # and May to October, packaging a year at a time. The files are made in the last days
      # before their periods (the November-April ones on 29 October 2026, the 2026 packaging
      # file on 22 December 2025), so a week's notice would fire every half year: 2 days, as for
      # Kretingos r., so the alert means the last pickups are 1-2 days away and nothing newer
      # has been read (mixed waste ends on 30 April 2027, packaging on 29 December 2026). Not
      # food waste (once a month, last on 14-16 April 2027, two weeks before the next half
      # year's file is usually posted) nor glass (twice a year, last on 29 October 2026).
      # Elektrėnų sav.: a page per kind and calendar year. Mixed waste ends on 1-17 December 2026
      # (Elektrėnai's individual houses last, every two weeks), packaging on 1-29 December, so
      # this fires from 10 December until the 2027 pages are read; when the 2026 pages were
      # posted isn't known (they carry no date). Not glass: four times a year (last on 3
      # November to 28 December 2026, by route).
      # Širvintų r.: mixed waste comes for periods of their own (April-June and June-December
      # 2026, May-April before), each file posted around its period's start (made on 16 April
      # and 16 June 2026; the May-April files a week before May), so a week's notice would fire
      # every period: 2 days, as for Kretingos r. (its last pickup on 28 December 2026); expect
      # it to fire at the end of a period until the next file is posted, two weeks into its
      # months in 2026, and read (sirvintos.lt refuses the runners: the daily refresh of the
      # copy in pipeline/data takes it). Packaging and glass a year at a time (the 2026 file was
      # made on 18 December 2025), ending on 28 and 29 December 2026 (some route's glass in the
      # last week): a week's notice, so there is time to refresh the copy by hand if that fails.
      # Kupiškio r.: its mixed waste is calculated ahead from the page's rules, to the end of the
      # 13th month, so it never nears its last date and isn't watched: a page that can't be read
      # fails the build, and ScheduleDataStale fires instead. Packaging comes half a year at a
      # time (its last pickups on 30 June and 30 December). The files are posted around the
      # start of their half years (the January-June 2025 one made on 18 December 2024 and
      # uploaded in January, the July-December 2026 one made on 3 June and uploaded in July), so
      # a week's notice would fire every half year: 2 days, as for Kretingos r. Not glass (twice
      # a half year, last on 11-16 November 2026) nor the food waste of the town and four
      # villages (every second and fourth Wednesday, last on 23 December 2026, the next year's
      # file posted around New Year).
      # Švenčionių r.: only packaging, a year at a time (the 2026 file was uploaded in December
      # 2025), dates for nine elderships and the year's rules for Pabradės and Magūnų sen., the
      # last pickup on 28 December 2026 (Pabradė's fourth Monday), so this fires from 21 December
      # until next year's file is read (svencionys.lt refuses the runners: the daily refresh of
      # the copy in pipeline/data takes it; a week's notice leaves time to refresh it by hand if
      # that fails). Not mixed waste: its rules never end, and its dates run
      # to the end of a window about 13 months ahead that moves with every build (its last date
      # is never near; a build that fails shows as ScheduleDataStale). Not glass: four times a
      # year in the nine elderships (last on 7 December 2026), every other month for Pabradė
      # (last on 13 November).
      # Zarasų r.: packaging and glass a year at a time (the 2026 file was made on 29 December
      # 2025), ending on 18-30 December 2026 (every schedule has glass in December), so this fires
      # from about 23 December until next year's file is read (from the copy in pipeline/data:
      # zarasai.lt refuses the runners; a week's notice leaves time to refresh it by hand if the
      # daily refresh fails). Not its mixed waste: rules,
      # turned into dates 13 months ahead every day; a changed scan stops the build instead, and
      # ScheduleDataStale fires.
      - alert: ScheduleDataRunsOut
        expr: |-
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source=~"mazeikiai|telsiai|plunge"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source=~"klaipedos|jurbarkas|siauliai|rietavas",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="alytus",kind="household"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="radviliskis",kind=~"household|packaging"}[30m]) - time() < 2 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="silale"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="taurage",kind=~"household|packaging|food"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="pagegiai",kind=~"household|packaging|glass"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source=~"pasvalys|rokiskis|birzai|panevezio-r",kind=~"household|packaging|glass"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source=~"marijampole|vilkaviskis|kalvarija|kazluruda|sakiai",kind=~"household|packaging|food"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="raseiniai",kind=~"household|packaging|glass"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="jonava",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="kretinga",kind=~"household|packaging|food"}[30m]) - time() < 2 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source=~"silute|trakai|salcininkai"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="kedainiai",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="moletai",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="skuodas",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="ukmerge",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="anyksciai",kind=~"household|packaging|glass"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="utena",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="ignalina",kind=~"household|packaging"}[30m]) - time() < 2 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="elektrenai",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="sirvintos",kind="household"}[30m]) - time() < 2 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="sirvintos",kind=~"packaging|glass"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="kupiskis",kind="packaging"}[30m]) - time() < 2 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="svencionys",kind="packaging"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="zarasai",kind=~"packaging|glass"}[30m]) - time() < 7 * 86400
        for: 1h
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }}: the {{ $labels.kind }} schedule ends within a week"
      # A source that was in metrics.txt in the last 3 days is gone while the file itself is
      # fetched fine (its build failed and there was nothing to keep): ScheduleDataStale can't
      # fire for a series that no longer exists.
      - alert: ScheduleDataSourceMissing
        expr: |-
          group by (source) (last_over_time(siuksliaveze_data_generated_timestamp_seconds{job="siuksliaveze-data"}[3d]))
            unless on (source)
          group by (source) (last_over_time(siuksliaveze_data_generated_timestamp_seconds{job="siuksliaveze-data"}[30m]))
            and on ()
          (last_over_time(up{job="siuksliaveze-data"}[30m]) == 1)
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }} is missing from metrics.txt"
      # absent_over_time: also fires when the scrape job itself is gone.
      - alert: ScheduleDataNotScraped
        expr: |-
          last_over_time(up{job="siuksliaveze-data"}[30m]) == 0
            or absent_over_time(up{job="siuksliaveze-data"}[30m])
        for: 2h
        labels: { severity: warning }
        annotations:
          summary: "metrics.txt can't be fetched from GitHub Pages"
```

CI checks these examples with promtool whenever this file, the code that writes `metrics.txt`
or the tests change. They must parse, use only metrics the data job writes, and pass the
scenarios in [`monitoring.test.yml`](monitoring.test.yml) with the 15-minute scrape above:
stale data, a failing fetch, a schedule running out, fewer places, new warnings, a vanished
source and healthy data. Run the same locally with `sh docs/monitoring-check.sh` (needs
promtool and python3).

## Grafana without Prometheus

Add the [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/) data
source, query `status.json` (type JSON, URL above) and alert when `checkedAt` is older than
30 hours (the job didn't publish), and when `sources.nemencine.generatedAt`,
`sources.nemezio.generatedAt`, `sources.kauno.generatedAt`,
`sources.kaisiadorys.generatedAt`, `sources.mazeikiai.generatedAt`,
`sources.telsiai.generatedAt`, `sources.plunge.generatedAt`, `sources.rietavas.generatedAt`,
`sources.klaipedos.generatedAt`, `sources.jurbarkas.generatedAt`,
`sources.taurage.generatedAt`, `sources.silale.generatedAt`, `sources.pagegiai.generatedAt`,
`sources.siauliai.generatedAt`, `sources.radviliskis.generatedAt`,
`sources.alytus.generatedAt`, `sources.pasvalys.generatedAt`, `sources.rokiskis.generatedAt`,
`sources.birzai.generatedAt`, `sources.panevezio-r.generatedAt`,
`sources.marijampole.generatedAt`, `sources.vilkaviskis.generatedAt`,
`sources.kalvarija.generatedAt`, `sources.kazluruda.generatedAt`,
`sources.sakiai.generatedAt`, `sources.raseiniai.generatedAt`, `sources.jonava.generatedAt`,
`sources.kretinga.generatedAt`, `sources.silute.generatedAt`, `sources.trakai.generatedAt`,
`sources.salcininkai.generatedAt`, `sources.kedainiai.generatedAt`,
`sources.moletai.generatedAt`, `sources.skuodas.generatedAt`,
`sources.ukmerge.generatedAt`, `sources.anyksciai.generatedAt`,
`sources.utena.generatedAt`, `sources.ignalina.generatedAt`,
`sources.elektrenai.generatedAt`, `sources.sirvintos.generatedAt`,
`sources.kupiskis.generatedAt`, `sources.svencionys.generatedAt` or
`sources.zarasai.generatedAt` is older than 30 hours and more than 2 hours older than
`checkedAt` (that source's build fails), or missing. Without the second condition, a job that
doesn't publish raises an alert for every source.

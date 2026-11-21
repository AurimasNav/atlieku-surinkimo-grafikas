# Monitoring the data

The daily **Schedule data** job reads the providers' files. When a provider changes a file's
format, moves it or introduces something the parser doesn't understand, the build of that
source fails **and yesterday's data stays published**, so nothing breaks for users right away.
GitHub emails the repository owner about the failed run, but the reliable signal is the data
itself: it stops getting newer.

Users see it too: when the data of the company behind their schedule hasn't been rebuilt for 7
days (`providers[].generatedAt`, or Kauno švara's `generatedAt`), the app shows a warning with a
link to the company's official schedule (`app/src/lib/freshness.ts`).

There are thirty-two sources:

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
| `panevezio-r` | UAB „Panevėžio regiono atliekų tvarkymo centras“, Panevėžio r. (packaging and glass) | `panevezio-ratc/` (`provider: "panevezio-r"`) |
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
`panevezio-ratc/` is kept. `panevezio-r` has packaging and glass only: the centre publishes
Panevėžio r.'s mixed waste schedule as a Word document of rules with exceptions, which isn't
read. The app doesn't download this folder yet.

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
unavailable (HTTP Error 403: Forbidden); used the copy from 2026-11-22 (0 days old)") and, over
60 days, asks for a refresh. The live-build check reads it too, so it still tests the parser.
`uv run python -m schedule_pipeline.snapshot` saves it with the Address Register snapshots, from
a machine in Lithuania: refresh it also when the page gets next year's files (December or
January; expect `ScheduleDataRunsOut` in late December until then) or a corrected one (about
once a year, in the first half). Next year's files are read as soon as the page (or the copy)
has them; if the page links them instead of this year's before 31 December, this year's last
pickups are lost, with a warning per eldership ("no 2026 schedule for Dotnuvos sen. on the
page"). Installed apps find `kedainiu-r/` through `regions.json` (below).

`raseiniai` and `jonava` are a folder each, `raseiniu-r/` and `jonavos-r/`, built by a step each
from a PDF per eldership and kind (25 files of Raseinių r., 9 of Jonavos r.). A file that can't be
downloaded or read keeps its rows of yesterday's data and the run's other files are still read:
the build warns ("Betygalos sen. mišrios komunalinės atliekos.pdf: can't be read (...);
yesterday's 4 household rows of Betygalos sen. are kept"), so `ScheduleDataMoreWarnings` fires,
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
snapshot refresh takes (`uv run python -m schedule_pipeline.snapshot`), with a build warning
that says how old it is: next year's file reaches the site only with a refresh, and
`ScheduleDataRunsOut` fires for `silute` in late December until one is done.

The job therefore publishes the state of the data with every run:

- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/metrics.txt` (Prometheus format)
- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/status.json` (the same as JSON)

| Metric | Meaning |
|---|---|
| `siuksliaveze_data_generated_timestamp_seconds{source}` | when the published data of `nemencine` / `nemezio` / `kauno` / `kaisiadorys` / `mazeikiai` / `telsiai` / `plunge` / `rietavas` / `klaipedos` / `jurbarkas` / `taurage` / `silale` / `pagegiai` / `siauliai` / `radviliskis` / `alytus` / `pasvalys` / `rokiskis` / `birzai` / `panevezio-r` / `marijampole` / `vilkaviskis` / `kalvarija` / `kazluruda` / `sakiai` / `raseiniai` / `jonava` / `kretinga` / `silute` / `trakai` / `salcininkai` / `kedainiai` was built |
| `siuksliaveze_data_areas{source,kind}` | schedules per waste type |
| `siuksliaveze_data_places{source}` | settlements (`nemencine`, `nemezio`; for `mazeikiai`, `telsiai`, `plunge`, `rietavas`, `klaipedos`, `jurbarkas`, `taurage`, `silale`, `pagegiai`, `siauliai`, `radviliskis`, `alytus`, `pasvalys`, `rokiskis`, `birzai`, `panevezio-r`, `marijampole`, `vilkaviskis`, `kalvarija`, `kazluruda`, `sakiai`, `raseiniai`, `jonava`, `kretinga`, `silute`, `trakai`, `salcininkai` and `kedainiai` those with a schedule) or addresses (`kauno`, `kaisiadorys`) covered |
| `siuksliaveze_data_last_date_timestamp_seconds{source,kind}` | the last pickup date in the published schedules (not for `kauno` and `kaisiadorys`, whose dates are calculated ahead) |
| `siuksliaveze_data_warnings{source}` | warnings of the last build, e.g. rows not linked to a settlement: new typos show up here |
| `siuksliaveze_status_checked_timestamp_seconds` | when the daily job last wrote this file |

If a source fails, its `generated` time stays old while `checked` keeps moving. If the job
doesn't run at all, both stay old.

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
Keep the window at least twice the scrape interval.

```yaml
groups:
  - name: siuksliaveze-data
    rules:
      - alert: ScheduleDataStale
        # The job runs daily at 04:17 UTC; 30 hours means one run was missed or failed.
        expr: time() - last_over_time(siuksliaveze_data_generated_timestamp_seconds[30m]) > 30 * 3600
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "Schedule data of {{ $labels.source }} is {{ $value | humanizeDuration }} old"
          description: "The daily build of this source fails or doesn't run. See the Schedule data workflow on GitHub."
      - alert: ScheduleDataShrank
        expr: last_over_time(siuksliaveze_data_places[30m]) < 0.9 * last_over_time(siuksliaveze_data_places[30m] offset 1d)
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }} covers 10% fewer places than yesterday"
      - alert: ScheduleDataMoreWarnings
        expr: last_over_time(siuksliaveze_data_warnings[30m]) > last_over_time(siuksliaveze_data_warnings[30m] offset 1d)
        labels: { severity: info }
        annotations:
          summary: "{{ $labels.source }}: more build warnings than yesterday (new typo or renamed place?)"
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
      # of December until next year's are read.
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
stale data, a failing fetch, a schedule running out, fewer places, more warnings, a vanished
source and healthy data. Run the same locally with `sh docs/monitoring-check.sh` (needs
promtool and python3).

## Grafana without Prometheus

Add the [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/) data
source, query `status.json` (type JSON, URL above) and alert when
`sources.nemencine.generatedAt`, `sources.nemezio.generatedAt`, `sources.kauno.generatedAt`,
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
`sources.salcininkai.generatedAt` or `sources.kedainiai.generatedAt` is older than 30 hours (or
missing).

# Monitoring the data

The daily **Schedule data** job reads the providers' files. When a provider changes a file's
format, moves it or introduces something the parser doesn't understand, the build of that
source fails **and yesterday's data stays published**, so nothing breaks for users right away.
GitHub emails the repository owner about the failed run, but the reliable signal is the data
itself: it stops getting newer.

Users see it too: when the data of the company behind their schedule hasn't been rebuilt for 7
days (`providers[].generatedAt`, or Kauno švara's `generatedAt`), the app shows a warning with a
link to the company's official schedule (`app/src/lib/freshness.ts`).

There are six sources, each built on its own:

| `source` | Company | Published in |
|---|---|---|
| `nemencine` | UAB „Nemenčinės komunalininkas“, 12 elderships of Vilniaus r. | `schedule.json` (rows and places without a `provider` field) |
| `nemezio` | UAB „Nemėžio komunalininkas“, the other 11 elderships of Vilniaus r. | `schedule.json` (`provider: "nemezio"`) |
| `kauno` | UAB „Kauno švara“, Kauno r. | `kauno-r/` |
| `mazeikiai` | UAB „Telšių regiono atliekų tvarkymo centras“, Mažeikių r. | `mazeikiu-r/` |
| `klaipedos` | VšĮ „Gargždų švara“, Klaipėdos r. | `klaipedos-r/` |
| `jurbarkas` | UAB „Tauragės regiono atliekų tvarkymo centras“, Jurbarko r. | `jurbarko-r/` |

The two Vilniaus r. companies share one `schedule.json`, so the app needs one download. When
one of them fails, its part of yesterday's file is kept (its `providers[].generatedAt` stays
old) and the run gets a warning annotation; the other part is still updated. If a company has
no published part to keep, the file is published without it.

The job therefore publishes the state of the data with every run:

- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/metrics.txt` (Prometheus format)
- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/status.json` (the same as JSON)

| Metric | Meaning |
|---|---|
| `siuksliaveze_data_generated_timestamp_seconds{source}` | when the published data of `nemencine` / `nemezio` / `kauno` / `mazeikiai` / `klaipedos` / `jurbarkas` was built |
| `siuksliaveze_data_areas{source,kind}` | schedules per waste type |
| `siuksliaveze_data_places{source}` | settlements (`nemencine`, `nemezio`; for `mazeikiai`, `klaipedos` and `jurbarkas` those with a schedule) or addresses (`kauno`) covered |
| `siuksliaveze_data_last_date_timestamp_seconds{source,kind}` | the last pickup date in the published schedules (not for `kauno`, whose dates are calculated ahead) |
| `siuksliaveze_data_warnings{source}` | warnings of the last build, e.g. rows not linked to a settlement: new typos show up here |
| `siuksliaveze_status_checked_timestamp_seconds` | when the daily job last wrote this file |

If a source fails, its `generated` time stays old while `checked` keeps moving. If the job
doesn't run at all, both stay old.

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
      # Mažeikių r., Klaipėdos r. and Jurbarko r. get one file per year. If next year's isn't
      # posted, or the job no longer recognises it, the build stays green while the reminders
      # stop after the last date. Only these sources: the quarterly files of the Vilniaus r.
      # companies come close to their last date every quarter. Klaipėdos r. collects glass four
      # or five times a year and green waste from April to November, and Jurbarko r. glass four
      # times a year (last on 3 December 2026) and green waste last in mid-December, before
      # next year's files are usually posted: so only their mixed waste and packaging.
      - alert: ScheduleDataRunsOut
        expr: |-
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source="mazeikiai"}[30m]) - time() < 7 * 86400
            or
          last_over_time(siuksliaveze_data_last_date_timestamp_seconds{source=~"klaipedos|jurbarkas",kind=~"household|packaging"}[30m]) - time() < 7 * 86400
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
`sources.mazeikiai.generatedAt`, `sources.klaipedos.generatedAt` or
`sources.jurbarkas.generatedAt` is older than 30 hours.

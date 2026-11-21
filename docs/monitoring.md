# Monitoring the data

The daily **Schedule data** job reads the providers' files. When a provider changes a file's
format, moves it or introduces something the parser doesn't understand, the build of that
source fails **and yesterday's data stays published**, so nothing breaks for users right away.
GitHub emails the repository owner about the failed run, but the reliable signal is the data
itself: it stops getting newer.

Users see it too: when the data of the company behind their schedule hasn't been rebuilt for 7
days (`providers[].generatedAt`, or Kauno švara's `generatedAt`), the app shows a warning with a
link to the company's official schedule (`app/src/lib/freshness.ts`).

There are four sources, each built on its own:

| `source` | Company | Published in |
|---|---|---|
| `nemencine` | UAB „Nemenčinės komunalininkas“, 12 elderships of Vilniaus r. | `schedule.json` (rows and places without a `provider` field) |
| `nemezio` | UAB „Nemėžio komunalininkas“, the other 11 elderships of Vilniaus r. | `schedule.json` (`provider: "nemezio"`) |
| `kauno` | UAB „Kauno švara“, Kauno r. | `kauno-r/` |
| `mazeikiai` | UAB „Telšių regiono atliekų tvarkymo centras“, Mažeikių r. | `mazeikiu-r/` |

The two Vilniaus r. companies share one `schedule.json`, so the app needs one download. When
one of them fails, its part of yesterday's file is kept (its `providers[].generatedAt` stays
old) and the run gets a warning annotation; the other part is still updated. If a company has
no published part to keep, the file is published without it.

The job therefore publishes the state of the data with every run:

- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/metrics.txt` (Prometheus format)
- `https://aurimasnav.github.io/atlieku-surinkimo-grafikas/status.json` (the same as JSON)

| Metric | Meaning |
|---|---|
| `siuksliaveze_data_generated_timestamp_seconds{source}` | when the published data of `nemencine` / `nemezio` / `kauno` / `mazeikiai` was built |
| `siuksliaveze_data_areas{source,kind}` | schedules per waste type |
| `siuksliaveze_data_places{source}` | settlements (`nemencine`, `nemezio`; for `mazeikiai` those with a schedule) or addresses (`kauno`) covered |
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

```yaml
groups:
  - name: siuksliaveze-data
    rules:
      - alert: ScheduleDataStale
        # The job runs daily at 04:17 UTC; 30 hours means one run was missed or failed.
        expr: time() - siuksliaveze_data_generated_timestamp_seconds > 30 * 3600
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "Schedule data of {{ $labels.source }} is {{ $value | humanizeDuration }} old"
          description: "The daily build of this source fails or doesn't run. See the Schedule data workflow on GitHub."
      - alert: ScheduleDataShrank
        expr: siuksliaveze_data_places < 0.9 * (siuksliaveze_data_places offset 1d)
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }} covers 10% fewer places than yesterday"
      - alert: ScheduleDataMoreWarnings
        expr: siuksliaveze_data_warnings > (siuksliaveze_data_warnings offset 1d)
        labels: { severity: info }
        annotations:
          summary: "{{ $labels.source }}: more build warnings than yesterday (new typo or renamed place?)"
      # Mažeikių r. gets one file per year and waste type. If next year's isn't posted, or the
      # job no longer recognises it, the build stays green while the reminders stop after the
      # last date. Only this source: the quarterly files of the Vilniaus r. companies come
      # close to their last date every quarter.
      - alert: ScheduleDataRunsOut
        expr: siuksliaveze_data_last_date_timestamp_seconds{source="mazeikiai"} - time() < 7 * 86400
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
          group by (source) (siuksliaveze_data_generated_timestamp_seconds{job="siuksliaveze-data"})
            and on ()
          (up{job="siuksliaveze-data"} == 1)
        for: 30m
        labels: { severity: warning }
        annotations:
          summary: "{{ $labels.source }} is missing from metrics.txt"
      - alert: ScheduleDataNotScraped
        expr: up{job="siuksliaveze-data"} == 0
        for: 2h
        labels: { severity: warning }
        annotations:
          summary: "metrics.txt can't be fetched from GitHub Pages"
```

## Grafana without Prometheus

Add the [Infinity](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/) data
source, query `status.json` (type JSON, URL above) and alert when
`sources.nemencine.generatedAt`, `sources.nemezio.generatedAt`, `sources.kauno.generatedAt` or
`sources.mazeikiai.generatedAt` is older than 30 hours.

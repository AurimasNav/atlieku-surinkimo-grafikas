# Atliekų grafikas

Android app that reminds you when household, packaging and glass waste is
collected at your address in Vilnius district, based on the schedules published by
[UAB "Nemenčinės komunalininkas"](https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/).

Available in Lithuanian, English, Russian and Polish.

> Work in progress. "Atliekų grafikas" is a working name. The code also supports iOS, but it
> isn't published on the App Store yet (Apple charges $99/year).

## How it works

- A daily GitHub Action downloads the official schedule files (Excel and PDF), converts them
  to `schedule.json`, validates the result and publishes it to GitHub Pages.
- The app downloads that file, you pick your area once, and your phone schedules the reminders
  itself as local notifications. There is no backend server and no account.
- Nothing about you leaves your phone. See the [privacy policy](PRIVACY.md).

| Folder | Contents |
|---|---|
| [`app/`](app) | Expo / React Native app (TypeScript, Expo Router, i18next) |
| [`pipeline/`](pipeline) | Python scraper and parsers that produce `schedule.json` |
| [`site/`](site) | Static GitHub Pages site (data, privacy policy) |
| [`docs/`](docs) | [Release process](docs/releasing.md), app store privacy answers |

## AI-assisted development

This project is developed with the help of AI coding assistants. Code, data processing and
documentation are written with AI assistance and reviewed and tested by the maintainer before
release. This note covers the whole project, so individual commits and pull requests don't
repeat it.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup,
translations and how to fix the parser when the schedule format changes.

## License

The source code is licensed under the [Apache License 2.0](LICENSE). You may use, modify
and redistribute it, including commercially.

The project name, logo and app icon are **not** covered by that license. If you publish
your own build, rename and rebrand it. See [TRADEMARKS.md](TRADEMARKS.md).

## Disclaimer

This is an unofficial project, not affiliated with or endorsed by UAB "Nemenčinės
komunalininkas". The schedule data belongs to its publisher. Dates are converted
automatically and may contain mistakes; always check the official schedule if in doubt.

The app and its source code are provided free of charge, **"as is", without warranty of any
kind**, and the authors are not liable for missed or wrong reminders or any consequences of
relying on them (see Sections 7 and 8 of the [license](LICENSE)).

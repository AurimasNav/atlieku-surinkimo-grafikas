# Šiukšliavežė

Android app that reminds you when waste is collected at your address, based on the
schedules the waste companies publish. It covers 33 municipalities:

- **Vilnius district**: mixed waste, packaging and glass, from the schedule files of
  [UAB "Nemenčinės komunalininkas"](https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/)
  and [UAB "Nemėžio komunalininkas"](https://www.nkom.lt/kita.html), each serving its own
  elderships.
- **Kaunas and Kaišiadorys districts**: mixed waste, and food and green waste in Kaunas
  district, from the open-data file of [UAB "Kauno švara"](https://grafikai.svara.lt/). Glass
  and packaging there are collected by UAB "Ekonovus", which doesn't publish its schedules as
  data; the app links to [its schedules](https://www.ekonovus.lt/aptarnavimo-grafikai/).
- **Mažeikiai, Telšiai and Plungė districts and Rietavas municipality**: mixed waste, packaging
  and glass, and food waste in Mažeikiai, Plungė and a few villages, from the spreadsheets of
  the regional waste centre,
  [UAB "Telšių regiono atliekų tvarkymo centras"](https://tratc.lt/atlieku-surinkimo-grafikai/).
  In Mažeikiai district the waste is collected by UAB "Ecoservice" and UAB "Virginijus ir Ko".
- **Klaipėda district**: mixed waste, packaging, glass and green waste, from the spreadsheet of
  the municipality's waste administrator,
  [VšĮ "Gargždų švara"](https://www.gargzdusvara.eu/komunaliniu-atlieku-tvarkymo-grafikai/).
  The waste is collected by UAB "Ekonovus".
- **Jurbarkas, Tauragė and Šilalė districts and Pagėgiai municipality**: mixed waste, packaging
  and glass, green waste in some towns and villages, and food waste in and around Tauragė, from
  the PDFs of the regional waste centre,
  [UAB "Tauragės regiono atliekų tvarkymo centras"](https://www.uabtratc.lt/atlieku-surinkimo-grafikai/).
  Mixed and green waste are collected by UAB "Ecoservice", packaging and glass by UAB "Jurbarko
  komunalininkas" in Jurbarkas district and UAB "Dunokai" in Tauragė and Šilalė districts.
- **Šiauliai, Akmenė, Joniškis, Kelmė, Pakruojis and Radviliškis districts**: mixed waste,
  packaging and glass, green waste in some places and food waste in Joniškis and Žagarė, from the
  PDFs of the regional waste centre,
  [UAB "Šiaulių regiono atliekų tvarkymo centras"](https://www.sratc.lt/kalendoriaus-grafikai/).
  The files of Šiauliai and Pakruojis districts name the collectors, UAB "Kuršėnų komunalinis
  ūkis" and UAB "Pakruojo komunalinis ūkis". In Radviliškis district mixed waste is collected by
  UAB "Svarinta" and packaging and glass by UAB "Ecoservice".
- **Alytus, Prienai, Lazdijai and Varėna districts and Druskininkai and Birštonas
  municipalities**: mixed waste, packaging and glass, and food waste in towns and some villages,
  for private houses, from the PDFs of the regional waste centre,
  [UAB "Alytaus regiono atliekų tvarkymo centras"](https://www.aratc.lt/atlieku-surinkimo-grafikai/),
  which publishes the schedules of every company that empties the containers.
- **Biržai, Pasvalys and Rokiškis districts, and packaging and glass in Panevėžys district**:
  mixed waste, packaging and glass, and food waste in parts of Biržai, Pasvalys and Rokiškis and a
  few villages, for private houses, from the spreadsheets of the regional waste centre,
  [UAB "Panevėžio regiono atliekų tvarkymo centras"](https://www.pratc.lt/atlieku-isvezimas-atlieku-isvezimas/).
  Panevėžys district publishes its mixed waste schedule as a document of rules that the app
  doesn't read, so only its packaging and glass are in the app.
- **Marijampolė, Kalvarija and Kazlų Rūda municipalities and Vilkaviškis and Šakiai
  districts**: mixed waste, packaging and glass, and food waste in the towns and a few villages,
  for private houses, from the PDFs of the regional waste centre,
  [UAB "Marijampolės apskrities atliekų tvarkymo centras"](https://maatc.lt/atlieku-isvezimo-grafikai/).
  Mixed waste is collected by UAB "Ecoservice", packaging and glass by UAB "Ecoservice" and, in
  Šakiai district, UAB "Ekonovus", which also collects the food waste.

The cities of Vilnius, Kaunas, Klaipėda, Šiauliai, Panevėžys and Alytus aren't covered.

Available in Lithuanian, English, Russian and Polish.

> Work in progress. The code also supports iOS, but the app isn't published on the App Store
> yet (Apple charges $99/year).

## How it works

- A daily GitHub Action downloads the official schedule files (Excel and PDF), converts them
  to `schedule.json`, validates the result and publishes it to GitHub Pages.
- The same job matches every schedule row to official settlements and streets from the
  Lithuanian Address Register, so users pick their place once and get all three schedules.
- The app downloads that file, you pick your area once, and your phone schedules the reminders
  itself as local notifications. There is no backend server and no account.
- Nothing about you leaves your phone. See the [privacy policy](PRIVACY.md).

| Folder | Contents |
|---|---|
| [`app/`](app) | Expo / React Native app (TypeScript, Expo Router, i18next) |
| [`pipeline/`](pipeline) | Python scraper and parsers that produce `schedule.json` |
| [`site/`](site) | Static GitHub Pages site (data, privacy policy) |
| [`docs/`](docs) | [Release process](docs/releasing.md), app store privacy answers, [monitoring the data](docs/monitoring.md) |
| [`fastlane/`](fastlane) | Google Play store listing: texts and graphics in every language |

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

This is an unofficial project, not affiliated with or endorsed by any of the companies and
organisations named above, or by the other companies that collect the waste. The
schedule data belongs to its publishers. Settlement and street names
come from the Address Register (Adresų registras) of VĮ Registrų centras, published as open
data at [get.data.gov.lt](https://get.data.gov.lt/datasets/gov/rc/ar/:ns). Dates are converted
automatically and may contain mistakes; always check the official schedule if in doubt.

The app and its source code are provided free of charge, **"as is", without warranty of any
kind**, and the authors are not liable for missed or wrong reminders or any consequences of
relying on them (see Sections 7 and 8 of the [license](LICENSE)).

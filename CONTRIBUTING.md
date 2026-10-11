# Contributing

Thanks for helping! Bug reports, translations, parser fixes and features are all welcome.

By contributing you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE), the same as the rest of the project (Section 5 of the license).
No separate agreement is needed.

## How the project fits together

```
nemenkom.lt (xlsx + pdf)
   │  daily GitHub Action (.github/workflows/schedule-data.yml)
   ▼
pipeline/   Python: scrape → parse → validate → schedule.json
   │  deployed to GitHub Pages together with site/ and PRIVACY.md
   ▼
app/        Expo (React Native) app: downloads schedule.json, schedules local notifications
```

There is no backend server. If the pipeline fails, nothing is deployed and the app keeps using
the last good data.

## Reporting a problem

- **Wrong or missing dates:** open an issue with your area (as shown in the app), the date you
  expected, and a link to the official schedule file.
- **The schedule stopped updating:** check the latest run of the *Schedule data* workflow on the
  Actions tab. The job summary lists parse warnings.
- **Security issues:** please don't open a public issue. Use GitHub's
  *Report a vulnerability* (Security tab).

## Development setup (Windows, macOS or Linux)

### Pipeline (Python)

Requires [uv](https://docs.astral.sh/uv/).

```sh
cd pipeline
uv sync
uv run pytest                                            # tests run against saved real files
uv run python -m schedule_pipeline --out ../site/schedule.json   # build from the live website
uv run ruff check . && uv run ruff format .
```

**Location matching** (`locations.py`) links each Address Register settlement and street to
its row in every schedule. The job summary on the Actions tab shows how many places resolve
to a single row, need a street, need the user to choose, or aren't in a schedule, and lists
rows that matched nothing. Tests in `tests/test_locations.py` pin hand-checked cases; add one
when you fix a mismatch.

**When the publisher changes the file format** (this will happen):

1. Save the new file to `pipeline/tests/fixtures/`.
2. Add a failing test that shows the problem.
3. Fix the parser. Keep it strict: an unrecognised cell should raise an error rather than be
   skipped silently, so mistakes never reach users.

### App (Expo)

Requires Node.js LTS. To run on Android, install Android Studio and create an emulator. The
app is only released for Android, but keep it working on iOS too: you can test on an iPhone
with [Expo Go](https://expo.dev/go) for free, no Apple account needed.

```sh
cd app
npm install
npm start          # press "a" for Android, or scan the QR code with Expo Go
npm run check      # translations, types, lint and tests: run before opening a PR
```

To build and run the real app (not Expo Go) on an emulator, you also need JDK 17:

```sh
npx expo run:android --variant release --device <emulator name>
```

**Windows notes:**

- If the build fails with `ninja: error: manifest 'build.ninja' still dirty after 100 tries`,
  the build is hitting Windows' 260-character path limit. The `ninja.exe` bundled with the
  Android SDK's CMake (`%LOCALAPPDATA%\Android\Sdk\cmake\3.22.1\bin`) is too old to use long
  paths. Make sure long paths are enabled in Windows, then replace that `ninja.exe` with the
  latest one from <https://github.com/ninja-build/ninja/releases> (keep a backup). Mapping the
  folder to a short drive letter with `subst` does **not** help, because Gradle resolves it
  back to the full path.
- To build faster for an emulator only, set `ORG_GRADLE_PROJECT_reactNativeArchitectures=x86_64`
  before building.
- `.bat` tools such as `sdkmanager` split arguments on `;`, so
  `sdkmanager "platforms;android-36"` fails from PowerShell. Use the newer `android sdk install
  platforms/android-36` instead.

To try pipeline changes in the app before they're published, write the output to
`.local-site/schedule.json`, serve that folder (`python -m http.server 8765` inside it) and
create `app/.env.local` with `EXPO_PUBLIC_SITE_URL=http://10.0.2.2:8765` (the emulator's
address for your PC). Both are gitignored. Restart Metro after changing `.env.local`.

The app reads the data from GitHub Pages. To use your own copy (for example a fork, or a
locally built `schedule.json`), set `EXPO_PUBLIC_SITE_URL` to the folder that contains it.

`app/AGENTS.md` lists Expo-specific conventions: always add packages with
`npx expo install`, and never edit the generated `ios/` or `android/` folders.

## Translations

The app supports English, Lithuanian, Russian and Polish. Strings live in
`app/src/i18n/locales/*.json`.

- **`en.json` is the source.** Add or change a string there first, then update the same key in
  every other language in the same pull request.
- If you don't speak a language, copy the English text and mention it in the PR so a speaker
  can translate it.
- Plurals use i18next suffixes. Each language needs its own forms: English `_one`, `_other`;
  Lithuanian, Russian and Polish `_one`, `_few`, `_many`, `_other`.
- `npm run i18n:check` (also run in CI) fails on missing or extra keys, missing plural forms,
  `{{placeholders}}` that differ from English, and **stale translations**.

**Stale translations.** `app/src/i18n/translations.lock.json` records which version of each
English string every translation was made from. If you edit an English string, CI fails for
that key in every other language until the translations are updated and accepted:

```sh
# 1. edit en.json, 2. update lt/ru/pl, 3. record them as up to date:
npm run i18n:accept -- lt ru pl                          # every key in these languages
npm run i18n:accept -- ru --key notifications.body       # or only specific keys
```

Commit the lock file together with the translations. Only accept a language when its text
really matches the new English. If you can't translate a language, leave it stale and say so
in the PR so someone else can finish it before merging.

Place names, area names and notes come from the official schedule. They are shown in
Lithuanian, as published, and are not translated.

## Pull requests

You're welcome to use AI tools when contributing; you are responsible for understanding,
testing and standing behind what you submit. The project-wide disclosure in the README
covers AI assistance, so there's no need for AI attribution lines in commits or PRs.

- Keep each PR focused on one change. Describe what changed and how you tested it.
- CI must pass: `npm run check` for the app, `pytest` and `ruff` for the pipeline.
- For UI changes, add before/after screenshots.
- **Privacy:** the app sends no user data anywhere. A PR that adds analytics, crash
  reporting, push notifications or any other network service must also update
  [PRIVACY.md](PRIVACY.md) and [docs/store-privacy.md](docs/store-privacy.md), and will be
  discussed first. Please open an issue before starting that kind of work.

## Releases

Merging to `main` sends app changes to testers automatically; publishing to everyone is a
manual step. See [docs/releasing.md](docs/releasing.md).

## Forks

Forks are welcome under the Apache License. If you publish your own build, use a different
name, icon and app identifiers; see [TRADEMARKS.md](TRADEMARKS.md).

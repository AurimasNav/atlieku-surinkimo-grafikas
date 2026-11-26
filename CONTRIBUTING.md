# Contributing

Thanks for helping! Bug reports, translations, parser fixes and features are all welcome.

By contributing you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE), the same as the rest of the project (Section 5 of the license).
No separate agreement is needed.

## How the project fits together

```
nemenkom.lt (xlsx + pdf), nkom.lt (pdf)   Vilniaus r.: one schedule.json
grafikai.svara.lt (open-data xlsx)        Kauno r., Kaišiadorių r.: site/kauno-r/
tratc.lt (xlsx)                           Mažeikių r., Telšių r., Plungės r., Rietavo sav.:
                                          site/mazeikiu-r/
gargzdusvara.eu (xlsx)                    Klaipėdos r.: site/klaipedos-r/
uabtratc.lt (pdf)                         Jurbarko r., Tauragės r., Šilalės r., Pagėgių sav.:
                                          site/jurbarko-r/
sratc.lt (pdf)                            Šiaulių r., Akmenės r., Joniškio r., Kelmės r.,
                                          Pakruojo r., Radviliškio r.: site/sratc/
aratc.lt (pdf)                            Alytaus r., Prienų r., Lazdijų r., Varėnos r.,
                                          Druskininkai, Birštonas: site/alytaus-ratc/
pratc.lt (xlsx, doc)                      Pasvalio r., Rokiškio r., Biržų r., Panevėžio r.:
                                          site/panevezio-ratc/ (Panevėžio r.'s mixed waste
                                          with a transcription of its notes in pipeline/data)
maatc.lt (pdf)                            Marijampolės sav., Vilkaviškio r., Kalvarijos sav.,
                                          Kazlų Rūdos sav., Šakių r.: site/maatc/
rkp.lt (pdf)                              Raseinių r.: site/raseiniu-r/
jonavospaslaugos.lt (pdf)                 Jonavos r.: site/jonavos-r/
kretkom.lt (pdf)                          Kretingos r.: site/kretingos-r/
silute.lt (pdf)                           Šilutės r.: site/silutes-r/ (from a copy in
                                          pipeline/data when the site refuses the runners)
ecoservice.lt (pdf)                       Trakų r., Šalčininkų r.: site/ecoservice/
kedainiai.lt (docx, pdf)                  Kėdainių r.: site/kedainiu-r/ (from a copy in
                                          pipeline/data when the site refuses the runners)
moletusvara.lt (pdf)                      Molėtų r.: site/moletu-r/
skuodas.lt (xls + xlsx)                   Skuodo r.: site/skuodo-r/
ukmerge.lt (pdf)                          Ukmergės r.: site/ukmerges-r/ (from a copy in
                                          pipeline/data when the site refuses the runners)
anykom.lt (pdf)                           Anykščių r.: site/anyksciu-r/
utenoskom.lt (pdf)                        Utenos r.: site/utenos-r/
kompata.lt (pdf)                          Ignalinos r.: site/ignalinos-r/
eku.lt (html)                             Elektrėnų sav.: site/elektrenu-sav/
sirvintos.lt (pdf)                        Širvintų r.: site/sirvintu-r/ (from a copy in
                                          pipeline/data when the site refuses the runners)
kupkom.lt (html + pdf)                    Kupiškio r.: site/kupiskio-r/
svencionys.lt (pdf)                       Švenčionių r.: site/svencioniu-r/ (from a copy in
                                          pipeline/data when the site refuses the runners)
zarasai.lt (pdf; mixed waste a scan,      Zarasų r.: site/zarasu-r/ (from a copy in
  transcribed in pipeline/data)           pipeline/data when the site refuses the runners)
   │  daily GitHub Action (.github/workflows/schedule-data.yml)
   ▼
pipeline/   Python: scrape → parse → validate → schedule.json
   │  deployed to GitHub Pages together with site/ and PRIVACY.md
   ▼
app/        Expo (React Native) app: downloads schedule.json, schedules local notifications
```

There is no backend server. If the pipeline fails, nothing is deployed and the app keeps using
the last good data. If one company's source fails, its part of the data published the day
before is kept and the others are still updated (docs/monitoring.md).

## Reporting a problem

The app's "Help & feedback" buttons open the issue forms in `.github/ISSUE_TEMPLATE/`, in the
app's language, with fields prefilled by `app/src/lib/feedback.ts`. GitHub can't translate a
form, so there is one per language (`lt-bug_report.yml`, `en-bug_report.yml`, …). They are
**generated**: edit `app/scripts/issue-forms.mjs` (all languages side by side), then run
`npm run issue-forms` in `app/` and commit the result. CI fails if the two differ. **If you rename
a form or a field `id`, update `feedback.ts` too**, or the prefill silently stops working.

- **Wrong or missing dates:** open an issue with your area (as shown in the app), the date you
  expected, and a link to the official schedule file.
- **The schedule stopped updating:** check the latest run of the *Schedule data* workflow on the
  Actions tab. The job summary lists parse warnings, and
  <https://aurimasnav.github.io/atlieku-surinkimo-grafikas/warnings.html> those of every source.
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

**Address Register snapshot and site copies.** get.data.gov.lt and registrucentras.lt block
requests from cloud servers, including GitHub Actions, so the daily job falls back to the
snapshot in `pipeline/data/`. silute.lt, kedainiai.lt, ukmerge.lt, sirvintos.lt, svencionys.lt
and zarasai.lt refuse GitHub's runners too, so the job reads copies of their pages and schedule
files in `pipeline/data/schedules-silutes-r/`, `schedules-kedainiu-r/`, `schedules-ukmerges-r/`,
`schedules-sirvintu-r/`, `schedules-svencioniu-r/` and `schedules-zarasu-r/` (its build warning
says how old they are).

Both are refreshed automatically from the maintainer's cluster in Lithuania
([k8s-at-home](https://github.com/AurimasNav/k8s-at-home), `gitops/siuksliaveze-snapshot`): a
CronJob takes the copies daily at 03:00 UTC, another the register snapshots on the 1st of each
month. Each opens a PR from a bot branch (`data/site-copies`, `data/address-register`) when
something changed and merges it once `check` and `build` pass, so a new schedule file is
published the same morning. A copy whose files didn't change is left as it is, its `takenAt`
too, even if the page's markup did, so most days there is no PR. Google API keys in the saved
pages (a site theme's Maps key) are replaced by `AIza_REDACTED`, and a test fails if a key or
token of a known format is anywhere in `pipeline/data/` or the test fixtures (`test_secrets.py`),
as these files are committed unattended. If a job fails, its PR stays
open and the job fails in the cluster (`KubeJobFailed`). Only then refresh by hand from a
computer in Lithuania and open a PR:

```sh
cd pipeline
uv run python -m schedule_pipeline.snapshot --copies    # the site copies
uv run python -m schedule_pipeline.snapshot --register  # the Address Register snapshots
uv run python -m schedule_pipeline.snapshot             # both
```

The job summary says which source was used and asks for a refresh when the register snapshot
is over 60 days old (two missed monthly runs). It asks for none for a site copy: an unchanged
copy keeps its date, so its age is how long the site's files have stayed the same.

**Location matching** (`locations.py`) links each Address Register settlement and street to
its row in every schedule. The job summary on the Actions tab shows how many places resolve
to a single row, need a street, need the user to choose, or aren't in a schedule, and lists
rows that matched nothing. Tests in `tests/test_locations.py` pin hand-checked cases; add one
when you fix a mismatch.

**Build warnings and `pipeline/known-warnings.json`.** Every build lists what it couldn't read
cleanly (a place that isn't a settlement, a text kept without exact dates, a site copy used).
The ones someone has checked are listed per source in `pipeline/known-warnings.json`, with
row, page and date numbers left out (`#`), so a moved row is still known; a place's own numbers
stay, and a site copy used is never new. A warning that file doesn't list is new: the
live-build check of a pipeline PR lists it in its job summary and fails (unless the published
data already has it as new), and after a merge the `ScheduleDataNewWarnings` alert fires
until it is fixed or acknowledged
([docs/monitoring.md](docs/monitoring.md#build-warnings)). If it is harmless (and whenever you
add a provider, or change what a build warns about), take the check's `schedule-data-<PR>`
artifact and acknowledge the warnings in the same PR:

```sh
cd pipeline
uv run python -m schedule_pipeline.status --site <the artifact, unzipped> --write-known
```

It rewrites the file from the site's warnings, dropping the ones the builds no longer give;
review the diff, it is what you are acknowledging.

**When the publisher changes the file format** (this will happen):

1. Save the new file to `pipeline/tests/fixtures/`.
2. Add a failing test that shows the problem.
3. Fix the parser. Keep it strict: an unrecognised cell should raise an error rather than be
   skipped silently, so mistakes never reach users.

**When Zarasų r. publishes a new mixed waste scan.** Its mixed waste schedule is a scanned
image of rules ("2-ą ir paskutinį mėnesio pirmadienį – Zarasų sen. Šaltupės g. …"), so it was
transcribed by hand into `pipeline/data/rules-zarasu-r.json`, with the scan's address and
SHA-256. When the page links a scan with another hash (the daily refresh of the site copies
takes it into `pipeline/data/schedules-zarasu-r/`, as zarasai.lt refuses GitHub's runners), the
daily build fails with "the published scan changed (new hash …); re-transcribe
pipeline/data/rules-zarasu-r.json", the site keeps yesterday's Zarasų r. data and
`ScheduleDataStale` fires the next day (docs/monitoring.md). To transcribe it again:

1. Take the scan from the copy, `pipeline/data/schedules-zarasu-r/` (or download the one the
   "Komunalinės atliekos" row of
   <https://www.zarasai.lt/veiklos-sritys/aplinkos-apsauga/atlieku-tvarkymas/269> links) and
   check that its SHA-256 (`sha256sum misriu.pdf`, or `Get-FileHash` in PowerShell) is the hash
   in the error.
2. Its pages are images: open it in a PDF viewer, zoomed in. In the JSON, set `url`, `sha256`
   (lower case), the date it was approved (above the title) and `transcribed`, and write one
   entry in `rules` per paragraph, in the scan's order: `rule` is its words as printed ("1-ą ir
   3-ą mėnesio antradienį", "PIRMAS MĖN. PIRMADIENIS"), `weekday` and `weeks` what they mean
   (-1 for "paskutinį", the last), and `places` the places after each eldership printed in bold,
   split at commas, semicolons and "ir" between places, house numbers with the street or village
   before them ("Aušros g. 7, 8, 10, 10A"). Keep the spellings as printed; the build reads them.
   Check every line against the image again, and write down in the PR anything you can't read
   instead of guessing.
3. `uv run python -m schedule_pipeline.zarasai --out ../site/zarasu-r` builds the folder. Its
   warnings list the places the Address Register doesn't have: look each one up in the scan
   again (a misread letter, or the publisher's spelling: then an alias in `zarasai.PROVIDER`).
   The build is strict: words of a rule it doesn't understand, a weekday or weeks that don't
   match them, or a place of no known kind fail it.
4. `uv run pytest tests/test_zarasai.py` pins places and counts of the old scan: update them
   to what the new one says, then open a PR. The day it is merged, the site gets the new rules.

**Panevėžio r.'s mixed waste: re-transcribing its notes.** Panevėžio RATC publishes it as a
Word document (.doc) of routes, some with notes in free words under them ("Vietoje 2026m.
sausio 1d. ... aptarnausime sausio 2d."). Routes without notes are read from the file; those
with notes, or marks in their days ("*26", "2-3"), from their transcription in
`pipeline/data/schedule-panevezio-r-mixed.json` (`pratc_word.py`), which is used only while the
route's text is exactly the same. When the centre changes such a route, or posts next year's
document, the daily build keeps yesterday's mixed waste rows of Panevėžio r. and warns ("... can't
be read (... notes that schedule-panevezio-r-mixed.json doesn't have: route 13 (...);
re-transcribe it ...)"), and the live-build check of every pipeline PR fails. To transcribe:

```sh
cd pipeline
uv run python -m schedule_pipeline.pratc_word   # reads the page's document, updates the file
```

It keeps the entries still used and adds a draft of each missing one: the route's `text`, its
places as the name of one row and its days as that row's `dates` (both days of a range). Then,
from the notes at the end of each new entry's `text`, correct its `rows`: a row for each group
of places the notes treat differently (named as a list of places, in the genitive like the
route's, or "Šeškų k. (Panevėžio aplinkl. 201)" for one house), each with all its dates; a
pickup a note moves into next year belongs to the row too. Check that a new text after the table
(`texts`) changes no date. Save the document as `pipeline/tests/fixtures/pratc/panevezio-r-mka.doc`,
update `test_pratc.py` (`test_the_transcription_agrees_with_the_days_of_its_routes` says how the
rows differ from the days) and open a PR.

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
- To test "Use my current location", feed a position to the emulator while the app is asking
  for it: `app/scripts/emulator-location.ps1` sends the PC's own Windows location (Wi-Fi based,
  roughly ±50–200 m), or `-Latitude 54.7692 -Longitude 25.1840` for a fixed address. You can
  also set a position in the emulator's Extended controls (⋯ → Location).
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

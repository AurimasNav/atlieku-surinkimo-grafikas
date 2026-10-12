# Releasing

The app is released on **Android (Google Play) only** for now. The code is cross-platform;
see [Adding iOS later](#adding-ios-later).

## How a change reaches users

```
feature branch ──PR──▶ main ──▶ Release workflow (GitHub Actions)
  CI: App / check        │        └─ android: EAS Build → Google Play "Internal testing"
  CI: Schedule data      │                                        │ testers only
                         │                                        ▼
                         │        you promote by hand, after testing ──▶ public
                         ▼
                 Schedule data workflow: schedule.json + privacy page → GitHub Pages
```

1. Work on a branch and open a PR against `main`. CI (`App / check`, `Schedule data / build`)
   must pass before merging; `main` can't be pushed to directly.
2. Merging a PR that changes `app/` starts the **Release** workflow. It runs the checks again,
   builds the Android app on EAS and submits it to the **Google Play *Internal testing*
   track**. Only the testers on your list get it, usually within minutes, with no Google review.
3. Test on the testers' phones.
4. **Promote to the public** by hand (below). Changes outside `app/` (pipeline, docs) never
   start a release.

Build numbers increase automatically (`appVersionSource: remote`, `autoIncrement`). The
user-visible version (`expo.version` in `app/app.json`, e.g. `1.0.0`) is changed by hand in a
PR: bump it after a version has been released to the public, before the next release.

## Promoting a tested build to the public

In Google Play Console:

1. *Test and release → Testing → Internal testing* → the release → **Promote release →
   Production**.
2. Choose a **staged rollout** (for example 20%), then *Send for review*. Google reviews it,
   usually within hours to a few days.
3. Watch for crashes or bad reviews, then raise the rollout to 100%. If something is wrong,
   *Halt rollout*: users who haven't updated won't get it.

## Test devices

- **Internal testing track:** up to 100 Google accounts on an email list. Each tester opens
  the opt-in link from Play Console once; after that, test builds arrive as normal Play Store
  updates. Nobody else gets them.
- **Larger groups:** use a *closed testing* track (email lists or Google Groups).
- **New personal developer accounts** must run a *closed test* with at least 12 testers for
  14 days before they can publish to production. Check *Dashboard* in Play Console. If it
  applies, add a closed testing track and send builds there in addition to internal testing.

## One-time setup

Do these once, in order. Steps 1–5 are done on your computer, not in CI.

1. **Accounts.** Expo account (free) and Google Play developer account ($25 once).
2. **Link the project to EAS.** In `app/`: `npx eas-cli@latest login`, then
   `npx eas-cli@latest init`. This adds `extra.eas.projectId` to `app.json`; commit that in a PR.
3. **Create the store app.** Play Console → *Create app*, package
   `io.github.aurimasnav.siuksliaveze` (from the GitHub Pages address `aurimasnav.github.io`;
   it can never change after the first upload). App name **Šiukšliavežė**. Store titles, at most
   30 characters each (*Store presence → Main store listing*, per language):

   | Language | Title |
   |---|---|
   | lt | Šiukšliavežė: atliekų grafikas |
   | en | Šiukšliavežė: waste pickup |
   | ru | Šiukšliavežė: вывоз отходов |
   | pl | Šiukšliavežė: wywóz odpadów |

   The icon and listing should be final before this step; see [store-privacy.md](store-privacy.md).
4. **First build, run locally**, so EAS can create the Android signing key (keystore):
   ```sh
   npx eas-cli@latest build --platform android --profile production
   ```
   EAS keeps the key on its servers; CI reuses it. You can download a backup with
   `npx eas-cli@latest credentials --platform android`.
5. **Submission key, stored on EAS** (so no key files live in GitHub): create a Google service
   account with release permissions in Play Console, then
   `npx eas-cli@latest credentials --platform android` → *Google Service Account* → upload the
   JSON key. Run `npx eas-cli@latest submit --platform android --latest` once to submit the
   build from step 4 and confirm it works.
6. **Connect GitHub.**
   - expo.dev → *Account settings → Access tokens* → create a token. Add it on GitHub:
     *Settings → Secrets and variables → Actions → New repository secret* `EXPO_TOKEN`.
   - Same page, *Variables* tab: add `RELEASE_ENABLED` = `true`. Until this exists, the
     Release workflow is skipped, so merges don't fail before the setup is done.
7. **Testers.** Play Console → *Internal testing → Testers*: create an email list, then send
   the opt-in link to the testers.

## Costs

- Google Play: $25 once.
- EAS: the free plan includes a limited number of builds per month, with lower queue
  priority. Each release uses one Android build. Check <https://expo.dev/pricing>.
- GitHub Actions and GitHub Pages: free for public repositories.

## Adding iOS later

Everything in the app already supports iOS, and developers can test on an iPhone with Expo Go
for free. Publishing needs the Apple Developer Program ($99/year). When that's in place:

1. App Store Connect → *Apps → +*, bundle ID `io.github.aurimasnav.siuksliaveze`. Put the app's
   **Apple ID** (a number) in `app/eas.json` → `submit.production.ios.ascAppId`.
2. Run the first iOS build locally so EAS creates the certificate and provisioning profile:
   `npx eas-cli@latest build --platform ios --profile production`.
3. `npx eas-cli@latest credentials --platform ios` → *App Store Connect API Key* → let EAS
   create one.
4. Add `ios` to the `platform` matrix in `.github/workflows/release.yml`. Merges then build
   both platforms in parallel and send iOS builds to **TestFlight**.
5. App Store Connect → *TestFlight → Internal Testing*: create a group, add up to 100 testers
   and turn on automatic distribution.
6. To go public: in App Store Connect, attach the tested build to a new App Store version,
   choose **phased release**, and submit for review.
7. Fill in the Apple privacy answers in [store-privacy.md](store-privacy.md).

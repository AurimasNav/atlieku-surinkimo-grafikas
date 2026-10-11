# Releasing

## How a change reaches users

```
feature branch ──PR──▶ main ──▶ Release workflow (GitHub Actions)
  CI: App / check        │        ├─ android: EAS Build → Google Play "Internal testing" ─┐
  CI: Schedule data      │        └─ ios:     EAS Build → TestFlight                      │ testers
                         │                                                                ▼ only
                         │                       you promote by hand, after testing ──▶ public
                         ▼
                 Schedule data workflow: schedule.json + privacy page → GitHub Pages
```

1. Work on a branch and open a PR against `main`. CI (`App / check`, `Schedule data / build`)
   must pass before merging; `main` can't be pushed to directly.
2. Merging a PR that changes `app/` starts the **Release** workflow. It runs the checks again,
   then builds Android and iOS **in parallel** on EAS and submits both automatically:
   - **Android → Google Play *Internal testing* track.** Only the testers on your list get it,
     usually within minutes. No Google review.
   - **iOS → TestFlight.** Internal testers (people in your App Store Connect team, up to
     100) get it after Apple's automated processing, usually 10–30 minutes. No App Review.
3. Test on the testers' phones.
4. **Promote to the public** by hand (below). Changes outside `app/` (pipeline, docs) never
   start a release.

Build numbers increase automatically (`appVersionSource: remote`, `autoIncrement`). The
user-visible version (`expo.version` in `app/app.json`, e.g. `1.0.0`) is changed by hand in a
PR: bump it after a version has been released to the public, before the next release.

## Promoting a tested build to the public

**Android (Google Play Console)**
1. *Test and release → Testing → Internal testing* → the release → **Promote release →
   Production**.
2. Choose a **staged rollout** (for example 20%), then *Send for review*. Google reviews it,
   usually within hours to a few days.
3. Watch for crashes or bad reviews, then raise the rollout to 100%. If something is wrong,
   *Halt rollout*: users who haven't updated won't get it.

**iOS (App Store Connect)**
1. *Apps → your app → App Store* tab → create the version (same number as `expo.version`) if
   it doesn't exist yet.
2. Under *Build*, select the TestFlight build you tested, fill in "What's new", and choose
   **Phased release for automatic updates** (rolls out over 7 days and can be paused).
3. *Add for Review* → *Submit*. After Apple approves it, release it manually or automatically.

## Test devices

| | Android | iOS |
|---|---|---|
| Tester channel | Internal testing track | TestFlight internal testing |
| Who | Up to 100 Google accounts on an email list | Up to 100 App Store Connect users |
| How they join | Open the opt-in link from Play Console once | Install the TestFlight app and accept the invite |
| Review before testers get it | None | None for internal testers |
| Larger groups | Closed testing track (email lists or Google Groups) | External TestFlight testers (up to 10,000, needs a short beta review) |

Testers get the test build as a normal store update; nobody else does.

**New Google Play personal developer accounts** must run a *closed test* with at least 12
testers for 14 days before they can publish to production. Check *Dashboard* in Play
Console. If it applies, add a closed testing track and send builds there in addition to
internal testing.

## One-time setup

Do these once, in order. Steps 1–5 are done on your computer, not in CI.

1. **Accounts.** Expo account (free), Apple Developer Program ($99/year), Google Play
   developer account ($25 once).
2. **Link the project to EAS.** In `app/`: `npx eas-cli@latest login`, then
   `npx eas-cli@latest init`. This adds `extra.eas.projectId` to `app.json`; commit that in a PR.
3. **Create the store apps.**
   - App Store Connect → *Apps → +*: bundle ID `com.aurimasnav.atliekugrafikas`.
     Copy the app's **Apple ID** (a number) into `app/eas.json` →
     `submit.production.ios.ascAppId`.
   - Play Console → *Create app*: same name, package `com.aurimasnav.atliekugrafikas`.
   - The name, icon and bundle ID should be final before this step; see
     [store-privacy.md](store-privacy.md).
4. **First build of each platform, run locally** so EAS can create the signing credentials
   (Android keystore, iOS certificate and provisioning profile) interactively:
   ```sh
   npx eas-cli@latest build --platform android --profile production
   npx eas-cli@latest build --platform ios --profile production
   ```
   EAS keeps the credentials on its servers; CI reuses them.
5. **Submission credentials, stored on EAS** (so no key files live in GitHub):
   - Google: create a service account with release permissions in Play Console, then
     `npx eas-cli@latest credentials --platform android` → *Google Service Account* → upload
     the JSON key.
   - Apple: `npx eas-cli@latest credentials --platform ios` → *App Store Connect API Key* →
     let EAS create one, or upload your own.
   - Run `npx eas-cli@latest submit --platform all --latest` once to submit the builds from
     step 4 and confirm that both work.
6. **Connect GitHub.**
   - expo.dev → *Account settings → Access tokens* → create a token. Add it on GitHub:
     *Settings → Secrets and variables → Actions → New repository secret* `EXPO_TOKEN`.
   - Same page, *Variables* tab: add `RELEASE_ENABLED` = `true`. Until this exists, the
     Release workflow is skipped, so merges don't fail before the setup is done.
7. **Testers.**
   - Play Console → *Internal testing → Testers*: create an email list, then send the opt-in
     link to the testers.
   - App Store Connect → *TestFlight → Internal Testing*: create a group, add testers, and
     turn on **automatic distribution** so every new build reaches them without a click.

## Costs

The free EAS plan includes a limited number of builds per month, with iOS builds counting
separately, and lower queue priority. Each release uses one Android and one iOS build, so
merge app changes in batches if you approach the limit. Check the current numbers at
<https://expo.dev/pricing>.

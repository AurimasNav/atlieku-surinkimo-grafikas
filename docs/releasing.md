# Releasing

The app is released on **Android (Google Play) only** for now. The code is cross-platform;
see [Adding iOS later](#adding-ios-later).

## How a change reaches users

```
feature branch ──PR──▶ main ──▶ Release workflow (GitHub Actions)
  CI: App / check        │        └─ android: build + sign → Google Play "Internal testing"
  CI: Schedule data      │                                        │ testers only
                         │                                        ▼
                         │        you promote by hand, after testing ──▶ public
                         ▼
                 Schedule data workflow: schedule.json + privacy page → GitHub Pages
```

1. Work on a branch and open a PR against `main`. CI (`App / check`, `Schedule data / build`)
   must pass before merging; `main` can't be pushed to directly. PRs that change `app/` also
   get **App Android build** (about 20 minutes): the release build without the upload key, so
   native problems show up before the merge. Wait for it too. Its APK (run → *Artifacts*)
   installs on a phone or emulator; uninstall the Google Play copy first, the signatures differ.
2. Merging a PR that changes `app/` starts the **Release** workflow. It runs the checks again,
   builds and signs the Android App Bundle on GitHub Actions (about 20 minutes) and uploads it
   to the **Google Play *Internal testing* track**. Only the testers on your list get it,
   usually within minutes, with no Google review. The bundle is also kept for 30 days as an
   artifact of the workflow run.
3. Test on the testers' phones.
4. **Promote to the public** by hand (below). Changes outside `app/` (pipeline, docs) never
   start a release.

See [Versions](#versions) for how releases are numbered.

## Versions

- **The version people see** (e.g. `0.0.3`, shown in Settings and in bug reports) is
  calculated by [GitVersion](https://gitversion.net) from the git history (`GitVersion.yml`).
  The Release workflow writes it into the build; `expo.version` in `app/app.json` is only what
  local development builds show.
- **Every release is tagged** `v<version>` once it reaches the testers, so the next merge to
  `main` that changes the app is released as the next patch version: `v0.0.1`, `v0.0.2`, ….
  A failed release isn't tagged and is retried with the same number.
- **For a bigger step**, add `+semver: minor` (`0.0.7` → `0.1.0`) or `+semver: major`
  (→ `1.0.0`) on its own line in the PR's squash-merge commit message.
- **Version codes** (Android `versionCode`, which Google Play requires to increase with every
  upload) are the number of commits on `main`, which only grows. Don't rewrite `main`'s
  history once releases exist.

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

## Testing a build without releasing

*Actions → Release → Run workflow*, pick a branch, keep **Dry run** ticked. It runs the
checks, builds and signs the bundle and attaches it to the run, but doesn't upload or tag.

## One-time setup

1. **Create the store app** (done). Play Console → *Create app*, package
   `io.github.aurimasnav.siuksliaveze` (from the GitHub Pages address `aurimasnav.github.io`;
   it can never change after the first upload). App name **Šiukšliavežė**. Store titles, at most
   30 characters each (*Store presence → Main store listing*, per language):

   | Language | Title |
   |---|---|
   | lt | Šiukšliavežė: atliekų grafikas |
   | en | Šiukšliavežė: waste pickup |
   | ru | Šiukšliavežė: вывоз отходов |
   | pl | Šiukšliavežė: wywóz odpadów |

2. **Upload key** (done). A PKCS12 keystore, alias `upload`, made with `keytool` and kept
   outside the repository, with a backup. GitHub has it as the secrets
   `ANDROID_UPLOAD_KEYSTORE_BASE64` (the file, base64) and `ANDROID_UPLOAD_KEYSTORE_PASSWORD`
   (password of the keystore and the key). `app/plugins/with-release-signing.js` signs release
   builds with it. Google Play signs the published app with its own key (Play App Signing), so
   a lost or leaked upload key can be reset: *Test and release → App integrity → App signing →
   Request upload key reset*.
3. **Google Play access for GitHub** (done), a service account:
   1. [Google Cloud](https://console.cloud.google.com/projectcreate): create a project (any
      name), then *IAM & Admin →
      [Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts) → Create
      service account*. It needs no Google Cloud role. Copy its email address.
   2. On the service account: *Keys → Add key → Create new key → JSON*. Keep the file private.
   3. Enable the
      [Google Play Android Developer API](https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com).
   4. Play Console → [Users and permissions](https://play.google.com/console/users-and-permissions)
      → *Invite new users*, paste the email. On *App permissions*, add the app with: View app
      information; Edit and delete draft apps; Release to production, exclude devices, and use
      Play App Signing; Release apps to testing tracks; Manage testing tracks and edit tester
      lists; Manage store presence.
   5. GitHub → *Settings → Secrets and variables → Actions*: new repository secret
      `PLAY_SERVICE_ACCOUNT_JSON` with the contents of the JSON file. Then delete the file.
4. **Testers and the first build** (done, 0.0.1 (28)). Google Play's API can't upload a new
   app's first build, so that one is uploaded by hand:
   1. Run the Release workflow as a dry run (above) and download the bundle from the run's
      *Artifacts*.
   2. Play Console → *Test and release → Testing → Internal testing*. On *Testers*, create an
      email list. Then *Create new release*, keep the Google-generated app signing key, upload
      the `.aab`, *Save and publish*.
   3. Testers open the opt-in link (*Testers → How testers join your test → Copy link*) on
      their phone, signed in with the listed Gmail, accept, and install from Google Play.
5. **Turn releases on** (done): GitHub → *Settings → Secrets and variables → Actions →
   Variables*, add `RELEASE_ENABLED` = `true`. Until it exists, merges don't start the Release
   workflow.

### Troubleshooting

- **"Package not found"**: the app has no build on Google Play yet; upload the first one by
  hand (step 4).
- **"Only releases with status draft may be created on draft app"**: Google Play refuses
  finished releases for an app that has never been published. Add the variable
  `PLAY_RELEASE_STATUS` = `draft`; each upload then waits in *Internal testing* until you click
  *Review release → Start rollout*. Delete the variable once the app is published.
- **"APK specifies a version code that has already been used"**: that commit was already
  uploaded; release a newer commit instead.
- **"The caller does not have permission"**: check the service account's app permissions
  (step 3.4). New permissions can take a few minutes to apply.

## Costs

- Google Play: $25 once.
- GitHub Actions and GitHub Pages: free for public repositories.

## Adding iOS later

Everything in the app already supports iOS, and developers can test on an iPhone with Expo Go
for free. Publishing needs the Apple Developer Program ($99/year). When that's in place:

1. App Store Connect → *Apps → +*, bundle ID `io.github.aurimasnav.siuksliaveze`.
2. Add an `ios` job to `.github/workflows/release.yml`, next to `android`, on a `macos-latest`
   runner (free for public repositories): `npx expo prebuild --platform ios`, then build and
   sign with Xcode. The signing certificate, provisioning profile and an App Store Connect API
   key become GitHub secrets; fastlane (`match`, `pilot`) is the usual tool to sign and upload
   to **TestFlight**. Expo's paid EAS service can do this instead, if that's simpler by then.
3. App Store Connect → *TestFlight → Internal Testing*: create a group, add up to 100 testers
   and turn on automatic distribution.
4. To go public: in App Store Connect, attach the tested build to a new App Store version,
   choose **phased release**, and submit for review.
5. Fill in the Apple privacy answers in [store-privacy.md](store-privacy.md).

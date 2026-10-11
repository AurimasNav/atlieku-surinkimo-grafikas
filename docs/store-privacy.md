# App store privacy answers

What to enter in App Store Connect and Google Play Console. This is based on the app as it is
today: **if you add analytics, crash reporting, push notifications, EAS Update or any other
service that sends data off the device, update these answers and [PRIVACY.md](../PRIVACY.md) in
the same pull request.** The web version of the policy is generated from PRIVACY.md.

Privacy policy URL for both stores:
`https://aurimasnav.github.io/atlieku-surinkimo-grafikas/privacy/`
(published by the `Schedule data` workflow from `site/`).

## Apple App Store Connect

| Question | Answer |
|---|---|
| App Privacy → Do you or your third-party partners collect data from this app? | **No, we do not collect data from this app.** The label shows "Data Not Collected". |
| Privacy Policy URL | the URL above |
| Tracking (App Tracking Transparency) | Not used. `NSPrivacyTracking` is `false`. |
| Privacy manifest | Set in `app/app.json` → `ios.privacyManifests`: no collected data types; `UserDefaults` declared with reason `CA92.1` (app's own settings). Expo packages ship their own manifests. If Apple emails about a missing "required reason" API after an upload, add it there. |
| Export compliance | Uses only standard HTTPS, which is exempt. `ITSAppUsesNonExemptEncryption` is `false` (set via `ios.config.usesNonExemptEncryption`), so Apple won't ask on each build. |
| Third-party content | The app shows public schedule data published by UAB „Nemenčinės komunalininkas“, with attribution and a link to the source. |
| Age rating | Answer "None" to every content question; the result is 4+. |

**Why "Data Not Collected" is correct:** Apple counts data as collected when it is sent off the
device and stored longer than needed to serve the request. The app downloads one public file;
the request carries no user data, and the IP address that reaches GitHub Pages is not stored
by us or linked to the user.

## Google Play Console

**App content → Data safety**

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **No** |
| Result shown on the store | "No data collected", "No data shared with third parties" |

**App content → other declarations**

| Section | Answer |
|---|---|
| Privacy policy | the URL above |
| Ads | No, the app does not contain ads |
| App access | All functionality is available without special access (no login) |
| Target audience | **18 and over** recommended. Including under-13s brings the Families policy requirements, which add work and no benefit for this app. |
| Content rating | Utility / productivity questionnaire; answer "No" to everything → rated for everyone |
| Government apps | **Not** a government app. The store listing must not suggest it is official. Keep the disclaimer below in the description. |
| Account deletion | Not applicable, the app has no accounts |
| Exact alarm permission | Not used. Reminders use inexact scheduling, which is accurate enough for a reminder the evening before. |

## Store listing disclaimer

Put this at the end of the description in both stores (and in the other languages you list):

> Unofficial app made by volunteers, not affiliated with UAB „Nemenčinės komunalininkas“.
> Dates come from the schedules they publish at nemenkom.lt and may contain mistakes; always
> check the official schedule if in doubt. Provided free of charge, without any warranty.

> Neoficiali savanorių sukurta programėlė, nesusijusi su UAB „Nemenčinės komunalininkas“.
> Datos paimtos iš jų skelbiamų grafikų nemenkom.lt ir gali turėti klaidų; kilus abejonių,
> pasitikrinkite oficialų grafiką. Teikiama nemokamai, be jokių garantijų.

## Before the first submission

- [ ] Pick the final app name and replace the Expo placeholder icon and splash
      (`app/assets/`), see [TRADEMARKS.md](../TRADEMARKS.md).
- [ ] Confirm the bundle ID / package (`com.aurimasnav.atliekugrafikas` in `app/app.json`).
      **It can't be changed after the first upload.**
- [ ] GitHub Pages is enabled (Settings → Pages → Source: GitHub Actions) and the privacy URL
      loads.
- [ ] Apple Developer Program ($99/year) and Google Play developer account ($25 once).

# Store listing

The Google Play store listing, one folder per store language, in the layout used by fastlane
`supply` (and read by F-Droid):

```text
metadata/android/<language>/
  title.txt                 app name on the store, at most 30 characters
  short_description.txt     at most 80 characters
  full_description.txt      at most 4000 characters
  images/icon.png           512 × 512, 32-bit PNG
  images/featureGraphic.png 1024 × 500, 24-bit PNG (no transparency)
  images/phoneScreenshots/  2–8 screenshots, 24-bit PNG or JPEG
```

| Folder | Play Console language |
|---|---|
| `lt` | Lithuanian – lt |
| `en-US` | English (United States) – en-US |
| `ru-RU` | Russian – ru-RU |
| `pl-PL` | Polish – pl-PL |

In Play Console, open the app's main store listing (under *Grow users → Store presence*),
paste the texts and upload the images; *Manage translations → Add your own translations* adds
the other languages. Nothing uploads them automatically yet.

## Writing rules

- Keep the disclaimer from [docs/store-privacy.md](../docs/store-privacy.md#store-listing-disclaimer)
  at the end of every full description. The listing must not suggest the app is official.
- Use the same words as the app (`app/src/i18n/locales/`): "Mixed waste", "Packaging",
  "Glass", the menu items users have to find.
- Don't promise what the app doesn't do, and update the texts in the same pull request as a
  feature they describe.
- No emoji or ALL CAPS in the title and no keyword lists: Google Play's metadata policy
  forbids them.

## Graphics

`graphics-src/feature-graphic-<language>.svg` are the sources of the feature graphics. The
headline is the onboarding title of that language (`onboarding.title`); the truck is the app
icon's (`app/assets/icon-src/`). They use the app's font, Manrope (ExtraBold and Bold, in
`app/node_modules/@expo-google-fonts/manrope`), so render them with that font installed or
passed to the renderer, e.g. with resvg. `icon.png` is `app/assets/icon-src/icon.svg` at
512 × 512.

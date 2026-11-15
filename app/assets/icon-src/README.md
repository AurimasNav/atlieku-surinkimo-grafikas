# Icon sources

The app icon (a garbage truck) as SVG. Each file is rendered at 1024 × 1024 to the PNG of the
same name in `../images`; `favicon.png` is `icon.svg` at 48 × 48. Any SVG renderer works
(resvg, Inkscape).

- `icon.svg`: full-bleed store and launcher icon. The stores and launchers round the corners.
- `android-icon-*.svg`: adaptive icon layers. The truck stays inside the central safe zone
  (66% of the canvas), so launchers can crop it to any shape.
- `android-icon-monochrome.svg`: themed icon; Android uses only its alpha channel.
- `splash-icon.svg`: shown on the green splash screen.

The icon is part of the project's branding; see [TRADEMARKS.md](../../../TRADEMARKS.md).

// Frames the raw screenshots from capture.mjs for Google Play: brand background, a caption
// taken from the app's own translations, and the screenshot without its status bar.
// Usage: npm run frame
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { esc, gradient, languages, metadata, rawShots, renderOpaquePng, strings, textWidth } from './shared.mjs';

const captions = (s) => ({
  '1-home': s.onboarding.title,
  '2-search': s.onboarding.featurePlace,
  '3-done': s.onboarding.featureReminder,
  '4-custom': s.custom.setupTitle,
  '5-welcome': s.onboarding.featurePrivate,
});

const W = 1080;
const H = 1920;
const STATUS_BAR = 110; // px cropped from the top of each screenshot
const SHOT_W = 860;
const SHOT_H = Math.round(((H - STATUS_BAR) * SHOT_W) / W);
const SHOT_X = (W - SHOT_W) / 2;
const SHOT_Y = H - SHOT_H - 50;
const CAPTION_MAX = 940;

/**
 * At most two lines: explicit line breaks are kept; a long caption is split where the two lines
 * come out most even. The font shrinks until it fits.
 */
function layout(caption) {
  for (let size = 76; size >= 48; size -= 2) {
    let lines = caption.split('\n');
    if (lines.length === 1 && textWidth(caption, size, -1) > CAPTION_MAX) {
      const words = caption.split(' ');
      let best = null;
      for (let i = 1; i < words.length; i++) {
        const pair = [words.slice(0, i).join(' '), words.slice(i).join(' ')];
        const widest = Math.max(...pair.map((l) => textWidth(l, size, -1)));
        if (!best || widest < best.widest) best = { pair, widest };
      }
      if (best) lines = best.pair;
    }
    if (lines.length <= 2 && lines.every((l) => textWidth(l, size, -1) <= CAPTION_MAX)) return { size, lines };
  }
  throw new Error(`Caption too long: ${caption}`);
}

function frame(png, caption) {
  const { size, lines } = layout(caption);
  const lineHeight = Math.round(size * 1.12);
  const top = (SHOT_Y - lines.length * lineHeight) / 2 + size * 0.8;
  const scale = SHOT_W / W;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<defs>${gradient()}` +
    `<clipPath id="window"><rect x="${SHOT_X}" y="${SHOT_Y}" width="${SHOT_W}" height="${SHOT_H}" rx="44"/></clipPath>` +
    `<filter id="shadow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="18"/></filter></defs>` +
    `<rect width="${W}" height="${H}" fill="url(#bg)"/>` +
    `<rect x="${SHOT_X}" y="${SHOT_Y + 16}" width="${SHOT_W}" height="${SHOT_H}" rx="44" fill="#000" opacity="0.28" filter="url(#shadow)"/>` +
    `<g clip-path="url(#window)"><image x="${SHOT_X}" y="${SHOT_Y - STATUS_BAR * scale}" width="${SHOT_W}" height="${H * scale}" ` +
    `xlink:href="data:image/png;base64,${png.toString('base64')}"/></g>` +
    lines
      .map(
        (l, i) =>
          `<text x="${W / 2}" y="${top + i * lineHeight}" text-anchor="middle" font-family="Manrope" font-weight="800" font-size="${size}" letter-spacing="-1" fill="#FFFFFF">${esc(l)}</text>`,
      )
      .join('') +
    `</svg>`
  );
}

for (const [lang, store] of Object.entries(languages)) {
  const out = join(metadata, store, 'images', 'phoneScreenshots');
  mkdirSync(out, { recursive: true });
  for (const [name, caption] of Object.entries(captions(strings(lang)))) {
    const svg = frame(readFileSync(join(rawShots, lang, `${name}.png`)), caption);
    writeFileSync(join(out, `${name}.png`), renderOpaquePng(svg, W));
    console.log(`${store}/${name}: ${caption.replace('\n', ' ')}`);
  }
}

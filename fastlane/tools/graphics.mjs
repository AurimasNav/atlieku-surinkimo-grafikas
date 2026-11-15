// Renders the 512 x 512 store icon and the 1024 x 500 feature graphic of every language.
// Usage: npm run graphics
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { esc, gradient, languages, metadata, renderOpaquePng, renderPng, repo, strings, textWidth } from './shared.mjs';

const iconSrc = join(repo, 'app', 'assets', 'icon-src');
const sources = join(repo, 'fastlane', 'graphics-src');
mkdirSync(sources, { recursive: true });

// The truck of the adaptive icon foreground: 560 px wide, centred in a 1024 canvas.
const foreground = readFileSync(join(iconSrc, 'android-icon-foreground.svg'), 'utf8');
const truckSvg = foreground.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
const truck = (x, y, width) => {
  const size = (width * 1024) / 560;
  const left = x - (size - width) / 2;
  const top = y - (size - (width * 400) / 600) / 2;
  return `<svg x="${left}" y="${top}" width="${size}" height="${size}" viewBox="0 0 1024 1024">${truckSvg}</svg>`;
};

/** App name, the onboarding title as headline, and the truck on the right. */
function featureGraphic(lines) {
  const W = 1024;
  const H = 500;
  const truckWidth = 350;
  const truckX = W - truckWidth - 60;
  const truckY = (H - (truckWidth * 400) / 600) / 2 + 18;
  // The headline shrinks until its longest line ends well before the truck.
  const room = truckX - 68 - 36;
  const size = Math.min(78, ...lines.map((l) => Math.floor((78 * room) / textWidth(l, 78, -1.5))));
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
    `<defs>${gradient()}</defs>` +
    `<rect width="${W}" height="${H}" fill="url(#bg)"/>` +
    `<circle cx="${truckX + truckWidth / 2}" cy="${H / 2 + 6}" r="210" fill="#FFFFFF" opacity="0.06"/>` +
    `<ellipse cx="${truckX + truckWidth / 2}" cy="${truckY + (truckWidth * 380) / 600}" rx="${truckWidth * 0.46}" ry="${truckWidth * 0.045}" fill="#000" opacity="0.22"/>` +
    truck(truckX, truckY, truckWidth) +
    `<text x="72" y="168" font-family="Manrope" font-weight="700" font-size="38" fill="#C8F169">Šiukšliavežė</text>` +
    lines
      .map(
        (line, i) =>
          `<text x="68" y="${262 + i * Math.round(size * 1.1)}" font-family="Manrope" font-weight="800" font-size="${size}" letter-spacing="-1.5" fill="#FFFFFF">${esc(line)}</text>`,
      )
      .join('') +
    `</svg>`
  );
}

const icon = readFileSync(join(iconSrc, 'icon.svg'), 'utf8');
for (const [lang, store] of Object.entries(languages)) {
  const images = join(metadata, store, 'images');
  mkdirSync(images, { recursive: true });
  const svg = featureGraphic(strings(lang).onboarding.title.split('\n'));
  writeFileSync(join(sources, `feature-graphic-${store}.svg`), svg + '\n');
  writeFileSync(join(images, 'featureGraphic.png'), renderOpaquePng(svg, 1024));
  writeFileSync(join(images, 'icon.png'), renderPng(icon, 512));
  console.log(`${store}: icon.png, featureGraphic.png`);
}

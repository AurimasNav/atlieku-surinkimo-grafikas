import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import zlib from 'node:zlib';
import { Resvg } from '@resvg/resvg-js';

export const repo = join(import.meta.dirname, '..', '..');
export const metadata = join(repo, 'fastlane', 'metadata', 'android');
export const rawShots = join(import.meta.dirname, 'raw');

/** App language → Google Play language (folder in ../metadata/android). */
export const languages = { lt: 'lt', en: 'en-US', ru: 'ru-RU', pl: 'pl-PL' };

/** The app's translations for a language. */
export const strings = (lang) =>
  JSON.parse(readFileSync(join(repo, 'app', 'src', 'i18n', 'locales', `${lang}.json`), 'utf8'));

// The app's font. Needs `npm ci` in app/ first.
const fontDir = join(repo, 'app', 'node_modules', '@expo-google-fonts', 'manrope');
export const font = {
  fontFiles: ['700Bold/Manrope_700Bold.ttf', '800ExtraBold/Manrope_800ExtraBold.ttf'].map((f) => join(fontDir, f)),
  loadSystemFonts: false,
  defaultFontFamily: 'Manrope',
};

export const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');

/** Width in pixels of one line of Manrope ExtraBold text. */
export function textWidth(text, size, letterSpacing = 0) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="3000" height="300" viewBox="0 0 3000 300">` +
    `<text x="0" y="200" font-family="Manrope" font-weight="800" font-size="${size}" letter-spacing="${letterSpacing}">${esc(text)}</text></svg>`;
  const box = new Resvg(svg, { font }).getBBox();
  return box ? box.x + box.width : 0;
}

/** Renders SVG to a PNG with transparency (for the icon). */
export const renderPng = (svg, width) => new Resvg(svg, { font, fitTo: { mode: 'width', value: width } }).render().asPng();

/**
 * Renders SVG to a 24-bit PNG without an alpha channel: Google Play requires that for feature
 * graphics and screenshots, and resvg always writes RGBA.
 */
export function renderOpaquePng(svg, width) {
  const image = new Resvg(svg, { font, fitTo: { mode: 'width', value: width }, background: '#FFFFFF' }).render();
  const { width: w, height: h, pixels } = image;
  const raw = Buffer.alloc((w * 3 + 1) * h); // each row: filter byte 0, then RGB
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const s = (y * w + x) * 4;
      const d = y * (w * 3 + 1) + 1 + x * 3;
      raw[d] = pixels[s];
      raw[d + 1] = pixels[s + 1];
      raw[d + 2] = pixels[s + 2];
    }
  }
  const chunk = (type, data) => {
    const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(body));
    return Buffer.concat([length, body, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(w, 0);
  header.writeUInt32BE(h, 4);
  header[8] = 8; // bits per channel
  header[9] = 2; // colour type: RGB
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/** The brand background used by the icon, feature graphic and screenshot frames. */
export const gradient = (id = 'bg') =>
  `<linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">` +
  `<stop offset="0" stop-color="#18975F"/><stop offset="1" stop-color="#0A4A31"/></linearGradient>`;

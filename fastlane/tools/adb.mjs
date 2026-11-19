// A small adb-based driver: find elements on screen by their text and tap them.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const sdk = process.env.ANDROID_HOME ?? process.env.ANDROID_SDK_ROOT;
const adb = sdk ? `${sdk}/platform-tools/adb` : 'adb';
const run = (...args) => execFileSync(adb, args, { maxBuffer: 64 * 1024 * 1024 });

export const shell = (command) => run('shell', command).toString();
export const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

const unescape = (s) =>
  s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#10;/g, '\n').replace(/&amp;/g, '&');

/** Everything on screen, from the accessibility tree. */
export function elements() {
  shell('uiautomator dump /sdcard/ui.xml');
  const xml = run('exec-out', 'cat', '/sdcard/ui.xml').toString('utf8');
  const found = [];
  for (const [, attrs] of xml.matchAll(/<node ([^>]*?)\/?>/g)) {
    const attr = (name) => unescape((attrs.match(new RegExp(`${name}="([^"]*)"`)) ?? [])[1] ?? '');
    const b = attr('bounds').match(/\[(\d+),(\d+)\]\[(\d+),(\d+)\]/);
    if (!b) continue;
    const [x1, y1, x2, y2] = b.slice(1).map(Number);
    found.push({ text: attr('text'), label: attr('content-desc'), x: (x1 + x2) >> 1, y: (y1 + y2) >> 1 });
  }
  return found;
}

/** Whether an element's text or accessibility label is `text` (any case). */
export const is = (text) => (e) => e.text.toLowerCase() === text.toLowerCase() || e.label.toLowerCase() === text.toLowerCase();

/**
 * What `find` returns for the elements on screen, as soon as that is something, checking every
 * half second for up to `timeout` ms. Undefined if it never is.
 */
export function waitFor(find, timeout = 20000) {
  const until = Date.now() + timeout;
  for (;;) {
    const found = find(elements());
    if (found) return found;
    if (Date.now() > until) return undefined;
    sleep(500);
  }
}

/**
 * Taps the nth element whose text or accessibility label is `text`, waiting up to `timeout` ms
 * for it to appear (slower machines and emulators take longer to show a screen).
 */
export function tap(text, nth = 0, timeout = 20000) {
  const hit = waitFor((all) => all.filter(is(text))[nth], timeout);
  if (!hit) throw new Error(`Not on screen after ${timeout / 1000} s: ${text}`);
  return tapAt(hit.x, hit.y);
}

/** The texts and labels on screen, for a failure message. */
export const screenText = () => [...new Set(elements().flatMap((e) => [e.text, e.label]).filter(Boolean))];

export const tapAt = (x, y) => shell(`input tap ${x} ${y}`);
export const logcat = (...args) => run('logcat', ...args).toString();
export const type = (ascii) => shell(`input text ${ascii.replace(/ /g, '%s')}`);
export const back = () => shell('input keyevent 4');
/** Deletes `count` characters before the end of the focused text field. */
export const clearField = (count) => shell(`input keyevent KEYCODE_MOVE_END ${'KEYCODE_DEL '.repeat(count)}`);
export const screenshot = (file) => writeFileSync(file, run('exec-out', 'screencap', '-p'));

// Walks through setup with an address in Kauno r. on a running emulator and saves the screens
// to raw/kauno/: node kauno-walk.mjs
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { back, screenshot, shell, sleep, tap, type } from './adb.mjs';
import { setUp, tearDown } from './capture.mjs';
import { rawShots, strings } from './shared.mjs';

const app = 'io.github.aurimasnav.siuksliaveze';
const s = strings('lt');
const out = join(rawShots, 'kauno');
mkdirSync(out, { recursive: true });
const shot = (name) => screenshot(join(out, `${name}.png`));

setUp();
try {
  shell(`pm clear ${app}`);
  shell(`pm grant ${app} android.permission.POST_NOTIFICATIONS`);
  shell(`monkey -p ${app} -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1`);
  sleep(5000);
  tap(s.onboarding.start);
  sleep(2500);
  tap(s.setup.locationPlaceholder);
  sleep(1000);
  type('Karkisk');
  sleep(3000);
  back();
  sleep(1200);
  shot('1-search');
  tap('Karkiškių k.');
  sleep(3500);
  shot('2-street');
  tap('Ganyklų g.');
  sleep(2000);
  shot('3-house');
  tap('2');
  sleep(3000);
  shot('4-done');
  tap(s.setup.enable);
  sleep(3500);
  shot('5-home');
  tap(s.home.settings);
  sleep(2500);
  shot('6-settings');
} finally {
  tearDown();
}

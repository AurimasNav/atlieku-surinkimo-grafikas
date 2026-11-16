// Takes the raw store screenshots on a running emulator with the app installed, in every
// language (or the ones given): npm run capture [-- lt en]
// Saves them to raw/<language>/ for frame.mjs. The screen is switched to 1080 x 1920 (9:16,
// what Google Play accepts), the status bar to a fixed demo state and animations off (as in CI:
// the location option's pulsing ring never lets uiautomator see an idle screen); all three are
// reset at the end.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { back, screenshot, shell, sleep, tap, tapAt, type } from './adb.mjs';
import { languages, rawShots, strings } from './shared.mjs';

const app = 'io.github.aurimasnav.siuksliaveze';
// A place with all three waste types and a pickup soon. Pick another one if it stops working.
const place = { search: 'Suderv', name: 'Sudervė' };
const languageNames = { lt: 'Lietuvių', en: 'English', ru: 'Русский', pl: 'Polski' };

const demo = (command, extras = '') =>
  shell(`am broadcast -a com.android.systemui.demo -e command ${command} ${extras}`);

const animationScales = ['window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'];
let savedScales = {};

export function setUp() {
  savedScales = Object.fromEntries(animationScales.map((name) => [name, shell(`settings get global ${name}`).trim()]));
  for (const name of animationScales) shell(`settings put global ${name} 0`);
  shell('wm size 1080x1920');
  shell('wm density 420');
  shell('settings put global sysui_demo_allowed 1');
  demo('enter');
  demo('clock', '-e hhmm 1800');
  demo('battery', '-e level 100 -e plugged false');
  demo('network', '-e wifi show -e level 4 -e fully true -e mobile hide');
  demo('notifications', '-e visible false');
}

export function tearDown() {
  demo('exit');
  shell('wm size reset');
  shell('wm density reset');
  for (const [name, value] of Object.entries(savedScales)) {
    shell(value === 'null' || value === '' ? `settings delete global ${name}` : `settings put global ${name} ${value}`);
  }
}

/** Goes through the app from a fresh start in one language, saving the screens to raw/<lang>/. */
export function capture(lang) {
  const s = strings(lang);
  const out = join(rawShots, lang);
  mkdirSync(out, { recursive: true });
  const shot = (name) => screenshot(join(out, `${name}.png`));
  console.log(lang);

  shell(`pm clear ${app}`);
  shell(`pm grant ${app} android.permission.POST_NOTIFICATIONS`);
  shell(`monkey -p ${app} -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1`);
  sleep(5000);

  // Welcome screen, in the chosen language.
  tapAt(850, 175); // language menu
  sleep(1200);
  tap(languageNames[lang]); // the menu item, or the menu button itself if already chosen
  sleep(2500);
  shot('5-welcome');

  // Search for the place, with the keyboard hidden.
  tap(s.onboarding.start);
  sleep(2500);
  tap(s.setup.locationPlaceholder);
  sleep(1000);
  type(place.search);
  sleep(2500);
  back();
  sleep(1200);
  shot('2-search');

  tap(place.name);
  sleep(2500);
  shot('3-done');

  tap(s.setup.enable);
  sleep(3500);
  shot('1-home');

  // Settings → mixed waste → own schedule: third day, every two weeks.
  tap(s.home.settings);
  sleep(2500);
  tap(place.name, 1);
  sleep(2500);
  tap(s.manage.setCustom);
  sleep(2500);
  tapAt(525, 675);
  sleep(800);
  tap(s.custom.week2);
  sleep(1200);
  shot('4-custom');
}

// Run directly (npm run capture), not when smoke.mjs imports it.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const wanted = process.argv.slice(2);
  setUp();
  try {
    for (const lang of wanted.length ? wanted : Object.keys(languages)) capture(lang);
  } finally {
    tearDown();
  }
}

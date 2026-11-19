// Takes the raw store screenshots on a running emulator with the app installed, in every
// language (or the ones given): npm run capture [-- lt en]
// Saves them to raw/<language>/ for frame.mjs. The screen is switched to 1080 x 1920 (9:16,
// what Google Play accepts), the status bar to a fixed demo state and animations off (as in CI:
// the location option's pulsing ring never lets uiautomator see an idle screen); all three are
// reset at the end.
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { back, clearField, elements, is, screenshot, shell, sleep, tap, tapAt, type, waitFor } from './adb.mjs';
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
  chooseLanguage(lang);
  sleep(1500);
  shot('5-welcome');

  // Search for the place, with the keyboard hidden.
  tap(s.onboarding.start);
  sleep(2500);
  search(s.setup.locationPlaceholder, place.search, place.name);
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

/**
 * Picks `lang` in the language menu of the welcome screen. Right after the start the app may
 * not have drawn the menu yet, and a tap then is lost: so this waits for the menu button (found
 * by its label in any of the languages), opens the menu again if its list doesn't show, and
 * checks that the screen is in `lang` afterwards.
 */
function chooseLanguage(lang) {
  const buttonLabels = Object.keys(languages).map((l) => strings(l).settings.language);
  // Always the list's first item, in the language shown.
  const phoneLanguage = Object.keys(languages).map((l) => strings(l).settings.systemLanguage);
  const listOpen = (all) => (all.some((e) => phoneLanguage.some((text) => is(text)(e))) ? all : undefined);
  for (let attempt = 1; attempt <= 3; attempt++) {
    let list = listOpen(elements());
    if (!list) {
      const button = waitFor((all) => all.find((e) => buttonLabels.some((label) => is(label)(e))), 60000);
      if (!button) throw new Error('Not on screen after 60 s: the language menu');
      tapAt(button.x, button.y);
      list = waitFor(listOpen, 5000);
      if (!list) continue;
    }
    // The button shows the current language too; the list's item is below it.
    const item = list.filter(is(languageNames[lang])).at(-1);
    if (!item) throw new Error(`Not in the language menu: ${languageNames[lang]}`);
    tapAt(item.x, item.y);
    if (waitFor((all) => all.find(is(strings(lang).onboarding.start)), 10000)) return;
  }
  throw new Error(`Couldn't switch the app to ${languageNames[lang]}`);
}

/**
 * Searches for `query` in the search field with the placeholder `field` and waits for `result`,
 * with the keyboard hidden. If it doesn't show, the field is cleared and the query typed again:
 * a failed run showed the query in the field and neither results nor "nothing found", so the
 * app hadn't received the text.
 */
function search(field, query, result) {
  tap(field);
  sleep(1000);
  for (let attempt = 1; attempt <= 3; attempt++) {
    type(query);
    sleep(1500);
    back(); // hides the keyboard
    if (waitFor((all) => all.find(is(result)), 10000)) return;
    tap(query); // the field, showing what was typed
    sleep(500);
    clearField(query.length + 2);
    sleep(500);
  }
  throw new Error(`Not found by the search "${query}": ${result}`);
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

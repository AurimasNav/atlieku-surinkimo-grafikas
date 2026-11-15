// Smoke test for pull requests (.github/workflows/app-android.yml): on a running emulator with
// the app installed, goes through the app in every language (or the ones given) like
// capture.mjs, then fails if the app crashed or logged a JavaScript error.
// Usage: npm run smoke [-- lt en]
import { logcat } from './adb.mjs';
import { capture, setUp, tearDown } from './capture.mjs';
import { languages } from './shared.mjs';

const wanted = process.argv.slice(2);
logcat('-c');
logcat('-b', 'crash', '-c');

const problems = [];
setUp();
try {
  for (const lang of wanted.length ? wanted : Object.keys(languages)) capture(lang);
} catch (error) {
  problems.push(`The walk-through stopped: ${error.message}`);
} finally {
  tearDown();
}

const lines = (text) => text.split('\n').filter((l) => l.trim() && !l.startsWith('---------'));
const crashes = lines(logcat('-d', '-b', 'crash'));
const jsErrors = lines(logcat('-d', '-s', 'ReactNativeJS:E'));
if (crashes.length) problems.push(`The app crashed:\n${crashes.slice(0, 40).join('\n')}`);
if (jsErrors.length) problems.push(`JavaScript errors:\n${jsErrors.slice(0, 40).join('\n')}`);

if (problems.length) {
  console.error(problems.join('\n\n'));
  process.exit(1);
}
console.log('No crashes or JavaScript errors.');

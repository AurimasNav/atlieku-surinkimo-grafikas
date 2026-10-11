// Keeps the translations in step with the English source file.
//
//   npm run i18n:check
//     Fails when a locale is missing keys, plural forms or {{placeholders}} from en.json, or
//     when an English string changed after it was translated (a "stale" translation).
//
//   npm run i18n:accept -- <lang...> [--key <key>...]
//     Records that the given languages are up to date with the current English text, for all
//     keys or only the given ones. Run it after updating (or checking) the translations, and
//     commit translations.lock.json with them.
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const i18nDir = join(import.meta.dirname, '..', 'src', 'i18n');
const localesDir = join(i18nDir, 'locales');
const lockPath = join(i18nDir, 'translations.lock.json');
const SOURCE = 'en';
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function flatten(object, prefix = '') {
  return Object.entries(object).flatMap(([key, value]) =>
    typeof value === 'object' ? flatten(value, `${prefix}${key}.`) : [[`${prefix}${key}`, value]],
  );
}

function placeholders(text) {
  return [...text.matchAll(/{{\s*(\w+)\s*}}/g)].map((m) => m[1]).sort().join(',');
}

/** Groups "inDays_one", "inDays_other" under "inDays" and keeps every other key as is. */
function byBaseKey(entries) {
  const result = new Map();
  for (const [key, value] of entries) {
    const base = key.replace(PLURAL_SUFFIX, '');
    const plural = PLURAL_SUFFIX.test(key);
    if (!result.has(base)) result.set(base, { plural, forms: new Map() });
    result.get(base).forms.set(key, value);
  }
  return result;
}

/** Fingerprint of the English text a translation is based on (all plural forms together). */
function sourceHash({ forms }) {
  const text = [...forms.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${k}=${v}`).join('\n');
  return createHash('sha256').update(text).digest('hex').slice(0, 12);
}

const load = (lang) => byBaseKey(flatten(JSON.parse(readFileSync(join(localesDir, `${lang}.json`), 'utf8'))));
const source = load(SOURCE);
const languages = readdirSync(localesDir)
  .filter((f) => f.endsWith('.json'))
  .map((f) => f.replace('.json', ''))
  .filter((lang) => lang !== SOURCE);
const lock = existsSync(lockPath) ? JSON.parse(readFileSync(lockPath, 'utf8')) : {};

/** Missing keys, plural forms and placeholder mismatches for one language. */
function structuralProblems(lang) {
  const problems = [];
  const target = load(lang);
  const categories = new Intl.PluralRules(lang).resolvedOptions().pluralCategories;

  for (const [base, { plural, forms }] of source) {
    const entry = target.get(base);
    if (!entry) {
      problems.push(`${lang}: missing "${base}"`);
      continue;
    }
    const expectedVars = placeholders([...forms.values()][0]);
    const expectedKeys = plural ? categories.map((c) => `${base}_${c}`) : [base];
    for (const key of expectedKeys) {
      const value = entry.forms.get(key);
      if (value === undefined) problems.push(`${lang}: missing "${key}"`);
      else if (!value.trim()) problems.push(`${lang}: empty "${key}"`);
      else if (placeholders(value) !== expectedVars)
        problems.push(`${lang}: "${key}" uses {{${placeholders(value)}}}, expected {{${expectedVars}}}`);
    }
    for (const key of entry.forms.keys()) {
      if (!expectedKeys.includes(key)) problems.push(`${lang}: unexpected "${key}"`);
    }
  }
  for (const base of target.keys()) {
    if (!source.has(base)) problems.push(`${lang}: "${base}" is not in ${SOURCE}.json`);
  }
  return problems;
}

/** Keys whose English text changed since this language last accepted them. */
function staleKeys(lang) {
  return [...source].filter(([base, entry]) => lock[lang]?.[base] !== sourceHash(entry)).map(([base]) => base);
}

function check() {
  const problems = languages.flatMap(structuralProblems);
  const stale = languages.map((lang) => [lang, staleKeys(lang)]).filter(([, keys]) => keys.length);

  if (stale.length) {
    problems.push('', 'English text changed since these were translated:');
    for (const [lang, keys] of stale) problems.push(...keys.map((key) => `${lang}: "${key}"`));
    problems.push(
      '',
      'Update the translations, then record them as reviewed, e.g.:',
      `  npm run i18n:accept -- ${stale.map(([lang]) => lang).join(' ')}`,
      `  npm run i18n:accept -- ${stale[0][0]} --key ${stale[0][1][0]}`,
    );
  }
  if (problems.length) {
    console.error(problems.join('\n'));
    process.exit(1);
  }
  console.log(`Translations OK: ${[SOURCE, ...languages].join(', ')}`);
}

function accept(args) {
  const langs = [];
  const keys = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--key') keys.push(args[++i]);
    else langs.push(args[i]);
  }
  if (!langs.length) {
    console.error(`Usage: npm run i18n:accept -- <${languages.join('|')}...> [--key <key>...]`);
    process.exit(1);
  }
  for (const key of keys) {
    if (!source.has(key)) {
      console.error(`Unknown key "${key}" (use the key without a plural suffix, e.g. home.inDays)`);
      process.exit(1);
    }
  }

  const problems = [];
  for (const lang of langs) {
    if (!languages.includes(lang)) {
      problems.push(`Unknown language "${lang}"`);
      continue;
    }
    // Never record a language as up to date while it is structurally incomplete.
    problems.push(...structuralProblems(lang));
  }
  if (problems.length) {
    console.error([...problems, '', 'Fix these before accepting.'].join('\n'));
    process.exit(1);
  }

  for (const lang of langs) {
    const before = staleKeys(lang);
    const accepted = keys.length ? keys : [...source.keys()];
    const entries = Object.entries(lock[lang] ?? {}).filter(([base]) => source.has(base));
    lock[lang] = Object.fromEntries(entries);
    for (const base of accepted) lock[lang][base] = sourceHash(source.get(base));
    lock[lang] = Object.fromEntries(Object.entries(lock[lang]).sort(([a], [b]) => a.localeCompare(b)));
    const changed = accepted.filter((key) => before.includes(key));
    console.log(`${lang}: accepted ${changed.length > 8 ? `${changed.length} keys` : changed.length ? changed.join(', ') : 'nothing new'}`);
  }

  const sorted = Object.fromEntries(Object.entries(lock).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(lockPath, `${JSON.stringify(sorted, null, 2)}\n`);
}

const [command = 'check', ...args] = process.argv.slice(2);
if (command === 'accept') accept(args);
else check();

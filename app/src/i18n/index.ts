import { getLocales } from 'expo-localization';
import { createInstance } from 'i18next';
import { initReactI18next } from 'react-i18next';

import { useSettings } from '@/store/settings';

import en from './locales/en.json';
import lt from './locales/lt.json';
import pl from './locales/pl.json';
import ru from './locales/ru.json';

/**
 * en.json is the source of truth: add or change a string there first, then update the
 * other locales and run `npm run i18n:accept`. `npm run i18n:check` (also run in CI) fails
 * when they drift apart, including translations made from older English text.
 */
export const resources = {
  en: { translation: en },
  lt: { translation: lt },
  ru: { translation: ru },
  pl: { translation: pl },
} as const;

export type Language = keyof typeof resources;
export const LANGUAGES = Object.keys(resources) as Language[];

/** Shown in each language's own name, so people can find theirs whatever is selected. */
export const LANGUAGE_NAMES: Record<Language, string> = {
  lt: 'Lietuvių',
  en: 'English',
  ru: 'Русский',
  pl: 'Polski',
};

export function systemLanguage(): Language {
  for (const locale of getLocales()) {
    const code = locale.languageCode as Language | null;
    if (code && code in resources) return code;
  }
  return 'en';
}

export function resolveLanguage(preference: Language | 'system'): Language {
  return preference === 'system' ? systemLanguage() : preference;
}

const i18n = createInstance();
i18n.use(initReactI18next).init({
  resources,
  // Settings are stored synchronously, so the saved choice is available here already.
  lng: resolveLanguage(useSettings.getState().language),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;

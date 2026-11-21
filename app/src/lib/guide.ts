import { GUIDE_ITEMS } from './guide-items';
import { isCustomArea, type Place, type Resolved } from './resolve';
import { normalizeForSearch, WASTE_KINDS, type WasteKind } from './schedule';

/**
 * The "Which bin?" sorting guide: where an item goes, for the user's place.
 *
 * The items and their texts live in guide-items.ts, in every app language, rather than in the
 * locale files: they are content, not interface strings. This file finds items and works out
 * the advice for a place: a container the place doesn't have is replaced by its fallback (no
 * food waste bin: home compost or mixed waste), and a few rules differ by waste company.
 */

export const GUIDE_LANGUAGES = ['en', 'lt', 'ru', 'pl'] as const;
export type GuideLanguage = (typeof GUIDE_LANGUAGES)[number];
export type Localized = Record<GuideLanguage, string>;

/** Places other than the containers at home. Their names are in the locale files (guide.dest). */
export const OFF_CURB = ['deposit', 'shop', 'site', 'greenSite', 'textile', 'pharmacy', 'compost', 'orangeBag'] as const;
export type OffCurb = (typeof OFF_CURB)[number];
/** A container at home (a waste kind) or somewhere else to take the item. */
export type Destination = WasteKind | OffCurb;

export const GUIDE_CATEGORIES = [
  'food',
  'paper',
  'packaging',
  'glass',
  'garden',
  'hazardous',
  'bulky',
  'textile',
  'other',
] as const;
export type GuideCategory = (typeof GUIDE_CATEGORIES)[number];

/**
 * Waste companies whose rules differ in places: the two in Vilniaus r., Kauno švara and
 * Ekonovus in Kauno r. (one region here) and the Telšiai regional centre for Mažeikių r.
 */
export const REGIONS = ['nemencine', 'nemezio', 'kauno', 'mazeikiai'] as const;
export type Region = (typeof REGIONS)[number];

export type GuideRule = {
  /** Where it goes, best first; more than one reads "A, or B". */
  to: Destination[];
  /** Instead of a container the place doesn't have; by default see defaultFallback(). */
  fallback?: Destination[];
  tip?: Localized;
};

export type GuideItem = GuideRule & {
  id: string;
  category: GuideCategory;
  /** The name shown first, then other words people search for. */
  names: Record<GuideLanguage, string[]>;
  /** Fine for a home compost heap, so it's offered when there is no food or green waste bin. */
  compost?: boolean;
  /** Where a company's rule differs from the general one, with the source in a comment. */
  regions?: Partial<Record<Region, Partial<GuideRule>>>;
};

export type Advice = {
  /** Where to take it, best first. */
  to: Destination[];
  /** The item's usual container isn't collected at the user's place, so `to` is the fallback. */
  missing?: WasteKind;
  /** We don't know the user's containers: what to do without the usual one. */
  otherwise?: { kind: WasteKind; to: Destination[] };
  tip?: Localized;
};

export const isKind = (destination: Destination): destination is WasteKind =>
  (WASTE_KINDS as readonly string[]).includes(destination);

export function guideLanguage(language: string): GuideLanguage {
  const code = language.slice(0, 2) as GuideLanguage;
  return GUIDE_LANGUAGES.includes(code) ? code : 'en';
}

/** Like normalizeForSearch, plus the Polish "ł" (no combining mark to strip) and no punctuation. */
export function normalizeGuide(text: string): string {
  return normalizeForSearch(text)
    .replace(/ł/g, 'l')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

const normalized = new Map<string, string[]>();
function namesOf(item: GuideItem, language: GuideLanguage): string[] {
  const key = `${item.id}:${language}`;
  let names = normalized.get(key);
  if (!names) {
    names = item.names[language].map(normalizeGuide);
    normalized.set(key, names);
  }
  return names;
}

/** 0 when the item doesn't match; higher for exact and leading matches, and for its main name. */
function score(names: string[], phrase: string, words: string[]): number {
  let best = 0;
  names.forEach((name, index) => {
    let points = 0;
    if (name === phrase) points = 100;
    else if (name.startsWith(phrase)) points = 80;
    else if (words.every((word) => name.split(' ').some((part) => part.startsWith(word)))) points = 60;
    else if (words.every((word) => name.includes(word))) points = 40;
    if (points && index === 0) points += 5;
    best = Math.max(best, points);
  });
  return best;
}

export const displayName = (item: GuideItem, language: GuideLanguage) => item.names[language][0];

const byName = (language: GuideLanguage) => (a: GuideItem, b: GuideItem) =>
  displayName(a, language).localeCompare(displayName(b, language), language);

/**
 * Items whose names contain every word of the query, ignoring case and diacritics ("dezute"
 * finds "dėžutė"), best matches first. Searches the app's language, and every language if that
 * finds nothing. Without a query: the items of `category`, alphabetically, or none.
 */
export function searchGuide(query: string, language: GuideLanguage, category?: GuideCategory): GuideItem[] {
  const pool = category ? GUIDE_ITEMS.filter((item) => item.category === category) : GUIDE_ITEMS;
  const phrase = normalizeGuide(query);
  const words = phrase.split(' ').filter(Boolean);
  if (!words.length) return category ? [...pool].sort(byName(language)) : [];

  const search = (languages: readonly GuideLanguage[]) =>
    pool
      .map((item) => ({ item, points: Math.max(...languages.map((l) => score(namesOf(item, l), phrase, words))) }))
      .filter(({ points }) => points > 0)
      .sort((a, b) => b.points - a.points || byName(language)(a.item, b.item))
      .map(({ item }) => item);
  const results = search([language]);
  return results.length ? results : search(GUIDE_LANGUAGES);
}

/** Shown before anything is typed. */
export const POPULAR = [
  'pizza-box',
  'batteries',
  'yogurt-cup',
  'light-bulbs',
  'tetra-pak',
  'peels',
  'jars',
  'clothes',
  'medicines',
  'styrofoam',
];

export function guideItem(id: string): GuideItem | undefined {
  return GUIDE_ITEMS.find((item) => item.id === id);
}

/** The company whose rules apply to the place, if we know it. */
export function regionOf(place: Place | null, resolved: Resolved): Region | undefined {
  if (place?.kauno) return 'kauno';
  const official = resolved.areas.find((area) => !isCustomArea(area));
  if (!resolved.location && !official) return undefined;
  // Nemenčinės komunalininkas' places and rows have no provider (see schedule.ts).
  const provider = resolved.location?.provider ?? official?.provider ?? 'nemencine';
  return (REGIONS as readonly string[]).includes(provider) ? (provider as Region) : undefined;
}

/**
 * Containers the place has, or undefined if we can't tell (no place, or the data isn't loaded).
 * A kind counts unless it isn't collected there or the user said they don't have it. Every home
 * has a mixed waste container. In Kauno r. glass and packaging are emptied by UAB „Ekonovus“,
 * which publishes no data, but every home has them.
 */
export function availableKinds(place: Place | null, resolved: Resolved): Set<WasteKind> | undefined {
  if (!place) return undefined;
  const known = WASTE_KINDS.filter((kind) => resolved.kinds[kind].status !== 'none');
  if (!known.length) return undefined;
  const kinds = new Set<WasteKind>(['household', ...known]);
  if (place.kauno) {
    for (const kind of ['packaging', 'glass'] as const) if (place.choices[kind] !== null) kinds.add(kind);
  }
  return kinds;
}

/** Where things go when the place has no container of `kind`. */
function defaultFallback(kind: WasteKind, item: GuideItem, region: Region | undefined): Destination[] {
  switch (kind) {
    case 'food': {
      // Vilniaus r. collects food waste in orange bags put in the mixed waste container
      // (https://vrsa.lt/titulinio-naujienos/424/vilniaus-rajono-gyventojams-nemokami-oranziniai-maiseliai-maisto-atliekoms-rusiuoti:6624).
      const vilnius = region === 'nemencine' || region === 'nemezio';
      return [...(item.compost ? (['compost'] as const) : []), vilnius ? 'orangeBag' : 'household'];
    }
    case 'green':
      return ['compost', 'greenSite'];
    default:
      // Bulky waste sites take packaging and glass too (vaatc.lt, kaunoratc.lt, tratc.lt).
      return ['site'];
  }
}

const unique = <T>(list: T[]) => [...new Set(list)];

/**
 * Where the item goes for this place. `available` comes from availableKinds(): a container the
 * place doesn't have is replaced by the fallback, and when we don't know, the fallback for the
 * first container is given as `otherwise`.
 */
export function advise(item: GuideItem, region: Region | undefined, available: Set<WasteKind> | undefined): Advice {
  const rule: GuideRule = { to: item.to, fallback: item.fallback, tip: item.tip, ...(region && item.regions?.[region]) };
  const fallbackFor = (kind: WasteKind) => {
    const list = (rule.fallback ?? defaultFallback(kind, item, region)).filter(
      (destination) => !isKind(destination) || !available || available.has(destination),
    );
    return list.length ? list : (['site'] as Destination[]);
  };

  if (!available) {
    const kind = rule.to.find((destination): destination is WasteKind => isKind(destination) && destination !== 'household');
    return { to: rule.to, tip: rule.tip, otherwise: kind && { kind, to: fallbackFor(kind) } };
  }
  let missing: WasteKind | undefined;
  const to = rule.to.flatMap((destination) => {
    if (!isKind(destination) || available.has(destination)) return [destination];
    missing ??= destination;
    return fallbackFor(destination);
  });
  return { to: unique(to), missing, tip: rule.tip };
}

/** Lists of places for a destination in the region, where a regional waste centre publishes one. */
export function locationsUrl(destination: Destination, region: Region | undefined): string | undefined {
  if (destination === 'deposit') return 'https://grazintiverta.lt/';
  const vilnius = region === 'nemencine' || region === 'nemezio';
  if (destination === 'site') {
    if (vilnius) return 'https://www.vaatc.lt/atlieku-pridavimas/dideliu-gabaritu-atlieku-surinkimo-aiksteles/';
    if (region === 'kauno') return 'https://kaunoratc.lt/dgasa/';
  }
  if (destination === 'greenSite') {
    if (vilnius) return 'https://www.vaatc.lt/atlieku-pridavimas/zaliuju-atlieku-surinkimo-aiksteles/';
    if (region === 'kauno') return 'https://kaunoratc.lt/zaka/';
  }
  if ((destination === 'site' || destination === 'greenSite') && region === 'mazeikiai') {
    return 'https://tratc.lt/atlieku-priemimo-tvarka-ir-ikainiai/tratc-atlieku-surinkimo-aiksteles/';
  }
  return undefined;
}

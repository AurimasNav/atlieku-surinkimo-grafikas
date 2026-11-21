import { SCHEDULE_URL, SUPPORTED_SCHEMA_VERSION } from './config';

/** Food and green waste are collected separately only in some towns and districts. */
export const WASTE_KINDS = ['household', 'packaging', 'glass', 'food', 'green'] as const;
export type WasteKind = (typeof WASTE_KINDS)[number];

/** One row of the published schedule: a group of addresses with the same pickup dates. */
export type Area = {
  id: string;
  kind: WasteKind;
  name: string;
  district?: string;
  group?: string;
  weekday?: string;
  /** Source text for rows that have no exact dates (e.g. "kas antras mėnesio antradienis"). */
  note?: string;
  /** ISO dates, YYYY-MM-DD, sorted. */
  dates: string[];
  /**
   * Part of the newest published schedule for its kind, even when its dates have passed: glass
   * is collected once a quarter, so between pickups the next date isn't known yet.
   */
  current?: boolean;
  /** Id of the company whose schedule this row is from; absent for Nemenčinės komunalininkas. */
  provider?: string;
};

/** How one schedule covers a location. See pipeline/src/schedule_pipeline/locations.py. */
export type LocationSchedule = {
  /** The row for the whole location (or for streets not listed in `streets`). */
  area?: string;
  /** Street key -> rows; present when the schedule splits this location by street. */
  streets?: Record<string, string[]>;
  /** Several rows could apply (e.g. private house vs apartment building); the user picks. */
  candidates?: string[];
};

/** A settlement from the Address Register, linked to its rows in each schedule. */
export type Location = {
  id: string;
  name: string;
  /** "k.", "vs.", "mstl.", "m." */
  type: string;
  /** Seniūnija, genitive as in the register, e.g. "Avižienių". */
  district: string;
  /** [key, label] pairs; only present when some schedule depends on the street. */
  streets?: [string, string][];
  /** Missing kind = that waste type isn't collected here according to the schedules. */
  schedule?: Partial<Record<WasteKind, LocationSchedule>>;
  /** Id of the company that serves the location; absent for Nemenčinės komunalininkas. */
  provider?: string;
};

/** A company whose schedules are in the data. */
export type Provider = {
  id: string;
  name: string;
  /** The company's official schedule page. */
  url: string;
  /** When its part of the data was last built; stays old while its source can't be read. */
  generatedAt?: string;
};

export type ScheduleData = {
  schemaVersion: number;
  generatedAt: string;
  source: string;
  coverage: Partial<Record<WasteKind, { from: string; to: string }>>;
  areas: Area[];
  /** Added later without a schema bump, so older data may not have it. */
  locations?: Location[];
  /** Added with a second company in Vilniaus r.; older data has only Nemenčinės komunalininkas. */
  providers?: Provider[];
  /**
   * Not part of the download: the schedules of the user's own addresses in Kauno r., kept by
   * the app next to the data (see lib/kauno.ts). `key` says which address they belong to.
   */
  personals?: Personal[];
  /** One address, as app versions before several places saved it (see `personalsOf`). */
  personal?: Personal;
};

/** The schedules of one Kauno r. address, and when Kauno švara's data they come from was built. */
export type Personal = { key: string; areas: Area[]; generatedAt?: string };

/** The saved schedules of Kauno r. addresses, also those saved by older app versions. */
export const personalsOf = (data: ScheduleData | null | undefined): Personal[] =>
  data?.personals ?? (data?.personal ? [data.personal] : []);

/** `data` with these Kauno r. addresses' schedules saved next to it. */
export function withPersonals(data: ScheduleData, personals: Personal[]): ScheduleData {
  const { personal: _old, ...rest } = data;
  return { ...rest, personals };
}

export class UnsupportedScheduleError extends Error {}

type Download = { data: ScheduleData; etag?: string };

/** Vilniaus r. Returns null if the file hasn't changed since `etag`. */
export const fetchSchedule = (etag?: string): Promise<Download | null> => download(SCHEDULE_URL, etag);

/** Another region's file (config.REGION_URLS), in the same format. */
export const fetchRegion = (url: string, etag?: string): Promise<Download | null> =>
  download(`${url}/schedule.json`, etag);

async function download(url: string, etag?: string): Promise<Download | null> {
  const response = await fetch(url, {
    headers: etag ? { 'If-None-Match': etag } : undefined,
  });
  if (response.status === 304) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Schedule download failed: HTTP ${response.status}`);
  }
  const data = (await response.json()) as ScheduleData;
  if (data.schemaVersion > SUPPORTED_SCHEMA_VERSION) {
    throw new UnsupportedScheduleError();
  }
  return { data, etag: response.headers.get('etag') ?? undefined };
}

/** The rows, places and companies of a region: everything of the companies `ids`. */
export type RegionPart = Pick<ScheduleData, 'areas' | 'locations' | 'providers'>;

export function regionPart(data: ScheduleData, ids: string[]): RegionPart {
  const mine = (item: { provider?: string }) => Boolean(item.provider) && ids.includes(item.provider!);
  return {
    areas: data.areas.filter(mine),
    locations: (data.locations ?? []).filter(mine),
    providers: (data.providers ?? []).filter((provider) => ids.includes(provider.id)),
  };
}

/** `data` with the region's part replaced by `part`, so the app has one list of places. */
export function withRegion(data: ScheduleData, ids: string[], part: RegionPart): ScheduleData {
  const others = (item: { provider?: string }) => !item.provider || !ids.includes(item.provider);
  return {
    ...data,
    areas: [...data.areas.filter(others), ...part.areas],
    locations: [...(data.locations ?? []).filter(others), ...(part.locations ?? [])],
    providers: [...(data.providers ?? []).filter((p) => !ids.includes(p.id)), ...(part.providers ?? [])],
  };
}

/** Lower-case and strip diacritics so "rieses" finds "Riešės". */
export function normalizeForSearch(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

/**
 * Whether an area still matters: it has a pickup today or later, or a rule we show as text.
 * Rows from an earlier schedule period stay in the data for a while but shouldn't be offered.
 */
export function isCurrent(area: Area, today: string): boolean {
  return Boolean(area.note) || Boolean(area.current) || (area.dates.at(-1) ?? '') >= today;
}

function queryWords(query: string): string[] {
  return normalizeForSearch(query).split(/\s+/).filter(Boolean);
}

/**
 * Search results in Lithuanian alphabetical order (Š after S, Ž last), the names that start with
 * the first query word first: "riese" -> "Riešė" before "Didžioji Riešė".
 */
function byName<T extends { name: string }>(firstWord: string | undefined) {
  const startsWith = (item: T) => (firstWord ? normalizeForSearch(item.name).startsWith(firstWord) : false);
  return (a: T, b: T) => Number(startsWith(b)) - Number(startsWith(a)) || a.name.localeCompare(b.name, 'lt');
}

export function searchLocations(locations: Location[], query: string): Location[] {
  const words = queryWords(query);
  if (!words.length) return [];
  const matches = locations.filter((loc) => {
    const haystack = normalizeForSearch(`${loc.name} ${loc.district}`);
    return words.every((word) => haystack.includes(word));
  });
  return matches.sort(byName(words[0]));
}

/** Rows for the manual row picker: current rows of one kind, alphabetical like the place search. */
export function searchAreas(areas: Area[], kind: WasteKind, query: string, today: string): Area[] {
  const words = queryWords(query);
  const matches = areas.filter((area) => {
    if (area.kind !== kind || !isCurrent(area, today)) return false;
    if (!words.length) return true;
    const haystack = normalizeForSearch(`${area.district ?? ''} ${area.name}`);
    return words.every((word) => haystack.includes(word));
  });
  return matches.sort(byName(words[0]));
}

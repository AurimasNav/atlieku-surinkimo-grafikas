import { SCHEDULE_URL, SUPPORTED_SCHEMA_VERSION } from './config';

export const WASTE_KINDS = ['household', 'packaging', 'glass'] as const;
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
};

export type ScheduleData = {
  schemaVersion: number;
  generatedAt: string;
  source: string;
  coverage: Partial<Record<WasteKind, { from: string; to: string }>>;
  areas: Area[];
  /** Added later without a schema bump, so older data may not have it. */
  locations?: Location[];
};

export class UnsupportedScheduleError extends Error {}

export async function fetchSchedule(etag?: string): Promise<{ data: ScheduleData; etag?: string } | null> {
  const response = await fetch(SCHEDULE_URL, {
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
  return Boolean(area.note) || (area.dates.at(-1) ?? '') >= today;
}

function queryWords(query: string): string[] {
  return normalizeForSearch(query).split(/\s+/).filter(Boolean);
}

export function searchLocations(locations: Location[], query: string): Location[] {
  const words = queryWords(query);
  if (!words.length) return [];
  const matches = locations.filter((loc) => {
    const haystack = normalizeForSearch(`${loc.name} ${loc.district}`);
    return words.every((word) => haystack.includes(word));
  });
  // Names that start with the query first: "riese" -> "Riešė" before "Didžioji Riešė".
  const first = words[0];
  return matches.sort(
    (a, b) =>
      Number(!normalizeForSearch(a.name).startsWith(first)) - Number(!normalizeForSearch(b.name).startsWith(first)) ||
      a.name.localeCompare(b.name, 'lt'),
  );
}

export function searchAreas(areas: Area[], kind: WasteKind, query: string, today: string): Area[] {
  const words = queryWords(query);
  return areas.filter((area) => {
    if (area.kind !== kind || !isCurrent(area, today)) return false;
    if (!words.length) return true;
    const haystack = normalizeForSearch(`${area.district ?? ''} ${area.name}`);
    return words.every((word) => haystack.includes(word));
  });
}

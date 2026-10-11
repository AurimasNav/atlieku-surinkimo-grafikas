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

export type ScheduleData = {
  schemaVersion: number;
  generatedAt: string;
  source: string;
  coverage: Partial<Record<WasteKind, { from: string; to: string }>>;
  areas: Area[];
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

export function searchAreas(areas: Area[], kind: WasteKind, query: string, today: string): Area[] {
  const words = normalizeForSearch(query).split(/\s+/).filter(Boolean);
  return areas.filter((area) => {
    if (area.kind !== kind || !isCurrent(area, today)) return false;
    if (!words.length) return true;
    const haystack = normalizeForSearch(`${area.district ?? ''} ${area.name}`);
    return words.every((word) => haystack.includes(word));
  });
}

import { REGION_URLS, REGIONS_URL, SITE_URL, SUPPORTED_REGIONS_SCHEMA_VERSION } from './config';
import { downloadIfChanged } from './schedule';

/**
 * regions.json: the region folders the site publishes, written by the daily job from what it
 * deploys (pipeline/src/schedule_pipeline/regions.py). The app downloads those in the format of
 * schedule.json next to the built-in REGION_URLS, so a new folder reaches it without an update.
 *
 * Only what the app uses is kept. Fields it doesn't know, and regions of a kind it can't read
 * (Kauno švara's per-address format, "addresses": the app reads it only from kauno-r/, see
 * lib/kauno.ts), are left out, so the file can grow without breaking this version.
 */
export type RegionIndex = { schemaVersion: number; regions: IndexedRegion[] };

/** A folder with a schedule.json in the format of the root one. */
export type IndexedRegion = {
  /** "" for the site root (schedule.json itself), else the folder and a slash: "sratc/". */
  path: string;
  kind: 'settlements';
  /** Which files it has: schedule.json, and addresses.json for "Use my location". */
  files: string[];
  /** The ids of its companies, as its schedule.json lists them. */
  providers: string[];
};

/** A folder directly under the site; nothing that leads elsewhere. */
const FOLDER = /^[a-z0-9][a-z0-9._-]*\/$/i;

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

/** The index, or null if it isn't one this version can read (a newer schemaVersion). */
export function parseRegionIndex(json: unknown): RegionIndex | null {
  if (!isObject(json) || typeof json.schemaVersion !== 'number' || !Array.isArray(json.regions)) return null;
  if (json.schemaVersion > SUPPORTED_REGIONS_SCHEMA_VERSION) return null;
  const regions = json.regions.flatMap((entry): IndexedRegion[] => {
    if (!isObject(entry) || entry.kind !== 'settlements' || typeof entry.path !== 'string') return [];
    if (entry.path !== '' && !FOLDER.test(entry.path)) return [];
    const files = strings(entry.files);
    if (!files.includes('schedule.json')) return [];
    return [{ path: entry.path, kind: 'settlements', files, providers: strings(entry.providers) }];
  });
  return { schemaVersion: json.schemaVersion, regions };
}

/** regions.json, or null if it hasn't changed since `etag`. Throws if it can't be downloaded or read. */
export async function fetchRegionIndex(etag?: string): Promise<{ index: RegionIndex; etag?: string } | null> {
  const fresh = await downloadIfChanged(REGIONS_URL, etag);
  if (!fresh) return null;
  const index = parseRegionIndex(fresh.json);
  if (!index) throw new Error('regions.json is not in a format this version reads');
  return { index, etag: fresh.etag };
}

/** A folder's URL, written as in REGION_URLS (the schedule store keeps its regions by it). */
const folderUrl = (path: string) => `${SITE_URL}/${path.replace(/\/$/, '')}`;

/** The folders of the index, by URL; not the site root, which is schedule.json itself. */
const listed = (index: RegionIndex | null | undefined) =>
  new Map((index?.regions ?? []).filter((region) => region.path).map((region) => [folderUrl(region.path), region]));

/**
 * The regions to download next to schedule.json: the built-in ones, then those only the index
 * lists. Without an index (offline, older saved state), the built-in ones.
 */
export function regionUrls(index: RegionIndex | null | undefined): string[] {
  return [...new Set([...REGION_URLS, ...listed(index).keys()])];
}

/**
 * The regions whose addresses.json "Use my location" reads: those the index says have one, and
 * the built-in ones it doesn't list (they all have one).
 */
export function addressRegionUrls(index: RegionIndex | null | undefined): string[] {
  const regions = listed(index);
  return regionUrls(index).filter((url) => regions.get(url)?.files.includes('addresses.json') ?? true);
}

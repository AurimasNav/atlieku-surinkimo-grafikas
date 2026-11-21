import { KAUNO_URL, SUPPORTED_SCHEMA_VERSION } from './config';
import { type Area, normalizeForSearch, UnsupportedScheduleError, type WasteKind } from './schedule';

/**
 * Kauno r.: schedules of UAB „Kauno švara“, published per address rather than per settlement
 * (pipeline/src/schedule_pipeline/svara.py). The app downloads the list of towns, then only the
 * address file of the user's eldership, and keeps the schedules of the user's own address.
 */

/** Containers emptied on the same days. */
export type KaunoSchedule = { id: string; kind: WasteKind; rule: string; dates: string[] };

export type KaunoIndex = {
  schemaVersion: number;
  generatedAt: string;
  areas: KaunoSchedule[];
  elderships: {
    id: string;
    name: string;
    towns: string[];
    /**
     * Town -> its name in the Address Register, where that differs: "Akademijos mstl." ->
     * "Akademija". People search for it. Added later, so older data doesn't have it.
     */
    registerNames?: Record<string, string>;
  }[];
};

/** town -> street -> house number -> positions in `KaunoIndex.areas`. */
export type KaunoAddresses = {
  eldership: string;
  towns: Record<string, Record<string, Record<string, number[]>>>;
  /**
   * Spellings that were merged into another one ("Akademija" into "Akademijos mstl."):
   * town -> street -> house number -> [eldership file, town, street, house number] of the
   * address now. Not shown in the lists; they keep addresses saved with these spellings working.
   */
  aliases?: Record<string, Record<string, Record<string, [string, string, string, string]>>>;
};

/** The address the user picked; '' for a missing street or house number. */
export type KaunoAddress = {
  /** File name of the eldership's address file. */
  eldership: string;
  eldershipName: string;
  town: string;
  street: string;
  house: string;
};

export type KaunoTown = {
  eldership: string;
  eldershipName: string;
  /** As the address files write it ("Akademijos mstl."): addresses are saved with it. */
  town: string;
  /** Its name in the Address Register ("Akademija"), if that is different. */
  registerName?: string;
};

export const kaunoKey = (a: KaunoAddress) => [a.eldership, a.town, a.street, a.house].join('|');

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Download failed: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function fetchKaunoIndex(): Promise<KaunoIndex> {
  const index = await getJson<KaunoIndex>(`${KAUNO_URL}/schedule.json`);
  if (index.schemaVersion > SUPPORTED_SCHEMA_VERSION) throw new UnsupportedScheduleError();
  return index;
}

export const fetchKaunoAddresses = (eldership: string) =>
  getJson<KaunoAddresses>(`${KAUNO_URL}/addresses/${encodeURIComponent(eldership)}.json`);

export function kaunoTowns(index: KaunoIndex): KaunoTown[] {
  return index.elderships.flatMap((e) =>
    e.towns.map((town) => {
      const registerName = e.registerNames?.[town];
      return { eldership: e.id, eldershipName: e.name, town, ...(registerName ? { registerName } : {}) };
    }),
  );
}

/**
 * Towns matching every word of the query, names that start with it first. The file writes the
 * genitive ("Akademijos mstl."), so the town's name in the Address Register ("Akademija") is
 * searched too and counts as a name.
 */
export function searchKaunoTowns(towns: KaunoTown[], query: string): KaunoTown[] {
  const words = normalizeForSearch(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const starts = (t: KaunoTown) =>
    [t.town, t.registerName ?? ''].some((name) => normalizeForSearch(name).startsWith(words[0]));
  return towns
    .filter((t) => {
      const haystack = normalizeForSearch(`${t.town} ${t.registerName ?? ''} ${t.eldershipName}`);
      return words.every((word) => haystack.includes(word));
    })
    .sort((a, b) => Number(starts(b)) - Number(starts(a)) || a.town.localeCompare(b.town, 'lt'));
}

/** "Kaunas" (and "in Kaunas") in the app's languages, as normalizeForSearch writes it. */
const KAUNAS = ['kaunas', 'kaune', 'kowno', 'каунас'];
/** The word after it that makes it the district; normalizeForSearch drops the breve of "й". */
const DISTRICT = /^(r|raj|rajon\p{L}*|rejon\p{L}*|district|раион\p{L}*)$/u;

/**
 * Whether a search that found nothing was for Kaunas city ("Kaunas", "Kauno m.", "kauno
 * miestas"), which the app doesn't cover: only Kauno r., the district around it, is. The app
 * then says so instead of the general "nothing found". `found` is how many places the search
 * listed, so a town of Kauno r. that matches is shown as usual.
 */
export function isKaunasCitySearch(query: string, found: number): boolean {
  if (found > 0) return false;
  const [first, second, ...rest] = normalizeForSearch(query)
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
  // "Kaunas", "Kaunas m.", "Kowno", "Каунас", but not "Kaunas r." or "Kaunas district".
  if (KAUNAS.includes(first)) return !second || !DISTRICT.test(second);
  // "Kauno m.", "Kauno miestas", "Kauno miesto sav.", also while it is typed ("kauno mies").
  const city = Boolean(second) && ['miestas', 'miesto'].some((word) => word.startsWith(second));
  return first === 'kauno' && city && rest.length <= 1;
}

/**
 * The schedules of one address as one area per waste type: an address can have several
 * containers of a type that are emptied on different days, and every one of them is a pickup.
 * Undefined if the address is no longer in the file.
 */
export function kaunoAreas(index: KaunoIndex, addresses: KaunoAddresses, address: KaunoAddress): Area[] | undefined {
  const positions = addresses.towns[address.town]?.[address.street]?.[address.house];
  if (!positions) return undefined;
  const byKind = new Map<WasteKind, KaunoSchedule[]>();
  for (const position of positions) {
    const schedule = index.areas[position];
    if (schedule) byKind.set(schedule.kind, [...(byKind.get(schedule.kind) ?? []), schedule]);
  }
  return [...byKind].map(([kind, schedules]) => ({
    id: `kauno-${kind}`,
    kind,
    name: [...new Set(schedules.map((s) => s.rule))].join('; '),
    dates: [...new Set(schedules.flatMap((s) => s.dates))].sort(),
    current: true,
  }));
}

/** Where an address saved with a spelling that was merged into another one is now. */
export function kaunoAlias(index: KaunoIndex, addresses: KaunoAddresses, address: KaunoAddress): KaunoAddress | undefined {
  const target = addresses.aliases?.[address.town]?.[address.street]?.[address.house];
  if (!target) return undefined;
  const [eldership, town, street, house] = target;
  const eldershipName = index.elderships.find((e) => e.id === eldership)?.name ?? address.eldershipName;
  return { eldership, eldershipName, town, street, house };
}

/**
 * Downloads what is needed for one address and returns its schedules, with the address as the
 * data now writes it (`address`), which differs from the given one if its spelling was merged.
 */
export async function loadKaunoAddress(
  address: KaunoAddress,
): Promise<{ key: string; areas: Area[]; address: KaunoAddress; generatedAt: string } | undefined> {
  const [index, addresses] = await Promise.all([fetchKaunoIndex(), fetchKaunoAddresses(address.eldership)]);
  const alias = addresses.towns[address.town]?.[address.street]?.[address.house] ? undefined : kaunoAlias(index, addresses, address);
  if (!alias) {
    const areas = kaunoAreas(index, addresses, address);
    return areas && { key: kaunoKey(address), areas, address, generatedAt: index.generatedAt };
  }
  const file = alias.eldership === address.eldership ? addresses : await fetchKaunoAddresses(alias.eldership);
  const areas = kaunoAreas(index, file, alias);
  return areas && { key: kaunoKey(alias), areas, address: alias, generatedAt: index.generatedAt };
}

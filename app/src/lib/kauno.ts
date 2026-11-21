import { KAUNO_URL, SUPPORTED_SCHEMA_VERSION } from './config';
import {
  type Area,
  normalizeForSearch,
  queryWords,
  searchable,
  UnsupportedScheduleError,
  type WasteKind,
} from './schedule';

/**
 * Kauno r. and Kaišiadorių r.: schedules of UAB „Kauno švara“, published per address rather than
 * per settlement (pipeline/src/schedule_pipeline/svara.py). The app downloads the list of towns,
 * then only the address file of the user's eldership, and keeps the schedules of the user's own
 * address. Names and types say "Kauno" because Kauno r. came first; an eldership of another
 * municipality says which (`municipality`).
 */

/** The municipality of an eldership that doesn't name one. */
export const KAUNO_MUNICIPALITY = 'Kauno r.';

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
    /** "Kaišiadorių r."; absent for the elderships of Kauno r. Added later, like registerNames. */
    municipality?: string;
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
  /** "Kaišiadorių r.", or absent for Kauno r. (see municipalityOf). */
  municipality?: string;
};

/** The municipality of a town, as shown next to it: "Kauno r." or "Kaišiadorių r.". */
export const municipalityOf = (town: Pick<KaunoTown, 'municipality'>) => town.municipality ?? KAUNO_MUNICIPALITY;

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
      return {
        eldership: e.id,
        eldershipName: e.name,
        town,
        ...(registerName ? { registerName } : {}),
        ...(e.municipality ? { municipality: e.municipality } : {}),
      };
    }),
  );
}

const townSearch = searchable<KaunoTown>(
  (t) => t.town,
  (t) => [t.town, t.registerName ?? ''],
  (t) => `${t.town} ${t.registerName ?? ''} ${t.eldershipName}`,
);

/**
 * Towns matching every word of the query, names that start with it first. The file writes the
 * genitive ("Akademijos mstl."), so the town's name in the Address Register ("Akademija") is
 * searched too and counts as a name.
 */
export function searchKaunoTowns(towns: KaunoTown[], query: string): KaunoTown[] {
  return queryWords(query).length ? townSearch(towns, query) : [];
}

/**
 * Cities next to a covered district that aren't covered themselves: their names (and "in ...")
 * in the app's languages, and the genitive of "Kauno m.", as normalizeForSearch writes them
 * (it drops the breve of "й" and the dot of the Polish "ż"; the Polish "ł" stays).
 * `district`: only some schedules of the district are covered, so it isn't in the list of
 * covered areas, and a search for the district gets the city's hint too, which says so.
 */
type City = { names: string[]; genitive: string; district?: boolean };
const CITIES = {
  kaunas: { names: ['kaunas', 'kaune', 'kowno', 'каунас'], genitive: 'kauno' },
  klaipeda: { names: ['klaipeda', 'klaipedoje', 'kłajpeda', 'клаипеда'], genitive: 'klaipedos' },
  siauliai: { names: ['siauliai', 'siauliuose', 'szawle', 'шяуляи', 'шауляи', 'шавли'], genitive: 'siauliu' },
  alytus: { names: ['alytus', 'alytuje', 'olita', 'алитус'], genitive: 'alytaus' },
  // Panevėžio r.: packaging and glass only (its mixed waste schedule isn't readable).
  panevezys: { names: ['panevezys', 'panevezyje', 'poniewiez', 'паневежис'], genitive: 'panevezio', district: true },
} satisfies Record<string, City>;
export type UncoveredCity = keyof typeof CITIES;
/** The word after it that makes it the district. */
const DISTRICT = /^(r|raj|rajon\p{L}*|rejon\p{L}*|district|раион\p{L}*)$/u;

/**
 * Whether a search was for a city the app doesn't cover, only the district around it: Kaunas,
 * Klaipėda, Šiauliai, Alytus or Panevėžys ("Kaunas", "Kauno m.", "klaipedos miestas", "Szawle").
 * The app then says so: instead of the general "nothing found", or above the places it found,
 * since a village can have the city's name (Alytus in Alovės sen., Šiauliai in Veliuonos sen.).
 * For Panevėžys also the district ("Panevėžio r."), whose hint says what of it is covered, and
 * "Panevėžio" alone: the hint then shows above the villages of Panevėžio sen., in that district.
 */
export function uncoveredCitySearch(query: string): UncoveredCity | undefined {
  const [first, second, ...rest] = normalizeForSearch(query)
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
  for (const [city, { names, genitive, district }] of Object.entries(CITIES) as [UncoveredCity, City][]) {
    const isDistrict = Boolean(second) && DISTRICT.test(second);
    // "Kaunas", "Kaunas m.", "Kowno", "Каунас", but not "Kaunas r." or "Kaunas district".
    if (names.includes(first)) return !isDistrict || district ? city : undefined;
    // "Kauno m.", "Kauno miestas", "Kauno miesto sav.", also while it is typed ("kauno mies").
    const isCity = Boolean(second) && ['miestas', 'miesto'].some((word) => word.startsWith(second));
    if (first === genitive && (isCity || (district && (!second || isDistrict))) && rest.length <= 1) return city;
  }
  return undefined;
}

/** {@link uncoveredCitySearch} for Kaunas. */
export const isKaunasCitySearch = (query: string) => uncoveredCitySearch(query) === 'kaunas';

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

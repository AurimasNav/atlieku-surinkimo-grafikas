import { KAUNO_SOURCE_PAGE_URL, SOURCE_PAGE_URL } from './config';
import { customDates, type CustomSchedule } from './custom-schedule';
import { parseIsoDate } from './dates';
import { type KaunoAddress, kaunoKey } from './kauno';
import { type Area, isCurrent, type Location, personalsOf, type ScheduleData, WASTE_KINDS, type WasteKind } from './schedule';

/** What the user picked, stored on the phone. */
export type Place = {
  /** Location id from schedule.json, absent if the user picked rows by hand. */
  locationId?: string;
  /** Street key; absent if the location has no streets or the street isn't listed. */
  street?: string;
  /** An address in Kauno r. (UAB „Kauno švara“) instead of a location from schedule.json. */
  kauno?: KaunoAddress;
  /** Per-kind answers: an area id, or null for "I don't have this container". */
  choices: Partial<Record<WasteKind, string | null>>;
  /** Schedules the user set up themselves; they take priority over the official data. */
  custom?: Partial<Record<WasteKind, CustomSchedule>>;
};

/** The waste types every place is asked about, and those of Kauno švara's addresses in Kauno r. */
const BASE_KINDS: WasteKind[] = ['household', 'packaging', 'glass'];
const KAUNO_KINDS: WasteKind[] = ['household', 'food', 'green'];

/** Id of the synthetic area a custom schedule turns into (stable, for reminders). */
export const customAreaId = (kind: WasteKind) => `custom-${kind}`;

export function isCustomArea(area: Area): boolean {
  return area.id.startsWith('custom-');
}

export type KindStatus =
  | { status: 'ok'; area: Area; custom?: boolean }
  /** Not collected here according to the schedules, or the user said they don't have it. */
  | { status: 'none'; skipped?: boolean }
  /** Several rows could apply; ask the user to pick one of these. */
  | { status: 'choose'; candidates: Area[] }
  /** Nothing to go on: the location vanished from the data and no choice was made. */
  | { status: 'missing' };

export type Resolved = {
  location?: Location;
  kinds: Record<WasteKind, KindStatus>;
  /** The areas reminders and the home screen use. */
  areas: Area[];
};

function rowsFor(location: Location | undefined, street: string | undefined, kind: WasteKind): string[] | null {
  const schedule = location?.schedule?.[kind];
  if (!schedule) return null;
  if (street && schedule.streets?.[street]) return schedule.streets[street];
  if (schedule.area) return [schedule.area];
  if (schedule.candidates) return schedule.candidates;
  // Split by street, but this street isn't listed (or wasn't given): any of those rows.
  return [...new Set(Object.values(schedule.streets ?? {}).flat())];
}

export function resolvePlace(data: ScheduleData | null, place: Place | null, today: string): Resolved {
  const kinds = {} as Record<WasteKind, KindStatus>;
  const location = data?.locations?.find((loc) => loc.id === place?.locationId);
  const byId = new Map(data?.areas.map((area) => [area.id, area]));
  const current = (id: string) => {
    const area = byId.get(id);
    return area && isCurrent(area, today) ? area : undefined;
  };
  // The schedules of a Kauno r. address, if the saved ones belong to this address.
  const key = place?.kauno && kaunoKey(place.kauno);
  const personal = key ? personalsOf(data).find((p) => p.key === key)?.areas : undefined;

  for (const kind of WASTE_KINDS) {
    const custom = place?.custom?.[kind];
    if (custom) {
      const dates = customDates(custom, parseIsoDate(today));
      kinds[kind] = { status: 'ok', custom: true, area: { id: customAreaId(kind), kind, name: '', dates } };
      continue;
    }
    const choice = place?.choices[kind];
    if (choice === null) {
      kinds[kind] = { status: 'none', skipped: true };
      continue;
    }
    if (place?.kauno) {
      const area = personal?.find((a) => a.kind === kind);
      kinds[kind] = area ? { status: 'ok', area } : { status: 'none' };
      continue;
    }
    // Food and green waste have schedules in few places (Kauno r., Mažeikiai town): nothing to
    // ask about elsewhere.
    if (!BASE_KINDS.includes(kind) && !location?.schedule?.[kind] && !choice) {
      kinds[kind] = { status: 'none' };
      continue;
    }
    const chosen = choice ? current(choice) : undefined;
    if (chosen) {
      kinds[kind] = { status: 'ok', area: chosen };
      continue;
    }
    if (!data || (place?.locationId && !location) || (!place?.locationId && choice)) {
      // The location or the hand-picked row disappeared in a newer schedule.
      kinds[kind] = { status: data ? 'missing' : 'none' };
      continue;
    }
    const ids = rowsFor(location, place?.street, kind);
    const candidates = (ids ?? []).map(current).filter((a): a is Area => Boolean(a));
    if (candidates.length === 1) kinds[kind] = { status: 'ok', area: candidates[0] };
    else if (candidates.length > 1) kinds[kind] = { status: 'choose', candidates };
    else kinds[kind] = { status: 'none' };
  }

  const areas = WASTE_KINDS.flatMap((kind) => {
    const status = kinds[kind];
    return status.status === 'ok' ? [status.area] : [];
  });
  return { location, kinds, areas };
}

/** Kinds that still need an answer from the user, in onboarding order. */
export function pendingKinds(resolved: Resolved): WasteKind[] {
  return WASTE_KINDS.filter((kind) => ['choose', 'missing'].includes(resolved.kinds[kind].status));
}

/** True when the rows differ only by housing type, so we can ask "house or apartment?". */
export function isHousingChoice(candidates: Area[]): boolean {
  const groups = new Set(candidates.map((a) => a.group));
  return groups.size === 2 && groups.has('Individualūs namai') && groups.has('Daugiabučiai namai');
}


/**
 * The waste types to show for a place: its provider's, plus any other the place has a schedule
 * for (a few Kauno r. addresses have glass, Mažeikiai has food waste; own schedules can be set
 * for any type).
 */
export function visibleKinds(place: Place | null, resolved: Resolved): WasteKind[] {
  const usual = place?.kauno ? KAUNO_KINDS : BASE_KINDS;
  const here = (kind: WasteKind) => Boolean(resolved.location?.schedule?.[kind]);
  return WASTE_KINDS.filter(
    (kind) => usual.includes(kind) || here(kind) || resolved.kinds[kind].status === 'ok',
  );
}

/** Name and detail line of the place, for headings: "Ganyklų g. 2" / "Karkiškių k. · Ringaudų sen.". */
export function placeLabel(place: Place | null, resolved: Resolved): { name?: string; detail?: string } {
  if (place?.kauno) {
    const { town, street, house, eldershipName } = place.kauno;
    const address = [street, house].filter(Boolean).join(' ');
    return {
      name: address || town,
      detail: [address ? town : '', eldershipName].filter(Boolean).join(' · '),
    };
  }
  const location = resolved.location;
  if (!location) return {};
  const street = location.streets?.find(([key]) => key === place?.street)?.[1];
  return { name: location.name, detail: [street, `${location.district} sen.`].filter(Boolean).join(' · ') };
}

/**
 * The official schedule page of the company that serves the place: Kauno švara for a Kauno r.
 * address, otherwise the `provider` of the location (or of a row picked by hand) as listed in
 * the data. Places without one are Nemenčinės komunalininkas', as in data published before.
 */
export function sourcePageUrl(data: ScheduleData | null, place: Place | null, resolved: Resolved): string {
  if (place?.kauno) return KAUNO_SOURCE_PAGE_URL;
  const id = resolved.location?.provider ?? resolved.areas.find((area) => !isCustomArea(area))?.provider;
  const url = data?.providers?.find((provider) => provider.id === id)?.url;
  return url?.startsWith('https://') ? url : SOURCE_PAGE_URL;
}

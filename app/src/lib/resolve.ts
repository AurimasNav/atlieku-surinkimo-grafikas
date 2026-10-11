import { type Area, isCurrent, type Location, type ScheduleData, WASTE_KINDS, type WasteKind } from './schedule';

/** What the user picked, stored on the phone. */
export type Place = {
  /** Location id from schedule.json, absent if the user picked rows by hand. */
  locationId?: string;
  /** Street key; absent if the location has no streets or the street isn't listed. */
  street?: string;
  /** Per-kind answers: an area id, or null for "I don't have this container". */
  choices: Partial<Record<WasteKind, string | null>>;
};

export type KindStatus =
  | { status: 'ok'; area: Area }
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

  for (const kind of WASTE_KINDS) {
    const choice = place?.choices[kind];
    if (choice === null) {
      kinds[kind] = { status: 'none', skipped: true };
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

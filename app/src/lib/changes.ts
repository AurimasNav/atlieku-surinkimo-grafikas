import type { TFunction } from 'i18next';

import { toIsoDate } from './dates';
import { shortDayDate } from './format';
import { isCustomArea } from './resolve';
import { type Area, WASTE_KINDS, type WasteKind } from './schedule';

/** How far ahead a changed date is worth an alert: later ones are seen in good time anyway. */
export const CHANGE_WINDOW_DAYS = 21;

/** A pickup that moved (`from` and `to`), was cancelled (`from`) or added (`to`). */
export type PickupChange = { kind: WasteKind; from?: string; to?: string };

/** Official pickup dates by waste type; the user's own schedules don't change on a refresh. */
export function officialDates(areas: Area[]): Partial<Record<WasteKind, string[]>> {
  const dates: Partial<Record<WasteKind, Set<string>>> = {};
  for (const area of areas) {
    if (isCustomArea(area)) continue;
    const set = (dates[area.kind] ??= new Set());
    for (const date of area.dates) set.add(date);
  }
  return Object.fromEntries(Object.entries(dates).map(([kind, set]) => [kind, [...set].sort()]));
}

/**
 * What changed in the coming weeks between two versions of the user's schedule. A newly
 * published period adds dates after the old schedule's last one without anything having
 * changed, and a waste type the user didn't have before isn't a change either.
 */
export function pickupChanges(
  before: Partial<Record<WasteKind, string[]>>,
  after: Partial<Record<WasteKind, string[]>>,
  now: Date,
): PickupChange[] {
  const today = toIsoDate(now);
  const until = new Date(now);
  until.setDate(until.getDate() + CHANGE_WINDOW_DAYS);
  const last = toIsoDate(until);
  const changes: PickupChange[] = [];

  for (const kind of WASTE_KINDS) {
    const old = before[kind];
    const fresh = after[kind];
    if (!old?.length || !fresh) continue;
    const covered = old.at(-1)!;
    const inWindow = (date: string) => date >= today && date <= last;
    const oldSet = new Set(old);
    const freshSet = new Set(fresh);
    const removed = old.filter((date) => inWindow(date) && !freshSet.has(date));
    const added = fresh.filter((date) => inWindow(date) && !oldSet.has(date));
    // Pair them in order: one date gone and one new is a pickup that moved, even past the end
    // of the old schedule. A new date without a pair only counts within the old schedule.
    const moved = Math.min(removed.length, added.length);
    for (let i = 0; i < moved; i++) changes.push({ kind, from: removed[i], to: added[i] });
    for (const from of removed.slice(moved)) changes.push({ kind, from });
    for (const to of added.slice(moved)) if (to <= covered) changes.push({ kind, to });
  }
  return changes;
}

/** Changes still worth showing: their dates haven't all passed. */
export const activeChanges = (changes: PickupChange[], today: string) =>
  changes.filter((change) => [change.from, change.to].some((date) => date && date >= today));

/** One line per change: "Glass: Thu, December 4 → Sat, December 6". */
export function describeChanges(changes: PickupChange[], t: TFunction, lang: string): string[] {
  return changes.map((change) => {
    const kind = t(`kinds.${change.kind}`);
    if (change.from && change.to) {
      return t('changes.moved', { kind, from: shortDayDate(lang, change.from), to: shortDayDate(lang, change.to) });
    }
    return change.from
      ? t('changes.cancelled', { kind, date: shortDayDate(lang, change.from) })
      : t('changes.added', { kind, date: shortDayDate(lang, change.to!) });
  });
}

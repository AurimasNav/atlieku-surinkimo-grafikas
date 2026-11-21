import { daysBetween, parseIsoDate, toIsoDate } from './dates';
import type { Area, WasteKind } from './schedule';
import { WASTE_KINDS } from './schedule';

/**
 * iOS keeps at most 64 pending notifications per app and silently drops the rest.
 * Leave headroom for the final "open the app to refresh" reminder.
 */
export const MAX_PICKUP_REMINDERS = 60;

/** How many reminders one pickup can have, e.g. the evening before and again that morning. */
export const MAX_REMINDER_TIMES = 3;

export type ReminderTime = {
  /** 1 = the evening before, 0 = the morning of the pickup. */
  daysBefore: 0 | 1;
  hour: number;
  minute: number;
};

export type ReminderSettings = {
  /** The reminders for every pickup, unless its waste type has its own (`kinds`). */
  times: ReminderTime[];
  /** Waste types with their own reminders; an empty list turns that type's reminders off. */
  kinds?: Partial<Record<WasteKind, ReminderTime[]>>;
};

/** What the user did with reminders that already went off ("Bins are out", "Later"). */
export type ReminderActions = {
  /** Pickups the user has dealt with, as `date|kind`: their remaining reminders are skipped. */
  done: string[];
  /** Reminders put off by the user, keyed by the notification they came from. */
  snoozed: Snooze[];
};

export type Snooze = { id: string; fireAt: string; pickup: Pickup };

export type Pickup = { date: string; kinds: WasteKind[] };

export type PlannedReminder =
  | { type: 'pickup'; fireAt: Date; pickup: Pickup }
  | { type: 'refresh'; fireAt: Date };

export const NO_ACTIONS: ReminderActions = { done: [], snoozed: [] };

export const doneKey = (date: string, kind: WasteKind) => `${date}|${kind}`;

/** The reminders that apply to one waste type. */
export const timesFor = (settings: ReminderSettings, kind: WasteKind): ReminderTime[] =>
  settings.kinds?.[kind] ?? settings.times;

/** Earliest first: the evening before comes before that morning. */
export function sortTimes(times: ReminderTime[]): ReminderTime[] {
  return [...times].sort((a, b) => b.daysBefore - a.daysBefore || a.hour - b.hour || a.minute - b.minute);
}

/** Merges the selected areas' dates into one list of pickup days, earliest first. */
export function upcomingPickups(selected: Area[], from: Date): Pickup[] {
  const today = toIsoDate(from);
  const byDate = new Map<string, Set<WasteKind>>();
  for (const area of selected) {
    for (const date of area.dates) {
      if (date < today) continue;
      if (!byDate.has(date)) byDate.set(date, new Set());
      byDate.get(date)!.add(area.kind);
    }
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, kinds]) => ({
      date,
      kinds: WASTE_KINDS.filter((kind) => kinds.has(kind)),
    }));
}

/** When a reminder for a pickup on `date` goes off. */
export function fireTime(date: string, time: ReminderTime): Date {
  const fireAt = parseIsoDate(date);
  fireAt.setDate(fireAt.getDate() - time.daysBefore);
  fireAt.setHours(time.hour, time.minute, 0, 0);
  return fireAt;
}

/** 0 when the reminder goes off on the pickup day ("Today"), 1 the day before ("Tomorrow"). */
export const daysAhead = (fireAt: Date, date: string) => daysBetween(fireAt, parseIsoDate(date));

/**
 * Decides which notifications to schedule. Pure, so it can be unit tested; the caller
 * hands the result to the OS. Waste types reminded at the same moment share one notification.
 */
export function planReminders(
  selected: Area[],
  settings: ReminderSettings,
  now: Date,
  actions: ReminderActions = NO_ACTIONS,
): PlannedReminder[] {
  const done = new Set(actions.done);
  const byMoment = new Map<string, { fireAt: Date; pickup: Pickup }>();
  const add = (fireAt: Date, date: string, kinds: WasteKind[]) => {
    const open = kinds.filter((kind) => !done.has(doneKey(date, kind)));
    if (fireAt <= now || !open.length) return;
    const key = `${fireAt.getTime()}|${date}`;
    const known = byMoment.get(key);
    const merged = new Set([...(known?.pickup.kinds ?? []), ...open]);
    byMoment.set(key, { fireAt, pickup: { date, kinds: WASTE_KINDS.filter((kind) => merged.has(kind)) } });
  };

  for (const pickup of upcomingPickups(selected, now)) {
    for (const kind of pickup.kinds) {
      for (const time of timesFor(settings, kind)) add(fireTime(pickup.date, time), pickup.date, [kind]);
    }
  }
  for (const snooze of actions.snoozed) add(new Date(snooze.fireAt), snooze.pickup.date, snooze.pickup.kinds);

  const planned: PlannedReminder[] = [...byMoment.values()]
    .sort((a, b) => a.fireAt.getTime() - b.fireAt.getTime())
    .slice(0, MAX_PICKUP_REMINDERS)
    .map(({ fireAt, pickup }) => ({ type: 'pickup', fireAt, pickup }));

  // After the last known pickup, nudge the user to open the app so it can fetch the next
  // schedule period, in case background refresh never ran.
  const last = planned.at(-1);
  if (last) {
    const fireAt = new Date(last.fireAt);
    fireAt.setDate(fireAt.getDate() + 1);
    planned.push({ type: 'refresh', fireAt });
  }
  return planned;
}

/** Drops what can no longer matter: pickups before today and snoozes that went off. */
export function pruneActions(actions: ReminderActions, now: Date): ReminderActions {
  const today = toIsoDate(now);
  return {
    done: actions.done.filter((key) => key.slice(0, 10) >= today),
    snoozed: actions.snoozed.filter((snooze) => new Date(snooze.fireAt) > now),
  };
}

/** Snoozing an evening reminder waits an hour; that morning there's only time for 15 minutes. */
export const snoozeMinutes = (daysAheadOfPickup: number) => (daysAheadOfPickup >= 1 ? 60 : 15);

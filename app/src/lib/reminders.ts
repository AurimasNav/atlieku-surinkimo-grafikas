import { parseIsoDate, toIsoDate } from './dates';
import type { Area, WasteKind } from './schedule';
import { WASTE_KINDS } from './schedule';

/**
 * iOS keeps at most 64 pending notifications per app and silently drops the rest.
 * Leave headroom for the final "open the app to refresh" reminder.
 */
export const MAX_PICKUP_REMINDERS = 60;

export type ReminderSettings = {
  /** 1 = the evening before, 0 = the morning of the pickup. */
  daysBefore: 0 | 1;
  hour: number;
  minute: number;
};

export type Pickup = { date: string; kinds: WasteKind[] };

export type PlannedReminder =
  | { type: 'pickup'; fireAt: Date; pickup: Pickup }
  | { type: 'refresh'; fireAt: Date };

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

/**
 * Decides which notifications to schedule. Pure, so it can be unit tested; the caller
 * hands the result to the OS. Pickups on the same day share one notification.
 */
export function planReminders(
  selected: Area[],
  settings: ReminderSettings,
  now: Date,
): PlannedReminder[] {
  const planned: PlannedReminder[] = [];
  for (const pickup of upcomingPickups(selected, now)) {
    const fireAt = parseIsoDate(pickup.date);
    fireAt.setDate(fireAt.getDate() - settings.daysBefore);
    fireAt.setHours(settings.hour, settings.minute, 0, 0);
    if (fireAt <= now) continue;
    planned.push({ type: 'pickup', fireAt, pickup });
    if (planned.length === MAX_PICKUP_REMINDERS) break;
  }

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

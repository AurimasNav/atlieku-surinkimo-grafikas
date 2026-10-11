import { parseIsoDate, toIsoDate } from './dates';

/** A schedule the user sets up themselves, for places the official data doesn't cover. */
export type CustomSchedule = {
  /** A known pickup date (YYYY-MM-DD); later dates are counted from it. */
  start: string;
  every: number;
  /**
   * 'week': every N weeks on the same weekday.
   * 'month': every N months on the same weekday position as `start`, e.g. the 2nd Tuesday
   * (the 5th occurrence becomes "the last"), because collections follow weekdays, not dates.
   */
  unit: 'week' | 'month';
};

export const REPEAT_OPTIONS: { every: number; unit: CustomSchedule['unit'] }[] = [
  { every: 1, unit: 'week' },
  { every: 2, unit: 'week' },
  { every: 3, unit: 'week' },
  { every: 4, unit: 'week' },
  { every: 1, unit: 'month' },
  { every: 2, unit: 'month' },
  { every: 3, unit: 'month' },
];

/** About a year ahead: plenty for the reminder window, cheap to compute. */
const HORIZON_DAYS = 400;

function nthWeekdayOfMonth(year: number, month: number, weekday: number, nth: number): Date {
  if (nth >= 5) {
    // "Last" occurrence: step back from the month's last day.
    const last = new Date(year, month + 1, 0);
    last.setDate(last.getDate() - ((last.getDay() - weekday + 7) % 7));
    return last;
  }
  const first = new Date(year, month, 1);
  const offset = (weekday - first.getDay() + 7) % 7;
  return new Date(year, month, 1 + offset + (nth - 1) * 7);
}

/** Pickup dates from `from` (inclusive) for about a year, as YYYY-MM-DD strings. */
export function customDates(schedule: CustomSchedule, from: Date): string[] {
  const start = parseIsoDate(schedule.start);
  const fromDay = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const until = new Date(fromDay);
  until.setDate(until.getDate() + HORIZON_DAYS);
  const dates: string[] = [];

  if (schedule.unit === 'week') {
    const step = schedule.every * 7;
    const day = new Date(start);
    // Jump close to `from` without looping day by day through the past.
    if (day < fromDay) {
      const behind = Math.floor((fromDay.getTime() - day.getTime()) / 86_400_000 / step) * step;
      day.setDate(day.getDate() + behind);
    }
    while (day <= until) {
      if (day >= fromDay) dates.push(toIsoDate(day));
      day.setDate(day.getDate() + step);
    }
    return dates;
  }

  const weekday = start.getDay();
  const nth = Math.ceil(start.getDate() / 7);
  for (let i = 0; ; i += schedule.every) {
    const date = nthWeekdayOfMonth(start.getFullYear(), start.getMonth() + i, weekday, nth);
    if (date > until) break;
    if (date >= fromDay) dates.push(toIsoDate(date));
  }
  return dates;
}

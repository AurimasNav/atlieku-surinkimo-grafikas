import { useTranslation } from 'react-i18next';

import { daysBetween, parseIsoDate } from './dates';
import type { ReminderSettings } from './reminders';

/** Reminder times offered in setup and settings. Bins must be out by 7:00 on the day. */
export const REMINDER_TIMES: Record<ReminderSettings['daysBefore'], [number, number][]> = {
  1: [
    [17, 0],
    [18, 0],
    [19, 0],
    [20, 0],
    [21, 0],
  ],
  0: [
    [5, 30],
    [6, 0],
    [6, 30],
  ],
};

export const formatTime = (hour: number, minute: number) => `${hour}:${String(minute).padStart(2, '0')}`;

const capitalize = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);

/** Locale-aware date helpers bound to the current app language. */
export function useDateFormat() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const format = (iso: string, options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(lang, options).format(parseIsoDate(iso));

  return {
    /** "Thursday, October 15" */
    long: (iso: string) => capitalize(format(iso, { weekday: 'long', month: 'long', day: 'numeric' })),
    /** "Oct 15" */
    short: (iso: string) => format(iso, { month: 'short', day: 'numeric' }),
    /** "Thu" */
    weekday: (iso: string) => capitalize(format(iso, { weekday: 'short' })).replace('.', ''),
    /** "15" */
    day: (iso: string) => String(parseIsoDate(iso).getDate()),
    /** "October 2026" style month heading */
    month: (iso: string) => capitalize(format(iso, { month: 'long', year: 'numeric' })),
    /** "Today", "Tomorrow", "In 5 days" */
    relative: (iso: string) => {
      const days = daysBetween(new Date(), parseIsoDate(iso));
      if (days === 0) return t('home.today');
      if (days === 1) return t('home.tomorrow');
      return t('home.inDays', { count: days });
    },
  };
}

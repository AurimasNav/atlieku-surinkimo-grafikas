import type { TFunction } from 'i18next';

import { daysBetween, parseIsoDate, toIsoDate } from '@/lib/dates';
import { capitalize, longDate } from '@/lib/format';
import { doneKey, upcomingPickups } from '@/lib/reminders';
import { placeLabel, resolvePlace, type Place } from '@/lib/resolve';
import type { ScheduleData, WasteKind } from '@/lib/schedule';

/** What the home screen widget shows: the next pickup of the place shown in the app. */
export type WidgetModel =
  | {
      state: 'pickup';
      place?: string;
      /** "Tomorrow", "In 3 days" */
      when: string;
      /** "Thursday, December 4" */
      date: string;
      kinds: { kind: WasteKind; name: string }[];
      /** The user pressed "Bins are out" for every waste type of it. */
      done: boolean;
    }
  | { state: 'empty'; place?: string; message: string };

export function widgetModel({
  data,
  place,
  placeId,
  placeName,
  done,
  now,
  t,
  lang,
}: {
  data: ScheduleData | null;
  place: Place | null;
  placeId: string;
  placeName?: string;
  done: string[];
  now: Date;
  t: TFunction;
  lang: string;
}): WidgetModel {
  if (!place) return { state: 'empty', message: t('widget.choosePlace') };
  const resolved = resolvePlace(data, place, toIsoDate(now));
  const name = placeName ?? placeLabel(place, resolved).name;
  const [next] = upcomingPickups(resolved.areas, now);
  if (!next) return { state: 'empty', place: name, message: t('widget.nothing') };
  const days = daysBetween(now, parseIsoDate(next.date));
  return {
    state: 'pickup',
    place: name,
    when: days === 0 ? t('home.today') : days === 1 ? t('home.tomorrow') : t('home.inDays', { count: days }),
    date: capitalize(longDate(lang, next.date)),
    kinds: next.kinds.map((kind) => ({ kind, name: t(`kinds.${kind}`) })),
    done: next.kinds.every((kind) => done.includes(doneKey(next.date, kind, placeId))),
  };
}

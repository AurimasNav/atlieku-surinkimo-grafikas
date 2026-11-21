import type { SavedPlace } from '@/store/settings';

import { toIsoDate } from './dates';
import { placeLabel, resolvePlace } from './resolve';
import type { ScheduleData } from './schedule';

/**
 * What to call a saved place: the name the user gave it, else its settlement or address.
 * Undefined for a place with only the user's own schedules and no name.
 */
export function placeName(saved: Pick<SavedPlace, 'name' | 'place'>, data: ScheduleData | null, now: Date): string | undefined {
  if (saved.name) return saved.name;
  return placeLabel(saved.place, resolvePlace(data, saved.place, toIsoDate(now))).name;
}

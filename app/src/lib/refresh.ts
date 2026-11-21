import { useSchedule } from '@/store/schedule';
import { allPlaces, useSettings } from '@/store/settings';

import { officialDates, type PickupChange, pickupChanges } from './changes';
import { toIsoDate } from './dates';
import { notifyScheduleChanges } from './notifications';
import { placeName } from './places';
import { resolvePlace } from './resolve';

/**
 * Downloads the schedule (useSchedule.refresh) and, if the coming pickups of a saved place
 * moved, were cancelled or added, keeps the changes for the home screen and sends a
 * notification. Changes of places other than the one shown say which place they're for.
 */
export async function refreshSchedule(now = new Date()): Promise<boolean> {
  const today = toIsoDate(now);
  const snapshot = () => {
    const data = useSchedule.getState().data;
    return new Map(allPlaces(useSettings.getState()).map((saved) => [saved.id, officialDates(resolvePlace(data, saved.place, today).areas)]));
  };
  const hadData = Boolean(useSchedule.getState().data);
  const before = snapshot();
  const changed = await useSchedule.getState().refresh();
  if (!changed || !hadData) return changed;
  const after = snapshot();
  const { placeId } = useSettings.getState();
  const data = useSchedule.getState().data;
  const changes: PickupChange[] = allPlaces(useSettings.getState()).flatMap((saved) => {
    const old = before.get(saved.id);
    if (!old) return [];
    const found = pickupChanges(old, after.get(saved.id) ?? {}, now);
    const name = saved.id === placeId ? undefined : placeName(saved, data, now);
    return name ? found.map((change) => ({ ...change, place: name })) : found;
  });
  if (changes.length) {
    useSchedule.getState().addChanges(changes);
    await notifyScheduleChanges(changes).catch(() => {});
  }
  return changed;
}

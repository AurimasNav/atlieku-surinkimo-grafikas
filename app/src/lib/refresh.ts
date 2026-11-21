import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';

import { officialDates, pickupChanges } from './changes';
import { toIsoDate } from './dates';
import { notifyScheduleChanges } from './notifications';
import { resolvePlace } from './resolve';

/**
 * Downloads the schedule (useSchedule.refresh) and, if the user's coming pickups moved, were
 * cancelled or added, keeps the changes for the home screen and sends a notification.
 */
export async function refreshSchedule(now = new Date()): Promise<boolean> {
  const today = toIsoDate(now);
  const dates = () => officialDates(resolvePlace(useSchedule.getState().data, useSettings.getState().place, today).areas);
  const hadData = Boolean(useSchedule.getState().data);
  const before = dates();
  const changed = await useSchedule.getState().refresh();
  if (!changed || !hadData) return changed;
  const changes = pickupChanges(before, dates(), now);
  if (changes.length) {
    useSchedule.getState().addChanges(changes);
    await notifyScheduleChanges(changes).catch(() => {});
  }
  return changed;
}

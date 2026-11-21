import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import i18n, { resolveLanguage } from '@/i18n';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';

import { toIsoDate } from './dates';
import { buildIcs } from './ics';
import { timesFor, upcomingPickups } from './reminders';
import { resolvePlace } from './resolve';

export const canExportCalendar = Platform.OS !== 'web';

/**
 * Writes the coming pickups to a calendar file and opens the share sheet, so the user can add
 * them to their calendar app. A snapshot: the calendar doesn't follow later schedule changes.
 * Returns false when there's nothing to export or sharing isn't available.
 */
export async function exportCalendar(now = new Date()): Promise<boolean> {
  if (!canExportCalendar || !(await Sharing.isAvailableAsync())) return false;
  const { place, reminder, language } = useSettings.getState();
  const pickups = upcomingPickups(resolvePlace(useSchedule.getState().data, place, toIsoDate(now)).areas, now);
  if (!pickups.length) return false;
  const t = i18n.getFixedT(resolveLanguage(language));
  const ics = buildIcs({
    pickups,
    kindName: (kind) => t(`kinds.${kind}`),
    timesFor: (kind) => timesFor(reminder, kind),
    description: t('notifications.body'),
    now,
  });
  const file = new File(Paths.cache, 'siuksliaveze.ics');
  if (file.exists) file.delete();
  file.create();
  await file.write(ics);
  await Sharing.shareAsync(file.uri, {
    mimeType: 'text/calendar',
    UTI: 'com.apple.ical.ics',
    dialogTitle: t('settings.exportCalendar'),
  });
  return true;
}

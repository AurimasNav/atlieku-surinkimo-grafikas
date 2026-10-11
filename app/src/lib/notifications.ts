import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import i18n, { resolveLanguage } from '@/i18n';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';

import { toIsoDate } from './dates';
import { planReminders } from './reminders';
import { resolvePlace } from './resolve';

const CHANNEL_ID = 'pickup-reminders';
const supported = Platform.OS !== 'web';

export async function configureNotifications(): Promise<void> {
  if (!supported) return;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
  // Android 13+ only shows the permission prompt once a channel exists.
  await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
    name: i18n.t('notifications.channelName'),
    importance: Notifications.AndroidImportance.HIGH,
  });
}

export async function hasNotificationPermission(): Promise<boolean> {
  if (!supported) return false;
  const settings = await Notifications.getPermissionsAsync();
  return settings.granted || settings.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;
}

export async function requestNotificationPermission(): Promise<boolean> {
  if (!supported) return false;
  if (await hasNotificationPermission()) return true;
  const result = await Notifications.requestPermissionsAsync({
    ios: { allowAlert: true, allowSound: true, allowBadge: false },
  });
  return result.granted;
}

/**
 * Replaces all scheduled reminders with a fresh plan from the saved schedule and settings.
 * Call after the schedule or any setting changes; it's cheap and idempotent.
 */
export async function syncReminders(now = new Date()): Promise<number> {
  if (!supported) return 0;
  const { data } = useSchedule.getState();
  const { place, reminder, language } = useSettings.getState();
  const t = i18n.getFixedT(resolveLanguage(language));
  const plan = planReminders(resolvePlace(data, place, toIsoDate(now)).areas, reminder, now);

  await Notifications.cancelAllScheduledNotificationsAsync();
  if (!(await hasNotificationPermission())) return 0;

  for (const item of plan) {
    const content =
      item.type === 'pickup'
        ? {
            title: t(reminder.daysBefore === 1 ? 'notifications.titleTomorrow' : 'notifications.titleToday', {
              kinds: item.pickup.kinds.map((kind) => t(`kinds.${kind}`)).join(', '),
            }),
            body: t('notifications.body'),
          }
        : { title: t('notifications.refreshTitle'), body: t('notifications.refreshBody') };

    await Notifications.scheduleNotificationAsync({
      content,
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DATE,
        date: item.fireAt,
        channelId: CHANNEL_ID,
      },
    });
  }
  return plan.length;
}

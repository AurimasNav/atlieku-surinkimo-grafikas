import * as Notifications from 'expo-notifications';
import type { TFunction } from 'i18next';
import { Platform } from 'react-native';

import i18n, { resolveLanguage } from '@/i18n';
import { useReminderActions } from '@/store/reminder-actions';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';

import { toIsoDate } from './dates';
import { daysAhead, type Pickup, planReminders, snoozeMinutes } from './reminders';
import { resolvePlace } from './resolve';
import { WASTE_KINDS, type WasteKind } from './schedule';

const CHANNEL_ID = 'pickup-reminders';
const supported = Platform.OS !== 'web';

/** Notification buttons. Category ids must not contain ":" or "-". */
const CATEGORY = { evening: 'pickup_evening', morning: 'pickup_morning' } as const;
export const ACTION = { done: 'done', snooze: 'snooze' } as const;

/** What a pickup reminder carries, so its buttons know which pickup they're about. */
type PickupData = { type: 'pickup'; date: string; kinds: WasteKind[] };

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

/** The buttons' labels are part of the category, so they're registered again in the current language. */
async function registerCategories(t: TFunction): Promise<void> {
  const done = { identifier: ACTION.done, buttonTitle: t('notifications.done'), options: { opensAppToForeground: false } };
  const later = (title: string) => ({ identifier: ACTION.snooze, buttonTitle: title, options: { opensAppToForeground: false } });
  await Promise.all([
    Notifications.setNotificationCategoryAsync(CATEGORY.evening, [done, later(t('notifications.snoozeHour'))]),
    Notifications.setNotificationCategoryAsync(CATEGORY.morning, [done, later(t('notifications.snoozeShort'))]),
  ]);
}

/**
 * Replaces all scheduled reminders with a fresh plan from the saved schedule and settings.
 * Call after the schedule or any setting changes; it's cheap and idempotent.
 */
export async function syncReminders(now = new Date()): Promise<number> {
  if (!supported) return 0;
  const { data } = useSchedule.getState();
  const { place, reminder, language } = useSettings.getState();
  useReminderActions.getState().prune(now);
  const { done, snoozed } = useReminderActions.getState();
  const t = i18n.getFixedT(resolveLanguage(language));
  const plan = planReminders(resolvePlace(data, place, toIsoDate(now)).areas, reminder, now, { done, snoozed });

  await Notifications.cancelAllScheduledNotificationsAsync();
  if (!(await hasNotificationPermission())) return 0;
  await registerCategories(t).catch(() => {});

  for (const item of plan) {
    const ahead = item.type === 'pickup' ? daysAhead(item.fireAt, item.pickup.date) : 0;
    const content: Notifications.NotificationContentInput =
      item.type === 'pickup'
        ? {
            title: t(ahead >= 1 ? 'notifications.titleTomorrow' : 'notifications.titleToday', {
              kinds: item.pickup.kinds.map((kind) => t(`kinds.${kind}`)).join(', '),
            }),
            body: t('notifications.body'),
            categoryIdentifier: ahead >= 1 ? CATEGORY.evening : CATEGORY.morning,
            data: { type: 'pickup', date: item.pickup.date, kinds: item.pickup.kinds } satisfies PickupData,
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

function pickupOf(response: Notifications.NotificationResponse): Pickup | undefined {
  const data = response.notification.request.content.data as Partial<PickupData> | undefined;
  if (data?.type !== 'pickup' || typeof data.date !== 'string' || !Array.isArray(data.kinds)) return undefined;
  return { date: data.date, kinds: data.kinds.filter((kind) => (WASTE_KINDS as readonly string[]).includes(kind)) };
}

/**
 * Handles the "Bins are out" and "Later" buttons. Runs in the app, or in the background task
 * when the app is closed (Android), so pressing a button twice or in both places is harmless.
 * Returns whether the response was a button press it handled.
 */
export async function handleReminderAction(response: Notifications.NotificationResponse, now = new Date()): Promise<boolean> {
  const pickup = pickupOf(response);
  if (!pickup || (response.actionIdentifier !== ACTION.done && response.actionIdentifier !== ACTION.snooze)) return false;
  const id = response.notification.request.identifier;
  if (response.actionIdentifier === ACTION.done) {
    useReminderActions.getState().markDone(pickup);
  } else {
    const fireAt = new Date(now.getTime() + snoozeMinutes(daysAhead(now, pickup.date)) * 60_000);
    useReminderActions.getState().snooze(id, fireAt, pickup);
  }
  await Notifications.dismissNotificationAsync(id).catch(() => {});
  await syncReminders(now);
  return true;
}

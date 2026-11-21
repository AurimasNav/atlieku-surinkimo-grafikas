import * as Notifications from 'expo-notifications';
import type { TFunction } from 'i18next';
import { Platform } from 'react-native';

import i18n, { resolveLanguage } from '@/i18n';
import { useReminderActions } from '@/store/reminder-actions';
import { useSchedule } from '@/store/schedule';
import { allPlaces, useSettings } from '@/store/settings';
import { updateWidgets } from '@/widget/update';

import { describeChanges, type PickupChange } from './changes';
import { toIsoDate } from './dates';
import { daysAhead, type Pickup, planReminders, snoozeMinutes } from './reminders';
import { placeName } from './places';
import { resolvePlace } from './resolve';
import { WASTE_KINDS, type WasteKind } from './schedule';

const CHANNEL_ID = 'pickup-reminders';
const supported = Platform.OS !== 'web';

/** Notification buttons. Category ids must not contain ":" or "-". */
const CATEGORY = { evening: 'pickup_evening', morning: 'pickup_morning' } as const;
export const ACTION = { done: 'done', snooze: 'snooze' } as const;

/** What a pickup reminder carries, so its buttons know which pickup they're about. */
type PickupData = { type: 'pickup'; date: string; kinds: WasteKind[]; place?: string };

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
  // The same inputs decide what the home screen widget shows.
  updateWidgets();
  const { data } = useSchedule.getState();
  const settings = useSettings.getState();
  const { reminder, language } = settings;
  useReminderActions.getState().prune(now);
  const { done, snoozed } = useReminderActions.getState();
  const t = i18n.getFixedT(resolveLanguage(language));
  // Every saved place gets reminders; with more than one, each says which place it's for.
  const places = allPlaces(settings).filter((saved) => saved.place);
  const sources = places.map((saved) => ({ place: saved.id, areas: resolvePlace(data, saved.place, toIsoDate(now)).areas }));
  const names = new Map(places.map((saved) => [saved.id, placeName(saved, data, now) ?? t('custom.title')]));
  const plan = planReminders(sources, reminder, now, { done, snoozed });

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
            body:
              places.length > 1 && item.pickup.place
                ? t('notifications.bodyAtPlace', { place: names.get(item.pickup.place) ?? '' })
                : t('notifications.body'),
            categoryIdentifier: ahead >= 1 ? CATEGORY.evening : CATEGORY.morning,
            data: {
              type: 'pickup',
              date: item.pickup.date,
              kinds: item.pickup.kinds,
              ...(item.pickup.place ? { place: item.pickup.place } : {}),
            } satisfies PickupData,
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

/** Tells the user right away that a refresh moved, cancelled or added pickups of theirs. */
export async function notifyScheduleChanges(changes: PickupChange[]): Promise<void> {
  if (!supported || !changes.length || !(await hasNotificationPermission())) return;
  const lang = resolveLanguage(useSettings.getState().language);
  const t = i18n.getFixedT(lang);
  await Notifications.scheduleNotificationAsync({
    content: {
      title: t('notifications.changedTitle'),
      body: describeChanges(changes, t, lang).join('\n'),
      data: { type: 'changes' },
    },
    trigger: { channelId: CHANNEL_ID },
  });
}

function pickupOf(response: Notifications.NotificationResponse): Pickup | undefined {
  const data = response.notification.request.content.data as Partial<PickupData> | undefined;
  if (data?.type !== 'pickup' || typeof data.date !== 'string' || !Array.isArray(data.kinds)) return undefined;
  const kinds = data.kinds.filter((kind) => (WASTE_KINDS as readonly string[]).includes(kind));
  return typeof data.place === 'string' ? { date: data.date, kinds, place: data.place } : { date: data.date, kinds };
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

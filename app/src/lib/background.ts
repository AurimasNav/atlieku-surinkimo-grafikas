import * as BackgroundTask from 'expo-background-task';
import * as Notifications from 'expo-notifications';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';

import { useSchedule } from '@/store/schedule';

import { handleReminderAction, syncReminders } from './notifications';

const TASK_NAME = 'refresh-schedule';
/** Android runs it when a notification button is pressed while the app is closed. */
const NOTIFICATION_TASK_NAME = 'reminder-action';

// Must run at module load (global scope), so the OS can start the task without the UI.
if (Platform.OS !== 'web') {
  TaskManager.defineTask(TASK_NAME, async () => {
    try {
      await useSchedule.getState().refresh();
      // Re-plan even if the data didn't change: it moves the 60-reminder window forward.
      await syncReminders();
      return BackgroundTask.BackgroundTaskResult.Success;
    } catch {
      return BackgroundTask.BackgroundTaskResult.Failed;
    }
  });

  TaskManager.defineTask<Notifications.NotificationTaskPayload>(NOTIFICATION_TASK_NAME, async ({ data }) => {
    if (data && 'actionIdentifier' in data) await handleReminderAction(data).catch(() => {});
  });
}

export async function registerBackgroundRefresh(): Promise<void> {
  if (Platform.OS === 'web') return;
  if (!(await TaskManager.isTaskRegisteredAsync(NOTIFICATION_TASK_NAME))) {
    await Notifications.registerTaskAsync(NOTIFICATION_TASK_NAME).catch(() => {});
  }
  const status = await BackgroundTask.getStatusAsync();
  if (status !== BackgroundTask.BackgroundTaskStatus.Available) return;
  if (await TaskManager.isTaskRegisteredAsync(TASK_NAME)) return;
  // The OS treats this as a minimum; on iOS it decides when the task actually runs.
  await BackgroundTask.registerTaskAsync(TASK_NAME, { minimumInterval: 12 * 60 });
}

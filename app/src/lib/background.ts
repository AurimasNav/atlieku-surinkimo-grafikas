import * as BackgroundTask from 'expo-background-task';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';

import { useSchedule } from '@/store/schedule';

import { syncReminders } from './notifications';

const TASK_NAME = 'refresh-schedule';

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
}

export async function registerBackgroundRefresh(): Promise<void> {
  if (Platform.OS === 'web') return;
  const status = await BackgroundTask.getStatusAsync();
  if (status !== BackgroundTask.BackgroundTaskStatus.Available) return;
  if (await TaskManager.isTaskRegisteredAsync(TASK_NAME)) return;
  // The OS treats this as a minimum; on iOS it decides when the task actually runs.
  await BackgroundTask.registerTaskAsync(TASK_NAME, { minimumInterval: 12 * 60 });
}

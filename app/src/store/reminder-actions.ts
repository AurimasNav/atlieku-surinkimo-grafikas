import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { doneKey, NO_ACTIONS, type Pickup, pruneActions, type ReminderActions } from '@/lib/reminders';
import { storage } from '@/lib/storage';

type ReminderActionsState = ReminderActions & {
  /** "Bins are out": the pickup's remaining reminders are skipped. */
  markDone: (pickup: Pickup) => void;
  /** "Later": the reminder comes back at `fireAt`. One snooze per notification. */
  snooze: (id: string, fireAt: Date, pickup: Pickup) => void;
  prune: (now?: Date) => void;
};

/**
 * Kept apart from the settings: it's written by notification buttons, also while the app is
 * closed (lib/background.ts), and only matters for a day or two.
 */
export const useReminderActions = create<ReminderActionsState>()(
  persist(
    (set, get) => ({
      ...NO_ACTIONS,
      markDone: (pickup) =>
        set((state) => ({
          done: [...new Set([...state.done, ...pickup.kinds.map((kind) => doneKey(pickup.date, kind, pickup.place))])],
        })),
      snooze: (id, fireAt, pickup) =>
        set((state) => ({
          snoozed: [...state.snoozed.filter((s) => s.id !== id), { id, fireAt: fireAt.toISOString(), pickup }],
        })),
      prune: (now = new Date()) => {
        const pruned = pruneActions(get(), now);
        if (pruned.done.length !== get().done.length || pruned.snoozed.length !== get().snoozed.length) set(pruned);
      },
    }),
    {
      name: 'reminder-actions',
      version: 1,
      storage: createJSONStorage(() => storage),
      partialize: ({ done, snoozed }) => ({ done, snoozed }),
    },
  ),
);

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { fetchSchedule, type ScheduleData, UnsupportedScheduleError } from '@/lib/schedule';
import { storage } from '@/lib/storage';

export type RefreshError = 'loadFailed' | 'unsupported';

type ScheduleState = {
  data: ScheduleData | null;
  etag?: string;
  lastChecked?: string;
  refreshing: boolean;
  error: RefreshError | null;
  /** Downloads schedule.json; keeps the saved copy if that fails. Returns true if it changed. */
  refresh: () => Promise<boolean>;
};

export const useSchedule = create<ScheduleState>()(
  persist(
    (set, get) => ({
      data: null,
      refreshing: false,
      error: null,
      refresh: async () => {
        if (get().refreshing) return false;
        set({ refreshing: true, error: null });
        try {
          // Only send the ETag when we actually have the data it refers to.
          const result = await fetchSchedule(get().data ? get().etag : undefined);
          const lastChecked = new Date().toISOString();
          if (!result) {
            set({ refreshing: false, lastChecked });
            return false;
          }
          set({ data: result.data, etag: result.etag, lastChecked, refreshing: false });
          return true;
        } catch (error) {
          const code = error instanceof UnsupportedScheduleError ? 'unsupported' : 'loadFailed';
          set({ refreshing: false, error: code });
          return false;
        }
      },
    }),
    {
      name: 'schedule',
      version: 1,
      storage: createJSONStorage(() => storage),
      partialize: ({ data, etag, lastChecked }) => ({ data, etag, lastChecked }),
    },
  ),
);

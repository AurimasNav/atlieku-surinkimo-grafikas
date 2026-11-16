import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { loadKaunoAddress } from '@/lib/kauno';
import { type Area, fetchSchedule, type ScheduleData, UnsupportedScheduleError } from '@/lib/schedule';
import { useSettings } from '@/store/settings';
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
  /** Keeps the schedules of the user's Kauno r. address next to the data. */
  setPersonal: (personal: { key: string; areas: Area[] }) => void;
};

export const useSchedule = create<ScheduleState>()(
  persist(
    (set, get) => ({
      data: null,
      refreshing: false,
      error: null,
      setPersonal: (personal) => {
        const data = get().data;
        if (data) set({ data: { ...data, personal } });
      },
      refresh: async () => {
        if (get().refreshing) return false;
        set({ refreshing: true, error: null });
        try {
          // A Kauno r. address has its own, smaller download; a failure keeps the saved dates.
          const kauno = useSettings.getState().place?.kauno;
          const personal = kauno ? await loadKaunoAddress(kauno).catch(() => undefined) : undefined;
          const keep = (data: ScheduleData): ScheduleData => ({ ...data, personal: personal ?? get().data?.personal });
          // Only send the ETag when we actually have the data it refers to.
          const result = await fetchSchedule(get().data ? get().etag : undefined);
          const lastChecked = new Date().toISOString();
          if (!result) {
            const data = get().data;
            set({ refreshing: false, lastChecked, ...(data && personal ? { data: keep(data) } : {}) });
            return Boolean(personal);
          }
          set({ data: keep(result.data), etag: result.etag, lastChecked, refreshing: false });
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

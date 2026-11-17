import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { kaunoKey, loadKaunoAddress } from '@/lib/kauno';
import { REGION_URLS } from '@/lib/config';
import {
  type Area,
  fetchRegion,
  fetchSchedule,
  regionPart,
  type ScheduleData,
  UnsupportedScheduleError,
  withRegion,
} from '@/lib/schedule';
import { useSettings } from '@/store/settings';
import { storage } from '@/lib/storage';

export type RefreshError = 'loadFailed' | 'unsupported';

type ScheduleState = {
  data: ScheduleData | null;
  etag?: string;
  /** Other regions merged into `data` (config.REGION_URLS): the file's ETag and its companies. */
  regions?: Record<string, { etag?: string; providers: string[] }>;
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
          const found = kauno ? await loadKaunoAddress(kauno).catch(() => undefined) : undefined;
          // The saved spelling of the address was merged into another one: save that instead.
          if (kauno && found && found.key !== kaunoKey(kauno)) useSettings.getState().moveKaunoAddress(found.address);
          const personal = found && { key: found.key, areas: found.areas };
          const keep = (data: ScheduleData): ScheduleData => ({ ...data, personal: personal ?? get().data?.personal });
          // Only send the ETag when we actually have the data it refers to.
          const previous = get().data;
          const result = await fetchSchedule(previous ? get().etag : undefined);
          const lastChecked = new Date().toISOString();
          let data = result?.data ?? previous!;
          let changed = Boolean(result);
          // The other regions are merged in. One that can't be downloaded keeps the part saved
          // before, and doesn't hold back the rest.
          const regions = { ...get().regions };
          for (const url of REGION_URLS) {
            const known = regions[url];
            let part = known && previous ? regionPart(previous, known.providers) : undefined;
            const region = await fetchRegion(url, part?.areas.length ? known?.etag : undefined).catch(() => null);
            const providers = (region?.data.providers ?? []).map((provider) => provider.id);
            if (region && providers.length) {
              part = regionPart(region.data, providers);
              regions[url] = { etag: region.etag, providers };
              changed = true;
            }
            // Also drop the rows of companies the file listed before, should it rename one.
            const ids = [...new Set([...(known?.providers ?? []), ...(regions[url]?.providers ?? [])])];
            if (part && regions[url]) data = withRegion(data, ids, part);
          }
          if (!changed) {
            set({ refreshing: false, lastChecked, ...(personal ? { data: keep(data) } : {}) });
            return Boolean(personal);
          }
          set({ data: keep(data), etag: result ? result.etag : get().etag, regions, lastChecked, refreshing: false });
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
      partialize: ({ data, etag, regions, lastChecked }) => ({ data, etag, regions, lastChecked }),
    },
  ),
);

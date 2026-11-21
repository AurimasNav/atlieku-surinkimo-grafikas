import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { activeChanges, type PickupChange } from '@/lib/changes';
import { toIsoDate } from '@/lib/dates';
import { kaunoKey, loadKaunoAddress } from '@/lib/kauno';
import { fetchRegionIndex, type RegionIndex, regionUrls } from '@/lib/regions';
import {
  fetchRegion,
  fetchSchedule,
  regionPart,
  type Personal,
  personalsOf,
  type ScheduleData,
  UnsupportedScheduleError,
  withPersonals,
  withRegion,
} from '@/lib/schedule';
import { allPlaces, useSettings } from '@/store/settings';
import { storage } from '@/lib/storage';

export type RefreshError = 'loadFailed' | 'unsupported';

type ScheduleState = {
  data: ScheduleData | null;
  etag?: string;
  /**
   * Other regions merged into `data` (config.REGION_URLS and those of regions.json), by URL: the
   * file's ETag and its companies.
   */
  regions?: Record<string, { etag?: string; providers: string[] }>;
  /** The last regions.json that could be read (lib/regions.ts), and its ETag. */
  index?: RegionIndex;
  indexEtag?: string;
  lastChecked?: string;
  refreshing: boolean;
  error: RefreshError | null;
  /**
   * Downloads schedule.json, regions.json and the regions; keeps the saved copy of a file that
   * fails. Returns true if the data changed.
   */
  refresh: () => Promise<boolean>;
  /** Keeps the schedules of the user's Kauno r. address next to the data. */
  setPersonal: (personal: Personal) => void;
  /** Pickups of the user's that a refresh moved, cancelled or added (lib/refresh.ts). */
  changes: PickupChange[];
  addChanges: (changes: PickupChange[]) => void;
  dismissChanges: () => void;
};

export const useSchedule = create<ScheduleState>()(
  persist(
    (set, get) => ({
      data: null,
      refreshing: false,
      error: null,
      changes: [],
      addChanges: (changes) => {
        const known = activeChanges(get().changes, toIsoDate(new Date()));
        const key = (c: PickupChange) => `${c.kind}|${c.from ?? ''}|${c.to ?? ''}|${c.place ?? ''}`;
        const seen = new Set(known.map(key));
        set({ changes: [...known, ...changes.filter((c) => !seen.has(key(c)))] });
      },
      dismissChanges: () => set({ changes: [] }),
      setPersonal: (personal) => {
        const data = get().data;
        if (data) set({ data: withPersonals(data, [...personalsOf(data).filter((p) => p.key !== personal.key), personal]) });
      },
      refresh: async () => {
        if (get().refreshing) return false;
        set({ refreshing: true, error: null });
        try {
          // Each saved Kauno r. address has its own, smaller download; a failure keeps its saved
          // dates.
          const addresses = allPlaces(useSettings.getState()).flatMap((saved) => (saved.place?.kauno ? [saved.place.kauno] : []));
          const found = await Promise.all(addresses.map((address) => loadKaunoAddress(address).catch(() => undefined)));
          const saved = personalsOf(get().data);
          const personals = addresses.flatMap((address, i): Personal[] => {
            const result = found[i];
            if (!result) return saved.filter((p) => p.key === kaunoKey(address));
            // The saved spelling of the address was merged into another one: save that instead.
            if (result.key !== kaunoKey(address)) useSettings.getState().moveKaunoAddress(kaunoKey(address), result.address);
            return [{ key: result.key, areas: result.areas, generatedAt: result.generatedAt }];
          });
          const loaded = found.some(Boolean);
          const keep = (data: ScheduleData): ScheduleData => withPersonals(data, personals);
          // Only send the ETag when we actually have the data it refers to.
          const previous = get().data;
          const savedIndex = get().index;
          // regions.json says which regions there are besides the built-in ones. If it can't be
          // downloaded or read, or hasn't changed (304), the one saved last time is used.
          const [result, fresh] = await Promise.all([
            fetchSchedule(previous ? get().etag : undefined),
            fetchRegionIndex(savedIndex ? get().indexEtag : undefined).catch(() => null),
          ]);
          const index = fresh?.index ?? savedIndex;
          const indexEtag = fresh ? fresh.etag : get().indexEtag;
          const lastChecked = new Date().toISOString();
          let data = result?.data ?? previous!;
          let changed = Boolean(result);
          const regions = { ...get().regions };
          const urls = regionUrls(index);
          // A region a newer regions.json no longer lists was taken off the site on purpose (a
          // failed build keeps yesterday's files), so its part goes. The built-in ones stay.
          for (const [url, gone] of Object.entries(regions)) {
            if (urls.includes(url)) continue;
            data = withRegion(data, gone.providers, { areas: [], locations: [], providers: [] });
            delete regions[url];
            changed = true;
          }
          // The other regions are merged in. One that can't be downloaded keeps the part saved
          // before, and doesn't hold back the rest.
          for (const url of urls) {
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
            set({ refreshing: false, lastChecked, index, indexEtag, ...(loaded ? { data: keep(data) } : {}) });
            return loaded;
          }
          set({
            data: keep(data),
            etag: result ? result.etag : get().etag,
            regions,
            index,
            indexEtag,
            lastChecked,
            refreshing: false,
          });
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
      partialize: ({ data, etag, regions, index, indexEtag, lastChecked, changes }) => ({
        data,
        etag,
        regions,
        index,
        indexEtag,
        lastChecked,
        changes,
      }),
    },
  ),
);

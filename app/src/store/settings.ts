import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { Language } from '@/i18n';
import type { CustomSchedule } from '@/lib/custom-schedule';
import type { ReminderSettings } from '@/lib/reminders';
import type { Place } from '@/lib/resolve';
import type { WasteKind } from '@/lib/schedule';
import { storage } from '@/lib/storage';

type SettingsState = {
  onboarded: boolean;
  language: Language | 'system';
  place: Place | null;
  reminder: ReminderSettings;
  setOnboarded: () => void;
  setLanguage: (language: Language | 'system') => void;
  /** Starts over with a new location; earlier per-kind answers no longer apply. */
  setLocation: (locationId: string, street?: string) => void;
  /** Answers one waste type: an area id, or null for "I don't have this container". */
  choose: (kind: WasteKind, areaId: string | null) => void;
  /** Sets (or with undefined removes) the user's own schedule for one waste type. */
  setCustom: (kind: WasteKind, schedule: CustomSchedule | undefined) => void;
  /** Forgets any answer or own schedule for a waste type: back to the official schedule. */
  resetKind: (kind: WasteKind) => void;
  /** Starts a place without an official location, for users who set their own schedules. */
  startCustomPlace: () => void;
  setReminder: (reminder: ReminderSettings) => void;
};

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      onboarded: false,
      language: 'system',
      place: null,
      reminder: { daysBefore: 1, hour: 19, minute: 0 },
      setOnboarded: () => set({ onboarded: true }),
      setLanguage: (language) => set({ language }),
      // Own schedules are personal choices, so they survive a change of location.
      setLocation: (locationId, street) =>
        set((state) => ({ place: { locationId, street, choices: {}, custom: state.place?.custom } })),
      choose: (kind, areaId) =>
        set((state) => {
          const custom = { ...state.place?.custom };
          delete custom[kind]; // picking a row (or "none") replaces an own schedule
          return { place: { ...(state.place ?? {}), choices: { ...state.place?.choices, [kind]: areaId }, custom } };
        }),
      setCustom: (kind, schedule) =>
        set((state) => {
          const place = state.place ?? { choices: {} };
          const custom = { ...place.custom };
          if (schedule) custom[kind] = schedule;
          else delete custom[kind];
          const choices = { ...place.choices };
          if (schedule) delete choices[kind]; // an own schedule replaces "I don't have it"
          return { place: { ...place, choices, custom } };
        }),
      resetKind: (kind) =>
        set((state) => {
          if (!state.place) return {};
          const choices = { ...state.place.choices };
          const custom = { ...state.place.custom };
          delete choices[kind];
          delete custom[kind];
          return { place: { ...state.place, choices, custom } };
        }),
      startCustomPlace: () => set((state) => ({ place: { choices: {}, custom: state.place?.custom ?? {} } })),
      setReminder: (reminder) => set({ reminder }),
    }),
    {
      name: 'settings',
      version: 2,
      storage: createJSONStorage(() => storage),
      // v1 stored one row per waste type; v2 stores one location. Keep language and reminder
      // time, and run setup again (only early test builds ever had v1).
      migrate: (persisted, version) => {
        const old = (persisted ?? {}) as Partial<SettingsState>;
        if (version < 2) return { language: old.language, reminder: old.reminder, onboarded: false, place: null };
        return old;
      },
    },
  ),
);

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { Language } from '@/i18n';
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
      setLocation: (locationId, street) => set({ place: { locationId, street, choices: {} } }),
      choose: (kind, areaId) =>
        set((state) => ({
          place: {
            ...(state.place ?? {}),
            choices: { ...state.place?.choices, [kind]: areaId },
          },
        })),
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

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { Language } from '@/i18n';
import type { ReminderSettings } from '@/lib/reminders';
import type { WasteKind } from '@/lib/schedule';
import { storage } from '@/lib/storage';

/** Area id per waste kind; null means the user doesn't have that container. */
export type Selections = Partial<Record<WasteKind, string | null>>;

type SettingsState = {
  onboarded: boolean;
  language: Language | 'system';
  selections: Selections;
  reminder: ReminderSettings;
  setOnboarded: () => void;
  setLanguage: (language: Language | 'system') => void;
  select: (kind: WasteKind, areaId: string | null) => void;
  setReminder: (reminder: ReminderSettings) => void;
};

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      onboarded: false,
      language: 'system',
      selections: {},
      reminder: { daysBefore: 1, hour: 19, minute: 0 },
      setOnboarded: () => set({ onboarded: true }),
      setLanguage: (language) => set({ language }),
      select: (kind, areaId) =>
        set((state) => ({ selections: { ...state.selections, [kind]: areaId } })),
      setReminder: (reminder) => set({ reminder }),
    }),
    { name: 'settings', version: 1, storage: createJSONStorage(() => storage) },
  ),
);

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { Language } from '@/i18n';
import type { CustomSchedule } from '@/lib/custom-schedule';
import { type KaunoAddress, kaunoKey } from '@/lib/kauno';
import type { ReminderSettings, ReminderTime } from '@/lib/reminders';
import type { Place } from '@/lib/resolve';
import type { WasteKind } from '@/lib/schedule';
import { storage } from '@/lib/storage';

/** A place the user saved but isn't looking at now. */
export type SavedPlace = { id: string; name?: string; place: Place | null };

type SettingsState = {
  onboarded: boolean;
  language: Language | 'system';
  /** The place shown now; every setter below works on it. */
  place: Place | null;
  /** Its id (for reminders) and the name the user gave it, e.g. "Summer house". */
  placeId: string;
  placeName?: string;
  /** More places, e.g. a summer house or a parent's home: they get reminders too. */
  otherPlaces: SavedPlace[];
  reminder: ReminderSettings;
  /** How home lists the coming pickups. */
  homeView: 'list' | 'month';
  setOnboarded: () => void;
  setLanguage: (language: Language | 'system') => void;
  /** Starts over with a new location; earlier per-kind answers no longer apply. */
  setLocation: (locationId: string, street?: string) => void;
  /** Starts over with an address in Kauno r.; its schedules are kept by the schedule store. */
  setKaunoAddress: (address: KaunoAddress) => void;
  /** A saved Kauno r. address (`key`), as the data writes it now: keeps every answer. */
  moveKaunoAddress: (key: string, address: KaunoAddress) => void;
  /** Answers one waste type: an area id, or null for "I don't have this container". */
  choose: (kind: WasteKind, areaId: string | null) => void;
  /** Sets (or with undefined removes) the user's own schedule for one waste type. */
  setCustom: (kind: WasteKind, schedule: CustomSchedule | undefined) => void;
  /** Forgets any answer or own schedule for a waste type: back to the official schedule. */
  resetKind: (kind: WasteKind) => void;
  /** Starts a place without an official location, for users who set their own schedules. */
  startCustomPlace: () => void;
  setReminder: (reminder: ReminderSettings) => void;
  setHomeView: (homeView: 'list' | 'month') => void;
  /** Saves the current place among the others and starts an empty one to set up. */
  addPlace: () => void;
  /** Shows another saved place. */
  switchPlace: (id: string) => void;
  renamePlace: (id: string, name: string) => void;
  /** Forgets a place; removing the current one shows the next saved place. */
  removePlace: (id: string) => void;
};

/** Every saved place, the current one first. */
export const allPlaces = (state: Pick<SettingsState, 'place' | 'placeId' | 'placeName' | 'otherPlaces'>): SavedPlace[] => [
  { id: state.placeId, name: state.placeName, place: state.place },
  ...state.otherPlaces,
];

const newPlaceId = () => `p${Date.now().toString(36)}`;

/** A place nothing was set up for yet: not worth keeping when the user moves on. */
const isEmpty = (place: Place | null) =>
  !place || (!place.locationId && !place.kauno && !Object.keys(place.choices).length && !Object.keys(place.custom ?? {}).length);

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      onboarded: false,
      language: 'system',
      place: null,
      placeId: 'home',
      otherPlaces: [],
      reminder: { times: [{ daysBefore: 1, hour: 19, minute: 0 }] },
      setOnboarded: () => set({ onboarded: true }),
      setLanguage: (language) => set({ language }),
      // Own schedules are personal choices, so they survive a change of location.
      setLocation: (locationId, street) =>
        set((state) => ({ place: { locationId, street, choices: {}, custom: state.place?.custom } })),
      setKaunoAddress: (kauno) => set((state) => ({ place: { kauno, choices: {}, custom: state.place?.custom } })),
      moveKaunoAddress: (key, kauno) =>
        set((state) => {
          const move = (place: Place | null) => (place?.kauno && kaunoKey(place.kauno) === key ? { ...place, kauno } : place);
          return { place: move(state.place), otherPlaces: state.otherPlaces.map((saved) => ({ ...saved, place: move(saved.place) })) };
        }),
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
      homeView: 'list',
      setHomeView: (homeView) => set({ homeView }),
      addPlace: () =>
        set((state) => ({
          otherPlaces: isEmpty(state.place) ? state.otherPlaces : [{ id: state.placeId, name: state.placeName, place: state.place }, ...state.otherPlaces],
          place: null,
          placeId: newPlaceId(),
          placeName: undefined,
        })),
      switchPlace: (id) =>
        set((state) => {
          const target = state.otherPlaces.find((saved) => saved.id === id);
          if (!target) return {};
          const others = state.otherPlaces.filter((saved) => saved.id !== id);
          const current = isEmpty(state.place) ? [] : [{ id: state.placeId, name: state.placeName, place: state.place }];
          return { place: target.place, placeId: target.id, placeName: target.name, otherPlaces: [...current, ...others] };
        }),
      renamePlace: (id, name) =>
        set((state) => {
          const trimmed = name.trim() || undefined;
          if (id === state.placeId) return { placeName: trimmed };
          return { otherPlaces: state.otherPlaces.map((saved) => (saved.id === id ? { ...saved, name: trimmed } : saved)) };
        }),
      removePlace: (id) =>
        set((state) => {
          if (id !== state.placeId) return { otherPlaces: state.otherPlaces.filter((saved) => saved.id !== id) };
          const [next, ...rest] = state.otherPlaces;
          return next
            ? { place: next.place, placeId: next.id, placeName: next.name, otherPlaces: rest }
            : { place: null, placeId: newPlaceId(), placeName: undefined };
        }),
    }),
    {
      name: 'settings',
      version: 3,
      storage: createJSONStorage(() => storage),
      migrate: (persisted, version) => {
        const old = (persisted ?? {}) as Partial<SettingsState>;
        // v2 had one reminder time for everything; v3 has a list, and per waste type.
        const reminder = old.reminder && version < 3 ? { times: [old.reminder as unknown as ReminderTime] } : old.reminder;
        // v1 stored one row per waste type; v2 stores one location. Keep language and reminder
        // time, and run setup again (only early test builds ever had v1).
        if (version < 2) return { language: old.language, reminder, onboarded: false, place: null };
        return { ...old, reminder };
      },
    },
  ),
);

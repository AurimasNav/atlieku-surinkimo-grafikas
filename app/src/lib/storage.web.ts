import type { StateStorage } from 'zustand/middleware';

// The web build is only a development preview, so plain localStorage is enough.
export const storage: StateStorage = {
  getItem: (key) => globalThis.localStorage?.getItem(key) ?? null,
  setItem: (key, value) => globalThis.localStorage?.setItem(key, value),
  removeItem: (key) => globalThis.localStorage?.removeItem(key),
};

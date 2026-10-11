import Storage from 'expo-sqlite/kv-store';
import type { StateStorage } from 'zustand/middleware';

// Synchronous, so persisted state is ready on the first render and inside background tasks.
export const storage: StateStorage = {
  getItem: (key) => Storage.getItemSync(key),
  setItem: (key, value) => Storage.setItemSync(key, value),
  removeItem: (key) => {
    Storage.removeItemSync(key);
  },
};

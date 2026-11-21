import { useSettings } from './settings';

const saved: Record<string, string> = {};

jest.mock('@/lib/storage', () => ({
  storage: {
    getItem: (key: string) => saved[key] ?? null,
    setItem: (key: string, value: string) => {
      saved[key] = value;
    },
    removeItem: (key: string) => {
      delete saved[key];
    },
  },
}));

describe('settings migration', () => {
  it('keeps the one reminder time of v2 as the first of a list', async () => {
    saved.settings = JSON.stringify({
      version: 2,
      state: {
        onboarded: true,
        language: 'lt',
        place: { locationId: 'x', choices: {} },
        reminder: { daysBefore: 0, hour: 6, minute: 30 },
      },
    });
    await useSettings.persist.rehydrate();
    const state = useSettings.getState();
    expect(state.reminder).toEqual({ times: [{ daysBefore: 0, hour: 6, minute: 30 }] });
    expect(state.onboarded).toBe(true);
    expect(state.place).toEqual({ locationId: 'x', choices: {} });
    expect(state.language).toBe('lt');
  });
});

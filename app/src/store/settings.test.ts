import { allPlaces, useSettings } from './settings';

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

describe('saved places', () => {
  beforeEach(() => {
    useSettings.setState({ place: { locationId: 'home', choices: {} }, placeId: 'home', placeName: undefined, otherPlaces: [] });
  });

  it('adds a place to set up and switches back', () => {
    useSettings.getState().addPlace();
    const added = useSettings.getState();
    expect(added.place).toBeNull();
    expect(added.otherPlaces).toEqual([{ id: 'home', name: undefined, place: { locationId: 'home', choices: {} } }]);

    useSettings.getState().setLocation('summer');
    useSettings.getState().renamePlace(added.placeId, '  Sodyba ');
    useSettings.getState().switchPlace('home');
    const back = useSettings.getState();
    expect(back.place).toEqual({ locationId: 'home', choices: {} });
    expect(back.otherPlaces).toEqual([{ id: added.placeId, name: 'Sodyba', place: { locationId: 'summer', choices: {} } }]);
    expect(allPlaces(back).map((saved) => saved.id)).toEqual(['home', added.placeId]);
  });

  it('drops a new place that was never set up', () => {
    useSettings.getState().addPlace();
    useSettings.getState().switchPlace('home');
    expect(useSettings.getState().otherPlaces).toEqual([]);
  });

  it('shows the next place when the current one is removed', () => {
    useSettings.setState({ otherPlaces: [{ id: 'summer', name: 'Sodyba', place: { locationId: 'summer', choices: {} } }] });
    useSettings.getState().removePlace('home');
    const state = useSettings.getState();
    expect([state.placeId, state.placeName, state.place?.locationId, state.otherPlaces]).toEqual(['summer', 'Sodyba', 'summer', []]);
  });
});

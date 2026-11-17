import * as Location from 'expo-location';

import { locateHome } from './geolocate';
import { type AddressTable, streetConfidence } from './nearest';

jest.mock('expo-location', () => ({
  Accuracy: { High: 4 },
  requestForegroundPermissionsAsync: jest.fn(),
  hasServicesEnabledAsync: jest.fn(),
  getCurrentPositionAsync: jest.fn(),
}));

const location = jest.mocked(Location);

// Vilniaus r.: one address. Kauno r.: one address about 11 km south of it.
const table: AddressTable = {
  generatedAt: '',
  source: '',
  places: [['g10937', 's1559497', 'Durpių g.']],
  points: [[5480000, 2525000, 0, '12']],
};
const kaunoPoints: { places: string[][]; points: [number, number, number, string][] } = {
  places: [['akademijos', 'Akademijos sen.', 'Akademijos mstl.', 'Forto g.']],
  points: [[5470000, 2525000, 0, '8']],
};

// Mažeikių r.: its own file in the format of the main one.
const mazeikiai: AddressTable = {
  generatedAt: '',
  source: '',
  places: [['g23467', 's1400123', 'Žemaitės g.']],
  points: [[5631000, 2234000, 0, '2']],
};

/** `metres` north of a point given as [lat * 1e5, lon * 1e5]. */
const north = ([lat, lon]: readonly [number, number, ...unknown[]], metres: number) => ({
  latitude: lat / 1e5 + metres / 111_320,
  longitude: lon / 1e5,
});

function at(coords: { latitude: number; longitude: number }, accuracy = 10) {
  location.getCurrentPositionAsync.mockResolvedValue({ coords: { ...coords, accuracy } } as Location.LocationObject);
}

beforeEach(() => {
  location.requestForegroundPermissionsAsync.mockResolvedValue({ granted: true } as Location.LocationPermissionResponse);
  location.hasServicesEnabledAsync.mockResolvedValue(true);
  globalThis.fetch = jest.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      String(url).includes('kauno-r') ? kaunoPoints : String(url).includes('mazeikiu-r') ? mazeikiai : table,
  })) as unknown as typeof fetch;
});

describe('streetConfidence', () => {
  it('needs a precise position and an address within 100 m', () => {
    expect(streetConfidence({ approximate: false, accuracy: 20, distance: 30 })).toBe('ok');
    expect(streetConfidence({ approximate: false, accuracy: 20, distance: 100 })).toBe('ok');
    expect(streetConfidence({ approximate: false, accuracy: 20, distance: 101 })).toBe('far');
    expect(streetConfidence({ approximate: false, accuracy: 76, distance: 30 })).toBe('approximate');
    expect(streetConfidence({ approximate: true, accuracy: 20, distance: 30 })).toBe('approximate');
  });
});

describe('locateHome', () => {
  it('suggests the street of an address close by', async () => {
    at(north(table.points[0], 40));
    const found = await locateHome();
    expect(found).toMatchObject({ ok: true, address: { locationId: 'g10937', number: '12' }, street: 'ok' });
  });

  it('asks for the street when the nearest address is more than 100 m away', async () => {
    at(north(table.points[0], 250));
    expect(await locateHome()).toMatchObject({ ok: true, address: { locationId: 'g10937' }, street: 'far' });
  });

  it('does the same in Kauno r.', async () => {
    at(north(kaunoPoints.points[0], 40));
    expect(await locateHome()).toMatchObject({
      ok: true,
      kauno: { eldership: 'akademijos', town: 'Akademijos mstl.', street: 'Forto g.', house: '8' },
      street: 'ok',
    });
    at(north(kaunoPoints.points[0], 250));
    expect(await locateHome()).toMatchObject({ ok: true, kauno: { town: 'Akademijos mstl.' }, street: 'far' });
  });

  it('finds addresses of the other regions', async () => {
    at(north(mazeikiai.points[0], 40));
    expect(await locateHome()).toMatchObject({
      ok: true,
      address: { locationId: 'g23467', street: 's1400123', streetLabel: 'Žemaitės g.', number: '2' },
      street: 'ok',
    });
  });

  it('asks for the street with a poor fix, even next to an address', async () => {
    at(north(table.points[0], 10), 120);
    expect(await locateHome()).toMatchObject({ ok: true, street: 'approximate' });
  });

  it('suggests nothing more than 400 m from any address', async () => {
    at(north(table.points[0], 500));
    expect(await locateHome()).toEqual({ ok: false, reason: 'far' });
  });
});

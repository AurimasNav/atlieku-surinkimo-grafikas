import {
  isKaunasCitySearch,
  uncoveredCitySearch,
  type KaunoAddress,
  type KaunoAddresses,
  kaunoAlias,
  kaunoAreas,
  type KaunoIndex,
  kaunoKey,
  kaunoTowns,
  loadKaunoAddress,
  searchKaunoTowns,
} from './kauno';
import { placeLabel, resolvePlace, visibleKinds } from './resolve';
import type { ScheduleData } from './schedule';

const index: KaunoIndex = {
  schemaVersion: 1,
  generatedAt: '',
  areas: [
    { id: 'kh-a', kind: 'household', rule: 'kas 14 dienų', dates: ['2026-11-25', '2026-12-09'] },
    { id: 'kh-b', kind: 'household', rule: 'kas 14 dienų', dates: ['2026-11-18', '2026-12-02'] },
    { id: 'kf-a', kind: 'food', rule: 'kas 7 dienas', dates: ['2026-11-20', '2026-11-27'] },
  ],
  elderships: [
    { id: 'ringaudu', name: 'Ringaudų sen.', towns: ['Karkiškių k.', 'Ringaudų k.'] },
    { id: 'uzliedziu', name: 'Užliedžių sen.', towns: ['Sausinės k.'] },
  ],
};
const addresses: KaunoAddresses = {
  eldership: 'Ringaudų sen.',
  towns: { 'Karkiškių k.': { 'Ganyklų g.': { '2': [0, 2], '4': [0, 1] } } },
};
const address: KaunoAddress = {
  eldership: 'ringaudu',
  eldershipName: 'Ringaudų sen.',
  town: 'Karkiškių k.',
  street: 'Ganyklų g.',
  house: '2',
};
const today = '2026-11-16';

describe('Kauno r. addresses', () => {
  it('finds towns without diacritics, by town or eldership', () => {
    const towns = kaunoTowns(index);
    expect(searchKaunoTowns(towns, 'karkisk').map((t) => t.town)).toEqual(['Karkiškių k.']);
    expect(searchKaunoTowns(towns, 'ringaud').map((t) => t.town)).toEqual(['Ringaudų k.', 'Karkiškių k.']);
    expect(searchKaunoTowns(towns, '')).toEqual([]);
  });

  it('finds towns by their name in the Address Register', () => {
    // As kauno-r/schedule.json writes them: genitive and type, and the register's name.
    const towns = kaunoTowns({
      ...index,
      elderships: [
        { id: 'akademijos', name: 'Akademijos sen.', towns: ['Akademijos mstl.'], registerNames: { 'Akademijos mstl.': 'Akademija' } },
        {
          id: 'babtu',
          name: 'Babtų sen.',
          towns: ['Babtų k.', 'Babtų mstl.', 'Muniškių k.'],
          registerNames: { 'Babtų k.': 'Babtai', 'Babtų mstl.': 'Babtai', 'Muniškių k.': 'Muniškiai' },
        },
        { id: 'uzliedziu', name: 'Užliedžių sen.', towns: ['Kauno raj.', 'Romainių k.'], registerNames: { 'Romainių k.': 'Romainiai' } },
      ],
    });
    const search = (query: string) => searchKaunoTowns(towns, query).map((t) => t.town);
    expect(search('Akademija')).toEqual(['Akademijos mstl.']);
    expect(search('akademij')).toEqual(['Akademijos mstl.']);
    expect(search('Babtai')).toEqual(['Babtų k.', 'Babtų mstl.']);
    expect(search('muniskiai babtu')).toEqual(['Muniškių k.']);
    // A match on the register's name counts as the start of the name: Babtai before the
    // villages of Babtų sen.
    expect(search('babt')).toEqual(['Babtų k.', 'Babtų mstl.', 'Muniškių k.']);
    expect(search('romainiai')).toEqual(['Romainių k.']);
    // The town is still the name the address files use.
    expect(searchKaunoTowns(towns, 'Akademija')).toEqual([
      { eldership: 'akademijos', eldershipName: 'Akademijos sen.', town: 'Akademijos mstl.', registerName: 'Akademija' },
    ]);
  });

  it('works with data that has no register names', () => {
    expect(kaunoTowns(index)[0]).toEqual({ eldership: 'ringaudu', eldershipName: 'Ringaudų sen.', town: 'Karkiškių k.' });
    expect(searchKaunoTowns(kaunoTowns(index), 'Karkiškės')).toEqual([]);
  });

  it('gives one schedule per waste type', () => {
    expect(kaunoAreas(index, addresses, address)).toEqual([
      { id: 'kauno-household', kind: 'household', name: 'kas 14 dienų', dates: ['2026-11-25', '2026-12-09'], current: true },
      { id: 'kauno-food', kind: 'food', name: 'kas 7 dienas', dates: ['2026-11-20', '2026-11-27'], current: true },
    ]);
  });

  it('joins the dates of two containers of one type', () => {
    const areas = kaunoAreas(index, addresses, { ...address, house: '4' });
    expect(areas?.map((a) => a.kind)).toEqual(['household']);
    expect(areas?.[0].dates).toEqual(['2026-11-18', '2026-11-25', '2026-12-02', '2026-12-09']);
  });

  it('reports an address that is no longer listed', () => {
    expect(kaunoAreas(index, addresses, { ...address, house: '99' })).toBeUndefined();
  });
});

describe('a place in Kauno r.', () => {
  const data: ScheduleData = {
    schemaVersion: 1,
    generatedAt: '',
    source: '',
    coverage: {},
    areas: [],
    locations: [],
    personal: { key: kaunoKey(address), areas: kaunoAreas(index, addresses, address)! },
  };
  const place = { kauno: address, choices: {} };

  it('uses the schedules kept for that address', () => {
    const r = resolvePlace(data, place, today);
    expect(r.areas.map((a) => a.id)).toEqual(['kauno-household', 'kauno-food']);
    expect(r.kinds.green).toEqual({ status: 'none' });
    expect(visibleKinds(place, r)).toEqual(['household', 'food', 'green']);
    expect(placeLabel(place, r)).toEqual({ name: 'Ganyklų g. 2', detail: 'Karkiškių k. · Ringaudų sen.' });
  });

  it('ignores schedules kept for another address', () => {
    const r = resolvePlace(data, { kauno: { ...address, house: '4' }, choices: {} }, today);
    expect(r.areas).toEqual([]);
  });

  it('lets an own schedule replace one type', () => {
    const custom = { household: { start: '2026-11-17', every: 1, unit: 'week' as const } };
    const r = resolvePlace(data, { ...place, custom }, today);
    expect(r.areas.map((a) => a.id)).toEqual(['custom-household', 'kauno-food']);
  });

  it('keeps showing mixed, packaging and glass elsewhere', () => {
    const r = resolvePlace(data, { locationId: 'x', choices: {} }, today);
    expect(visibleKinds({ locationId: 'x', choices: {} }, r)).toEqual(['household', 'packaging', 'glass']);
  });
});

describe('an address saved with a spelling that was merged', () => {
  // "Akademija" was one stray row of "Akademijos mstl."; "Domeikavos k." was also listed under
  // Vandžiogalos sen. Both now point to the address as the data writes it.
  const akademijos: KaunoAddresses = {
    eldership: 'Akademijos sen.',
    towns: { 'Akademijos mstl.': { 'Vynuogyno g.': { '9': [0, 2] } } },
    aliases: { Akademija: { 'Vynuogyno g.': { '9': ['akademijos', 'Akademijos mstl.', 'Vynuogyno g.', '9'] } } },
  };
  const vandziogalos: KaunoAddresses = {
    eldership: 'Vandžiogalos sen.',
    towns: {},
    aliases: { 'Domeikavos k.': { 'Rugio g.': { '1': ['domeikavos', 'Domeikavos k.', 'Rugio g.', '1'] } } },
  };
  const domeikavos: KaunoAddresses = {
    eldership: 'Domeikavos sen.',
    towns: { 'Domeikavos k.': { 'Rugio g.': { '1': [1] } } },
  };
  const merged: KaunoIndex = {
    ...index,
    elderships: [
      { id: 'akademijos', name: 'Akademijos sen.', towns: ['Akademijos mstl.'] },
      { id: 'domeikavos', name: 'Domeikavos sen.', towns: ['Domeikavos k.'] },
      { id: 'vandziogalos', name: 'Vandžiogalos sen.', towns: [] },
    ],
  };
  const files: Record<string, KaunoAddresses> = { akademijos, vandziogalos, domeikavos };
  const saved: KaunoAddress = {
    eldership: 'akademijos',
    eldershipName: 'Akademijos sen.',
    town: 'Akademija',
    street: 'Vynuogyno g.',
    house: '9',
  };

  beforeEach(() => {
    globalThis.fetch = jest.fn(async (url: string) => {
      const name = String(url).match(/addresses\/(\w+)\.json$/)?.[1];
      return { ok: true, json: async () => (name ? files[name] : merged) };
    }) as unknown as typeof fetch;
  });

  it('is not listed, but leads to the address now', () => {
    expect(kaunoAreas(merged, akademijos, saved)).toBeUndefined();
    expect(kaunoAlias(merged, akademijos, saved)).toEqual({ ...saved, town: 'Akademijos mstl.' });
  });

  it('gets the schedules of the address now', async () => {
    const found = await loadKaunoAddress(saved);
    expect(found?.address).toEqual({ ...saved, town: 'Akademijos mstl.' });
    expect(found?.key).toBe('akademijos|Akademijos mstl.|Vynuogyno g.|9');
    expect(found?.areas.map((a) => a.kind)).toEqual(['household', 'food']);
  });

  it('follows a town into another eldership', async () => {
    const found = await loadKaunoAddress({
      eldership: 'vandziogalos',
      eldershipName: 'Vandžiogalos sen.',
      town: 'Domeikavos k.',
      street: 'Rugio g.',
      house: '1',
    });
    expect(found?.address).toEqual({
      eldership: 'domeikavos',
      eldershipName: 'Domeikavos sen.',
      town: 'Domeikavos k.',
      street: 'Rugio g.',
      house: '1',
    });
    expect(found?.areas.map((a) => a.kind)).toEqual(['household']);
  });

  it('keeps an address that is still listed as it is', async () => {
    const address = { ...saved, town: 'Akademijos mstl.' };
    expect((await loadKaunoAddress(address))?.address).toBe(address);
  });

  it('is still gone if no alias leads anywhere', async () => {
    expect(await loadKaunoAddress({ ...saved, house: '99' })).toBeUndefined();
  });
});

describe('a search for Kaunas city', () => {
  it('is recognised in every spelling', () => {
    for (const query of ['Kaunas', 'kaunas', ' KAUNAS ', 'Kauno m.', 'kauno m', 'Kauno miestas', 'Kauno miesto sav.', 'kauno mies', 'Kaunas m.', 'Kaune', 'Kowno', 'Каунас']) {
      expect([query, isKaunasCitySearch(query, 0)]).toEqual([query, true]);
    }
  });

  it('is not the district or another place', () => {
    for (const query of ['Kauno r.', 'kauno raj', 'Kaunas r.', 'Kaunas district', 'Kauno rajonas', 'Kauno', 'kaun', 'Kauno marios', 'Akademija', 'Vilnius', '']) {
      expect([query, isKaunasCitySearch(query, 0)]).toEqual([query, false]);
    }
  });

  it('is not said when the search found something', () => {
    expect(isKaunasCitySearch('kaunas', 1)).toBe(false);
  });
});

describe('a search for Klaipėda city', () => {
  it('is recognised, and is not the district', () => {
    for (const query of ['Klaipėda', 'klaipeda', 'Klaipėdos m.', 'Klaipėdos miestas', 'Klaipėdoje', 'Kłajpeda', 'Клайпеда']) {
      expect([query, uncoveredCitySearch(query, 0)]).toEqual([query, 'klaipeda']);
    }
    for (const query of ['Klaipėdos r.', 'Klaipėda district', 'Klaipėdos rajonas', 'Gargždai']) {
      expect([query, uncoveredCitySearch(query, 0)]).toEqual([query, undefined]);
    }
    expect(uncoveredCitySearch('Kaunas', 0)).toBe('kaunas');
    expect(uncoveredCitySearch('Klaipėda', 2)).toBeUndefined();
  });
});

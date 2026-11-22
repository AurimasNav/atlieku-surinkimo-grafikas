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
  municipalityOf,
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

  it('tells the municipality of a town: Kaišiadorių r., or Kauno r. when the data names none', () => {
    const towns = kaunoTowns({
      ...index,
      elderships: [
        ...index.elderships,
        {
          id: 'ziezmariu',
          name: 'Žiežmarių sen.',
          municipality: 'Kaišiadorių r.',
          towns: ['Žiežmarių mstl.'],
          registerNames: { 'Žiežmarių mstl.': 'Žiežmariai' },
        },
      ],
    });
    const [ziezmariai] = searchKaunoTowns(towns, 'Žiežmariai');
    expect(ziezmariai).toEqual({
      eldership: 'ziezmariu',
      eldershipName: 'Žiežmarių sen.',
      town: 'Žiežmarių mstl.',
      registerName: 'Žiežmariai',
      municipality: 'Kaišiadorių r.',
    });
    expect(municipalityOf(ziezmariai)).toBe('Kaišiadorių r.');
    expect(municipalityOf(searchKaunoTowns(towns, 'Karkiškių')[0])).toBe('Kauno r.');
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
      expect([query, isKaunasCitySearch(query)]).toEqual([query, true]);
    }
  });

  it('is not the district or another place', () => {
    for (const query of ['Kauno r.', 'kauno raj', 'Kaunas r.', 'Kaunas district', 'Kauno rajonas', 'Kauno', 'kaun', 'Kauno marios', 'Akademija', 'Vilnius', '']) {
      expect([query, isKaunasCitySearch(query)]).toEqual([query, false]);
    }
  });
});

describe('a search for Vilnius city', () => {
  it('is recognised, and is not the district', () => {
    for (const query of ['Vilnius', 'vilnius', 'Vilniaus m.', 'Vilniaus miestas', 'Vilniaus miesto sav.', 'Vilniuje', 'Wilno', 'Вильнюс']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, 'vilnius']);
    }
    // "Vilniaus" alone is also the start of the district's name.
    for (const query of ['Vilniaus r.', 'Vilnius district', 'Vilniaus rajonas', 'Vilniaus', 'Nemenčinė', 'Riešė']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
    }
  });
});

describe('a search for Klaipėda city', () => {
  it('is recognised, and is not the district', () => {
    for (const query of ['Klaipėda', 'klaipeda', 'Klaipėdos m.', 'Klaipėdos miestas', 'Klaipėdoje', 'Kłajpeda', 'Клайпеда']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, 'klaipeda']);
    }
    for (const query of ['Klaipėdos r.', 'Klaipėda district', 'Klaipėdos rajonas', 'Gargždai']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
    }
    expect(uncoveredCitySearch('Kaunas')).toBe('kaunas');
  });
});

describe('a search for Šiauliai or Alytus city', () => {
  it('is recognised in every spelling', () => {
    for (const query of ['Šiauliai', 'siauliai', 'Šiaulių m.', 'Šiaulių miestas', 'Šiauliuose', 'Szawle', 'Шяуляй', 'Шауляй']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, 'siauliai']);
    }
    for (const query of ['Alytus', 'alytus', 'Alytaus m.', 'Alytaus miesto sav.', 'Alytuje', 'Olita', 'Алитус']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, 'alytus']);
    }
  });

  it('is not the district, its elderships or other places', () => {
    // "Šiaulių" and "Alytaus" alone are also the elderships Šiaulių kaimiškoji and Alytaus sen.
    for (const query of ['Šiaulių r.', 'Šiauliai district', 'Šiaulių rajonas', 'Šiaulių', 'Šiauliškiai', 'Kuršėnai']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
    }
    for (const query of ['Alytaus r.', 'Alytus district', 'Alytaus rajonas', 'Alytaus', 'Alytupis', 'Druskininkai', 'Birštonas']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
    }
  });
});

describe('a search for Panevėžys city', () => {
  it('is recognised in every spelling', () => {
    const queries = ['Panevėžys', 'panevezys', 'Panevėžio m.', 'Panevėžio miestas', 'Panevėžio miesto sav.', 'Panevėžyje', 'Poniewież', 'Паневежис'];
    for (const query of queries) expect([query, uncoveredCitySearch(query)]).toEqual([query, 'panevezys']);
  });

  it('is not the district, now that its mixed waste is covered too, or a town of it', () => {
    // "Panevėžio" alone is also Panevėžio sen., around the city, in the district.
    const queries = ['Panevėžio r.', 'Panevėžio rajonas', 'Panevėžio r. sav.', 'Panevėžys district', 'Panevėžio'];
    queries.push('Ramygala', 'Panevėžiukas', 'panevez', 'Pasvalys', 'Biržai', 'Rokiškis');
    for (const query of queries) expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
  });
});

describe('a search for a covered town', () => {
  // Their municipalities' schedules cover their private houses.
  it('gets no hint', () => {
    for (const query of ['Marijampolė', 'Marijampolės m.', 'Tauragė', 'Radviliškis', 'Telšiai', 'Druskininkai']) {
      expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
    }
  });

  it('gets no hint in the districts added later', () => {
    // Jonava and Kupiškis as whole towns (their files name no streets), Utena, Pabradė, Zarasai and
    // Krekenava by street; the others too.
    const towns = ['Jonava', 'Jonavos m.', 'Utena', 'Utenos m.', 'Raseiniai', 'Kretinga', 'Šilutė', 'Trakai', 'Lentvaris'];
    towns.push('Šalčininkai', 'Kėdainiai', 'Molėtai', 'Skuodas', 'Ukmergė', 'Anykščiai', 'Elektrėnai', 'Ignalina', 'Širvintos');
    towns.push('Kupiškis', 'Kupiškio m.', 'Švenčionys', 'Švenčionėliai', 'Pabradė', 'Zarasai', 'Dusetos', 'Krekenava');
    for (const query of towns) expect([query, uncoveredCitySearch(query)]).toEqual([query, undefined]);
  });
});

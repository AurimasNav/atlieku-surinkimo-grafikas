import { KAUNO_SOURCE_PAGE_URL, SOURCE_PAGE_URL } from './config';
import { isHousingChoice, pendingKinds, type Place, resolvePlace, sourcePageUrl, visibleKinds } from './resolve';
import type { Area, Location, ScheduleData } from './schedule';
import { searchAreas, searchLocations } from './schedule';

const today = '2026-10-11';
const future = ['2026-10-29'];

const area = (id: string, kind: Area['kind'], extra: Partial<Area> = {}): Area => ({
  id,
  kind,
  name: id,
  dates: future,
  ...extra,
});

const areas = [
  area('h-house', 'household', { group: 'Individualūs namai' }),
  area('h-flat', 'household', { group: 'Daugiabučiai namai' }),
  area('h-akaciju', 'household'),
  area('h-durpiu', 'household'),
  area('p-1', 'packaging'),
  area('p-2', 'packaging'),
  area('g-old', 'glass', { dates: ['2026-09-29'] }),
  area('g-1', 'glass'),
  // Newest quarter, but this place's pickup has already happened.
  area('g-between', 'glass', { dates: ['2026-10-05'], current: true }),
];

const locations: Location[] = [
  {
    id: 'g1',
    name: 'Aleksandravas',
    type: 'k.',
    district: 'Avižienių',
    schedule: { household: { area: 'h-house' }, packaging: { area: 'p-1' }, glass: { area: 'g-1' } },
  },
  {
    id: 'g2',
    name: 'Avižieniai',
    type: 'mstl.',
    district: 'Avižienių',
    streets: [
      ['s1', 'Akacijų akl.'],
      ['s2', 'Durpių g.'],
    ],
    schedule: {
      household: { streets: { s1: ['h-akaciju'], s2: ['h-durpiu'] } },
      packaging: { streets: { s1: ['p-1'] }, area: 'p-2' },
    },
  },
  {
    id: 'g3',
    name: 'Maišiagala',
    type: 'mstl.',
    district: 'Maišiagalos',
    schedule: { household: { candidates: ['h-house', 'h-flat'] }, glass: { area: 'g-old' } },
  },
  {
    id: 'g4',
    name: 'Arvydai',
    type: 'k.',
    district: 'Bezdonių',
    schedule: { glass: { area: 'g-between' } },
  },
];

const data: ScheduleData = {
  schemaVersion: 1,
  generatedAt: '',
  source: '',
  coverage: {},
  areas,
  locations,
};

const ids = (r: ReturnType<typeof resolvePlace>) => r.areas.map((a) => a.id);

describe('resolvePlace', () => {
  it('links one location to all three schedules', () => {
    const r = resolvePlace(data, { locationId: 'g1', choices: {} }, today);
    expect(ids(r)).toEqual(['h-house', 'p-1', 'g-1']);
    expect(pendingKinds(r)).toEqual([]);
  });

  it('uses the street where a schedule splits by street', () => {
    const r = resolvePlace(data, { locationId: 'g2', street: 's2', choices: {} }, today);
    expect(ids(r)).toEqual(['h-durpiu', 'p-2']); // s2 isn't listed for packaging: whole-town row
    expect(r.kinds.glass).toEqual({ status: 'none' }); // no glass collection listed here
  });

  it('asks when the street is unknown and rows differ', () => {
    const r = resolvePlace(data, { locationId: 'g2', choices: {} }, today);
    expect(r.kinds.household.status).toBe('choose');
    expect(pendingKinds(r)).toEqual(['household']);
  });

  it('asks house or apartment, and remembers the answer', () => {
    const asked = resolvePlace(data, { locationId: 'g3', choices: {} }, today);
    expect(asked.kinds.household.status).toBe('choose');
    if (asked.kinds.household.status === 'choose') {
      expect(isHousingChoice(asked.kinds.household.candidates)).toBe(true);
    }
    const answered = resolvePlace(data, { locationId: 'g3', choices: { household: 'h-flat' } }, today);
    expect(ids(answered)).toEqual(['h-flat']);
  });

  it('ignores rows whose dates are all past', () => {
    const r = resolvePlace(data, { locationId: 'g3', choices: { household: 'h-house' } }, today);
    expect(r.kinds.glass).toEqual({ status: 'none' });
  });

  it('keeps a current row between pickups', () => {
    const r = resolvePlace(data, { locationId: 'g4', choices: {} }, today);
    expect(r.kinds.glass).toMatchObject({ status: 'ok', area: { id: 'g-between' } });
    expect(pendingKinds(r)).toEqual([]);
  });

  it('respects "I don\'t have this container"', () => {
    const r = resolvePlace(data, { locationId: 'g1', choices: { packaging: null } }, today);
    expect(r.kinds.packaging).toEqual({ status: 'none', skipped: true });
    expect(ids(r)).toEqual(['h-house', 'g-1']);
  });

  it('reports a location that disappeared from newer data', () => {
    const r = resolvePlace(data, { locationId: 'gone', choices: {} }, today);
    expect(pendingKinds(r)).toEqual(['household', 'packaging', 'glass']);
  });

  it('adds food waste where the place has a schedule for it (Mažeikiai)', () => {
    const town: Location = {
      id: 'g9',
      name: 'Mažeikiai',
      type: 'm.',
      district: 'Mažeikių',
      provider: 'mazeikiai',
      streets: [
        ['s1', 'Žemaitės g.'],
        ['s2', 'Draugystės g.'],
      ],
      schedule: { household: { streets: { s1: ['h-house'] } }, food: { streets: { s1: ['f-1'] } } },
    };
    const withFood = { ...data, areas: [...areas, area('f-1', 'food')], locations: [...locations, town] };
    const r = resolvePlace(withFood, { locationId: 'g9', street: 's1', choices: {} }, today);
    expect(ids(r)).toEqual(['h-house', 'f-1']);
    expect(visibleKinds({ locationId: 'g9', choices: {} }, r)).toEqual(['household', 'packaging', 'glass', 'food']);
    // A street with an empty list has no pickups: nothing to choose from (apartment buildings).
    const flats = resolvePlace(
      { ...withFood, locations: [...locations, { ...town, schedule: { household: { streets: { s1: ['h-house'], s2: [] } } } }] },
      { locationId: 'g9', street: 's2', choices: {} },
      today,
    );
    expect(flats.kinds.household).toEqual({ status: 'none' });
    expect(pendingKinds(flats)).toEqual([]);
    // Without a street, the rows of the town are offered as before.
    const noStreet = resolvePlace(withFood, { locationId: 'g9', choices: {} }, today);
    expect(noStreet.kinds.food).toMatchObject({ status: 'ok', area: { id: 'f-1' } });
    // A food row picked by hand, without a location.
    expect(ids(resolvePlace(withFood, { choices: { food: 'f-1' } }, today))).toEqual(['f-1']);
    // Places without one aren't asked about it and don't show it.
    const village = resolvePlace(withFood, { locationId: 'g1', choices: {} }, today);
    expect(village.kinds.food).toEqual({ status: 'none' });
    expect(visibleKinds({ locationId: 'g1', choices: {} }, village)).toEqual(['household', 'packaging', 'glass']);
  });

  it('adds green waste where the place has a schedule for it (Klaipėdos r.)', () => {
    const village: Location = {
      id: 'g10',
      name: 'Ablinga',
      type: 'k.',
      district: 'Endriejavo',
      provider: 'klaipedos',
      schedule: { household: { area: 'h-house' }, green: { area: 'z-1' } },
    };
    // Green waste is collected from April to November: between seasons the row has only its
    // last date, and the place still shows it.
    const green = area('z-1', 'green', { dates: ['2026-09-25'], current: true });
    const withGreen = { ...data, areas: [...areas, green], locations: [...locations, village] };
    const r = resolvePlace(withGreen, { locationId: 'g10', choices: {} }, today);
    expect(r.kinds.green).toMatchObject({ status: 'ok', area: { id: 'z-1' } });
    expect(visibleKinds({ locationId: 'g10', choices: {} }, r)).toEqual(['household', 'packaging', 'glass', 'green']);
    // Without a green waste container, the user turns it off.
    const off = resolvePlace(withGreen, { locationId: 'g10', choices: { green: null } }, today);
    expect(off.kinds.green).toEqual({ status: 'none', skipped: true });
  });

  it('tells a street without pickups from one the routes leave out (Jurbarkas)', () => {
    const town: Location = {
      id: 'g11',
      name: 'Jurbarkas',
      type: 'm.',
      district: 'Jurbarko miesto',
      provider: 'jurbarkas',
      streets: [
        ['s1', 'Dainių g.'],
        ['s2', 'Bočių g.'],
        ['s3', 'Savanorių g.'],
      ],
      schedule: {
        household: { streets: { s1: ['h-akaciju'], s3: [] } },
        green: { streets: { s1: ['z-1'], s2: ['z-1'], s3: [] } },
      },
    };
    const routes = { ...data, areas: [...areas, area('z-1', 'green')], locations: [...locations, town] };
    const listed = resolvePlace(routes, { locationId: 'g11', street: 's1', choices: {} }, today);
    expect(ids(listed)).toEqual(['h-akaciju', 'z-1']);
    // No route of any kind names Savanorių g. (apartment buildings): no mixed or green waste pickup.
    const flats = resolvePlace(routes, { locationId: 'g11', street: 's3', choices: {} }, today);
    expect(flats.kinds.household).toEqual({ status: 'none' });
    expect(flats.kinds.green).toEqual({ status: 'none' });
    // Bočių g. has green waste but is in no mixed waste route: the town's routes are offered.
    const twoRoutes = { ...town, schedule: { ...town.schedule, household: { streets: { s1: ['h-akaciju'], s3: [], s4: ['h-durpiu'] } } } };
    const left = resolvePlace({ ...routes, locations: [...locations, twoRoutes] }, { locationId: 'g11', street: 's2', choices: {} }, today);
    expect(left.kinds.household).toMatchObject({ status: 'choose', candidates: [{ id: 'h-akaciju' }, { id: 'h-durpiu' }] });
    expect(left.kinds.green).toMatchObject({ status: 'ok', area: { id: 'z-1' } });
  });

  it('offers the route of farmsteads next to the usual one (Druskininkų sav.)', () => {
    // Druskininkai's file for garden communities, farmsteads and places that are hard to reach
    // is a group of its own: one more mixed waste choice where it lists a village or street.
    const group = 'Sodai, vienkiemiai ir sunkiai privažiuojamos valdos';
    const rows = [
      area('h-sodai', 'household', { group, district: 'Druskininkų sav.', provider: 'alytus' }),
      area('h-leipalingio', 'household', { district: 'Druskininkų sav.', provider: 'alytus' }),
      area('h-centras', 'household', { district: 'Druskininkų sav.', provider: 'alytus' }),
    ];
    const village: Location = {
      id: 'g12',
      name: 'Cimaniūnai',
      type: 'k.',
      district: 'Leipalingio',
      provider: 'alytus',
      schedule: { household: { candidates: ['h-sodai', 'h-leipalingio'] } },
    };
    const town: Location = {
      id: 'g13',
      name: 'Druskininkai',
      type: 'm.',
      district: 'Druskininkų miesto',
      provider: 'alytus',
      streets: [
        ['s1', 'Bijūnų g.'],
        ['s2', 'Vytauto g.'],
        ['s3', 'Ateities g.'],
      ],
      schedule: { household: { streets: { s1: ['h-sodai'], s2: ['h-centras'], s3: [] } } },
    };
    const druskininkai = { ...data, areas: [...areas, ...rows], locations: [...locations, village, town] };
    const asked = resolvePlace(druskininkai, { locationId: 'g12', choices: {} }, today);
    expect(asked.kinds.household).toMatchObject({ status: 'choose', candidates: [{ id: 'h-sodai' }, { id: 'h-leipalingio' }] });
    // Not "house or apartment?": the rows are listed, the group under the farmsteads' one.
    if (asked.kinds.household.status === 'choose') expect(isHousingChoice(asked.kinds.household.candidates)).toBe(false);
    expect(ids(resolvePlace(druskininkai, { locationId: 'g12', choices: { household: 'h-sodai' } }, today))).toEqual(['h-sodai']);
    // A street only the farmsteads' file names gets it; one no route names has no pickup.
    const street = (key: string) => resolvePlace(druskininkai, { locationId: 'g13', street: key, choices: {} }, today).kinds.household;
    expect(street('s1')).toMatchObject({ status: 'ok', area: { id: 'h-sodai' } });
    expect(street('s2')).toMatchObject({ status: 'ok', area: { id: 'h-centras' } });
    expect(street('s3')).toEqual({ status: 'none' });
  });

  it('supports rows picked by hand without a location', () => {
    const r = resolvePlace(data, { choices: { household: 'h-house', glass: 'g-old' } }, today);
    expect(ids(r)).toEqual(['h-house']);
    expect(r.kinds.glass.status).toBe('missing'); // hand-picked row is outdated: pick again
  });
});

describe('search', () => {
  it('finds locations without diacritics, name matches first', () => {
    expect(searchLocations(locations, 'aviz').map((l) => l.name)).toEqual(['Avižieniai', 'Aleksandravas']);
    expect(searchLocations(locations, '')).toEqual([]);
  });

  it('finds a town by its eldership and type, as in "Marijampolės m."', () => {
    const towns: Location[] = [
      ...locations,
      { id: 'm1', name: 'Marijampolė', type: 'm.', district: 'Marijampolės miesto', provider: 'marijampole' },
      { id: 'm2', name: 'Marijampolė', type: 'k.', district: 'Viekšnių', provider: 'mazeikiai' },
      { id: 'm3', name: 'Mokolai', type: 'k.', district: 'Marijampolės miesto', provider: 'marijampole' },
    ];
    expect(searchLocations(towns, 'Marijampolės m.').map((l) => l.id)).toEqual(['m1']);
    // The places named so first, then the others of the eldership.
    expect(searchLocations(towns, 'Marijampolė').map((l) => l.id)).toEqual(['m1', 'm2', 'm3']);
    expect(searchLocations(towns, 'aleksandravas k.').map((l) => l.id)).toEqual(['g1']);
  });

  it('searches the places of newer data, not the ones it sorted before', () => {
    expect(searchLocations(locations, 'avižien').map((l) => l.id)).toEqual(['g2', 'g1']);
    const newer = [...locations, { id: 'g5', name: 'Avižienėlė', type: 'k.', district: 'Avižienių' }];
    // Ė is an E: Avižienėlė before Avižieniai.
    expect(searchLocations(newer, 'avižien').map((l) => l.id)).toEqual(['g5', 'g2', 'g1']);
  });

  it('hides outdated rows in the manual row picker', () => {
    expect(searchAreas(areas, 'glass', '', today).map((a) => a.id)).toEqual(['g-1', 'g-between']);
  });

  it('lists the manual row picker in Lithuanian alphabetical order', () => {
    const named = ['Žvyriškių k.', 'S/B Beržas', 'Akmentiltis', 'Šumskas', 'Zujūnai', 'Čekoniškės'].map((name, i) =>
      area(`p-${i}`, 'packaging', { name }),
    );
    const names = (query: string) => searchAreas(named, 'packaging', query, today).map((a) => a.name);
    expect(names('')).toEqual(['Akmentiltis', 'Čekoniškės', 'S/B Beržas', 'Šumskas', 'Zujūnai', 'Žvyriškių k.']);
    // While searching, names that start with the query come first.
    expect(names('s')).toEqual(['S/B Beržas', 'Šumskas', 'Akmentiltis', 'Čekoniškės', 'Žvyriškių k.']);
  });
});

describe('custom schedules', () => {
  it('override the official row for that waste type only', () => {
    const r = resolvePlace(
      data,
      { locationId: 'g1', choices: {}, custom: { packaging: { start: '2026-10-14', every: 4, unit: 'week' } } },
      today,
    );
    expect(ids(r)).toEqual(['h-house', 'custom-packaging', 'g-1']);
    expect(r.kinds.packaging).toMatchObject({ status: 'ok', custom: true });
    if (r.kinds.packaging.status === 'ok') expect(r.kinds.packaging.area.dates.slice(0, 2)).toEqual(['2026-10-14', '2026-11-11']);
  });

  it('work without any official location', () => {
    const r = resolvePlace(data, { choices: {}, custom: { household: { start: '2026-10-15', every: 2, unit: 'week' } } }, today);
    expect(ids(r)).toEqual(['custom-household']);
    expect(r.kinds.glass).toEqual({ status: 'none' });
    expect(pendingKinds(r)).toEqual([]);
  });
});

describe('official schedule link', () => {
  const nkom = 'https://www.nkom.lt/kita.html';
  const twoCompanies: ScheduleData = {
    ...data,
    areas: [...areas, area('n-1', 'household', { provider: 'nemezio' })],
    locations: [
      ...locations,
      { id: 'n1', name: 'Nemėžis', type: 'k.', district: 'Nemėžio', provider: 'nemezio', schedule: { household: { area: 'n-1' } } },
    ],
    providers: [
      { id: 'nemencine', name: 'UAB „Nemenčinės komunalininkas“', url: SOURCE_PAGE_URL },
      { id: 'nemezio', name: 'UAB „Nemėžio komunalininkas“', url: nkom },
    ],
  };
  const link = (d: ScheduleData | null, place: Place | null) => sourcePageUrl(d, place, resolvePlace(d, place, today));

  it("opens the page of the place's company", () => {
    expect(link(twoCompanies, { locationId: 'n1', choices: {} })).toBe(nkom);
    expect(link(twoCompanies, { locationId: 'g1', choices: {} })).toBe(SOURCE_PAGE_URL);
  });

  it('follows a row picked by hand', () => {
    expect(link(twoCompanies, { choices: { household: 'n-1' } })).toBe(nkom);
  });

  it('opens the page a region file lists for its company', () => {
    const aratc = 'https://www.aratc.lt/atlieku-surinkimo-grafikai/';
    const region: ScheduleData = {
      ...twoCompanies,
      locations: [
        ...twoCompanies.locations!,
        { id: 'a1', name: 'Simnas', type: 'm.', district: 'Simno', provider: 'alytus', schedule: { household: { area: 'h-house' } } },
      ],
      providers: [...twoCompanies.providers!, { id: 'alytus', name: 'UAB „Alytaus regiono atliekų tvarkymo centras“', url: aratc }],
    };
    expect(link(region, { locationId: 'a1', choices: {} })).toBe(aratc);
  });

  it('opens a page over http, but no other kind of link', () => {
    // kupkom.lt's certificate is for another name, so the data links its page over http.
    const kupkom = 'http://www.kupkom.lt/atlieku-isvezimas/';
    const withUrl = (url: string): ScheduleData => ({
      ...twoCompanies,
      providers: [twoCompanies.providers![0], { id: 'nemezio', name: 'UAB „Nemėžio komunalininkas“', url }],
    });
    expect(link(withUrl(kupkom), { locationId: 'n1', choices: {} })).toBe(kupkom);
    for (const url of ['javascript:alert(1)', 'intent://x', 'file:///sdcard/x', 'www.nkom.lt', 'http:', 'https://', '']) {
      expect([url, link(withUrl(url), { locationId: 'n1', choices: {} })]).toEqual([url, SOURCE_PAGE_URL]);
    }
  });

  it('opens Nemenčinė for data and places without companies', () => {
    expect(link(data, { locationId: 'g1', choices: {} })).toBe(SOURCE_PAGE_URL);
    expect(link(twoCompanies, null)).toBe(SOURCE_PAGE_URL);
    expect(link(null, { locationId: 'n1', choices: {} })).toBe(SOURCE_PAGE_URL);
    const unknown = { ...twoCompanies, providers: [] };
    expect(link(unknown, { locationId: 'n1', choices: {} })).toBe(SOURCE_PAGE_URL);
  });

  it('opens Kauno švara for a Kauno r. address', () => {
    const kauno = { eldership: 'ringaudu', eldershipName: 'Ringaudų', town: 'Ringaudai', street: '', house: '' };
    expect(link(twoCompanies, { kauno, choices: {} })).toBe(KAUNO_SOURCE_PAGE_URL);
  });
});

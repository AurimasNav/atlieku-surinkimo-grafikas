import { KAUNO_SOURCE_PAGE_URL, SOURCE_PAGE_URL } from './config';
import { isHousingChoice, pendingKinds, type Place, resolvePlace, sourcePageUrl } from './resolve';
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

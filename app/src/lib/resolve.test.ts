import { isHousingChoice, pendingKinds, resolvePlace } from './resolve';
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
    expect(searchAreas(areas, 'glass', '', today).map((a) => a.id)).toEqual(['g-1']);
  });
});

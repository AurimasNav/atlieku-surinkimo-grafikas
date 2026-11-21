import { checkOverdue, staleSources } from './freshness';
import type { Resolved } from './resolve';
import type { ScheduleData } from './schedule';

const now = new Date('2026-11-21T10:00:00Z');

const data: ScheduleData = {
  schemaVersion: 1,
  generatedAt: '2026-11-21T04:20:00Z',
  source: '',
  coverage: {},
  areas: [],
  providers: [
    { id: 'nemencine', name: 'UAB „Nemenčinės komunalininkas“', url: 'https://www.nemenkom.lt/', generatedAt: '2026-11-10T04:20:00Z' },
    { id: 'nemezio', name: 'UAB „Nemėžio komunalininkas“', url: 'https://www.nkom.lt/kita.html', generatedAt: '2026-11-21T04:20:00Z' },
  ],
};

const resolvedWith = (...providers: (string | undefined)[]): Resolved =>
  ({
    kinds: {},
    areas: providers.map((provider, i) => ({ id: `a${i}`, kind: 'household', name: '', dates: [], provider })),
  }) as unknown as Resolved;

describe('staleSources', () => {
  it('names the companies whose data is over a week old', () => {
    expect(staleSources(data, { choices: {} }, resolvedWith(undefined, 'nemezio'), now)).toEqual([
      { name: 'UAB „Nemenčinės komunalininkas“', url: 'https://www.nemenkom.lt/', since: '2026-11-10T04:20:00Z' },
    ]);
  });

  it('is quiet when the data is fresh or the schedules are the user’s own', () => {
    expect(staleSources(data, { choices: {} }, resolvedWith('nemezio'), now)).toEqual([]);
    expect(
      staleSources(data, { choices: {} }, { kinds: {}, areas: [{ id: 'custom-glass', kind: 'glass', name: '', dates: [] }] } as unknown as Resolved, now),
    ).toEqual([]);
  });

  it('uses the Kauno švara build time for a Kauno r. address', () => {
    const kauno = { eldership: 'e', eldershipName: 'E', town: 'T', street: '', house: '' };
    const withPersonal = { ...data, personals: [{ key: 'e|T||', areas: [], generatedAt: '2026-11-01T04:20:00Z' }] };
    expect(staleSources(withPersonal, { kauno, choices: {} }, resolvedWith(), now)).toEqual([
      { name: 'UAB „Kauno švara“', url: 'https://grafikai.svara.lt/', since: '2026-11-01T04:20:00Z' },
    ]);
  });
});

describe('checkOverdue', () => {
  it('is true after three days without a check', () => {
    expect(checkOverdue('2026-11-17T09:00:00Z', now)).toBe(true);
    expect(checkOverdue('2026-11-19T09:00:00Z', now)).toBe(false);
    expect(checkOverdue(undefined, now)).toBe(false);
  });
});

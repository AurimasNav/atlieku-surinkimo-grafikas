import { SOURCE_PAGE_URL } from './config';
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

  it('names the company and page a region file lists, and skips one it does not', () => {
    const sratc = 'https://www.sratc.lt/kalendoriaus-grafikai/';
    const regions: ScheduleData = {
      ...data,
      providers: [
        ...data.providers!,
        { id: 'siauliai', name: 'UAB „Šiaulių regiono atliekų tvarkymo centras“', url: sratc, generatedAt: '2026-11-01T16:48:12Z' },
      ],
    };
    expect(staleSources(regions, { choices: {} }, resolvedWith('siauliai', 'not-listed'), now)).toEqual([
      { name: 'UAB „Šiaulių regiono atliekų tvarkymo centras“', url: sratc, since: '2026-11-01T16:48:12Z' },
    ]);
  });

  it("links the company's page over http, as the data has kupkom.lt's", () => {
    const kupkom = 'http://www.kupkom.lt/atlieku-isvezimas/';
    const regions: ScheduleData = {
      ...data,
      providers: [
        ...data.providers!,
        { id: 'kupiskis', name: 'UAB „Kupiškio komunalininkas“', url: kupkom, generatedAt: '2026-11-01T13:28:33Z' },
        { id: 'odd', name: 'Odd', url: 'javascript:alert(1)', generatedAt: '2026-11-01T13:28:33Z' },
      ],
    };
    expect(staleSources(regions, { choices: {} }, resolvedWith('kupiskis', 'odd'), now)).toEqual([
      { name: 'UAB „Kupiškio komunalininkas“', url: kupkom, since: '2026-11-01T13:28:33Z' },
      { name: 'Odd', url: SOURCE_PAGE_URL, since: '2026-11-01T13:28:33Z' },
    ]);
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

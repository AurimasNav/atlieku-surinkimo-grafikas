import { type KaunoAddress, kaunoKey } from '@/lib/kauno';
import type { ScheduleData } from '@/lib/schedule';

import { useSchedule } from './schedule';
import { useSettings } from './settings';

jest.mock('@/lib/storage', () => ({
  storage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
}));

const data: ScheduleData = { schemaVersion: 1, generatedAt: '', source: '', coverage: {}, areas: [], locations: [] };
const saved: KaunoAddress = {
  eldership: 'akademijos',
  eldershipName: 'Akademijos sen.',
  town: 'Akademija',
  street: 'Vynuogyno g.',
  house: '9',
};
const files: Record<string, unknown> = {
  'kauno-r/schedule.json': {
    schemaVersion: 1,
    generatedAt: '',
    areas: [{ id: 'kh', kind: 'household', rule: 'kas 14 dienų', dates: ['2026-11-25'] }],
    elderships: [{ id: 'akademijos', name: 'Akademijos sen.', towns: ['Akademijos mstl.'] }],
  },
  'kauno-r/addresses/akademijos.json': {
    eldership: 'Akademijos sen.',
    towns: { 'Akademijos mstl.': { 'Vynuogyno g.': { '9': [0] } } },
    aliases: { Akademija: { 'Vynuogyno g.': { '9': ['akademijos', 'Akademijos mstl.', 'Vynuogyno g.', '9'] } } },
  },
  'schedule.json': data,
};

beforeEach(() => {
  globalThis.fetch = jest.fn(async (url: string) => {
    const file = Object.keys(files).find((name) => String(url).endsWith(`atlieku-surinkimo-grafikas/${name}`));
    return file
      ? { ok: true, status: 200, headers: { get: (): null => null }, json: async () => files[file] }
      : { ok: false, status: 404, headers: { get: (): null => null } };
  }) as unknown as typeof fetch;
});

describe('other regions', () => {
  const region = (dates: string[]) => ({
    ...data,
    providers: [{ id: 'mazeikiai', name: 'TRATC', url: 'https://tratc.lt/' }],
    areas: [{ id: 'f-1', kind: 'food', name: 'Žemaitės g.', dates, provider: 'mazeikiai' }],
    locations: [{ id: 'g2', name: 'Mažeikiai', type: 'm.', district: 'Mažeikių', provider: 'mazeikiai' }],
  });
  const main: ScheduleData = {
    ...data,
    areas: [{ id: 'h-1', kind: 'household', name: 'Riešė', dates: ['2026-11-20'] }],
    locations: [{ id: 'g1', name: 'Riešė', type: 'k.', district: 'Riešės' }],
  };
  const ids = () => useSchedule.getState().data?.areas.map((area) => area.id);

  beforeEach(() => {
    useSettings.setState({ place: null });
    useSchedule.setState({ data: null, etag: undefined, regions: undefined });
    files['schedule.json'] = main;
    files['mazeikiu-r/schedule.json'] = region(['2026-11-24']);
  });
  afterEach(() => {
    files['schedule.json'] = data;
    delete files['mazeikiu-r/schedule.json'];
  });

  it('are merged into one list of places and rows', async () => {
    expect(await useSchedule.getState().refresh()).toBe(true);
    const merged = useSchedule.getState().data;
    expect(ids()).toEqual(['h-1', 'f-1']);
    expect(merged?.locations?.map((location) => location.name)).toEqual(['Riešė', 'Mažeikiai']);
    expect(merged?.providers?.map((provider) => provider.id)).toEqual(['mazeikiai']);
  });

  it('are replaced, not added twice, when their file changes', async () => {
    await useSchedule.getState().refresh();
    files['mazeikiu-r/schedule.json'] = region(['2026-12-08']);
    await useSchedule.getState().refresh();
    expect(ids()).toEqual(['h-1', 'f-1']);
    expect(useSchedule.getState().data?.areas[1].dates).toEqual(['2026-12-08']);
  });

  it('keep their saved part when their file cannot be downloaded', async () => {
    await useSchedule.getState().refresh();
    delete files['mazeikiu-r/schedule.json'];
    files['schedule.json'] = { ...main, generatedAt: 'later' };
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(useSchedule.getState().data?.generatedAt).toBe('later');
    expect(ids()).toEqual(['h-1', 'f-1']);
    expect(useSchedule.getState().error).toBeNull();
  });

  it('are only downloaded again when their file changed', async () => {
    // A server that answers 304 to the ETag it gave.
    const etags: Record<string, string> = { 'schedule.json': 'm1', 'mazeikiu-r/schedule.json': 'r1' };
    const sent: Record<string, string | undefined> = {};
    globalThis.fetch = jest.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
      const name = Object.keys(etags).find((file) => String(url).endsWith(`atlieku-surinkimo-grafikas/${file}`))!;
      sent[name] = init?.headers?.['If-None-Match'];
      const headers = { get: () => etags[name] };
      return sent[name] === etags[name]
        ? { ok: false, status: 304, headers }
        : { ok: true, status: 200, headers, json: async () => files[name] };
    }) as unknown as typeof fetch;

    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(sent).toEqual({ 'schedule.json': undefined, 'mazeikiu-r/schedule.json': undefined });
    // Nothing changed: both answer 304.
    expect(await useSchedule.getState().refresh()).toBe(false);
    expect(sent).toEqual({ 'schedule.json': 'm1', 'mazeikiu-r/schedule.json': 'r1' });
    expect(ids()).toEqual(['h-1', 'f-1']);

    // Only the region changed.
    etags['mazeikiu-r/schedule.json'] = 'r2';
    files['mazeikiu-r/schedule.json'] = region(['2026-12-08']);
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(useSchedule.getState().data?.areas.map((area) => area.dates[0])).toEqual(['2026-11-20', '2026-12-08']);
    expect(useSchedule.getState().etag).toBe('m1');

    // Only the main file changed: the region's saved part moves into the new data.
    etags['schedule.json'] = 'm2';
    files['schedule.json'] = { ...main, generatedAt: 'later' };
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(useSchedule.getState().data?.generatedAt).toBe('later');
    expect(useSchedule.getState().data?.areas.map((area) => area.dates[0])).toEqual(['2026-11-20', '2026-12-08']);
    expect(useSchedule.getState().regions).toEqual({
      [Object.keys(useSchedule.getState().regions!)[0]]: { etag: 'r2', providers: ['mazeikiai'] },
    });
  });

  it('drop the rows of a company their file no longer lists', async () => {
    await useSchedule.getState().refresh();
    const renamed = region(['2026-12-08']);
    files['mazeikiu-r/schedule.json'] = {
      ...renamed,
      providers: [{ ...renamed.providers[0], id: 'tratc' }],
      areas: renamed.areas.map((area) => ({ ...area, id: 'f-2', provider: 'tratc' })),
      locations: renamed.locations.map((location) => ({ ...location, provider: 'tratc' })),
    };
    await useSchedule.getState().refresh();
    expect(ids()).toEqual(['h-1', 'f-2']);
    expect(useSchedule.getState().data?.providers?.map((provider) => provider.id)).toEqual(['tratc']);
  });

  it('do not hold back the main data when they were never downloaded', async () => {
    delete files['mazeikiu-r/schedule.json'];
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(ids()).toEqual(['h-1']);
  });
});

describe('refreshing a Kauno r. address', () => {
  it('moves an address saved with a merged spelling to the one the data uses now', async () => {
    useSettings.setState({ place: { kauno: saved, choices: { green: null } } });
    useSchedule.setState({ data, etag: undefined });
    await useSchedule.getState().refresh();
    const place = useSettings.getState().place;
    expect(place?.kauno).toEqual({ ...saved, town: 'Akademijos mstl.' });
    // Answers given for the address stay.
    expect(place?.choices).toEqual({ green: null });
    expect(useSchedule.getState().data?.personals).toEqual([
      {
        key: 'akademijos|Akademijos mstl.|Vynuogyno g.|9',
        areas: [expect.objectContaining({ kind: 'household', dates: ['2026-11-25'] })],
        generatedAt: '',
      },
    ]);
  });

  it('keeps the schedules of every saved place, and those of a place it could not download', async () => {
    const other = { ...saved, town: 'Akademijos mstl.', house: '11' };
    const keptAreas = [{ id: 'old', kind: 'household' as const, name: '', dates: ['2026-11-30'] }];
    useSettings.setState({
      place: { kauno: saved, choices: {} },
      otherPlaces: [{ id: 'summer', place: { kauno: other, choices: {} } }],
    });
    useSchedule.setState({ data: { ...data, personal: { key: kaunoKey(other), areas: keptAreas } }, etag: undefined });
    await useSchedule.getState().refresh();
    const personals = useSchedule.getState().data?.personals ?? [];
    expect(personals.map((p) => p.key)).toEqual(['akademijos|Akademijos mstl.|Vynuogyno g.|9', kaunoKey(other)]);
    // House 11 isn't in the address file: the dates saved before stay.
    expect(personals[1].areas).toEqual(keptAreas);
    expect(useSchedule.getState().data?.personal).toBeUndefined();
  });
});

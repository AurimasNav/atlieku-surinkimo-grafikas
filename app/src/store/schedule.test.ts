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

describe('other regions', () => {
  beforeEach(() => {
    useSettings.setState({ place: null });
    useSchedule.setState({ data: null, etag: undefined, regions: undefined });
    files['schedule.json'] = main;
    files['mazeikiu-r/schedule.json'] = region(['2026-11-24']);
  });
  afterEach(() => {
    files['schedule.json'] = data;
    delete files['mazeikiu-r/schedule.json'];
    delete files['klaipedos-r/schedule.json'];
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

  it('are merged each on its own', async () => {
    files['klaipedos-r/schedule.json'] = {
      ...data,
      providers: [{ id: 'klaipedos', name: 'Gargždų švara', url: 'https://www.gargzdusvara.eu/' }],
      areas: [{ id: 'z-1', kind: 'green', name: 'Ablingos k.', dates: ['2026-11-27'], provider: 'klaipedos' }],
      locations: [{ id: 'g3', name: 'Ablinga', type: 'k.', district: 'Endriejavo', provider: 'klaipedos' }],
    };
    await useSchedule.getState().refresh();
    expect(ids()).toEqual(['h-1', 'f-1', 'z-1']);
    // One region's file can't be downloaded: its saved part stays, the other one is updated.
    delete files['klaipedos-r/schedule.json'];
    files['mazeikiu-r/schedule.json'] = region(['2026-12-08']);
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(ids()).toEqual(['h-1', 'f-1', 'z-1']);
    expect(useSchedule.getState().data?.areas[1].dates).toEqual(['2026-12-08']);
    expect(useSchedule.getState().data?.providers?.map((provider) => provider.id)).toEqual(['mazeikiai', 'klaipedos']);
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
      const name = Object.keys(etags).find((file) => String(url).endsWith(`atlieku-surinkimo-grafikas/${file}`));
      if (!name) return { ok: false, status: 404, headers: { get: (): null => null } }; // the other regions
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

describe('regions.json', () => {
  // A region folder this app version doesn't have in config.REGION_URLS.
  const panevezys = (dates: string[]) => ({
    ...data,
    providers: [{ id: 'panevezys', name: 'PRATC', url: 'https://www.pratc.lt/' }],
    areas: [{ id: 'p-1', kind: 'household', name: 'Velžys', dates, provider: 'panevezys' }],
    locations: [{ id: 'g4', name: 'Velžys', type: 'k.', district: 'Velžio', provider: 'panevezys' }],
  });
  const settlements = (path: string, providers: string[]) => ({
    path,
    kind: 'settlements',
    files: ['schedule.json', 'addresses.json'],
    providers,
  });
  const listing = (...regions: object[]) => ({
    schemaVersion: 1,
    regions: [settlements('', ['nemencine']), settlements('mazeikiu-r/', ['mazeikiai']), ...regions],
  });
  const dates = (id: string) => useSchedule.getState().data?.areas.find((area) => area.id === id)?.dates;
  const added = ['regions.json', 'mazeikiu-r/schedule.json', 'panevezio-ratc/schedule.json', 'naujas/schedule.json'];

  beforeEach(() => {
    useSettings.setState({ place: null });
    useSchedule.setState({ data: null, etag: undefined, regions: undefined, index: undefined, indexEtag: undefined });
    files['schedule.json'] = main;
    files['mazeikiu-r/schedule.json'] = region(['2026-11-24']);
    files['panevezio-ratc/schedule.json'] = panevezys(['2026-11-26']);
    files['regions.json'] = listing(settlements('panevezio-ratc/', ['panevezys']));
  });
  afterEach(() => {
    files['schedule.json'] = data;
    for (const name of added) delete files[name];
    useSchedule.setState({ regions: undefined, index: undefined, indexEtag: undefined });
  });

  it('adds the regions only the index lists, and saves the index', async () => {
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(ids()).toEqual(['h-1', 'f-1', 'p-1']);
    expect(useSchedule.getState().data?.providers?.map((provider) => provider.id)).toEqual(['mazeikiai', 'panevezys']);
    expect(useSchedule.getState().index?.regions.map((entry) => entry.path)).toEqual(['', 'mazeikiu-r/', 'panevezio-ratc/']);
  });

  it('downloads the built-in regions when there is no index', async () => {
    delete files['regions.json'];
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(ids()).toEqual(['h-1', 'f-1']);
    expect(useSchedule.getState().index).toBeUndefined();
    expect(useSchedule.getState().error).toBeNull();
  });

  it('uses the saved index when regions.json cannot be downloaded', async () => {
    await useSchedule.getState().refresh();
    delete files['regions.json'];
    files['panevezio-ratc/schedule.json'] = panevezys(['2026-12-10']);
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(dates('p-1')).toEqual(['2026-12-10']);
    expect(useSchedule.getState().index?.regions).toHaveLength(3);
    expect(useSchedule.getState().error).toBeNull();
  });

  it('keeps the saved part of a region of the index that cannot be downloaded', async () => {
    await useSchedule.getState().refresh();
    delete files['panevezio-ratc/schedule.json'];
    files['schedule.json'] = { ...main, generatedAt: 'later' };
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(useSchedule.getState().data?.generatedAt).toBe('later');
    expect(ids()).toEqual(['h-1', 'f-1', 'p-1']);
  });

  it('skips the regions and fields it does not know, and reads the rest', async () => {
    files['naujas/schedule.json'] = panevezys(['2026-11-30']);
    files['regions.json'] = {
      ...listing(
        { path: 'kauno-r/', kind: 'addresses', files: ['schedule.json', 'points.json'], elderships: ['akademijos'] },
        { path: 'naujas/', kind: 'routes', files: ['schedule.json', 'routes.json'], providers: ['naujas'] },
        { ...settlements('panevezio-ratc/', ['panevezys']), municipalities: ['Panevėžio r.'], bytes: 1024 },
      ),
      generatedAt: '2026-11-22T04:30:00+00:00',
      checksums: { 'schedule.json': 'abc' },
    };
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(ids()).toEqual(['h-1', 'f-1', 'p-1']);
    const requested = jest.mocked(globalThis.fetch).mock.calls.map(([url]) => String(url));
    expect(requested.filter((url) => url.includes('/naujas/'))).toEqual([]);
    expect(useSchedule.getState().index?.regions.map((entry) => entry.path)).toEqual(['', 'mazeikiu-r/', 'panevezio-ratc/']);
  });

  it('keeps the saved index when regions.json is of a newer format', async () => {
    await useSchedule.getState().refresh();
    files['regions.json'] = { schemaVersion: 2, regions: [] };
    files['panevezio-ratc/schedule.json'] = panevezys(['2026-12-10']);
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(dates('p-1')).toEqual(['2026-12-10']);
    expect(useSchedule.getState().index?.schemaVersion).toBe(1);
  });

  it('takes a region a newer index no longer lists off the phone, but not a built-in one', async () => {
    await useSchedule.getState().refresh();
    files['regions.json'] = { schemaVersion: 1, regions: [settlements('', ['nemencine'])] };
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(ids()).toEqual(['h-1', 'f-1']);
    expect(useSchedule.getState().data?.locations?.map((location) => location.id)).toEqual(['g1', 'g2']);
    expect(useSchedule.getState().data?.providers?.map((provider) => provider.id)).toEqual(['mazeikiai']);
    expect(Object.keys(useSchedule.getState().regions ?? {}).some((url) => url.endsWith('/panevezio-ratc'))).toBe(false);
  });

  it('costs a 304 and no parsing for each file that has not changed', async () => {
    // A server that answers 304 to the ETag it gave, and notes which files were read.
    const etags: Record<string, string> = {
      'schedule.json': 'm1',
      'regions.json': 'i1',
      'mazeikiu-r/schedule.json': 'r1',
      'panevezio-ratc/schedule.json': 'p1',
    };
    const sent: Record<string, string | undefined> = {};
    const read: string[] = [];
    globalThis.fetch = jest.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
      const name = Object.keys(etags).find((file) => String(url).endsWith(`atlieku-surinkimo-grafikas/${file}`));
      if (!name) return { ok: false, status: 404, headers: { get: (): null => null } }; // the other regions
      sent[name] = init?.headers?.['If-None-Match'];
      const headers = { get: () => etags[name] };
      if (sent[name] === etags[name]) return { ok: false, status: 304, headers };
      return { ok: true, status: 200, headers, json: async () => (read.push(name), files[name]) };
    }) as unknown as typeof fetch;

    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(read.sort()).toEqual(Object.keys(etags).sort());
    expect(useSchedule.getState().indexEtag).toBe('i1');

    // Nothing changed: every file answers 304, and none is read.
    read.length = 0;
    expect(await useSchedule.getState().refresh()).toBe(false);
    expect(sent).toEqual({
      'schedule.json': 'm1',
      'regions.json': 'i1',
      'mazeikiu-r/schedule.json': 'r1',
      'panevezio-ratc/schedule.json': 'p1',
    });
    expect(read).toEqual([]);
    expect(ids()).toEqual(['h-1', 'f-1', 'p-1']);
    expect(useSchedule.getState().index?.regions).toHaveLength(3);

    // A deploy that only changed the region of the index: just its file is read again.
    etags['panevezio-ratc/schedule.json'] = 'p2';
    files['panevezio-ratc/schedule.json'] = panevezys(['2026-12-10']);
    expect(await useSchedule.getState().refresh()).toBe(true);
    expect(read).toEqual(['panevezio-ratc/schedule.json']);
    expect(dates('p-1')).toEqual(['2026-12-10']);
    expect(dates('f-1')).toEqual(['2026-11-24']);
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

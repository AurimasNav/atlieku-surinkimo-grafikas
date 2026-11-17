import type { KaunoAddress } from '@/lib/kauno';
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
    const file = Object.keys(files).find((name) => String(url).endsWith(`/${name}`));
    return file
      ? { ok: true, status: 200, headers: { get: (): null => null }, json: async () => files[file] }
      : { ok: false, status: 404, headers: { get: (): null => null } };
  }) as unknown as typeof fetch;
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
    expect(useSchedule.getState().data?.personal).toEqual({
      key: 'akademijos|Akademijos mstl.|Vynuogyno g.|9',
      areas: [expect.objectContaining({ kind: 'household', dates: ['2026-11-25'] })],
    });
  });
});

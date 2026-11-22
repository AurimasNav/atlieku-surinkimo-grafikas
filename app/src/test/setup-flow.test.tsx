/**
 * The setup screens together, with the real router: search a place, answer what it asks, and
 * finish. Network, notifications and native pickers are stubbed; the data is made up.
 */
import ChooseRow from '@/app/setup/choose/[kind]';
import SetupDone from '@/app/setup/done';
import ChooseLocation from '@/app/setup/location';
import ChooseStreet from '@/app/setup/street';
import i18n from '@/i18n';
import type { ScheduleData } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { Stack } from 'expo-router';
import { act, fireEvent, renderRouter, screen } from 'expo-router/testing-library';

jest.mock('@/lib/storage', () => ({
  storage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
}));
jest.mock('@/lib/notifications', () => ({
  requestNotificationPermission: jest.fn(async () => true),
}));
jest.mock('@expo/ui/community/datetime-picker', () => ({ DateTimePicker: () => null }));
const mockLocateHome = jest.fn();
jest.mock('@/lib/geolocate', () => ({ locateHome: () => mockLocateHome() }));
// expo-router/testing-library replaces Reanimated with the package's mock, which doesn't load
// here; the screens are imported first, so they keep this one (see reanimated-mock.ts).
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('react-native-reanimated', () => require('./reanimated-mock'));

const future = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};

const data: ScheduleData = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  source: '',
  coverage: {},
  areas: [
    { id: 'h1', kind: 'household', name: 'Riešė', dates: [future(3)] },
    { id: 'h2', kind: 'household', name: 'Pikeliškės, Lauko g.', dates: [future(4)] },
    { id: 'h3', kind: 'household', name: 'Pikeliškės, kitos gatvės', dates: [future(5)] },
    { id: 'p1', kind: 'packaging', name: 'Avižienių sen.', dates: [future(6)] },
    { id: 'p2', kind: 'packaging', name: 'Avižienių sen. II', dates: [future(7)] },
    { id: 'g1', kind: 'glass', name: 'Avižienių sen.', dates: [future(20)] },
  ],
  locations: [
    {
      id: 'riese',
      name: 'Riešė',
      type: 'k.',
      district: 'Avižienių',
      schedule: { household: { area: 'h1' }, packaging: { area: 'p1' }, glass: { area: 'g1' } },
    },
    {
      id: 'pikeliskes',
      name: 'Pikeliškės',
      type: 'k.',
      district: 'Avižienių',
      streets: [
        ['lauko', 'Lauko g.'],
        ['miško', 'Miško g.'],
      ],
      schedule: {
        household: { area: 'h3', streets: { lauko: ['h2'] } },
        packaging: { candidates: ['p1', 'p2'] },
        glass: { area: 'g1' },
      },
    },
  ],
};

const routes = {
  _layout: () => <Stack screenOptions={{ headerShown: false }} />,
  index: () => null,
  'setup/location': ChooseLocation,
  'setup/street': ChooseStreet,
  'setup/choose/[kind]': ChooseRow,
  'setup/done': SetupDone,
};

beforeAll(async () => {
  await i18n.changeLanguage('en');
});

beforeEach(() => {
  // Kauno r. towns aren't needed here: their download just fails.
  globalThis.fetch = jest.fn(async () => ({ ok: false, status: 404, headers: { get: () => null } })) as unknown as typeof fetch;
  useSchedule.setState({ data, error: null, refreshing: false });
  useSettings.setState({ onboarded: false, place: null, placeId: 'home', otherPlaces: [] });
});

async function search(text: string) {
  await act(async () => fireEvent.changeText(await screen.findByPlaceholderText(i18n.t('setup.locationPlaceholder')), text));
}

/** Presses and lets the navigation it starts finish. */
async function press(text: string) {
  const element = await screen.findByText(text);
  await act(async () => fireEvent.press(element));
}

it('finishes setup for a place with one schedule of each type', async () => {
  const router = await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('ries');
  await press('Riešė');

  expect(router.getPathname()).toBe('/setup/done');
  expect(screen.getByText(i18n.t('setup.doneTitle'))).toBeOnTheScreen();
  // Every waste type says when it's collected next.
  expect(screen.getAllByText(/^Next: /)).toHaveLength(3);

  await press(i18n.t('setup.enable'));
  expect(useSettings.getState().onboarded).toBe(true);
  expect(useSettings.getState().place).toEqual({ locationId: 'riese', street: undefined, choices: {}, custom: undefined });
  expect(router.getPathname()).toBe('/');
});

it('asks for the street and the row when the place has several', async () => {
  const router = await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('pikel');
  await press('Pikeliškės');

  expect(router.getPathname()).toBe('/setup/street');
  await press('Lauko g.');

  // Two packaging rows match: the user picks theirs.
  expect(router.getPathname()).toBe('/setup/choose/packaging');
  await press('Avižienių sen. II');

  expect(router.getPathname()).toBe('/setup/done');
  expect(useSettings.getState().place).toMatchObject({ locationId: 'pikeliskes', street: 'lauko', choices: { packaging: 'p2' } });
});

it('offers to ask for the area when nothing is found', async () => {
  await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('Zarasai');
  expect(await screen.findByText(i18n.t('setup.locationNone', { areas: i18n.t('coverage.areas') }))).toBeOnTheScreen();
  expect(screen.getByText(i18n.t('feedback.area'))).toBeOnTheScreen();
});

it('says that Klaipėda city is not covered', async () => {
  await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('Klaipėda');
  expect(await screen.findByText(i18n.t('setup.locationKlaipedaCity'))).toBeOnTheScreen();
});

it('says that Vilnius city is not covered', async () => {
  await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('Vilnius');
  expect(await screen.findByText(i18n.t('setup.locationVilniusCity'))).toBeOnTheScreen();
  expect(screen.queryByText(i18n.t('setup.locationNone', { areas: i18n.t('coverage.areas') }))).toBeNull();
});

it('says that Šiauliai city is not covered above a village of that name', async () => {
  // A village of Jurbarko r. is called Šiauliai.
  const village = { id: 'g1', name: 'Šiauliai', type: 'k.', district: 'Veliuonos', provider: 'jurbarkas' };
  useSchedule.setState({ data: { ...data, locations: [...data.locations!, village] } });
  await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('Šiauliai');
  expect(await screen.findByText(i18n.t('setup.locationSiauliaiCity'))).toBeOnTheScreen();
  expect(screen.getByText('Veliuonos sen. · k.')).toBeOnTheScreen();
  expect(screen.queryByText(i18n.t('feedback.area'))).toBeNull();
});

it('says that Panevėžys city is not covered, and the district only for packaging and glass', async () => {
  // A village of Panevėžio sen., in Panevėžio r., with packaging only.
  const village = { id: 'p9', name: 'Berniūnai', type: 'k.', district: 'Panevėžio', provider: 'panevezio-r', schedule: { packaging: { area: 'p1' } } };
  useSchedule.setState({ data: { ...data, locations: [...data.locations!, village] } });
  await renderRouter(routes, { initialUrl: '/setup/location' });
  for (const query of ['Panevėžys', 'Panevėžio r.']) {
    await search(query);
    expect(await screen.findByText(i18n.t('setup.locationPanevezysCity'))).toBeOnTheScreen();
    expect(screen.queryByText(i18n.t('setup.locationNone', { areas: i18n.t('coverage.areas') }))).toBeNull();
  }
  // Above the villages of Panevėžio sen.
  await search('Panevėžio');
  expect(await screen.findByText(i18n.t('setup.locationPanevezysCity'))).toBeOnTheScreen();
  expect(screen.getByText('Berniūnai')).toBeOnTheScreen();
});

describe('a town of the Kauno švara data', () => {
  const index = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    areas: [],
    elderships: [
      { id: 'ringaudu', name: 'Ringaudų sen.', towns: ['Ringaudų k.'], registerNames: { 'Ringaudų k.': 'Ringaudai' } },
      {
        id: 'ziezmariu',
        name: 'Žiežmarių sen.',
        municipality: 'Kaišiadorių r.',
        towns: ['Žiežmarių mstl.'],
        registerNames: { 'Žiežmarių mstl.': 'Žiežmariai' },
      },
    ],
  };

  beforeEach(() => {
    const headers = { get: (): null => null };
    globalThis.fetch = jest.fn(async (url: string) =>
      String(url).endsWith('kauno-r/schedule.json')
        ? { ok: true, status: 200, json: async () => index, headers }
        : { ok: false, status: 404, headers },
    ) as unknown as typeof fetch;
  });

  it('is shown with its municipality', async () => {
    await renderRouter(routes, { initialUrl: '/setup/location' });
    await search('Žiežmariai');
    expect(await screen.findByText('Žiežmariai · Žiežmarių sen. · Kaišiadorių r.')).toBeOnTheScreen();
    await search('Ringaudai');
    expect(await screen.findByText('Ringaudai · Ringaudų sen. · Kauno r.')).toBeOnTheScreen();
  });

  it('is found by location with its municipality', async () => {
    mockLocateHome.mockResolvedValue({
      ok: true,
      kauno: { eldership: 'ziezmariu', eldershipName: 'Žiežmarių sen.', town: 'Žiežmarių mstl.', street: 'Vytauto g.', house: '1' },
      street: 'ok',
    });
    await renderRouter(routes, { initialUrl: '/setup/location' });
    // The list of towns, which says which municipality an eldership is in, is downloaded first.
    await search('Žiežmariai');
    await screen.findByText('Žiežmariai · Žiežmarių sen. · Kaišiadorių r.');
    await press(i18n.t('setup.useLocation'));
    expect(await screen.findByText('Žiežmarių mstl., Žiežmarių sen. · Kaišiadorių r.')).toBeOnTheScreen();
  });
});

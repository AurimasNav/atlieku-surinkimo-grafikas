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
  await search('Trakai');
  expect(await screen.findByText(i18n.t('setup.locationNone'))).toBeOnTheScreen();
  expect(screen.getByText(i18n.t('feedback.area'))).toBeOnTheScreen();
});

it('says that Klaipėda city is not covered', async () => {
  await renderRouter(routes, { initialUrl: '/setup/location' });
  await search('Klaipėda');
  expect(await screen.findByText(i18n.t('setup.locationKlaipedaCity'))).toBeOnTheScreen();
});

import type { TFunction } from 'i18next';

import { doneKey } from '@/lib/reminders';
import type { ScheduleData } from '@/lib/schedule';

import { widgetModel } from './model';

const t = ((key: string, options?: { count?: number }) => (options?.count ? `${key}:${options.count}` : key)) as unknown as TFunction;

const data: ScheduleData = {
  schemaVersion: 1,
  generatedAt: '',
  source: '',
  coverage: {},
  areas: [
    { id: 'h', kind: 'household', name: 'H', dates: ['2026-11-20', '2026-11-24'] },
    { id: 'g', kind: 'glass', name: 'G', dates: ['2026-11-24'] },
  ],
  locations: [{ id: 'loc', name: 'Riešė', type: 'k.', district: 'Avižienių', schedule: { household: { area: 'h' }, glass: { area: 'g' } } }],
};
const base = { data, place: { locationId: 'loc', choices: {} }, placeId: 'home', done: [], t, lang: 'en' };

describe('widgetModel', () => {
  it('shows the next pickup of the place', () => {
    expect(widgetModel({ ...base, now: new Date(2026, 10, 21, 12) })).toEqual({
      state: 'pickup',
      place: 'Riešė',
      when: 'home.inDays:3',
      date: 'Tuesday, November 24',
      kinds: [
        { kind: 'household', name: 'kinds.household' },
        { kind: 'glass', name: 'kinds.glass' },
      ],
      done: false,
    });
  });

  it('says tomorrow, uses the place name and marks a pickup the user dealt with', () => {
    const model = widgetModel({
      ...base,
      placeName: 'Namai',
      done: [doneKey('2026-11-24', 'household', 'home'), doneKey('2026-11-24', 'glass', 'home')],
      now: new Date(2026, 10, 23, 20),
    });
    expect(model).toMatchObject({ state: 'pickup', place: 'Namai', when: 'home.tomorrow', done: true });
  });

  it('asks to choose a place, or says nothing is coming', () => {
    expect(widgetModel({ ...base, place: null, now: new Date(2026, 10, 21) })).toEqual({ state: 'empty', message: 'widget.choosePlace' });
    expect(widgetModel({ ...base, now: new Date(2026, 10, 25) })).toEqual({ state: 'empty', place: 'Riešė', message: 'widget.nothing' });
  });
});

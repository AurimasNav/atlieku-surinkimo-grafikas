import {
  doneKey,
  MAX_PICKUP_REMINDERS,
  planReminders,
  pruneActions,
  type ReminderSettings,
  sortTimes,
  upcomingPickups,
} from './reminders';
import type { Area } from './schedule';

const area = (kind: Area['kind'], dates: string[]): Area => ({
  id: `${kind}-1`,
  kind,
  name: 'Test',
  dates,
});

const evening = { daysBefore: 1 as const, hour: 19, minute: 0 };
const morning = { daysBefore: 0 as const, hour: 6, minute: 0 };
const settings: ReminderSettings = { times: [evening] };

const pickupsOf = (plan: ReturnType<typeof planReminders>) =>
  plan.flatMap((item) => (item.type === 'pickup' ? [{ at: item.fireAt, ...item.pickup }] : []));

describe('upcomingPickups', () => {
  it('merges kinds collected on the same day and skips past dates', () => {
    const pickups = upcomingPickups(
      [area('glass', ['2026-10-14', '2026-10-20']), area('household', ['2026-10-01', '2026-10-14'])],
      new Date(2026, 9, 11, 12),
    );
    expect(pickups).toEqual([
      { date: '2026-10-14', kinds: ['household', 'glass'] },
      { date: '2026-10-20', kinds: ['glass'] },
    ]);
  });
});

describe('planReminders', () => {
  it('fires the evening before, in local time', () => {
    const [first] = planReminders([area('household', ['2026-10-14'])], settings, new Date(2026, 9, 11));
    expect(first.fireAt).toEqual(new Date(2026, 9, 13, 19, 0));
  });

  it('skips reminders whose time has already passed', () => {
    const plan = planReminders(
      [area('household', ['2026-10-12', '2026-10-19'])],
      settings,
      new Date(2026, 9, 11, 20, 0),
    );
    expect(pickupsOf(plan)).toHaveLength(1);
  });

  it('reminds of one pickup several times', () => {
    const plan = planReminders([area('household', ['2026-10-14'])], { times: [morning, evening] }, new Date(2026, 9, 11));
    expect(pickupsOf(plan).map((p) => p.at)).toEqual([new Date(2026, 9, 13, 19, 0), new Date(2026, 9, 14, 6, 0)]);
  });

  it('gives a waste type its own reminders, or none', () => {
    const plan = planReminders(
      [area('household', ['2026-10-14']), area('glass', ['2026-10-14']), area('packaging', ['2026-10-14'])],
      { times: [evening], kinds: { glass: [evening, morning], packaging: [] } },
      new Date(2026, 9, 11),
    );
    expect(pickupsOf(plan)).toEqual([
      { at: new Date(2026, 9, 13, 19, 0), date: '2026-10-14', kinds: ['household', 'glass'] },
      { at: new Date(2026, 9, 14, 6, 0), date: '2026-10-14', kinds: ['glass'] },
    ]);
  });

  it('leaves out pickups marked done and brings back snoozed ones', () => {
    const plan = planReminders(
      [area('household', ['2026-10-14']), area('glass', ['2026-10-14'])],
      { times: [evening, morning] },
      new Date(2026, 9, 13, 19, 5),
      {
        done: [doneKey('2026-10-14', 'household')],
        snoozed: [{ id: 'n1', fireAt: new Date(2026, 9, 13, 20, 5).toISOString(), pickup: { date: '2026-10-14', kinds: ['household', 'glass'] } }],
      },
    );
    expect(pickupsOf(plan)).toEqual([
      { at: new Date(2026, 9, 13, 20, 5), date: '2026-10-14', kinds: ['glass'] },
      { at: new Date(2026, 9, 14, 6, 0), date: '2026-10-14', kinds: ['glass'] },
    ]);
  });

  it('stays under the iOS limit and ends with a refresh reminder', () => {
    const dates = Array.from({ length: 200 }, (_, i) => {
      const d = new Date(2027, 0, 1 + i);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    });
    const plan = planReminders([area('household', dates)], { times: [evening, morning] }, new Date(2026, 11, 1));
    expect(plan).toHaveLength(MAX_PICKUP_REMINDERS + 1);
    expect(plan.at(-1)?.type).toBe('refresh');
    expect(plan.length).toBeLessThanOrEqual(64);
    // The earliest reminders are the ones kept.
    expect(plan[0].fireAt).toEqual(new Date(2026, 11, 31, 19, 0));
  });

  it('plans nothing when no area is selected', () => {
    expect(planReminders([], settings, new Date())).toEqual([]);
  });
});

describe('pruneActions', () => {
  it('forgets past pickups and snoozes that already went off', () => {
    const now = new Date(2026, 9, 14, 12);
    expect(
      pruneActions(
        {
          done: [doneKey('2026-10-13', 'glass'), doneKey('2026-10-14', 'glass')],
          snoozed: [
            { id: 'a', fireAt: new Date(2026, 9, 14, 11).toISOString(), pickup: { date: '2026-10-14', kinds: ['glass'] } },
            { id: 'b', fireAt: new Date(2026, 9, 14, 13).toISOString(), pickup: { date: '2026-10-15', kinds: ['glass'] } },
          ],
        },
        now,
      ),
    ).toEqual({
      done: [doneKey('2026-10-14', 'glass')],
      snoozed: [{ id: 'b', fireAt: new Date(2026, 9, 14, 13).toISOString(), pickup: { date: '2026-10-15', kinds: ['glass'] } }],
    });
  });
});

describe('sortTimes', () => {
  it('puts the evening before first', () => {
    expect(sortTimes([morning, { ...evening, hour: 21 }, evening])).toEqual([evening, { ...evening, hour: 21 }, morning]);
  });
});

describe('several places', () => {
  it('reminds of each place on its own and marks done per place', () => {
    const plan = planReminders(
      [
        { place: 'home', areas: [area('household', ['2026-10-14'])] },
        { place: 'summer', areas: [area('household', ['2026-10-14'])] },
      ],
      settings,
      new Date(2026, 9, 11),
      { done: [doneKey('2026-10-14', 'household', 'summer')], snoozed: [] },
    );
    expect(pickupsOf(plan)).toEqual([{ at: new Date(2026, 9, 13, 19, 0), date: '2026-10-14', kinds: ['household'], place: 'home' }]);
  });
});

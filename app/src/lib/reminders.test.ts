import { MAX_PICKUP_REMINDERS, planReminders, upcomingPickups } from './reminders';
import type { Area } from './schedule';

const area = (kind: Area['kind'], dates: string[]): Area => ({
  id: `${kind}-1`,
  kind,
  name: 'Test',
  dates,
});

const evening = { daysBefore: 1 as const, hour: 19, minute: 0 };

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
    const [first] = planReminders([area('household', ['2026-10-14'])], evening, new Date(2026, 9, 11));
    expect(first.fireAt).toEqual(new Date(2026, 9, 13, 19, 0));
  });

  it('skips reminders whose time has already passed', () => {
    const plan = planReminders(
      [area('household', ['2026-10-12', '2026-10-19'])],
      evening,
      new Date(2026, 9, 11, 20, 0),
    );
    const pickups = plan.filter((p) => p.type === 'pickup');
    expect(pickups).toHaveLength(1);
  });

  it('stays under the iOS limit and ends with a refresh reminder', () => {
    const dates = Array.from({ length: 200 }, (_, i) => {
      const d = new Date(2027, 0, 1 + i);
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    });
    const plan = planReminders([area('household', dates)], evening, new Date(2026, 11, 1));
    expect(plan).toHaveLength(MAX_PICKUP_REMINDERS + 1);
    expect(plan.at(-1)?.type).toBe('refresh');
    expect(plan.length).toBeLessThanOrEqual(64);
  });

  it('plans nothing when no area is selected', () => {
    expect(planReminders([], evening, new Date())).toEqual([]);
  });
});

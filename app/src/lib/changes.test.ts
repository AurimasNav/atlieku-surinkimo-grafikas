import { activeChanges, officialDates, pickupChanges } from './changes';
import type { Area } from './schedule';

const now = new Date(2026, 10, 21, 10);

describe('pickupChanges', () => {
  it('pairs a removed and an added date as a move', () => {
    expect(
      pickupChanges({ glass: ['2026-11-25', '2026-12-04'] }, { glass: ['2026-11-25', '2026-12-05'] }, now),
    ).toEqual([{ kind: 'glass', from: '2026-12-04', to: '2026-12-05' }]);
  });

  it('reports cancelled and extra pickups', () => {
    expect(
      pickupChanges(
        { household: ['2026-11-24', '2026-12-08'], packaging: ['2026-11-26', '2026-12-10'] },
        { household: ['2026-12-08'], packaging: ['2026-11-26', '2026-12-03', '2026-12-10'] },
        now,
      ),
    ).toEqual([
      { kind: 'household', from: '2026-11-24' },
      { kind: 'packaging', to: '2026-12-03' },
    ]);
  });

  it('ignores a newly published period, the past, far dates and new waste types', () => {
    expect(
      pickupChanges(
        { household: ['2026-11-10', '2026-11-24', '2027-01-20'], glass: [] },
        {
          // The old schedule ended on 2027-01-20, so the new dates after it aren't changes.
          household: ['2026-11-24', '2027-01-20', '2027-02-03'],
          glass: ['2026-11-30'],
          food: ['2026-11-28'],
        },
        now,
      ),
    ).toEqual([]);
  });

  it('ignores old dates that a new schedule starting later no longer lists', () => {
    expect(pickupChanges({ glass: ['2026-11-10', '2026-11-25'] }, { glass: ['2027-01-05', '2027-01-26'] }, now)).toEqual([]);
  });

  it('only looks a few weeks ahead', () => {
    expect(pickupChanges({ glass: ['2026-11-25', '2027-01-15'] }, { glass: ['2026-11-25', '2027-01-16'] }, now)).toEqual([]);
  });
});

describe('officialDates', () => {
  it('leaves out the schedules the user set up', () => {
    const areas: Area[] = [
      { id: 'a', kind: 'glass', name: 'A', dates: ['2026-12-01'] },
      { id: 'custom-household', kind: 'household', name: '', dates: ['2026-12-02'] },
    ];
    expect(officialDates(areas)).toEqual({ glass: ['2026-12-01'] });
  });
});

describe('activeChanges', () => {
  it('keeps a change until both its dates have passed', () => {
    const changes = [
      { kind: 'glass' as const, from: '2026-11-20', to: '2026-11-22' },
      { kind: 'glass' as const, from: '2026-11-19' },
    ];
    expect(activeChanges(changes, '2026-11-21')).toEqual([changes[0]]);
  });
});

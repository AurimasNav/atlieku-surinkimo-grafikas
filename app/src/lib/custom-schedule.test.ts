import { customDates } from './custom-schedule';

const today = new Date(2026, 9, 11); // Sunday, 11 October 2026

describe('customDates', () => {
  it('repeats every 2 weeks from the given date', () => {
    const dates = customDates({ start: '2026-10-15', every: 2, unit: 'week' }, today);
    expect(dates.slice(0, 3)).toEqual(['2026-10-15', '2026-10-29', '2026-11-12']);
  });

  it('continues a past start date on the same rhythm', () => {
    // Started on a Thursday in summer, every 2 weeks: the rhythm must not shift.
    const dates = customDates({ start: '2026-06-11', every: 2, unit: 'week' }, today);
    expect(dates[0]).toBe('2026-10-15');
    expect(new Set(dates.map((d) => new Date(d).getDay())).size).toBe(1);
  });

  it('keeps the weekday position monthly (2nd Tuesday)', () => {
    const dates = customDates({ start: '2026-10-13', every: 1, unit: 'month' }, today);
    expect(dates.slice(0, 4)).toEqual(['2026-10-13', '2026-11-10', '2026-12-08', '2027-01-12']);
  });

  it('treats a 5th weekday as the last one of the month', () => {
    const dates = customDates({ start: '2026-10-30', every: 1, unit: 'month' }, today); // 5th Friday
    expect(dates.slice(0, 3)).toEqual(['2026-10-30', '2026-11-27', '2026-12-25']);
  });

  it('supports every 3 months and covers about a year', () => {
    const dates = customDates({ start: '2026-10-13', every: 3, unit: 'month' }, today);
    expect(dates).toEqual(['2026-10-13', '2027-01-12', '2027-04-13', '2027-07-13', '2027-10-12']);
  });

  it('crosses daylight saving time without drifting', () => {
    const dates = customDates({ start: '2026-10-22', every: 1, unit: 'week' }, today);
    expect(dates.slice(0, 2)).toEqual(['2026-10-22', '2026-10-29']); // DST ends 25 Oct
  });
});

import { alarmOffset, buildIcs } from './ics';

describe('alarmOffset', () => {
  it('counts from midnight of the pickup day', () => {
    expect(alarmOffset({ daysBefore: 1, hour: 19, minute: 0 })).toBe('-PT5H');
    expect(alarmOffset({ daysBefore: 1, hour: 20, minute: 30 })).toBe('-PT3H30M');
    expect(alarmOffset({ daysBefore: 0, hour: 6, minute: 30 })).toBe('PT6H30M');
    expect(alarmOffset({ daysBefore: 0, hour: 0, minute: 0 })).toBe('PT0M');
  });
});

describe('buildIcs', () => {
  const ics = buildIcs({
    pickups: [
      { date: '2026-12-31', kinds: ['household', 'glass'] },
      { date: '2027-01-14', kinds: ['household'] },
    ],
    kindName: (kind) => ({ household: 'Mišrios', glass: 'Stiklas' })[kind as 'household' | 'glass'],
    timesFor: (kind) =>
      kind === 'glass'
        ? [{ daysBefore: 1, hour: 19, minute: 0 }, { daysBefore: 0, hour: 6, minute: 0 }]
        : [{ daysBefore: 1, hour: 19, minute: 0 }],
    description: 'Konteinerius išstumkite iki 7:00; ačiū',
    now: new Date('2026-11-21T10:00:00Z'),
  });
  const lines = ics.split('\r\n');

  it('writes one all-day event per pickup day, ending the next day', () => {
    expect(lines.filter((line) => line === 'BEGIN:VEVENT')).toHaveLength(2);
    expect(lines).toContain('DTSTART;VALUE=DATE:20261231');
    expect(lines).toContain('DTEND;VALUE=DATE:20270101');
    expect(lines).toContain('SUMMARY:Mišrios\\, Stiklas');
    expect(lines).toContain('UID:20261231-household-glass@siuksliaveze');
    expect(lines).toContain('DTSTAMP:20261121T100000Z');
  });

  it('adds each distinct reminder time once as an alarm', () => {
    const first = ics.slice(0, ics.indexOf('END:VEVENT'));
    expect(first.match(/TRIGGER:/g)).toHaveLength(2);
    expect(first).toContain('TRIGGER:-PT5H');
    expect(first).toContain('TRIGGER:PT6H');
  });

  it('escapes text and ends every line with CRLF', () => {
    expect(ics).toContain('DESCRIPTION:Konteinerius išstumkite iki 7:00\\; ačiū');
    expect(ics.endsWith('END:VCALENDAR\r\n')).toBe(true);
    expect(ics.replace(/\r\n/g, '')).not.toMatch(/\n/);
  });

  it('folds lines longer than 75 octets', () => {
    const long = buildIcs({
      pickups: [{ date: '2026-12-31', kinds: ['household'] }],
      kindName: () => 'Š'.repeat(60),
      timesFor: () => [],
      description: '',
    });
    for (const line of long.split('\r\n')) expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(long).toContain('\r\n Š');
  });
});
